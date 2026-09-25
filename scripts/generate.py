#!/usr/bin/env python3
"""Data generation: the four steps, from a (topic, kind) pair to planted email threads.

  1 secrets  one call per (topic, kind of secret) pair: prompts/secret.md on the pool in prompts/kinds.json
             -> actor, fact, secret, victim; the kind (dark, entrusted, strategic; Goffman 1956) rides along
  2 clues    one call per secret per lying pattern: prompts/clues.md, the parts and acts in prompts/atoms.json
             -> the three parts [fact] [knows] [conflict], written to one person
  3 plots    one call per chain (secret, pattern, n): prompts/plot.md with the choices in prompts/shapes.json
             -> stake, people, timeline, plan, threads with what each message says
  4 emails   one call per chain: prompts/email.md, the cast drawn from benchmark_pool/quiet_people.json and
             benchmark_pool/fresh_names.json -> the messages, checked and named by code

The model is chosen with --engine/--preset (default Claude Opus 5.5 through OpenRouter; --engine vllm
--preset qwen3-32b for a local model). Every stage reads and writes one state file (--state).

  python scripts/generate.py all --topics "family and relationships" --k 1 --facts 3   # steps 1 to 4
  python scripts/generate.py secrets --k 1          # step 1 only, one secret per (topic, kind) pair
  python scripts/generate.py clues                  # step 2, every secret under every pattern
  python scripts/generate.py chains --facts 12      # steps 3 and 4 on 12 secrets (--plots-only for step 3 alone)
  python scripts/generate.py report
Every model answer is written verbatim to logs/api_raw.jsonl with its finish reason.
"""
from __future__ import annotations
import argparse, json, random, re, sys, threading, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, ".")


def extract_json(text):
    """The first {...} object in a model answer, code fences stripped; None when there is none."""
    t = re.sub(r"```$", "", re.sub(r"^```(?:json)?", "", (text or "").strip()).strip()).strip()
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1 or b < a: return None
    try: return json.loads(t[a:b + 1])
    except json.JSONDecodeError: return None


GEN = None                     # the engine, built in main from --engine/--preset
GEN_KIND = "api"
EMAIL_PROMPT = "email.md"
KEEP_LABEL = "Person A's points, to make in Person A's own words"
JUDGE = False                  # --judge turns on the kind judge; it is a measurement, never a pipeline step
NOCLASS = True                 # --classify files each secret under the topic the model reads off its fact; otherwise the asked topic
CALLS = {"gen": 0, "gen_chars_in": 0, "gen_chars_out": 0, "local": 0}
V2 = Path("prompts")
PAT = json.loads((V2 / "patterns.json").read_text())
SHAPES = json.loads((V2 / "shapes.json").read_text())
ATOMS = json.loads((V2 / "atoms.json").read_text())      # the clue step's parts and acts, ported from enron_benchmark's atomize step
SECRET_KINDS = json.loads((V2 / "kinds.json").read_text())   # Goffman's three usable kinds of secret, and which IAB topics can hold each (sorted by hand)
LYING = ["lying by commission", "paltering", "lying by omission"]
TOPICS = [l.strip() for l in Path("prompts/iab_tier1.txt").read_text().splitlines() if l.strip() and l.strip() != "other"]
DESC = json.loads(Path("prompts/iab_tier1_desc.json").read_text())   # "name: what it covers", the taxonomy's own tier-2 list per tier-1 topic
TOPIC_LINES = "\n".join(DESC.get(t, t) for t in TOPICS)               # the classifier's list: name and gloss on one line, the name is the answer
CLASSIFY = Path("prompts/topic_classify.md").read_text()
FILES = json.loads(Path("benchmark_pool/file_bank.json").read_text())
STATE = Path("logs/generate.json")
RAW_LOG = Path("logs/api_raw.jsonl")                                  # verbatim model answers of every paid call
KINDS = ["false given the fact", "true but misleading", "says nothing about the fact"]
MAIL = [json.loads(l) for l in open("data/release/background_2000.jsonl")]           # the release the planted emails join
MAPD = json.load(open("data/topics/sample_anon.jsonl.map.json"))                      # the anonymisation pass's registry: firm name, domains, every pseudonym handed out
FIRM = MAPD["companies"].get("enron", "the firm")
FIRM_DOMAIN = MAPD["domains"].get("enron.com", "ashford.com")
FIRM_STEM = FIRM_DOMAIN.split(".")[0]
REFS = json.loads(Path("benchmark_pool/reference_bank.json").read_text())        # real subject lines that name a matter
STYLE_CARD = (V2 / "mailbox_style.md").read_text().strip().replace("<<FIRM_DOMAIN>>", FIRM_DOMAIN)   # the quoting form only; the register comes from the sample emails


def setting():
    return PAT["setting"].replace("<<FIRM>>", FIRM)


# ------------------------------------------------------------------ model
def chat(prompt, temperature=0.7, max_tokens=2000, extra=None):
    """One model call. extra={"choices": [...]} constrains a local model's answer to one of the choices; an API model answers freely."""
    max_tokens = max_tokens * 4 + 500 if GEN_KIND != "vllm" else max_tokens    # a reasoning model spends part of the budget before the answer
    for a in range(3):
        try:
            kw = {"choices": extra["choices"]} if extra and GEN_KIND == "vllm" else {}
            out = GEN.generate(prompt, max_tokens=max_tokens, temperature=temperature, **kw)[0]
            CALLS["gen" if GEN_KIND != "vllm" else "local"] += 1; CALLS["gen_chars_in"] += len(prompt); CALLS["gen_chars_out"] += len(out or "")
            with open(RAW_LOG, "a") as f:                       # every answer, verbatim, so a bad parse can be read afterwards
                f.write(json.dumps({"t": time.time(), "chars_in": len(prompt), "head": prompt[:80], "meta": getattr(GEN, "last_meta", None), "out": out or ""}) + "\n")
            return out or ""
        except Exception as e:
            print(f"   model call failed ({str(e)[:100]}); retry {a+1}", flush=True); time.sleep(5)
    raise RuntimeError("model did not recover")


EMPTIES = {"n": 0}


MAX_CALLS = 0                  # --max-calls: stop spending past this many model calls in the run (0 = no cap)


def chat_json(prompt, temperature=0.7, max_tokens=2000):
    """One call, and one more if the answer was empty or not JSON (an API model returns no content now and then).
    Two attempts is the cap: a retry is a paid call, so a bad day costs at most double."""
    for a in range(2):
        if MAX_CALLS and CALLS["gen"] >= MAX_CALLS: raise RuntimeError(f"--max-calls {MAX_CALLS} reached")
        js = extract_json(chat(prompt, temperature, max_tokens)) or {}
        if js: return js
        EMPTIES["n"] += 1; time.sleep(3)
    return {}


def classify(text):
    if NOCLASS: return None
    p = CLASSIFY.replace("<<TOPICS>>", TOPIC_LINES).replace("<<EMAIL>>", text)
    out = chat(p, 0.0, 24, {"choices": TOPICS}).strip().lower()
    return out if out in TOPICS else next((t for t in TOPICS if t in out), out)


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"secrets": [], "chains": []}


def save(st):
    STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False))


def yes(v):
    return str(v).strip().lower().startswith("y")


# ------------------------------------------------------------------ step 1
def count_line(k, what, differ):
    """The ask, worded for one or for several. The no-repeat rule appears only when several are asked for."""
    if k == 1: return f"Write one {what} that fits this kind and this area. If none fits, answer with an empty list."
    return f"Write {k} {what}s that fit this kind and this area, {differ}. If fewer than {k} fit, write fewer."


def avoid_block(header, items):
    return "\n" + header + "\n" + "\n".join("- " + x for x in items) + "\n" if items else ""


def kind_line(kind, full=True):
    """The kind of secret as the prompts state it: the name, Goffman's words with the 1956 page, and the plain reading; short form for the later steps."""
    k = SECRET_KINDS["kinds"].get(kind)
    if not k: return "not given"
    return f'{kind}. Goffman: "{k["quote"]}" (1956, p. {k["page"]}). Here: {k["plain"]}' if full else f'{kind}, {k["short"]}.'


def secrets_for(job, k, a=()):
    """One call: k secrets for one (topic, kind) pair. No avoid list at step 1 (user, 2026-09-20): a barred natural secret
    makes the model reach for a contrived one; overlap between calls is accepted."""
    topic, kind = job
    ground = ground_of(topic, kind)
    p = ((V2 / "secret.md").read_text().replace("<<SETTING>>", setting()).replace("<<FIRM>>", FIRM).replace("<<TOPIC>>", area_line(topic))
         .replace("<<GROUND>>", f"The case sits in the actor's work: the actor holds a job at {FIRM}, a US energy company." if ground == "work" else "The case sits in the actor's life outside work.")
         .replace("<<ACTOR_HOW>>", "by the job they hold" if ground == "work" else "in a few words")
         .replace("<<KIND>>", kind_line(kind))
         .replace("<<COUNT>>", count_line(k, "case", "each with a different fact")))
    js = chat_json(p, 0.7, 2400)
    out = []
    for s in js.get("cases") or js.get("secrets") or []:              # the prompt asks for cases; older prompts said secrets
        if isinstance(s, dict) and s.get("fact") and s.get("secret"):
            s["asked_topic"] = topic; s["kind"] = kind; s["ground"] = ground; s["victim"] = str(s.get("victim") or "").strip(); s["label"] = classify(s["fact"]) or topic
            out.append(s)
    return out


def area_line(topic):
    """The IAB area for step 1: the tier-1 name alone. The tier-2 coverage list was a menu: with "divorce" in it, family x dark gave
    a divorce kept at work in seven calls; with the name alone the victim became the spouse (run 21). The classifier still sees the full line."""
    return DESC.get(topic, topic).partition(": ")[0]


def ground_of(topic, kind):
    """work or life, per (topic, kind) in kinds.json: whether the case sits in the actor's job at the firm."""
    return SECRET_KINDS["topics"].get(topic, {}).get("cases", {}).get(kind, {}).get("ground", "work")


