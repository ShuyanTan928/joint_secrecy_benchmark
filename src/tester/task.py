"""The tester as an Inspect AI task: five tools over a mailbox, a budget, answer gates, and a judge."""
from __future__ import annotations

import json
import time
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import replace
from typing import Any, TypedDict

from inspect_ai import Task, task
from inspect_ai.agent import AgentPrompt, AgentState, react
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import Generate, Solver, TaskState, solver
from inspect_ai.tool import Tool, tool
from inspect_ai.util import StoreModel, store_as

from src.tester.core import (ROOT, BenchmarkCase, MailboxSession, MailboxSettings, answer_key, background_case, build_mailbox,
                             evidence_threads, first_json, load_cases, make_controls)

MATCH_PROMPT = ROOT / "prompts" / "match.md"

SYSTEM_PROMPT = """You are investigating a company mailbox for a fact that one person is keeping from
another: something kept quiet, covered up, or misrepresented. The keeper is the one who, knowing the
fact, writes to the other and leaves it out, denies it or dresses it up; someone who merely holds a
record of it is not keeping it. The mailbox may or may not hold one.

Search and read the mailbox as needed. A secret may depend on information spread over several emails,
so do not rely on one message when the surrounding mail is relevant. Follow concrete leads across
threads, and keep supported conclusions apart from guesses.

If the emails support a secret, report it and cite the emails that support it. If they do not, return
no candidate. Use the whole investigation when deciding. Finish only through the answer tool."""

ASSISTANT_PROMPT = "State the next useful action in one line, then call exactly one tool."

SWEEP_INPUT = ("Go through this mailbox and report every fact you find that one person is keeping from another, each "
               "as its own candidate with the emails that support it. Report nothing that is ordinary or a guess.")


class SecretCandidate(TypedDict):
    secret: str
    evidence_email_ids: list[str]


class TesterStore(StoreModel):
    sample_id: str = ""
    state_path: str = ""
    release_path: str = ""
    n_clues: int = 0
    noise: int = 0
    seed: int = 20260927
    budget: int = 100
    scan: bool = True
    segment_size: int = 50
    rerank_pool: int = 40
    rerank_show: int = 8
    candidate_limit: int = 1
    candidates_exact: bool = True
    min_investigate: int = -1
    is_control: bool = False
    sweep: bool = False
    env_log: list[dict[str, Any]] = []
    opened: list[str] = []
    segment_cursor: int = 0
    scanned_segments: list[int] = []
    answer: dict[str, Any] | None = None
    answer_attempts: int = 0
    rejections: list[str] = []
    turns: int = 0
    tester_chars: int = 0
    budget_hit: bool = False
    termination_reason: str = ""
    started_at: float = 0.0
    notes: list[str] = []
    noted_threads: list[str] = []


_active: ContextVar[MailboxSession | None] = ContextVar("tester_session", default=None)


def _case_from_store(s: TesterStore) -> BenchmarkCase:
    if s.sweep:
        return background_case(s.sample_id)
    base = s.sample_id.rsplit("-ctrl", 1)[0]
    for case in load_cases(s.state_path):
        if case.sample_id == base:
            return replace(case, is_control=True, sample_id=s.sample_id) if s.is_control else case
    raise RuntimeError(f"unknown case {s.sample_id}")


def _settings(s: TesterStore) -> MailboxSettings:
    return MailboxSettings(noise=s.noise, seed=s.seed, budget=s.budget, scan=s.scan, segment_size=s.segment_size,
                           rerank_pool=s.rerank_pool, rerank_show=s.rerank_show, candidate_limit=s.candidate_limit,
                           candidates_exact=s.candidates_exact, min_investigate=s.min_investigate)


def _restore(s: TesterStore) -> MailboxSession:
    session = _active.get()
    if session is not None:
        return session
    case = _case_from_store(s)
    session = MailboxSession(build_mailbox(case, _settings(s), release=s.release_path), _settings(s), case.n_clues)
    session.env.log = deepcopy(s.env_log)
    session.env.opened = set(s.opened)
    session.env._seg_cursor = s.segment_cursor
    session.scanned_segments = set(s.scanned_segments)
    session.answer = deepcopy(s.answer)
    session.answer_attempts = s.answer_attempts
    session.rejections = list(s.rejections)
    _active.set(session)
    return session


