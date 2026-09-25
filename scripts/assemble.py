#!/usr/bin/env python3
"""Place finished chains into the background mailbox and write the answer key.

Threads are placed whole, by the date of their first message, among the release's threads. Planted
rows take the release's schema with fresh ids and carry no mark. The key lists per chain the secret,
kind, pattern, stake, cast, and the planted email ids by clue.

  python scripts/assemble.py --state logs/generate.json     -> data/benchmark/mailbox.jsonl, answer_key.json
"""
import argparse
import json
import re
from pathlib import Path

RELEASE = Path("data/release/background_2000.jsonl")


def addr(s: str) -> str:
    m = re.search(r"[\w.+-]+@[\w.-]+", s or ""); return m.group(0).lower() if m else (s or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="logs/generate.json")
    ap.add_argument("--release", default=str(RELEASE))
    ap.add_argument("--outdir", default="data/benchmark")
    ap.add_argument("--keep-flagged", action="store_true", help="also place chains whose code checks flagged something")
    a = ap.parse_args()
    st = json.loads(Path(a.state).read_text())
    rows = [json.loads(l) for l in Path(a.release).open() if l.strip()]
    threads = {}
    for r in rows: threads.setdefault(r["thread_id"], []).append(r)
    placed = [sorted(ms, key=lambda m: (m["date"], m["thread_pos"])) for ms in threads.values()]

    key, n_chain = [], 0
    for r in st.get("chains", []):
        if r.get("error") or not r.get("emails"): continue
        if not a.keep_flagged and (r.get("isolation") or r.get("holds_leak") or r.get("placeholders_left")): continue
        n_chain += 1; ids = {}
        for c, carries in zip(r["emails"]["clues"], r["plan"]):
            ms = c.get("messages") or []; tid = f"p_{n_chain:03d}_{c['i']}"
            th = []
            for j, m in enumerate(ms, 1):
                eid = f"{tid}_{j}"; ids.setdefault(c["i"], []).append(eid)
                th.append({"email_id": eid, "thread_id": tid, "thread_pos": j, "thread_len": len(ms), "topic": r.get("topic"),
                           "from": addr(m.get("from", "")), "date": m.get("date", ""), "subject": m.get("subject", ""), "body": m.get("body", "")})
            placed.append(th)
        key.append({"chain": n_chain, "topic": r.get("topic"), "kind": r.get("kind"), "pattern": r.get("pattern"), "secret": r.get("secret"),
                    "stake": r.get("stake"), "n": r.get("n"), "planted": ids, "names": {k: v["name"] for k, v in (r.get("names") or {}).items()}})
    placed.sort(key=lambda th: (th[0]["date"], th[0]["thread_id"]))     # whole threads, by the first message's date
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    with (out / "mailbox.jsonl").open("w") as f:
        for th in placed:
            for m in th: f.write(json.dumps(m, ensure_ascii=False) + "\n")
    (out / "answer_key.json").write_text(json.dumps({"state": a.state, "release": a.release, "chains": key}, indent=1, ensure_ascii=False))
    n_pl = sum(len(v) for k in key for v in k["planted"].values())
    print(f"WROTE {out/'mailbox.jsonl'}: {sum(len(t) for t in placed):,} emails in {len(placed):,} threads, {n_pl} planted from {len(key)} chains; key {out/'answer_key.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
