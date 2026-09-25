#!/usr/bin/env python3
"""Build the background mailbox from the corpus with one model choice.

Stages, each also a script of its own:
  classify   classify_topics.py   one call per email: its IAB tier-1 topic
  sample     sample_dataset.py    a seeded draw, equal per topic, round-robin over senders
  people     extract_people.py    one call per sampled email: the people in it
  anonymize  anonymize_llm.py     one pseudonym per person
  audit      audit_names.py       one call per email: surviving names
  release    make_release.py      data/release/background_2000.jsonl and its manifest
  banks      mailbox_profile.py, quiet_people.py, fresh_names.py

--limit caps the classified pool and scales the sampler's per-topic floor (limit/40). classify_topics
refuses more than 5,000 API calls without --allow-big-run.

  python scripts/build_mailbox.py --limit 500 --total 200
  python scripts/build_mailbox.py --engine vllm --preset qwen3-32b
  python scripts/build_mailbox.py --from people                  # or --only STAGE, --dry
  python scripts/build_mailbox.py --engine stub --limit 500 --total 200
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src.models.engine_factory import add_engine_args   # noqa: E402

STAGES = ["classify", "sample", "people", "anonymize", "audit", "release", "banks"]


def main() -> int:
    ap = add_engine_args(argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter))
    ap.add_argument("--limit", type=int, default=0, help="classify at most this many eligible emails (0 = all 133k)")
    ap.add_argument("--total", type=int, default=2000, help="emails in the mailbox")
    ap.add_argument("--seed", type=int, default=20260910, help="the sampling seed")
    ap.add_argument("--min-pool", type=int, default=0, help="a topic needs this many labelled emails to be sampled; default 100, or limit/40 when --limit is set")
    ap.add_argument("--from", dest="start", default="classify", choices=STAGES, help="start at this stage")
    ap.add_argument("--only", default="", choices=[""] + STAGES, help="run one stage")
    ap.add_argument("--dry", action="store_true", help="print the commands and stop")
    a = ap.parse_args()
    py = sys.executable
    model = ["--engine", a.engine, "--preset", a.preset, "--tp", str(a.tp), "--gpu-mem", str(a.gpu_mem)]
    min_pool = a.min_pool or (max(5, a.limit // 40) if a.limit else 100)
    if not a.eager: model.append("--no-eager")
    cmds = {
        "classify": [[py, "scripts/classify_topics.py", *model] + (["--limit", str(a.limit)] if a.limit else [])],
        "sample": [[py, "scripts/sample_dataset.py", "--total", str(a.total), "--seed", str(a.seed), "--min-pool", str(min_pool), "--with-text", "--whole-threads"]],
        "people": [[py, "scripts/extract_people.py", *model]],
        "anonymize": [[py, "scripts/anonymize_llm.py", "--seed", str(a.seed % 1000)]],
        "audit": [[py, "scripts/audit_names.py", *model]],
        "release": [[py, "scripts/make_release.py"]],
        "banks": [[py, "scripts/mailbox_profile.py"], [py, "scripts/quiet_people.py", *model], [py, "scripts/fresh_names.py"]],
    }
    todo = [a.only] if a.only else STAGES[STAGES.index(a.start):]
    for stage in todo:
        for cmd in cmds[stage]:
            print(f"\n== {stage}: {' '.join(cmd)}", flush=True)
            if a.dry: continue
            r = subprocess.run(cmd)
            if r.returncode != 0:
                print(f"stage {stage} failed ({r.returncode}); rerun with --from {stage}"); return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