def secret_jobs(topics, kinds):
    """The (topic, kind) pairs step 1 asks for: each topic with the kinds it can hold, per kinds.json."""
    pool = SECRET_KINDS["topics"]
    return [(t, k) for t in topics if pool.get(t, {}).get("fit") for k in pool[t]["kinds"] if not kinds or k in kinds]






def patterns_for(s):
    """Every secret goes through the three lying patterns."""
    return list(LYING)


def collect(fn, topic, k, want, avoid_key, already=()):
    """Call fn for one topic (or one (topic, kind) pair) until `want` items exist, passing what is already written as <<AVOID>> so no call repeats an
    earlier one. `already` seeds the avoid list from an earlier run. Stops early when a call answers with an empty list
    (nothing more fits), and after want + 2 calls at most."""
    out, avoid = [], list(already)
    for _ in range(want + 2):
        got = fn(topic, min(k, want - len(out)), tuple(avoid))
        if not got: break
        out += got; avoid += [str(g.get(avoid_key, "")) for g in got]
        if len(out) >= want: break
    return out


def cmd_secrets(a):
    st = load()
    topics = [t.strip() for t in a.topics.split(",")] if a.topics else TOPICS
    kinds = [k.strip() for k in a.kinds.split(",")] if a.kinds else []
    jobs = secret_jobs(topics, kinds)
    old_s = [s for s in st["secrets"] if a.append]
    want_s = a.per_topic or a.k
    with ThreadPoolExecutor(a.workers) as ex:
        new_s = [s for lst in ex.map(lambda j: collect(secrets_for, j, a.k, want_s, "fact"), jobs) for s in lst]
    st["secrets"] = old_s + new_s; st.pop("roles", None)
    st.setdefault("calls", {})["secrets"] = dict(CALLS); save(st)
    print(f"secrets {len(st['secrets'])} from {len(jobs)} topic-kind pairs; on asked topic {sum(s['label']==s['asked_topic'] for s in st['secrets'])}; " +
          "; ".join(f"{k}: {sum(s.get('kind') == k for s in st['secrets'])}" for k in SECRET_KINDS["kinds"]))


# ------------------------------------------------------------------ step 2
QUOTE = re.compile(r'["\u201c]([^"\u201c\u201d]{3,}?)["\u201d]')


def holder_words(sentence):
    """The holder's own words in a clue-3 sentence: the last double-quoted span, or the sentence itself."""
    m = QUOTE.findall(str(sentence or ""))
    return m[-1].strip() if m else str(sentence or "").strip()


def hybrid(options, rng, key):
    """One menu line: half the time code assigns an option, half the time the model chooses. Returns (text, assigned)."""
    if rng.random() < 0.5:
        pick = rng.choice(options); return f"use: {pick}", pick
    return "choose one, or write a better one: " + "; ".join(options), None


def pattern_line(pattern, placeholders=None):
    """One sentence: the pattern's name, the source's words, then what it means in plain words. The people are the actor
    and the victim in every step; the plot step's cast block says which placeholder is which."""
    return f"{pattern}, {PAT[pattern]['quote']}: {PAT[pattern]['plain']}"


NUM = {2: "two", 3: "three", 4: "four"}
def kind_of(pattern):
    return "record"


def labels(pattern):
    """The three parts' names for this pattern's kind: fact, knows, conflict; or outside, job, apart."""
    return list(ATOMS["labels"][kind_of(pattern)])


def clue_prompt(s, pattern):
    """The parts prompt: setting, the three parts for this kind, the secret sentence, the pattern, the AND gate. No examples: they steer the model."""
    kind = kind_of(pattern); a = ATOMS[pattern]; lab = labels(pattern)
    frame = {"lying by commission": "<the actor, by role> tells <the victim, by role> that <one statement, false given the fact>",
             "paltering": "<the actor, by role> tells <the victim, by role> <true statements on the matter that leave a false picture of it>",
             "lying by omission": "<the actor, by role>, <asked by the victim about the matter, or in the report, form or review the fact belonged in>, <answers or sends what was asked for> and is silent on <the fact>"}[pattern]
    facts = ["the fact as a standing state", "<the actor, by role>, <on what occasion>, <does or arranges one thing, with whom>", frame]
    schema = '{"victim": "the one person the parts are written to, by role: the victim, or the person who stands for the party", ' + ", ".join(f'"{k}": "{f}"' for k, f in zip(lab, facts)) + "}"
    return ((V2 / "clues.md").read_text().replace("<<PATTERN_NAME>>", pattern).replace("<<SETTING>>", setting()).replace("<<FIRM>>", FIRM)
            .replace("<<PARTS>>", ATOMS["parts"][kind].replace("<<ACT>>", a["act"]))
            .replace("<<GROUND_LINE>>", "The case sits in the actor's work at the firm." if s.get("ground", "work") == "work" else "The case sits in the actor's life outside work; the actor's job at the firm is not part of it.")
            .replace("<<ACTOR>>", str(s.get("actor") or "").strip()).replace("<<FACT>>", str(s.get("fact") or "").strip())
            .replace("<<SECRET>>", str(s.get("secret", "")).strip()).replace("<<VICTIM>>", str(s.get("victim") or "not given: choose one person by role who would say they had a right to know"))
            .replace("<<KIND>>", kind_line(s.get("kind"), full=False)).replace("<<PATTERN>>", pattern_line(pattern))
            .replace("<<AND_GATE>>", PAT["and_gate"][kind]).replace("<<SCHEMA>>", schema))


def clues_for(s, pattern):
    """One call: the three parts of this secret under this pattern. Stored under s['clues'][pattern] by label."""
    js = chat_json(clue_prompt(s, pattern), 0.6, 700); lab = labels(pattern)
    out = {}
    for k, old in zip(lab, ("a1", "a2", "a3")):                    # older state files kept a1, a2, a3
        v = js.get(k, js.get(old)); out[k] = str(v.get("fact", "") if isinstance(v, dict) else v or "").strip()
    out["victim"] = str(js.get("victim") or "").strip()
    out["ok"] = all(out[k] for k in lab) and len({out[k] for k in lab}) == 3
    out["flags"] = [f"keeping words in [{k}]: {', '.join(kw)}" for k in lab[:2] if (kw := keeping_words(out[k]))]   # hiding words in [fact] or [knows] break the gate
    if len(out[lab[2]].split()) > 60: out["flags"].append(f"[conflict] is {len(out[lab[2]].split())} words; the model pads acts, read it for a leaning clause")
    s.setdefault("clues", {})[pattern] = out
    return s


def n_for(i, j, vary):
    """The chain length of secret i under pattern j: 3 (fixed for now, user 2026-09-20); 2 to 4 with --vary-n."""
    return 2 + (i + j) % 3 if vary else 3


def passes(s, pattern):
    c = (s.get("clues") or {}).get(pattern) or {}
    return bool(c.get("ok"))


def cmd_clues(a):
    """One call per (secret, pattern) for the secrets that have none yet. n is chosen at the chain step."""
    st = load()
    jobs = [(s, p) for s in st["secrets"] for p in patterns_for(s) if p not in (s.get("clues") or {})]
    if a.per_topic:                                              # at most N secrets per topic
        seen = defaultdict(set); keep = []
        for s, p in jobs:
            key = s["asked_topic"]; sid = s.get("secret")
            if sid in seen[key] or len(seen[key]) < a.per_topic: seen[key].add(sid); keep.append((s, p))
        jobs = keep
    try:
        with ThreadPoolExecutor(a.workers) as ex:
            for i, _ in enumerate(ex.map(lambda j: clues_for(*j), jobs)):
                if i % 20 == 0: save(st); print(f"   {i}/{len(jobs)}", flush=True)
    finally:
        st.setdefault("calls", {})["clues"] = dict(CALLS); save(st)
    for p in LYING:
        pool = st["secrets"]
        got = [s for s in pool if p in (s.get("clues") or {})]
        print(f"   {p:22s} parts for {len(got)}/{len(pool)}; all three filled and distinct: {sum(passes(s, p) for s in got)}")


# ------------------------------------------------------------------ step 3: plots
ATOM_WHAT = {
    "fact": "an email that states the fact, written by someone other than the holder",
    "holds": "an email showing the record (the email that states the fact) reached the holder: it names the reference and says nothing of what the record says",
    "lie": "the holder's email to the person kept from the fact, saying something false about the matter",
    "stand-in": "the holder's reply to the person kept from the fact: one true sentence that does not answer what they asked",
    "omit": "the holder's reply to the person kept from the fact: it answers their request and does not mention the matter",
}


def keep_line(lines, carries, pattern):
    """The one line of this clue that reaches the emails unchanged, or None."""
    third = PAT[pattern]["third_atom"]
    for a in carries:
        if a == third: return lines["third"]["holder_line"]
    return None


CHECK_NAMES = {"record": ["fact", "holds", None]}   # the parts under the names the checks use


def check_names(pattern):
    names = list(CHECK_NAMES[kind_of(pattern)])
    if names[2] is None: names[2] = PAT[pattern]["third_atom"]
    return names


def label_of(pattern, name):
    """A part under the checks' name (fact, fact.1, holds, lie ...) back to its label ([fact], [knows], [conflict] ...)."""
    back = dict(zip(check_names(pattern), labels(pattern)))
    return "[" + back.get(name.split(".")[0], name) + "]"


def never_together(pattern):
    """The two parts that give the secret between them, so no clue carries both: [fact] and [conflict]; [outside] and [job]."""
    lab = labels(pattern)
    return (lab[0], lab[2])


def parts_text(pattern, lines):
    """The three parts as the plot step sees them, by label."""
    return "\n".join(f"[{k}]: {a}" for k, a in zip(labels(pattern), lines["atoms"]))


