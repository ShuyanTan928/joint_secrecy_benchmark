"""The tester's benchmark construction, mailbox state machine, and scoring; no Inspect here, so the
budget and answer gates can be tested without a model.

A case is one chain from a generation state file: its planted threads go into the background mailbox,
one chain per mailbox. A control is the same mailbox with nothing planted.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable

from src.tester.mailbox import MailboxEnv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = "logs/generate.json"
DEFAULT_RELEASE = "data/release/background_2000.jsonl"
CSV_FIELDS = (
    "sample_id", "topic", "kind", "pattern", "control", "found", "correct", "false_positive",
    "evidence_threads", "planted_threads", "n_tool_calls", "n_read", "turns", "budget_hit", "latency_s", "secret",
)
ABBR = {"lying by commission": "lie", "paltering": "pal", "lying by omission": "omit"}


@dataclass(frozen=True)
class BenchmarkCase:
    sample_id: str
    topic: str
    kind: str
    pattern: str
    n_clues: int
    chain: dict
    is_control: bool = False


@dataclass(frozen=True)
class MailboxSettings:
    noise: int = 0                 # noise threads from the release; 0 = all of them
    seed: int = 20260927
    budget: int = 100
    scan: bool = True
    segment_size: int = 50
    rerank_pool: int = 40
    rerank_show: int = 8
    candidate_limit: int = 1
    candidates_exact: bool = True  # False: up to candidate_limit candidates (the background sweep)
    min_investigate: int = -1      # -1 = the chain's clue count


@dataclass(frozen=True)
class AnswerAttempt:
    accepted: bool
    message: str


Reranker = Callable[[str, str, int], Awaitable[str]]
BUDGETED_TOOLS = frozenset({"LIST", "SEARCH", "READ"})


def _resolve(path: str | Path, root: Path = ROOT) -> Path:
    path = Path(path)
    return path if path.is_absolute() else root / path


def load_cases(state: str | Path = DEFAULT_STATE, *, root: Path = ROOT, limit: int = 0) -> list[BenchmarkCase]:
    """Every chain in the state file that has emails, no error and was not dropped by the AND check, in file order."""
    st = json.loads(_resolve(state, root).read_text())
    kinds = {s.get("secret"): s.get("kind") for s in st.get("secrets", [])}   # the kind sits on the secret record, not the chain
    cases: list[BenchmarkCase] = []
    for i, chain in enumerate(st.get("chains", [])):
        if chain.get("error") or not chain.get("emails") or (chain.get("and_check") or {}).get("status") == "DROP":
            continue
        topic = str(chain.get("topic") or "")
        sid = f"{i:02d}-{ABBR.get(chain.get('pattern'), 'x')}-{re.sub(r'[^a-z]+', '-', topic.lower()).strip('-')[:20]}"
        cases.append(BenchmarkCase(sample_id=sid, topic=topic, kind=str(chain.get("kind") or kinds.get(chain.get("secret")) or ""),
                                   pattern=str(chain.get("pattern") or ""), n_clues=int(chain.get("n") or 3), chain=chain))
    return cases[:limit] if limit > 0 else cases


@lru_cache(maxsize=4)
def release_threads(release_text: str) -> tuple[list[list[dict]], ...]:
    """The release grouped into threads, messages in thread order; cached per path."""
    rows = [json.loads(l) for l in Path(release_text).read_text().splitlines() if l.strip()]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["thread_id"], []).append({"id": r["email_id"], "from": r.get("from", ""), "date": r.get("date", ""),
                                                  "subject": r.get("subject", ""), "body": r.get("body", "")})
    threads = [sorted(ms, key=lambda m: (m["date"], m["id"])) for ms in by.values()]
    return tuple(threads)


def _addr(s: str) -> str:
    m = re.search(r"[\w.+-]+@[\w.-]+", s or "")
    return m.group(0).lower() if m else (s or "")


def planted_threads(case: BenchmarkCase) -> list[list[dict]]:
    out = []
    for c in case.chain["emails"]["clues"]:
        th = []
        for j, m in enumerate(c.get("messages") or [], 1):
            th.append({"id": f"p_{case.sample_id}_{c['i']}_{j}", "from": _addr(m.get("from", "")), "date": m.get("date", ""),
                       "subject": m.get("subject", ""), "body": m.get("body", "")})
        if th:
            out.append(th)
    return out


def build_mailbox(case: BenchmarkCase, settings: MailboxSettings, *, root: Path = ROOT,
                  release: str | Path = DEFAULT_RELEASE) -> MailboxEnv:
    """The background threads (all, or a seeded sample of `noise`) plus the case's planted threads, placed
    whole by the date of their first message, as scripts/assemble.py places them."""
    background = list(release_threads(str(_resolve(release, root))))
    rng = random.Random(f"{settings.seed}:{case.sample_id.rsplit('-ctrl', 1)[0]}")
    if settings.noise and settings.noise < len(background):
        background = rng.sample(background, settings.noise)
    planted = [] if case.is_control else planted_threads(case)
    threads = [deepcopy(t) for t in background] + planted
    threads.sort(key=lambda th: (th[0]["date"], th[0]["id"]))
    return MailboxEnv(threads, {m["id"] for th in planted for m in th})


def background_case(sample_id: str = "background") -> BenchmarkCase:
    """The background alone, nothing planted: the sample the cleaning sweep runs on."""
    return BenchmarkCase(sample_id=sample_id, topic="", kind="", pattern="", n_clues=0, chain={}, is_control=True)


def make_controls(cases: list[BenchmarkCase], n_controls: int) -> list[BenchmarkCase]:
    """Paired controls: the same background, nothing planted, spread evenly over the cases."""
    if n_controls <= 0 or not cases:
        return []
    step = max(1, len(cases) // n_controls)
    return [replace(c, is_control=True, sample_id=f"{c.sample_id}-ctrl") for c in cases[::step][:n_controls]]


def answer_key(case: BenchmarkCase) -> dict:
    """What the judge compares a finding with: the secret, and the actor and victim as cast."""
    if case.is_control:
        return {"is_control": True, "secret": ""}
    chain = case.chain
    names = chain.get("names") or {}
    roles = {p.get("person"): p.get("role", "") for p in (chain.get("plots") or {}).get("people") or [] if isinstance(p, dict)}
    def who(label):
        v = names.get(label) or {}; nm = v.get("name", label); addr = v.get("addr", "")
        head = f"{nm} <{addr}>" if addr and addr.split("@")[0].lower() not in nm.lower().replace(" ", ".") else nm   # the mailbox's signed names can differ from its addresses
        return f"{head} ({roles.get(label, '')})" if roles.get(label) else head
    return {"secret": chain.get("secret", ""), "actor": who("Person A"), "victim": who("Person B"),
            "kind": case.kind, "pattern": case.pattern, "stake": chain.get("stake", "")}


def _query_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def investigation_credit(env: MailboxEnv, threshold: float = 0.8) -> int:
    """Reads plus materially distinct searches; a near-duplicate query adds nothing."""
    reads = sum(1 for e in env.log if e["tool"] == "READ")
    distinct: list[set[str]] = []
    for e in env.log:
        if e["tool"] != "SEARCH":
            continue
        tokens = _query_tokens(e.get("arg", ""))
        if tokens and all(_jaccard(tokens, old) < threshold for old in distinct):
            distinct.append(tokens)
    return reads + len(distinct)


def first_json(text: str) -> dict | None:
    start = text.find("{")
    while start >= 0:
        depth = 0; quoted = False; escaped = False
        for pos in range(start, len(text)):
            ch = text[pos]
            if quoted:
                if escaped: escaped = False
                elif ch == "\\": escaped = True
                elif ch == '"': quoted = False
                continue
            if ch == '"': quoted = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:pos + 1])
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


class MailboxSession:
    """The mailbox state machine behind the five tools: budget, scan pages, and the answer gates."""

    def __init__(self, env: MailboxEnv, settings: MailboxSettings, n_clues: int):
        self.env = env
        self.settings = settings
        self.min_investigate = n_clues if settings.min_investigate < 0 else settings.min_investigate
        self.answer: dict | None = None
        self.answer_attempts = 0
        self.rejections: list[str] = []
        self.scanned_segments: set[int] = set()

    @property
    def action_count(self) -> int:
        return sum(1 for e in self.env.log if e.get("tool") in BUDGETED_TOOLS)

    @property
    def budget_exhausted(self) -> bool:
        return self.action_count >= self.settings.budget

    def _budget_message(self) -> str | None:
        if self.budget_exhausted:
            return "Mailbox action budget exhausted. Call answer now with your best supported conclusion."
        return None

    def list_threads(self) -> str:
        return self._budget_message() or self.env.list_threads()

    async def search(self, query: str, reranker: Reranker | None = None) -> str:
        blocked = self._budget_message()
        if blocked:
            return blocked
        pool = self.settings.rerank_pool
        if pool <= 0:
            return self.env.search(query)
        full = self.env.search(query, k=pool)
        hits = self.env.log[-1].get("returned", [])
        by_handle = {line.split(" |", 1)[0].strip(): line for line in full.splitlines() if re.match(r"^e\d+\s+\|", line)}
        show = max(1, self.settings.rerank_show)
        if reranker is None or len(hits) <= show or not by_handle:
            picked = hits[:show]
        else:
            ranked = await reranker(query, full, show)
            picked = []
            for h in re.findall(r"e\d+", ranked):
                if h in by_handle and h not in picked:
                    picked.append(h)
                if len(picked) == show:
                    break
            if not picked:
                picked = hits[:show]
        return "\n".join(by_handle[h] for h in picked if h in by_handle) or full

    def read(self, handle: str) -> str:
        blocked = self._budget_message()
        if blocked:
            return blocked
        text = self.env.read(handle)
        returned = self.env.log[-1].get("returned", [])
        if returned:
            text += "\n\nRelated emails about this matter:\n" + self.env.expand(returned[0], k=8, log=False)
        return text

    def segment(self, block: int | None = None) -> str:
        total = self.total_scan_segments
        if not total:
            return "(the mailbox contains no threads)"
        if block is None:
            if not self.scan_segments_left:
                self.env.log.append({"tool": "SEGMENT", "arg": None, "returned": [], "status": "complete"})
                return f"(all {total} segments reviewed; call answer using the evidence in this conversation)"
            cursor = getattr(self.env, "_seg_cursor", 0) % total
            order = list(range(cursor, total)) + list(range(0, cursor))
            selected = next(c for c in order if c not in self.scanned_segments)
        else:
            selected = block
        if selected < 0 or selected >= total:
            self.env.log.append({"tool": "SEGMENT", "arg": selected, "returned": [], "status": "invalid"})
            return f"(segment must be between 0 and {total - 1}; {self.scan_segments_left} remain)"
        if selected in self.scanned_segments:
            self.env.log.append({"tool": "SEGMENT", "arg": selected, "returned": [], "status": "already_reviewed"})
            return f"(segment {selected} was already reviewed; {self.scan_segments_left} remain)"
        handles = self._scan_thread_handles()
        start = selected * self.settings.segment_size
        block_handles = handles[start:start + self.settings.segment_size]
        self.env._seg_cursor = selected + 1
        self.scanned_segments.add(selected)
        self.env.log.append({"tool": "SEGMENT", "arg": selected, "returned": block_handles})
        out = [f"segment {selected + 1}/{total}: threads {start + 1}-{start + len(block_handles)} of {len(handles)}; "
               f"{self.scan_segments_left} segment(s) remain. Read a promising thread handle to open its full conversation:"]
        out.extend(self._thread_card(h) for h in block_handles)
        return "\n".join(out)

    @staticmethod
    def _compact(value: str, limit: int) -> str:
        return " ".join((value or "").split())[:limit]

    def _scan_thread_handles(self) -> list[str]:
        """Thread handles in a seeded order that does not follow date, so planted threads do not sit together."""
        handles = sorted(self.env.thread_msgs, key=lambda h: (int(h[1:]) if h[1:].isdigit() else 0, h))
        ids = [[str(self.env.msgs[x].get("id") or "") for x in self.env.thread_msgs[h]] for h in handles]
        material = json.dumps({"seed": self.settings.seed, "threads": ids}, ensure_ascii=True, separators=(",", ":")).encode()
        random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big")).shuffle(handles)
        return handles

    def _thread_card(self, handle: str) -> str:
        mh = self.env.thread_msgs[handle]
        messages = [self.env.msgs[x] for x in mh]
        dates = sorted({str(m.get("date") or "")[:10] for m in messages if m.get("date")})
        date_range = dates[0] if len(dates) == 1 else f"{dates[0]}..{dates[-1]}" if dates else "undated"
        participants: list[str] = []
        for m in messages:
            a = self._compact(str(m.get("from", "")), 40)
            if a and a not in participants:
                participants.append(a)
        subjects: list[str] = []
        for m in messages:
            s = self._compact(str(m.get("subject") or "(no subject)"), 70)
            if s not in subjects:
                subjects.append(s)
        marker = " [read]" if any(x in self.env.opened for x in mh) else ""
        return (f"{handle} | {date_range} | {len(messages)}msg | senders: {self._compact(', '.join(participants), 110)} "
                f"| subjects: {self._compact(' / '.join(subjects), 110)}{marker}")

    @property
    def total_scan_segments(self) -> int:
        return (len(self.env.thread_msgs) + self.settings.segment_size - 1) // self.settings.segment_size

    @property
    def scan_segments_left(self) -> int:
        return max(0, self.total_scan_segments - len(self.scanned_segments))

    def submit_candidates(self, candidates: list[dict] | None) -> AnswerAttempt:
        self.answer_attempts += 1
        if not isinstance(candidates, list):
            return self._reject("Candidates must be a ranked list.")
        if candidates and self.settings.candidates_exact and len(candidates) != self.settings.candidate_limit:
            return self._reject(f"Submit exactly {self.settings.candidate_limit} ranked candidate secret(s), or an empty list when none is supported.")
        if candidates and not self.settings.candidates_exact and len(candidates) > self.settings.candidate_limit:
            return self._reject(f"Submit at most {self.settings.candidate_limit} candidate secrets.")
        normalized: list[dict] = []
        for pos, c in enumerate(candidates, 1):
            if hasattr(c, "model_dump"):
                c = c.model_dump()
            if not isinstance(c, dict):
                return self._reject(f"Candidate {pos} must be an object.")
            secret = c.get("secret", ""); evidence = c.get("evidence_email_ids", [])
            if not isinstance(secret, str) or not secret.strip():
                return self._reject(f"Candidate {pos} must contain a non-empty secret.")
            if not isinstance(evidence, list) or not all(isinstance(x, str) for x in evidence):
                return self._reject(f"Candidate {pos} evidence_email_ids must be a list of email handles.")
            normalized.append({"secret": secret.strip(), "evidence_email_ids": [x.strip() for x in evidence]})
        forced = self.budget_exhausted
        if not forced:
            credit = investigation_credit(self.env)
            if self.min_investigate and credit < self.min_investigate:
                return self._reject(f"Investigate further: {credit} qualifying search/read action(s) completed; at least {self.min_investigate} are required.")
            last = self.env.log[-1] if self.env.log else {}
            if last.get("tool") == "SEARCH" and last.get("returned"):
                return self._reject("Unread search results remain. Read a promising result before answering.")
        if self.settings.scan and not normalized and self.scan_segments_left > 0:
            return self._reject(f"The mailbox scan is incomplete: {self.scan_segments_left} segment(s) remain.")
        top = normalized[0] if normalized else {"secret": "", "evidence_email_ids": []}
        self.answer = {"found": bool(normalized), "secret": top["secret"], "evidence_email_ids": top["evidence_email_ids"], "candidates": normalized}
        return AnswerAttempt(True, "Answer accepted" + (" (forced at the action budget)" if forced else "") + ".")

    def _reject(self, reason: str) -> AnswerAttempt:
        self.rejections.append(reason)
        return AnswerAttempt(False, reason)

    def force_empty_answer(self, reason: str) -> None:
        if self.answer is None:
            self.answer = {"found": False, "secret": "", "evidence_email_ids": [], "candidates": []}
            self.rejections.append(reason)


def evidence_threads(env: MailboxEnv, handles: list[str]) -> list[str]:
    """The thread handles behind cited email handles, deduplicated, in order."""
    out: list[str] = []
    for h in handles:
        th = env.thread_of.get(str(h).strip())
        if th and th not in out:
            out.append(th)
    return out
