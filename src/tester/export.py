"""Rows from the Inspect logs: one line per sample, the score and the trajectory counts, to rows.csv."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log

from src.tester.core import CSV_FIELDS

TOKEN_FIELDS = ["in_tokens", "out_tokens", "total_tokens", "judge_total_tokens"]
FIELDS = list(CSV_FIELDS) + TOKEN_FIELDS


def _stored(sample: Any, key: str, default: Any = "") -> Any:
    return sample.store.get(f"TesterStore:{key}", default)


def _tokens(sample: Any, tested_model: str) -> dict[str, Any]:
    usage = getattr(sample, "model_usage", None) or {}
    tested = usage.get(tested_model)
    if tested is None:
        tested = max(usage.values(), key=lambda u: getattr(u, "total_tokens", 0) or 0, default=None)
    judge = sum((getattr(u, "total_tokens", 0) or 0) for u in usage.values() if u is not tested)
    return {"in_tokens": getattr(tested, "input_tokens", "") if tested is not None else "",
            "out_tokens": getattr(tested, "output_tokens", "") if tested is not None else "",
            "total_tokens": getattr(tested, "total_tokens", "") if tested is not None else "", "judge_total_tokens": judge}


def _score(sample: Any):
    if not sample.scores:
        return None
    for name, value in sample.scores.items():
        if name.split("/")[-1] == "recovery_scorer":
            return value
    return next(iter(sample.scores.values()))


def _row(sample: Any, tested_model: str = "") -> dict[str, Any]:
    score = _score(sample)
    values = score.value if score is not None and isinstance(score.value, dict) else {}
    d = score.metadata if score is not None and isinstance(score.metadata, dict) else {}
    md = sample.metadata or {}
    cands = d.get("candidates") or []
    return {**_tokens(sample, tested_model),
            "sample_id": md.get("sample_id", sample.id), "topic": md.get("topic", ""), "kind": md.get("kind", ""), "pattern": md.get("pattern", ""),
            "control": int(bool(d.get("is_control", md.get("is_control", False)))),
            "found": values.get("found", ""), "correct": values.get("correct", ""), "false_positive": values.get("false_positive", ""),
            "evidence_threads": " ".join(th for c in cands for th in c.get("evidence_threads", [])),
            "planted_threads": " ".join(d.get("planted_threads") or []),
            "n_tool_calls": d.get("n_tool_calls", ""), "n_read": d.get("n_read", ""), "turns": d.get("turns", ""), "budget_hit": d.get("budget_hit", ""),
            "latency_s": round(float(sample.total_time), 3) if sample.total_time is not None else "",
            "secret": str(d.get("secret") or (cands[0]["secret"] if cands else ""))[:400]}


def rows_from_logs(logs: Iterable[EvalLog]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for log in logs:
        tested = getattr(getattr(log, "eval", None), "model", "") or ""
        for sample in log.samples or []:
            latest[(str(sample.id), int(sample.epoch))] = _row(sample, tested)
    return sorted(latest.values(), key=lambda r: str(r["sample_id"]))


def export_rows(log_dir: str | Path, csv_path: str | Path) -> list[dict[str, Any]]:
    infos = list_eval_logs(str(log_dir), formats=["eval"], descending=False)
    if not infos:
        raise FileNotFoundError(f"no Inspect .eval logs under {log_dir}")
    rows = rows_from_logs(read_eval_log(i.name) for i in infos)
    csv_path = Path(csv_path); csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    return rows
