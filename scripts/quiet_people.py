#!/usr/bin/env python3
"""Firm people a planted chain may cast into a role: senders of one email who received at most one, not
named in full in anyone else's email, whose email, read by a model, fixes no role of theirs (job,
reporting line, society, relationship). Firm domain only; outside parties are minted at casting.

  python scripts/quiet_people.py --dry            # code stage only
  python scripts/quiet_people.py                  -> benchmark_pool/quiet_people.json
"""
from pathlib import Path
import argparse
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import collections
import json
import re

RELEASE = Path("data/release/background_2000.jsonl")
PROMPT = Path("prompts/quiet_people.md")
OUT = Path("benchmark_pool/quiet_people.json")


def name_from_addr(addr: str):
    loc = addr.split("@")[0]
    parts = [p for p in loc.split(".") if p.isalpha()]
    if len(parts) >= 2:
        return " ".join(p.capitalize() for p in parts)
    return ""


def thread_text(mine: dict, other: dict | None, window: int) -> str:
    def block(r, mark):
        t = f"{mark}\nFrom: {r['from']}\nDate: {r['date']}\nSubject: {r.get('subject') or ''}\n\n{(r.get('body') or '').strip()}"
        return t[:window]
    out = [block(mine, "=== THE MARKED EMAIL ===")]
    if other:
        out.append(block(other, "=== the other message of the thread (context only) ==="))
    return "\n\n".join(out)


