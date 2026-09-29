#!/usr/bin/env python3
"""Replace one thread of the released mailbox: a fresh thread of the same topic and length drawn from the corpus
the way the sampler draws, anonymised by the release's own anonymiser held to the release (the firm's pseudonym, pseudonyms
and domains from the release's reserve of unused names), audited, and swapped in with the manifest updated. For a thread
the cleaning found to hold a real secret. The release's private map is not needed and is not touched.

  python scripts/replace_thread.py --remove t_0598 --why "cited by gpt-6-sol, claude-opus-5.5, gemini-3.7-flash" --dry   # choose only
  python scripts/replace_thread.py --remove t_0598 --why "..." --engine api --preset openai/gpt-6-sol                 # two model passes, then apply
"""
from __future__ import annotations

import argparse, collections, hashlib, json, random, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, "."); sys.path.insert(0, "scripts")
import pyarrow.parquet as pq   # noqa: E402
from sample_dataset import own_body   # noqa: E402

RELEASE = Path("data/release/background_2000.jsonl"); MANIFEST = Path("data/release/background_2000.manifest.json")
RESERVE = Path("benchmark_pool/fresh_names.json"); QUIET = Path("benchmark_pool/quiet_people.json")
WORK = Path("logs/replace")


def signature(body: str) -> str:
    """A body with names, addresses and numbers removed, so an anonymised copy still matches its source."""
    t = re.sub(r"\S+@\S+|\d+|[A-Z][a-z]+", " ", body or "")
    return " ".join(t.lower().split())[:240]


def choose(topic: str, length: int, release: list[dict], seed: int) -> list[dict]:
    lab = {}
    for l in Path("data/topics/labels.jsonl").open():
        r = json.loads(l); lab[r["message_id"]] = r["topic"]
    m2t = json.load(Path("data/topics/mid2tid.json").open())
    cols = ["message_id", "from_addr", "date", "subject", "body", "word_count"]
    meta = {}
    for b in pq.ParquetFile("data/enron/parsed_emails.parquet").iter_batches(batch_size=20000, columns=cols):
        d = b.to_pydict()
        for mid, frm, dt, subj, body, wc in zip(*(d[c] for c in cols)):
            if lab.get(mid) == topic:
                meta[mid] = {"from": (frm or "?").lower(), "date": str(dt)[:10], "subject": subj or "", "body": body or "", "word_count": wc or 0}
    groups = collections.defaultdict(list)
    for mid in meta: groups[m2t.get(mid, mid)].append(mid)
    have = {signature(r["body"]) for r in release}
    keys = sorted(k for k, ms in groups.items() if len(ms) == length and all(signature(meta[m]["body"]) not in have for m in ms)
                  and all(meta[m]["word_count"] >= 30 for m in ms) and len({meta[m]["from"] for m in ms}) > 1)
    print(f"{topic}: {len(groups):,} topic-threads in the corpus, {len(keys):,} of length {length} with two writers, not in the release")
    k = random.Random(seed).choice(keys)
    ms = sorted(groups[k], key=lambda m: (meta[m]["date"], m))
    return [{"message_id": m, **meta[m]} for m in ms]