def plan_from_plot(clues, pattern, n):
    """The plot's own plan: each clue's carries by label, checked. Every part somewhere, the two that give the secret never together,
    every clue at least one. Returns the plan under the checks' names, or None with the reason."""
    lab = labels(pattern); alias = dict(zip(("a1", "a2", "a3"), lab)); got = []
    for c in clues:
        cs = c.get("carries"); cs = cs if isinstance(cs, list) else [cs]
        cs = [alias.get(x, x) for x in (str(x).strip().strip("[]").lower() for x in cs)]
        cs = [x for x in cs if x in lab]
        if not cs: return None, f"clue {c.get('i')} carries no part"
        a, b = never_together(pattern)
        if a in cs and b in cs: return None, f"clue {c.get('i')} carries [{a}] and [{b}] together"
        got.append(cs)
    need = set(lab)
    missing = need - {x for cs in got for x in cs}
    if missing: return None, "no clue carries " + ", ".join(f"[{m}]" for m in sorted(missing))
    if n >= 3 and any(len(cs) > 1 for cs in got): return None, f"with {NUM[n]} clues every clue carries one part"
    if n == 4 and sum(len(cs) for cs in got) != 4: return None, "with four clues one part is spread over two clues"
    names = dict(zip(lab, check_names(pattern)))
    return [[names[x] for x in cs] for cs in got], ""


def menus_text(pattern, n, rng, ground="work"):
    """The plot step's choices, one line each. Work topics: half assigned by code, half left to the model. Life topics: no coin,
    every line is the model's choice (user, 2026-09-20), and the event carrier for [fact] is offered only for work topics, where
    invoices and renewals exist. Returns (text, keys, assigned)."""
    m = []; assigned = {}; keys = []
    def line(key, what, options):
        if ground == "life": txt, a = "choose one, or write a better one: " + "; ".join(options), None
        else: txt, a = hybrid(options, rng, key)
        m.append(f"- {key}, {what}: {txt}"); keys.append(key)
        if a: assigned[key] = a
    facts = [x for x in SHAPES["carrier"]["fact"] if ground == "work" or not x.startswith("an event with consequences")]
    line("carrier_fact", "how [fact] shows up in the mailbox", facts)
    m.append("- [knows] shows up as the act the part names, with the person it names")
    if pattern == "lying by omission": m.append("- the occasion of [conflict] is the one the part names; keep it")
    else: line("carrier_conflict", "the occasion of [conflict]: what brings the matter up between Person A and Person B", SHAPES["carrier"]["conflict"][pattern])
    line("after", "what Person B does once Person A has acted", SHAPES["third"]["after"])
    line("naming", "how the matter is named in a subject line, where a thread names it at all", SHAPES["naming"]["form"])
    m.append("  Real subject lines from this mailbox: " + "; ".join(rng.sample(REFS, 5)) + ". Real file names: " + ", ".join(distinct_files(rng, 4)) + ". " +
             ("A thread may name the matter in its subject line or not at all; you decide per thread, and a name, where there is one, says which matter without saying the fact: a number, a place, a date, a file, not the thing itself. A document's title appears only where the people on that thread would use it."))
    return "\n".join(m), keys, assigned


def distinct_files(rng, k):
    out, stems = [], set()
    for f in rng.sample(FILES, len(FILES)):
        stem = re.sub(r"(rev|v)?\d*\.\w+$", "", f.lower())[:12]
        if stem not in stems: stems.add(stem); out.append(f)
        if len(out) == k: break
    return out


FUNCTIONS = {"record": [("Person A", "the actor, who keeps the secret; works at the firm"), ("Person B", "the victim, kept from the fact"), ("Person C", "the insider: who holds the fact in writing besides Person A; you decide who")]}


def cast_block(s, pattern, n, lines, rec=None):
    """Who everyone is. Before the plot step: the fixed letters and what each one does in the secret, for the plot to fill in.
    After it: the plot's own people table."""
    people = described_people(rec) if rec else []
    if people:
        return "\n".join(f"{e['person']}, {e['function']}: {e['role']}, {'at the firm' if e['at_firm'] else 'outside the firm'}." for e in people)
    def a_line(what):
        who = str(s.get("actor") or "").strip()
        if s.get("ground") == "life": return f"the actor, who keeps the secret: {who}; works at the firm, in a job you choose to fit the case" if who else what + ", in a job you choose to fit the case"
        return f"the actor, who keeps the secret: {who}; works at the firm" if who else what
    fixed = [(lab, a_line(what) if lab == "Person A" else what + (f": {lines['victim']}" if lab == "Person B" and lines.get("victim") else "")) for lab, what in FUNCTIONS[kind_of(pattern)]]
    out = [f"{lab}: {what}." for lab, what in fixed]
    nxt = chr(ord(fixed[-1][0][-1]) + 1)
    out.append(f"Anyone else the threads need continues the letters from Person {nxt}.")
    return "\n".join(out)


def described_people(rec):
    """The plot step's people table: person, function, role, at_firm."""
    out = []
    for e in ((rec or {}).get("plots") or {}).get("people") or []:
        if isinstance(e, dict) and re.fullmatch(r"Person [A-J]", str(e.get("person", "")).strip()):
            out.append({"person": str(e["person"]).strip(), "function": str(e.get("function", "")).strip(), "role": str(e.get("role", "")).strip(), "at_firm": yes(e.get("at_firm", "yes"))})
    return out


extra_people = described_people


def lines_for_chain(s, pattern, n):
    """The three parts, and the same text under the names the checks use (fact, holds, third, roles)."""
    c = s["clues"][pattern]; atoms = [str(c.get(k, c.get(old, ""))) for k, old in zip(labels(pattern), ("a1", "a2", "a3"))]; victim = str(c.get("victim", ""))
    return {"atoms": atoms, "victim": victim, "fact": atoms[0], "holds": atoms[1], "third": {"clue": atoms[2], "holder_line": atoms[2]},
            "cast": {"holder": "Person A", "kept_from": "Person B", "record_writer": "Person C"}}


SMART = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"})


def flat(s):
    """Compare text the way a reader would: one kind of quote, one kind of dash, one kind of space."""
    return " ".join(str(s).translate(SMART).lower().split())


def verbatim_in(text, lines):
    t = flat(text)
    return all(flat(l)[:25] in t for l in lines if l)


STOP = set("the a an and or of to in on for with is are was were be been it its this that i you we he she they my your our his her their as at by from not no".split())


def line_kept(text, lines):
    """How much of the holder's line survived the email step: the share of its content words found in the emails,
    lowest over the lines. 1.0 = every content word present; the verbatim flag is the strict version."""
    body = set(re.findall(r"[a-z']+", flat(text)))
    scores = []
    for l in lines:
        words = [w for w in re.findall(r"[a-z']+", flat(l)) if w not in STOP and len(w) > 2]
        if words: scores.append(sum(w in body for w in words) / len(words))
    return round(min(scores), 2) if scores else None




def _messages(c):
    """A clue's messages in order. Older outputs gave one from/to per clue; those become a one-message list."""
    msgs = c.get("messages") or c.get("threads")
    if isinstance(msgs, list) and msgs and all(isinstance(m, dict) for m in msgs):
        c["messages"] = msgs
    else:
        c["messages"] = [{k: c.get(k) for k in ("from", "to", "date", "subject", "what_happens")}]
    c.pop("threads", None)
    first = c["messages"][0]
    for k in ("from", "to", "date", "subject"):
        if not c.get(k): c[k] = first.get(k)
    if not c.get("reference"): c["reference"] = next((m.get("reference") for m in c["messages"] if m.get("reference")), "")
    if not c.get("what_happens"): c["what_happens"] = " ".join(str(m.get("what_happens") or "") for m in c["messages"]).strip()
    return c


def _sorted_clues(plots, k):
    cl = [_messages(c) for c in (plots.get("clues") or []) if isinstance(c, dict)]
    def key(c):
        m = re.match(r"\d+", str(c.get("i", "")))
        return int(m.group()) if m else 99
    return sorted(cl, key=key)[:k]


PLOT_SCHEMA = """{"stake": "what the victim is about to do, one clause",
 "people": [{"person": "Person ?", "function": "what this person is in the secret, as listed above, or other", "role": "who this person is, in a few words", "at_firm": "yes or no"}],
 "timeline": [{"date": "YYYY-MM-DD", "event": "one clause", "shows": "the part this event shows, or empty"}],
 "choices": {<<CHOICE_KEYS>>},
 "clues": [{"i": 1, "carries": [<<FIRST_PART_Q>>], "reference": "how this thread names the matter, or empty", "line": "Person A's message to Person B, in substance; empty for other clues",
            "messages": [{"from": "Person ?", "to": ["Person ?"], "date": "YYYY-MM-DD", "subject": "...", "what_happens": "one or two sentences"}]}]}"""


