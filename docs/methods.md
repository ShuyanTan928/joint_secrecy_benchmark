# Methods — the background pool

How the 2,000-email mailbox was selected from the Enron corpus, and how it was anonymized. Every
number here is measured on the data in this repository and reproducible from the scripts named.
The README summarises the result; this file is the record.

Real mail, unmodified except for anonymization. It is what makes the planted clues hard to find, and
the source of the anchors the items are grounded in.

### A.1 Source

Enron email corpus, 2015-05-07 release: 517,401 messages, 150 custodian mailboxes, 173,601 threads.
**The unit is the individual email, not the thread** — every count, quota and filter is per message.

### A.2 Eligibility filters

Deterministic, no model. Applied per message over the full corpus:

| filter | rule | dropped |
|---|---|---|
| bulk / newsletter | `<html`, `<meta`, `<table`, `unsubscribe`, `click here to`, tracking domains | 8,286 |
| auto-generated | folder sync, out-of-office, undeliverable, delivery status, automated reply | 3,269 |
| non-prose | alphabetic+space ratio below 0.75 (pasted tables, encoding garbage) | 25,553 |
| mostly quoted | more than 60% of lines are `>`-quoted or header lines | 1,885 |
| near-duplicate | MD5 of the first 240 chars of subject+body, lower-cased, whitespace-collapsed | 189,523 |
| length band | outside [30, 500] tokens (A.3) | remainder |

Near-duplicates are a third of the corpus — the release contains each message up to three times.
Commercial mail that passes the bulk filter is **kept**: IAB treats it as content, it is 3.5% of the
eligible pool, it is what real 2001 inboxes contained, and as mass mail it names no private individual.

**Result: 133,252 eligible emails** (25.8% of the corpus), full text retained.

### A.3 Own body, and the length band

- **Own body.** Everything after `-----Original Message-----` / `---- Forwarded by` is removed, along
  with `>`-quoted lines and `From:/To:/Cc:/Subject:` headers. 39% of eligible mail is a reply or
  forward, and on a keyword probe 11–23% of topic matches came from the inherited subject line or the
  quoted parent rather than anything the sender wrote. A reply saying "sounds good" is not *about* the
  topic it answers.
- **What each stage sees.** The length band is computed on the own body alone. The classifier sees the
  own body **plus the subject** — and the subject only for messages that are not `RE:`/`FW:`, since a
  reply inherits its subject rather than writing one.
- **Bounded in tokens**, not words, using the classifier's own tokenizer: 1.55 tokens/word median on
  30,000 eligible emails (p10 1.27, p90 2.44). Email is dense with numbers, addresses and contract
  references.
- **Floor 30 tokens** (~20 words): below this a message is a procedural handoff with no subject matter.
- **Ceiling 500 tokens** (~300 words): the multi-topic rate by own-body length is ≤1% under 300 words,
  4% at 300–449, 9% at 450–699, 42% past 700. One-email-one-topic holds below ~300 words and fails
  above it.

The band is tokenizer-specific and is recorded with the corpus.

### A.4 Taxonomy

**IAB Content Taxonomy v3.1**, tier 1, from the official TSV. The file has 37 tier-1 rows; 36 are
subject categories. The 37th, *Sensitive Topics*, is a brand-suitability dimension orthogonal to
subject — an article about a terrorist attack is simultaneously `war and conflicts` and `Terrorism` —
so it is excluded rather than offered as a 37th mutually-exclusive choice.

One label, **`other`, is ours**: it appears nowhere in IAB at any tier. A page that fits nothing is
simply left untagged in IAB, an option a forced-choice classifier does not have. Total label set:
**36 + `other` = 37** (`prompts/iab_tier1.txt`).

Labels are written lower-case with `&` spelled `and` — with `&` in the list the model answered
`Technology and Computing` for `Technology & Computing`, producing phantom disagreements between
messages of one thread. Official spelling is recovered through `prompts/iab_official_names.json`.

Using a *published* taxonomy is the point: a topic list written by reading the corpus reproduces the
corpus's skew. An external list makes the coverage claim checkable and makes gaps visible as gaps.
(v3.1 over v2.2, which put 66.5% of this corpus in `business and finance`; v3.1 drops that to 63.0%
and adds `law`, `politics`, `crime`, `disasters`, `war and conflicts` and others. Residual gaps the
classifier asks for and v3.1 has no tier-1 home for: weather, transportation, charity/nonprofit.)

### A.5 Classification

Qwen3-32B served locally with vLLM, tensor parallel 4, thinking off, temperature 0, 24 max output
tokens. The prompt (`prompts/topic_classify.md`) is the 37 labels, the email, and `topic:` as a
completion cue — no examples, no formatting instructions, no negative instructions.

**Constrained decoding** restricts the sampler to emitting exactly one of the 37 labels
(`StructuredOutputsParams(choice=...)`), enforced at the token level rather than asked for in the
prompt. Without it — a free-text pass over the same 133,252 emails — 1.9% of answers named no listed
label: the model either invented one (`weather` 87, `transportation` 22, `charity` 17, … ~990 cases)
or declined to choose (~1,567 cases). Under constraint that bucket is empty. `--free-text` reproduces
the unconstrained behaviour, which is what surfaced the taxonomy gaps above.

Output: `data/topics/labels.jsonl`, one label per `message_id`.

