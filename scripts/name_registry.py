#!/usr/bin/env python3
"""The pseudonym registry anonymize_llm.py uses: one pseudonym per person, applied to every form of the
name (address, Lotus handle, "Last, First", full name, bare surname or first name in scope), plus
companies, domains, phones, street addresses and ZIP codes. Run alone it is the older regex-only
anonymiser.

Name pools (data/names/): census (default), SSA first names x Census 2010 surnames; corpus, names
from the Enron address book recombined. A pseudonym never equals a real corpus person and never
shares a half with the person it replaces. The output is rescanned for surviving real names, and the
run exits non-zero on a hit.

  python scripts/name_registry.py --seed 1234
"""
from __future__ import annotations
import argparse, collections, csv, json, random, re, secrets, sys
from pathlib import Path

IN = Path("data/topics/sample.jsonl")
ADDR_BOOK = Path("data/enron/sender_stats.csv")

# ----------------------------------------------------------------------------------------------- names
FIRST = """James John Robert Michael William David Richard Joseph Thomas Charles Christopher Daniel Matthew
Anthony Donald Steven Paul Andrew Joshua Kenneth Kevin Brian George Timothy Ronald Edward Jason Jeffrey
Ryan Jacob Gary Nicholas Eric Jonathan Stephen Larry Justin Scott Brandon Benjamin Samuel Gregory
Alexander Patrick Frank Raymond Jack Dennis Jerry Tyler Aaron Jose Adam Nathan Henry Douglas Zachary
Peter Kyle Noah Ethan Jeremy Walter Christian Keith Roger Terry Austin Sean Gerald Carl Harold Dylan
Arthur Lawrence Jordan Jesse Bryan Billy Bruce Gabriel Joe Logan Alan Juan Albert Willie Elijah Wayne
Randy Vincent Mason Roy Ralph Eugene Russell Bobby Philip Louis
Mary Patricia Jennifer Linda Elizabeth Barbara Susan Jessica Sarah Karen Lisa Nancy Betty Sandra Margaret
Ashley Kimberly Emily Donna Michelle Carol Amanda Melissa Deborah Stephanie Dorothy Rebecca Sharon Laura
Cynthia Amy Kathleen Angela Shirley Brenda Emma Anna Pamela Nicole Samantha Katherine Christine Helen
Debra Rachel Carolyn Janet Maria Catherine Heather Diane Olivia Julie Joyce Victoria Ruth Virginia
Lauren Kelly Christina Joan Evelyn Judith Andrea Hannah Megan Cheryl Jacqueline Martha Madison Teresa
Gloria Sara Janice Ann Kathryn Abigail Sophia Frances Jean Alice Judy Isabella Julia Grace Amber Denise
Danielle Marilyn Beverly Charlotte Natalie Theresa Diana Brittany Doris Kayla Alexis Lori Marie""".split()
LAST = """Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Gonzalez
Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris Sanchez Clark Ramirez
Lewis Robinson Walker Young Allen King Wright Scott Torres Nguyen Hill Flores Green Adams Nelson Baker
Hall Rivera Campbell Mitchell Carter Roberts Gomez Phillips Evans Turner Diaz Parker Cruz Edwards
Collins Reyes Stewart Morris Morales Murphy Cook Rogers Gutierrez Ortiz Morgan Cooper Peterson Bailey
Reed Kelly Howard Ramos Kim Cox Ward Richardson Watson Brooks Chavez Wood James Bennett Gray Mendoza
Ruiz Hughes Price Alvarez Castillo Sanders Patel Myers Long Ross Foster Jimenez Powell Jenkins Perry
Russell Sullivan Bell Coleman Butler Henderson Barnes Gonzales Fisher Vasquez Simmons Romero Jordan
Patterson Alexander Hamilton Graham Reynolds Griffin Wallace Moreno West Cole Hayes Bryant Herrera
Gibson Ellis Tran Medina Aguilar Stevens Murray Ford Castro Marshall Owens Harrison Fernandez McDonald
Woods Washington Kennedy Wells Vargas Henry Chen Freeman Webb Tucker Guzman Burns Crawford Olson
Simpson Porter Hunter Gordon Mendez Silva Shaw Snyder Mason Dixon Munoz Hunt Hicks Holmes Palmer""".split()
COMPANY_WORDS = """Meridian Calvert Northgate Ironwood Cascade Sterling Beacon Emberline Halcyon Vantage Ridgeline
Corvid Ashford Brightwater Keystone Larkspur Tidewater Summit Harbor Crestline Fairmont Oakridge Silverton""".split()

# nickname groups: every member maps to the same canonical person-key
NICKS = [
    "robert rob bob bobby", "william will bill billy", "james jim jimmy", "michael mike",
    "jeffrey jeff", "david dave", "thomas tom tommy", "richard rick dick rich", "christopher chris",
    "steven stephen steve", "susan sue susie", "elizabeth liz beth betsy", "katherine kathy kate kay",
    "jennifer jen jenny", "charles chuck charlie", "kenneth ken kenny", "edward ed eddie ted",
    "daniel dan danny", "matthew matt", "anthony tony", "andrew andy drew", "gregory greg",
    "patricia pat patty", "patrick pat", "samuel sam", "samantha sam", "joseph joe joey",
    "benjamin ben", "nicholas nick", "alexander alex", "timothy tim", "ronald ron", "donald don",
    "lawrence larry", "gerald jerry", "vincent vince", "margaret meg peggy", "deborah debbie deb",
    "rebecca becky", "kimberly kim", "cynthia cindy", "pamela pam", "barbara barb",
    "raymond ray", "douglas doug", "leonard len", "frederick fred", "theodore ted", "philip phil",
    "kathleen kathy", "christine chris", "joshua josh", "jonathan jon", "nathan nate",
]
# The `nicknames` package is the primary source when installed; the table above is the fallback.
CANON = {}
for grp in NICKS:
    ws = grp.split()
    for w in ws:
        CANON.setdefault(w, set()).add(ws[0])
_NICK = None
try:
    from nicknames import NickNamer
    _NICK = NickNamer()
except Exception:
    pass

