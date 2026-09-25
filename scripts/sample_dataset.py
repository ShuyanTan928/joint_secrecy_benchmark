#!/usr/bin/env python3
"""Draw a seeded sample from the labelled pool: equal count per topic, round-robin over senders, whole threads.

A topic quota alone leaves a topic dominated by one sender or one month, so within a topic the draw
rotates over senders and spreads months. The manifest records the config and a digest of the chosen ids.

  python scripts/sample_dataset.py --total 2000 --with-text --whole-threads   -> data/topics/sample.jsonl, its manifest, a private id map
"""
from __future__ import annotations
import argparse, re, collections, hashlib, json, random, re
from pathlib import Path

import pyarrow.parquet as pq

PARQUET = Path("data/enron/parsed_emails.parquet")
LABELS = Path("data/topics/labels.jsonl")
NON_TOPIC = {"other", "?"}          # not IAB categories; never counted as a topic quota

SEP = re.compile(r"-{3,}\s*(original message|forwarded by)|^\s*_{5,}", re.I | re.M)
QLINE = re.compile(r"^\s*(>|from:|to:|sent:|cc:|subject:)", re.I)


def own_body(b: str) -> str:
    m = SEP.search(b)
    b = b[:m.start()] if m else b
    return "\n".join(l for l in b.splitlines() if not QLINE.match(l)).strip()


def round_robin_threads(units: list[tuple[str, list]], quota: int, rng) -> list:
    """Fill a topic's quota with whole threads: multi-email threads first while they fit, then singletons to land on the number; one thread per lead sender in rotation."""
    multi = [u for u in units if len(u[1]) > 1]
    singles = [u for u in units if len(u[1]) == 1]
    picked: list[str] = []

    for group in (multi, singles):
        by_sender: dict[str, list] = collections.defaultdict(list)
        for s, mids in group:
            by_sender[s].append(mids)
        order = sorted(by_sender)
        rng.shuffle(order)
        for s in order:
            rng.shuffle(by_sender[s])
        while len(picked) < quota:
            progressed = False
            for s in order:
                if len(picked) >= quota:
                    break
                q = by_sender[s]
                while q:
                    mids = q[-1]
                    if len(picked) + len(mids) > quota:   # would overshoot: leave it for a later pass
                        break
                    picked.extend(q.pop())
                    progressed = True
                    break
            if not progressed:
                break
    return picked


