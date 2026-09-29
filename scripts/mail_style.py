#!/usr/bin/env python3
"""How the planted emails of a set read against the released mailbox: the features that give generated mail away, the share
of emails with each, per set and for the release, and the planted emails that carry the most of them.

  python scripts/mail_style.py --state data/benchmark/keystone30/state.json
  python scripts/mail_style.py --state data/benchmark/keystone30/state.json --state logs/restyle.json --top 15

Only the sender's own text is read: a quoted or forwarded message below it is cut off."""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
from pathlib import Path

RELEASE = Path("data/release/background_2000.jsonl")
QUOTE = re.compile(r"-----\s*(?:Original Message|Forwarded by)|^\s*From:\s|^[ \t]{2,}\S.*<[^>]+@[^>]+>", re.M)


def own(text: str) -> str:
    m = QUOTE.search(text or "")
    return (text[:m.start()] if m else text or "").rstrip()


def sentences(t: str) -> int:
    return len(re.findall(r"[a-z0-9)]\.\s+[A-Z]", t))


# Habits of generated mail; each is a regex over the sender's own text.
TELLS = {
    "introduces itself or its purpose": (r"this is in response to|i(?:'m| am) writing|following up on|as part of (?:our|your|the)\b", re.I),
    "a reference said as a label": (r"\b[A-Z]{0,5}-?\d[\w./-]*\d\b,? (?:is|was) (?:my|our|his|her|the|us)\b|\bunder my (?:[a-z]+ )?(?:id|number|no\.?|file)\b|\bthat'?s us\b|\bbelongs to\b", re.I),
    "the next step reported": (r"\bI(?:'ll| will)? (?:sign(?:ed)?|mail(?:ed)?|paid|drop(?:ped)? off|told the|go ahead)\b|\bwe're officially\b|\bso there's no reason to\b", 0),
    "an institution left unnamed": (r"\b(?:the|a) (?:state university|county [a-z' ]{0,20}(?:clinic|office)|rival (?:company|firm|trading firm)|women's health clinic)\b", re.I),
    "a title block": (r"\n\s*[A-Z][A-Za-z&' ]+(?:Officer|Coordinator|Specialist|Clerk|Representative|Examiner|Administration|Services|Department)\s*$", re.M),
    "Thanks, alone on a line": (r"^\s*thanks,\s*$", re.I | re.M),
}
SHAPE = {
    "a line over 100 characters": lambda t: max((len(l) for l in t.split("\n")), default=0) > 100,
    "two spaces after a sentence": lambda t: bool(re.search(r"[a-z0-9)]\.  [A-Z]", t)),
    "opens with a greeting line": lambda t: bool(re.match(r"\s*(?:(?:hi|hello|dear|hey)\b[^\n]{0,40}|[A-Z][\w.' -]{0,30}[,:!-]?)\s*\n", t, re.I)),
    "an exclamation mark": lambda t: "!" in t,
    "dots or a spaced dash": lambda t: bool(re.search(r"\.\.\.| - | -- ", t)),
    "over 150 words": lambda t: len(t.split()) > 150,
    "under 20 words": lambda t: len(t.split()) < 20,
}


def planted(state: Path) -> list[dict]:
    d = json.loads(state.read_text())
    out = []
    for i, c in enumerate(d.get("chains", [])):
        if c.get("error") or not c.get("emails"):
            continue
        for q in c["emails"].get("clues") or []:
            for m in q.get("messages") or []:
                out.append({"chain": i, "clue": q.get("i"), "pattern": c.get("pattern", ""), "from": str(m.get("from", "")).split("<")[0].strip(),
                            "subject": m.get("subject", ""), "text": own(str(m.get("body", "")))})
    return out


def shares(texts: list[str]) -> dict[str, str]:
    n = len(texts) or 1
    row = {"emails": str(len(texts)), "median words": str(int(st.median([len(t.split()) for t in texts]))) if texts else "0"}
    multi = [t for t in texts if sentences(t) >= 2]
    for name, f in SHAPE.items():
        pool = multi if name == "two spaces after a sentence" else texts
        row[name] = f"{100 * sum(f(t) for t in pool) / (len(pool) or 1):.0f}%"
    for name, (rx, fl) in TELLS.items():
        row[name] = f"{100 * sum(bool(re.search(rx, t, fl)) for t in texts) / n:.0f}%"
    return row


def tells_of(t: str) -> list[str]:
    got = [name for name, (rx, fl) in TELLS.items() if re.search(rx, t, fl)]
    return got + (["a line over 100 characters"] if SHAPE["a line over 100 characters"](t) else [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", action="append", required=True, help="a state file with planted chains; may be given more than once")
    ap.add_argument("--release", default=str(RELEASE))
    ap.add_argument("--top", type=int, default=10, help="list the planted emails with the most tells")
    a = ap.parse_args()
    release = [own(json.loads(l).get("own_body") or json.loads(l).get("body") or "") for l in Path(a.release).open() if l.strip()]
    sets = {Path(s).parent.name if Path(s).name == "state.json" else Path(s).stem: planted(Path(s)) for s in a.state}
    rows = {name: shares([e["text"] for e in em]) for name, em in sets.items()}
    rows["the release"] = shares(release)
    cols = list(rows)
    print("| feature | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols))
    for feat in rows["the release"]:
        print(f"| {feat} | " + " | ".join(rows[c][feat] for c in cols) + " |")
    for name, em in sets.items():
        ranked = sorted(em, key=lambda e: -len(tells_of(e["text"])))[: a.top]
        print(f"\n{name}: the {len(ranked)} planted emails with the most tells")
        for e in ranked:
            snippet = " ".join(e["text"].split())[:220]
            print(f"- chain {e['chain']}, clue {e['clue']}, {e['from']}, \"{e['subject']}\": {', '.join(tells_of(e['text'])) or 'none'}\n    {snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