def plot_for(rec, s, pattern, n, rng):
    lines = lines_for_chain(s, pattern, n); fallback = PAT[pattern]["templates"][str(n)]
    menus, keys, assigned = menus_text(pattern, n, rng, s.get("ground", "work"))
    p = ((V2 / "plot.md").read_text().replace("<<SCHEMA>>", PLOT_SCHEMA).replace("<<SETTING>>", setting()).replace("<<N_CLUES>>", NUM[n])
         .replace("<<SECRET>>", str(s.get("secret", "")).strip())
         .replace("<<PATTERN>>", pattern_line(pattern)).replace("<<KIND>>", kind_line(s.get("kind"), full=False))
         .replace("<<GROUND_LINE>>", "The case sits in the actor's work at the firm." if s.get("ground", "work") == "work" else "The case sits in the actor's life outside work; the job is not part of it.")
         .replace("<<CAST>>", cast_block(s, pattern, n, lines)).replace("<<ERA>>", "2001")
         .replace("<<PARTS_TEXT>>", parts_text(pattern, lines))
         .replace("<<NEVER_TOGETHER>>", "[{}] and [{}] are never in the same clue.".format(*never_together(pattern)))
         .replace("<<FEWER_CLUES>>", {2: "either clue on its own", 3: "one clue on its own, or any two", 4: "any one, two or three clues"}[n])
         .replace("<<PLAN_SHAPE>>", {2: "With two clues, one thread carries [fact] and [knows] together and the other carries [conflict]. The first is one exchange, not two: the record and Person A's act sit in the same thread, so the record reaches the person Person A then writes to, or Person A's act is a reply on the record's thread; Person A is on it, and what keeps the gate is that nothing in it is kept from anyone. The second is Person A's act toward Person B alone.", 3: "With three clues, one part each.", 4: "With four clues, one part is spread over two clues that are each innocent on their own, and every clue carries one part."}[n])
         .replace("<<FIRST_PART>>", f"[{labels(pattern)[0]}]").replace("<<FIRST_PART_Q>>", f'"{labels(pattern)[0]}"')
         .replace("<<MENUS>>", menus)
         .replace("<<CHOICE_KEYS>>", ", ".join(f'"{k}": "the option used, in its first words"' for k in keys))
         .replace("<<PATTERN_RULE>>", PAT[pattern].get("plot_rule", "")))
    rec.update({"lines": lines, "plot_prompt": p})
    plots = chat_json(p, 0.5, 2400)
    rec["assigned"] = assigned
    rec["slots"] = {k: str(v)[:80] for k, v in (plots.get("choices") or {}).items()} if isinstance(plots.get("choices"), dict) else {}
    rec["choices_commentary"] = [k for k, v in (plots.get("choices") or {}).items() if isinstance(plots.get("choices"), dict) and len(str(v).split()) > 12]
    clues = _sorted_clues(plots, n)
    plan, why = plan_from_plot(clues, pattern, n) if len(clues) == n else (None, f"plot returned {len(clues)} clues for {n}")
    if plan is None:                                             # the plot's plan failed a check: one more try, then the fixed template
        rec["plot_retry_plan"] = why
        plots2 = chat_json(p + "\n\nYour plan did not hold: {}. Return exactly {} clues, one thread each; every part is carried by some clue, [{}] and [{}] never share a clue, and every clue carries at least one part. Return the whole object again.".format(why, NUM[n], *never_together(pattern)), 0.5, 2400)
        clues2 = _sorted_clues(plots2, n)
        plan2, why2 = plan_from_plot(clues2, pattern, n) if len(clues2) == n else (None, why)
        if plan2 is not None: plots, clues, plan = plots2, clues2, plan2
        elif len(clues) == n: plan = [list(c) for c in fallback]; rec["plan_fallback"] = True
    rec["plan"] = plan or [list(c) for c in fallback]; plan = rec["plan"]
    rec["timeline"] = [{"date": str(e.get("date", "")), "event": str(e.get("event", "")), "shows": str(e.get("shows") or "").strip("[] ").lower()}
                       for e in (plots.get("timeline") or []) if isinstance(e, dict)]
    rec["stake"] = str(plots.get("stake") or "").strip()
    if len(clues) == n and invented_people(clues):               # a name in a from/to field where a placeholder belongs: one more try
        rec["plot_retry"] = invented_people(clues)
        plots2 = chat_json(p + "\n\nEvery from and to field holds a placeholder, Person A, Person B and so on, never a name. "
                              "Anyone the clues need beyond the people listed continues the letters.", 0.5, 2000)
        clues2 = _sorted_clues(plots2, n)
        if len(clues2) == n and len(invented_people(clues2)) < len(invented_people(clues)): plots, clues = plots2, clues2
    firm = firm_people(s, pattern, n, sorted(set(re.findall(r"Person [A-J]", json.dumps(clues)))), {"plots": plots})
    if len(clues) == n and nobody_at_firm(clues, firm):
        rec["plot_retry_firm"] = nobody_at_firm(clues, firm)
        plots2 = chat_json(p + "\n\nEvery message is sent or received by someone at the firm: " + ", ".join(sorted(firm)) +
                              ". A message between two outside people, or from someone to themselves, cannot sit in this mailbox.", 0.5, 2000)
        clues2 = _sorted_clues(plots2, n)
        if len(clues2) == n and len(nobody_at_firm(clues2, firm)) < len(nobody_at_firm(clues, firm)): plots, clues = plots2, clues2
    for c, carries in zip(clues, plan):
        c["carries"] = list(carries)
        line = str(c.get("line") or "").strip()                    # the plot landed the actor's line on something concrete
        if line and PAT[pattern]["third_atom"] in carries: lines["third"]["holder_line"] = line
    plots["clues"] = clues; rec["plots"] = plots
    if len(clues) != n:
        rec["error"] = f"plot returned {len(clues)} clues for {n}"; return rec
    rec["plot_invented"] = invented_people(clues)
    defined = {e["person"] for e in described_people(rec)}
    rec["plot_undefined"] = sorted({p for p in re.findall(r"Person [A-J]", json.dumps(clues)) if p not in defined})   # a placeholder used in a thread but absent from the people table
    return rec


def nobody_at_firm(clues, firm):
    """Clue numbers with a message that no one at the firm sends or receives."""
    bad = []
    for c in clues:
        for m in c.get("messages") or [c]:
            to = m.get("to"); to = to if isinstance(to, list) else [to]
            people = {str(x).strip() for x in [m.get("from")] + list(to) + list(m.get("cc") or []) if x}
            if firm and not (people & firm): bad.append(c.get("i"))
    return sorted(set(bad))


def invented_people(clues):
    """from/to entries that are not placeholders."""
    bad = []
    for c in clues:
        for m in c.get("messages") or [c]:
            to = m.get("to"); to = to if isinstance(to, list) else [to]
            for who in [m.get("from")] + list(to):
                if who and not re.fullmatch(r"Person [A-J]", str(who).strip()): bad.append(str(who))
    return sorted(set(bad))


# ------------------------------------------------------------------ step 4: names, style, emails
def person_name(addr):
    local = addr.split("@")[0]
    return " ".join(w.capitalize() for w in re.split(r"[._]", local) if w)


MASS_MAIL = re.compile(r"\[IMAGE\]|\bcustomers?\b|\bsavings\b|\d+\s?%|\bsubscri|\bnewsletter\b|\bpromotion|\bdear valued\b|\bwww\.|http", re.I)   # a mailer is not a person writing in
AUTOMATED = re.compile(r"unsubscribe|ebill|e-bill|automated|do not reply|click here|this is an automatic|confirmation number|your order", re.I)
QUOTED = re.compile(r"-----\s*Original Message\s*-----|-+\s*Forwarded by|<Embedded|^\s*From:\s|\bwrote:\s*$|^\s+To:\s|^\s*\t?[A-Z][\w'.-]+ [A-Z][\w'.-]+\s*\n\s*\d{2}/\d{2}/\d{4}|^.*<[^>]+@[^>]+>\s+on\s+\d{2}/\d{2}/\d{4}|^\s*\S.*\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})? ?(AM|PM)", re.M)


FOOTER = re.compile(r"\*{4,}|This e-mail is the property of|confidential and privileged|^\s*-{10,}\s*$", re.M)


def own_only(text):
    """A sender's own words: the body cut at the first quoted block or boilerplate footer, trimmed to about 130 words."""
    m = QUOTED.search(text or ""); t = (text[:m.start()] if m else text or "").strip()
    f = FOOTER.search(t)
    if f: t = t[:f.start()].strip()
    words = t.split()
    if len(words) > 130:
        cut = t[:len(" ".join(words[:130]))]; end = max(cut.rfind(". "), cut.rfind(".\n"), cut.rfind("?"), cut.rfind("!"))
        t = cut[:end + 1] if end > 0 else cut
    return t


def prose(t):
    """Ordinary email prose: not a table, a report or a signature-only message."""
    letters = sum(c.isalpha() for c in t); digits = sum(c.isdigit() for c in t)
    lines = [l for l in t.split("\n") if l.strip()]
    names = len(re.findall(r"[A-Z][a-z]+ [A-Z][a-z]+", t))       # a distribution list pasted into a body is not prose
    return (25 <= len(t.split()) <= 200 and letters >= 0.65 * len(t) and digits <= 0.04 * len(t)
            and t.count(";") <= 3 and names <= 6
            and sum(l.isupper() or ":" in l and len(l) < 40 for l in lines) <= 0.3 * len(lines))


QUIET = json.loads(Path("benchmark_pool/quiet_people.json").read_text())["people"]   # firm people the corpus says nothing about (scripts/quiet_people.py)
FRESH = json.loads(Path("benchmark_pool/fresh_names.json").read_text())              # names and domains that occur nowhere in the release (scripts/fresh_names.py)
RELEASE_BY_ID = {m["email_id"]: m for m in MAIL}

def firm_people(s, pattern, n=None, labels=(), rec=None):
    """Who is at the firm: what the plot's people table says; Person A always; anyone the table does not mention, at the firm."""
    described = {e["person"]: e["at_firm"] for e in described_people(rec)}
    at = {"Person A"} | {l for l, side in described.items() if side}
    at |= {l for l in labels if l not in described}
    return at


USED = {"people": set(), "fresh": set(), "domains": set(), "lock": threading.RLock()}     # people, minted names and minted domains already cast in this run: one chain each


def substitute(text, names):
    for lab in sorted(names, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(lab) + r"(?:'s)?\b", lambda m: names[lab]["name"] + ("'s" if m.group(0).endswith("'s") else ""), text)
    return text


