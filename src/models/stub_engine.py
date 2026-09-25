"""A stub engine: replays stored answers, so any command runs end to end without a model (--engine stub).

The topic classifier gets a topic, the people and audit passes get "none", the quiet-people check gets
"no role", and the generation steps get one real chain's answers from STUB_STATE (default
logs/fourstep_opus37.json). Calls are counted in .calls.
"""
import json
import os
import random
from pathlib import Path

TOPICS = ["business and finance", "careers", "family and relationships", "personal finance", "real estate",
          "technology and computing", "travel", "sports", "education", "law"]


class StubEngine:
    model_name = "stub (replays stored answers)"

    def __init__(self, state: str | None = None, seed: int = 0):
        self.calls = 0; self.rng = random.Random(seed); self.last_meta = {"finish_reason": "stop", "in": 0, "out": 0}
        p = Path(state or os.environ.get("STUB_STATE", "logs/fourstep_opus37.json"))
        self.chain = self.secret = None
        if p.exists():
            st = json.loads(p.read_text())
            self.chain = next((c for c in st.get("chains", []) if c.get("emails") and not c.get("error")), None)
            if self.chain:
                self.secret = next(s for s in st["secrets"] if s["asked_topic"] == self.chain["topic"] and s["kind"] == self.chain["kind"])

    def answer(self, prompt: str) -> str:
        tail = prompt.rstrip()[-12:].lower()
        if tail.endswith("topic:"): return self.rng.choice(TOPICS)
        if tail.endswith("people:") or tail.endswith("names:"): return "none"
        if "signed_name" in prompt: return json.dumps({"signed_name": "", "role_fixed": "no", "role": "", "evidence": ""})
        if self.chain is None: return "{}"
        if '"cases"' in prompt: return json.dumps({"cases": [{k: self.secret[k] for k in ("actor", "fact", "secret", "victim")}]})
        if "## The secret to place" in prompt: return json.dumps(self.secret["clues"][self.chain["pattern"]])
        if '"cast"' in prompt: return json.dumps(dict(self.chain["emails_placeholders"], cast=self.chain["cast_by_model"]))
        if '"stake"' in prompt: return json.dumps(self.chain["plots"])
        return "{}"

    def generate(self, prompts, max_tokens=1024, temperature=0.0, **kwargs):
        if isinstance(prompts, str): prompts = [prompts]
        out = []
        for p in prompts:
            self.calls += 1; a = self.answer(p); self.last_meta = {"finish_reason": "stop", "in": len(p) // 4, "out": len(a) // 4}; out.append(a)
        return out
