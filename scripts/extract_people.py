#!/usr/bin/env python3
"""Anonymisation, pass 1: a model lists the people in each sampled email, every form of their name and
their address. It tags and links per email; it never invents a replacement and never sees the map.
The output is written once, so anonymize_llm.py is a pure function of this file and the seed.

  python scripts/extract_people.py --limit 60                        -> data/topics/people_extract.jsonl
  python scripts/extract_people.py --engine vllm --preset qwen3-32b
"""
from __future__ import annotations
import argparse, collections, json, re, sys
from pathlib import Path

sys.path.insert(0, ".")

SAMPLE = Path("data/topics/sample.jsonl")
PROMPT = Path("prompts/people_extract.md")

ADDR = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
STRIP = re.compile(r"^[\s\-*•\d.)\]]+|[\s.;:]+$")
NOISE = re.compile(r"^\s*(none|no (people|names?)|people:|here (is|are)|unknown)\s*$", re.I)
# Honorifics: kept with a name, refused alone.
ROLE = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "rev", "sir", "madam", "jr", "sr",
        "the", "all", "everyone", "sender", "recipient", "customer", "support", "service",
        "services", "manager", "director", "president", "admin", "administrator", "staff",
        "chairperson", "chairman", "chair", "secretary", "treasurer", "coordinator", "analyst",
        "associate", "assistant", "specialist", "engineer", "counsel", "attorney", "trader",
        "ceo", "cfo", "coo", "vp", "unknown", "none"}
# Any of these in a form marks an organisation, not a person.
ORG_WORD = {"team", "group", "committee", "department", "dept", "inc", "llc", "ltd", "corp",
            "corporation", "company", "council", "division", "board", "desk", "center", "centre",
            "institute", "association", "university", "school", "college", "agency", "bureau",
            "commission", "foundation", "society", "club", "systems", "solutions", "partners",
            "associates", "office", "bank", "energy", "gas", "power", "capital", "holdings"}


def parse(raw: str, text: str) -> list[dict]:
    """Model output -> [{'forms': [...], 'addr': str|None}]. A form or an address that does not occur in the email is dropped."""
    low = text.lower()
    in_text = {a.lower() for a in ADDR.findall(text)}
    out = []
    for line in (raw or "").splitlines():
        line = STRIP.sub("", line).strip()
        if not line or NOISE.match(line):
            continue
        names_part, _, addr_part = line.partition("|")
        addr = None
        m = ADDR.search(addr_part)
        if m and m.group(0).lower() in in_text:
            addr = m.group(0).lower()
        forms = []
        for f in names_part.split(","):
            f = STRIP.sub("", f).strip().strip('"\'')
            if not f or len(f) > 60 or not re.search(r"[A-Za-z]{2}", f):
                continue
            if f.lower() not in low:                      # guard: must be in the email
                continue
            toks = [w for w in re.findall(r"[A-Za-z']+", f.lower()) if len(w) > 1]
            if not toks or all(t in ROLE for t in toks):   # guard: a bare title is not a person
                continue
            if any(t in ORG_WORD for t in toks):           # guard: an organisation is not a person
                continue
            forms.append(f)
        if forms:
            out.append({"forms": sorted(set(forms), key=len, reverse=True), "addr": addr})
    return out


def main() -> int:
    from src.models.engine_factory import add_engine_args, engine_from_args, write_model_record
    ap = add_engine_args(argparse.ArgumentParser())
    ap.add_argument("--in", dest="inp", default=str(SAMPLE))
    ap.add_argument("--out", default="data/topics/people_extract.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--window", type=int, default=8000,
                    help="chars per prompt; longer emails are cut into overlapping windows")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.inp).open()]
    if args.limit:
        rows = rows[:args.limit]

    # The full body, quoted history included; long emails are windowed, not truncated.
    shell = PROMPT.read_text()
    win, overlap = args.window, 400
    texts, owner = [], []
    for i, r in enumerate(rows):
        t = f"{r.get('subject') or ''}\n{r.get('body') or ''}".strip()
        for s in range(0, max(1, len(t)), win - overlap):
            texts.append(t[s:s + win])
            owner.append(i)
            if s + win >= len(t):
                break
    print(f"{len(rows):,} emails -> {len(texts):,} prompts")
    prompts = [shell.replace("<<EMAIL>>", t) for t in texts]

    eng = engine_from_args(args)
    outs = eng.generate(prompts, max_tokens=512, temperature=0.0)

    per_email: dict[int, list[dict]] = collections.defaultdict(list)
    for i, t, o in zip(owner, texts, outs):
        per_email[i].extend(parse(o, t))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_people = n_anchored = 0
    with out.open("w") as f:
        for i, r in enumerate(rows):
            people = per_email.get(i, [])
            n_people += len(people)
            n_anchored += sum(1 for p in people if p["addr"])
            f.write(json.dumps({"email_id": r["email_id"], "people": people}) + "\n")

    forms = collections.Counter(fm.lower() for ps in per_email.values()
                                for p in ps for fm in p["forms"])
    write_model_record(out, eng, args)
    print(f"\nWROTE {out}")
    print(f"  person mentions     : {n_people:,}")
    print(f"  with an address     : {n_anchored:,}  ({100*n_anchored/max(1,n_people):.0f}%)")
    print(f"  distinct name forms : {len(forms):,}\n")
    for fm, c in forms.most_common(20):
        print(f"    {c:>4}  {fm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
