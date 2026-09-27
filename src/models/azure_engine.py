"""Checkpointed Azure Responses calls for the mailbox's independent passes."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

DEFAULT_OUTPUT_TOKENS = 8192
DEFAULT_WORKERS = 16
SWEEP_OUTPUT_TOKENS = 16384
PROGRESS_INTERVAL = 50
TOKENS_PER_MILLION = 1_000_000
INPUT_PER_MILLION = 2.0
OUTPUT_PER_MILLION = 10.0
CACHE_READ_PER_MILLION = 0.2
CACHE_WRITE_PER_MILLION = 2.5
SWEEP_MODEL = "openai/gpt-6-sol"
ENV_PAIRS = (
    ("BENCHMARK_AZURE_OPENAI_ENDPOINT", "BENCHMARK_AZURE_OPENAI_API_KEY"),
    ("FOUNDRY_API_BASE", "FOUNDRY_API_KEY"),
    ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"),
)


def azure_connection() -> tuple[str, str]:
    """Keep provider credentials paired with their own endpoint."""
    for endpoint_var, key_var in ENV_PAIRS:
        endpoint, key = os.getenv(endpoint_var), os.getenv(key_var)
        if not endpoint or not key:
            continue
        base = endpoint.rstrip("/")
        if base.endswith("/responses"):
            base = base.removesuffix("/responses")
        if not base.endswith("/openai/v1"):
            base += "/openai/v1"
        if not base.startswith("https://"):
            raise ValueError("Azure requires an HTTPS endpoint")
        return base, key
    raise ValueError("Set a paired Azure endpoint and API key")


def azure_model(name: str, effort: str, *, http_client=None):
    """Configure Inspect's Responses transport without changing model identity."""
    from inspect_ai.model import GenerateConfig, ModelCost, ModelInfo, get_model, set_model_info

    if name != SWEEP_MODEL:
        raise ValueError("This release's Azure sweep requires openai/gpt-6-sol")
    base, key = azure_connection()
    # Inspect 0.3.260 needs this capability family to transmit GPT-6 reasoning.
    set_model_info(name, ModelInfo(model="GPT-6 Sol", family="gpt-5.6", reasoning=True,
                                  context_length=1_050_000, output_tokens=128_000,
                                  cost=ModelCost(input=INPUT_PER_MILLION, output=OUTPUT_PER_MILLION,
                                                 input_cache_read=CACHE_READ_PER_MILLION,
                                                 input_cache_write=CACHE_WRITE_PER_MILLION)))
    transport = {} if http_client is None else {"http_client": http_client}
    return get_model(name, base_url=base, api_key=key, responses_api=True, responses_store=False,
                     memoize=False, config=GenerateConfig(reasoning_effort=effort, reasoning_summary="none",
                                                         max_tokens=SWEEP_OUTPUT_TOKENS, max_retries=3,
                                                         timeout=180), **transport)


class AzureEngine:
    def __init__(self, model_name: str, *, reasoning: str = "medium",
                 checkpoint: str, workers: int = DEFAULT_WORKERS):
        if workers < 1:
            raise ValueError("workers must be positive")
        self.model_name = model_name
        self._reasoning = reasoning
        self._workers = workers
        self._path = Path(checkpoint)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        self._usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
        self._base, key = azure_connection()
        self._client = OpenAI(base_url=self._base, api_key=key, timeout=180, max_retries=3)
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line in self._path.read_text().splitlines():
            row = json.loads(line)
            self._count(row)
            if row["status"] == "completed" and row.get("text"):
                self._cache[row["key"]] = row["text"]

    def _count(self, row: dict) -> None:
        self._usage["calls"] += 1
        for name in ("input_tokens", "output_tokens"):
            self._usage[name] += row.get("usage", {}).get(name, 0)

    def _save(self, row: dict) -> None:
        # Flush each paid response so interruptions retain completed work.
        with self._lock:
            with self._path.open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._count(row)
            if row["status"] == "completed" and row.get("text"):
                self._cache[row["key"]] = row["text"]

    def _key(self, prompt: str, max_tokens: int) -> str:
        data = [self._base, self.model_name, self._reasoning, max_tokens, prompt]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()

    def _request(self, key: str, prompt: str, max_tokens: int) -> str:
        # One larger retry covers reasoning that exhausted the initial allowance.
        for limit in (max_tokens, max_tokens * 2):
            response = self._client.responses.create(
                model=self.model_name, input=prompt, store=False,
                reasoning={"effort": self._reasoning}, max_output_tokens=limit,
            )
            row = {"key": key, "response_id": response.id, "model": response.model,
                   "reasoning_effort": self._reasoning, "max_output_tokens": limit,
                   "status": response.status, "text": response.output_text.strip(),
                   "usage": response.usage.model_dump() if response.usage else {}}
            self._save(row)
            if row["status"] == "completed" and row["text"]:
                return row["text"]
            reason = getattr(response.incomplete_details, "reason", None)
            if reason != "max_output_tokens":
                break
        raise RuntimeError(f"Azure returned no complete answer; checkpoint key {key}")

    def generate(self, prompts: str | list[str], max_tokens: int = DEFAULT_OUTPUT_TOKENS,
                 temperature: float = 0.0, **kwargs) -> list[str]:
        if isinstance(prompts, str):
            prompts = [prompts]
        keyed = [(self._key(prompt, max_tokens), prompt) for prompt in prompts]
        pending = {key: prompt for key, prompt in keyed if key not in self._cache}
        print(f"Azure: {len(keyed)} prompts, {len(pending)} uncached, effort {self._reasoning}", flush=True)
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            futures = [pool.submit(self._request, key, prompt, max_tokens) for key, prompt in pending.items()]
            for completed, future in enumerate(as_completed(futures), 1):
                future.result()
                if completed % PROGRESS_INTERVAL == 0 or completed == len(futures):
                    print(f"  completed {completed}/{len(futures)}; {self.record()['usage']}", flush=True)
        return [self._cache[key] for key, _ in keyed]

    def record(self) -> dict:
        usage = dict(self._usage)
        usage["estimated_standard_usd"] = round(
            (usage["input_tokens"] * INPUT_PER_MILLION
             + usage["output_tokens"] * OUTPUT_PER_MILLION) / TOKENS_PER_MILLION, 4)
        return {"provider": "Azure OpenAI", "endpoint": self._base, "api": "Responses",
                "reasoning_effort": self._reasoning, "checkpoint": str(self._path), "usage": usage}
