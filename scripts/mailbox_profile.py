#!/usr/bin/env python3
"""Run once per mailbox: a profile of how its mail reads, and a bank of real subject lines that
name a matter. The profile is what prompts/mailbox_style.md was written from by hand; the plot step
draws real subject lines from the bank. No model.

  python scripts/mailbox_profile.py        -> benchmark_pool/mailbox_profile.json, benchmark_pool/reference_bank.json
"""
import json, re, collections, statistics
from pathlib import Path

M = [json.loads(l) for l in open("data/release/background_2000.jsonl")]
MAP = json.load(open("data/topics/sample_anon.jsonl.map.json"))
FIRM_DOMAIN = MAP["domains"].get("enron.com", "")
own = [m["own_body"] for m in M if m.get("own_body")]
n = len(own)


def rate(pat, texts=own, flags=0):
    return round(sum(bool(re.search(pat, b, flags)) for b in texts) / len(texts), 3)


def first_line(b):
    return next((l.strip() for l in b.strip().split("\n") if l.strip()), "")


wc = sorted(len(b.split()) for b in own)
greet = collections.Counter()
for b in own:
    fl = first_line(b).lower()
    m = re.match(r"(hi|hello|hey|dear|good morning|good afternoon)\b", fl)
    if m: greet[m.group(1)] += 1
    elif re.match(r"^[a-z]+( and [a-z]+)?[,:\-]\s*", fl) and len(fl.split()) <= 4: greet["name only"] += 1
    else: greet["none"] += 1
signoff = collections.Counter()
for b in own:
    tail = " ".join(b.strip().split("\n")[-3:]).lower()
    m = re.search(r"\b(thanks|thank you|thx|regards|best regards|best|sincerely|cheers|take care)\b", tail)
    signoff[m.group(1) if m else "none"] += 1
body = [m["body"] for m in M if m.get("body")]
subj = [m.get("subject", "") for m in M]
profile = {
    "emails": len(M), "senders": len({m["from"] for m in M}), "share_from_firm": round(sum(m["from"].endswith("@" + FIRM_DOMAIN) for m in M) / len(M), 3),
    "own_body_words": {"median": wc[n // 2], "p25": wc[n // 4], "p75": wc[3 * n // 4], "share_under_30": round(sum(w <= 30 for w in wc) / n, 3)},
    "greeting_first_line": {k: round(v / n, 3) for k, v in greet.most_common()},
    "sign_off_last_lines": {k: round(v / n, 3) for k, v in signoff.most_common()},
    "all_lowercase": round(sum(b == b.lower() and any(c.isalpha() for c in b) for b in own) / n, 3),
    "punctuation": {"exclamation": rate(r"!"), "double_exclamation": rate(r"!!"), "ellipsis": rate(r"\.\.\."), "spaced_dash": rate(r" - "), "double_dash": rate(r"--"),
                    "question": rate(r"\?"), "two_spaces_after_period": rate(r"\.  [A-Z]"), "digits": rate(r"\d")},
    "signature": {"phone_number": rate(r"\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}"), "sent_from_device": rate(r"Sent from my")},
    "quoting_in_full_bodies": {"lotus_to_cc_subject_block": rate(r"\n\s*To:\s.*\n\s*cc:", body), "original_message_separator": rate(r"-----\s*Original Message\s*-----", body),
                               "forwarded_by_line": rate(r"Forwarded by .* on \d", body), "x_wrote": rate(r"\bwrote:\s*\n", body)},
    "subject": {"words_median": statistics.median(len(s.split()) for s in subj if s),
                "prefix": {k: round(v / len(subj), 3) for k, v in collections.Counter((re.match(r"^(re|fw|fwd)\b", s.strip().lower()) or [None])[0] or "none" for s in subj).items()}},
    "thread_len": dict(sorted(collections.Counter(int(m["thread_len"]) for m in M).items())),
    "reference_forms_in_bodies": {"date": rate(r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b"), "file_name": rate(r"\b[\w \-]{2,40}\.(doc|xls|pdf|ppt|txt)\b", own, re.I),
                                  "hash_number": rate(r"#\s?\d{3,7}\b"), "order_or_account_number": rate(r"\b(order|account|acct|invoice|contract|deal)\s*(no\.?|number|#)?\s*[:#]?\s*[A-Z]?\d{3,8}\b", own, re.I),
                                  "named_matter (Strawflower Plant, Option Agreement)": rate(r"\b[A-Z][a-z]+ (?:[A-Z][a-z]+ )?(Project|Deal|Agreement|Contract|Facility|Pipeline|Plant|Report|Memo|Proposal|Case|Matter|Review|Property|Lease)\b")},
}
Path("benchmark_pool/mailbox_profile.json").write_text(json.dumps(profile, indent=1))

# reference bank: real subject lines that name a matter, without people's names
names = set()
for v in MAP["people"].values():
    names.update(w.lower() for w in v["fake"].split())
stop = {"fyi", "hello", "hi", "dinner", "lunch", "thanks", "thank you", "question", "update", "meeting", "reminder", "re", "darn", "security", "test", "hey", "help", "call", "info", "request", "schedule", "today", "tomorrow", "yes", "no", "ok"}
bank, seen = [], set()
for s in subj:
    t = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", s.strip(), flags=re.I).strip()
    k = t.lower()
    if not t or k in seen or k in stop or not 2 <= len(t.split()) <= 7: continue
    if re.search(r"<<|>>|@|http|!{2}|\$\$|free|click|\s{3,}|\.{3,}", t, re.I) or t.isupper(): continue
    if any(w.strip(",.:-()'\"").lower() in names for w in t.split()): continue
    if re.search(r"[A-Za-z]+\d+|\*|[\"“”!\[\]:]|\.(com|org|net)\b|^(your|my|our|happy|hello|hi|hey|good|wrong|getting|thank|welcome|congrat)", t, re.I) or t == t.lower(): continue
    matter = (r"\b(agreement|contract|sale|lease|property|title|invoice|order|template|report|memo|notice|letter|policy|plan|proposal|draft|schedule|review|audit|filing|application|permit|claim|amendment|budget|forecast|deal|project|conveyance|closing|settlement|renewal|extension|assignment|transfer|option|bid|rfp|study|survey|issue|issues|motion|motions|capacity|tariff|hearing|subpoena|deposition|negotiation|term sheet|loi|prepay|curtailment|outage|pipeline|plant|storage|transport|nomination|imbalance|credit|guaranty|isda|confirmation|confirm|payment|tax|insurance|benefits|payroll|offer|resume|interview|position|relocation|training|seminar|conference|committee|regulation|legislation|petition|complaint|dispute|resolution|remediation|inspection|license|certificate|registration|approval|authorization|waiver|release|indemnity|warranty|purchase|acquisition|merger|financing|loan|bond|equity|valuation|appraisal|estimate|quote|pricing|rate|rates|volume|volumes|meter|well|lands|easement|right of way|survey|environmental|safety|incident|accident|injury|medical|leave|vacation|expense|expenses|reimbursement|travel)\b")
    if not re.search(matter, t, re.I): continue
    seen.add(k); bank.append(t)
Path("benchmark_pool/reference_bank.json").write_text(json.dumps(bank, indent=1, ensure_ascii=False))
print(json.dumps(profile, indent=1)); print(f"\nreference bank: {len(bank)} subjects, e.g. {bank[:15]}")
