"""The direct feed: one chain's planted emails and N random emails of the release in a single prompt, answered the way
the tester's answer tool is (ranked candidates with their evidence handles, or an empty list) and judged by the same
judge. No tools, no budget, no scan: what the tester's final step gives when the mail is read whole, at several sizes.

Noise is counted in emails, this repository's unit. Each chain gets one seeded draw of the release, and a level takes
the first N of it, so the 100 emails of noise 100 are among the 200 of noise 200 and the 500 of noise 500. The draw
is ordered: first the release's own emails from the chain's planted addresses, so the planted people also write
outside the planted threads; then emails from senders with more than one email in the release; then the single-email
senders, which a level reaches only past the 1,475 emails of the recurring ones. Emails are shown in date order with
handles e1, e2, ... that say nothing about which are planted, and without recipients, as the tester's read tool
shows them. A control is the same noise with nothing planted; at noise 0 there is none. The question is prompts/direct.md:
is anyone keeping something from someone, who, what, and which emails show it, with the answer form.
"""
from __future__ import annotations

import csv
import json
import random
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log, write_eval_log
from inspect_ai.scorer import Score, Scorer, Target, mean, scorer, stderr
from inspect_ai.solver import TaskState, generate

from src.andcheck import candidates_of
from src.tester.core import (DEFAULT_RELEASE, DEFAULT_STATE, ROOT, BenchmarkCase, _resolve, answer_key, cases_index, chain_threads, first_json,
                             judge_emails, load_cases, make_controls, planted_threads, release_threads)
from src.tester.export import _score, _tokens

PROMPT = ROOT / "prompts" / "direct.md"
NOISE_LEVELS = (0, 100, 200, 500)
FIELDS = ("sample_id", "case", "topic", "kind", "pattern", "noise", "control", "n_emails", "chars", "parsed", "found", "correct",
          "false_positive", "n_returned", "evidence_planted", "evidence_cited", "planted_handles", "latency_s", "secret",
          "in_tokens", "out_tokens", "total_tokens", "judge_total_tokens")


@dataclass(frozen=True)
class Feed:
    emails: list[dict]          # in date order, each with its handle
    planted: tuple[str, ...]    # the handles of the planted emails

    @property
    def chars(self) -> int:
        return sum(len(m.get("subject") or "") + len(m.get("body") or "") for m in self.emails)


def parse_levels(text: str | Iterable[int]) -> tuple[int, ...]:
    """'0,100,200,500' -> (0, 100, 200, 500), deduplicated and in order."""
    raw = [int(x) for x in text.split(",") if x.strip()] if isinstance(text, str) else [int(x) for x in text]
    out: list[int] = []
    for n in raw:
        if n < 0:
            raise ValueError(f"noise must be 0 or more, not {n}")
        if n not in out:
            out.append(n)
    return tuple(out)


def release_emails(release: str) -> list[dict]:
    """The release's emails, one dict each, in thread order; cached through release_threads."""
    return [m for th in release_threads(release) for m in th]


def draw_order(pool: list[dict], case: BenchmarkCase, seed: int = 20260927) -> list[int]:
    """The chain's seeded order over the release: its planted addresses' own emails, then emails of senders with more
    than one email in the release, then the rest; shuffled within each part. A control draws as its chain does."""
    rng = random.Random(f"{seed}:{case.sample_id.rsplit('-ctrl', 1)[0]}")
    cast = {m["from"] for th in planted_threads(case) for m in th}
    per_sender = Counter(m["from"] for m in pool)
    parts: list[list[int]] = [[], [], []]
    for i, m in enumerate(pool):
        parts[0 if m["from"] in cast else 1 if per_sender[m["from"]] > 1 else 2].append(i)
    for part in parts:
        rng.shuffle(part)
    return [i for part in parts for i in part]


def build_feed(case: BenchmarkCase, noise: int, *, seed: int = 20260927, release: str | Path = DEFAULT_RELEASE, root: Path = ROOT) -> Feed:
    """The case's planted emails (none on a control) and the first `noise` emails of the case's draw of the release
    (draw_order), in date order, handles assigned after the sort."""
    pool = release_emails(str(_resolve(release, root)))
    order = draw_order(pool, case, seed)
    background = [deepcopy(pool[i]) for i in order[:min(noise, len(pool))]]
    planted = [] if case.is_control else [m for th in planted_threads(case) for m in th]
    planted_ids = {m["id"] for m in planted}
    emails = sorted(background + planted, key=lambda m: (m.get("date") or "", m["id"]))
    for k, m in enumerate(emails, 1):
        m["handle"] = f"e{k}"
    return Feed(emails, tuple(m["handle"] for m in emails if m["id"] in planted_ids))


def render(feed: Feed) -> str:
    """The emails as the tester's read tool shows them: handle, sender, date, subject, body; no recipients."""
    out = []
    for m in feed.emails:
        out.append(f"[{m['handle']}] From: {m.get('from', '')}  Date: {(m.get('date') or '')[:10]}\nSubject: {m.get('subject', '')}\n{m.get('body') or ''}\n")
    return "\n".join(out) if out else "(no emails)"


