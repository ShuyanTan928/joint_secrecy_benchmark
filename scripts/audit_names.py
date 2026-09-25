#!/usr/bin/env python3
"""Audit the anonymised sample: a model lists every person name it sees in each email; code keeps the
spans that occur in the email and are not made of pseudonym tokens. What is left is the leak list.

  python scripts/audit_names.py                                   -> data/topics/name_audit.jsonl
  python scripts/audit_names.py --engine vllm --preset qwen3-32b
"""
from __future__ import annotations
import argparse, collections, json, re, sys
from pathlib import Path

sys.path.insert(0, ".")

SAMPLE = Path("data/topics/sample_anon.jsonl")
PROMPT = Path("prompts/name_audit.md")

# Lines the model writes around the list.
NOISE = re.compile(r"^\s*(none|no names?|names?:|here (is|are)|the (names?|person)|\d+[.)]?\s*$)", re.I)
STRIP = re.compile(r"^[\s\-*•\d.)\]]+|[\s,.;:]+$")

# Tokens that carry no identity; single letters are middle initials.
HONORIFIC = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "rev", "sir", "madam", "jr",
             "sr", "ii", "iii", "iv", "the", "senator", "judge"}


def load_fakes(map_path: Path) -> set[str]:
    """Every token the anonymiser put into the text: pseudonyms, companies, domain bases. A span made only of these is not a leak."""
    m = json.loads(map_path.read_text())
    out: set[str] = set()
    for v in m.get("people", {}).values():
        out |= {t.lower() for t in str(v.get("fake", "")).split()}
    # Bare-first-name pseudonyms sit in their own section of the map.
    for v in m.get("solo", {}).values():
        out |= {t.lower() for t in str(v).split()}
    # Addresses that resolved to nobody still have a fake local part from the pool.
    for v in m.get("unknown_addrs", {}).values():
        out |= set(re.findall(r"[a-z]+", str(v).lower()))
    for v in m.get("companies", {}).values():
        out |= {t.lower() for t in str(v).split()}
    for v in m.get("domains", {}).values():
        out.add(str(v).lower().split(".")[0])
    # Fake domain bases carry a digit suffix; register the letters-only form too.
    out |= {re.sub(r"\d+", "", t) for t in out}
    return {t for t in out if t}


def classify(name: str, fakes: set[str]) -> str:
    """'clean', 'partial' or 'leak' for one span. Partial: one half is a pseudonym, the other a surviving real name."""
    toks = [w for w in re.findall(r"[A-Za-z']+", name.lower())
            if len(w) > 1 and w not in HONORIFIC]
    if not toks:
        return "clean"
    n = sum(w in fakes for w in toks)
    return "clean" if n == len(toks) else ("partial" if n else "leak")


def parse(raw: str) -> list[str]:
    """Model output -> candidate name strings. One per line, list furniture removed."""
    names = []
    for line in (raw or "").splitlines():
        line = STRIP.sub("", line).strip()
        if not line or NOISE.match(line) or len(line) > 60:
            continue
        if not re.search(r"[A-Za-z]{2}", line):
            continue
        names.append(line)
    return names


def main() -> int:
    from src.models.engine_factory import add_engine_args, engine_from_args, write_model_record
    ap = add_engine_args(argparse.ArgumentParser())
    ap.add_argument("--in", dest="inp", default=str(SAMPLE))
    ap.add_argument("--map", default="", help="defaults to <in>.map.json")
    ap.add_argument("--out", default="data/topics/name_audit.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--window", type=int, default=8000,
                    help="chars per prompt; longer emails are cut into overlapping windows")
    args = ap.parse_args()

    inp = Path(args.inp)
    mp = Path(args.map) if args.map else Path(str(inp) + ".map.json")
    fakes = load_fakes(mp)
    rows = [json.loads(l) for l in inp.open()]
    if args.limit:
        rows = rows[:args.limit]
    print(f"{len(rows):,} emails   {len(fakes):,} pseudonym tokens")

    # The full body, quoted history included. Long emails are cut into overlapping windows, not truncated.
    shell = PROMPT.read_text()
    win, overlap = args.window, 400
    texts, owner = [], []                       # owner[i] = index of the email window i came from
    for i, r in enumerate(rows):
        t = f"{r.get('subject') or ''}\n{r.get('body') or ''}".strip()
        for s in range(0, max(1, len(t)), win - overlap):
            texts.append(t[s:s + win])
            owner.append(i)
            if s + win >= len(t):
                break
    if len(texts) > len(rows):
        print(f"  {len(texts) - len(rows):,} extra windows from long emails -> {len(texts):,} prompts")
    prompts = [shell.replace("<<EMAIL>>", t) for t in texts]

    eng = engine_from_args(args)
    outs = eng.generate(prompts, max_tokens=256, temperature=0.0)

    docs = {"leak": collections.Counter(), "partial": collections.Counter()}
    hits = {"leak": collections.Counter(), "partial": collections.Counter()}
    flagged: set[str] = set()
    halluc = known = 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    per_email: dict[int, list[tuple[str, str]]] = collections.defaultdict(list)
    for i, t, o in zip(owner, texts, outs):
        low = t.lower()
        for name in parse(o):
            if name.lower() not in low:                # guard 1: must occur in the window
                halluc += 1
                continue
            kind = classify(name, fakes)               # guard 2: already a pseudonym?
            if kind == "clean":
                known += 1
                continue
            per_email[i].append((kind, name))

    with out.open("w") as f:
        for i, r in enumerate(rows):
            found = per_email.get(i, [])
            low = f"{r.get('subject') or ''}\n{r.get('body') or ''}".lower()
            if found:
                flagged.add(r["email_id"])
                for kind, name in {(k, n.lower()) for k, n in found}:
                    docs[kind][name] += 1
                for kind, name in found:
                    hits[kind][name.lower()] += low.count(name.lower())
                f.write(json.dumps({"email_id": r["email_id"], "from": r.get("from", ""),
                                    "found": [{"kind": k, "name": n} for k, n in found]}) + "\n")

    write_model_record(out, eng, args)
    print(f"\nWROTE {out}")
    print(f"  emails with something surviving : {len(flagged):,} / {len(rows):,}")
    print(f"  dropped, fully a pseudonym      : {known:,}")
    print(f"  dropped, not in the email       : {halluc:,}")
    for kind, label in (("leak", "UNTOUCHED  (no half replaced)"),
                        ("partial", "PARTIAL    (one half replaced, one survived)")):
        print(f"\n  {label}   {len(docs[kind]):,} distinct, "
              f"{sum(hits[kind].values()):,} occurrences")
        for name, d in docs[kind].most_common(30):
            print(f"    {hits[kind][name]:>5} occ  in {d:>4} emails   {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