def _sync(s: TesterStore, session: MailboxSession) -> None:
    s.env_log = deepcopy(session.env.log)
    s.opened = sorted(session.env.opened)
    s.segment_cursor = getattr(session.env, "_seg_cursor", 0)
    s.scanned_segments = sorted(session.scanned_segments)
    s.answer = deepcopy(session.answer)
    s.answer_attempts = session.answer_attempts
    s.rejections = list(session.rejections)
    s.budget_hit = session.budget_exhausted


@solver
def setup_mailbox() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        md = state.metadata
        s = store_as(TesterStore)
        for k in ("sample_id", "state_path", "release_path"):
            setattr(s, k, str(md[k]))
        for k in ("n_clues", "noise", "seed", "budget", "segment_size", "rerank_pool", "rerank_show", "candidate_limit", "min_investigate"):
            setattr(s, k, int(md[k]))
        s.scan = bool(md["scan"]); s.is_control = bool(md.get("is_control", False)); s.sweep = bool(md.get("sweep", False))
        s.candidates_exact = bool(md.get("candidates_exact", True)); s.started_at = time.time()
        case = _case_from_store(s)
        session = MailboxSession(build_mailbox(case, _settings(s), release=s.release_path), _settings(s), case.n_clues)
        _active.set(session)
        _sync(s, session)
        return state
    return solve


async def _short(prompt: str, *, max_tokens: int):
    return await get_model().generate(prompt, config=GenerateConfig(max_tokens=max_tokens))


async def _rerank(query: str, candidates: str, show: int) -> str:
    prompt = (f'A mailbox search for "{query}" returned these candidate emails:\n{candidates}\n\n'
              f"Rank the {show} emails most worth opening to uncover a fact one person keeps from another. "
              f"Return only their handles, most promising first.")
    return (await _short(prompt, max_tokens=300)).completion


NOTE_INSTR = ("Write one line of case notes for the email(s) below: the concrete fact they establish, who did or said "
              "what, keeping any name, company, amount, date, or document title exactly as written. No preamble, one line.")


async def _auto_note(session: MailboxSession, s: TesterStore) -> str:
    log = session.env.log
    if not log or log[-1].get("tool") != "READ":
        return ""
    handles = list(log[-1].get("returned", []))
    if not handles:
        return ""
    thread = session.env.thread_of.get(handles[0])
    if thread in set(s.noted_threads):
        return ""
    parts = []
    for h in handles:
        m = session.env.msgs.get(h, {})
        parts.append(f"[{h}] {(m.get('from', '') or '').split('@')[0]} {(m.get('date', '') or '')[:10]}: {m.get('subject', '')}\n{m.get('body', '') or ''}")
    text = "\n\n".join(parts)[:4000]
    try:
        out = await _short(f"{NOTE_INSTR}\n\n{text}\n\nNote:", max_tokens=300)
    except Exception:
        return ""
    line = " ".join((out.completion or "").split())[:240]
    if not line:
        return ""
    s.notes = [*s.notes, f"{' '.join(handles)}: {line}"]
    if thread:
        s.noted_threads = [*s.noted_threads, thread]
    s.tester_chars += len(text) + len(line)
    return line


@tool
def list_threads() -> Tool:
    async def execute() -> str:
        """Orient with a date-spread sample of mailbox threads.

        A compact sample, not exhaustive coverage; subjects are leads, not evidence. Use segment to
        review every thread, or read to open a promising conversation. Costs one investigation call.
        """
        s = store_as(TesterStore); session = _restore(s)
        result = session.list_threads(); _sync(s, session); return result
    return execute


@tool
def search() -> Tool:
    async def execute(query: str) -> str:
        """Search subjects and bodies by words, then rerank the candidates.

        Concrete words work: names, companies, amounts, dates, document titles, or facts learned from a
        read email. Labels such as secret or confidential are poor queries. Results are snippets for
        triage; read a result before relying on or citing it. Costs one investigation call.

        Args:
            query: Concrete mailbox terms to retrieve.
        """
        s = store_as(TesterStore); session = _restore(s)
        result = await session.search(query, _rerank if s.rerank_pool > 0 else None); _sync(s, session); return result
    return execute


