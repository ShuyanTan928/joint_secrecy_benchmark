#!/usr/bin/env python3
"""The final run on the testers: one or more tested models, each over every kept chain of a state file, with the same judge;
the logs of each go to results/tester/<model>/ (Inspect .eval logs, rows.csv, run.log), and one table over all of them
to results/tester/table.md and table.csv.

  python scripts/run_testers.py --models openrouter/anthropic/claude-opus-5.5,openrouter/google/gemini-3.7-flash \\
      --judge-model openrouter/openai/gpt-6-sol --state logs/run44.json --n-controls 30
  python scripts/run_testers.py --models mockllm/model --judge-model mockllm/model --state logs/run43.json --limit 1   # no model
  python scripts/run_testers.py --table-only --out-root results/tester                                                  # the table from rows.csv files

A model whose rows.csv already exists is not run again unless --redo; the table always covers every rows.csv under --out-root."""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", model).strip("_")


def run_one(model: str, a) -> Path:
    out = Path(a.out_root) / slug(model); out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT / "scripts" / "test_agent.py"), "--model", model, "--judge-model", a.judge_model, "--state", a.state,
           "--release", a.release, "--out", str(out), "--n-controls", str(a.n_controls), "--budget", str(a.budget), "--noise", str(a.noise),
           "--max-samples", str(a.max_samples), "--epochs", str(a.epochs), "--display", "plain"]
    if a.limit: cmd += ["--limit", str(a.limit)]
    if a.model_args: cmd += ["--model-args", a.model_args]
    if a.helper_tokens: cmd += ["--helper-tokens", str(a.helper_tokens)]
    if a.exclude_ids: cmd += ["--exclude-ids", a.exclude_ids]
    print(f"\n== {model} -> {out}", flush=True)
    with (out / "run.log").open("w") as log:
        log.write(" ".join(cmd) + "\n\n"); log.flush()
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            print("   " + line.rstrip(), flush=True); log.write(line)
        p.wait()
    if p.returncode: print(f"   {model}: exit {p.returncode}, see {out / 'run.log'}")
    return out


def load_rows(out: Path) -> list[dict]:
    f = out / "rows.csv"
    return list(csv.DictReader(f.open())) if f.exists() else []


def table(out_root: Path) -> tuple[str, list[dict]]:
    """One line per model: chains, said yes, correct, precision, recall, controls said yes, correct by thread count, by pattern, by kind, tool calls, tokens."""
    lines, csv_rows = [], []
    for d in sorted(p for p in out_root.iterdir() if p.is_dir() and (p / "rows.csv").exists()):
        rows = load_rows(d); model = d.name
        if not rows: continue
        chains = [r for r in rows if not int(r.get("control") or 0)]; controls = [r for r in rows if int(r.get("control") or 0)]
        n = lambda rs, k: sum(int(float(r.get(k) or 0)) for r in rs)
        yes, ok = n(chains, "found"), n(chains, "correct"); cyes = n(controls, "found")
        by_n = Counter(); tot_n = Counter()
        for r in chains:
            k = len((r.get("planted_threads") or "").split()); tot_n[k] += 1; by_n[k] += int(float(r.get("correct") or 0))
        by = lambda key: ", ".join(f"{v}: {sum(int(float(r.get('correct') or 0)) for r in chains if r.get(key) == v)}/{sum(1 for r in chains if r.get(key) == v)}"
                                   for v in sorted({r.get(key) for r in chains} - {"", None}))
        mean = lambda k: (sum(float(r.get(k) or 0) for r in chains) / len(chains)) if chains else 0
        rec = {"model": model, "chains": len(chains), "said_yes": yes, "correct": ok,
               "precision": round(ok / yes, 2) if yes else "", "recall": round(ok / len(chains), 2) if chains else "",
               "controls": len(controls), "controls_said_yes": cyes, "false_alarm": round(cyes / len(controls), 2) if controls else "",
               "correct_by_threads": ", ".join(f"{k}: {by_n[k]}/{tot_n[k]}" for k in sorted(tot_n)), "by_pattern": by("pattern"), "by_kind": by("kind"),
               "mean_tool_calls": round(mean("n_tool_calls"), 1), "mean_tokens": int(mean("total_tokens"))}
        csv_rows.append(rec)
    cols = ["model", "chains", "said_yes", "correct", "precision", "recall", "controls", "controls_said_yes", "false_alarm", "correct_by_threads", "by_pattern", "by_kind", "mean_tool_calls", "mean_tokens"]
    lines.append("| " + " | ".join(cols) + " |"); lines.append("|" + "---|" * len(cols))
    for r in csv_rows: lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    md = "\n".join(lines)
    (out_root / "table.md").write_text(md + "\n")
    with (out_root / "table.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(csv_rows)
    return md, csv_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="", help="comma list of tested models, Inspect model strings (openrouter/<slug>, mockllm/model)")
    ap.add_argument("--judge-model", default="openrouter/openai/gpt-6-sol", help="the judge, an Inspect model string")
    ap.add_argument("--model-args", default="", help="JSON passed to Inspect when building each tested model")
    ap.add_argument("--state", default="logs/generate.json", help="generation state file; kept chains become the samples")
    ap.add_argument("--release", default="data/release/background_2000.jsonl")
    ap.add_argument("--out-root", default="results/tester")
    ap.add_argument("--n-controls", type=int, default=0, help="paired mailboxes with nothing planted")
    ap.add_argument("--limit", type=int, default=0, help="first N chains only")
    ap.add_argument("--budget", type=int, default=100); ap.add_argument("--noise", type=int, default=0)
    ap.add_argument("--max-samples", type=int, default=4, help="Inspect sample concurrency"); ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--helper-tokens", type=int, default=0, help="output allowance of the tester's reranking and note-taking helpers (default 300)")
    ap.add_argument("--exclude-ids", default="", help="comma list of sample ids to leave out, e.g. those a pilot already ran")
    ap.add_argument("--redo", action="store_true", help="run a model again even when its rows.csv exists")
    ap.add_argument("--table-only", action="store_true", help="only the table, from the rows.csv files present")
    a = ap.parse_args()
    out_root = Path(a.out_root); out_root.mkdir(parents=True, exist_ok=True)
    if not a.table_only:
        for m in [x.strip() for x in a.models.split(",") if x.strip()]:
            if (out_root / slug(m) / "rows.csv").exists() and not a.redo: print(f"== {m}: rows.csv exists, skipped (--redo to run again)"); continue
            run_one(m, a)
    md, rows = table(out_root)
    print("\n" + md + f"\n\nwritten to {out_root / 'table.md'} and table.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
