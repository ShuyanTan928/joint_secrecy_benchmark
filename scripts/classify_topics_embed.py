#!/usr/bin/env python3
"""A second topic classifier, by embedding similarity, independent of the generation one, so agreement
between the two says something about the labels. Each tier-1 topic is represented by its tier-2
children from the taxonomy; a best score below --floor is "other".

  CUDA_VISIBLE_DEVICES=2 python scripts/classify_topics_embed.py
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

import pyarrow.parquet as pq

LABELS = Path("data/topics/labels.jsonl")          # the LLM pass, defines the email set to score
DESC = Path("prompts/iab_tier1_desc.json")

SEP = re.compile(r"-{3,}\s*(original message|forwarded by)|^\s*_{5,}", re.I | re.M)
QLINE = re.compile(r"^\s*(>|from:|to:|sent:|cc:|subject:)", re.I)
REPLY = re.compile(r"^\s*(re|fw|fwd)\s*:", re.I)


def own_body(b: str) -> str:
    m = SEP.search(b)
    b = b[:m.start()] if m else b
    return "\n".join(l for l in b.splitlines() if not QLINE.match(l)).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="BAAI/bge-large-en-v1.5")
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--floor", type=float, default=0.0,
                    help="min cosine to accept a topic; below it the email is called 'other'")
    ap.add_argument("--out", default="data/topics/labels_embed.jsonl")
    args = ap.parse_args()

    want = {json.loads(l)["message_id"] for l in LABELS.read_text().splitlines() if l.strip()}
    print(f"scoring the same {len(want):,} emails the LLM pass labelled")

    ids, texts = [], []
    for b in pq.ParquetFile("data/enron/parsed_emails.parquet").iter_batches(
            batch_size=20000, columns=["message_id", "subject", "body"]):
        d = b.to_pydict()
        for mid, s, body in zip(d["message_id"], d["subject"], d["body"]):
            if mid not in want:
                continue
            head = "" if REPLY.match(s or "") else (s or "").strip()
            ob = own_body(body or "")
            ids.append(mid)
            texts.append(f"{head}\n{ob}".strip() if head else ob)
    print(f"gathered {len(ids):,} texts")

    from sentence_transformers import SentenceTransformer
    import torch

    desc = json.loads(DESC.read_text())
    topics = list(desc)
    m = SentenceTransformer(args.model, device="cuda")
    # bge wants a query instruction on the *query* side; the emails are the queries here.
    T = m.encode([desc[t] for t in topics], normalize_embeddings=True, convert_to_tensor=True)
    E = m.encode(texts, batch_size=args.batch, normalize_embeddings=True,
                 convert_to_tensor=True, show_progress_bar=True)
    sims = E @ T.T                                        # cosine, both sides unit-normalised
    best = sims.argmax(dim=1)
    top = sims.max(dim=1).values

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for mid, bi, sc in zip(ids, best.tolist(), top.tolist()):
            lab = topics[bi] if sc >= args.floor else "other"
            f.write(json.dumps({"message_id": mid, "topic": lab, "score": round(sc, 4)}) + "\n")
    print(f"WROTE {out}  ({len(ids):,} labels)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