> An embedding second opinion (`scripts/classify_topics_embed.py`, BAAI/bge-large-en-v1.5) agreed only
> 32.6% (κ 0.176), but cosine scores spanned just 0.465–0.555 across the whole corpus, so its argmax is
> close to noise; in every inspected disagreement the LLM was right. Reported for completeness, not used.

### A.6 Sampling — `scripts/sample_dataset.py`

Target: 2,000 emails, equal count per topic, `other` counted as one topic, threads not broken.

1. **Buckets.** Categories below `--min-pool` fold into `other`, together with the classifier's own
   `other`.
2. **Allocation.** `2000 / buckets` each; the remainder goes to the deepest pools, so a thin bucket is
   never asked for mail it does not have.
3. **Sub-threads.** Every thread is split at the topic boundary into per-topic sub-threads — the
   sampling unit, drawn whole with its own id. (A drift check on 180 threads found 81% single-label,
   ~13–15% true drift, so a thread is a valid unit as long as mixed ones are split rather than
   discarded.) 57.7% of eligible emails are singletons in their thread, which is what makes an exact
   count reachable without cutting a thread.
4. **Draw.** Per bucket, round-robin over lead sender — one sub-thread per sender in rotation.
   Multi-email sub-threads first, taken only while the whole sub-thread fits the remaining quota;
   singletons then land the exact count. This is what removes raw-pool skew: `medical health` was 18.7%
   one sender and 23.5% one month; after round-robin the top sender across the whole sample is ~2%.
5. Seeded. The manifest records configuration, per-bucket allocation, merged categories, sender/month
   spread, and a SHA-256 digest of the source ids.

> A rebuilt mailbox that has no thread map (`data/topics/mid2tid.json`) gets one from
> `scripts/sample_dataset.py`: the labelled pool threaded by normalized subject with RE:/FW: prefixes
> stripped. The released mailbox's map came from the parent corpus's threading (subject and
> participants), which that recipe reproduces thread-by-thread but merges some same-subject threads.

### A.7 Identifiers and anonymization

Source `message_id` values are direct lookup keys into the public corpus — one search recovers the real
sender and recipients regardless of any change to the text. The released files carry none of them.
Released ids are `e_NNNNNN` / `t_NNNN`, assigned in seeded-shuffled order so the numbering encodes
nothing, plus `thread_pos` / `thread_len`. There is **no `reply_to` field**: `in_reply_to` is empty on
all 517,401 source messages (the corpus was threaded by subject and participants), so chronological
position is the only thread structure the source honestly supports. The id map back to source ids is
gitignored.

**The unit is the person, not the string.** The released mailbox was anonymised in two passes: a model
lists the people in each email (`scripts/extract_people.py`, `prompts/people_extract.md`; it tags and links
names, never invents a replacement, never sees the map), then code merges the claims into people, gives
each one pseudonym and rewrites only the tagged spans (`scripts/anonymize_llm.py`, a pure function of the
extraction file and the seed). A second model pass re-reads the output for surviving names
(`scripts/audit_names.py`), and `scripts/make_release.py` measures the result into the manifest. The
registry, name pools and collision rules below live in `scripts/name_registry.py`. One human appears as
`kay.mann@enron.com`, `Kay Mann`, `Mann, Kay`, `KAY MANN`, `Kay Mann/HOU/ECT@ECT`, bare `Kay`, `Kay's`,
and by nickname. Identities resolve to `(first, last)` with nicknames canonicalised; each person gets
one pseudonym; every surface form is rewritten to the matching form.

- **Identity sources**: the corpus address book (20,324 senders — `first.last@enron.com` is a name in
  disguise), the sample's own senders, Lotus Notes handles, header lines, `Last, First` forms, and
  First-Last bigrams accepted only when both halves are already known names. Tokens from system and
  role mailboxes and English function words are never names — without that rule "Enron" became a first
  name and `Ted Yes` became a person.
- **Substitution order**, most specific first: addresses; full names in any case; `Last, First`; bare
  surname and bare first name for people established in that email; a global pass for unambiguous bare
  first names (≥4 letters, not an English word — `Mark`, `Bill`, `May`, `Grant` excluded, because
  `Mark to Market` is not a person); companies, with `enron` replaced as a **substring** so
  `ENRON_DEVELOPMENT` and `enronXgate` do not survive word boundaries; every domain.
- **Placeholders.** Every substitution writes a letterless placeholder; pseudonyms are inserted only at
  the end. Without this, later passes rewrote earlier passes' output — pseudonym first names overlap
  real first names — producing `Ann Kenneth` and `Doris Kenneth`.
- **Three collision classes are excluded**, each found empirically: a pseudonym equal to a real person
  (one run produced 106, 90 of them real Enron employees); a pseudonym reusing the subject's own name
  (`Kay Mann → Kay Shackleton` still names her; 1 in 6,167 on the census pool); and a real name spelled
  *across* a boundary, invisible to a per-pseudonym check — caught by the output scanner, so the
  pipeline **self-heals**, redrawing the pseudonyms that supplied either half and rewriting, up to
  `--max-redraws`.
- **Name pools** (`--name-pool`): `census` (default) is SSA first names × Census 2010 surnames, both US
  government public domain, ~1.2 billion combinations. `corpus` recombines the address book's own names
  — era-realistic, but two adjacent pseudonyms can jointly spell a third real person, so not the default.
- **Fail-closed.** The output is rescanned for any real address, any adjacent word pair that is a real
  registry name, and the `enron` substring. The run exits non-zero on a hit.
