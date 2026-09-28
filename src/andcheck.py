"""The AND check on a chain's emails, and the diagnosis that drives a fix round.

Blind probers read every proper subset of the planted threads and then the full set, one call each with
nothing else, and answer in the tester's form: a candidate secret with its evidence, or an empty list.
Each candidate goes to the tester's judge (prompts/match.md) against the answer key. A chain passes when
no proper subset gives the secret to any prober and the full set gives it to every prober. A failed
chain goes to a diagnoser that sees the secret (prompts/diagnose.md) and names the clue at fault, the
step to redo and one change; scripts/generate.py reruns that step with the change and checks again.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Callable

from src.tester.core import first_json

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "prompts" / "probe.md"
MATCH = ROOT / "prompts" / "match.md"
DIAGNOSE = ROOT / "prompts" / "diagnose.md"

Ask = Callable[[object, str], str]   # ask(engine, prompt) -> the model's text


def subsets(n: int) -> list[tuple[int, ...]]:
    """Every non-empty set of thread indices, smallest first; the full set is last."""
    return [s for r in range(1, n + 1) for s in itertools.combinations(range(n), r)]


def render(threads: list[list[dict]], chosen: tuple[int, ...]) -> tuple[str, dict[str, list[int]]]:
    """The chosen threads as the tester's read tool shows them, e-handles numbered within this set; returns the text and handle -> [thread, message]."""
    out, handles, n = [], {}, 0
    for k, i in enumerate(chosen, 1):
        out.append(f"thread t{k} ({len(threads[i])} message{'s' if len(threads[i]) != 1 else ''}):")
        for j, m in enumerate(threads[i]):
            n += 1; handles[f"e{n}"] = [i, j]
            out.append(f"\n[e{n}] From: {m.get('from', '')}  Date: {(m.get('date', '') or '')[:10]}\nSubject: {m.get('subject', '')}\n{m.get('body', '')}")
        out.append("")
    return "\n".join(out), handles


def candidates_of(ans: dict | None) -> list[dict]:
    """The prober's answer in the tester's form: a list of {secret, evidence_email_ids}; anything else is a no."""
    out = []
    for c in (ans or {}).get("candidates") or []:
        if isinstance(c, dict) and str(c.get("secret") or "").strip():
            ev = c.get("evidence_email_ids") or []
            out.append({"secret": str(c["secret"]).strip(), "evidence_email_ids": [str(x) for x in ev] if isinstance(ev, list) else []})
    return out


def decide(per_model: dict[str, dict[tuple[int, ...], bool]], n: int) -> dict:
    """per_model[model][subset] = the judge matched. Keep: no proper subset matched for any model, the full set matched for every model."""
    full = tuple(range(n))
    leaks = sorted((m, s) for m, ms in per_model.items() for s, ok in ms.items() if ok and s != full)
    full_ok = {m: bool(ms.get(full)) for m, ms in per_model.items()}
    return {"keep": not leaks and bool(full_ok) and all(full_ok.values()),
            "leaks": [{"model": m, "threads": list(s)} for m, s in leaks], "full_set": full_ok}


def reduce_to_subset(report: dict, n: int, conflict: int, fact: int = 0) -> list[int] | None:
    """The smaller set a failed chain is delivered on, or None: a proper subset of two or more threads that holds the
    [concealment] thread, that every prober recovered, and none of whose own proper subsets any prober recovered. Among
    several, the smallest, then one holding the [fact] thread, then the lowest indices."""
    matched: dict[tuple[int, ...], set[str]] = {}
    for c in report["calls"]:
        if c["correct"]:
            matched.setdefault(tuple(c["threads"]), set()).add(c["prober"])
    probers = {c["prober"] for c in report["calls"]}
    ok = []
    for size in range(2, n):
        for s in itertools.combinations(range(n), size):
            if conflict not in s or matched.get(s, set()) != probers:
                continue
            inner = [t for k in range(1, size) for t in itertools.combinations(s, k)]
            if any(matched.get(t) for t in inner):
                continue
            ok.append(s)
    if not ok:
        return None
    return list(sorted(ok, key=lambda s: (len(s), fact not in s, s))[0])


def key_lines(key: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in key.items() if k in ("secret", "actor", "victim") and v)


