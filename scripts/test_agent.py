#!/usr/bin/env python3
"""Run the tester: an agent investigates one mailbox per chain with read-only tools and reports the
secret it finds; a judge model decides whether the finding is the planted secret.

Each chain in the state file becomes one sample: the release's threads plus the chain's planted threads,
placed by date. --n-controls adds paired mailboxes with nothing planted. The report is three counts:
how many samples the tester said yes on, how many of those the judge accepted as the planted secret,
and how many controls it said yes on. Full trajectories are in Inspect .eval logs; rows.csv has one
line per sample.

Models are Inspect model strings: openrouter/anthropic/claude-opus-5.5, openai/gpt-5.6-sol,
vllm/Qwen/Qwen3-32B (a local server), or mockllm/model for a run without a model.

  python scripts/test_agent.py --model openrouter/anthropic/claude-opus-5.5 --judge-model openrouter/anthropic/claude-sonnet-4.6 \\
      --state logs/generate.json --out results/tester/opus
  python scripts/test_agent.py --model mockllm/model --judge-model mockllm/model --limit 1 --out results/tester/mock   # no model
  python scripts/test_agent.py --export-only --out results/tester/opus                                                 # rows.csv from logs
  inspect view --log-dir results/tester/opus/logs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="the tested model, an Inspect model string")
    ap.add_argument("--judge-model", help="the judge, an Inspect model string")
    ap.add_argument("--model-args", default="{}", help="JSON passed to Inspect when building the tested model")
    ap.add_argument("--state", default="logs/generate.json", help="generation state file with the chains")
    ap.add_argument("--release", default="data/release/background_2000.jsonl", help="the background mailbox")
    ap.add_argument("--noise", type=int, default=0, help="background threads per mailbox; 0 = the whole release")
    ap.add_argument("--budget", type=int, default=100, help="list/search/read calls per mailbox")
    ap.add_argument("--no-scan", dest="scan", action="store_false", default=True, help="allow an empty answer without full segment coverage")
    ap.add_argument("--rerank", type=int, default=40, help="search candidates the model reranks; 0 = plain BM25")
    ap.add_argument("--rerank-show", type=int, default=8)
    ap.add_argument("--candidate-count", dest="candidate_limit", type=int, default=1, help="ranked hypotheses per answer")
    ap.add_argument("--segment-size", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--min-invest", type=int, default=-1, help="searches/reads before an answer is accepted; -1 = the clue count")
    ap.add_argument("--n-controls", type=int, default=0, help="paired mailboxes with nothing planted")
    ap.add_argument("--limit", type=int, default=0, help="first N chains only")
    ap.add_argument("--sample-id", help="one sample id")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--max-samples", type=int, default=1, help="Inspect sample concurrency")
    ap.add_argument("--max-output-tokens", type=int)
    ap.add_argument("--out", required=True, help="directory for logs/ and rows.csv")
    ap.add_argument("--export-only", action="store_true", help="rows.csv from existing logs, no model")
    ap.add_argument("--display", choices=("full", "conversation", "rich", "plain", "log", "none"), default="plain")
    a = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except ImportError:
        pass
    out = Path(a.out); log_dir = out / "logs"; csv_path = out / "rows.csv"
    from src.tester.export import export_rows
    if a.export_only:
        rows = export_rows(log_dir, csv_path); print(summary(rows)); print(f"exported {len(rows)} row(s) to {csv_path}"); return 0
    if not a.model or not a.judge_model:
        raise SystemExit("--model and --judge-model are required unless --export-only")
    model_args = json.loads(a.model_args)
    from inspect_ai import eval
    from src.tester.task import secrecy_tester
    out.mkdir(parents=True, exist_ok=True); log_dir.mkdir(parents=True, exist_ok=True)
    task = secrecy_tester(judge_model=a.judge_model, state_path=a.state, release_path=a.release, noise=a.noise, budget=a.budget, scan=a.scan,
                          segment_size=a.segment_size, rerank_pool=a.rerank, rerank_show=a.rerank_show, candidate_limit=a.candidate_limit,
                          seed=a.seed, min_investigate=a.min_invest, n_controls=a.n_controls, limit=a.limit)
    gen = {"max_tokens": a.max_output_tokens} if a.max_output_tokens else {}
    logs = eval(task, model=a.model, model_args=model_args, log_dir=str(log_dir), log_format="eval", epochs=a.epochs,
                max_samples=a.max_samples, sample_id=a.sample_id, display=a.display, **gen)
    rows = export_rows(log_dir, csv_path)
    print(summary(rows))
    print(f"wrote {len(rows)} row(s) to {csv_path}\nlogs: {log_dir}  (inspect view --log-dir {log_dir})")
    return 1 if any(l.status != "success" for l in logs) else 0


def summary(rows) -> str:
    chains = [r for r in rows if not int(r.get("control") or 0)]
    controls = [r for r in rows if int(r.get("control") or 0)]
    n = lambda rs, k: sum(int(r.get(k) or 0) for r in rs)
    return (f"chains {len(chains)}: said yes {n(chains, 'found')}, correct secret {n(chains, 'correct')}; "
            f"controls {len(controls)}: said yes {n(controls, 'found')}")


if __name__ == "__main__":
    raise SystemExit(main())
