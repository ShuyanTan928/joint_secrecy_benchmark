#!/usr/bin/env python3
"""Freeze the anonymised sample as data/release/background_2000.jsonl with a manifest computed from the
files: counts, the model of every stage, how many identifiable Enron surnames are gone, the audit's
buckets, and two regression lists (phrases that must survive, names that must be gone).

  python scripts/make_release.py
"""
from __future__ import annotations
import collections, hashlib, json, re, sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")

from anonymize_llm import word_stats, is_wordlike, NOT_PERSON, name_tokens   # noqa: E402
from audit_names import load_fakes, classify                                 # noqa: E402

ORIG = Path("data/topics/sample.jsonl")
ANON = Path("data/topics/sample_anon.jsonl")
MAP = Path("data/topics/sample_anon.jsonl.map.json")
EXTRACT = Path("data/topics/people_extract.jsonl")
AUDIT = Path("data/topics/name_audit.jsonl")
OUT = Path("data/release/background_2000.jsonl")

EMAIL_ENRON = re.compile(r"([A-Za-z0-9._%+\-]+)@(enron\.com|ect\.com|enron\.net)", re.I)
# Local parts that name a function, not a person.
ROLE_LOCAL = {"health", "center", "public", "relations", "team", "address", "administrator",
              "agent", "office", "support", "service", "services", "help", "info", "news", "mail",
              "all", "enron", "outlook", "system", "payroll", "benefits", "wellness", "hardware",
              "security", "travel", "information", "management"}
ORG_WORD = {"team", "group", "committee", "department", "dept", "inc", "llc", "corp", "council",
            "division", "board", "desk", "center", "institute", "association", "university",
            "school", "office", "bank", "energy"}

# Phrases that must survive; each was once destroyed by over-replacement.
MUST_KEEP = ["Long time no talk", "Long-Term Care", "Customer Satisfaction Manager",
             "Long Term Northwest", "January", "February", "Monday", "Houston", "Texas"]
# Names that must be gone.
MUST_GO = ["Skilling", "Kaminski", "Dasovich", "Titman", "Perlingiere", "Whalley", "Zufferli",
           "Lokay", "Enron"]


def model_of(path: Path, default: str) -> str:
    """The model that wrote a file, from the <file>.model.json its script left beside it."""
    side = Path(str(path) + ".model.json")
    if side.exists():
        d = json.loads(side.read_text()); return f"{d.get('model')} ({d.get('engine')}, preset {d.get('preset')})"
    return default


