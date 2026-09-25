#!/usr/bin/env python3
"""Anonymisation, pass 2: merge the model's per-email people into clusters, give each one pseudonym,
rewrite the tagged spans. No model. A pure function of data/topics/people_extract.jsonl and --seed.

Join keys: an address, always; a multi-token name, across emails; a single token, only within the
email that produced it. Replacement covers the spans tagged in each email, plus a corpus-wide sweep of
full names, surnames that are not ordinary words, unambiguous first names, and bare logins.

  python scripts/anonymize_llm.py --seed 7    -> data/topics/sample_anon.jsonl and sample_anon.jsonl.map.json (private)
"""
from __future__ import annotations
import argparse, collections, json, random, re, sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")

from name_registry import (                                                   # noqa: E402
    Registry, canon_first, nicks_of, person_key, load_name_pool, load_name_vocab,
    _case_like, PHONE, SSN, SUITE, PO_BOX, STREET, CITY_ST_ZIP, CITY_STFULL_ZIP, EMAIL,
    NOT_NAME, STOP_EN, NOT_SURNAME, COMPANY_SRC,
)

HONORIFIC = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "rev", "sir", "madam"}
SUFFIX = {"jr", "sr", "ii", "iii", "iv"}
# Pronouns and kinship terms refer to a person without identifying one; they are not rewritten.
NOT_PERSON = {"you", "your", "yours", "i", "me", "my", "we", "us", "our", "he", "him", "his",
              "she", "her", "hers", "they", "them", "their", "it", "who", "whom", "someone",
              "anyone", "everybody", "somebody", "dad", "mom", "mum", "mother", "father", "parents",
              "grandma", "grandpa", "granny", "sis", "bro", "brother", "sister", "husband", "wife",
              "son", "daughter", "kids", "children", "family", "folks", "guys", "bubba", "honey",
              "boss", "colleague", "friend", "friends", "team", "guy", "man", "woman", "lady", "sir"}


def name_tokens(form: str) -> list[str]:
    """The identity-bearing words of a tagged form: honorifics, suffixes and initials removed."""
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", form)
    return [t for t in toks
            if len(t) > 1 and t.lower() not in HONORIFIC and t.lower() not in SUFFIX]


def is_person(form: str) -> bool:
    """False for a form that refers to a person without naming one (pronoun, kinship term)."""
    t = name_tokens(form)
    return bool(t) and not all(w.lower() in NOT_PERSON for w in t)


def word_stats(rows: list[dict]) -> tuple[dict[str, float], collections.Counter]:
    """Per token: the share of prose occurrences that are lowercase, and the lowercase count. Addresses are stripped first."""
    lower: collections.Counter = collections.Counter()
    upper: collections.Counter = collections.Counter()
    for r in rows:
        t = f"{r.get('subject') or ''}\n{r.get('body') or ''}"
        t = re.sub(r"\S+@\S+", " ", t)
        for w in re.findall(r"(?<![A-Za-z@.'])([A-Za-z][A-Za-z']{1,})(?![A-Za-z@.])", t):
            (lower if w[0].islower() else upper)[w.lower()] += 1
    frac = {w: lower[w] / (lower[w] + upper[w])
            for w in set(lower) | set(upper) if lower[w] + upper[w]}
    return frac, lower


def is_wordlike(tok: str, frac: dict[str, float], lower_n: collections.Counter | None = None,
                thresh: float = 0.25, min_n: int = 5) -> bool:
    """True if the token occurs as an ordinary lowercase word in the corpus: a high lowercase share over a minimum count."""
    w = tok.lower()
    if lower_n is not None and lower_n.get(w, 0) < min_n:
        return False
    return frac.get(w, 0.0) >= thresh


IS_ADDR = re.compile(r"^\s*<?[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}>?\s*$")


class Union:
    """Plain union-find over strings. Small enough that path compression alone is plenty."""

    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)      # deterministic: lexicographically smaller wins


def merge(extract: list[dict]) -> tuple[Union, dict]:
    """Join the per-email claims into clusters. Returns (union-find, per-email [(form, key)])."""
    uf = Union()
    mentions: dict[str, list[tuple[str, str]]] = {}
    for row in extract:
        local: list[tuple[str, str]] = []
        for p in row["people"]:
            forms = [f for f in p["forms"] if is_person(f)]
            if not forms:
                continue
            keys = []
            if p["addr"]:
                keys.append("@" + p["addr"])
            for f in forms:
                # An address in the name column is an address, not a name key.
                if IS_ADDR.match(f):
                    keys.append("@" + f.strip().strip("<>").lower())
                elif len(name_tokens(f)) > 1:            # multi-token names are safe global keys
                    keys.append("n:" + " ".join(t.lower() for t in name_tokens(f)))
            for a, b in zip(keys, keys[1:]):
                uf.union(a, b)
            anchor = keys[0] if keys else None
            for f in forms:
                if anchor is None:                       # lone token, no anchor: keyed by itself
                    anchor = "s:" + f.lower()
                    uf.find(anchor)
                local.append((f, anchor))
        mentions[row["email_id"]] = local
    return uf, mentions


