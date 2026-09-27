#!/usr/bin/env python3
"""Remove the secrets the background already holds, before anything is planted in it.

The tester runs on the untouched mailbox with several models, each asked to report every fact it finds
that one person keeps from another, with the emails that support it. A thread that two or more models
(--agree) cite as evidence is treated as a real secret and removed from the release. Runs per model are
Inspect epochs; a model votes for a thread once, however many runs cite it.

  python scripts/clean_background.py --models openrouter/anthropic/claude-opus-5.5,openrouter/openai/gpt-6-sol --runs 2 --out results/clean
  python scripts/clean_background.py --models mockllm/model --out results/clean_mock          # the path, no model
  python scripts/clean_background.py --out results/clean --apply                               # remove the agreed threads from the release
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def handle_to_thread_ids(release: str, settings) -> dict[str, str]:
    """Thread handle -> release thread_id, for the sweep mailbox (background only, deterministic)."""
    from src.tester.core import background_case, build_mailbox
    env = build_mailbox(background_case(), settings, release=release)
    rows = [json.loads(l) for l in Path(release).read_text().splitlines() if l.strip()]
    tid_of = {r["email_id"]: r["thread_id"] for r in rows}
    return {th: tid_of[env.msgs[mh[0]]["id"]] for th, mh in env.thread_msgs.items() if env.msgs[mh[0]]["id"] in tid_of}


def collect_votes(log_dir: Path, mapping: dict[str, str]) -> tuple[dict[str, set], dict[str, list]]:
    """thread_id -> models that cited it; thread_id -> the secrets they reported, from the .eval logs."""
    from inspect_ai.log import list_eval_logs, read_eval_log
    votes: dict[str, set] = defaultdict(set); said: dict[str, list] = defaultdict(list)
    for info in list_eval_logs(str(log_dir), formats=["eval"], descending=False):
        log = read_eval_log(info.name); model = getattr(getattr(log, "eval", None), "model", "") or "?"
        for sample in log.samples or []:
            for value in (sample.scores or {}).values():
                for c in (getattr(value, "metadata", None) or {}).get("candidates") or []:
                    for th in c.get("evidence_threads") or []:
                        tid = mapping.get(th)
                        if tid:
                            votes[tid].add(model); said[tid].append({"model": model, "secret": c.get("secret", "")})
    return votes, said


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="", help="comma list of Inspect model strings to sweep with")
    ap.add_argument("--runs", type=int, default=1, help="runs per model")
    ap.add_argument("--release", default="data/release/background_2000.jsonl")
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--candidate-count", type=int, default=5, help="at most this many secrets per run")
    ap.add_argument("--no-scan", dest="scan", action="store_false", default=True)
    ap.add_argument("--rerank", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--agree", type=int, default=2, help="models that must cite a thread for it to be removed")
    ap.add_argument("--out", required=True, help="directory for logs/, votes.json, removed.jsonl")
    ap.add_argument("--apply", action="store_true", help="write the release without the agreed threads")
    ap.add_argument("--display", choices=("full", "conversation", "rich", "plain", "log", "none"), default="plain")
    a = ap.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except ImportError:
        pass
    out = Path(a.out); log_dir = out / "logs"; out.mkdir(parents=True, exist_ok=True); log_dir.mkdir(exist_ok=True)
    from src.tester.core import MailboxSettings
    settings = MailboxSettings(seed=a.seed, budget=a.budget, scan=a.scan, rerank_pool=a.rerank, candidate_limit=a.candidate_count, candidates_exact=False)

    if a.models:
        from inspect_ai import eval
        from src.tester.task import secrecy_tester
        task = secrecy_tester(release_path=a.release, budget=a.budget, scan=a.scan, rerank_pool=a.rerank, candidate_limit=a.candidate_count,
                              seed=a.seed, sweep=True)
        for model in [m.strip() for m in a.models.split(",") if m.strip()]:
            print(f"== sweep with {model}, {a.runs} run(s)", flush=True)
            eval(task, model=model, log_dir=str(log_dir), log_format="eval", epochs=a.runs, display=a.display)

    mapping = handle_to_thread_ids(a.release, settings)
    votes, said = collect_votes(log_dir, mapping)
    agreed = sorted(t for t, ms in votes.items() if len(ms) >= a.agree)
    (out / "votes.json").write_text(json.dumps({"agree": a.agree, "threads": {t: {"models": sorted(ms), "reported": said[t]} for t, ms in votes.items()},
                                                "removed": agreed}, indent=1, ensure_ascii=False))
    models_seen = sorted({m for ms in votes.values() for m in ms})
    print(f"models with votes: {models_seen}; threads cited by any model: {len(votes)}; by {a.agree} or more: {len(agreed)}")
    if a.apply:
        rows = [json.loads(l) for l in Path(a.release).read_text().splitlines() if l.strip()]
        keep = [r for r in rows if r["thread_id"] not in set(agreed)]
        removed = [r for r in rows if r["thread_id"] in set(agreed)]
        (out / "removed.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in removed))
        Path(a.release).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
        note = Path(a.release).with_suffix(".cleaned.json")
        note.write_text(json.dumps({"removed_threads": agreed, "removed_emails": len(removed), "agree": a.agree, "models": models_seen}, indent=1))
        print(f"removed {len(agreed)} thread(s), {len(removed)} email(s); release now {len(keep)} emails; record in {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