# first names that are also ordinary English words: never replaced by the GLOBAL bare-first-name pass
RISKY_FIRST = set("""mark bill will may june art rich pat grant chase frank grace hope guy jack joy lance
max miles ray rob rose sandy sue wade warren chuck dick don ed gene cliff cole dean drew duke earl flint
glen hank lee rusty skip tanner wes woody buck bob kay kim jay ken van ward hunter carol chip curt dawn
faith gay herb jean jimmy jo kit lane lot mac major marc matt mike nick pearl penny pete randy reed ruby
sky tab teddy terry tom tony victor wells win wolf""".split())

# Local parts of system, list and role addresses: never a person.
NOT_NAME = set("""enron ect ena ees ebs eol announcements announcement team admin administration administrator
technology chairman office mail noreply no reply help desk support info information news list group
communications communication development corp corporate global services service houston na hou legal
outlook exchange system notification notifications bulletin daily weekly report reports hr payroll
benefits security facilities travel finance accounting risk trading energy power gas marketing
america north europe london calgary portland sales credit research center centre general public
relations investor investors capital markets broadband wholesale retail online mailbox postmaster
webmaster root""".split())

# Bare-surname replacement fired on these and produced "Legal Destry" and "Houston, Rori".
NOT_SURNAME = set("""alabama alaska arizona arkansas california colorado connecticut delaware florida
georgia hawaii idaho illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts
michigan minnesota mississippi missouri montana nebraska nevada hampshire jersey mexico york carolina
dakota ohio oklahoma oregon pennsylvania rhode island tennessee texas utah vermont virginia washington
wisconsin wyoming columbia
houston dallas austin denver chicago boston portland seattle atlanta phoenix calgary london tokyo
omaha tulsa vegas miami tampa detroit cleveland orleans francisco angeles diego antonio worth
philadelphia baltimore pittsburgh minneapolis sacramento vancouver toronto montreal
department division group corporation corp company services service center centre office building
floor suite room street avenue road drive lane boulevard court place circle parkway terrace highway
university college institute school hospital center bank energy gas power trading legal finance
january february march april june july august september october november december monday tuesday
wednesday thursday friday saturday sunday""".split())

STOP_EN = set("""was or the and for with from this that will can may not are you our your has have been
but all any new per re fw fwd subject sent date time please thanks thank regards best dear hi hello
yes no ok okay sure call meeting fyi good great sorry sincerely cheers do done note noted
attached see below above here there what when where which who why how would could should also just
into onto over under after before about between within without during until while because since""".split())

COMPANY_SRC = ["Enron", "ENRON", "EnronOnline", "Enron Online", "EOL", "ECT", "ENA", "EES", "EBS",
               "Enron North America", "Enron Wholesale", "Enron Corp", "Transwestern", "Northern Natural",
               "Portland General", "Azurix", "Dynegy", "Reliant", "El Paso", "Calpine", "Williams",
               "Duke Energy", "PG&E", "Edison", "Sempra", "Mirant", "Aquila", "TXU", "Entergy"]

# Contact details: a phone or a street address identifies a person on its own. Each real value maps to
# one fake value for the whole run.
PHONE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(\d{3}\)\s*|\d{3}[-.\s])\d{3}[-.\s]\d{4}\b")
ZIP4 = re.compile(r"(?<!\d)(\d{5})-(\d{4})(?!\d)")
# A bare 5-digit number is a ZIP only right after a US state abbreviation.
CITY_ST_ZIP = re.compile(r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})\s*,\s*"
                         r"(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|"
                         r"MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|"
                         r"WY|DC)\s+(\d{5})(?!\d)")
# same thing with the state spelled out ("Houston, Texas 77002")
STATE_FULL = {"alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA","colorado":"CO",
 "connecticut":"CT","delaware":"DE","florida":"FL","georgia":"GA","hawaii":"HI","idaho":"ID","illinois":"IL",
 "indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY","louisiana":"LA","maine":"ME","maryland":"MD",
 "massachusetts":"MA","michigan":"MI","minnesota":"MN","mississippi":"MS","missouri":"MO","montana":"MT",
 "nebraska":"NE","nevada":"NV","new hampshire":"NH","new jersey":"NJ","new mexico":"NM","new york":"NY",
 "north carolina":"NC","north dakota":"ND","ohio":"OH","oklahoma":"OK","oregon":"OR","pennsylvania":"PA",
 "rhode island":"RI","south carolina":"SC","south dakota":"SD","tennessee":"TN","texas":"TX","utah":"UT",
 "vermont":"VT","virginia":"VA","washington":"WA","west virginia":"WV","wisconsin":"WI","wyoming":"WY",
 "district of columbia":"DC"}
ST_FULL_OF = {}
CITY_STFULL_ZIP = re.compile(r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,3})\s*,\s*("
                             + "|".join(sorted(STATE_FULL, key=len, reverse=True)) + r")\s+(\d{5})(?!\d)", re.I)
ST_FULL_OF.update({v: k.title() for k, v in STATE_FULL.items()})
STREET = re.compile(r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3}\s+"
                    r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Blvd|Boulevard|Ct|Court|Way|Pl|"
                    r"Place|Cir|Circle|Pkwy|Parkway|Ter|Terrace|Hwy|Highway|Frwy|Freeway|Expy|"
                    r"Expressway|Trl|Trail|Loop|Sq|Square|Row|Path|Walk|Bend|Ridge|Creek)\b\.?", re.I)
PO_BOX = re.compile(r"\bP\.?\s?O\.?\s*Box\s+\d+\b", re.I)
SUITE = re.compile(r"\b(?:Ste|Suite|Apt|Apartment|Unit|Rm|Room|Fl|Floor)\.?\s*#?\s*\d{1,5}\b", re.I)
SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
STREET_WORDS = """Aspen Birch Cedar Larkin Maple Juniper Quarry Bellamy Foxglove Harrow Kestrel Linden
Marlow Nightingale Ormond Pennine Quinlan Rosemont Sable Thornbury Umber Verity Wexford Yarrow Alder
Brookline Camden Dunmore Elmwood Fairhaven Glenmoor Holloway Ivybridge""".split()
STREET_TYPES = "St Ave Rd Dr Ln Blvd Ct Way Pl Cir".split()

