"""Keep the release audit complete and resumable."""
import asyncio
from http import HTTPStatus
from types import SimpleNamespace

import pytest

from src.tester.mailbox import MailboxEnv


def test_read_keeps_full_body():
    body = "First line\n" + "Context matters. " * 200 + "\nFinal evidence."
    env = MailboxEnv([[{"id": "one", "body": body}]], set())

    assert body in env.read("t1")


def test_reasoning_note_has_room(monkeypatch):
    from src.tester import task

    seen = []

    async def generate(prompt, config):
        seen.append(config.max_tokens)
        return SimpleNamespace(completion="A note")

    model = SimpleNamespace(config=SimpleNamespace(reasoning_effort="high"), generate=generate)
    monkeypatch.setattr(task, "get_model", lambda: model)
    asyncio.run(task._short("Evidence", max_tokens=300))

    assert seen[0] >= 8192


def test_cache_resumes(monkeypatch, tmp_path):
    from src.models import azure_engine

    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(id="response", model="gpt-6-sol", status="completed",
                               output_text=kwargs["input"].upper(), usage=None, incomplete_details=None)

    monkeypatch.setenv("BENCHMARK_AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("BENCHMARK_AZURE_OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(azure_engine, "OpenAI", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    path = tmp_path / "cache.jsonl"
    engine = azure_engine.AzureEngine("gpt-6-sol", checkpoint=str(path), workers=1)
    assert engine.generate(["a", "b", "a"]) == ["A", "B", "A"]

    resumed = azure_engine.AzureEngine("gpt-6-sol", checkpoint=str(path), workers=1)
    assert resumed.generate(["b", "a"]) == ["B", "A"]
    assert len(seen) == 2
    assert seen[0]["reasoning"] == {"effort": "medium"}
    assert "temperature" not in seen[0]
    assert "test-secret" not in path.read_text()

    changed = azure_engine.AzureEngine("gpt-6-sol", reasoning="high", checkpoint=str(path), workers=1)
    changed.generate("a")
    assert len(seen) == 3


def test_empty_answer_is_rejected(monkeypatch, tmp_path):
    from src.models import azure_engine

    response = SimpleNamespace(id="response", model="gpt-6-sol", status="completed",
                               output_text="", usage=None, incomplete_details=None)
    monkeypatch.setenv("BENCHMARK_AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("BENCHMARK_AZURE_OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(azure_engine, "OpenAI", lambda **kwargs: SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: response)))
    engine = azure_engine.AzureEngine("gpt-6-sol", checkpoint=str(tmp_path / "cache.jsonl"), workers=1)

    with pytest.raises(RuntimeError, match="no complete answer"):
        engine.generate("Who is named?")


def test_sweep_sends_high_effort(monkeypatch):
    import json
    import httpx
    from src.models.azure_engine import azure_model

    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(HTTPStatus.OK, json={
            "id": "resp_test", "object": "response", "created_at": 1,
            "status": "completed", "model": "gpt-6-sol",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": "OK", "annotations": []}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        })

    monkeypatch.setenv("BENCHMARK_AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("BENCHMARK_AZURE_OPENAI_API_KEY", "test-secret")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            model = azure_model("openai/gpt-6-sol", "high", http_client=client)
            return await model.generate("Return OK")

    result = asyncio.run(run())
    assert result.completion == "OK"
    assert seen[0]["model"] == "gpt-6-sol"
    assert seen[0]["reasoning"]["effort"] == "high"
    assert seen[0]["max_output_tokens"] == 16384
    assert seen[0]["store"] is False


def test_manifest_records_effort(tmp_path):
    import json
    from scripts.make_release import model_of

    output = tmp_path / "extract.jsonl"
    output.with_name(output.name + ".model.json").write_text(json.dumps({
        "model": "gpt-6-sol", "engine": "azure", "preset": "gpt-6-sol", "reasoning_effort": "medium",
    }))

    assert "reasoning medium" in model_of(output, "unrecorded")


def test_sweep_requires_full_scan():
    from src.tester.core import MailboxSession, MailboxSettings

    env = MailboxEnv([[{"id": "one", "body": "Evidence"}]], set())
    settings = MailboxSettings(scan=True, candidate_limit=5, candidates_exact=False)
    session = MailboxSession(env, settings, 0)
    session.read("t1")
    candidates = [{"secret": "A supported fact", "evidence_email_ids": ["e1"]}]

    assert not session.submit_candidates(candidates).accepted
    session.segment(0)
    assert session.submit_candidates(candidates).accepted
