#!/usr/bin/env python3
"""A release bundle for a direct-feed run: summary.md and summary.json, rows.csv, table.md and table.csv, conversations.jsonl.gz
(one record per sample: the prompt, the model's answer, the candidates, the score, the judge's verdicts), judge-decisions.json,
provenance.json (the commits, source and input hashes, the logs' hashes, token use, the prompt rebuild check, limits),
REPRODUCE.md and SHA256SUMS, zipped; the summary, rows, provenance and checksums are copied beside the zip for the release page.

  python scripts/bundle_direct.py --src results/direct/gemini-3.8-flash --tag keystone30-direct-gemini-3.8-flash-2026-10-03 \\
      --tested-commit 11c9d53 [--earlier-judge results/direct/gemini-3.8-flash_500_earlier_judge] [--release-commit HEAD]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from inspect_ai.log import list_eval_logs, read_eval_log   # noqa: E402

from src.tester.core import answer_key, cases_index, chain_threads, judge_emails   # noqa: E402
from src.tester.direct import FIELDS, build_samples, parse_levels, rows_from_logs, table   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/ShuyanTan928/joint_secrecy_benchmark"
SOURCE_FILES = ["src/tester/core.py", "src/tester/task.py", "src/tester/direct.py", "src/andcheck.py", "scripts/direct_feed.py",
                "scripts/run_direct.py", "prompts/direct.md", "prompts/match.md", "pyproject.toml"]
INPUT_FILES = ["data/benchmark/keystone30/state.json", "data/release/background_2000.jsonl", "prompts/direct.md", "prompts/match.md"]
RATES = {"openrouter/google/gemini-3.8-flash": (0.75, 3.75), "openrouter/openai/gpt-6-sol": (2.0, 10.0)}   # $ per million tokens, OpenRouter's list of 2026-10-02


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def blob_at(commit: str, path: str) -> str | None:
    try:
        return git("rev-parse", f"{commit}:{path}")
    except subprocess.CalledProcessError:
        return None


def judge_events(sample) -> list[dict]:
    out = []
    for e in sample.events or []:
        if getattr(e, "event", "") == "model" and "gemini" not in str(getattr(e, "model", "")) and getattr(e, "output", None) is not None:
            out.append({"model": e.model, "completion": e.output.completion, "stop_reason": getattr(e.output, "stop_reason", None)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="the run folder: logs/ and rows.csv")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--tested-commit", required=True, help="the commit whose code ran")
    ap.add_argument("--release-commit", default="HEAD")
    ap.add_argument("--earlier-judge", default="", help="a folder whose logs hold the first judging of part of the run, counted in the cost")
    ap.add_argument("--state", default="data/benchmark/keystone30/state.json")
    ap.add_argument("--out-root", default="results/release")
    a = ap.parse_args()
    tested, released = git("rev-parse", a.tested_commit), git("rev-parse", a.release_commit)
    src = Path(a.src); out = Path(a.out_root) / a.tag; inner = out / a.tag; inner.mkdir(parents=True, exist_ok=True)

    infos = list_eval_logs(str(src / "logs"), formats=["eval"], descending=False)
    logs = [read_eval_log(i.name) for i in infos]
    rows = rows_from_logs(logs)
    with (inner / "rows.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(FIELDS)); w.writeheader(); w.writerows(rows)
    md = table(rows); (inner / "table.md").write_text(md + "\n")
    with (inner / "table.csv").open("w", newline="") as f:
        cols = [c.strip() for c in md.splitlines()[0].strip("|").split("|")]
        w = csv.writer(f); w.writerow(cols)
        for line in md.splitlines()[2:]: w.writerow([c.strip() for c in line.strip("|").split("|")])

    # ---- the samples, newest log wins per id
    latest = {}
    for log in logs:
        for s in log.samples or []:
            latest[str(s.id)] = (log, s)
    judge_model = next((str(log.eval.task_args.get("judge_model")) for log in logs if log.eval.task_args.get("judge_model")), "")
    tested_model = logs[0].eval.model
    cases = cases_index(a.state)
    usage = defaultdict(lambda: [0, 0]); judged = 0; invalid = 0; unparsed = 0; errors = 0
    records = []; decisions = []
    for sid, (log, s) in sorted(latest.items()):
        md_ = s.metadata or {}; sc = next(iter(s.scores.values())) if s.scores else None
        d = (sc.metadata if sc else {}) or {}; v = (sc.value if sc else {}) or {}
        for m, u in (s.model_usage or {}).items():
            usage[m][0] += u.input_tokens or 0; usage[m][1] += u.output_tokens or 0
        errors += int(bool(s.error)); unparsed += int(not d.get("parsed", False))
        prompt_in = s.input if isinstance(s.input, str) else "\n".join(getattr(m, "text", "") for m in s.input)
        completion = s.output.completion if s.output else ""
        case = cases.get(md_.get("case", ""))
        verdicts = []
        if not md_.get("is_control") and d.get("candidates") and case:
            key = answer_key(case); secret = "\n".join(f"{k}: {x}" for k, x in key.items() if k in ("secret", "actor", "victim") and x)
            shell = (ROOT / "prompts" / "match.md").read_text().replace("<<SECRET>>", secret).replace("<<EMAILS>>", judge_emails(chain_threads(case.chain)))
            reasons = d.get("judge_reason", "")
            for pos, c in enumerate(d["candidates"], 1):
                judged += 1
                matched = bool(v.get("correct")) and d.get("candidate_rank") == pos
                verdicts.append({"candidate": pos, "judge_prompt": shell.replace("<<FINDING>>", c["secret"]), "match": matched, "reason": reasons})
                if "judge gave no reason" in reasons: invalid += 1
                decisions.append({"sample_id": sid, "noise": md_.get("noise"), "candidate": pos, "finding": c["secret"], "evidence_email_ids": c["evidence_email_ids"],
                                  "valid": "judge gave no reason" not in reasons, "match": matched, "reason": reasons})
                if matched: break
        records.append({"sample_id": sid, "epoch": s.epoch, "control": bool(md_.get("is_control")), "case": md_.get("case"), "topic": md_.get("topic"), "kind": md_.get("kind"),
                        "pattern": md_.get("pattern"), "noise": md_.get("noise"), "n_emails": md_.get("n_emails"), "chars": md_.get("chars"), "planted_handles": md_.get("planted_handles"),
                        "target": json.loads(s.target) if isinstance(s.target, str) and s.target.startswith("{") else s.target,
                        "input_sha256": hashlib.sha256(prompt_in.encode()).hexdigest(),
                        "messages": [{"role": "user", "content": prompt_in}, {"role": "assistant", "content": completion}],
                        "candidates": d.get("candidates", []), "score": {"value": v, "explanation": sc.explanation if sc else "", "metadata": {k: x for k, x in d.items() if k != "candidates"}},
                        "judge": verdicts, "judge_raw": judge_events(s), "model_usage": {m: {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "total_tokens": u.total_tokens} for m, u in (s.model_usage or {}).items()},
                        "log": Path(log.location).name, "total_time_s": s.total_time})
    with gzip.open(inner / "conversations.jsonl.gz", "wt") as f:
        for r in records: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (inner / "judge-decisions.json").write_text(json.dumps(decisions, indent=1, ensure_ascii=False))

    # ---- the prompts rebuilt from this checkout against the logged ones
    args0 = logs[-1].eval.task_args
    levels = sorted({int(r["noise"]) for r in rows})
    rebuilt = {smp.id: smp.input for smp in build_samples(state_path=a.state, release_path=str(args0.get("release_path", "data/release/background_2000.jsonl")),
                                                          levels=levels, candidate_limit=int(args0.get("candidate_limit", 1)), seed=int(args0.get("seed", 20260927)),
                                                          n_controls=int(args0.get("n_controls", 0)))}
    same = sum(1 for r in records if hashlib.sha256(rebuilt.get(r["sample_id"], "").encode()).hexdigest() == r["input_sha256"])

    # ---- cost
    cost = {}; total = 0.0
    for m, (i, o) in usage.items():
        ri, ro = RATES.get(m, (0, 0)); c = i / 1e6 * ri + o / 1e6 * ro; total += c
        cost[m] = {"input_tokens": i, "output_tokens": o, "usd_at_listed_rates": round(c, 2)}
    earlier = {}
    if a.earlier_judge:
        for info in list_eval_logs(str(Path(a.earlier_judge) / "logs"), formats=["eval"]):
            for s in read_eval_log(info.name).samples or []:
                for m, u in (s.model_usage or {}).items():
                    if m != tested_model:
                        earlier.setdefault(m, [0, 0]); earlier[m][0] += u.input_tokens or 0; earlier[m][1] += u.output_tokens or 0
        for m, (i, o) in earlier.items():
            ri, ro = RATES.get(m, (0, 0)); c = i / 1e6 * ri + o / 1e6 * ro; total += c
            earlier[m] = {"input_tokens": i, "output_tokens": o, "usd_at_listed_rates": round(c, 2)}

    # ---- per level and overall
    per = []
    for lvl in levels:
        rs = [r for r in rows if int(r["noise"]) == lvl]; ch = [r for r in rs if r["control"] == 0]; ct = [r for r in rs if r["control"] == 1]
        yes = sum(r["found"] for r in ch); ok = sum(r["correct"] for r in ch)
        per.append({"noise": lvl, "secret_cases": len(ch), "findings_on_secret_cases": yes, "correct": ok, "recall": ok / len(ch) if ch else None,
                    "precision": ok / yes if yes else None, "correct_citing_planted_only": sum(1 for r in ch if r["correct"] and set(r["evidence_cited"].split()) <= set(r["planted_handles"].split())),
                    "controls": len(ct), "findings_on_controls": sum(r["found"] for r in ct), "control_false_alarm_rate": (sum(r["found"] for r in ct) / len(ct)) if ct else None,
                    "mean_input_tokens": int(sum(float(r["in_tokens"] or 0) for r in rs) / len(rs))})
    ch_all = [r for r in rows if r["control"] == 0]; ct_all = [r for r in rows if r["control"] == 1]
    yes_all = sum(r["found"] for r in ch_all); ok_all = sum(r["correct"] for r in ch_all); cyes_all = sum(r["found"] for r in ct_all)
    runs = [{"log": Path(l.location).name, "samples": len(l.samples or []), "started_at": l.stats.started_at, "completed_at": l.stats.completed_at,
             "recorded_git_revision": getattr(l.eval.revision, "commit", None)} for l in logs]
    summary = {"benchmark": "Keystone30, direct feed", "tester_model": tested_model.split("/")[-1], "judge_model": judge_model.split("/")[-1], "provider": "OpenRouter",
               "noise_levels": levels, "secret_cases": len({r["case"] for r in ch_all}), "controls": len({r["case"] for r in ct_all}), "samples": len(rows),
               "secret_prompts": len(ch_all), "findings_on_secret_cases": yes_all, "correct_secret_recoveries": ok_all, "recall": ok_all / len(ch_all) if ch_all else None,
               "precision": ok_all / yes_all if yes_all else None, "control_prompts": len(ct_all), "findings_on_controls": cyes_all,
               "control_false_alarm_rate": cyes_all / len(ct_all) if ct_all else None, "per_level": per, "sample_errors": errors, "unparsed_answers": unparsed,
               "judge_calls": judged, "invalid_judge_responses": invalid, "prompts_rebuilt_from_release_commit_matching_logged": f"{same}/{len(records)}",
               "token_use_and_cost_at_listed_rates": cost, "earlier_judging_of_part_one": earlier, "cost_usd_by_token_counts": round(total, 2),
               "cost_usd_openrouter_account": None, "runs": runs}
    (inner / "summary.json").write_text(json.dumps(summary, indent=1))

    # ---- provenance
    prov = {"repository": REPO, "release_tag": a.tag, "tested_commit": tested, "release_commit": released,
            "logs_recorded_git_revision": {r["log"]: r["recorded_git_revision"] for r in runs},
            "note_on_commits": "The logs record the last commit at run time with uncommitted changes; the code that ran is the tested commit's "
                               "(committed from the same working tree during the run). The release commit renames the question file and removes "
                               "a prompt option; the question's text is unchanged, and every prompt rebuilt from the release commit matches the logged one (see summary.json).",
            "source_files": {p: {"git_blob_sha_tested": blob_at(tested, p), "git_blob_sha_release": blob_at(released, p), "sha256_now": sha256(ROOT / p) if (ROOT / p).exists() else None,
                                 "same_in_both_commits": blob_at(tested, p) == blob_at(released, p)} for p in SOURCE_FILES},
            "question_file_at_tested_commit": {"path": "prompts/direct_plain.md", "git_blob_sha": blob_at(tested, "prompts/direct_plain.md"),
                                               "same_text_as_release_prompts_direct_md": blob_at(tested, "prompts/direct_plain.md") == blob_at(released, "prompts/direct.md")},
            "input_sha256": {p: sha256(ROOT / p) for p in INPUT_FILES},
            "original_native_log_sha256": {Path(i.name).name: sha256(Path(i.name.replace("file:", "", 1))) for i in infos},
            "tester_model": tested_model, "judge_model": judge_model, "provider": "OpenRouter", "api": "OpenAI-compatible chat completions",
            "task_args": args0, "inspect_ai": logs[-1].eval.packages.get("inspect_ai"), "python": sys.version.split()[0],
            "judge": "sees the planted secret, its keeper and the one kept from, and the planted emails; one call per candidate, first match wins; output allowance 1,500 tokens",
            "noise_draw": "per chain, seeded: the release's own emails from the planted addresses first, then emails of senders with more than one email in the release, then the rest; a level takes the first N",
            "limitations": ["a single run of one reader model and one judge model; API reruns can differ",
                            "part one (the 30 planted cases at noise 500) was judged first by a judge that saw only the secret, then judged again by the released judge with the reader's answers kept; the second verdicts stand",
                            "cost is computed from the logs' token counts at OpenRouter's listed rates; the account's own figure was not read",
                            "the planted emails differ from the release's in form (unwrapped lines, no quoted history, length), which a reader can use; see docs/run_log.md"]}
    (inner / "provenance.json").write_text(json.dumps(prov, indent=1))

    # ---- summary.md and REPRODUCE.md
    lv = {p["noise"]: p for p in per}
    def pct(x): return f"{100 * x:.1f}%"
    rec_line = ", ".join(f"{lv[n]['correct']}/{lv[n]['secret_cases']} at noise {n}" for n in levels)
    ctl_line = ", ".join(f"{lv[n]['findings_on_controls']}/{lv[n]['controls']} at {n}" for n in levels if lv[n]["controls"])
    planted_only = sum(p["correct_citing_planted_only"] for p in per)
    g = cost.get(tested_model, {}); j = cost.get(judge_model, {}); je = earlier.get(judge_model, {})
    parts = "; ".join(f"{r['samples']} samples {r['started_at'][11:16]}–{r['completed_at'][11:16]} UTC" for r in runs)
    text = f"""{summary['tester_model']} read all **{summary['secret_cases']} planted-secret cases and {summary['controls']} controls** at {len(levels)} noise sizes, {', '.join(map(str, levels))} release emails around the planted threads ({len(rows)} prompts, one call each); {summary['judge_model']} served as the judge.