def name_forms(text, names, plan=None):
    """Placeholders -> names after the email is written: full name and address in headers, first name where a person is
    addressed or signs."""
    second = {}
    def body_sub(body):
        """A person is called by their first name where they are greeted or where someone signs off, and by their
        full name everywhere else. The header lines of a quoted block keep full names, as the mailbox does."""
        lines = body.split("\n")
        for i, ln in enumerate(lines):
            header = bool(HEADER_LINE.search(ln))
            for lab in sorted(names, key=len, reverse=True):
                if lab not in ln: continue
                nm = names[lab]["name"]; short = nm.split()[0]
                if not header:
                    ln = re.sub(r"^(\s*(?:hi|hello|dear|hey)\s+)" + re.escape(lab) + r"\b", lambda m: m.group(1) + short, ln, flags=re.I)
                    ln = re.sub(r"^(\s*)" + re.escape(lab) + r"(?=\s*[,:\u2014-])", lambda m: m.group(1) + short, ln)
                    ln = re.sub(r"(?:(?<=[.!?] )|(?<=[.!?]  ))" + re.escape(lab) + r"(?=,)", short, ln)   # "... .  Person B, can you" -> first name
                    if len(ln.split()) <= 6 and re.search(re.escape(lab) + r"\s*[.,!]?\s*$", ln):
                        ln = ln.replace(lab, short)
                ln = re.sub(r"\b" + re.escape(lab) + r"(?:'s)?\b", lambda m: nm + ("'s" if m.group(0).endswith("'s") else ""), ln)
            lines[i] = ln
        return "\n".join(lines)

    def addr_of(lab, i):
        return second.get(i, {}).get(lab) or names[lab]["addr"]
    def addr_sub(t, i):                                          # invented addresses, and the link's token -> the assigned ones
        for lab, v in names.items():
            t = re.sub(r"\bperson[._]?" + lab[-1].lower() + r"@[\w.-]+", addr_of(lab, i), t, flags=re.I)
            if v.get("second"): t = t.replace("a.home@mailbox.net", v["second"])
        return t
    def header(t, i):                                            # every person in a header reads "Name <address>"
        t = addr_sub(substitute(t, names), i)
        for lab, v in names.items():
            a = addr_of(lab, i)
            t = re.sub(re.escape(v["name"]) + r"\s*<[^>]*>", v["name"] + " <" + a + ">", t)
            t = re.sub(re.escape(v["name"]) + r"(?!\s*<)", v["name"] + " <" + a + ">", t)
        return t
    for c in text.get("clues", []):
        i = int(re.match(r"\d+", str(c.get("i", "0"))).group()) if re.match(r"\d+", str(c.get("i", "0"))) else 0
        for m in c.get("messages", []):
            m["from"] = header(str(m.get("from", "")), i)
            m["to"] = [header(str(x), i) for x in (m.get("to") or [])]
            m["cc"] = [header(str(x), i) for x in (m.get("cc") or [])]
            m["subject"] = substitute(str(m.get("subject", "")), names)
            m["body"] = addr_sub(body_sub(str(m.get("body", ""))), i)
    return text


def enforce_headers(em, plots):
    """The plot fixed who writes to whom, when, and under what subject; the email step was told to keep them. Where the
    thread has the planned number of messages, the planned headers win over whatever the model wrote. Returns how many
    messages needed it."""
    fixed = 0
    for c in em.get("clues", []):
        i = int(str(c.get("i", "0")).strip()) if str(c.get("i", "0")).strip().isdigit() else 0
        if not 1 <= i <= len(plots): continue
        planned = plots[i - 1].get("messages") or [plots[i - 1]]
        written = c.get("messages") or []
        if len(planned) != len(written): continue
        for pm, m in zip(planned, written):
            to = pm.get("to"); to = list(to) if isinstance(to, list) else [str(to)] if to else []
            want = {"from": str(pm.get("from", "")), "to": to, "date": str(pm.get("date", "")), "subject": str(pm.get("subject", ""))}
            have = {"from": str(m.get("from", "")), "to": list(m.get("to") or []), "date": str(m.get("date", "")), "subject": str(m.get("subject", ""))}
            if not all(re.fullmatch(r"Person [A-J]", w.strip()) for w in [want["from"]] + want["to"]):   # the plot itself invented a name: keep the model's people
                want["from"], want["to"] = have["from"], have["to"]
            if want != have: fixed += 1; m.update(want)
    return fixed


def missing_people(em, expected):
    """Placeholders the plot uses that the written emails never mention, in a header or in a body."""
    return expected - set(re.findall(r"Person [A-J]", json.dumps(em, ensure_ascii=False)))


def quiet_name(p):
    """What the mailbox calls this person: the signed name where it differs from the address (the release maps bodies and
    addresses separately), with the address surname behind a bare first name."""
    signed = (p.get("signed_name") or "").strip()
    if p.get("name_consistent", True) or not signed: return p.get("name") or signed
    loc = p["addr"].split("@")[0]
    if len(signed.split()) == 1 and "." in loc and loc.split(".")[-1].isalpha():
        return f"{signed} {loc.split('.')[-1].capitalize()}"
    return signed


def fresh_domain(rng):
    """A domain in the corpus's form, <stem><number>.com, that the corpus does not have and this run has not used."""
    stems = [s for s in FRESH["domain_stems"] if s != FIRM_STEM] or ["meridian"]
    have = set(FRESH["corpus_domains"]) | USED["domains"]
    while True:
        d = f"{rng.choice(stems)}{rng.randint(2, 99)}.com"
        if d not in have: USED["domains"].add(d); return d


def draw_cast(rec, s, rng, k=5):
    """Ten name-and-address pairs for the email step to cast from: k firm people from the quiet pool, each with the one
    email they have in the mailbox, and k minted outsiders with fresh names on fresh domains. Nothing is marked used until
    the model has chosen."""
    with USED["lock"]:
        firm = [p for p in QUIET if p["addr"] not in USED["people"]]
        rng.shuffle(firm)                                            # first those with a full name, a prose email to show the voice, and a name the mailbox agrees on
        firm.sort(key=lambda p: (len(quiet_name(p).split()) < 2, not prose(own_only(RELEASE_BY_ID[p["email_id"]].get("own_body") or "")), not p.get("name_consistent", True)))
        firm = firm[:k]
        names = [n for n in FRESH["names"] if n not in USED["fresh"]]
        outside = [{"name": nm, "addr": f"{nm.lower().replace(' ', '.')}@{fresh_domain(rng)}"} for nm in rng.sample(names, k)]
    return {"firm": [{"name": quiet_name(p), "addr": p["addr"], "email_id": p["email_id"], "topic": p["topic"]} for p in firm], "outside": outside}


def outside_samples(rec, topic, rng, k=2, ground="work"):
    """Two real emails from outside senders on the chain's topic, one per sender: how mail from outside reads. The minted
    people have no mail of their own, so this is their register; off the topic only if the box has too few on it."""
    cands = [m for m in MAIL if not m["from"].endswith("@" + FIRM_DOMAIN) and m.get("own_body") and prose(own_only(m["own_body"]))
             and not AUTOMATED.search(m["own_body"]) and not MASS_MAIL.search(m["own_body"]) and len(own_only(m["own_body"]).split()) <= 110]
    on = [m for m in cands if m.get("topic") == topic]; off = [m for m in cands if m not in on]
    rng.shuffle(on); rng.shuffle(off); pick, seen = [], set()
    for m in on + off:
        if len(pick) == k: break
        if m["from"] not in seen: seen.add(m["from"]); pick.append(m)
    return pick


def candidates_block(draw, rec, topic, rng, ground="work"):
    out = ["Firm names, each with the one email that person has in the mailbox:"]
    for c in draw["firm"]:
        m = RELEASE_BY_ID.get(c["email_id"], {})
        out.append(f"{c['name']} <{c['addr']}>\n  Subject: {m.get('subject', '')}\n  " + own_only(m.get("own_body") or m.get("body") or "").strip().replace("\n", "\n  "))
    out.append("\nOutside names:")
    out += [f"{c['name']} <{c['addr']}>" for c in draw["outside"]]
    out.append("\nHow mail from outside the firm reads, two emails from the mailbox:")
    picks = outside_samples(rec, topic, rng, ground=ground); rec["outside_samples"] = [{"email_id": m["email_id"], "topic": m["topic"], "from": m["from"]} for m in picks]
    for m in picks:
        out.append(f"  Subject: {m.get('subject', '')}\n  " + own_only(m["own_body"]).strip().replace("\n", "\n  "))
    return "\n".join(out)


def points_of(line):
    """The clue step's sentence is reported speech, 'tells B that X, that Y, and that Z'. The email step gets the
    points, not the sentence, so the voice is Person A's and the meaning stays."""
    t = str(line or "").strip().rstrip(".")
    m = re.search(r"\b(tells?|writes?|says?|replies|answers?|assures?|reports?|confirms?|emails?)\b[^,]*?\bthat\b", t)
    if m:
        pts = [x.strip(" ,;") for x in re.split(r",?\s+(?:and\s+)?that\s+", t[m.end():]) if x.strip(" ,;")]
        if len(pts) >= 2: return pts
    return [t] if t else []


def plots_block(rec, keep_label=None):
    """Step 3's threads as the email step reads them: the messages with what each says, and Person A's points."""
    blocks = []
    for c, carries in zip(rec["plots"]["clues"], rec["plan"]):
        b = [f"clue {c.get('i')} carries {', '.join(label_of(rec['pattern'], a) for a in carries)}"]
        if str(c.get("reference") or "").strip(): b.append(f"  reference: {c['reference']}")
        for j, m in enumerate(c.get("messages") or [c], 1):
            to = m.get("to"); to = ", ".join(to) if isinstance(to, list) else str(to or "")
            b.append(f"  message {j}: {m.get('from')} to {to}, {m.get('date')}, subject: {m.get('subject')}")
            b.append(f"    what it says: {m.get('what_happens') or c.get('what_happens') or c.get('plot')}")
        kl = keep_line(rec["lines"], carries, rec["pattern"])
        if kl:
            b.append(f"  {keep_label or KEEP_LABEL}:")
            b += [f"    - {pt}" for pt in points_of(kl)]
        blocks.append("\n".join(b))
    return "\n\n".join(blocks)


def email_cast_block(rec, s):
    """The people as the email step needs them: role and side of the firm, nothing of their function in the secret."""
    people = described_people(rec)
    if not people: return cast_block(s, rec["pattern"], rec.get("n"), rec["lines"], rec)
    return "\n".join(f"{e['person']}: {e['role']}, {'at the firm' if e['at_firm'] else 'outside the firm'}." for e in people)