def main() -> int:
    orig = [json.loads(l) for l in ORIG.open()]
    anon = [json.loads(l) for l in ANON.open()]
    frac, lower_n = word_stats(orig)
    fakes = load_fakes(MAP)
    blob = "\n".join(f"{r.get('subject') or ''}\n{r.get('body') or ''}" for r in anon)
    orig_blob = "\n".join(f"{r.get('subject') or ''}\n{r.get('body') or ''}" for r in orig)
    low = blob.lower()

    # ---- coverage of the people who are verifiably real Enron staff
    people = set()
    for r in orig:
        for f in ("from", "subject", "body"):
            for loc, _d in EMAIL_ENRON.findall(r.get(f) or ""):
                m = re.fullmatch(r"([a-z]+)\.(?:[a-z]\.)?([a-z]+)", loc.lower())
                if m and len(m.group(1)) > 1 and len(m.group(2)) > 2 \
                        and m.group(1) not in ROLE_LOCAL and m.group(2) not in ROLE_LOCAL:
                    people.add((m.group(1), m.group(2)))
    surviving = [(a, b) for a, b in sorted(people)
                 if b not in fakes and re.search(rf"(?<![a-z]){re.escape(b)}(?![a-z])", low)]
    word_sur = [f"{a} {b}" for a, b in surviving if is_wordlike(b, frac, lower_n)]
    real_sur = [f"{a} {b}" for a, b in surviving if not is_wordlike(b, frac, lower_n)]

    # ---- independent audit, re-bucketed
    buckets: collections.Counter = collections.Counter()
    flagged = set()
    if AUDIT.exists():
        for a in (json.loads(l) for l in AUDIT.open()):
            for f in a["found"]:
                if classify(f["name"], fakes) == "clean":
                    continue
                t = name_tokens(f["name"].lower())
                flagged.add(a["email_id"])
                if not t or all(w.lower() in NOT_PERSON for w in t):
                    k = "kinship_or_pronoun_left_deliberately"
                elif any(w.lower() in ORG_WORD for w in t):
                    k = "organisation_left_deliberately"
                elif all(len(w) <= 2 for w in t):
                    k = "initials"
                elif all(is_wordlike(w, frac, lower_n) for w in t):
                    k = "ordinary_english_word_left_deliberately"
                else:
                    k = "residual_name_leak"
                buckets[k] += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(ANON.read_bytes())
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()

    manifest = {
        "name": "background_2000",
        "status": "FINAL as of this run",
        "n_emails": len(anon),
        "n_threads": len({r.get("thread_id") for r in anon}),
        "topics": dict(sorted(collections.Counter(r.get("topic") for r in anon).items())),
        "sha256": digest,
        "provenance": {
            "source": "Enron corpus (FERC 2003 release), 150 custodians, full parsed set",
            "sampled_by": "scripts/sample_dataset.py",
            "name_detection": {
                "script": "scripts/extract_people.py",
                "model": model_of(EXTRACT, "unrecorded") + ", temperature 0",
                "cache": str(EXTRACT),
                "note": "the model tags and links names per email; it never generates a "
                        "replacement and never sees the real->fake map",
            },
            "replacement": {
                "script": "scripts/anonymize_llm.py",
                "seed": json.loads(MAP.read_text()).get("seed"),
                "note": "pure function of (cache, seed); verified byte-identical across runs "
                        "under randomised PYTHONHASHSEED",
            },
            "verification": {"script": "scripts/audit_names.py",
                             "model": model_of(AUDIT, "unrecorded") + ", reads the anonymized text with no "
                                      "knowledge of the pipeline"},
        },
        "verification": {
            "enron_people_identifiable_from_an_address": len(people),
            "surname_absent_from_output": len(people) - len(surviving),
            "surname_present_but_an_ordinary_english_word": len(word_sur),
            "surname_present_genuine_miss": len(real_sur),
            "genuine_misses": real_sur,
            "ordinary_word_surnames_left_alone": word_sur,
            "audit_emails_flagged": len(flagged),
            "audit_buckets": dict(buckets.most_common()),
            "must_keep": {s: len(re.findall(re.escape(s), blob, re.I)) for s in MUST_KEEP if re.search(re.escape(s), orig_blob, re.I)},   # only phrases the source has
            "must_go": {s: len(re.findall(re.escape(s), blob, re.I)) for s in MUST_GO},
        },
        "known_gaps": [
            "surnames that are also ordinary English words (Long, Black, King, May, Cash, Kitchen) "
            "are replaced only where the model identifies a person; sweeping them corpus-wide is "
            "what produced 'Gwyneth time no talk' in the previous pipeline",
            "'January' is in NOT_SURNAME, so Steve January is not registered — the month is worth "
            "more than the one surname",
            "logins that never appear beside an @domain (lbaltz, ktennes, sevatt) have nothing to "
            "map them to",
            "EB nnnn Enron Building room numbers are not yet anonymized",
            "the planted-secret cast must be drawn from this pseudonym pool, or the cast is a tell",
        ],
        "private_do_not_publish": [str(MAP), "data/topics/sample.jsonl.idmap.json"],
        "topic_classifier": model_of(Path("data/topics/labels.jsonl"), "unrecorded"),
    }
    mf = OUT.with_suffix(".manifest.json")
    mf.write_text(json.dumps(manifest, indent=1))
    print(f"WROTE {OUT}   sha256 {digest[:16]}…")
    print(f"WROTE {mf}")
    print(f"\n  enron people from addresses : {len(people):,}")
    print(f"    surname gone              : {len(people)-len(surviving):,} "
          f"({100*(len(people)-len(surviving))/len(people):.1f}%)")
    print(f"    ordinary word, left alone : {len(word_sur)}")
    print(f"    genuine miss              : {len(real_sur)}  {', '.join(real_sur)}")
    bad_keep = [s for s, n in manifest["verification"]["must_keep"].items() if n == 0]
    bad_go = [s for s, n in manifest["verification"]["must_go"].items() if n > 0]
    print(f"\n  regression: must-keep intact : {'YES' if not bad_keep else 'NO ' + str(bad_keep)}")
    print(f"  regression: must-go absent   : {'YES' if not bad_go else 'NO ' + str(bad_go)}")
    return 0 if not bad_keep and not bad_go else 1


if __name__ == "__main__":
    raise SystemExit(main())