- **Secrets recovered: {rec_line}** ({ok_all}/{len(ch_all)}, {pct(summary['recall'])} recall). The reader returned a candidate on {yes_all} of {len(ch_all)} planted prompts; {ok_all} matched ({pct(summary['precision'])} precision). {planted_only} of the {ok_all} matched findings cited planted emails only.
- **Controls with a finding: {ctl_line}** ({cyes_all}/{len(ct_all)}). Asked whether anyone is keeping something from someone, the reader names the most secret-like matter in the mailbox, and the release has matters of its own (a surprise party, a trip kept from coworkers, conference shirts kept from attendees); they are listed in judge-decisions.json.
- All {len(rows)} samples finished; {len(rows) - unparsed} of {len(rows)} answers parsed as JSON; {judged} judge calls, {judged - invalid} with a valid verdict. The judge sees the planted emails beside the secret, keeper and victim, so a finding in the emails' words is not refused for the key's. Every prompt rebuilt from the release commit matches the logged prompt ({same}/{len(records)}).

**How it ran.** OpenRouter, {summary['tester_model']} reading and {summary['judge_model']} judging, one epoch, four concurrent samples, seed {args0.get('seed')}, one candidate per answer. Two parts on the same code ({parts}): first the 30 planted cases at noise 500, then the other {len(rows) - 30} samples with `--exclude-ids`; the rows are merged. The first part's findings were judged first by a judge that saw only the secret and then judged again by the released judge with the reader's answers kept; one verdict changed (chain 21, refused to matched). Cost by the logs' token counts at OpenRouter's listed rates: ${g.get('usd_at_listed_rates', 0):.2f} for {summary['tester_model']} ({g.get('input_tokens', 0) / 1e6:.1f}M input, {g.get('output_tokens', 0) / 1e6:.2f}M output tokens) and ${j.get('usd_at_listed_rates', 0) + je.get('usd_at_listed_rates', 0):.2f} for the judge; the account total was not read.

