"""A content-filtered generation call goes to the fallback model, once, and is recorded on the chain."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import generate   # noqa: E402


class Fake:
    def __init__(self, out, reason="stop"):
        self.out, self.last_meta, self.calls = out, {"finish_reason": reason}, 0
    def generate(self, prompt, max_tokens=0, temperature=0.0, **kw):
        self.calls += 1; return [self.out]


def test_filtered_answer_goes_to_the_fallback_without_a_second_try(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "RAW_LOG", tmp_path / "raw.jsonl")
    gen, fb = Fake("", "content_filter"), Fake('{"clues": [1]}')
    monkeypatch.setattr(generate, "GEN", gen); monkeypatch.setattr(generate, "FALLBACK", fb)
    generate.TL.rec = {}
    assert generate.chat_json("# Write the emails\n\nhello") == {"clues": [1]}
    assert gen.calls == 1 and fb.calls == 1 and generate.TL.rec["fallback"] == ["# Write the emails"]


def test_plain_empty_answer_is_retried_once_then_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "RAW_LOG", tmp_path / "raw.jsonl")
    gen, fb = Fake("", "stop"), Fake('{"x": 1}')
    monkeypatch.setattr(generate, "GEN", gen); monkeypatch.setattr(generate, "FALLBACK", fb); monkeypatch.setattr(generate.time, "sleep", lambda s: None)
    generate.TL.rec = {}
    assert generate.chat_json("# Lay out the story") == {"x": 1}
    assert gen.calls == 2 and fb.calls == 1