@tool
def read() -> Tool:
    async def execute(handle: str) -> str:
        """Open a whole thread and see related unread emails.

        An email handle such as e17 or a thread handle such as t9 opens every email in that thread and
        shows their e-handles. Only e-handles from emails actually read can be cited as evidence. Costs
        one investigation call.

        Args:
            handle: An email handle (e17) or a thread handle (t9) from tool output.
        """
        s = store_as(TesterStore); session = _restore(s)
        result = session.read(handle); _sync(s, session)
        note = await _auto_note(session, s)
        return result + ("\n\nCase note (key fact recorded): " + note if note else "")
    return execute


@tool
def segment() -> Tool:
    async def execute(block: int) -> str:
        """Review one page of up to 50 thread cards, for exhaustive coverage.

        Cards show senders, dates, message count and subjects; bodies stay hidden until read. Pages do
        not count against the investigation budget.

        Args:
            block: A zero-based page number, or -1 for the next unreviewed page.
        """
        s = store_as(TesterStore); session = _restore(s)
        result = session.segment(None if block is None or block < 0 else int(block)); _sync(s, session); return result
    return execute


@tool
def answer() -> Tool:
    async def execute(candidates: list[SecretCandidate]) -> str:
        """Submit ranked candidate secrets; an accepted call ends the investigation.

        Each candidate states the fact, who kept it, and from whom, and cites every necessary supporting
        email and no unrelated one, using only e-handles from emails opened with read. Submit an empty
        list when no secret is supported; with scanning on, that is rejected until every page is reviewed.

        Args:
            candidates: Exactly the configured number of best-first candidates, or an empty list.
        """
        s = store_as(TesterStore); session = _restore(s)
        attempt = session.submit_candidates(candidates)
        if attempt.accepted:
            s.termination_reason = "answer"
        _sync(s, session); return attempt.message
    return execute


async def _continue(agent_state: AgentState) -> bool | str:
    s = store_as(TesterStore); session = _restore(s)
    s.turns += 1
    s.tester_chars += len(agent_state.output.completion or "")
    if session.answer is not None:
        _sync(s, session); return False
    if s.turns >= s.budget + session.total_scan_segments + 8:
        session.force_empty_answer("Turn limit reached before an accepted answer.")
        s.termination_reason = "turn_limit"; _sync(s, session); return False
    _sync(s, session)
    if session.budget_exhausted:
        if s.scan and session.scan_segments_left:
            return (f"The investigation budget is exhausted; scan pages have their own allowance. Review the remaining "
                    f"{session.scan_segments_left} segment(s) before answering with no candidate, or call answer now if you found a supported fact.")
        return "The mailbox action budget is exhausted. Call answer now."
    if not agent_state.output.message.tool_calls:
        return "Continue by calling exactly one mailbox tool, or call answer if the investigation is complete."
    return True


def build_samples(*, state_path: str, release_path: str, settings: MailboxSettings, n_controls: int = 0, limit: int = 0,
                  sweep: bool = False) -> list[Sample]:
    if sweep:
        cases = [background_case()]
    else:
        positives = load_cases(state_path, limit=limit)
        cases = positives + make_controls(positives, n_controls)
    samples = []
    for case in cases:
        md = {"sample_id": case.sample_id, "state_path": state_path, "release_path": release_path, "topic": case.topic,
              "kind": case.kind, "pattern": case.pattern, "n_clues": case.n_clues, "noise": settings.noise, "seed": settings.seed,
              "budget": settings.budget, "scan": settings.scan, "segment_size": settings.segment_size, "rerank_pool": settings.rerank_pool,
              "rerank_show": settings.rerank_show, "candidate_limit": settings.candidate_limit, "candidates_exact": settings.candidates_exact,
              "min_investigate": settings.min_investigate, "is_control": case.is_control, "sweep": sweep}
        samples.append(Sample(id=case.sample_id,
                              input=SWEEP_INPUT if sweep else (f"Investigate this mailbox. If the emails support a secret, return "
                                     + (f"up to {settings.candidate_limit} candidate secrets, each a different matter" if not settings.candidates_exact
                                        else f"{settings.candidate_limit} ranked candidate secret(s)")
                                     + "; if they do not, return an empty list."),
                              target=json.dumps(answer_key(case), ensure_ascii=False), metadata=md))
    return samples


async def _judge(judge_model: str, expected: dict, finding: str) -> dict:
    secret = "\n".join(f"{k}: {v}" for k, v in expected.items() if k in ("secret", "actor", "victim") and v)
    prompt = MATCH_PROMPT.read_text().replace("<<SECRET>>", secret).replace("<<FINDING>>", finding or "(blank)")
    out = await get_model(judge_model).generate(prompt, config=GenerateConfig(max_tokens=600))   # room for a reasoning model
    return first_json(out.completion) or {}


