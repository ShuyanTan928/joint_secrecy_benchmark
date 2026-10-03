#!/usr/bin/env python3
"""The direct feed on one or more tested models, each over the chains of a state file at the same noise levels with the same
judge; the results of each go to results/direct/<model>/ (Inspect .eval logs, rows.csv, table.md, run.log), and one table over
all of them, one line per model and noise level, to results/direct/table.md and table.csv.

  python scripts/run_direct.py --models openrouter/anthropic/claude-opus-5.5,openrouter/openai/gpt-6-sol \\
      --judge-model openrouter/openai/gpt-6-sol --state data/benchmark/keystone30/state.json --noise 0,100,200,500,1000,2000 --n-controls 30
  python scripts/run_direct.py --models mockllm/model --judge-model mockllm/model --limit 1 --noise 0,100   # no model
  python scripts/run_direct.py --table-only --out-root results/direct                                       # the table from the rows.csv files

A model whose rows.csv already exists is not run again unless --redo; --tag adds a suffix to the model's folder, for a second
run of the same model under another prompt. The table always covers every rows.csv under --out-root."""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLS = ["model", "noise", "chains", "said_yes", "correct", "recall", "evidence_hit", "controls", "controls_said_yes", "false_alarm",
        "unparsed", "mean_in_tokens", "mean_out_tokens"]


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", model).strip("_")


def run_one(model: str, a) -> Path:
    out = Path(a.out_root) / (slug(model) + (f"_{a.tag}" if a.tag else "")); out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT / "scripts" / "direct_feed.py"), "--model", model, "--judge-model", a.judge_model, "--state", a.state,
           "--release", a.release, "--noise", a.noise, "--n-controls", str(a.n_controls), "--prompt", a.prompt, "--candidate-count", str(a.candidate_limit),
           "--seed", str(a.seed), "--max-samples", str(a.max_samples), "--display", "plain", "--out", str(out)]
    if a.limit: cmd += ["--limit", str(a.limit)]
    if a.model_args: cmd += ["--model-args", a.model_args]
    if a.max_output_tokens: cmd += ["--max-output-tokens", str(a.max_output_tokens)]
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


def table(out_root: Path) -> tuple[str, list[dict]]:
    """One line per model and noise level: chains, said yes, correct, recall, findings citing a planted email, controls said yes,
    false-alarm rate, unparsed answers, mean input and output tokens."""
    recs = []
    for d in sorted(p for p in out_root.iterdir() if p.is_dir() and (p / "rows.csv").exists()):
        rows = list(csv.DictReader((d / "rows.csv").open()))
        n = lambda rs, k: sum(int(float(r.get(k) or 0)) for r in rs)
        mean = lambda rs, k: (sum(float(r[k]) for r in rs if r.get(k) not in ("", None)) / max(1, sum(1 for r in rs if r.get(k) not in ("", None))))
        for noise in sorted({int(r.get("noise") or 0) for r in rows}):
            rs = [r for r in rows if int(r.get("noise") or 0) == noise]
            chains = [r for r in rs if not int(r.get("control") or 0)]; controls = [r for r in rs if int(r.get("control") or 0)]
            ok = n(chains, "correct"); cyes = n(controls, "found")
            recs.append({"model": d.name, "noise": noise, "chains": len(chains), "said_yes": n(chains, "found"), "correct": ok,
                         "recall": round(ok / len(chains), 2) if chains else "", "evidence_hit": sum(1 for r in chains if int(float(r.get("evidence_planted") or 0)) > 0),
                         "controls": len(controls), "controls_said_yes": cyes, "false_alarm": round(cyes / len(controls), 2) if controls else "",
                         "unparsed": sum(1 for r in rs if not int(float(r.get("parsed") or 0))),
                         "mean_in_tokens": int(mean(rs, "in_tokens")), "mean_out_tokens": int(mean(rs, "out_tokens"))})
    lines = ["| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)] + ["| " + " | ".join(str(r[c]) for c in COLS) + " |" for r in recs]
    md = "\n".join(lines)
    (out_root / "table.md").write_text(md + "\n")
    with (out_root / "table.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(recs)
    return md, recs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="", help="comma list of tested models, Inspect model strings (openrouter/<slug>, openai/<model>, mockllm/model)")
    ap.add_argument("--judge-model", default="openrouter/openai/gpt-6-sol", help="the judge, an Inspect model string")
    ap.add_argument("--model-args", default="", help="JSON passed to Inspect when building each tested model")
    ap.add_argument("--state", default="data/benchmark/keystone30/state.json", help="generation state file; kept chains become the samples")
    ap.add_argument("--release", default="data/release/background_2000.jsonl", help="the background the noise is drawn from")
    ap.add_argument("--noise", default="0,100,200,500", help="comma list of noise levels, in emails; 2000 is the whole release")
    ap.add_argument("--n-controls", type=int, default=0, help="controls: the same noise with nothing planted, at every level above 0")
    ap.add_argument("--prompt", default="prompts/direct.md", help="prompts/direct.md (the tester's words) or prompts/direct_plain.md (the bare question)")
    ap.add_argument("--candidate-count", dest="candidate_limit", type=int, default=1)
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--limit", type=int, default=0, help="first N chains only")
    ap.add_argument("--exclude-ids", default="", help="comma list of sample ids to leave out")
    ap.add_argument("--max-samples", type=int, default=4, help="Inspect sample concurrency")
    ap.add_argument("--max-output-tokens", type=int)
    ap.add_argument("--tag", default="", help="suffix for the model's folder, e.g. plain for a run under the bare question")
    ap.add_argument("--out-root", default="results/direct")
    ap.add_argument("--redo", action="store_true", help="run a model again even when its rows.csv exists")
    ap.add_argument("--table-only", action="store_true", help="only the table, from the rows.csv files present")
    a = ap.parse_args()
    out_root = Path(a.out_root); out_root.mkdir(parents=True, exist_ok=True)
    if not a.table_only:
        for m in [x.strip() for x in a.models.split(",") if x.strip()]:
            folder = out_root / (slug(m) + (f"_{a.tag}" if a.tag else ""))
            if (folder / "rows.csv").exists() and not a.redo: print(f"== {m}: {folder / 'rows.csv'} exists, skipped (--redo to run again)"); continue
            run_one(m, a)
    md, _ = table(out_root)
    print("\n" + md + f"\n\nwritten to {out_root / 'table.md'} and table.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