WORD = r"[A-Za-z][A-Za-z'\-]*"
LOTUS = re.compile(r"\b([A-Z][a-z]+(?: [A-Z]\.?)? [A-Z][A-Za-z'\-]+)(/[A-Z]{2,4}/[A-Z]{2,4}(?:@[A-Z]+)?)")
HDR = re.compile(r"(?im)^\s*(?:from|to|cc|bcc|sent by)\s*:\s*(.+)$")
LASTFIRST = re.compile(r'"?\b([A-Z][a-z]+), ([A-Z][a-z]+)\b"?')
EMAIL = re.compile(r"\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
BIGRAM = re.compile(r"\b([A-Z][a-z]{2,})(?: [A-Z]\.?)? ([A-Z][a-z]{2,})\b")


def canon_first(f: str) -> str:
    f = f.lower()
    if _NICK is not None:
        try:
            c = _NICK.canonicals_of(f)
            if c:
                return sorted(c)[0]
        except Exception:
            pass
    c = CANON.get(f)
    return sorted(c)[0] if c else f


def nicks_of(f: str) -> set:
    """Every short form of a first name, so a person is matched however they sign off."""
    out = {f.lower()}
    if _NICK is not None:
        try:
            out |= {n.lower() for n in _NICK.nicknames_of(f.lower())}
            for c in _NICK.canonicals_of(f.lower()):
                out.add(c.lower())
                out |= {n.lower() for n in _NICK.nicknames_of(c.lower())}
        except Exception:
            pass
    for alt in CANON.get(f.lower(), ()):
        out.add(alt)
        out |= {w for g in NICKS for w in g.split() if g.split()[0] == alt}
    return out


def person_key(first: str, last: str) -> tuple[str, str]:
    return canon_first(first), last.lower().replace("'", "").replace("-", "")


# ----------------------------------------------------------------------------------------------- registry
class Registry:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.person: dict[tuple, dict] = {}            # key -> {first, last, fake_first, fake_last, forms}
        self.addr2key: dict[str, tuple] = {}
        self.known_first: set[str] = set()
        self.known_last: set[str] = set()
        self.first_fake: dict[str, str] = {}           # global bare-first-name map (canonical -> fake)
        self.company: dict[str, str] = {}
        self.domain: dict[str, str] = {}
        self._used = set()
        self._place_used = set()
        self.remap_cities = False
        self.short2key: dict[str, tuple] = {}          # flast / firstl / last -> key, built once
        self.first_re = None                            # compiled global bare-first-name pattern
        self.contact: dict[str, str] = {}               # real contact value -> fake, stable per run
        self.seen_contact: set[str] = set()             # the real values, for the fail-closed rescan
        self.zip_re = None                              # known ZIPs, compiled once after harvesting
        self.org_re = None                              # company words taken from mapped domains
        self.city_zips: dict[tuple, list] = {}          # (city, ST) -> real ZIPs there, from GeoNames
        self.zip_city: dict[str, tuple] = {}            # real ZIP -> (city, ST)
        self.zip_seen: dict[str, tuple] = {}            # real ZIP found in the corpus -> (city, ST)
        self.place: dict[tuple, tuple] = {}             # real (city, ST) -> fake (city, ST)
        self.city_re = None                             # learned city names, for bare prose mentions

    pool_first: list[str] = []
    pool_last: list[str] = []

    def _fresh(self, real: tuple[str, str] | None = None):
        """A pseudonym that is unused, is not a real person in the registry, and shares neither half with the person it replaces."""
        PF = self.pool_first or FIRST
        PL = self.pool_last or LAST
        rf = canon_first(real[0]) if real else None
        rl = real[1].lower() if real else None
        for _ in range(10000):
            f, l = self.rng.choice(PF), self.rng.choice(PL)
            if (f, l) in self._used or person_key(f, l) in self.person:
                continue
            if rf is not None and (canon_first(f) == rf or l.lower() == rl):
                continue
            self._used.add((f, l))
            return f, l
        raise RuntimeError("name pool exhausted: cannot draw a pseudonym sharing no half with the real name")

    def assign(self):
        """Second phase: pseudonyms are drawn only after every real identity is known, so the
        collision check in _fresh sees the complete registry."""
        for k in sorted(self.person):
            p = self.person[k]
            if p["fake_first"] is None:
                p["fake_first"], p["fake_last"] = self._fresh((p["first"], p["last"]))
        clash = [f"{p['first']} {p['last']} -> {p['fake_first']} {p['fake_last']}"
                 for p in self.person.values()
                 if person_key(p["fake_first"], p["fake_last"]) in self.person
                 or canon_first(p["fake_first"]) == canon_first(p["first"])
                 or p["fake_last"].lower() == p["last"].lower()]
        assert not clash, f"pseudonym reuses a real identity: {clash[:5]}"

    def add(self, first: str, last: str, addr: str | None = None) -> tuple:
        if not first or not last or len(last) < 2:
            return None
        if first.lower() in NOT_NAME or last.lower() in NOT_NAME:
            return None
        if first.lower() in STOP_EN or last.lower() in STOP_EN or len(first) < 2:
            return None
        if first.lower() in NOT_SURNAME or last.lower() in NOT_SURNAME:
            return None
        k = person_key(first, last)
        p = self.person.get(k)
        if p is None:
            p = self.person[k] = {"first": first, "last": last, "fake_first": None, "fake_last": None,
                                  "firsts": set(), "addrs": set()}
        fl, fi = first.lower()[0] + last.lower(), first.lower() + last.lower()[0]
        self.short2key.setdefault(fl, k); self.short2key.setdefault(fi, k)
        self.short2key.setdefault(last.lower(), k)
        p["firsts"] |= nicks_of(first)
        if addr:
            p["addrs"].add(addr.lower())
            self.addr2key[addr.lower()] = k
        self.known_first.add(first.lower())
        self.known_last.add(last.lower())
        return k

    def build_first_map(self):
        """(Re)build the global bare-first-name map and its compiled pattern. Must run after any
        pseudonym is drawn or redrawn, since it maps a canonical real first name -> a fake first."""
        self.first_fake = {}
        for k, p in self.person.items():
            c = k[0]
            if c not in self.first_fake and len(c) >= 4 and c not in RISKY_FIRST:
                self.first_fake[c] = p["fake_first"]
        alts = sorted({w for c in self.first_fake
                       for w in ([c] + [n for g in NICKS for n in g.split() if g.split()[0] == c])
                       if len(w) >= 4 and w not in RISKY_FIRST}, key=len, reverse=True)
        self.first_re = re.compile(r"\b(" + "|".join(re.escape(w.capitalize()) for w in alts) + r")\b") if alts else None

    def redraw(self, first: str, last: str) -> int:
        """Give a new pseudonym to every person whose fake name supplied either half of `first last`.
        Used when a real name is formed ACROSS a boundary, a pseudonym's first name landing beside a
        surname written by a different rule, which the per-pseudonym check in _fresh cannot see."""
        n = 0
        for p in self.person.values():
            if p["fake_first"].lower() == first.lower() or p["fake_last"].lower() == last.lower():
                self._used.discard((p["fake_first"], p["fake_last"]))
                p["fake_first"], p["fake_last"] = self._fresh((p["first"], p["last"]))
                n += 1
        return n

    def fake_phone(self, real: str) -> str:
        """Keep the shape, (713) 853-6460 stays parenthesised, 713-853-6460 stays hyphenated, so the
        text still reads like a signature block. 555 is the reserved fictional exchange."""
        if real not in self.contact:
            self.seen_contact.add(real)
            d = f"{self.rng.randint(100,999)}{self.rng.randint(1000,9999)}"
            self.contact[real] = (f"(555) {d[:3]}-{d[3:]}" if real.lstrip("+1 ").startswith("(")
                                  else f"555-{d[:3]}-{d[3:]}")
        return self.contact[real]

    def fake_street(self, real: str) -> str:
        if real not in self.contact:
            self.seen_contact.add(real)
            self.contact[real] = (f"{self.rng.randint(1,9899)} {self.rng.choice(STREET_WORDS)} "
                                  f"{self.rng.choice(STREET_TYPES)}")
        return self.contact[real]

    def load_geo(self, path: Path):
        """GeoNames US postal codes: ZIP, city, state. Lets a replacement ZIP stay valid for the city
        it sits next to, replacing 77002 with a random five digits gives "Houston, Texas 63282", which
        is not a Houston ZIP and is spottable by anyone who checks."""
        if not path.exists():
            return
        for line in path.read_text(errors="ignore").splitlines():
            f = line.split("\t")
            if len(f) > 4 and f[1].isdigit():
                key = (f[2].strip().lower(), f[4].strip().upper())
                self.city_zips.setdefault(key, []).append(f[1])
                self.zip_city.setdefault(f[1], key)

    def fake_place(self, city: str, st: str) -> tuple:
        """City and state are kept; the ZIP moves to another ZIP of the same city. --remap-cities also moves the city, matched on size."""
        key = (city.strip().lower(), st.strip().upper())
        if not self.remap_cities:
            return key
        if key not in self.place:
            n = len(self.city_zips.get(key, []) or [1])
            lo, hi = n / 3, n * 3
            band = [k for k, v in self.city_zips.items()
                    if lo <= len(v) <= hi and k != key and k not in self._place_used]
            pick = self.rng.choice(sorted(band)) if band else key
            self._place_used.add(pick)
            self.place[key] = pick
        return self.place[key]

    def note_zip(self, real: str, city: str | None = None, st: str | None = None):
        """Harvest only: record that this ZIP is real and where it sits. Replacements are chosen later,
        once every real ZIP is known, so a replacement can never be another real ZIP from the corpus."""
        self.seen_contact.add(real)
        self.zip_seen[real] = ((city.strip().lower(), st.strip().upper()) if city and st
                               else self.zip_city.get(real.split("-")[0]))

    def assign_zips(self):
        taken = {z.split("-")[0] for z in self.zip_seen}
        for real, key in self.zip_seen.items():
            base = real.split("-")[0]
            dest = self.fake_place(*key) if key else None          # ZIP follows the city it moved to
            pool = [z for z in (self.city_zips.get(dest or ("", "")) or []) if z not in taken]
            if not pool and dest:
                pool = [z for k, v in self.city_zips.items() if k[1] == dest[1]
                        for z in v if z not in taken]
            new = self.rng.choice(pool) if pool else f"{self.rng.randint(10000, 99999)}"
            self.contact[real] = f"{new}-{self.rng.randint(1000, 9999)}" if "-" in real else new

    def fake_zip(self, real: str, city: str | None = None, st: str | None = None) -> str:
        """A ZIP is replaced by ANOTHER REAL ZIP of the same city where the city is known, so the
        address stays internally consistent; the specific building is what needed hiding, not the town.
        Falls back to any ZIP of the same state, then to random digits."""
        if real in self.contact:
            return self.contact[real]
        self.seen_contact.add(real)
        base = real.split("-")[0]
        key = (city.strip().lower(), st.strip().upper()) if city and st else self.zip_city.get(base)
        pool = self.city_zips.get(key or ("", "")) or []
        pool = [z for z in pool if z != base]
        if not pool and key:                              # nothing else in that town: widen to the state
            pool = [z for k, v in self.city_zips.items() if k[1] == key[1] for z in v if z != base]
        new = self.rng.choice(pool) if pool else f"{self.rng.randint(10000, 99999)}"
        self.contact[real] = f"{new}-{self.rng.randint(1000, 9999)}" if "-" in real else new
        return self.contact[real]

    def fake_addr(self, k: tuple, real: str) -> str:
        """Rebuild the address in the same shape as the original: first.last, flast, first_last or a bare word."""
        local, dom = real.split("@", 1)
        p = self.person[k]
        f, l = p["fake_first"].lower(), p["fake_last"].lower()
        return f"{self._shape(local.lower(), f, l)}@{self.fake_domain(dom.lower())}"

    @staticmethod
    def _shape(local: str, f: str, l: str) -> str:
        if re.fullmatch(r"[a-z]+\.[a-z]\.[a-z]+", local):   # first.m.last
            return f"{f}.{l[0]}.{l}"
        if re.fullmatch(r"[a-z]+\.[a-z]+", local):           # first.last
            return f"{f}.{l}"
        if re.fullmatch(r"[a-z]+_[a-z]+", local):            # first_last
            return f"{f}_{l}"
        if re.fullmatch(r"[a-z]\.[a-z]+", local):            # f.last
            return f"{f[0]}.{l}"
        m = re.fullmatch(r"([a-z])([a-z]{3,})", local)       # flast, possibly truncated
        if m:
            return f"{f[0]}{l[:len(m.group(2))]}"
        if re.fullmatch(r"[a-z]+[0-9]+", local):             # word+digits
            return f"{l}{local[len(local.rstrip('0123456789')):]}"
        return l if len(local) <= len(l) + 2 else f"{f}{l}"  # single word / anything else

    def fake_unknown_addr(self, real: str) -> str:
        """An address that resolves to nobody still gets a plausible person-shaped local part, stable
        for the run, rather than a uNNN placeholder."""
        local, dom = real.split("@", 1)
        key = real.lower()
        if key not in self.contact:
            self.seen_contact.add(key)
            f, l = self._fresh()
            self.contact[key] = f"{self._shape(local.lower(), f.lower(), l.lower())}@{self.fake_domain(dom.lower())}"
        return self.contact[key]

    def fake_domain(self, dom: str) -> str:
        dom = dom.lower()
        if dom not in self.domain:
            parts = dom.split(".")
            tld = parts[-1]
            if dom.endswith("enron.com") or dom == "ect.com":
                base = self.company_token("Enron").lower()
            else:
                base = self.rng.choice(COMPANY_WORDS).lower() + str(self.rng.randint(2, 99))
            self.domain[dom] = f"{base}.{tld}"
        return self.domain[dom]

    def company_token(self, src: str) -> str:
        key = src.lower()
        if key not in self.company:
            enron_family = {"enron", "ect", "ena", "ees", "ebs", "eol", "enrononline", "enron online",
                            "enron north america", "enron wholesale", "enron corp"}
            if key in enron_family:
                base = self.company.get("enron") or self.rng.choice(COMPANY_WORDS)
                self.company["enron"] = base
                self.company[key] = {"ect": base[:3].upper(), "ena": base[:2].upper() + "N",
                                     "ees": base[:2].upper() + "S", "ebs": base[:2].upper() + "B",
                                     "eol": base[:2].upper() + "OL", "enrononline": base + "Online",
                                     "enron online": base + " Online",
                                     "enron north america": base + " North America",
                                     "enron wholesale": base + " Wholesale",
                                     "enron corp": base + " Corp"}.get(key, base)
            else:
                # if this word is a domain base we already mapped, reuse that fake base word
                reuse = next((v.split(".")[0] for d, v in self.domain.items()
                              if d.split(".")[-2:-1] == [key]), None)
                self.company[key] = (reuse.capitalize() if reuse else
                                     self.rng.choice([w for w in COMPANY_WORDS
                                                      if w.lower() not in self.company.values()] or COMPANY_WORDS))
        return self.company[key]

    def resolve_local(self, local: str, dom: str) -> tuple | None:
        """Map an address local-part to a person: first.last, first.m.last, flast, first_last, firstl."""
        a = f"{local}@{dom}".lower()
        if a in self.addr2key:
            return self.addr2key[a]
        l = local.lower()
        m = re.fullmatch(r"([a-z]+)[._]([a-z]\.?[._])?([a-z]+)", l)
        if m:
            k = person_key(m.group(1), m.group(3))
            if k in self.person:
                return k
        if l in self.short2key:
            return self.short2key[l]
        # Truncated logins (dperlin, jdasovic) are the commonest shape: match an initial plus a surname prefix, longest first.
        m = re.fullmatch(r"([a-z])([a-z]{3,})", l)
        if m:
            ini, stem = m.group(1), m.group(2)
            best = None
            for k, p in self.person.items():
                if p["first"].lower().startswith(ini) and p["last"].lower().startswith(stem):
                    if best is None or len(self.person[best]["last"]) > len(p["last"]):
                        best = k
            if best:
                return best
        return None


# ----------------------------------------------------------------------------------------------- harvest
def load_name_pool(reg: Registry, mode: str):
    """Where pseudonyms come from: corpus (address-book names recombined) or census (SSA first names x Census 2010 surnames)."""
    if mode == "census":
        firsts, lasts = set(), set()
        flat = Path("data/names/ssa_atleast100.txt")
        if flat.exists():
            firsts.update(n.strip() for n in flat.read_text().splitlines() if n.strip().isalpha() and len(n.strip()) >= 3)
        for f in sorted(Path("data/names/ssa").glob("yob*.txt")):
            yr = int(f.stem[3:])
            if 1940 <= yr <= 1985:
                for line in f.read_text().splitlines():
                    n, _sex, c = line.split(",")
                    if int(c) >= 200:
                        firsts.add(n)
        for f in Path("data/names/census").glob("*.csv"):
            for i, line in enumerate(f.read_text(errors="ignore").splitlines()):
                if i == 0:
                    continue
                n = line.split(",")[0].strip()
                if n.isalpha() and len(n) >= 3:
                    lasts.add(n.capitalize())
        cf = sorted({p["first"].capitalize() for p in reg.person.values() if len(p["first"]) >= 3})
        cl = sorted({p["last"].capitalize() for p in reg.person.values() if len(p["last"]) >= 3})
        # each half degrades independently: Census surnames without SSA firsts is still a bigger pool
        reg.pool_first = sorted(firsts) if firsts else cf
        reg.pool_last = sorted(lasts) if lasts else cl
        if not firsts:
            print("  SSA first names not found under data/names/ssa — using corpus first names")
        if not lasts:
            print("  Census surnames not found under data/names/census — using corpus surnames")
        return
    firsts = sorted({p["first"].capitalize() for p in reg.person.values() if len(p["first"]) >= 3})
    lasts = sorted({p["last"].capitalize() for p in reg.person.values() if len(p["last"]) >= 3})
    reg.pool_first, reg.pool_last = firsts, lasts


GEONAMES = Path("data/names/uszip/US.txt")


def load_name_vocab(reg: Registry):
    reg.load_geo(GEONAMES)
    """Seed the first/last name vocabulary from the public lists, so a First-Last bigram is recognised
    as a person even when neither half is an Enron employee. The Enron address book alone found 1,013
    people in the sample; SSA x Census finds 1,490 — the extra 650 are outside contacts, counterparty
    staff and petition signers, exactly the people the address book cannot know about."""
    ssa = Path("data/names/ssa_atleast100.txt")
    if ssa.exists():
        reg.known_first |= {n.strip().lower() for n in ssa.read_text().splitlines()
                            if n.strip().isalpha() and len(n.strip()) >= 3}
    for f in Path("data/names/census").glob("*.csv"):
        for i, line in enumerate(f.read_text(errors="ignore").splitlines()):
            if i:
                n = line.split(",")[0].strip().lower()
                if n.isalpha() and len(n) >= 3:
                    reg.known_last.add(n)
    reg.known_first -= NOT_SURNAME | STOP_EN | NOT_NAME
    reg.known_last -= NOT_SURNAME | STOP_EN | NOT_NAME


def harvest(rows: list[dict], reg: Registry, name_pool: str = "corpus"):
    load_name_vocab(reg)
    if ADDR_BOOK.exists():
        for r in csv.DictReader(ADDR_BOOK.open()):
            a = (r.get("sender") or "").strip().lower()
            m = re.fullmatch(r"([a-z]+)\.(?:[a-z]\.)?([a-z]+)@enron\.com", a)
            if m:
                reg.add(m.group(1).capitalize(), m.group(2).capitalize(), a)
    for r in rows:
        a = (r.get("from") or "").lower()
        m = re.fullmatch(r"([a-z]+)\.(?:[a-z]\.)?([a-z]+)@([a-z0-9.\-]+)", a)
        if m:
            reg.add(m.group(1).capitalize(), m.group(2).capitalize(), a)
    for r in rows:
        for field in ("subject", "body"):
            t = r.get(field) or ""
            for name, _ in LOTUS.findall(t):
                parts = name.replace(".", "").split()
                reg.add(parts[0], parts[-1])
            for last, first in LASTFIRST.findall(t):
                reg.add(first, last)
            for line in HDR.findall(t):
                for name, _ in LOTUS.findall(line):
                    parts = name.replace(".", "").split()
                    reg.add(parts[0], parts[-1])
                for f, l in BIGRAM.findall(line):
                    if f.lower() in reg.known_first and l.lower() in reg.known_last:
                        reg.add(f, l)
                for local, dom in EMAIL.findall(line):
                    m = re.fullmatch(r"([a-z]+)\.(?:[a-z]\.)?([a-z]+)", local.lower())
                    if m:
                        reg.add(m.group(1).capitalize(), m.group(2).capitalize(), f"{local}@{dom}")
    # ZIPs are learned where a state abbreviation makes them certain, then replaced everywhere they occur.
    for r in rows:
        for field in ("subject", "body"):
            for city, st, z in CITY_ST_ZIP.findall(r.get(field) or ""):
                reg.note_zip(z, city, st)
            for city, st, z in CITY_STFULL_ZIP.findall(r.get(field) or ""):
                reg.note_zip(z, city, STATE_FULL[st.lower()])
            for z in ZIP4.findall(r.get(field) or ""):
                reg.note_zip("-".join(z) if isinstance(z, tuple) else z)

    # bigrams anywhere in the body, accepted only when BOTH halves are already known names
    for r in rows:
        for f, l in BIGRAM.findall(r.get("body") or ""):
            if f.lower() in reg.known_first and l.lower() in reg.known_last:
                reg.add(f, l)
    # every domain seen anywhere becomes a company word candidate
    orgs = set()
    for r in rows:
        for field in ("from", "subject", "body"):
            for _l, dom in EMAIL.findall(r.get(field) or ""):
                base = dom.lower().split(".")[-2] if dom.count(".") >= 1 else dom.lower()
                if len(base) >= 4 and base.isalpha() and base not in STOP_EN | NOT_SURNAME:
                    orgs.add(base)
                    reg.fake_domain(dom.lower())        # register so name and domain share a word
    orgs -= {"enron"}                                   # handled by the explicit Enron family rules
    if orgs:
        reg.org_re = re.compile(r"(?<![A-Za-z])(" + "|".join(sorted(map(re.escape, orgs), key=len, reverse=True))
                                + r")(?![A-Za-z])", re.I)
    print(f"  company words from domains: {len(orgs):,}")

    reg.assign_zips()                                   # all real ZIPs known -> choose replacements
    # Bare city mentions in prose, only for cities seen in an address and not also a state or a common surname.
    reg.city_map = {}
    for (c, st), (c2, _s2) in (reg.place.items() if reg.remap_cities else {}.items()):
        if c in NOT_SURNAME or c in reg.known_last or len(c) < 5:
            continue
        reg.city_map[c] = c2.title()
    if reg.city_map:
        reg.city_re = re.compile(r"(?<![A-Za-z])(" + "|".join(sorted(map(re.escape, reg.city_map),
                                 key=len, reverse=True)) + r")(?![A-Za-z])", re.I)
    print(f"  places remapped: {len(reg.place):,}   bare city mentions rewritten: {len(reg.city_map):,}")
    zips = sorted((z for z in reg.contact if z.isdigit() and len(z) == 5), key=len, reverse=True)
    if zips:
        reg.zip_re = re.compile(r"(?<!\d)(" + "|".join(zips) + r")(?!\d)")
    load_name_pool(reg, name_pool)                        # registry complete -> pool can be built from it
    reg.assign()                                          # pseudonyms only now: registry is complete
    reg.build_first_map()


# ----------------------------------------------------------------------------------------------- rewrite
def _case_like(src: str, repl: str) -> str:
    if src.isupper():
        return repl.upper()
    if src.islower():
        return repl.lower()
    return repl


def people_in_email(text: str, sender: str, reg: Registry) -> set[tuple]:
    """Who is established in THIS email, found by looking mentions UP in the registry, never by
    scanning the registry against the text (20k people x 2k emails would be the slow way)."""
    keys = set()
    a = (sender or "").lower()
    if a in reg.addr2key:
        keys.add(reg.addr2key[a])
    for local, dom in EMAIL.findall(text):
        k = reg.resolve_local(local, dom)
        if k:
            keys.add(k)
    for name, _ in LOTUS.findall(text):
        parts = name.replace(".", "").split()
        k = person_key(parts[0], parts[-1])
        if k in reg.person:
            keys.add(k)
    for last, first in LASTFIRST.findall(text):
        k = person_key(first, last)
        if k in reg.person:
            keys.add(k)
    # any-case adjacent word pairs: catches "Kay Mann", "KAY MANN", "kay mann", "Kay A. Mann"
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    for i in range(len(toks) - 1):
        w1, w2 = toks[i], toks[i + 1]
        k = person_key(w1, w2)
        if k in reg.person:
            keys.add(k)
        elif i + 2 < len(toks) and len(w2) <= 2:          # middle initial
            k = person_key(w1, toks[i + 2])
            if k in reg.person:
                keys.add(k)
    return keys


def rewrite(text: str, sender: str, reg: Registry) -> str:
    """Every substitution writes a letterless placeholder; the real strings go in only at the end.
    Without this, a later pass re-matches an earlier pass's output, pseudonym first names overlap
    real first names, so the global first-name pass was rewriting pseudonyms into other pseudonyms."""
    if not text:
        return text
    scope = people_in_email(text, sender, reg)
    ph: list[str] = []

    def hold(final: str) -> str:
        ph.append(final)
        return f"\x02{len(ph) - 1}\x03"

    # 0. contact details first: a street or a phone can contain capitalised words.
    text = SSN.sub(lambda m: hold("000-00-0000"), text)
    text = STREET.sub(lambda m: hold(reg.fake_street(m.group(0))), text)
    text = PO_BOX.sub(lambda m: hold(f"PO Box {reg.rng.randint(100, 99999)}"), text)
    text = ZIP4.sub(lambda m: hold(reg.fake_zip(m.group(0))), text)
    def _place(city, st_txt, st_code, zipc):
        c2, s2 = reg.fake_place(city, st_code)
        st_out = ST_FULL_OF.get(s2, s2) if st_txt.lower() in STATE_FULL else s2  # keep TX vs Texas spelling
        return hold(f"{c2.title()}, {st_out} {reg.fake_zip(zipc, city, st_code)}")
    text = CITY_ST_ZIP.sub(lambda m: _place(m.group(1), m.group(2), m.group(2), m.group(3)), text)
    text = CITY_STFULL_ZIP.sub(
        lambda m: _place(m.group(1), m.group(2), STATE_FULL[m.group(2).lower()], m.group(3)), text)
    if reg.city_re is not None:                       # bare mentions, so prose and address agree
        text = reg.city_re.sub(lambda m: hold(_case_like(m.group(0), reg.city_map[m.group(0).lower()])), text)
    if reg.zip_re is not None:
        text = reg.zip_re.sub(lambda m: hold(reg.contact[m.group(0)]), text)
    text = SUITE.sub(lambda m: hold(re.sub(r"\d+", str(reg.rng.randint(1, 999)), m.group(0))), text)
    text = PHONE.sub(lambda m: hold(reg.fake_phone(m.group(0))), text)

    # 1. addresses
    def _addr(m):
        local, dom = m.group(1), m.group(2)
        k = reg.resolve_local(local, dom)
        if k:
            return hold(reg.fake_addr(k, f"{local}@{dom}"))
        return hold(reg.fake_unknown_addr(f"{local}@{dom}"))
    text = EMAIL.sub(_addr, text)

    # 2-4. full-name forms, only for the people established in this email (longest surname first)
    for k in sorted(scope, key=lambda kk: -len(reg.person[kk]["last"])):
        p = reg.person[k]
        last = re.escape(p["last"])
        firsts = "|".join(re.escape(f) for f in sorted(p["firsts"], key=len, reverse=True))
        fake_full = f"{p['fake_first']} {p['fake_last']}"
        L, R = r"(?<![A-Za-z])", r"(?![A-Za-z])"
        text = re.sub(rf"{L}(?:{firsts})(?:[ _.]+[A-Za-z]\.?)?[ _.]+{last}{R}",
                      lambda m: hold(_case_like(m.group(0), fake_full)), text, flags=re.I)
        text = re.sub(rf"{L}{last},\s*(?:{firsts}){R}",
                      lambda m: hold(_case_like(m.group(0), f"{p['fake_last']}, {p['fake_first']}")),
                      text, flags=re.I)

    # 5-6. bare surname / first name for people established in this email
    for k in scope:
        p = reg.person[k]
        text = re.sub(rf"(?<![A-Za-z]){re.escape(p['last'])}(?![A-Za-z])",
                      lambda m: hold(_case_like(m.group(0), p["fake_last"])), text)
        for f in p["firsts"]:
            risky = len(f) < 4 or f in RISKY_FIRST
            pat = re.escape(f.capitalize()) if risky else re.escape(f)
            text = re.sub(rf"(?<![A-Za-z]){pat}(?![A-Za-z])",
                          lambda m: hold(_case_like(m.group(0), p["fake_first"])),
                          text, flags=0 if risky else re.I)

    # 6b. global bare-first-name pass: unambiguous names only, capitalised only
    if reg.first_re is not None:
        def _first(m):
            w = m.group(0)
            fk = reg.first_fake.get(canon_first(w))
            return hold(fk) if fk else w
        text = reg.first_re.sub(_first, text)

    # 7. companies: multi-word forms first, then "enron" as a substring. Domain-derived names map to the same
    # base word as the domain.
    if reg.org_re is not None:
        text = reg.org_re.sub(lambda m: hold(_case_like(m.group(0), reg.company_token(m.group(0)))), text)

    for src in sorted(COMPANY_SRC, key=len, reverse=True):
        if "enron" in src.lower():
            continue
        text = re.sub(rf"\b{re.escape(src)}\b",
                      lambda m, s_=src: hold(_case_like(m.group(0), reg.company_token(s_))), text, flags=re.I)
    for src in ("Enron North America", "Enron Wholesale", "Enron Online", "EnronOnline", "Enron Corp"):
        text = re.sub(re.escape(src), lambda m, s_=src: hold(_case_like(m.group(0), reg.company_token(s_))),
                      text, flags=re.I)
    text = re.sub(r"enron", lambda m: hold(_case_like(m.group(0), reg.company_token("Enron"))), text, flags=re.I)
    for src in ("ECT", "ENA", "EES", "EBS", "EOL"):
        text = re.sub(rf"\b{src}\b", lambda m, s_=src: hold(reg.company_token(s_)), text)

    return re.sub(r"\x02(\d+)\x03", lambda m: ph[int(m.group(1))], text)


# ----------------------------------------------------------------------------------------------- verify
def leaks(rows: list[dict], reg: Registry) -> list[str]:
    """Fail-closed check, done by lookup: every address and every adjacent word pair in the output is
    looked up in the registry; a hit means a real identity survived."""
    found = []
    for r in rows:
        blob = " ".join(str(r.get(f) or "") for f in ("from", "subject", "body", "own_body"))
        for local, dom in EMAIL.findall(blob):
            if f"{local}@{dom}".lower() in reg.addr2key:
                found.append(f"{r['email_id']}: address {local}@{dom}")
                break
        toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", blob)
        for i in range(len(toks) - 1):
            if toks[i + 1].isupper() and len(toks[i + 1]) <= 4:      # /HOU/ECT routing, not a name
                continue
            k = person_key(toks[i], toks[i + 1])
            if k in reg.person:
                found.append(f"{r['email_id']}: name {toks[i]} {toks[i+1]}")
                break
        if re.search(r"\benron\b", blob, re.I):
            found.append(f"{r['email_id']}: token enron")
        # A ZIP is matched on digit boundaries, so ids like DS51002180 are not flagged.
        for real in reg.seen_contact:
            pat = (rf"(?<!\d){re.escape(real)}(?!\d)" if real.isdigit() else re.escape(real))
            if re.search(pat, blob):
                found.append(f"{r['email_id']}: contact {real}")
                break
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(IN))
    ap.add_argument("--out", default="data/topics/sample_anon.jsonl")
    ap.add_argument("--seed", type=int, default=None, help="omit for a fresh random map every run")
    ap.add_argument("--remap-cities", action="store_true",
                    help="also move each city to a different real city of similar size; off by default "
                         "because a company's home city is public context, not personal data")
    ap.add_argument("--max-redraws", type=int, default=8,
                    help="how many times to redraw pseudonyms and rewrite when a real name is spelled "
                         "across a boundary")
    ap.add_argument("--name-pool", choices=["census", "corpus"], default="census",
                    help="census (default) = SSA first names x Census surnames, ~1.2 billion combinations; "
                         "corpus = recombine the address book's own names. corpus is era-realistic but, "
                         "being real names, two adjacent pseudonyms can spell a third real person")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else secrets.randbits(48)
    rng = random.Random(seed)
    rows = [json.loads(l) for l in Path(args.inp).read_text().splitlines() if l.strip()]
    reg = Registry(rng)
    reg.remap_cities = args.remap_cities
    harvest(rows, reg, args.name_pool)
    print(f"identities: {len(reg.person):,} people ({len(reg.addr2key):,} addresses), "
          f"{len(reg.first_fake):,} global first-name rules, seed {seed}")
    print(f"pseudonym pool [{args.name_pool}]: {len(reg.pool_first):,} first x {len(reg.pool_last):,} last names")

    def rewrite_all():
        res = []
        for r in rows:
            o = dict(r)
            sender = r.get("from") or ""
            for f in ("subject", "body", "own_body"):
                if f in o:
                    o[f] = rewrite(o[f], sender, reg)
            o["from"] = rewrite(sender, sender, reg) if sender else sender
            res.append(o)
        return res

    # Self-healing: a real name spelled across a boundary is caught by the scan; the pseudonyms involved are
    # redrawn and the text rewritten.
    for attempt in range(1, args.max_redraws + 2):
        out_rows = rewrite_all()
        bad = leaks(out_rows, reg)
        name_bad = [b for b in bad if ": name " in b]
        if not bad or not name_bad or attempt > args.max_redraws:
            break
        pairs = {tuple(b.split(": name ", 1)[1].split()[:2]) for b in name_bad}
        n = sum(reg.redraw(f, l) for f, l in pairs)
        reg.build_first_map()
        print(f"  pass {attempt}: {len(name_bad)} cross-boundary name(s) {sorted(pairs)[:3]} "
              f"-> redrew {n} pseudonym(s), rewriting again")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n")
    private = Path(str(out) + ".map.json")
    private.write_text(json.dumps({
        "seed": seed,
        "people": {f"{p['first']} {p['last']}": {"fake": f"{p['fake_first']} {p['fake_last']}",
                                                 "addrs": sorted(p["addrs"])} for p in reg.person.values()},
        "companies": reg.company, "domains": reg.domain,
    }, indent=1, ensure_ascii=False) + "\n")
    print(f"WROTE {out}  ({len(out_rows):,} emails)   map (PRIVATE, gitignored) -> {private}")
    print(f"companies: " + ", ".join(f"{k}->{v}" for k, v in list(reg.company.items())[:5]) + " ...")
    print(f"domains  : " + ", ".join(f"{k}->{v}" for k, v in list(reg.domain.items())[:4]) + " ...")
    if bad:
        print(f"\nLEAKS: {len(bad)} rows still carry a real identity — FAILING", file=sys.stderr)
        for b in bad[:15]:
            print("   " + b, file=sys.stderr)
        return 1
    print("verify: no real full name, address, or source company token survives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