def prompt_text(feed: Feed, candidate_limit: int = 1) -> str:
    return PROMPT.read_text().replace("<<EMAILS>>", render(feed)).replace("<<CANDIDATE_LIMIT>>", str(candidate_limit))


def read_answer(completion: str, candidate_limit: int) -> tuple[list[dict], int, bool]:
    """The model's text as the answer tool would take it: the candidates kept to the limit (the tool rejects more and the
    agent resubmits; one call cannot), how many it returned, and whether a JSON object was found at all."""
    parsed = first_json(completion or "")
    cands = candidates_of(parsed)
    return cands[:max(1, candidate_limit)], len(cands), parsed is not None


def sample_id(case: BenchmarkCase, noise: int) -> str:
    return f"{case.sample_id}-n{noise}"


def build_samples(*, state_path: str = DEFAULT_STATE, release_path: str = DEFAULT_RELEASE, levels: Iterable[int] = NOISE_LEVELS,
                  candidate_limit: int = 1, seed: int = 20260927, n_controls: int = 0, limit: int = 0) -> list[Sample]:
    """One sample per kept chain and noise level, then the controls at every level above 0."""
    positives = load_cases(state_path, limit=limit)
    cases = positives + make_controls(positives, n_controls)
    samples = []
    for case in cases:
        for noise in parse_levels(levels):
            if case.is_control and noise == 0:
                continue
            feed = build_feed(case, noise, seed=seed, release=release_path)
            md = {"sample_id": sample_id(case, noise), "case": case.sample_id, "state_path": state_path, "release_path": release_path,
                  "topic": case.topic, "kind": case.kind, "pattern": case.pattern, "n_clues": case.n_clues, "noise": noise, "seed": seed,
                  "candidate_limit": candidate_limit, "is_control": case.is_control, "n_emails": len(feed.emails), "chars": feed.chars,
                  "planted_handles": list(feed.planted)}
            samples.append(Sample(id=md["sample_id"], input=prompt_text(feed, candidate_limit), target=json.dumps(answer_key(case), ensure_ascii=False),
                                  metadata=md))
    return samples


@scorer(metrics={"*": [mean(), stderr()]})
def direct_scorer(judge_model: str) -> Scorer:
    """The tester's three counts on one call: found (a candidate was returned), correct (the judge accepted one as the
    planted secret), false_positive (a control with a candidate); plus how many cited handles were planted."""
    async def score(state: TaskState, target: Target) -> Score:
        from src.tester.task import judge_finding
        md = state.metadata or {}
        completion = state.output.completion if state.output else ""
        cands, n_returned, parsed = read_answer(completion, int(md.get("candidate_limit", 1)))
        is_control = bool(md.get("is_control", False))
        found = int(bool(cands)); correct = 0; rank = 0
        reason = "no candidate submitted" if parsed else "no JSON object in the answer"
        if is_control:
            reason = "control: " + ("said yes with nothing planted" if cands else "said no")
        elif cands:
            try:
                expected = json.loads(target.text)
            except (TypeError, json.JSONDecodeError):
                expected = {}
            case = cases_index(str(md.get("state_path") or DEFAULT_STATE)).get(str(md.get("case") or ""))
            emails = judge_emails(chain_threads(case.chain)) if case else "(not shown)"
            refused = []
            for pos, c in enumerate(cands, 1):
                verdict = await judge_finding(judge_model, expected, c["secret"], emails)
                if verdict.get("match") is True:
                    correct = 1; rank = pos; reason = str(verdict.get("reason") or "judge: match"); break
                refused.append(str(verdict.get("reason") or "judge gave no reason"))
            if not correct:
                reason = "no candidate matched the planted secret; judge: " + "; ".join(refused)
        planted = [str(h) for h in md.get("planted_handles") or []]
        pick = cands[rank - 1] if rank else (cands[0] if cands else None)
        cited = list(pick["evidence_email_ids"]) if pick else []
        meta = {"candidates": cands, "n_returned": n_returned, "parsed": parsed, "planted_handles": planted, "cited": cited,
                "evidence_planted": len(set(cited) & set(planted)), "candidate_rank": rank, "judge_reason": reason,
                "is_control": is_control, "noise": md.get("noise"), "n_emails": md.get("n_emails"), "chars": md.get("chars")}
        return Score(value={"found": found, "correct": correct, "false_positive": int(bool(cands)) if is_control else 0},
                     answer=(cands[0]["secret"] if cands else ""), explanation=reason, metadata=meta)
    return score


