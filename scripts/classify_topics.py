#!/usr/bin/env python3
"""Label every eligible Enron email with one IAB tier-1 topic.

Eligibility is decided on the email's own text: quoted history, forwarded blocks and header lines are
cut, and the subject counts only when it is not a reply. Bulk, automated and non-prose mail and
near-duplicates are dropped. Length is bounded to 30-500 tokens of one fixed tokenizer (Qwen3-32B's),
whatever model classifies. One call per eligible email; the pool is 133,252.

  python scripts/classify_topics.py --limit 300                          -> data/topics/labels.jsonl
  python scripts/classify_topics.py --engine vllm --preset qwen3-32b     # the whole pool
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

sys.path.insert(0, ".")
import pyarrow.parquet as pq                                                    # noqa: E402

PARQUET = Path("data/enron/parsed_emails.parquet")
PROMPT = Path("prompts/topic_classify.md")
TOPICS_FILE = Path("prompts/iab_tier1.txt")
DESC_FILE = Path("prompts/iab_tier1_desc.json")     # "name: what it covers" per tier-1 topic, the taxonomy's own tier-2 list

# IAB Content Taxonomy tier 1, one per line, plus "other". The taxonomy's metadata dimensions (Content
# Channel, Language, Media Format, Source, Type, Brand Suitability, Sensitive Topics) are not topics.
TOPICS = [l.strip() for l in TOPICS_FILE.read_text().splitlines() if l.strip()]
_CANON = {re.sub(r"\s*(&|and)\s*", " ", t).strip(): t for t in TOPICS}


def canon(s: str) -> str:
    """The label inside the model's answer: earliest match in TOPICS, longest on a tie; '?' if none."""
    k = re.sub(r"\s*(&|and)\s*", " ", (s or "").lower())
    k = re.sub(r"[^a-z ]+", " ", k)
    k = re.sub(r"\s+", " ", k)
    best = None
    for norm, label in _CANON.items():
        i = k.find(norm)
        if i >= 0 and (best is None or (i, -len(norm)) < best[0]):
            best = ((i, -len(norm)), label)
    return best[1] if best else "?"


SEP = re.compile(r"-{3,}\s*(original message|forwarded by)|^\s*_{5,}", re.I | re.M)
QLINE = re.compile(r"^\s*(>|from:|to:|sent:|cc:|subject:)", re.I)
REPLY = re.compile(r"^\s*(re|fw|fwd)\s*:", re.I)
BULK = re.compile(r"<html|<meta |<table|unsubscribe|click here to|mailing list|"
                  r"privacy policy|m0\.net|akamai|to remove yourself", re.I)
AUTO = re.compile(r"synchronizing folder|out of the office|undeliverable|delivery status|"
                  r"automatic reply|this is an automated", re.I)


def own_body(b: str) -> str:
    """The text this sender actually wrote: quoted history and header lines removed."""
    m = SEP.search(b)
    b = b[:m.start()] if m else b
    return "\n".join(l for l in b.splitlines() if not QLINE.match(l)).strip()


def eligible(subject: str, body: str):
    """(text_to_classify) or None. Deterministic gates only, no model involved."""
    if BULK.search(body) or AUTO.search(body):
        return None
    alpha = sum(c.isalpha() or c.isspace() for c in body)
    if alpha / max(1, len(body)) < 0.75:                    # pasted tables, encoding garbage
        return None
    ob = own_body(body)
    if not ob:
        return None
    head = "" if REPLY.match(subject or "") else (subject or "").strip()
    return f"{head}\n{ob}".strip() if head else ob