def round_robin(by_sender: dict[str, list], quota: int, cap: int | None, rng) -> list:
    """One email per sender in rotation until quota is met, so no sender can dominate a topic
    while other senders still have unused mail. `cap` hard-limits any single sender."""
    order = sorted(by_sender)                       # deterministic before shuffling
    rng.shuffle(order)
    queues = {s: by_sender[s][:] for s in order}
    for s in order:
        rng.shuffle(queues[s])
    picked, taken = [], collections.Counter()
    while len(picked) < quota:
        progressed = False
        for s in order:
            if len(picked) >= quota:
                break
            if not queues[s] or (cap is not None and taken[s] >= cap):
                continue
            picked.append(queues[s].pop())
            taken[s] += 1
            progressed = True
        if not progressed:                          # every sender exhausted or capped
            break
    return picked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=int, default=2000, help="target dataset size")
    ap.add_argument("--per-topic", type=int, default=0, help="0 = derive from total / eligible topics")
    ap.add_argument("--min-pool", type=int, default=100,
                    help="topics with fewer labelled emails than this are excluded entirely")
    ap.add_argument("--max-per-sender", type=int, default=0, help="0 = no hard cap (round-robin still applies)")
    ap.add_argument("--reserve", default="", metavar="TOPIC:N,...",
                    help="hold back N background slots in TOPIC so planted emails can take their place. "
                         "The released mailbox keeps --total emails and the same per-topic counts as one "
                         "with no plants, so counting per topic reveals nothing about where they are.")
    ap.add_argument("--jitter", type=int, default=0, metavar="N",
                    help="vary each bucket's size uniformly by +/-N so the planted emails cannot be "
                         "located by counting per topic; the dataset total stays exact")
    ap.add_argument("--whole-threads", action="store_true",
                    help="sample whole threads, never a fragment — an email is taken with the rest of "
                         "its thread's eligible messages")
    ap.add_argument("--merge-thin", action="store_true",
                    help="fold topics below --min-pool into 'other' instead of discarding them, and "
                         "fold in the classifier's own 'other'/'?' too — nothing is thrown away")
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--with-text", action="store_true", help="include subject and body in the output")
    ap.add_argument("--labels", default=str(LABELS))
    ap.add_argument("--out", default="data/topics/sample.jsonl")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    lab = {}
    for line in Path(args.labels).read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            lab[d["message_id"]] = d["topic"]

    pool = collections.Counter(t for t in lab.values() if t not in NON_TOPIC)
    eligible = sorted([t for t, n in pool.items() if n >= args.min_pool])
    if not eligible:
        raise SystemExit(f"no topic reaches --min-pool {args.min_pool}")
    thin = sorted(set(pool) - set(eligible))

    # --merge-thin: relabel topics below the floor, and the classifier's no-fit answers, to "other".
    remap: dict[str, str] = {}
    if args.merge_thin:
        for t in thin:
            remap[t] = "other"
        for mid, t in list(lab.items()):
            if t in remap or t in NON_TOPIC:
                lab[mid] = "other"
        pool = collections.Counter(lab.values())
        eligible = sorted([t for t, n in pool.items() if n >= args.min_pool or t == "other"])
        excluded: list[str] = []
    else:
        excluded = thin

    # Exact allocation: every bucket gets the floor; the remainder goes to the deepest pools.
    if args.per_topic:
        alloc = {t: args.per_topic for t in eligible}
    else:
        base, rem = divmod(args.total, len(eligible))
        alloc = {t: base for t in eligible}
        for t in sorted(eligible, key=lambda x: -pool[x])[:rem]:
            alloc[t] += 1

    # --reserve: planted emails replace background emails of the same topic, so per-topic counts stay flat.
    reserve: dict[str, int] = {}
    if args.reserve:
        for part in args.reserve.split(","):
            t, _, n = part.rpartition(":")
            t = t.strip()
            if t not in alloc:
                raise SystemExit(f"--reserve names a topic that is not a bucket: {t!r}")
            reserve[t] = int(n)
        for t, n in reserve.items():
            if n > alloc[t]:
                raise SystemExit(f"--reserve {t}:{n} exceeds that bucket's allocation ({alloc[t]})")
            alloc[t] -= n
        print(f"  reserved for planted emails: " + ", ".join(f"{t}:{n}" for t, n in sorted(reserve.items()))
              + f"   -> sampling {sum(alloc.values()):,}, released mailbox {args.total:,} once planted")

    # --jitter: vary bucket sizes within a band instead. Weaker than reserve; default off. Offsets are corrected
    # back to --total, and only inside the band and the pool.
    if args.jitter:
        lo_ok = {t: max(1, min(alloc[t] - args.jitter, pool[t])) for t in eligible}
        hi_ok = {t: min(alloc[t] + args.jitter, pool[t]) for t in eligible}
        for t in eligible:
            alloc[t] = rng.randint(lo_ok[t], max(lo_ok[t], hi_ok[t]))
        drift = args.total - sum(alloc.values())            # put the total back exactly
        order = list(eligible)
        while drift:
            rng.shuffle(order)
            moved = False
            for t in order:
                if drift == 0:
                    break
                step = 1 if drift > 0 else -1
                if lo_ok[t] <= alloc[t] + step <= hi_ok[t]:
                    alloc[t] += step
                    drift -= step
                    moved = True
            if not moved:                                   # band is saturated; accept the shortfall
                break
    print(f"buckets: {len(eligible)}   target {sum(alloc.values()):,}   "
          f"quota/bucket: {min(alloc.values())}-{max(alloc.values())}"
          + (f"   (jitter +/-{args.jitter})" if args.jitter else ""))
    if args.merge_thin and thin:
        print(f"  merged into 'other' (pool < {args.min_pool}): "
              + ", ".join(f"{t}({pool[t] if t in pool else 0})" for t in thin)
              + f"  -> 'other' pool now {pool['other']:,}")
    if excluded:
        print(f"excluded (pool < {args.min_pool}): " + ", ".join(f"{t}({pool[t]})" for t in excluded))

    # gather candidates, grouped topic -> sender
    elig_set = set(eligible)
    cand: dict[str, dict[str, list]] = collections.defaultdict(lambda: collections.defaultdict(list))
    meta: dict[str, dict] = {}
    cols = ["message_id", "from_addr", "date", "subject", "body", "word_count", "in_reply_to"]
    for b in pq.ParquetFile(PARQUET).iter_batches(batch_size=20000, columns=cols):
        d = b.to_pydict()
        for mid, frm, dt, subj, body, wc, irt in zip(*(d[c] for c in cols)):
            t = lab.get(mid)
            if t is None or t not in elig_set:
                continue
            s = (frm or "?").lower()
            cand[t][s].append(mid)
            meta[mid] = {"from": s, "date": str(dt)[:10], "subject": subj or "",
                         "word_count": wc or 0, "body": body or "", "in_reply_to": irt or None}

    cap = args.max_per_sender or None
    m2t, sub_threads = {}, {}
    if args.whole_threads:
        m2t_path = Path("data/topics/mid2tid.json")
        if not m2t_path.exists():
            # No thread map: thread the pool by normalized subject, RE:/FW: stripped. The released map came from the
            # parent corpus's threading by subject and participants.
            import hashlib
            keys = {}
            for b in pq.ParquetFile(PARQUET).iter_batches(batch_size=50000, columns=["message_id", "normalized_subject"]):
                d = b.to_pydict()
                for mid, ns in zip(d["message_id"], d["normalized_subject"]):
                    if mid in lab:
                        k = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", (ns or "").lower()).strip() or mid
                        keys[mid] = "t_" + hashlib.sha1(k.encode()).hexdigest()[:16]
            m2t_path.write_text(json.dumps(keys))
            print(f"threaded {len(keys):,} labelled emails by subject -> {m2t_path}")
        m2t = json.loads(m2t_path.read_text())
        # A thread spanning two topics is split at the topic boundary; each part is its own unit.
        tmem: dict[str, list] = collections.defaultdict(list)
        for mid in lab:
            tmem[m2t.get(mid, mid)].append(mid)
        n_split = 0
        for tid, mids in tmem.items():
            by_topic: dict[str, list] = collections.defaultdict(list)
            for m in mids:
                by_topic[lab[m]].append(m)
            if len(by_topic) > 1:
                n_split += 1
            for t, part in by_topic.items():
                sub_threads.setdefault(t, []).append((tid, part))
        print(f"  whole-thread mode: {sum(len(v) for v in sub_threads.values()):,} sub-threads "
              f"({n_split:,} mixed-topic threads split at the topic boundary)")

    rows, short = [], []
    for t in eligible:
        q = alloc[t]
        if args.whole_threads:
            sender_of = {mid: s_ for s_, mids in cand[t].items() for mid in mids}
            units = [(min(sender_of.get(m, "?") for m in part), part)
                     for _tid, part in sub_threads.get(t, [])]
            got = round_robin_threads(units, q, rng)
        else:
            got = round_robin(cand[t], q, cap, rng)
        if len(got) < q:
            short.append((t, len(got), q))
        for mid in got:
            rows.append({"mid": mid, "topic": t})

    # Opaque ids: a source message id looks up the public dump, so the release carries e_NNNNNN and t_NNNN in
    # seeded-shuffled order. The source map goes to a private file.
    groups: dict[tuple, list] = collections.defaultdict(list)
    for r in rows:
        groups[(m2t.get(r["mid"], r["mid"]), r["topic"])].append(r["mid"])
    keys = sorted(groups)
    rng.shuffle(keys)
    email_id: dict[str, str] = {}
    thread_id: dict[tuple, str] = {}
    out_rows, idmap = [], {}
    n_e = 0
    for i, k in enumerate(keys, 1):
        tid = f"t_{i:04d}"
        thread_id[k] = tid
        members = sorted(groups[k], key=lambda m: (meta[m]["date"], m))    # chronological in-thread
        for m in members:
            n_e += 1
            email_id[m] = f"e_{n_e:06d}"
    for k in keys:
        members = sorted(groups[k], key=lambda m: (meta[m]["date"], m))
        for pos, m in enumerate(members, 1):
            me = meta[m]
            # in_reply_to is empty on every corpus message, so thread structure is chronological position only.
            r = {"email_id": email_id[m], "thread_id": thread_id[k], "thread_pos": pos,
                 "thread_len": len(members), "topic": k[1], "from": me["from"], "date": me["date"], "word_count": me["word_count"]}
            if args.with_text:
                r["subject"] = me["subject"]
                r["body"] = me["body"]
                r["own_body"] = own_body(me["body"])
            out_rows.append(r)
            idmap[email_id[m]] = {"message_id": m, "source_thread_id": k[0], "thread_id": thread_id[k]}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n")
    private = Path(str(out) + ".idmap.json")           # gitignored, never ships
    private.write_text(json.dumps(idmap, indent=0) + "\n")

    ids_digest = hashlib.sha256("".join(sorted(idmap[e]["message_id"] for e in idmap)).encode()).hexdigest()[:16]
    per_topic = collections.Counter(r["topic"] for r in out_rows)
    senders = collections.Counter(r["from"] for r in out_rows)
    months = collections.Counter(r["date"][:7] for r in out_rows)
    tlen = collections.Counter(r["thread_len"] for r in out_rows if r["thread_pos"] == 1)
    manifest = {
        "n": len(out_rows), "threads": len(keys), "thread_len_hist": dict(sorted(tlen.items())),
        "topics": len(eligible), "alloc": dict(sorted(alloc.items())),
        "whole_threads": args.whole_threads,
        "merge_thin": args.merge_thin, "merged_into_other": thin if args.merge_thin else [],
        "jitter": args.jitter, "reserve": reserve,
        "released_total_once_planted": args.total,
        "min_pool": args.min_pool, "max_per_sender": args.max_per_sender, "seed": args.seed,
        "labels_source": args.labels, "source_ids_sha256_16": ids_digest,
        "per_topic": dict(sorted(per_topic.items())),
        "excluded_topics": {t: pool[t] for t in excluded},
        "distinct_senders": len(senders), "distinct_months": len(months),
        "top_sender_share": round(100 * senders.most_common(1)[0][1] / len(out_rows), 2) if out_rows else 0,
        "top_month_share": round(100 * months.most_common(1)[0][1] / len(out_rows), 2) if out_rows else 0,
    }
    Path(str(out) + ".manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")

    print(f"\nWROTE {out}  ({len(out_rows):,} emails in {len(keys):,} threads)")
    print(f"  manifest -> {out}.manifest.json      id map (PRIVATE, gitignored) -> {private}")
    print(f"  distinct senders {len(senders):,}   top sender {manifest['top_sender_share']}%   "
          f"months {len(months)}   top month {manifest['top_month_share']}%")
    if short:
        print("  under quota: " + ", ".join(f"{t}({n}/{q})" for t, n, q in short))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