def check(threads: list[list[dict]], key: dict, probers: dict[str, object], matcher: object, ask: Ask) -> dict:
    """One check of a chain: every subset to every prober, every candidate to the judge; the keep decision and every call."""
    n = len(threads); probe_shell, match_shell = PROBE.read_text(), MATCH.read_text()
    secret = key_lines(key)
    per_model: dict[str, dict[tuple[int, ...], bool]] = {}
    calls = []
    for name, eng in probers.items():
        for s in subsets(n):
            text, handles = render(threads, s)
            out = ask(eng, probe_shell.replace("<<EMAILS>>", text))
            cands = candidates_of(first_json(out))
            correct, rank, reason = 0, 0, ("no candidate submitted" if not cands else "")
            for pos, cand in enumerate(cands, 1):   # the tester's scorer: first match wins
                verdict = first_json(ask(matcher, match_shell.replace("<<SECRET>>", secret).replace("<<FINDING>>", cand["secret"]))) or {}
                reason = (reason + "; " if reason else "") + str(verdict.get("reason") or ("judge: match" if verdict.get("match") is True else "judge gave no reason"))
                if verdict.get("match") is True:
                    correct, rank = 1, pos; break
            per_model.setdefault(name, {})[s] = bool(correct)
            calls.append({"prober": name, "threads": list(s), "full_set": len(s) == n, "handles": handles, "found": int(bool(cands)),
                          "correct": correct, "candidates": cands, "candidate_rank": rank, "judge_reason": reason, "raw": out})
    return {"n": n, **decide(per_model, n), "calls": calls}


def findings_text(report: dict) -> tuple[str, str]:
    """What the blind readers found, for the diagnoser: the leaking subsets with the finding, and the full-set findings."""
    leaks, full = [], []
    for c in report["calls"]:
        said = c["candidates"][0]["secret"] if c["candidates"] else "nothing"
        if c["full_set"]:
            full.append(f"- {c['prober']}: {said}" + ("" if c["correct"] else f" (the judge: {c['judge_reason']})" if c["candidates"] else ""))
        elif c["correct"]:
            ev = c["candidates"][0].get("evidence_email_ids") or []
            leaks.append(f"- clues {[i + 1 for i in c['threads']]} alone, {c['prober']}: {said}" + (f" (from {', '.join(ev)})" if ev else ""))
    return "\n".join(leaks) or "- none", "\n".join(full) or "- nothing"


def cast_lines(names: dict | None) -> str:
    """Person A: the name and address the emails use, one line per placeholder."""
    return "\n".join(f"{label}: {v.get('name', '')} <{v.get('addr', '')}>" for label, v in sorted((names or {}).items())) or "(as planned)"


def diagnose(report: dict, key: dict, parts: str, plan_text: str, emails_text: str, history: list[str], diagnoser: object, ask: Ask, cast: str = "") -> dict:
    """One call that sees the secret: the clue at fault, the step to redo (plot or emails) and one change."""
    leaks, full = findings_text(report)
    p = (DIAGNOSE.read_text().replace("<<SECRET>>", key_lines(key)).replace("<<PARTS>>", parts).replace("<<PLAN>>", plan_text).replace("<<CAST>>", cast or "(as planned)")
         .replace("<<EMAILS>>", emails_text).replace("<<LEAKS>>", leaks).replace("<<FULL>>", full)
         .replace("<<HISTORY>>", "\n".join(f"- {h}" for h in history) or "- none"))
    d = first_json(ask(diagnoser, p)) or {}
    step = str(d.get("step") or "").strip().lower()
    d["step"] = "clues" if step.startswith("clue") or step.startswith("part") else "plot" if step.startswith("plot") else "emails"
    d["change"] = str(d.get("change") or "").strip()
    return d


def revise_block(diagnosis: dict, history: list[str], report: dict | None = None, previous: str = "", cast: str = "") -> str:
    """The revision appended to the plot or email prompt on a fix round: what failed and what the readers found, the previous
    version (the plan, or the emails as the readers saw them), the one change, the changes before it, and the gate."""
    if not diagnosis.get("change"):
        return ""
    why = str(diagnosis.get("why") or "").strip()
    lines = ["", "## Revise", "Blind readers checked the previous version" + (f": {why}" if why else ".")]
    if report:
        leaks, full = findings_text(report)
        if leaks != "- none":
            lines += ["Fewer than all clues gave the secret:", leaks]
        if not all(report.get("full_set", {}).values()):
            lines += ["All clues together did not give it; the readers found:", full]
    if previous:
        lines += ["", "The previous version" + (", with the cast: " + cast.replace("\n", "; ") if cast else "") + ":", previous, ""]
    lines.append(f"Change: {diagnosis['change']}")
    if history:
        lines.append("Earlier changes, still in force: " + "; ".join(history))
    lines.append("Make this change and keep everything else as it was. All clues together give the secret; no smaller set does.")
    return "\n".join(lines)
