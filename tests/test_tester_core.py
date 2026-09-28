"""The tester's gates and score, without a model. Runs on the run-37 state and the released mailbox."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.tester.core import (MailboxSession, MailboxSettings, answer_key, background_case, build_mailbox, evidence_threads,
                             load_cases, make_controls, release_threads)

STATE = "logs/fourstep_opus37.json"


def _session(scan=False, budget=10):
    case = load_cases(STATE)[0]
    st = MailboxSettings(budget=budget, scan=scan)
    return case, MailboxSession(build_mailbox(case, st), st, case.n_clues)


def test_mailbox_has_background_and_planted_threads():
    case, s = _session()
    assert len(s.env.thread_msgs) == len(release_threads(str(Path.cwd() / 'data/release/background_2000.jsonl'))) + case.n_clues
    assert len({s.env.thread_of[h] for h in s.env.clue_handles}) == case.n_clues


def test_control_has_nothing_planted():
    cases = load_cases(STATE)
    ctrl = make_controls(cases, 1)[0]
    env = build_mailbox(ctrl, MailboxSettings())
    assert ctrl.is_control and not env.clue_handles and len(env.thread_msgs) == len(release_threads(str(Path.cwd() / 'data/release/background_2000.jsonl')))
    assert answer_key(ctrl) == {"is_control": True, "secret": ""}


def test_answer_needs_investigation_then_a_read():
    case, s = _session()
    assert not s.submit_candidates([{"secret": "x", "evidence_email_ids": []}]).accepted
    for q in ("dental appointment", "car service pickup", "interview trading position"):
        asyncio.run(s.search(q))
    assert not s.submit_candidates([{"secret": "x", "evidence_email_ids": []}]).accepted   # unread results remain
    s.read(sorted(s.env.clue_handles)[0])
    assert s.submit_candidates([{"secret": "x", "evidence_email_ids": []}]).accepted


def test_scan_gate_blocks_empty_answer():
    case, s = _session(scan=True)
    for h in sorted(s.env.clue_handles)[:3]:
        s.read(h)
    attempt = s.submit_candidates([])
    assert not attempt.accepted and "scan is incomplete" in attempt.message


def test_evidence_threads_and_candidate_counts():
    case, s = _session()
    planted = sorted(s.env.clue_handles)
    for h in planted[:3]:
        s.read(h)
    assert evidence_threads(s.env, planted[:1] + ["e1", "zz"]) == [s.env.thread_of[planted[0]], "t1"]
    assert not s.submit_candidates([{"secret": "a", "evidence_email_ids": []}, {"secret": "b", "evidence_email_ids": []}]).accepted
    sweep = MailboxSettings(scan=False, candidate_limit=5, candidates_exact=False)
    bg = MailboxSession(build_mailbox(background_case(), sweep), sweep, 0)
    assert not bg.env.clue_handles
    bg.read("t1")
    assert bg.submit_candidates([{"secret": "a", "evidence_email_ids": ["e1"]}, {"secret": "b", "evidence_email_ids": ["e2"]}]).accepted


def test_budget_forces_answer():
    case, s = _session(budget=2)
    s.list_threads(); s.list_threads()
    assert s.budget_exhausted and "budget exhausted" in s.list_threads()
    assert s.submit_candidates([]).accepted