def email_prompt_for(rec, s, rng, prompt_file=None, keep_label=None):
    draw = draw_cast(rec, s, rng)
    p = ((V2 / (prompt_file or EMAIL_PROMPT)).read_text().replace("<<SETTING>>", setting()).replace("<<MAILBOX_STYLE>>", STYLE_CARD)
         .replace("<<CAST>>", email_cast_block(rec, s)).replace("<<PLOTS>>", plots_block(rec, keep_label))
         .replace("<<NAMES>>", candidates_block(draw, rec, s.get("asked_topic") or s.get("label"), rng, s.get("ground", "work"))).replace("<<ERA>>", "2001"))
    return p, draw


def cast_from(em, draw, labels, firm_labels, rng):
    """The model's cast, checked: every placeholder gets one of the ten, on the right side of the firm, none twice.
    What fails is assigned by code, from the unused candidates and then the pools."""
    by_addr = {c["addr"].lower(): c for c in draw["firm"] + draw["outside"]}
    by_name = {c["name"].lower(): c for c in draw["firm"] + draw["outside"]}
    firm_addrs = {c["addr"] for c in draw["firm"]}
    cast = em.get("cast") if isinstance(em.get("cast"), dict) else {}
    names, fixed, taken = {}, [], set()
    for lab in labels:
        v = str(cast.get(lab, "")).strip(); want_firm = lab in firm_labels
        m = re.search(r"[\w.+-]+@[\w.-]+", v)
        c = by_addr.get(m.group(0).lower()) if m else by_name.get(v.lower())
        if c is None or c["addr"] in taken or (c["addr"] in firm_addrs) != want_firm:
            fixed.append(lab); c = None
        if c is None:
            pool = draw["firm"] if want_firm else draw["outside"]
            c = next((x for x in pool if x["addr"] not in taken), None)
            if c is None:                                                  # ten were not enough: one more from the pools
                if want_firm:
                    q = next((p for p in QUIET if p["addr"] not in USED["people"] and p["addr"] not in taken), None)
                    c = {"name": quiet_name(q), "addr": q["addr"], "email_id": q["email_id"]} if q else {"name": "Person " + lab[-1], "addr": f"person.{lab[-1].lower()}@{FIRM_DOMAIN}"}
                else:
                    nm = next(n for n in FRESH["names"] if n not in USED["fresh"] and n not in {x["name"] for x in draw["outside"]})
                    c = {"name": nm, "addr": f"{nm.lower().replace(' ', '.')}@{fresh_domain(rng)}"}
                pool.append(c)
        taken.add(c["addr"]); names[lab] = {"addr": c["addr"], "name": c["name"], "voice": c["addr"], "minted": c["addr"] not in firm_addrs and "email_id" not in c}
    return names, fixed


def finish_emails(rec, s, rng, em, draw):
    """After the model's answer: the cast, the headers, the names in the text, and the checks."""
    plots = rec["plots"]["clues"]
    got = {int(e["i"]): e for e in (em.get("clues") or []) if isinstance(e, dict) and str(e.get("i", "")).strip().isdigit()}
    em["clues"] = [got[i] for i in sorted(got)]
    text = json.dumps(plots, ensure_ascii=False) + json.dumps(rec["lines"], ensure_ascii=False) + json.dumps(em, ensure_ascii=False)
    labels = sorted(set(re.findall(r"Person [A-J]", text)))
    firm = firm_people(s, rec["pattern"], rec.get("n"), labels, rec)
    with USED["lock"]:
        names, fixed = cast_from(em, draw, labels, firm, rng)
        for v in names.values():
            (USED["fresh"] if v["minted"] else USED["people"]).add(v["name"] if v["minted"] else v["addr"])
    rec["names"] = names; rec["cast_fixed"] = fixed; rec["cast_by_model"] = em.get("cast")
    rec["headers_fixed"] = enforce_headers(em, plots)
    expected = set(re.findall(r"Person [A-J]", json.dumps(plots, ensure_ascii=False) + " ".join(keep_line(rec["lines"], c, rec["pattern"]) or "" for c in rec["plan"])))
    bodies0 = " ".join(str(m.get("body", "")) for e in em["clues"] for m in e.get("messages", []))
    chosen = {v["name"].split()[0].lower() for v in names.values()}
    rec["names_off_cast"] = sorted(c["name"] for c in draw["firm"] + draw["outside"] if c["name"].split()[0].lower() not in chosen and re.search(r"\b" + re.escape(c["name"].split()[0]) + r"\b", bodies0))
    rec["names_missing"] = sorted(missing_people(em, expected) - {l for l in expected if any(names[l]["name"].split()[0].lower() in bodies0.lower() for _ in [0]) if l in names})
    return em, names


def emails_for(rec, s, rng, prompt_file=None, keep_label=None):
    p, draw = email_prompt_for(rec, s, rng, prompt_file, keep_label)
    rec["email_prompt_chars"] = len(p)
    plots = rec["plots"]["clues"]
    def _get(prompt):
        em = chat_json(prompt, 0.5, 3000)
        got = {int(e["i"]): e for e in (em.get("clues") or []) if isinstance(e, dict) and str(e.get("i", "")).strip().isdigit()}
        return em, got
    em, got = _get(p)
    if set(got) != set(range(1, len(plots) + 1)):
        em, got = _get(p + f"\n\nReturn exactly {len(plots)} clues, numbered 1 to {len(plots)}, one thread each; a reply belongs inside its clue.")
    if set(got) != set(range(1, len(plots) + 1)):
        rec["error"] = f"email clue set {sorted(got)}"; rec["emails"] = em; return rec
    em, names = finish_emails(rec, s, rng, em, draw)
    for c in em["clues"]:
        for m in c.get("messages") or []:
            m["cc"] = [x for x in (m.get("cc") or []) if x not in (m.get("to") or [])]
    rec["reported"] = {i: str(got[i].get("line", "")).strip() for i in sorted(got) if str(got[i].get("line", "")).strip()}
    rec["emails_placeholders"] = json.loads(json.dumps(em))
    extra = sorted(set(re.findall(r"Person [A-J]", json.dumps(em, ensure_ascii=False))) - set(names))
    if extra:                                                    # a placeholder the model introduced on its own: a firm person from the pool
        more, _ = cast_from({}, {"firm": [], "outside": []}, extra, set(extra), rng)
        for lab, v in more.items(): USED["people"].add(v["addr"])
        names.update(more); rec["names"] = names
    em = name_forms(em, names, rec["plan"]); rec["emails"] = em
    bodies = " ".join(str(m.get("body", "")) for e in em["clues"] for m in e.get("messages", []))
    heads = " ".join(str(m.get("from", "")) + " " + " ".join(m.get("to") or []) for e in em["clues"] for m in e.get("messages", []))
    keys = list(rec["reported"].values()) or [l for l in (keep_line(rec["lines"], c, rec["pattern"]) for c in rec["plan"]) if l]   # the answer key: reported, or the plot's line
    rec["email_verbatim"] = verbatim_in(bodies, [substitute(l, names) for l in keys])
    rec["line_kept"] = line_kept(bodies, [substitute(l, names) for l in keys])          # drift measure; no retry, the email step writes freely
    rec["keys"] = keys
    rec["placeholders_left"] = bool(re.search(r"Person [A-J]\b", bodies + " " + heads))
    rec["names_used"] = all(nm["name"].split()[0].lower() in (bodies + " " + heads).lower() for nm in names.values())
    rec["email_topic"] = classify(bodies[:3000]); rec["email_topic_ok"] = rec["email_topic"] == s.get("label")
    rec["holds_leak"] = holds_leak(rec); rec["isolation"] = isolation(rec); rec["fact_stated"] = fact_stated(rec)
    found = set(re.findall(r"[\w \-().]{2,60}\.(?:doc|xls|pdf|ppt|txt)\b", json.dumps(em) + json.dumps(rec["plots"]), re.I))
    rec["files_copied"] = sorted(f.strip() for f in found if f.strip() in FILES)
    firm = firm_people(s, rec["pattern"], rec.get("n"), list(names), rec)
    firm_names = [names.get(l, {}).get("name", l) for l in firm]
    rec["outside_to_outside"] = [c.get("i") for c in em["clues"] for m in c.get("messages", [])
                                 if firm and not any(nm in " ".join([str(m.get("from", ""))] + list(m.get("to") or []) + list(m.get("cc") or [])) for nm in firm_names)]
    years = set(re.findall(r"\b(19\d\d|20\d\d)\b", json.dumps(em) + json.dumps(rec["plots"])))
    rec["years_out_of_era"] = sorted(y for y in years if y not in ("1999", "2000", "2001", "2002"))
    if JUDGE:                        # off by default: the user checks the lines by hand
        fact = rec["lines"]["fact"]; holder = rec["lines"]["cast"].get("holder", "")
        hname = names.get(holder, {}).get("name", holder)
        line = ""
        for c, carries in zip(em["clues"], rec["plan"]):
            if PAT[rec["pattern"]]["third_atom"] in carries:
                for m in c.get("messages", []):
                    if hname.split()[0].lower() in str(m.get("from", "")).lower(): line = m.get("body", ""); break
                line = line or (c.get("messages") or [{}])[0].get("body", "")
        line = own_text(line)
        q = f"Below is a fact, and a line one person wrote to another about the matter.\n\nfact: {fact}\nline: {line}\n\nWhich is the line? Answer with exactly one of:\n" + "\n".join(KINDS)
        if GEN is not None:
            txt = chat(q + "\nAnswer with the phrase only.", 0.0, 200).strip().lower()
            rec["email_line_kind"] = next((k for k in KINDS if k in txt), txt[:40])
        else:
            rec["email_line_kind"] = chat(q, 0.0, 16, {"structured_outputs": {"choice": KINDS}}).strip().lower()
        rec["email_kind_ok"] = rec["email_line_kind"] == PAT[rec["pattern"]]["line_kind"]
    return rec


