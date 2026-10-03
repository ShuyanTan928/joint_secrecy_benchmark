#!/usr/bin/env python3
"""The direct feed: each chain's planted emails and N random emails of the release go to the model in one prompt, and it
answers as the tester's answer tool does (ranked candidate secrets with evidence handles, or an empty list); the same
judge decides whether a finding is the planted secret. No tools, no budget, no scan. Noise is counted in emails and
nested across levels (the 100 of noise 100 are among the 200 of noise 200). --n-controls adds the same noise with
nothing planted, at every level above 0. The report is the tester's three counts per noise level, plus how many
findings cited a planted email. Full prompts and answers are in Inspect .eval logs; rows.csv has one line per sample.

  python scripts/direct_feed.py --dry-run --state data/benchmark/keystone30/state.json --out results/direct/dry   # sizes, no model
  python scripts/direct_feed.py --model openrouter/google/gemini-3.8-flash --judge-model openrouter/openai/gpt-6-sol \\
      --state data/benchmark/keystone30/state.json --n-controls 30 --out results/direct/gemini-3.8-flash
  python scripts/direct_feed.py --model mockllm/model --judge-model mockllm/model --limit 1 --noise 0,100 --out results/direct/mock
  python scripts/direct_feed.py --export-only --out results/direct/gemini-3.8-flash                                # rows.csv and table.md from logs
  python scripts/direct_feed.py --rejudge results/direct/gemini-3.8-flash --judge-model openrouter/openai/gpt-6-sol \\
      --out results/direct/gemini-3.8-flash_rejudged                                                              # the judge again over kept answers
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
    ap.add_argument("--release", default="data/release/background_2000.jsonl", help="the background the noise is drawn from")
    ap.add_argument("--noise", default="0,100,200,500", help="comma list of noise levels, in emails")
    ap.add_argument("--candidate-count", dest="candidate_limit", type=int, default=1, help="ranked candidates per answer")
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--n-controls", type=int, default=0, help="controls: the same noise with nothing planted, at every level above 0")
    ap.add_argument("--limit", type=int, default=0, help="first N chains only")
    ap.add_argument("--sample-id", help="one sample id, e.g. 00-lie-family-and-relations-n100")
    ap.add_argument("--exclude-ids", default="", help="comma list of sample ids to leave out, e.g. those a pilot already ran; the export merges every log under --out")
    ap.add_argument("--max-samples", type=int, default=4, help="Inspect sample concurrency")
    ap.add_argument("--max-output-tokens", type=int)
    ap.add_argument("--out", required=True, help="directory for logs/, rows.csv and table.md")
    ap.add_argument("--dry-run", action="store_true", help="build every sample, print sizes per level, write one example prompt per level; no model")
    ap.add_argument("--export-only", action="store_true", help="rows.csv and table.md from existing logs, no model")
    ap.add_argument("--rejudge", metavar="SRC", help="the judge again over the logs under SRC/logs, the model's answers kept; re-scored logs, rows.csv and table.md go to --out")
    ap.add_argument("--display", choices=("full", "conversation", "rich", "plain", "log", "none"), default="plain")
    a = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except ImportError:
        pass
    from src.tester.direct import build_samples, export_rows, parse_levels, rejudge, table
    out = Path(a.out); log_dir = out / "logs"; csv_path = out / "rows.csv"
    if a.rejudge:
        if not a.judge_model:
            raise SystemExit("--judge-model is required with --rejudge")
        written = rejudge(Path(a.rejudge) / "logs", a.judge_model, log_dir)
        rows = export_rows(log_dir, csv_path); md = table(rows); (out / "table.md").write_text(md + "\n")
        print(md); print(f"re-judged {len(written)} log(s) from {a.rejudge} -> {log_dir}; {len(rows)} row(s) to {csv_path}"); return 0
    if a.export_only:
        rows = export_rows(log_dir, csv_path); md = table(rows); (out / "table.md").write_text(md + "\n")
        print(md); print(f"exported {len(rows)} row(s) to {csv_path}"); return 0
    levels = parse_levels(a.noise)
    if a.dry_run:
        samples = build_samples(state_path=a.state, release_path=a.release, levels=levels, candidate_limit=a.candidate_limit, seed=a.seed,
                                n_controls=a.n_controls, limit=a.limit)
        ex = out / "examples"; ex.mkdir(parents=True, exist_ok=True)
        print("| noise | samples | controls | emails/sample | chars/sample | ~tokens/sample | ~tokens total |\n|---|---|---|---|---|---|---|")
        grand = 0
        for noise in levels:
            rs = [s for s in samples if s.metadata["noise"] == noise]
            if not rs:
                continue
            chars = [len(s.input) for s in rs]; toks = [c // 4 for c in chars]; grand += sum(toks)
            print(f"| {noise} | {len(rs)} | {sum(1 for s in rs if s.metadata['is_control'])} | {sum(s.metadata['n_emails'] for s in rs) / len(rs):.1f} "
                  f"| {sum(chars) / len(rs):.0f} | {sum(toks) / len(rs):.0f} | {sum(toks)} |")
            (ex / f"{rs[0].id}.md").write_text(rs[0].input)
        print(f"\n{len(samples)} sample(s), about {grand:,} input tokens in all (characters / 4), one call each plus one judge call per finding")
        print(f"example prompts in {ex}")
        return 0
    if not a.model or not a.judge_model:
        raise SystemExit("--model and --judge-model are required unless --dry-run or --export-only")
    model_args = json.loads(a.model_args)
    from inspect_ai import eval
    from src.tester.direct import direct_feed
    out.mkdir(parents=True, exist_ok=True); log_dir.mkdir(parents=True, exist_ok=True)
    task = direct_feed(judge_model=a.judge_model, state_path=a.state, release_path=a.release, noise=",".join(map(str, levels)),
                       candidate_limit=a.candidate_limit, seed=a.seed, n_controls=a.n_controls, limit=a.limit)
    ids = a.sample_id
    if a.exclude_ids:
        skip = {x.strip() for x in a.exclude_ids.split(",") if x.strip()}
        ids = [smp.id for smp in task.dataset if smp.id not in skip and (not a.sample_id or smp.id == a.sample_id)]
        print(f"{len(ids)} sample(s) after leaving out {len(skip)}")
    gen = {"max_tokens": a.max_output_tokens} if a.max_output_tokens else {}
    logs = eval(task, model=a.model, model_args=model_args, log_dir=str(log_dir), log_format="eval", max_samples=a.max_samples,
                sample_id=ids, display=a.display, **gen)
    rows = export_rows(log_dir, csv_path); md = table(rows); (out / "table.md").write_text(md + "\n")
    print(md)
    print(f"wrote {len(rows)} row(s) to {csv_path}\nlogs: {log_dir}  (inspect view --log-dir {log_dir})")
    return 1 if any(l.status != "success" for l in logs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
