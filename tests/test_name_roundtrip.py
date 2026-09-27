"""Preserve detected identities through replacement and audit."""
import json
import sys

from scripts.anonymize_llm import merge, name_tokens
from scripts.audit_names import load_fakes
from scripts.extract_people import parse


def test_alias_roots_are_resolved():
    people = [
        {"email_id": "a", "people": [{"forms": ["Alex Smith", "Alex"], "addr": "z@example.test"}]},
        {"email_id": "b", "people": [{"forms": ["Alex Smith"], "addr": "a@example.test"}]},
    ]
    union, mentions = merge(people)

    assert all(key == union.find(key) for values in mentions.values() for _, key in values)


def test_reversed_name_is_kept():
    people = parse("Laura Giambrone | unknown", "Giambrone, Laura")

    assert people == [{"forms": ["Giambrone, Laura"], "addr": None}]
    assert name_tokens(people[0]["forms"][0]) == ["Laura", "Giambrone"]


def _anonymize(monkeypatch, tmp_path, addresses, name="Rob", body=None):
    from scripts import anonymize_llm

    rows = [{"email_id": str(i), "from": addr, "subject": "Hello", "body": body or f"{name}\n{addr}"}
            for i, addr in enumerate(addresses)]
    people = [{"email_id": row["email_id"], "people": [{"forms": [name], "addr": row["from"]}]} for row in rows]
    source, extract, output = [tmp_path / name for name in ("source.jsonl", "people.jsonl", "anon.jsonl")]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    extract.write_text("".join(json.dumps(row) + "\n" for row in people))
    monkeypatch.setattr(sys, "argv", ["anonymize_llm", "--in", str(source), "--extract", str(extract), "--out", str(output)])
    monkeypatch.setattr(anonymize_llm, "write_unused_names", lambda *args, **kwargs: None)
    assert anonymize_llm.main() == 0
    return output, output.with_name(output.name + ".map.json")


def test_solo_map_keeps_aliases(monkeypatch, tmp_path):
    output, mapping = _anonymize(monkeypatch, tmp_path, ["a@example.test", "b@example.test"])
    fakes = load_fakes(mapping)
    rows = [json.loads(line) for line in output.read_text().splitlines()]

    assert all(row["body"].splitlines()[0].lower() in fakes for row in rows)


def test_address_anchors_nickname(monkeypatch, tmp_path):
    output, mapping = _anonymize(monkeypatch, tmp_path, ["robert.smith@example.test", "robert.jones@example.test"])
    mapped = json.loads(mapping.read_text())["people"]
    rows = [json.loads(line) for line in output.read_text().splitlines()]

    assert rows[0]["body"].splitlines()[0] == mapped["Robert Smith"]["fake"].split()[0]
    assert rows[1]["body"].splitlines()[0] == mapped["Robert Jones"]["fake"].split()[0]


def test_name_case_is_preserved(monkeypatch, tmp_path):
    output, mapping = _anonymize(monkeypatch, tmp_path, ["robert.smith@example.test"], body="ROB")
    first = json.loads(mapping.read_text())["people"]["Robert Smith"]["fake"].split()[0]

    assert json.loads(output.read_text())["body"] == first.upper()


def test_tagged_word_name_is_kept(monkeypatch, tmp_path):
    text = "Grant\nWe need grant grant grant grant grant grant grant approval."
    output, _ = _anonymize(monkeypatch, tmp_path, ["a@example.test"], name="Grant", body=text)
    body = json.loads(output.read_text())["body"]

    assert not body.startswith("Grant")
    assert body.splitlines()[1] == text.splitlines()[1]


def test_rendered_login_is_known(monkeypatch, tmp_path):
    output, mapping = _anonymize(monkeypatch, tmp_path, ["robert.smith@example.test"], name="rsmith")
    name = json.loads(output.read_text())["body"].splitlines()[0]

    assert name.lower() in load_fakes(mapping)


def test_general_is_a_title():
    assert name_tokens("General Sani Abacha") == ["Sani", "Abacha"]


def test_normalized_lowercase_name(monkeypatch, tmp_path):
    output, _ = _anonymize(monkeypatch, tmp_path, ["a@example.test"], name="Max", body="max\n" * 7)

    assert "max" not in json.loads(output.read_text())["body"]


def test_glued_signature_is_replaced(monkeypatch, tmp_path):
    output, _ = _anonymize(monkeypatch, tmp_path, ["a@example.test"], name="Donna", body="DonnaAt 11:08 AM")

    assert not json.loads(output.read_text())["body"].startswith("Donna")


def test_glued_name_keeps_suffix(monkeypatch, tmp_path):
    text = "Alex Smithwww.example.test\nAlex Smithand colleagues"
    output, _ = _anonymize(monkeypatch, tmp_path, ["a@example.test"], name="Alex Smith", body=text)
    body = json.loads(output.read_text())["body"]

    assert "Smith" not in body
    assert "www." in body
    assert "and colleagues" in body


def test_wrapped_full_name_is_kept():
    people = parse("Alex River Smith, Alex | unknown", "Alex River\nSmith wrote to Alex")

    assert people == [{"forms": ["Alex River\nSmith", "Alex"], "addr": None}]