def main() -> int:
    from src.models.engine_factory import add_engine_args, engine_from_args, write_model_record
    ap = add_engine_args(argparse.ArgumentParser())
    ap.add_argument("--min-tokens", type=int, default=30)
    ap.add_argument("--max-tokens-in", type=int, default=500)
    ap.add_argument("--limit", type=int, default=0, help="stop after N eligible emails (smoke test)")
    ap.add_argument("--out", default="data/topics/labels.jsonl")
    ap.add_argument("--allow-big-run", action="store_true", help="let an API model classify more than 5,000 emails (the full pool is about $800 on Opus 5.5)")
    ap.add_argument("--free-text", action="store_true",
                    help="disable constrained decoding; let the model answer freely and parse the label out")
    args = ap.parse_args()

    # One fixed tokenizer for the length band, whatever model classifies.
    BAND_TOKENIZER = "Qwen/Qwen3-32B"
    try:
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        _tk = Tokenizer.from_file(hf_hub_download(BAND_TOKENIZER, "tokenizer.json"))
        def n_tokens(batch: list[str]) -> list[int]:
            return [len(e.ids) for e in _tk.encode_batch(batch, add_special_tokens=False)]
    except Exception as e:                                   # no hub access: the corpus's measured ratio stands in
        print(f"tokenizer unavailable ({str(e)[:60]}); using 1.55 tokens per word")
        def n_tokens(batch: list[str]) -> list[int]:
            return [int(len(t.split()) * 1.55) for t in batch]

    # ---- gather + token-bound (deterministic, no GPU yet)
    seen: set[bytes] = set()
    ids: list[str] = []
    texts: list[str] = []
    raw = dropped = 0
    for batch in pq.ParquetFile(PARQUET).iter_batches(
            batch_size=20000, columns=["message_id", "subject", "body"]):
        d = batch.to_pydict()
        cand_id, cand_tx = [], []
        for mid, s, b in zip(d["message_id"], d["subject"], d["body"]):
            raw += 1
            t = eligible(s or "", b or "")
            if t is None:
                dropped += 1
                continue
            sig = hashlib.md5(re.sub(r"\s+", " ", t).lower()[:240].encode()).digest()
            if sig in seen:                                  # the corpus is triplicated
                dropped += 1
                continue
            seen.add(sig)
            cand_id.append(mid)
            cand_tx.append(t)
        if cand_tx:                                          # token bound, batched for speed
            for mid, t, n in zip(cand_id, cand_tx, n_tokens(cand_tx)):
                if args.min_tokens <= n <= args.max_tokens_in:
                    ids.append(mid)
                    texts.append(t)
                else:
                    dropped += 1
        if args.limit and len(ids) >= args.limit:
            ids, texts = ids[:args.limit], texts[:args.limit]
            break
    print(f"raw {raw:,}  dropped {dropped:,}  -> to classify: {len(ids):,}")

    # ---- classify: one email per prompt (vLLM batches internally; the API engine calls one by one)
    est = len(ids) * 1.6e-3 * 4 + len(ids) * 1e-5 * 20                # ~1.6k tokens in and ~10 out per call, at Opus 5.5's $4 / $20 per million
    print(f"calls to make: {len(ids):,} on {args.engine} {args.preset}" + (f"; about ${est:,.0f} on Opus 5.5" if args.engine == "api" else ""))
    if args.engine == "api" and len(ids) > 5000 and not args.allow_big_run:
        print("more than 5,000 API calls: pass --limit for a smaller pool, --engine vllm for a local model, or --allow-big-run"); return 2
    shell = PROMPT.read_text()
    desc = json.loads(DESC_FILE.read_text())
    topics = "\n".join(desc.get(t, t) for t in TOPICS)    # each line: the name, then what it covers; the answer is the name alone
    prompts = [shell.replace("<<TOPICS>>", topics).replace("<<EMAIL>>", t) for t in texts]

    if args.engine == "vllm": args.max_model_len = min(args.max_model_len, 2048)
    eng = engine_from_args(args)
    # Constrained decoding (vLLM only) pins the answer to one of TOPICS.
    outs = eng.generate(prompts, max_tokens=24, temperature=0.0,
                        choices=None if (args.free_text or args.engine != "vllm") else TOPICS)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with out.open("w") as f:
        for mid, o in zip(ids, outs):
            lab = canon(o)
            counts[lab] = counts.get(lab, 0) + 1
            if lab == "?":                      # keep the raw text so misses are diagnosable
                f.write(json.dumps({"message_id": mid, "topic": lab, "raw": o[:200]}) + "\n")
                continue
            f.write(json.dumps({"message_id": mid, "topic": lab}) + "\n")
    write_model_record(out, eng, args)
    print(f"\nWROTE {out}  ({len(ids):,} labels)\n")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {v:>7,}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