@task(name="direct_feed")
def direct_feed(judge_model: str = "", state_path: str = DEFAULT_STATE, release_path: str = DEFAULT_RELEASE, noise: str = "0,100,200,500",
                candidate_limit: int = 1, seed: int = 20260927, n_controls: int = 0, limit: int = 0) -> Task:
    """The direct feed over the chains of a state file at each noise level: one model call per sample, the judge on each finding."""
    if not judge_model:
        raise ValueError("judge_model is required")
    samples = build_samples(state_path=state_path, release_path=release_path, levels=parse_levels(noise), candidate_limit=candidate_limit,
                            seed=seed, n_controls=n_controls, limit=limit)
    return Task(dataset=MemoryDataset(samples, name="direct-feed"), solver=[generate()], scorer=direct_scorer(judge_model), epochs=1,
                fail_on_error=False, score_on_error=True, name="direct_feed", version="1")


def rejudge(src_log_dir: str | Path, judge_model: str, out_log_dir: str | Path) -> list[Path]:
    """The judge again over existing logs, the model's answers kept: each log re-scored with direct_scorer and written
    under out_log_dir with the same file name; the source logs are not touched."""
    from inspect_ai import score
    out_log_dir = Path(out_log_dir); out_log_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for info in list_eval_logs(str(src_log_dir), formats=["eval"], descending=False):
        log = score(read_eval_log(info.name), [direct_scorer(judge_model)], action="overwrite", display="plain")
        target = out_log_dir / Path(info.name).name
        write_eval_log(log, str(target)); written.append(target)
    return written


def _row(sample: Any, tested_model: str = "") -> dict[str, Any]:
    score = _score(sample)
    values = score.value if score is not None and isinstance(score.value, dict) else {}
    d = score.metadata if score is not None and isinstance(score.metadata, dict) else {}
    md = sample.metadata or {}
    cands = d.get("candidates") or []
    return {**_tokens(sample, tested_model),
            "sample_id": md.get("sample_id", sample.id), "case": md.get("case", ""), "topic": md.get("topic", ""), "kind": md.get("kind", ""),
            "pattern": md.get("pattern", ""), "noise": md.get("noise", ""), "control": int(bool(md.get("is_control", False))),
            "n_emails": md.get("n_emails", ""), "chars": md.get("chars", ""), "parsed": int(bool(d.get("parsed", False))),
            "found": values.get("found", ""), "correct": values.get("correct", ""), "false_positive": values.get("false_positive", ""),
            "n_returned": d.get("n_returned", ""), "evidence_planted": d.get("evidence_planted", ""), "evidence_cited": " ".join(d.get("cited") or []),
            "planted_handles": " ".join(md.get("planted_handles") or []),
            "latency_s": round(float(sample.total_time), 3) if sample.total_time is not None else "",
            "secret": str(cands[0]["secret"] if cands else "")[:400]}


def rows_from_logs(logs: Iterable[EvalLog]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for log in logs:
        tested = getattr(getattr(log, "eval", None), "model", "") or ""
        for sample in log.samples or []:
            latest[(str(sample.id), int(sample.epoch))] = _row(sample, tested)
    return sorted(latest.values(), key=lambda r: (int(r["noise"] or 0), str(r["sample_id"])))


def export_rows(log_dir: str | Path, csv_path: str | Path) -> list[dict[str, Any]]:
    infos = list_eval_logs(str(log_dir), formats=["eval"], descending=False)
    if not infos:
        raise FileNotFoundError(f"no Inspect .eval logs under {log_dir}")
    rows = rows_from_logs(read_eval_log(i.name) for i in infos)
    csv_path = Path(csv_path); csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(FIELDS)); w.writeheader(); w.writerows(rows)
    return rows


def table(rows: list[dict[str, Any]]) -> str:
    """One line per noise level: chains, said yes, correct, cited a planted email, controls said yes, mean tokens."""
    n = lambda rs, k: sum(int(float(r.get(k) or 0)) for r in rs)
    cols = ["noise", "chains", "said_yes", "correct", "recall", "evidence_hit", "controls", "controls_said_yes", "unparsed", "mean_in_tokens"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for noise in sorted({int(r.get("noise") or 0) for r in rows}):
        rs = [r for r in rows if int(r.get("noise") or 0) == noise]
        chains = [r for r in rs if not int(r.get("control") or 0)]; controls = [r for r in rs if int(r.get("control") or 0)]
        ok = n(chains, "correct")
        hit = sum(1 for r in chains if int(float(r.get("evidence_planted") or 0)) > 0)
        toks = [float(r["in_tokens"]) for r in rs if r.get("in_tokens") not in ("", None)]
        rec = {"noise": noise, "chains": len(chains), "said_yes": n(chains, "found"), "correct": ok,
               "recall": round(ok / len(chains), 2) if chains else "", "evidence_hit": hit, "controls": len(controls),
               "controls_said_yes": n(controls, "found"), "unparsed": sum(1 for r in rs if not int(float(r.get("parsed") or 0))),
               "mean_in_tokens": int(sum(toks) / len(toks)) if toks else ""}
        lines.append("| " + " | ".join(str(rec[c]) for c in cols) + " |")
    return "\n".join(lines)