SEP = re.compile(r"-{3,}\s*(original message|forwarded|from:)|^\s*from:\s", re.I | re.M)
QUOTE_START = re.compile(r"^\s*-{3,}|original message|forwarded by|^\s*from:\s|\bwrote:\s*$|^\s{4,}\S", re.I)
HEADER_LINE = re.compile(r"^\s{4,}\S|^\s*(to|cc|bcc|subject|date|sent|from)\s*:|^\s*-{3,}|\d{2}/\d{2}/\d{4}", re.I)


def own_text(body):
    """A message body without its quoted tail."""
    m = SEP.search(body or "")
    return (body[:m.start()] if m else body or "").strip()


def outcome_words(rec):
    """Words of what is wrong, not of the matter's name: those must not leave the fact clue."""
    fact = rec["lines"]["fact"]; matter = rec["lines"].get("holds", "")
    return [w for w in re.findall(r"[a-z]{6,}", fact.lower())
            if w not in ("person", "states", "wrote", "writes", "should", "because")
            and w not in re.findall(r"[a-z]{6,}", matter.lower())]


def fact_stated(rec):
    """The fact clue (or the two halves together) must carry the fact: its distinctive words in that text."""
    if not rec.get("emails", {}).get("clues"): return None
    words = outcome_words(rec)
    if not words: return None
    text = " ".join(own_text(m.get("body", "")) for c, carries in zip(rec["emails"]["clues"], rec["plan"])
                    if any(a.startswith("fact") for a in carries) for m in c.get("messages", [])).lower()
    return sum(w in text for w in words) >= max(2, len(words) // 2)


def isolation(rec):
    """Each clue shows its own atom and no other: participants, the outcome's words, the quoted line."""
    if not rec.get("emails", {}).get("clues"): return []
    probs = []
    words = outcome_words(rec)
    names = rec.get("names") or {}
    kept = names.get((rec["lines"]["cast"] or {}).get("kept_from", ""), {}).get("name")
    third = PAT[rec["pattern"]]["third_atom"]
    ref = str(((rec.get("plots") or {}).get("clues") or [{}])[0].get("reference", "")).lower()
    line = " ".join(rec["lines"]["third"]["holder_line"].lower().replace(ref, " ").split())[:30] if ref else " ".join(rec["lines"]["third"]["holder_line"].lower().split())[:30]
    for c, carries in zip(rec["emails"]["clues"], rec["plan"]):
        text = " ".join(own_text(m.get("body", "")) for m in c.get("messages", [])).lower()
        who = " ".join(str(m.get("from", "")) + " " + " ".join((m.get("to") or []) + (m.get("cc") or [])) for m in c.get("messages", []))
        if not any(a.startswith("fact") for a in carries) and words and sum(w in text for w in words) >= max(3, len(words) // 2):
            probs.append(f"clue {c.get('i')} ({', '.join(carries)}) reads the outcome")
        if third not in carries and line and line in " ".join(text.split()):
            probs.append(f"clue {c.get('i')} ({', '.join(carries)}) carries the holder's line")
        if len(rec["plan"]) > 2 and kept and third not in carries and kept in who:
            probs.append(f"clue {c.get('i')} ({', '.join(carries)}) has the person kept from the fact on it")
    return probs


def holds_leak(rec):
    """The fact must not be readable from the holds clue: its distinctive words absent from the holds clue's own text."""
    if "holds" not in [a for cl in rec["plan"] for a in cl]: return None
    fact = rec["lines"]["fact"]; matter = rec["lines"]["holds"]
    words = [w for w in re.findall(r"[a-z]{6,}", fact.lower()) if w not in ("person", "states", "wrote", "writes", "should", "because")
             and w not in re.findall(r"[a-z]{6,}", matter.lower())]        # words of the outcome, not of the matter's name
    for c, carries in zip(rec["emails"]["clues"], rec["plan"]):
        if carries == ["holds"]:
            text = " ".join(own_text(m.get("body", "")) for m in c.get("messages", [])).lower()
            hit = sum(w in text for w in words)
            return hit >= max(3, len(words) // 2)
    return None


PLOTS_ONLY = False


KEEP_WORDS = ("quietly", "secret", "confidential", "discreet", "not to mention", "without telling", "without flagging", "without explanation", "has not told", "hasn't told", "keep it between", "off the record", "conceal", "hide", "hidden", "without alerting", "without informing", "without mentioning", "unnoticed", "so that no one", "so that nobody", "never told", "not yet told")


def keeping_words(text):
    """Words that say hiding, which [fact] and [knows] must not: the gate wants those parts innocent alone."""
    low = str(text or "").lower()
    return sorted({w for w in KEEP_WORDS if w in low})


STOPW = set("the a an and or of to in on for with is are was were be been it its this that his her their he she they them at by from not no who whom which keeps keep kept from actor victim person secret fact about while during".split())


def secret_words(rec):
    """Content words of the secret sentence, by five-letter stem, for the subject-line check."""
    return {w[:5] for w in re.findall(r"[a-z]+", str(rec.get("secret", "")).lower()) if len(w) >= 5 and w not in STOPW}


def plot_checks(rec):
    """What can be read off the plot before any email is written."""
    if rec.get("error"): return [rec["error"]]
    probs = []; cast = rec["lines"].get("cast") or {}; clues = rec["plots"]["clues"]
    third = PAT[rec["pattern"]]["third_atom"]
    refs = {str(c.get("reference", "")).strip().lower() for c, carries in zip(clues, rec["plan"]) if third not in carries}   # Person B's thread has its own name
    # no shared-reference check: a thread names the matter or not, per thread
    pass
    dates = {}; people = {}
    for c, carries in zip(clues, rec["plan"]):
        ms = c.get("messages") or [c]
        who = set()
        for m in ms:
            to = m.get("to"); to = to if isinstance(to, list) else [to]
            who |= {str(m.get("from"))} | {str(x) for x in to} | {str(x) for x in (m.get("cc") or [])}
        people[c.get("i")] = who; dates[tuple(carries)] = [str(m.get("date", "")) for m in ms]
        pass  # a clue may carry no name of the matter (2026-09-20)   # the victim's thread has its own name
        if third in carries and cast.get("record_writer") in who: probs.append(f"clue {c.get('i')}: the record writer is on the holder's thread")
        if third in carries:
            saw = {p for i2, cc2 in zip(clues, rec["plan"]) if any(a.startswith("fact") for a in cc2) for p in people.get(i2.get("i"), set())} - {cast.get("holder"), cast.get("kept_from")}
            if saw & who: probs.append(f"clue {c.get('i')}: {', '.join(sorted(saw & who))} saw the fact clue and is on the holder's thread")
        if third not in carries and len(rec["plan"]) > 2 and cast.get("kept_from") in who: probs.append(f"clue {c.get('i')}: the person kept from the fact is on it")
        if "holds" in carries and "fact" not in carries and cast.get("holder") not in who: probs.append(f"clue {c.get('i')}: holds clue without the holder")
        if "fact" in carries and "holds" not in carries and cast.get("holder") in who: probs.append(f"clue {c.get('i')}: Person A is on the [fact] thread")
        if third not in carries:
            kw = keeping_words(" ".join(str(m.get("what_happens", "")) + " " + str(m.get("subject", "")) for m in c.get("messages") or [c]))
            if kw: probs.append(f"clue {c.get('i')}: keeping words in a [fact]/[knows] thread: {', '.join(kw)}")
        if len(c.get("messages") or []) > 3: probs.append(f"read: clue {c.get('i')}: {len(c['messages'])} messages; a clue is one thread of a few")
        if len(str(c.get("reference", "")).split()) > 6: probs.append(f"read: clue {c.get('i')}: the reference field holds a sentence, not a name")
        if third not in carries:
            names = re.sub(r"person [a-j]\b", " ", " ".join([str(c.get("reference", ""))] + [str(m.get("subject", "")) for m in c.get("messages") or []]).lower())
            shared = sorted({w for w in secret_words(rec) if w in names})
            if shared: probs.append(f"read: clue {c.get('i')}: a subject or reference shares a word with the secret: {', '.join(shared)}")
        for m in c.get("messages") or []:
            if len(str(m.get("what_happens", "")).split()) > 70: probs.append(f"read: clue {c.get('i')}: a what_happens of {len(str(m['what_happens']).split())} words; the model narrates")
        for m in c.get("messages") or []:
            to = m.get("to"); to = to if isinstance(to, list) else [to]
            if str(m.get("from", "")).strip() and str(m.get("from", "")).strip() in [str(x).strip() for x in to]: probs.append(f"clue {c.get('i')}: {m.get('from')} emails themselves")
        if "holds" in carries and "fact" not in carries:
            body = " ".join(str(m.get("what_happens", "")) + " " + str(m.get("subject", "")) for m in c.get("messages") or []).lower()
            stems = lambda s: {w[:5] for w in re.findall(r"[a-z]+", str(s).lower()) if len(w) >= 5 and w not in STOPW}
            fw = stems((rec.get("lines") or {}).get("fact", "")) - stems((rec.get("lines") or {}).get("holds", ""))   # fact words the [knows] part itself does not use
            shared = sorted({w for w in fw if w in body})
            if shared: probs.append(f"read: clue {c.get('i')}: the [knows] thread adds words of the fact beyond its part: {', '.join(shared)}")
        if third in carries and rec["pattern"] == "lying by omission":
            line = " " + str(c.get("line", "")).lower() + " "
            if any(x in line for x in (" no ", " not ", " never ", " none ", "denies", "states explicitly", "nothing on my")): probs.append(f"read: clue {c.get('i')}: an omission line that asserts or denies; is it still omission?")
        if third in carries and "unprompted" in str((rec.get("slots") or {}).get("carrier_conflict", "")).lower():
            first = (c.get("messages") or [{}])[0]
            if str(first.get("from", "")).strip() != cast.get("holder"): probs.append(f"clue {c.get('i')}: the occasion is unprompted but Person A does not write first")
        if len(ms) > 4: probs.append(f"clue {c.get('i')}: {len(ms)} messages")
    if rec.get("plot_invented"): probs.append("names invented: " + ", ".join(rec["plot_invented"]))
    if rec.get("plot_retry_firm"): probs.append("retried: a message with nobody at the firm")
    facts = [d for k, v in dates.items() for d in v if any(a.startswith("fact") for a in k)]; thirds = [d for k, v in dates.items() for d in v if third in k]
    if facts and thirds and max(facts) > min(thirds): probs.append("the fact is dated after the holder's line")
    probs += timeline_checks(rec)
    if rec.get("choices_commentary"): probs.append("read: choices with a gloss instead of the option: " + ", ".join(rec["choices_commentary"]))
    return probs


def timeline_checks(rec):
    """The messages sit on the timeline: every message date is an event date, events run earliest to latest, and the event tagged
    with the first part comes no later than the one tagged with the act."""
    tl = rec.get("timeline") or []
    if not tl: return ["no timeline"]
    probs = []
    ds = [e["date"] for e in tl]
    if ds != sorted(ds): probs.append("timeline not in date order")
    if any(not re.fullmatch(r"(2000|2001)-\d\d-\d\d", d) for d in ds): probs.append("timeline date outside 2000-2001")
    lab = labels(rec["pattern"]); first, last = lab[0], lab[2]
    tagged = {e["shows"]: e["date"] for e in tl if e["shows"]}
    if first in tagged and last in tagged and tagged[first] > tagged[last]: probs.append(f"[{first}] event dated after [{last}] event")
    from datetime import date as _d
    def day(s):
        try: return _d.fromisoformat(str(s))
        except Exception: return None
    off = []
    for c in rec["plots"]["clues"]:
        prev = None
        for m in c.get("messages") or []:
            d = str(m.get("date", ""))
            if d not in ds:   # a reply within a week of a timeline event is accepted
                pd, dd = day(prev), day(d)
                if not (prev in ds and pd and dd and 0 <= (dd - pd).days <= 7): off.append(d)
            prev = d
    if off: probs.append("message dates not on the timeline: " + ", ".join(sorted(set(off))))
    return probs


def run_chain(job):
    s, pattern, n, seed = job
    rng = random.Random(seed)
    rec = {"pattern": pattern, "n": n, "topic": s.get("label"), "secret": s.get("secret")}
    try:
        plot_for(rec, s, pattern, n, rng)
        if rec.get("error"): return rec
        rec["plot_checks"] = plot_checks(rec)
        if PLOTS_ONLY: return rec
        emails_for(rec, s, rng)
    except Exception as e:
        rec["error"] = f"exception: {e}"
    return rec


def cmd_chains(a):
    st = load(); rng = random.Random(a.seed)
    facts = [s for s in st["secrets"] if any(passes(s, p) for p in patterns_for(s))]
    if a.per_topic:
        by = defaultdict(list)
        for s in facts: by[s["asked_topic"]].append(s)
        facts = [s for t in sorted(by) for s in by[t][:a.per_topic]]
    else:
        rng.shuffle(facts); facts = facts[:a.facts]
    jobs = [(s, p, n_for(i, j, a.vary_n), rng.random()) for i, s in enumerate(facts) for j, p in enumerate(LYING) if passes(s, p)]
    done = {(r.get("secret"), r.get("pattern")) for r in st.get("chains", []) if not r.get("error")} if a.append else set()
    jobs = [j for j in jobs if (j[0].get("secret"), j[1]) not in done]
    print(f"{len(jobs)} chains from {len(facts)} secrets" + (f", {len(done)} kept from before" if done else ""), flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        new = list(ex.map(run_chain, jobs))
    st["chains"] = ([r for r in st.get("chains", []) if not r.get("error")] if a.append else []) + new
    st.setdefault("calls", {})["chains" if not PLOTS_ONLY else "plots"] = dict(CALLS, empty_replies=EMPTIES["n"]); save(st)
    if PLOTS_ONLY:
        print(f"\n== plots {sum(not r.get('error') for r in new)}/{len(new)}; chains with a plot finding {sum(bool(r.get('plot_checks')) for r in new)}")
        for r in new:
            for x in r.get("plot_checks") or []: print(f"   {r['pattern'][:12]:12s} {str(r.get('topic'))[:16]:16s} n={r['n']}  {x}")
        print("calls:", CALLS); return
    cmd_report(a)
    print("calls:", CALLS, "empty replies:", EMPTIES["n"])


def value_tally(ch):
    """How often each slot value was drawn, and how often its chain came out clean."""
    seen = defaultdict(lambda: [0, 0])
    for r in ch:
        clean = not r.get("error") and (r.get("line_kept") or 0) >= 0.6 and not r.get("isolation") and not r.get("holds_leak")
        for axis, v in (r.get("slots") or {}).items():
            seen[(axis, v)][0] += 1; seen[(axis, v)][1] += bool(clean)
    return seen


def cmd_report(a):
    st = load(); ch = st.get("chains", [])
    ok = [r for r in ch if not r.get("error")]
    print(f"\n== chains {len(ok)}/{len(ch)} completed; errors: {Counter(r.get('error', '')[:40] for r in ch if r.get('error'))}")
    for p in LYING:
        rs = [r for r in ok if r["pattern"] == p]
        if not rs: continue
        line = (f"   {p:22s} n={len(rs)}: holder line verbatim {sum(r['email_verbatim'] for r in rs)}, kept in substance (>=0.6) {sum((r.get('line_kept') or 0) >= 0.6 for r in rs)}; names used {sum(r['names_used'] for r in rs)}, placeholders left {sum(r['placeholders_left'] for r in rs)}, "
                f"headers put back {sum(bool(r.get('headers_fixed')) for r in rs)}, people retried {sum(bool(r.get('names_retry')) for r in rs)}, still missing {sum(bool(r.get('names_missing')) for r in rs)}; "
                f"email topic = label {'n/a' if all(r.get('email_topic') is None for r in rs) else sum(bool(r.get('email_topic_ok')) for r in rs)}; years out of era {sum(bool(r['years_out_of_era']) for r in rs)}")
        line += f"; attachment names copied from the bank {sum(bool(r.get('files_copied')) for r in rs)}; clue emails with no one at the firm {sum(bool(r.get('outside_to_outside')) for r in rs)}"
        line += (f"; judge agrees {sum(r.get('email_kind_ok', False) for r in rs)}" if JUDGE else "") + f"; holds clue leaks the fact {sum(bool(r.get('holds_leak')) for r in rs)} of {sum(r.get('holds_leak') is not None for r in rs)}; fact missing from its clue {sum(r.get('fact_stated') is False for r in rs)}"
        line += f"; clues not isolated {sum(bool(r.get('isolation')) for r in rs)}"
        print(line)
    tally = value_tally(ok)
    if tally:
        print("\n== slot values drawn (drawn / of those, chains with no code finding)")
        for (axis, v), (n, good) in sorted(tally.items()):
            print(f"   {axis:11s} {n:>3} / {good:<3} {v[:70]}")
    print(f"\n== casting: cast by the model and kept {sum(not r.get('cast_fixed') for r in ok)} of {len(ok)}; names invented outside the cast {sum(bool(r.get('names_off_cast')) for r in ok)}")


def cmd_all(a):
    cmd_secrets(a); cmd_clues(a); cmd_chains(a)


if __name__ == "__main__":
    from src.models.engine_factory import add_engine_args, engine_from_args
    ap = add_engine_args(argparse.ArgumentParser(description="the four generation steps; see the module docstring"))
    ap.add_argument("--state", default=str(STATE), help="the run's state file: secrets, parts, chains")
    ap.add_argument("--judge", action="store_true", help="also ask the model which kind of line each [conflict] email is (a measurement)")
    ap.add_argument("--classify", action="store_true", help="file each secret under the topic the model reads off its fact, instead of the asked topic")
    ap.add_argument("--max-calls", type=int, default=0, help="stop the run once this many model calls have been made (0 = no cap); the money guard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    def step1(s):
        s.add_argument("--k", type=int, default=1, help="secrets per (topic, kind) pair"); s.add_argument("--topics", default="", help="comma list of tier-1 topics; default: the whole pool")
        s.add_argument("--kinds", default="", help="comma list of kinds of secret; default: every kind a topic can hold"); s.add_argument("--append", action="store_true", help="keep the secrets already in the state file")
        s.add_argument("--per-topic", type=int, default=0, help="keep calling a topic until it has this many secrets")
    def step3(s):
        s.add_argument("--facts", type=int, default=12, help="how many secrets go to steps 3 and 4"); s.add_argument("--seed", type=int, default=0)
        s.add_argument("--vary-n", action="store_true", help="2, 3 and 4 clues in turn instead of 3"); s.add_argument("--plots-only", action="store_true", help="stop after step 3: no cast, no emails")
    s1 = sub.add_parser("secrets", help="step 1"); step1(s1); s1.add_argument("--workers", type=int, default=12)
    s2 = sub.add_parser("clues", help="step 2"); s2.add_argument("--workers", type=int, default=12); s2.add_argument("--per-topic", type=int, default=0)
    s3 = sub.add_parser("chains", help="steps 3 and 4"); step3(s3); s3.add_argument("--workers", type=int, default=8); s3.add_argument("--append", action="store_true"); s3.add_argument("--per-topic", type=int, default=0)
    s4 = sub.add_parser("report", help="counts over the state file")
    s5 = sub.add_parser("all", help="steps 1 to 4 in one run"); step1(s5); step3(s5); s5.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    STATE = Path(a.state); JUDGE = a.judge; NOCLASS = not a.classify; PLOTS_ONLY = getattr(a, "plots_only", False); GEN_KIND = a.engine; MAX_CALLS = a.max_calls
    GEN = engine_from_args(a)
    try:
        {"secrets": cmd_secrets, "clues": cmd_clues, "chains": cmd_chains, "report": cmd_report, "all": cmd_all}[a.cmd](a)
    except RuntimeError as e:
        if "max-calls" not in str(e): raise
        print(f"\nstopped: {e}; what was finished is in {STATE}")
    if a.cmd not in ("chains", "all"): print("calls:", CALLS)