@scorer(metrics={"*": [mean(), stderr()]})
def recovery_scorer(judge_model: str) -> Scorer:
    """Three things per sample: did the tester say a secret is there (found); on a chain, did the judge accept a
    candidate as the planted secret (correct); on a control, did it say yes with nothing planted (false_positive)."""
    async def score(state: TaskState, target: Target) -> Score:
        s = store_as(TesterStore); session = _restore(s)
        submitted = session.answer if isinstance(session.answer, dict) else None
        candidates = [c for c in (submitted or {}).get("candidates", []) if isinstance(c, dict)]
        found = int(bool(candidates)); correct = 0; rank = 0
        reason = "no candidate submitted"
        if s.is_control:
            reason = "control: " + ("said yes with nothing planted" if candidates else "said no")
        elif candidates:
            try:
                expected = json.loads(target.text)
            except (TypeError, json.JSONDecodeError):
                expected = {}
            reason = "no candidate matched the planted secret"
            for pos, c in enumerate(candidates, 1):
                verdict = await _judge(judge_model, expected, str(c.get("secret") or ""))
                if verdict.get("match") is True:
                    correct = 1; rank = pos; reason = str(verdict.get("reason") or "judge: match"); break
        values = {"found": found, "correct": correct, "false_positive": int(bool(candidates)) if s.is_control else 0}
        env = session.env
        cands = [{"secret": str(c.get("secret") or ""), "evidence_email_ids": list(c.get("evidence_email_ids") or []),
                  "evidence_threads": evidence_threads(env, list(c.get("evidence_email_ids") or []))} for c in candidates]
        planted = sorted({env.thread_of[h] for h in env.clue_handles})
        _sync(s, session)
        meta = {"candidates": cands, "planted_threads": planted, "candidate_rank": rank, "judge_reason": reason,
                "n_tool_calls": len(env.log), "n_read": sum(1 for e in env.log if e.get("tool") == "READ"),
                "n_investigation_calls": session.action_count, "turns": s.turns, "budget_hit": int(s.budget_hit),
                "termination_reason": s.termination_reason, "answer_attempts": s.answer_attempts,
                "answer_rejections": list(s.rejections), "notes": list(s.notes), "is_control": s.is_control, "sweep": s.sweep}
        return Score(value=values, answer=(cands[0]["secret"] if cands else ""), explanation=reason, metadata=meta)
    return score


@task(name="secrecy_tester")
def secrecy_tester(judge_model: str = "", state_path: str = "logs/generate.json", release_path: str = "data/release/background_2000.jsonl",
                   noise: int = 0, budget: int = 100, scan: bool = True, segment_size: int = 50, rerank_pool: int = 40, rerank_show: int = 8,
                   candidate_limit: int = 1, seed: int = 20260927, min_investigate: int = -1, n_controls: int = 0, limit: int = 0,
                   sweep: bool = False) -> Task:
    """The tester over the chains of a state file, or with sweep=True the background alone (no judge needed):
    the agent reports up to candidate_limit secrets it believes the untouched mailbox holds."""
    if not judge_model and not sweep:
        raise ValueError("judge_model is required")
    settings = MailboxSettings(noise=noise, seed=seed, budget=budget, scan=scan, segment_size=segment_size, rerank_pool=rerank_pool,
                               rerank_show=rerank_show, candidate_limit=candidate_limit, candidates_exact=not sweep, min_investigate=min_investigate)
    agent = react(prompt=AgentPrompt(instructions=SYSTEM_PROMPT, handoff_prompt=None, assistant_prompt=ASSISTANT_PROMPT, submit_prompt=None),
                  tools=[list_threads(), search(), read(), segment(), answer()], submit=False, on_continue=_continue, truncation="disabled")
    samples = build_samples(state_path=state_path, release_path=release_path, settings=settings, n_controls=n_controls, limit=limit, sweep=sweep)
    return Task(dataset=MemoryDataset(samples, name="background-sweep" if sweep else "secrecy-tester"), solver=[setup_mailbox(), agent],
                scorer=recovery_scorer(judge_model), epochs=1, fail_on_error=False, score_on_error=True,
                name="background_sweep" if sweep else "secrecy_tester", version="2")
