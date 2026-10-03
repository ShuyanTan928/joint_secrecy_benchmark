"""The direct feed without a model: the feed's contents, the seeded nested noise, the rendering, the samples and the answer parse.
Runs on the keystone30 state and the released background."""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.tester.core import chain_threads, judge_emails, load_cases, make_controls, planted_threads
from src.tester.direct import build_feed, build_samples, draw_order, parse_levels, prompt_text, read_answer, release_emails, render

STATE = "data/benchmark/keystone30/state.json"


def _case():
    return load_cases(STATE)[0]


def _planted_ids(case):
    return {m["id"] for th in planted_threads(case) for m in th}


def test_feed_holds_every_planted_email_and_the_noise_in_date_order():
    case = _case(); feed = build_feed(case, 100)
    assert len(feed.emails) == 100 + len(_planted_ids(case))
    assert {feed.emails[int(h[1:]) - 1]["id"] for h in feed.planted} == _planted_ids(case)
    assert [m["handle"] for m in feed.emails] == [f"e{i}" for i in range(1, len(feed.emails) + 1)]
    dates = [m["date"] for m in feed.emails]
    assert dates == sorted(dates)


def test_noise_zero_is_the_planted_emails_alone():
    case = _case(); feed = build_feed(case, 0)
    assert len(feed.emails) == len(_planted_ids(case)) == len(feed.planted)


def test_noise_is_seeded_and_nested():
    case = _case(); ids = lambda f: {m["id"] for m in f.emails} - _planted_ids(case)
    a, b, c = build_feed(case, 100), build_feed(case, 100), build_feed(case, 200)
    assert ids(a) == ids(b) and ids(a) < ids(c) and len(ids(c)) == 200
    assert ids(a) != ids(build_feed(case, 100, seed=1))
    assert ids(a) != ids(build_feed(load_cases(STATE)[1], 100))   # each chain its own draw


def test_draw_puts_the_cast_first_then_recurring_senders():
    case = _case(); pool = release_emails(str(Path.cwd() / "data/release/background_2000.jsonl"))
    cast = {m["from"] for th in planted_threads(case) for m in th}
    per_sender = Counter(m["from"] for m in pool)
    order = draw_order(pool, case)
    n_cast = sum(1 for m in pool if m["from"] in cast); n_rec = sum(1 for m in pool if m["from"] not in cast and per_sender[m["from"]] > 1)
    assert n_cast > 0 and all(pool[i]["from"] in cast for i in order[:n_cast])
    assert all(per_sender[pool[i]["from"]] > 1 for i in order[n_cast:n_cast + n_rec])
    assert all(per_sender[pool[i]["from"]] == 1 for i in order[n_cast + n_rec:]) and sorted(order) == list(range(len(pool)))
    feed = build_feed(case, 100)
    assert sum(1 for m in feed.emails if m["id"].startswith("e_") and m["from"] in cast) == n_cast


def test_plain_prompt_has_no_rule_and_the_same_form():
    feed = build_feed(_case(), 3)
    plain = prompt_text(feed, 1, "prompts/direct_plain.md")
    assert plain.startswith("Here is a mailbox.") and "keeper" not in plain and '"candidates"' in plain and "<<" not in plain


def test_control_has_the_same_noise_and_nothing_planted():
    cases = load_cases(STATE); ctrl = make_controls(cases, 1)[0]
    feed, ctrl_feed = build_feed(cases[0], 50), build_feed(ctrl, 50)
    assert not ctrl_feed.planted and len(ctrl_feed.emails) == 50
    assert {m["id"] for m in ctrl_feed.emails} == {m["id"] for m in feed.emails} - _planted_ids(cases[0])


def test_render_shows_handles_and_no_recipients():
    feed = build_feed(_case(), 5); text = render(feed)
    assert text.startswith("[e1] From: ") and f"[{feed.emails[-1]['handle']}] From: " in text
    lines = text.split("\n")
    heads = [i for i, l in enumerate(lines) if re.match(r"^\[e\d+\] From: ", l)]
    assert len(heads) == len(feed.emails)
    assert all(lines[i + 1].startswith("Subject: ") for i in heads)   # a header is sender, date and subject only; no recipients
    assert all("<" not in lines[i] for i in heads)                    # bare addresses, as the release has them
    prompt = prompt_text(feed, 2)
    assert "<<" not in prompt and "return 2 ranked" in prompt


def test_samples_cover_every_level_and_skip_the_empty_control():
    samples = build_samples(state_path=STATE, levels=(0, 100), n_controls=1, limit=1)
    assert [s.id for s in samples] == ["00-lie-family-and-relations-n0", "00-lie-family-and-relations-n100", "00-lie-family-and-relations-ctrl-n100"]
    assert samples[1].metadata["n_emails"] == 100 + len(samples[1].metadata["planted_handles"])
    assert samples[2].metadata["is_control"] and not samples[2].metadata["planted_handles"]
    assert parse_levels("500,0,100,100") == (500, 0, 100)


def test_read_answer_keeps_to_the_limit_and_reads_nothing_from_prose():
    two = '{"candidates": [{"secret": "a keeps x from b", "evidence_email_ids": ["e3", "e9"]}, {"secret": "c keeps y from d", "evidence_email_ids": []}]}'
    cands, n, parsed = read_answer("Here is my answer:\n" + two, 1)
    assert parsed and n == 2 and cands == [{"secret": "a keeps x from b", "evidence_email_ids": ["e3", "e9"]}]
    assert read_answer('{"candidates": []}', 1) == ([], 0, True)
    assert read_answer("I found nothing.", 1) == ([], 0, False)


def test_judge_sees_the_planted_emails_with_their_recipients():
    case = _case(); text = judge_emails(chain_threads(case.chain))
    msgs = [m for th in chain_threads(case.chain) for m in th]
    assert text.startswith("thread 1 (") and all(m["subject"] in text for m in msgs) and "  To: " in text
    shell = (Path.cwd() / "prompts" / "match.md").read_text()
    assert "<<EMAILS>>" in shell and "<<SECRET>>" in shell and "<<FINDING>>" in shell
    assert judge_emails([[{"from": "x@y", "date": "2001-01-01", "subject": "s", "body": "t"}]]) == "thread 1 (1 message):\nFrom: x@y  Date: 2001-01-01\nSubject: s\nt\n"
