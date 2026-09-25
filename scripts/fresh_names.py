#!/usr/bin/env python3
"""Names and domain stems that occur nowhere in the release, for the people planted chains mint. A
token is fresh if it never occurs in any body, subject or address of the release and is not a
pseudonym in the map.

  python scripts/fresh_names.py            -> benchmark_pool/fresh_names.json
"""
import csv
import json
import random
import re
from pathlib import Path

RELEASE = Path("data/release/background_2000.jsonl")
MAP = Path("data/topics/sample_anon.jsonl.map.json")
SSA = Path("data/names/ssa_atleast100.txt")
CENSUS = Path("data/names/census/Names_2010Census.csv")
OUT = Path("benchmark_pool/fresh_names.json")


def main():
    rows = [json.loads(l) for l in RELEASE.open() if l.strip()]
    text = "\n".join(f"{r['from']}\n{r.get('subject') or ''}\n{r.get('body') or ''}" for r in rows).lower()
    used = set(re.findall(r"[a-z]+", text))
    m = json.loads(MAP.read_text())
    for v in (m.get("people") or {}).values():
        used |= set(re.findall(r"[a-z]+", str(v).lower()))
    domains = sorted({r["from"].split("@")[1] for r in rows})
    stems = sorted({re.sub(r"\d.*$", "", d.split(".")[0]) for d in domains if re.match(r"[a-z]+\d+\.", d)})

    firsts = [l.strip() for l in SSA.read_text().splitlines() if l.strip()]
    firsts = [f for f in firsts if f.isalpha() and f.lower() not in used]
    with CENSUS.open() as f:
        surnames = [r["name"].capitalize() for r in csv.DictReader(f) if r["name"].isalpha() and r["name"].lower() not in used]
    surnames = surnames[:4000]                                    # the common ones read as names; the tail of the census does not
    rng = random.Random(20260924)
    names = sorted({f"{rng.choice(firsts)} {rng.choice(surnames)}" for _ in range(6000)})
    rng.shuffle(names)
    out = {"_about": "Names and domain stems that occur nowhere in the release corpus, for people a planted chain mints "
                     "(outside parties: family, a bank, a registrar). Built by scripts/fresh_names.py; belongs in the "
                     "anonymisation pass's registry on its next run.",
           "counts": {"first_names": len(firsts), "surnames": len(surnames), "names": len(names), "corpus_domains": len(domains)},
           "names": names, "domain_stems": stems, "corpus_domains": domains}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out["counts"]), "| stems", stems[:8])


if __name__ == "__main__":
    main()