def canonical(forms: collections.Counter) -> tuple[str, str] | None:
    """A cluster's real (first, last): the pair its mentions agree on most often; ties break alphabetically. Addresses are not tokenised."""
    votes: collections.Counter = collections.Counter()
    for f, n in forms.items():
        if IS_ADDR.match(f):
            continue
        t = name_tokens(f)
        if len(t) > 1:
            votes[(t[0].capitalize(), t[-1].capitalize())] += n
    if not votes:
        return None
    return min(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def render(form: str, first: str, last: str, ff: str, fl: str) -> str:
    """Rewrite one tagged form in the same shape: full name, first name, surname, honorific plus surname, login, initials. A middle name is dropped."""
    nicks = nicks_of(first) | {first.lower()}
    out, seen_any = [], False
    for tok in re.findall(r"[A-Za-z][A-Za-z'\-]*|[^A-Za-z]+", form):
        low = tok.lower().strip(".,'- ")
        if not low or not tok[0].isalpha():
            out.append(tok)
            continue
        if low in HONORIFIC or low in SUFFIX:
            out.append(tok)
        elif low in nicks or canon_first(low) == canon_first(first):
            out.append(_case_like(tok, ff)); seen_any = True
        elif low == last.lower():
            out.append(_case_like(tok, fl)); seen_any = True
        elif len(tok) == 1:
            out.append(tok)                              # a middle initial carries no identity
        else:
            continue                                     # unmatched word: drop rather than invent
    s = re.sub(r"\s{2,}", " ", "".join(out)).strip(" ,")
    if seen_any and s:
        return s
    # A login shape (vkamins, dp): rebuilt from the pseudonym the same way, so fake login and fake name agree.
    body = re.sub(r"[^A-Za-z]", "", form).lower()
    if body == (first[0] + last).lower()[:len(body)]:
        return (ff[0] + fl).lower()[:len(body)]
    if len(body) <= 3:
        return (ff[0] + fl[0]).lower() if len(body) <= 2 else (ff[0] + fl[:2]).lower()
    return (ff[0] + fl).lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", default="data/topics/people_extract.jsonl")
    ap.add_argument("--in", dest="inp", default="data/topics/sample.jsonl")
    ap.add_argument("--out", default="data/topics/sample_anon.jsonl")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--name-pool", choices=["census", "corpus"], default="census")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.inp).open()]
    extract = [json.loads(l) for l in Path(args.extract).open()]
    uf, mentions = merge(extract)

    # cluster -> every form and address the model attached to it
    forms_of: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    addrs_of: dict[str, set] = collections.defaultdict(set)
    for row in extract:
        for p in row["people"]:
            forms = [f for f in p["forms"] if is_person(f)]
            if not forms:
                continue
            keys = ["@" + p["addr"]] if p["addr"] else []
            keys += ["@" + f.strip().strip("<>").lower() for f in forms if IS_ADDR.match(f)]
            keys += ["n:" + " ".join(t.lower() for t in name_tokens(f))
                     for f in forms if not IS_ADDR.match(f) and len(name_tokens(f)) > 1]
            root = uf.find(keys[0]) if keys else None
            for f in forms:
                r = root if root is not None else uf.find("s:" + f.lower())
                forms_of[r][f] += 1
                if IS_ADDR.match(f):            # the model returned an address as a name form
                    addrs_of[r].add(f.strip().strip("<>").lower())
                if p["addr"]:
                    addrs_of[r].add(p["addr"])

    frac, lower_n = word_stats(rows)
    rng = random.Random(args.seed)
    reg = Registry(rng)
    load_name_vocab(reg)

    # Addresses are ground truth: first.last@ names a person, so the registry is seeded from them before the
    # model's clusters. Role accounts (health.center@) are refused.
    ROLE_LOCAL = {"health", "center", "centre", "public", "relations", "team", "address", "admin",
                  "administrator", "agent", "office", "support", "service", "services", "help",
                  "info", "news", "mail", "all", "enron", "outlook", "system", "payroll",
                  "benefits", "wellness", "hardware", "security", "travel", "customer", "manager",
                  "director", "president", "sales", "legal", "human", "resources", "desk", "group",
                  "corp", "the", "no", "reply", "noreply", "postmaster", "root", "webmaster"}
    # The full corpus's sender list settles who is real. Only surnames that occur in the sample are registered.
    seeded = 0
    present = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'\-]+",
                                             " ".join(f"{r.get('subject') or ''} {r.get('body') or ''}"
                                                      for r in rows))}
    stats = Path("data/enron/sender_stats.csv")
    if stats.exists():
        for line in stats.read_text().splitlines()[1:]:
            addr = line.split(",", 1)[0].strip().lower()
            mm = re.fullmatch(r"([a-z]+)\.(?:[a-z]\.)?([a-z]+)@(?:enron\.com|ect\.com|enron\.net)",
                              addr)
            if not mm:
                continue
            fn, ln = mm.group(1), mm.group(2)
            if fn in ROLE_LOCAL or ln in ROLE_LOCAL or len(fn) < 2 or len(ln) < 3:
                continue
            if ln not in present:                  # never mentioned here, so nothing to protect
                continue
            if reg.add(fn.capitalize(), ln.capitalize(), addr):
                seeded += 1
    print(f"  seeded from the full-corpus sender list: {seeded:,}")

    seeded = 0
    for r in rows:
        for field in ("from", "subject", "body"):
            for local, dom in EMAIL.findall(r.get(field) or ""):
                mm = re.fullmatch(r"([a-z]+)\.(?:[a-z]\.)?([a-z]+)", local.lower())
                if not mm:
                    continue
                fn, ln = mm.group(1), mm.group(2)
                if fn in ROLE_LOCAL or ln in ROLE_LOCAL or len(fn) < 2 or len(ln) < 3:
                    continue
                if reg.add(fn.capitalize(), ln.capitalize(), f"{local}@{dom}"):
                    seeded += 1
    print(f"  seeded from addresses: {len(reg.person):,} people ({seeded:,} address bindings)")


    # A cluster with a full name goes into the registry; a bare-first-name cluster is handled below.
    key_of: dict[str, tuple] = {}
    solo: dict[str, str] = {}
    for root, forms in sorted(forms_of.items()):
        cn = canonical(forms)
        if cn:
            k = reg.add(cn[0], cn[1], None)
            if k:
                key_of[root] = k
                for a in sorted(addrs_of[root]):
                    reg.person[k]["addrs"].add(a)
                    reg.addr2key[a] = k
                for f in forms:
                    reg.person[k]["firsts"] |= nicks_of(name_tokens(f)[0]) if name_tokens(f) else set()
    # A lone token may join an existing cluster when it identifies exactly one. Surnames are tried first;
    # a token that is also an ordinary word never joins.
    by_last: dict[str, set] = collections.defaultdict(set)
    by_first: dict[str, set] = collections.defaultdict(set)
    for k in reg.person:
        by_last[reg.person[k]["last"].lower()].add(k)
        for f in reg.person[k]["firsts"]:
            by_first[f.lower()].add(k)
    rescued = 0
    for root, forms in sorted(forms_of.items()):
        if root in key_of:
            continue
        toks = {t.lower() for f in forms for t in name_tokens(f)}
        if len(toks) != 1:
            continue
        tok = toks.pop()
        if is_wordlike(tok, frac, lower_n):
            continue
        cand = by_last.get(tok) or by_first.get(tok)
        if cand and len(cand) == 1:
            key_of[root] = next(iter(cand))
            rescued += 1
    if rescued:
        print(f"  rescued {rescued:,} lone tokens into the cluster they uniquely identify")

    # Every domain becomes a company word, so a firm's name and its domain map to the same base.
    orgs = set()
    for r in rows:
        for field in ("from", "subject", "body"):
            for _l, dom in EMAIL.findall(r.get(field) or ""):
                base = dom.lower().split(".")[-2] if dom.count(".") >= 1 else dom.lower()
                if len(base) >= 4 and base.isalpha() and base not in STOP_EN | NOT_SURNAME:
                    orgs.add(base)
                    reg.fake_domain(dom.lower())
    orgs -= {"enron"}                          # covered by the explicit Enron-family rules
    if orgs:
        reg.org_re = re.compile(r"(?<![A-Za-z])("
                                + "|".join(sorted(map(re.escape, orgs),
                                                  key=lambda w: (-len(w), w)))
                                + r")(?![A-Za-z])", re.I)
    print(f"  company words from domains: {len(orgs):,}")

    load_name_pool(reg, args.name_pool)
    reg.assign()

    used_first = {p["fake_first"].lower() for p in reg.person.values()}
    for root, forms in sorted(forms_of.items()):
        if root in key_of:
            continue
        real = sorted(forms)[0]
        for _ in range(10000):
            cand = rng.choice(reg.pool_first)
            if cand.lower() not in used_first and canon_first(cand) != canon_first(real):
                used_first.add(cand.lower())
                solo[root] = cand
                break

    print(f"clusters: {len(forms_of):,}   with a full name: {len(key_of):,}   "
          f"bare first name only: {len(solo):,}")

    # A lone word with no address, no full name, and an ordinary-word reading is dropped.
    dropped = {root for root, forms in forms_of.items()
               if root not in key_of and all(is_wordlike(f, frac, lower_n) for f in forms)}
    for root in dropped:
        solo.pop(root, None)
    if dropped:
        print(f"  dropped {len(dropped):,} lone tags that are ordinary words")

    # Sweep: a cluster's full name is swept corpus-wide; its surname too, unless the surname is an ordinary word.
    sweep: list[tuple[str, tuple]] = []
    for root, k in key_of.items():                 # every spelling the model saw for this person
        for f in forms_of[root]:
            if len(name_tokens(f)) > 1:
                sweep.append((f, k))
    # Over the registry, not only the model's clusters, so address-seeded people are swept too.
    for k, p in reg.person.items():
        sweep.append((f"{p['first']} {p['last']}", k))
        if not is_wordlike(p["last"], frac, lower_n) and len(p["last"]) > 2:
            sweep.append((p["last"], k))
    # A first name is swept only if it identifies one cluster and never occurs as lowercase prose.
    first_owner: dict[str, set] = collections.defaultdict(set)
    for k, p in reg.person.items():
        first_owner[p["first"].lower()].add(k)
    for f, ks in first_owner.items():
        if len(ks) == 1 and len(f) > 2 and not is_wordlike(f, frac, lower_n):
            sweep.append((f, next(iter(ks))))
    # A dict, not a set, and ties broken on the string: the output must not depend on PYTHONHASHSEED.
    sweep = list(dict.fromkeys(sweep))
    sweep.sort(key=lambda sk: (-len(sk[0]), sk[0]))
    print(f"  global sweep patterns: {len(sweep):,} (full names + non-word surnames)")

    # Bare logins (lbaltz) map to the local part of their own anonymised address.
    local_map: dict[str, str] = {}
    for r in rows:
        for field in ("from", "subject", "body"):
            for local, dom in EMAIL.findall(r.get(field) or ""):
                real = f"{local}@{dom}"
                k = reg.addr2key.get(real.lower())
                fake_local = (reg.fake_addr(k, real) if k
                              else reg.fake_unknown_addr(real)).split("@")[0]
                ll = local.lower()
                # A real login never occurs as a lowercase word; role accounts (customer, info) do. Require a count of zero.
                if len(ll) >= 4 and ll.isalnum() and lower_n.get(ll, 0) == 0:
                    local_map[ll] = fake_local
    login_sweep = sorted(local_map.items(), key=lambda kv: -len(kv[0]))
    print(f"  bare login tokens: {len(login_sweep):,}")

    # ---- rewrite
    out_rows = []
    changed = 0
    for r in rows:
        held: list[str] = []

        def hold(final: str) -> str:
            """Park a finished replacement behind a letterless placeholder so a later pass cannot
            rewrite it again, that is how 'Ann Kenneth' and 'Doris Kenneth' were manufactured."""
            held.append(final)
            return f"\x00{len(held) - 1}\x00"

        def do(text: str) -> str:
            if not text:
                return text
            text = SSN.sub(lambda m: hold(reg.fake_phone(m.group(0))), text)
            text = SUITE.sub(lambda m: hold(re.sub(r"\d+", str(rng.randint(1, 999)), m.group(0))), text)
            text = PO_BOX.sub(lambda m: hold(f"P.O. Box {rng.randint(100, 99999)}"), text)
            text = PHONE.sub(lambda m: hold(reg.fake_phone(m.group(0))), text)
            text = STREET.sub(lambda m: hold(reg.fake_street(m.group(0))), text)

            def _addr(m):
                local, dom = m.group(1), m.group(2)
                k = reg.addr2key.get(f"{local}@{dom}".lower())
                if k:
                    return hold(reg.fake_addr(k, f"{local}@{dom}"))
                return hold(reg.fake_unknown_addr(f"{local}@{dom}"))
            text = EMAIL.sub(_addr, text)

            # Only the spans tagged in this email, longest first.
            for form, root in sorted(mentions.get(r["email_id"], []),
                                     key=lambda fr: -len(fr[0])):
                k = key_of.get(root)
                if k:
                    p = reg.person[k]
                    rep = render(form, p["first"], p["last"], p["fake_first"], p["fake_last"])
                else:
                    fake = solo.get(root)
                    if not fake:
                        continue
                    # Keep the honorific: "Mr. Lay" becomes "Mr. <surname>".
                    lead = re.match(r"^\s*((?:(?:%s)\.?\s+)*)" % "|".join(HONORIFIC),
                                    form, re.I)
                    rep = (lead.group(1) if lead else "") + fake
                if not rep:
                    continue
                text = re.sub(rf"(?<![A-Za-z]){re.escape(form)}(?![A-Za-z])",
                              lambda m: hold(_case_like(m.group(0), rep)), text)

            # Companies: domain-derived names first, then "enron" as a substring (ENRON_DEVELOPMENT defeats word boundaries).
            if reg.org_re is not None:
                text = reg.org_re.sub(
                    lambda m: hold(_case_like(m.group(0), reg.company_token(m.group(0)))), text)
            for src in sorted(COMPANY_SRC, key=len, reverse=True):
                if "enron" in src.lower():
                    continue
                text = re.sub(rf"\b{re.escape(src)}\b",
                              lambda m, s_=src: hold(_case_like(m.group(0), reg.company_token(s_))),
                              text, flags=re.I)
            for src in ("Enron North America", "Enron Wholesale", "Enron Online", "EnronOnline",
                        "Enron Corp"):
                text = re.sub(re.escape(src),
                              lambda m, s_=src: hold(_case_like(m.group(0), reg.company_token(s_))),
                              text, flags=re.I)
            text = re.sub(r"enron",
                          lambda m: hold(_case_like(m.group(0), reg.company_token("Enron"))),
                          text, flags=re.I)
            for src in ("ECT", "ENA", "EES", "EBS", "EOL"):
                text = re.sub(rf"\b{src}\b",
                              lambda m, s_=src: hold(reg.company_token(s_)), text)

            # Safety net for names pass 1 missed in this particular email.
            for s, k in sweep:
                if s.lower() not in text.lower():
                    continue
                p = reg.person[k]
                rep = render(s, p["first"], p["last"], p["fake_first"], p["fake_last"])
                if rep:
                    # Allow a possessive tail without an apostrophe ("Skillings availability").
                    text = re.sub(rf"(?<![A-Za-z]){re.escape(s)}(?:'s|s'|'|s)?(?![A-Za-z])",
                                  lambda m: hold(_case_like(m.group(0), rep)), text, flags=re.I)
            for real_local, fake_local in login_sweep:
                if real_local not in text.lower():
                    continue
                # '@' is allowed on both sides: well-formed addresses were consumed earlier, so what is left is malformed (dperlin@enron).
                text = re.sub(rf"(?<![A-Za-z0-9.]){re.escape(real_local)}(?![A-Za-z0-9.])",
                              lambda m, fl=fake_local: hold(_case_like(m.group(0), fl)),
                              text, flags=re.I)
            return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)

        new = dict(r)
        for field in ("subject", "body", "own_body", "from"):
            if field in new:
                new[field] = do(new[field])
        if new.get("body") != r.get("body"):
            changed += 1
        out_rows.append(new)

    out = Path(args.out)
    with out.open("w") as f:
        for r in out_rows:
            f.write(json.dumps(r) + "\n")
    mp = Path(str(out) + ".map.json")
    mp.write_text(json.dumps({
        "seed": args.seed,
        "people": {f"{p['first']} {p['last']}": {"fake": f"{p['fake_first']} {p['fake_last']}",
                                                 "addrs": sorted(p["addrs"])}
                   for p in reg.person.values()},
        "solo": {sorted(forms_of[r])[0]: v for r, v in solo.items()},
        # Addresses that resolved to nobody get a person-shaped fake local part, recorded so the audit does not report it.
        "unknown_addrs": reg.contact,
        "companies": reg.company,
        "domains": reg.domain,
    }, indent=1))
    print(f"WROTE {out}   ({changed:,} of {len(rows):,} emails changed)")
    print(f"WROTE {mp}   (private — never publish)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