def main() -> int:
    from src.models.engine_factory import add_engine_args
    ap = add_engine_args(argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter), preset="openai/gpt-6-sol")
    ap.add_argument("--remove", required=True, help="the thread id to replace")
    ap.add_argument("--why", required=True, help="the reason, recorded in the manifest")
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--dry", action="store_true", help="choose and print the replacement, no model, no change")
    ap.add_argument("--reuse-extraction", action="store_true", help="use logs/replace/people_extract.jsonl from an earlier run")
    a = ap.parse_args()
    release = [json.loads(l) for l in RELEASE.open() if l.strip()]
    old = sorted([r for r in release if r["thread_id"] == a.remove], key=lambda r: r["thread_pos"])
    if not old: raise SystemExit(f"{a.remove} is not in the release")
    topic, length = old[0]["topic"], len(old)
    new = choose(topic, length, release, a.seed)
    for m in new: print(f"  chosen: {m['date']} {m['from']} | {m['subject']} | {m['word_count']} words")
    if a.dry: return 0

    WORK.mkdir(parents=True, exist_ok=True)
    n_e = max(int(r["email_id"].split("_")[1]) for r in release); n_t = max(int(r["thread_id"].split("_")[1]) for r in release)
    rows = [{"email_id": f"e_{n_e + i:06d}", "thread_id": f"t_{n_t + 1:04d}", "thread_pos": i, "thread_len": length, "topic": topic, "from": m["from"],
             "date": m["date"], "word_count": m["word_count"], "subject": m["subject"], "body": m["body"], "own_body": own_body(m["body"])}
            for i, m in enumerate(new, 1)]
    src = WORK / "sample.jsonl"; src.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    model = ["--engine", a.engine, "--preset", a.preset]
    if not (a.reuse_extraction and (WORK / "people_extract.jsonl").exists()):
        subprocess.run([sys.executable, "scripts/extract_people.py", "--in", str(src), "--out", str(WORK / "people_extract.jsonl"), *model], check=True)
    people = {json.loads(l)["email_id"]: json.loads(l)["people"] for l in (WORK / "people_extract.jsonl").open()}

    # the release's own anonymiser, held to the release: its firm, pseudonyms and domains from its reserve of unused names
    reserve = json.loads(RESERVE.read_text()); firm_domain = json.loads(QUIET.read_text())["firm_domain"]; firm = firm_domain.split(".")[0].capitalize()
    out = WORK / "sample_anon.jsonl"
    subprocess.run([sys.executable, "scripts/anonymize_llm.py", "--extract", str(WORK / "people_extract.jsonl"), "--in", str(src), "--out", str(out), "--seed", str(a.seed),
                    "--firm", firm, "--firm-domain", firm_domain, "--name-reserve", str(RESERVE), "--no-reserve-write", "--stats-from", str(RELEASE)], check=True)
    anon = [json.loads(l) for l in out.open() if l.strip()]
    mp = json.loads((WORK / "sample_anon.jsonl.map.json").read_text())
    subprocess.run([sys.executable, "scripts/audit_names.py", "--in", str(out), "--map", str(WORK / "sample_anon.jsonl.map.json"), "--out", str(WORK / "name_audit.jsonl"), *model], check=True)
    audit = [json.loads(l) for l in (WORK / "name_audit.jsonl").open() if l.strip()]
    print("\naudit:", "nothing flagged" if not audit else json.dumps(audit, ensure_ascii=False)[:800])
    for r in anon: print(f"\n[{r['email_id']}] {r['date']} {r['from']} | {r['subject']}\n" + re.sub(r"\s+", " ", r["body"])[:600])

    # apply: the release, its manifest, the removed thread beside the release, the reserve
    kept = [r for r in release if r["thread_id"] != a.remove] + anon
    RELEASE.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept))
    m = json.loads(MANIFEST.read_text()); m["n_emails"] = len(kept); m["n_threads"] = len({r["thread_id"] for r in kept})
    m["sha256"] = hashlib.sha256(RELEASE.read_bytes()).hexdigest()
    m.setdefault("replacements", []).append({"removed": a.remove, "why": a.why, "added": rows[0]["thread_id"], "topic": topic, "messages": length,
                                             "source_message_ids": [x["message_id"] for x in new],
                                             "anonymised": f"locally with scripts/replace_thread.py: the firm as {firm}, pseudonyms and domains from the release's reserve; people not linked to the private map",
                                             "people_pass": f"{a.engine} {a.preset}", "audit_flags": len(audit)})
    MANIFEST.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    rem = Path("results/clean_release/removed.jsonl"); rem.parent.mkdir(parents=True, exist_ok=True)
    with rem.open("a") as f:
        for r in old: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    text = " ".join(r["subject"] + " " + r["body"] + " " + r["from"] for r in anon)
    tokens = {t.lower() for t in re.findall(r"[A-Za-z]+", text)}                      # every word the new emails put into the mailbox
    used = sorted(n for n in reserve["names"] if any(t.lower() in tokens for t in n.split()))   # reserve names that now share a token with the mailbox
    reserve["names"] = [n for n in reserve["names"] if n not in set(used)]; reserve["counts"]["names"] = len(reserve["names"])
    reserve["corpus_domains"] = sorted(set(reserve["corpus_domains"]) | {r["from"].split("@")[-1] for r in anon} | set(mp["domains"].values()))
    reserve.setdefault("replacement_reserve_used", []).extend(used); RESERVE.write_text(json.dumps(reserve, indent=1, ensure_ascii=False) + "\n")
    print(f"\nrelease: {m['n_emails']} emails in {m['n_threads']} threads; removed {a.remove} -> results/clean_release/removed.jsonl; added {rows[0]['thread_id']}; reserve now {len(reserve['names'])} names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