def parse(o: str) -> dict:
    m = re.search(r"\{.*\}", o, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    return {"signed_name": str(d.get("signed_name") or "").strip(),
            "role_fixed": str(d.get("role_fixed") or "").strip().lower() == "yes",
            "role": str(d.get("role") or "").strip(),
            "evidence": str(d.get("evidence") or "").strip(),
            "parsed": bool(m and d)}


def main() -> int:
    from src.models.engine_factory import add_engine_args, engine_from_args, write_model_record
    ap = add_engine_args(argparse.ArgumentParser())
    ap.add_argument("--in", dest="inp", default=str(RELEASE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--max-received", type=int, default=1, help="at most this many other messages in the sender's thread")
    ap.add_argument("--window", type=int, default=6000, help="chars of each message given to the model")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--firm-only", action="store_true", default=True, help="keep only the firm domain (outsiders are minted new at casting)")
    ap.add_argument("--all-domains", dest="firm_only", action="store_false")
    ap.add_argument("--dry", action="store_true", help="code stage only")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.inp).open() if l.strip()]
    by_sender = collections.defaultdict(list)
    by_thread = collections.defaultdict(list)
    for r in rows:
        by_sender[r["from"]].append(r)
        by_thread[r["thread_id"]].append(r)
    domains = collections.Counter(a.split("@")[1] for a in by_sender)
    firm_domain = domains.most_common(1)[0][0]

    # --- code stage: quiet senders
    cands = []
    for addr, ms in by_sender.items():
        if len(ms) != 1:
            continue
        r = ms[0]
        others = [m for m in by_thread[r["thread_id"]] if m["email_id"] != r["email_id"]]
        if len(others) > args.max_received:
            continue
        cands.append({"addr": addr, "name": name_from_addr(addr), "firm": addr.endswith("@" + firm_domain),
                      "domain": addr.split("@")[1], "topic": r["topic"], "thread_id": r["thread_id"],
                      "email_id": r["email_id"], "date": r["date"], "sent": 1, "received": len(others),
                      "_row": r, "_other": others[0] if others else None})
    if args.firm_only:
        cands = [c for c in cands if c["firm"]]
    # Not named in full elsewhere; a shared surname alone does not count.
    lower_by_id = {r["email_id"]: (r.get("body") or "").lower() for r in rows}
    def named_elsewhere(c):
        nm = c["name"].lower().split()
        if len(nm) < 2:
            return False
        full = " ".join(nm)
        return any(full in body for eid, body in lower_by_id.items() if eid != c["email_id"])
    n_before = len(cands)
    cands = [c for c in cands if not named_elsewhere(c)]
    n_named = n_before - len(cands)
    cands.sort(key=lambda c: c["addr"])
    if args.limit:
        cands = cands[:args.limit]
    n_firm = sum(1 for c in cands if c["firm"])
    n_addr = sum(1 for c in cands if c["name"])
    print(f"senders {len(by_sender):,}; one email and at most {args.max_received} received{', firm only' if args.firm_only else ''}: "
          f"{len(cands)+n_named:,}; named in full in someone else's email and dropped: {n_named:,}; left {len(cands):,} "
          f"(firm {n_firm:,}, outside {len(cands)-n_firm:,}; name in address {n_addr:,}, handle only {len(cands)-n_addr:,})")
    if args.dry:
        return 0

    # --- model stage
    shell = PROMPT.read_text()
    prompts = [shell.replace("<<THREAD>>", thread_text(c["_row"], c["_other"], args.window)) for c in cands]
    from src.models.engine_factory import build_engine
    eng = engine_from_args(args)
    outs = eng.generate(prompts, max_tokens=300, temperature=0.0)

    people = []
    for c, o in zip(cands, outs):
        p = parse(o)
        rec = {k: v for k, v in c.items() if not k.startswith("_")}
        if not rec["name"] and p["signed_name"]:
            rec["name"] = p["signed_name"]
        rec.update({"signed_name": p["signed_name"], "role_fixed": p["role_fixed"], "role": p["role"],
                    "evidence": p["evidence"], "model_parsed": p["parsed"]})
        people.append(rec)
    def signed_by_code(body):
        """The last short line of the writer's own text, when it is one capitalised word and not a closing word."""
        lines = [l.strip() for l in (body or "").strip().splitlines() if l.strip()]
        for ln in reversed(lines[-3:]):
            if re.fullmatch(r"[A-Z][a-z]{1,15}[.,]?", ln) and ln.rstrip(".,").lower() not in ("thanks", "thx", "cheers", "best", "regards", "later", "sincerely"):
                return ln.rstrip(".,")
        return ""
    for c, rec in zip(cands, people):                    # the model sometimes reads the address as the signature; the code's read of the sign-off wins
        code_signed = signed_by_code(c["_row"].get("own_body") or c["_row"].get("body"))
        if code_signed and (not rec["signed_name"] or code_signed.lower() != rec["signed_name"].split()[0].lower()):
            rec["signed_name_model"] = rec["signed_name"]; rec["signed_name"] = code_signed
    for rec in people:                                   # the release maps body names and addresses separately, so a
        first = rec["addr"].split("@")[0].split(".")[0]  # signed first name can differ from the address; casting must
        signed = rec["signed_name"].split()[0].lower() if rec["signed_name"] else ""   # not add a third name on top
        rec["name_consistent"] = (not signed) or (not first.isalpha()) or ("." not in rec["addr"].split("@")[0]) or signed == first.lower()
    free = [p for p in people if not p["role_fixed"] and p["model_parsed"]]
    out = {"_about": "Background-corpus people a planted chain may cast into a role: one email sent, at most "
                     f"{args.max_received} received (thread position; the release has no To field), and the model "
                     "read their email as not fixing any role of theirs (job, reporting line, society, relationship); "
                     "nobody else's email names them in full; firm domain only unless --all-domains (outsiders are minted new at casting). Built by scripts/quiet_people.py from "
                     f"{args.inp} with prompts/quiet_people.md on {args.engine} {args.preset}. 'people' are the usable ones; "
                     "'role_fixed' lists the rest with the role and the words that fixed it, for checking.",
           "firm_domain": firm_domain, "counts": {
               "candidates": len(people), "usable": len(free),
               "usable_firm": sum(1 for p in free if p["firm"]), "usable_outside": sum(1 for p in free if not p["firm"]),
               "usable_with_name": sum(1 for p in free if p["name"]),
               "usable_name_consistent": sum(1 for p in free if p["name_consistent"]),
               "usable_firm_name_consistent": sum(1 for p in free if p["firm"] and p["name_consistent"]), "unparsed": sum(1 for p in people if not p["model_parsed"])},
           "people": free, "role_fixed": [p for p in people if p["role_fixed"]],
           "unparsed": [p for p in people if not p["model_parsed"]]}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    write_model_record(args.out, eng, args)
    print(f"WROTE {args.out}: {json.dumps(out['counts'])}")
    jobs = collections.Counter(p["role"].lower() for p in out["role_fixed"])
    for j, n in jobs.most_common(15):
        print(f"  {n:>3}  {j}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