Tested commit: {tested[:12]}. Release commit: {released[:12]}. Run: {runs[0]['started_at'][:10]}.

Assets contain the summary, per-sample CSV, per-level table, portable conversations with each prompt, answer and judge verdict, judge decisions, provenance, reproduction instructions, and SHA-256 checksums. The reader and the judge are different models; this is a small, single-run benchmark result, not independent human ground truth.
"""
    (inner / "summary.md").write_text(text)
    (inner / "REPRODUCE.md").write_text(f"""# Reproduce the Keystone30 direct-feed run of {summary['tester_model']}

Use repository {REPO} at commit {released}.

Set OPENROUTER_API_KEY to your own OpenRouter key; keep it outside the release files. From the benchmark checkout:

```sh
uv sync
uv pip install 'inspect-ai=={logs[-1].eval.packages.get("inspect_ai")}'
uv run --no-sync python scripts/direct_feed.py \\
  --model {tested_model} \\
  --judge-model {judge_model} \\
  --state {a.state} \\
  --noise {','.join(map(str, levels))} \\
  --n-controls {args0.get('n_controls')} \\
  --max-samples 4 \\
  --out results/direct/{summary['tester_model']}
```

One epoch, four concurrent samples, seed {args0.get('seed')}, one candidate per answer; the judge's output allowance is 1,500 tokens. The original run was split into the 30 planted cases at noise 500 and the other {len(rows) - 30} samples (`--exclude-ids`); one run of the command above covers the same {len(rows)} samples. API reruns can differ.

conversations.jsonl.gz holds one record per sample: the prompt, the reader's answer (reasoning omitted), the candidates, the score, and each judge call's prompt and verdict. summary.json has full-precision metrics; table.csv follows the runner's rounding. Token use is per model in each record's model_usage.

Verify the downloaded assets with SHA256SUMS. Inside the bundle, SHA256SUMS checks each included file. See provenance.json for commits, source and input hashes, log hashes and limitations.
""")
    files = sorted(p for p in inner.iterdir() if p.name != "SHA256SUMS")
    (inner / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in files))
    zpath = out / f"{a.tag}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(inner.iterdir()): z.write(p, f"{a.tag}/{p.name}")
    for name in ("summary.md", "summary.json", "rows.csv", "provenance.json"):
        shutil.copy(inner / name, out / name)
    (out / "SHA256SUMS").write_text("".join(f"{sha256(out / n)}  {n}\n" for n in (f"{a.tag}.zip", "summary.md", "summary.json", "rows.csv", "provenance.json")))
    print(text); print(f"bundle: {out}  ({zpath.stat().st_size / 1e6:.1f} MB zip)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
