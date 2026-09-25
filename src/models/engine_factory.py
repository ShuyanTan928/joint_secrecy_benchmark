"""Build a model engine: an API model (OpenRouter, Gemini), a local vLLM model, or the stub.

add_engine_args() adds the shared flags --engine and --preset; engine_from_args() builds the engine;
write_model_record() writes <out>.model.json beside an output so the manifest can name the model.
Every engine has .generate(prompts, max_tokens=, temperature=) -> list[str]; vLLM also takes choices=[...].
"""
from __future__ import annotations
import json
from pathlib import Path

DEFAULT_SEED = 20260620


def build_engine(kind: str, preset: str, tp: int = 2,
                 seed: int = DEFAULT_SEED, gpu_mem: float = 0.9, max_model_len: int | None = None,
                 reasoning: str | None = None, enforce_eager: bool = False):
    """kind 'vllm': a local tensor-parallel engine; 'api': an OpenRouter or Gemini preset or slug; 'stub': stored answers. tp, seed, gpu_mem and max_model_len apply to vLLM only."""
    if kind == "vllm":
        from src.models.vllm_engine import VLLMEngine
        kw = dict(tensor_parallel_size=tp, gpu_memory_utilization=gpu_mem, rng_seed=seed,
                  enforce_eager=enforce_eager)
        if max_model_len:
            kw["max_model_len"] = max_model_len
        return VLLMEngine.from_preset(preset, **kw)
    if kind == "api":
        from src.models.api_engine import APIEngine
        return APIEngine.from_preset(preset, reasoning=reasoning)
    if kind == "stub":
        from src.models.stub_engine import StubEngine
        return StubEngine()
    raise ValueError(f"unknown engine kind {kind!r} (use 'vllm', 'api' or 'stub')")


def add_engine_args(ap, engine: str = "api", preset: str = "or-claude-opus"):
    """The model flags every script shares. Defaults to Claude Opus 5.5 through OpenRouter."""
    g = ap.add_argument_group("model")
    g.add_argument("--engine", default=engine, choices=["api", "vllm", "stub"], help="api: OpenRouter/Gemini preset or slug; vllm: local model; stub: replays stored answers, no cost, for a dry run")
    g.add_argument("--preset", default=preset, help="an API preset (or-claude-opus, or-claude-sonnet, or-gpt-5, gemini-pro), an OpenRouter slug, or a vLLM preset (qwen3-32b)")
    g.add_argument("--tp", type=int, default=4, help="vllm: GPUs to shard over")
    g.add_argument("--gpu-mem", type=float, default=0.90, help="vllm: fraction of each GPU's memory")
    g.add_argument("--max-model-len", type=int, default=16384, help="vllm: context length")
    g.add_argument("--no-eager", dest="eager", action="store_false", default=True, help="vllm: allow CUDA graphs (faster start is --eager, the default)")
    return ap


def engine_from_args(a):
    if a.engine in ("api", "stub"):
        return build_engine(a.engine, a.preset)
    return build_engine("vllm", a.preset, tp=a.tp, gpu_mem=a.gpu_mem, max_model_len=a.max_model_len, enforce_eager=a.eager)


def model_record(engine, a) -> dict:
    return {"engine": a.engine, "preset": a.preset, "model": getattr(engine, "model_name", None) or type(engine).__name__}


def write_model_record(out_path, engine, a):
    """<out>.model.json beside an output file: which model produced it."""
    Path(str(out_path) + ".model.json").write_text(json.dumps(model_record(engine, a), indent=1))
