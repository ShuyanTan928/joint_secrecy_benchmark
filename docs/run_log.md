# Sonnet run, 2026-09-17

Three runs of `scripts/experiments/fourstep.py --engine api --preset or-claude-sonnet --no-classify --state logs/fourstep_sonnet.json`
on three topics (medical health, personal finance, travel): `secrets --per-topic 2` (the new AVOID loop: a second call per
topic lists the first call's fact), `clues --per-topic 1`, `chains --per-topic 1 --vary-n`. 12 chains each: 3 facts x 3 lying
patterns + 3 role pairs, n = 2..4. About 40 generator calls a run; no local classifier, so secrets are filed under the asked topic.
State files: `logs/fourstep_sonnet_run1.json`, `_run2.json`, and `logs/fourstep_sonnet.json` (run 3). Emails of run 3 are on the
review page's "Generated emails" tab (https://claude.ai/code/artifact/f6c05aed-c23c-4f9e-a0f1-a01901af383f).

## Bugs found and fixed between runs

| run | bug | fix |
|---|---|---|
| 1 | n = 2: clue 1 followed the holds rule and never stated the fact | clue_block writes one merged description for a fact+holds clue |
| 1 | step 2 fact line described the record ("C confirms to A that...") | clues.md task 2: the fact as a plain statement, not who told whom |
| 1 | carrier "the person the fact is about" drawn when that person is the holder | draw_slots excludes it when about == holder |
| 1 | same two senders cast as holder and spouse in 7 of 12 chains, then as doctor and vendor | USED set across the run; a fresh real pair if any, else fresh people one by one; casting serialized by a lock |
| 1 | role-pair audiences invented by the plot step (both roles to the same vendor) | secret_roles.md outputs to_1 / to_2; cast and clue blocks print them |
| 1 | a person in both to and cc; "Person B, can you" kept the full name | cc deduped against to; vocative-before-comma rule in name_forms |
| 2 | two clue emails from an outside person to herself | plot.md: someone at the firm on every message; plot retry when not |
| 2 | role audiences always cast outside the firm | firm_people: to_1/to_2 mentioning employer/supervisor/colleague/HR/Ironwood are at the firm |
| 2 | isolation check misfired when the key line began with the reference | reference stripped from the line before the prefix check |
| 2 | new check: fact_stated (fact's words in its clue's own text) | reported as "fact missing from its clue" |

Run 3: 12/12 chains, no code flags. Remaining by-hand findings: personal facts (a diagnosis, a private mortgage) still reach the
firm through a "routine log" sent to a colleague, which a clinic or lender would not do; the "someone else the matter involves"
slot can copy the vendor on the holder's lie; in n = 3 role chains the second address is always given to role 2, even when role 1
is the outside one.

## 2026-09-17, later: the light clue step (run 6, logs/fourstep_sonnet6.json)

User's call: step 2 was doing the plot's design work and its output was too heavy. Now `clues.md` gets the secret plus a
fixed cast built by code (Person A holder, B kept from, C record writer; sides of the firm from a new `sides` field in
secret.md) and returns four fields: clue_1, clue_2 (one sentence each), clue_3 per pattern (one sentence with the
holder's words in double quotes; code takes the last quoted span as the keep-word-for-word line), and one and_gate line.
The reference, cast roles, relation, at_firm and line_kind self-labels are gone; the plot step now names the matter (the
subject-line and file-name samples moved into <<MAILBOX_FORMS>>). Steps are named secret topic / clue / plot / email
generation everywhere. Run 6: 33 calls, 12/12 chains, no runtime errors.

Read of run 6, by where the fault enters:
- clue step: one holds clue named the diagnosis in its subject line; one fact clue was letter text with a bracketed
  placeholder; the and_gate lines run to four sentences.
- plot step: two emails from Person D to herself (the firm check accepts a self-message; needs a from != to rule);
  two four-clue chains whose fact halves are the same letter twice; the shared-reference rule putting the record's
  subject on the spouse's or executive's own mail; a firm assistant confirming a personal medical letter was opened;
  December dates against a clue that fixed timing.
- role pairs: the personal-finance pair does not clash (two different accounts); holders that are outside agents still
  cast at ironwood.com.
Clean end to end: the two-clue omission (finance), the two-clue commission (medical), the travel palter, two role pairs.

## 2026-09-17, run 7: one clue call per secret per pattern (logs/fourstep_sonnet7.json)

User's call: the three patterns must not share one clue call (it made clues 1 and 2 identical across patterns), and role
pairs must go through the clue step too. Now `clues.md` is one template assembled per pattern from patterns.json
(`<<PATTERN_NAME>>`, `<<PATTERN_DEFINITION>>`, `<<CLUE_RULES>>` = two shared lines + the pattern's `clue_rules`,
`<<N_CLUES>>`, `<<CLUE_SCHEMA>>`). secret_roles.md now names the two roles and audiences with sides; the two role
sentences are written at the clue step (clue_1, clue_2, quoted). Results live under s["clues"][pattern]. Calls: 6 + 11 +
20 = 37 for 10 chains (one pair dropped by its self-check, one paltering clue set failed the double-quote check).

Read: clue-2 sentences often describe inbox state ("received and opened", "flagged and read", "a read receipt") rather
than an email; two clue-2s put the diagnosis in the subject line the plot then reused on every thread; one fact email
says "see the attached summary" so the lien is never stated in a body; one four-clue lie is told on the vendor's own
thread with the executive on it. Cleanest: the omission chains (finance and travel), the travel palter, both role pairs.

## 2026-09-17, night: prompts rewritten as plain guidance (not yet run)

User's call after run 7: stop stacking rules; write the clue and plot prompts as plain instructions a called model can
follow, and move every choice with several good answers into the plot step as a menu the model picks from.
- clues.md: a short brief of the puzzle, the secret, the three fixed people, the pattern, the clue list for that
  pattern (patterns.json clue_rules, plus two shared lines for the lying patterns), then the schema. Person A's exact
  words come back in their own field (holder_words / words_1 / words_2), so no quotes inside prose; why_together
  replaces and_gate.
- plot.md: the brief, the people, the pattern, the layout for the chain length (patterns.json, rewritten in plain
  words: the fact now goes from Person C to Person A directly, no "between people other than the holder"), the decided
  clues in thread order (clues_text), the menus (menus_text: fact carrier, holds form, before, who else, after, naming
  with real subject lines and file names), one honesty sentence per pattern (<<KEEP>>), the schema with a `choices`
  object. Code no longer draws slots; rec['slots'] = the model's choices.
- shapes.json option lists reworded to Person A/B/C and to emails sent to Person A.
Dry-run assembled with a stub model and proofread; no API calls made. Next run needs the user's yes (~37 calls).
Follow-up the same night: menus are introduced as examples the model may replace with a better fit; the pattern line
is one fluent sentence (`<<PATTERN>>`: name, source quote, "Here, ..."); `<<KEEP>>` renamed `<<PATTERN_RULE>>`;
"kept word for word" is now "Person A's exact words"; the cast block no longer repeats the names-come-later line.
The page's PEOPLE, CAST, MENUS, CLUES and LAYOUT fills are generated from a stub assembly, not hand-written.
User's call, later: no "keep word for word" from plot to email. The plot and email prompts no longer require Person
A's line to appear unchanged; the PLOTS block gives it "in substance" and the email step writes freely. Code measures
drift afterwards: `email_verbatim` (strict) and `line_kept` (share of the line's content words found in the emails);
the report shows both, and "clean" in the slot tally means line_kept >= 0.6. No retry on drift.

## 2026-09-17, run 8: the rewritten prompts (logs/fourstep_sonnet8.json)

Same three topics, 42 calls (6 secrets, 12 clues, 24 plots and emails), 12/12 chains, no runtime errors. Holder line
kept in substance 12/12, verbatim 11/12 without any keep requirement.

Where the prompts misguide the generator, read from the outputs:
1. Clue rule for clue 2 lists example forms ("Person A thanks Person C ... asks a question ..."): 9 of 9 lying clue
   sets chose the first form, a reply to Person C, so the plot's holds menu never got a real choice. And a reply in
   this mailbox quotes the earlier message, so the holds clue carries the fact under it: 3 chains flagged as leaks,
   the rest leak the same way in the quoted tail. The layout only warns about forwards.
2. "Pick the option that fits best" in the plot menus converges: who_else = nobody else in 12/12, after = passes it
   on / makes a plan in 11/12, fact_carrier = formal notice or bank statement. Asking for the best fit removes variety.
3. The role-pair prompt's "roles that clash": all three pairs are either contradictions (medical, travel: a lie told
   to one audience) or compatible non-secrets (finance: two different accounts). The self-check passed all three. The
   model does not get "both true, forbidden together" from the word clash and the two examples.
4. Paltering rule "true but does not answer": the medical palter is "I'm not aware of anything that would prevent me
   from doing my job", a denial in effect. The rule needs to say the reply is about something else than the matter.
5. "One sentence" for why_together is ignored (2-3 sentences every time): the field invites explanation.
6. Naming is reported as prose, not a menu label, so the choices tally is unreadable for that line.
Code slips found: the 'references differ' check counted Person B's own thread (fixed: record clues only); a role
chain's Person D placed at the firm by the plot was cast outside (fixed); headers put back over a message the plot
addressed to an unlisted person leave a wrong salutation (chain 7).

## 2026-09-17, after run 8: hybrid choices, quoting made known, role-pair and palter guidance (not yet run)

- Choices are half assigned, half chosen: for every menu line code flips a coin; "use: X" (drawn at random) or
  "choose one, or write a better one". An assigned option can be swapped if it cannot fit, with a reason. The form of
  clue 1 and clue 2 is now decided at the clue step (clue_1_form, clue_2_form); the plot keeps before, who_else,
  after, naming (and audience_1/2 for role pairs). Choices come back as labels (CHOICE_KEYS).
- Both the clue and plot prompts say that a reply or forward quotes the earlier message, so a reply to the fact email
  carries the fact; clue 2 is a separate email and the holds list has no reply/forward of the fact email.
- secret_roles.md explains a role pair with three examples and a test (would each line still be true if the two people
  compared notes; would a rule be shown broken). The clue rules for a role pair carry the same test.
- The paltering rule says the reply is true about something else and never states or denies the fact, with a test.
- plot.md: everyone a message goes to is in its to field.
Assembled with a stub and proofread; no API call. A run needs the user's yes (~42 calls).
Manual read of the assembled forms before running, seven fixes: (1) the quoting note said "the fact", meaningless
for a role pair, now "an email that carries a clue"; (2) the role people block read "Person B is told the first role,
X: Y", now "Person B is Y; Person A shows them the first role, X"; (3) the roles pattern line said "an incompatible
thing", which invites contradictions, now "two roles that are not allowed together"; (4) two-clue chains printed the
clue step's clue 2 inside Person C's thread, contradicting the layout; now the layout's short reply stands and clue 2
is not used; (5) the honesty sentence excluded Person A, who received the fact, from A's own thread with B; (6) the
role-pair prompt gave the same examples twice (prose plus <<EXAMPLES>>), placeholder dropped; (7) the plot schema's
example person was "Person D", already taken in a three-clue role chain, now "Person ?".

## Clue step cut to four inputs (2026-09-17, after run 8)

The clue prompt now sees the setting, the secret sentence, the pattern and the AND-gate rule, plus the chain length n
and one sentence on what the n clues carry. It returns n plain sentences about the people by their roles in the secret
and nothing else. Gone from the clue step: the secret JSON (only the `secret` sentence is passed on, to the clue and
the plot step), the people block, the two form menus, `holder_words`, `why_together`. The people are now defined at
the plot step: the prompt lists Person A, B, C with what each does in the secret and the plot returns a `people`
table (person, function, role, at_firm) that the email step and name casting read. The form menus moved to the plot
step's choices (`fact_form`; `holds_form` for three or four clues). n is fixed at the clue call (`clues --vary-n`) and
the chain step reads it back. Drift is now measured against the last clue sentence (the holder's conduct) or the two
role sentences. Stub run passes for all four patterns; no API call made.

Comments of 2026-09-17 21:03-21:08 (Shuyan), applied: the AND-gate rule says any smaller set of clues does not give the
full secret; the pattern line and every clue-step text say "the deceiver" and "the target" instead of holder and person
kept from the fact, with no Person A/B mapping (the plot step's cast block does that); the task sentence reads "your job
is to split this secret into N clues, one plain sentence each, following the AND-gate rule: ..."; the "use only, no
names" rule is rewritten as what to do. Step 1's fields (holder, kept_from) are unchanged.

## Run 9: clue step only, new prompt (2026-09-17, 12 Sonnet calls)

State `logs/fourstep_sonnet9.json`: run 8's three secrets and three role pairs, old clues stripped, `clues --vary-n`.
12/12 returned, n honoured 12/12, all clues filled and distinct. Findings: the AND gate broke in 3 of 9 lying sets,
each time in the fact clue: the model copied the secret sentence, concealment and stake included, into clue 1 (medical
paltering) or clue 2 (finance paltering), or wrote "without the spouse's knowledge" into the fact (finance omission).
The best set is travel, lying by commission, four clues: matter, what is wrong, knows, lie. The palter and omission
clues describe the deceiver's line in the abstract ("a true statement about another aspect"), so the email step still
decides its content. Role pairs: the two-clue sets split faithfully but two pairs are lies by step 1's own doing; the
three-clue set is broken, the model gave the second address to the spouse, so the pieces line for three role clues does
not read as a split of the secret. Page: clue tab shows the twelve with diagnoses (notes9.json).

After run 9 (2026-09-17): three changes from the user's reading. (1) The clue step's pieces line now carries a worked
example from another domain (an expired permit; two full-time jobs), with the knows clue shown as "knows the permit has
expired" and nothing more, to stop the fact being copied into every clue. (2) The plot step lands abstract clues: a new
paragraph asks it to say what the target asked, what the deceiver writes, what the report or rule is, and a `line`
field per clue gives the deceiver's message in substance; that line is what the email step keeps in meaning and the
drift measure reads. (3) Three-clue role pairs no longer use the second-address link; the third clue is the rule, the
vow, contract or policy under which one person holds only one of the roles, stated by whoever keeps it. Two-clue role
pairs put the exclusive word inside a role clue instead. Atom `link` replaced by `rule` in patterns.json and code.

## Run 10: clue step again with the examples (2026-09-17, 12 jobs, 15 calls)

State `logs/fourstep_sonnet10.json`. 11 of 12 sets returned; the medical role pair (the one that is a lie by
construction) came back empty four times, three retries wasted. Against run 9: the knows clue is now bare ("knows he
has been diagnosed") in every set; the palter clues are concrete (a recent check-up, payments on time, the itinerary
sent); the three-clue role pair took the rule shape and the two-clue travel pair is clean. Still broken: the fact clue
swallows the concealment and the stake in 4 of 9 lying sets, all on the medical and finance secrets whose sentence is
written as fact plus "has not told" plus what follows. The travel secret split cleanly every time. The example did not
cure the copying; a positive phrase in the pieces line (the fact is the situation itself, without the target or what the
target is about to do) is the next thing to try.

## Clue step replaced by the ported atomize prompt (2026-09-17, after run 10)

At the user's request the clue step is now enron_benchmark's `prompts/atomize.md`, ported: three fixed atoms (a1 the
truth as a standing status, a2 "actor knows a1", a3 the concealing act rendered per pattern from fills/mechanisms.json),
the AND gate, two worked examples per pattern with people by role (fills/examples.json, work and casual), and the
a1/a2/a3 output. Lying by commission and paltering carry over as verified there; lying by omission uses that project's
omission act and examples; the role pair is new: a1 role 1 with the exclusive word, a2 role 2, a3 the tie (contract,
policy, vow or a third party's record that role 1 stands). The words are the actor and the victim, the prompt's own.
n moved back to the chain step: the plot merges a1+a2 for two clues and splits a1 for four, as the layouts say.
Fills live in prompts/v2/atoms.json. Stub run passes; no API call made.

Then (same day): the worked examples are dropped from the clue prompt, the paltering act's three mini-examples too;
the user judges the atoms clear enough and examples to steer the model into one shape, which is what happened to
enron_benchmark's secrets. Variety is the plot step's job: its choices paragraph now says so, and the "before" choice
(what prompts Person A's line) is drawn for every lying pattern, not only commission. The paltering pattern line now
matches the act: something true about the matter's visible side, not "about something else".

## Run 11: the ported atoms prompt, no examples (2026-09-18, 12 Sonnet calls)

State `logs/fourstep_sonnet11.json`. 12/12 returned. The nine lying sets are all clean: a1 is the truth as a standing
fact with nothing about who hides it, a2 is bare knowledge, and every a3 is concrete and of its kind, including the
three palters (strong trading performance; primary mortgage payments current; itinerary and logistics in order), which
had failed in every earlier run. The three role-pair sets are not: the model wrote a1 and a2 as first-person quotes,
one in the agency's voice, and a3 as a contract recital with invented names, dates and an account number. Two of the
three pairs are still broken by step 1 (a contradiction; an ambiguity about whether the two accounts are one). The
"keep to the secret, names come later" sentence was dropped with the port, and the role-pair block's "as the actor shows
it to the first victim" reads as "quote it". A crash after the save (the passes() helper had been cut by an earlier
edit) is fixed; the results were already on disk.

## Audience segregation on the same secret; step 1 gains the insider (2026-09-18)

Design change agreed with the user: no separate role-pair step. Step 1 is pattern-blind and writes fact, actor,
victim, insider (who shares the fact and has it in writing), stake and the secret sentence; secret_roles.md, the
both_true filter and the roles pool are gone. Audience segregation takes the same secret with atoms a1 the inner face
(the actor's own words to the insider), a2 the outer face (the matter shown to the victim, fact absent), a3 the
segregation (keeping the two audiences apart); two or three clues; cast A actor, B victim, C insider; plot menus
inner_channel and apart. Stub run passes for all four patterns.

Run 12, step 1 only, 3 Sonnet calls (state logs/fourstep_sonnet12.json): medical sound but long; travel usable; personal
finance broken by wording, the model wrote the field name into the prose ("The actor's spouse, who works at Ironwood")
and crossed the roles. The prompt names the fields actor, victim, insider and never says to keep those words out of
the sentence; that is the next fix.

## Audience segregation rebuilt as a second role against the job (2026-09-18)

The user rejected segregation on a fact kept: the inner and outer face gave the secret between them, and no role pair
was there. Everyone in the mailbox works at the firm, so a second role is only a secret when it conflicts with the
job. New step 1 prompt secret_role.md: job and the duty it crosses, the outside role and who it is with, the rule that
bars the pair, victim, insider (the outside contact), stake, fact, secret. Atoms: a1 the second role in the actor's own
words to the outside party with nothing of the job; a2 the job at the firm on the matter that touches that party with
nothing of the second role; a3 the segregation act. Two clues carry a1 and a2, three add a3. Second-role secrets go
through all four patterns, a fact kept through the three lying patterns, so patterns compare on the second-role set.
Plot menus: inner_channel, firm_channel, apart. Stub run passes on a hand-written second-role secret; no API call.

## Plot step rebuilt on a timeline, per-atom carriers and a plan the plot chooses (2026-09-18)

Agreed with the user: the three atoms are the logic of concealment and stay; what made the chains formulaic was one
carrier per atom, one email per atom in atom order, and the act always a statement. Now the plot step (plot.md) writes
the timeline first (dated events, earliest to most recent), then its own plan of which atoms each clue carries (every
atom somewhere, a1 and a3 never in one clue, more clues than atoms spread one atom over two innocent clues), then the
threads dated on the timeline. Carriers are choices per atom in shapes.json (a1: an outside record, the actor's own
admission, a third party's passing mention, an event with consequences; a2: forward, on the thread, a clerk's note, an
action only a knower would take, a later dating remark; a3: a message, an action the victim relies on, an answer inside
the victim's thread) with the coin flip. The layouts in patterns.json are gone; the templates stay as the fallback when
the plot's plan fails plan_from_plot twice. The email step gets the timeline (<<TIMELINE>>). Stub run passes for all
four patterns at 2, 3 and 4 clues; no API call.

Same day: insider and stake are out of step 1 (both prompts). The plot step decides the stake first, before the
timeline, and names the insider in its people table (Person C's role). Step 1 returns fact, actor, victim, secret; for
a second role job, outside_role, rule, victim, fact, secret. Stub run passes; no API call.

Same day: the a1/a2/a3 labels inherited from the ported prompt are replaced everywhere by the parts' names, [fact]
[knows] [conflict] for the lying patterns and [outside] [job] [apart] for audience segregation: in clues.md, atoms.json
(parts, act, labels), patterns.json (and_gate per kind), shapes.json (carrier by label), plot.md (never-together rule
by label, the plan's carries by label), the runner (labels(), never_together(), plan_from_plot accepts old a1/a2/a3),
the state format (clues stored by label; older files with a1/a2/a3 still read). Stub run passes.

## Step 1 down to actor, fact, secret; one prompt; the victim chosen at step 2 (2026-09-18)

The user's design: step 1 gives only the actor (someone at the firm, by job), the fact, and a sentence saying the fact
and that the actor keeps it. No victim: who is kept from a fact depends on how it is kept, so the parts step chooses
the victim per pattern and returns it with the parts (`victim`), and the plot's cast block shows it on Person B's line.
secret_role.md is retired; every secret goes through all four patterns, and for audience segregation the parts prompt
answers {"none": why} when the fact is not a standing the actor holds with a second person; that chain is skipped.
[outside] and [job] are now the second role and the first role, the first being what the actor is to the victim.
Stub run passes; no API call.

## Pipeline simulated by hand and proofread (2026-09-18)

The user asked for the pipeline as inputs and outputs, one line per element, simulated to the emails. Done on one
secret (a Gulf Coast desk trader who is a paid advisor to a producer his desk buys from) through all four patterns,
with hand-written answers standing in for the model and every stage's prompt assembled by the real code
(scratchpad/sim: sim.py, answers.json, prompts/, state.json). All four chains pass the code checks: plans accepted
without fallback, timelines in order, drift 0.85-1.0 on the plot's lines, no isolation or leak findings. Prompt fixes
found by reading the assembled prompts as the generator: (1) the plot's "before" choice and the [conflict] carrier
contradicted each other, merged into one occasion-of-[conflict] choice; (2) that choice is per pattern, paltering only
gets the asked forms, since its act is an answer by definition; (3) the [apart] carrier is dropped from the plot, the
parts step already fixes that act; (4) the naming note still said "the record", now [fact] and [knows]; (5) the email
prompt never glossed the [fact]/[knows]/[conflict] marks on the clues, now one line; (6) drift for segregation was
measured against the part descriptions, now only against lines the plot wrote; (7) the "holder writes the fact" check
is retired, the actor's own admission is a legitimate carrier now. plot.md is reordered as stake, people, timeline
(tagged), threads. New timeline_checks: dates on the timeline, in order, [fact] event no later than [conflict]. The
Pipeline tab on the review page shows the plan and the simulated outputs, emails included.

## Run 13: three topics, parts under four patterns (2026-09-18, 15 Sonnet calls)

State `logs/fourstep_sonnet13.json`: 3 secrets (MS again; the second mortgage again; diverted frequent-flyer miles,
new), 12 parts sets, all filled. The nine lying sets are clean: standing facts, bare knows, concrete acts, the three
palters true and on the visible side. Step 1 adds "keeps this from colleagues and supervisors" to the sentence though
not asked; harmless. Audience segregation failed 3/3 the same way: none of the three facts has a second role the
victim would object to (patient, borrower, loyalty member), yet the model never took the none exit because the rule
only asked for "a standing with a second person"; it wrote [outside] and [job] as first-person quotes, one victim as
two people, and [apart] as a paragraph. Fixes applied: the none rule now says the victim must object to the role
itself (advisor to a counterparty, second employer, second partner), not to the fact; the three parts are one
third-person sentence each; the victim is one person by role. Not rerun.

## Three kinds of secret, three patterns, topic pool by hand (2026-09-20, no API calls)

The user settled the pattern question: audience segregation is not a fourth mechanism but what the three lying
mechanisms achieve, and its "purpose" side comes from Goffman's kinds of secret (1956 monograph, pp. 87-89, quoted in
prompts/v2/purposes.json). Kept: dark, entrusted, strategic. Dropped: inside (hides no fact), free (costs nothing to
tell, so the actor has no reason to lie), latent (no holder). Changes:

- prompts/v2/kinds.json: the three kinds with Goffman's words and a plain reading, and the 36 IAB topics sorted by
  hand into the kinds each can hold (23 dark, 18 entrusted, 11 strategic, 11 topics none; 52 (topic, kind) pairs).
  Sorted by hand because a model says yes to every topic.
- secret.md: `Kind of secret: <<KIND>>` under the topic; output still actor, fact, secret; the example list is gone,
  the kind and the topic steer. `secrets --kinds` filters; state secrets carry `kind`.
- clues.md and plot.md get the kind's short line. atoms.json, patterns.json, shapes.json lose their segregation
  entries; `patterns_for` returns the three lying patterns; the ROLES branches in fourstep.py are dead code.
- The affair shape (the actor writes to B and to C, telling neither of the other) is lying by omission under a dark
  secret. patterns.json gives omission a `plot_rule` (the two threads run through the same weeks, touch the same
  days, money or place, and neither names the other person) and shapes.json a `carrier.conflict` option, "two threads
  side by side". The pattern rule moved from the plan paragraph to the "Keep these true" block of plot.md.
- Person C's cast line now says who the insider can be: the person the fact is about, the other party, or a
  colleague in the plan.

Simulated by hand (scratchpad/sim: three secrets, one per kind; nine parts sets; three chains to the emails, dark +
omission three clues, entrusted + paltering two, strategic + commission three). All pass the code checks: plans
accepted, timelines in order, drift 0.86-1.0, no isolation or leak findings. Two of my own answers failed the "[fact]
and [knows] name the matter the same way" check on the first run, which shows the check works. The Pipeline tab on the
review page shows the pool, the three secrets, the nine parts sets, the plots and the emails. Stub run passes.

Same day, the pool gated a second time: `fit` per topic. Out as sensitive: crime, war and conflicts, religion,
healthy living; politics kept for strategic only and food and drink for dark only (belief and addiction cases
removed); out as thin: books and literature, hobbies, shopping, sports. 19 topics asked, 42 (topic, kind) pairs.
secret.md gets a fixed guard line (no violence, abuse, harassment, sexual content, addiction; no religion, ethnicity,
orientation, political belief, disability or immigration status; adults only). Sim and stub pass.

## Run 14: step 1 on three topics x three kinds (2026-09-20, 9 Sonnet calls)

State `logs/fourstep_sonnet14.json`; 20,919 chars in, 4,005 out. Topics family and relationships, careers, real
estate; kinds dark, entrusted, strategic. All nine in kind; eight on topic (family x strategic drifted to a careers
secret: an SVP negotiating a move to a competitor). All facts are standing states. Findings and fixes, no rerun:
(1) every entrusted actor is an executive assistant, the first item of the kind's reading; the assistant is now last.
(2) divorce twice and subletting twice within a topic: the kinds of a topic now run in turn (cmd_secrets run_topic),
each seeing the earlier facts in <<AVOID>>, worded "of any kind ... not the same story under another kind".
(3) seven sentences name the victim; secret.md now says the sentence names nobody but the actor (and the owner of an
entrusted fact). (4) no affair; the guard line's "sexual content" became "explicit sexual detail". (5) strategic
removed from family and relationships (41 pairs). Careers x dark (a recruiter's trade certification, intending to
leave) is a strategic secret in dark clothing; left as is, to see whether it recurs. Results and reading on the
review page's Secret generation tab.

Follow-up the same day, per the user: (a) the entrusted reading's instance list ("their assistant, lawyer, payroll
clerk, doctor's office, friend or relative") is removed, the definition stands alone; a list of instances in a prompt
is a menu to the model and it takes the first. (b) Step 1 gets a `victim` field, whichever shape is true of the
secret: one person by role, a party, or everyone else; the "names nobody else" sentence is dropped. clues.md takes it
as "Kept from: <<VICTIM>>" and writes the parts to one person, the victim or the one who stands for the party, returned
in the victim field. Sim and stub pass. Not rerun.

Step 1 reframed (2026-09-20, user's call): secret.md is now "Worked examples of Goffman's kinds of secret". The model
plays the author of a chapter's worked examples set at the firm in 2000-2001 and is told nothing about the benchmark
(no <<SETTING>>, no "later steps"). Teeth from Goffman p. 87, quoted: the fact is destructive information, it would
discredit, disrupt or make useless an impression, and the people kept from it would say they had a right to know; a
fact that would only embarrass is not a case. "Moral or legal issue" was considered and rejected: it conflicts with
entrusted (someone else's trouble) and strategic (legitimate plans) and narrows dark beyond Goffman. Fields unchanged:
actor, fact, secret, victim. Old prompt kept at scratchpad/secret_before_role.md. Sim and stub pass; not run.
Proofread of the assembled step 1 prompt (same day): cut "readers who will later see the correspondence" (a leak of the
next steps), "money, work, health ... are the ground" (an instance list, and the area already says where the case
sits), the per-kind clauses under fact and secret (each prompt has one kind; the kind's reading already says it);
"still true at the time of the case" -> "still holds when the case is told: a present state, not something already
over"; the victim's "by name" (clashed with "not by name") -> "said as what it is"; the count line moved down to the
fields; the JSON key is "cases" (runner reads cases or secrets). The IAB tier-2 list was an instance list too; area_line()
now words it as coverage: "The taxonomy says this area covers ...; a case can sit anywhere in it."

## Run 15: the role-framed step 1 on the same pairs (2026-09-20, 8 Sonnet calls)

State `logs/fourstep_sonnet15.json` (run 14's secrets kept via --append, so their facts sat in <<AVOID>>); 29,976
chars in, 4,144 out; 8 pairs, strategic no longer on family. 8/8 in kind and on topic. Better than run 14: careers x
dark is a credential never earned (a present, destructive fact) instead of an evening course; entrusted actors are a
paralegal, a mentor and an attorney, not three assistants; the strategic secrets state in Goffman's terms why the
victim would act differently. Problems: real estate x dark is incoherent (billing the firm for consulting on one's own
vacation property), a contrivance forced by the avoid list once subletting was barred; real estate x strategic keeps a
plan from a listing broker who has no right to know ("or deal with it" in the strategic reading let it through);
sentences are long and explain themselves. Victims: 2 single people, 6 parties. Family x dark gives marital status
both runs (divorce, then separation); no affair in two runs. Results, reading and a run 14 / run 15 table on the
review page's Secret generation tab. No prompt change made after the run; three proposed, awaiting the user.
After run 15 (user): strategic reading says the people kept from it are at the firm (no "or deal with it"); the
secret field says "It states; it does not explain why."; the step 1 avoid list is removed (<<AVOID>> gone, calls per
pair independent again): a barred natural secret produced a contrived one, and overlap is accepted.

## Run 16: the final step 1 prompt, fresh state (2026-09-20, 8 Sonnet calls)

State `logs/fourstep_sonnet16.json`; 25,048 chars in, 3,372 out; no avoid list. 8/8 in kind, on topic, coherent;
sentences short. Natural cases return (divorce, lapsed credential, mentee interviewing, positions cut). Teeth: 5
strong, 1 moderate, 2 weak, the same two pairs as run 15: family x entrusted (someone else's marital news, no right
to know) and real estate x strategic (kept from the landlord; the "at the firm" sentence in the reading did not bind,
Goffman's strategic secret is against the opposition by definition). Proposed, not applied: entrusted leaves the family
topic; the strategic victim rule moves into the victim field ("the people at the firm the plan lands on"). Three-run
table on the review page's Secret generation tab.

## Pool regraded on teeth (2026-09-20, no API calls)

The user's diagnosis of runs 15-16: the weak pairs were weak because the pool matched topics to kinds without asking
whether the natural case has teeth. kinds.json now records, per (topic, kind), the natural case the model reaches
for, its victim, and whether that victim would say they had a right to know; only pairs whose natural case passes are
asked. Out on teeth: every entrusted pair whose fact is a colleague's private news (family, attractions, automotive,
home and garden, personal finance); every strategic pair whose opposition is outside the firm (disasters, events,
law, politics, real estate, science, technology, travel); personal celebrations, events and politics leave the pool
altogether. Kept moderate: automotive dark, education entrusted, medical dark and entrusted, real estate entrusted,
technology entrusted, travel entrusted (the right to know depends on the job or on the spouse being the victim).
Pool: 16 topics, 28 pairs (16 dark, 10 entrusted, 2 strategic: careers, business and finance). Strategic is thin by
nature; if more strategic cases are wanted, the way is a victim-field rule ("the people at the firm the plan lands
on"), not more topics. Page rebuilt: the pool table shows case, victim and verdict per pair.

## Step 2 input and clue prompt proofread (2026-09-20, no API calls)

`logs/fourstep_sonnet17.json`: the six run-16 secrets whose pair passes the teeth gate (family dark; careers dark,
entrusted, strategic; real estate dark, entrusted); the two weak ones dropped, nothing edited. clues.md proofread as
assembled, with the step-1 failure types in mind: (1) the mailbox SETTING paragraph and "a later step turns the parts
into email threads" told the model about the benchmark; now one line, people at the firm in 2000-2001. (2) "Name that
person in the parts" contradicted the AND gate's "[fact] is the truth and nothing about ... from whom"; now "in
[conflict] and in the victim field". (3) The output shape carried enron_benchmark's role names (true_state, knew,
withheld_disclosure), a second vocabulary for the same three parts; removed, each part is a string. (4) The
paltering act did not say the palter is an answer while the pattern line did; the act now starts "asked by the
victim about the matter". (5) Added: one sentence each, third person, people by role (run 13's segregation parts had
come back as first-person quotes). (6) The AND gate text now starts with a capital. Left as is, flagged: the paltering
act prescribes one form ("confirms that the matter's visible side is going fine"), so palters may all take that
shape; widen it only if the run shows sameness. Sim and stub pass. Next: 6 secrets x 3 patterns = 18 calls, not run.
Paltering rewritten from the sources (same day, user: "we can't allow all paltering to be the same"): the ported act
("asked ... confirms the visible side is going fine") was one form. atoms.json act and patterns.json definition/plain
now follow Rogers et al. ("the active use of truthful statements to convey a misleading impression", asked or
unasked) and Schauer & Zeckhauser's forms ("fudging, twisting, shading, bending, stretching, slanting, exaggerating,
distorting, whitewashing, and selective reporting"); every statement true, the fact neither stated nor denied. shapes
carrier.conflict[paltering] gains the unprompted occasions (a message, a report or handoff, a note on an action);
line_kind "true but misleading". Sim and stub pass; page rebuilt.
Step 2 gets all four step 1 fields (user, same day): clues.md's "The secret to place" block is Actor / Fact / Secret /
Kept from / Kind of secret; <<ACTOR>> and <<FACT>> added. Setting line reworded; kind line uses a comma. Second and
third proofreads of the assembled prompt (commission, paltering, omission; single and party victims) found nothing
further. Sim and stub pass. 18-call step 2 run still awaits a yes.

## Step 2 simulated by hand on the six kept secrets (2026-09-20, no API calls)

scratchpad/sim/sim2.py: 18 parts sets (6 secrets x 3 patterns) written to the current clues.md, routed by (topic,
kind, pattern), run through clues_for; all 18 pass. Party victims resolved to one person (the senior of the two
analysts; the buyer's acquisitions lead; the SVP's deputy). Palters use five of Schauer & Zeckhauser's forms, three
asked and three unasked. Findings written on the page's new Clue generation tab: [knows] is nearly empty for dark
secrets about the actor and is the hinge for entrusted ones; an omission that touches the matter's status leans, so
the roof package leaves the roof out. Model risks to read for after the real run: [knows] copied from [fact], a
party left plural, an omission [conflict] that states a status.

## Run 17: clue generation on the six kept secrets (2026-09-20, 18 Sonnet calls)

State `logs/fourstep_sonnet17.json`; 48,102 chars in, 11,912 out; 18/18 filled and distinct. Sound: standing
[fact]s; [knows] = fact with the actor in front (kept on purpose: it is the reader's proof); all six omissions hold;
four of six lies clean; victims resolved to one person in all 18. Faults: (1) paltering explains its effect (5/6 end
with what the victim concludes; 70-90 words); (2) paltering is asked 6/6 and one-shaped (three or four true statements
in a row) despite "asked or unasked" and the list of forms; (3) two lies are first-person quotes, one hedged into not
false; (4) the roof [fact] carries the concealing clause copied from the step 1 fact field. Two palters doubtful on
substance. Reading per set on the review page's Clue generation tab; the hand simulation sits below it. Fixes not yet
applied; proposals in the reply.
After run 17 (user: all three): (1) the output shape frames [conflict] per pattern ("<the actor, by role> tells <the
victim, by role> that <one statement, false given the fact>" / "... <true statements on the matter that leave a false
picture of it>" / "<the actor> writes to <the victim> about <the matter>, <what the message covers>, and says nothing
of <the fact>"); (2) the paltering act loses the outcome clause and says "the part gives what the actor states, not
what the victim takes from it"; (3) the occasion leaves step 2 for commission and paltering ("The occasion is not
given here"; "asked or unasked" removed); step 3's carrier menu chooses it. Gaps found in the check: "the matter" was
used in two acts and never defined (now: what the fact is about, the thing the victim would ask after); the step 1
fact field now says "the state itself, with nothing of what the actor does about it" (the roof fact carried the
concealing clause). Sim, sim2 and stub pass. Not rerun.
AND-gate check of run 17 by hand (same day; table on the Clue generation tab, scratchpad/gate17.json): together yes
13, moderate 1, weak 1, no 3; alone fails 2 (the roof [fact] with the concealing clause). Omission retrieves the
secret 4/6; the two failures (divorce to a counterparty; the SVP's sale to the chief of staff) wrote a message where
the fact did not belong, so its silence proves nothing. Fix applied: the omission act says the message is one in
which the fact belonged (an answer to the victim's question, or the report, form, review or handoff the fact should
have been in) and that for omission the occasion is part of the act; the schema frame says the same. Old act in
scratchpad/omission_act_before.txt. Also seen: for omission [fact]+[conflict] never suffices (could be ignorance), so
[knows] is the hinge, which supports keeping it.

## Pool regraded on the case each pair yields; "teeth" renamed (2026-09-20, no API calls)

The user asked why the divorce secret had been graded strong: it had not earned it. The grade described the case the
pair could give (an affair, victim the partner), not the case it yields at this firm (a divorce kept at work, victim
colleagues, who are owed nothing); the AND-gate check of run 17 had already shown its lie and its omission fail. All
36 x 3 pairs regraded on the yielded case with the victim the model picks, two tests written out per pair in
kinds.json (Goffman's destructive-information test; the right-to-know test). Out now: attractions, automotive,
family, food and drink, home and garden (dark pairs that fail the right to know at work). Pool: 11 topics, 23 pairs
(11 dark, 10 entrusted, 2 strategic). The word "teeth" (an idiom) is replaced on the page and in the pool by the two
tests' names. Kept set for step 3: `logs/fourstep_sonnet18.json`, the five run-17 secrets without the family one.
Step 1 addition (user, 2026-09-20): after the two tests, "The people kept from a fact may be at home as well as at
work: a spouse or partner, a parent, as much as a manager, a colleague or a counterparty." Reason: three runs of
family x dark gave a divorce kept at work, never the affair whose victim is the partner; the setting sentence pulls
the victim to the firm. The guard line's "explicit sexual detail" is left as is. Not run.
Same day (user): family x dark back in the pool "on trial" (24 pairs); secret.md gains "Everyone in a case is
invented; no real person is described. Secrets are, by their nature, often about conduct people would condemn; write
such cases as they are, without softening them." The guard line stays. Other dropped topics stay out: their fault
is the right to know at work, not caution.

## Run 19: family x dark, three calls (2026-09-20, 3 Sonnet calls)

`logs/fourstep_sonnet19.json`; 10,191 chars in, 1,144 out. Three independent calls on the current step 1 prompt
(fiction sentence, at-home victims). Three divorces, actor "senior trader" all three times, victims colleagues and
parents / colleagues and managers. No affair. The at-home sentence moved the victim to the parents at most. Untested:
the guard clause. Open choice: test the clause (1 call), name the affair (an example), or drop family again.
Step 1 reframed off the company (user, 2026-09-20): the firm now appears once, as the actor's job ("one person, the
actor, who holds a job at <<FIRM>>, a US energy company"); "set at the firm, among the people who work there" and
"really happens in such a firm" are gone; "the case may sit anywhere in the actor's life, at work or outside it".
Reason: three runs of family x dark gave a divorce kept at work; the setting placed the whole case at work. Fit to
the mailbox is unchanged: it needs only that the actor works at the firm. Old prompt in scratchpad/secret_before_nocompany.md. Not run.

## Run 20: family x dark, three variants (2026-09-20, 3 Sonnet calls)

`logs/fourstep_sonnet20.json`; 10,425 chars in, 1,139 out. Variant 1 without "explicit sexual detail", 2 as it
stands, 3 with "for example a debt kept from a spouse, an affair, a licence that has run out". All three: a marriage
over, kept from colleagues. The guard clause is not the block; a named example did not move it. The company-off
rewording varied the actor (contracts administrator, procurement manager, pipeline supervisor). Untested and now the
prime suspect: the IAB coverage line for the topic contains "divorce" and nothing like an affair. Next: area name
alone; coverage minus "divorce".

## Run 21: area name alone; no company (2026-09-20, 2 Sonnet calls)

`logs/fourstep_sonnet21.json`; 6,667 chars in, 790 out. Variant 1 (area name alone, firm kept on the actor): a
procurement manager's home-equity draw-downs kept from the spouse. Variant 2 (no company, "an ordinary adult"): a
child from a previous relationship kept from the wife. First spouse victims in nine calls on the pair. The tier-2
coverage list was the menu ("divorce" in it); area_line() now returns the tier-1 name alone for every topic, the
last list gone from step 1. Family x dark: kept. No affair either time; the model's partner-victim family secret is
money or a child, and it passes both tests.
Step 1 opening (user, after run 21): the actor is "an ordinary adult in the United States", the case "may sit
anywhere in the actor's life, and the people in it are whoever that life holds"; the firm appears once, in the actor
field ("with the job they hold at <<FIRM>>, a US energy company; the job is true of them whether or not the case
touches it"). Run 21's variant 2 wording, anchored to the mailbox by the job. Sim and stub pass; not run.

## Work and life ground per topic (2026-09-20, no API calls)

The user's design: a topic is either work or life. kinds.json topics[t].ground; life = family and relationships,
medical health, personal finance; the rest work. Step 1: work topics get "The case sits in the actor's work: the
actor holds a job at <<FIRM>>, a US energy company" and the actor "by the job they hold"; life topics get "The case
sits in the actor's life outside work" and the actor "in a few words", with no firm anywhere in the prompt. Step 2's
setting line says the actor holds a job at the firm and carries the ground line. Step 3's cast line for a life case
says Person A "works at the firm, in a job you choose to fit the case"; no extra landing step is needed, the plot
already places Person A at the firm and code casts a mailbox sender. Sim, sim2 and stub pass.

## Pool v4: every pair regraded under the fresh setting, ground per pair (2026-09-20, no API calls)

The user: apply the fresh setting (ordinary adult, firm only for work pairs, area name alone) to every topic and
regrade all three kinds. kinds.json now carries per (topic, kind): ground, case yielded, victim, both tests, verdict.
15 topics, 31 pairs (15 dark, 13 entrusted, 3 strategic); 12 life pairs (attractions dark/entrusted, education
entrusted, family dark/entrusted/strategic, home and garden dark, medical dark/entrusted, personal celebrations dark,
personal finance dark/entrusted), where the victim is a spouse, partner or family member and the right to know holds.
Family x strategic is back: a divorce prepared or assets moved, kept from the spouse. The strategic reading now says
the people kept from it are "the ones it lands on, at work or at home ... not an outside party the plan is aimed at".
ground_of(topic, kind) in the runner. Sim, sim2 and stub pass; not run.

## Run 22: the fresh step 1 on family, careers, business and finance (2026-09-20, 9 Sonnet calls)

`logs/fourstep_sonnet22.json`; 30,756 chars in, 3,513 out. 9/9 standing, short, both tests pass; 8/9 sound. Life
side works: family dark = a child from before the marriage kept from the wife; family strategic = the mother's
assisted-living deposit kept from the husband; family entrusted = the sister's fiancé still married, which passes
the tests but is a free secret (no relation to the fiancé obliges her). Fix: the entrusted reading now says "what the
actor is to the person the fact is about" (with the relation instances as a gloss of "is to"). Work side: careers
three sound; business and finance dark drifted to the credential case, strategic duplicated careers' spin-off with
the same actor; with the area name alone "business and finance" carries no meaning and the firm's business is not
in the prompt. Open: give work pairs a short line on what the firm does, or restore the coverage gloss for work
topics only.

## Run 22, step 2: the nine fresh secrets under three patterns (2026-09-20, 27 Sonnet calls)

State `logs/fourstep_sonnet22.json`; 78,651 chars in, 15,204 out; 27/27 filled and distinct. Run 17's faults are
gone: all [conflict]s third person in their frame, no explanatory tails, palters 40-55 words; all nine omissions give
an occasion where the fact belonged and hold on the gate; all [fact]s are the state alone. Gate holds in 27/27.
Pattern: 22 right, 2 wrong (a false clause inside the family-dark palter; a status assertion, "no other updates to
their record", inside the business-dark omission), 3 borderline (a not-quite-true phrase in the family-entrusted
palter; "approvals are current" in the business-entrusted omission; a near-telling hint in the business-strategic
palter). Persisting shapes: [knows] = fact + actor (intended); palters are three clauses each. Reading per set and
gate verdicts on the review page's Clue generation tab (run 17 and the hand simulation moved off the page; they are
in this log).

## Run 23: step 3 on five chains (2026-09-20, 6 Sonnet calls)

Plot prompt rechecked first: Person A's cast line now carries the step 1 actor description; a ground line sits under
the kind; the stake follows an occasion the part already names; omission gets no occasion menu (its part has it).
Then five plots, chosen from run 22 to differ on every axis (`logs/fourstep_sonnet23.json`; 46,799 chars in, 39,582
out). Sound: family x dark x omission (one leak: the [knows] clue quotes the [fact] letter), careers x strategic x
omission (clean). Gate broken: family x strategic x paltering (a forward says "she has not yet told her husband").
Messy: careers x entrusted x commission n=4 (a fourth clue with no part; the keeping in the [knows] clue; four code
flags). Failed: business x dark x paltering (two clues for three, twice). Menu literalism: "as I said when the letter
came" pasted verbatim twice. Fixes applied, untested: plot.md rules (a reply quoting the [fact] email belongs to the
[fact] clue; no message says the fact is kept; n=4 one part per clue with one part twice; a what-the-victim-did-next
message belongs to the act's thread); plan_from_plot enforces the per-n shape; retry text states the count; the
quotable phrase removed from the [knows] menu. Page: new Plot generation tab.
After run 23 (user): no explicit anti-leak rules, they make every chain alike. The two rules are replaced in plot.md's
"Keep these true" by the principle: the clues are an AND gate like the parts; a reader of one clue, or any two, must
not be able to say A keeps the fact from B; the model reads each thread as that reader, quotes included, and fixes
any that gives the secret alone. The [knows] carrier "reply to the [fact] email with a cover note" is removed (it
quotes the fact by construction). Clue count fixed at 3 (n_for returns 3; --vary-n still works); <<PLAN_SHAPE>>
fills the plan sentence per n. five.py now runs all five at n=3 into logs/fourstep_sonnet24.json. Not run.
Plot prompt double-checked on the five assembled prompts and hand-simulated on chain B (scratchpad/sim/sim3.py: all
checks clean). Two faults found and fixed: (1) the gate sentence said "one clue on its own, or any two" must not give
the secret, but the pair [fact]+[conflict] always does when the fact is about the actor (A is on every message, so
the [fact] clue shows A knows), which is exactly why those two never share a clue; the sentence now names only what
can hold: one clue on its own (four clues: or the two that share a part). (2) "choose another and say why" had no
field; now "give it in the choices field". Known, not a fault: the occasion menu for paltering can hand out "an
action the victim relies on" for a three-clause answer; the prompt allows choosing another. Sim, stub, dry run pass.

## Run 24: step 3 on the five chains at three clues (2026-09-20, 7 Sonnet calls against 5 authorised)

Call accounting: the user authorised 5 with no retries. First attempt spent 1 call: my cache keyed on the first 600
characters of the prompt, identical across chains, so chains B-E were served chain A's answer. Second attempt spent 6:
four chains, plus two retries on chain A provoked by my seeding chain A's processed answer (its carries were in the
checks' names, so the plan check failed and bought a fresh answer, then a firm-side retry bought another). Overspend
of 2 calls, mine. State `logs/fourstep_sonnet24.json`; 47,407 + 7,668 chars in, 47,279 + 8,142 out.
Results: family x strategic x paltering sound (the [knows] clue is an action on a fresh thread). The other four leak
through the [knows] clue: three are Person A's reply on the [fact] thread quoting the [fact] email in full (the plot
narrates the quote as the proof), one is a document that states the fact itself. The principle sentence did not
prevent it; assigned non-quoting carriers were overridden twice while the choices field reported them. Also one
outsider-to-outsider message (chain A) and two off-timeline dates (chain E), both caught by code. Two candidate
repairs proposed, not applied: a clue is its own thread (a reply belongs to the thread it answers); or [knows]
redefined as an action the actor takes because of the fact, with the reply-based carriers removed.
After run 24 (user): one rule added to plot.md, of the mechanical kind: "a reply or a forward carries the message it
quotes, so the clue that carries [knows] is never a reply to, a forward of, or a message on the thread of the email
that carries [fact]; it is its own thread, and [fact] is not in it." The [knows] menu loses "the actor is on the
thread that carries [fact], and says nothing" (the same shape). Three [knows] carriers remain: a clerk/assistant/
calendar entry by name only; an action that only makes sense if the actor knew; a later remark that dates the
knowledge. The step 2 redefinition of [knows] as a trace is still proposed, not applied.

## [knows] redefined as the trace (2026-09-20, no API calls)

The user asked me to guide the prompts the way I understand the task. Applied: atoms.json [fact] "with nothing of the
actor in it"; [knows] "the one thing the actor does or arranges that only makes sense if the actor knows the fact,
with the fact itself not in it: an instruction, a booking, a request, a change of routine. It is the reader's proof
that the actor knows"; the AND gate text and the step 2 schema frame say the same; plot.md's parts block adds one
line ("[knows] is the actor's act that shows they know; its thread carries that act and not the fact"); the [knows]
carrier menu is three action forms (an instruction/booking/request; a change to a routine, address, calendar or
form; a later remark to someone other than the victim); email.md's gloss updated; the naming check
("[fact] and [knows] clues name the matter the same way") now skips action-type [knows]. Simulations rewritten to the
new shape (sim, sim2's 18 sets, sim5's five reference plots): all pass. Next: the five chains need step 2 again
(5 calls) and step 3 (5 calls), 10 in all, with retries disabled in code.

## Run 25: step 2 on the five chains with [knows] as the trace (2026-09-20, 5 Sonnet calls)

`logs/fourstep_sonnet25.json`; 16,712 chars in, 3,342 out; 5/5 filled. All five [knows] are traces (a second account
with a fixed monthly transfer; the deposit share moved out of joint savings; recurring external calendar blocks and
voicemail; credential mail rerouted away from the supervisor; a private recruiter meeting), none a restatement, none a
reply. Two have a keeping tail ("without explanation to his wife"; "without flagging ... to anyone above him"). One
[fact] carries the actor (inherited from the run 22 step 1 fact). Palters ran to four clauses. Not changed. Step 3
on these five is the next 5 calls.

## Run 25, step 3: the five chains with [knows] as the trace (2026-09-20, 5 Sonnet calls, no retries)

`logs/fourstep_sonnet25.json`; 40,668 chars in, 36,363 out. Retries disabled in code (five2.py: a retry gets the
chain's first answer back). The quoting leak is gone in 5/5: every [knows] clue is an act on its own thread. Sound:
family x dark x omission. Holding with one fault each: family x strategic x paltering (a coin-assigned "third person
in passing" [fact] carrier produced a second thread in clue 1 and a contrived colleague); careers x entrusted x
commission (the shared reference "Meridian Interviews" states the fact in the [knows] clue's subject); careers x
strategic x omission (the [knows] message over-explains: "a significant organisational change is expected ... before
it becomes public"). Failed: business x dark x paltering, the victim sent the credential check and received the
[fact] reply (coin-assigned "someone outside the firm asks, with the victim copied"); code flagged the victim on
clues 1 and 2. Candidate fixes, not applied: the reference names the matter without stating it; drop or reword the
victim-copied occasion and the third-person-in-passing [fact] carrier; the [knows] act without commentary.
After run 25 (user): (1) naming note: the shared reference "says which matter without saying the fact: a number, a
place, a date, a file, not the thing itself"; (2) the [conflict] occasion "someone outside the firm asks, with the
victim copied" removed from all three patterns; the [fact] carrier "a third person mentioning the fact in passing"
reworded to one message to the actor about something else that refers to the fact as known between them; (3) [knows]
"gives the act only, not why" at step 2 and "said plainly and without a word of why" in the plot's parts line;
(4) email.md: "A reply reads as a reply: often a line or two, answering what was asked in the register of the thread,
without restating the question or announcing what the message does" (user: nobody writes "I confirm that").
Sim, sim2, sim5, stub and dry run pass.
Simulation of chain D (business x dark x paltering) under the current prompts through the plot and the emails
(scratchpad/sim/sim6.py, on the review page's Plot tab): all checks clean after one alignment fix found by the
simulation: the run 25 [knows] part addressed the victim, and plot_checks allows the victim only on the [conflict]
clue; atoms.json now says the [knows] act is "done with someone other than the victim" and plot.md "The victim is on
no message that carries [fact] or [knows]; the victim's only thread is the one that carries [conflict]". The
simulated emails show the reply rule: "Sure, will do."; "Thanks. Offer went to Person D this morning."

## Run 26: step 3 on the five chains, current prompt (2026-09-20, 5 Sonnet calls, no retries)

`logs/fourstep_sonnet26.json`; 43,139 chars in, 36,032 out. Sound: family x dark x omission, family x strategic x
paltering. Holding with faults: careers x entrusted x commission ("Re:" reply-in-form to the [fact] email as the
[knows] clue; "make sure the office looks covered" in the [fact] clue; Person E used but undefined); careers x
strategic x omission (two threads in the [knows] clue; reference "IWD-SpinCo 0201" says spin-off). Inherited: business
x dark x paltering, victim on the [knows] clue because the run 25 part addresses the HR manager (step 2 now forbids;
part needs regenerating). No quoting leaks; [knows] acts plain; references otherwise say the matter not the fact.
Code changes: "no reference" check skips the [conflict] clue; new rec["plot_undefined"] (placeholders absent from
the people table); plot.md reference field: "the name this clue uses for the matter, as it appears, nothing else".

## Run 27: the business chain regenerated (2026-09-20, 2 Sonnet calls)

`logs/fourstep_sonnet27.json`. Step 2 on business x dark x paltering with the current parts prompt: the [knows] act
is arranged with a junior colleague (HR document requests, credential inquiries routed straight back to HR), the
victim not in it; the inherited fault did not recur. Step 3, no retry: all checks clean, no undefined placeholders;
[fact] via the reworded third-person carrier (a registrar's aside in a message about a transcript correction);
[knows] its own thread, plain; palter inside the HR manager's thread, passed on as settled. One slip: the forward
"to the department head" is addressed to Person D, the junior clerk; the department head is in no people table.
Code cannot catch a defined placeholder used for the wrong person.

## Fixes after the plausibility read, and run 28: step 2 with occasion (2026-09-20, 5 Sonnet calls)

Applied (user): (1) the shared-reference rule is gone: the plot decides per thread whether to name the matter at all,
a name says which matter not the fact, and a document's title appears only where the people on that thread would use
it; the "name the matter the same way" and "no reference" checks are removed; the reference field may be empty.
(2) after-menu "cancels a check" -> "drops a check they would otherwise have made". (3) step 2 [knows] names the act,
whom it is done with, and an ordinary occasion, done where the victim will not see it; the schema frame says the same,
so step 3 knows exactly what the act is. Run 28 (`logs/fourstep_sonnet28.json`; 18,167 chars in, 3,847 out): 5/5
give act + whom + occasion, victim absent; best: headcount templates split from the parent's model in a reconciliation
meeting. Costs: longer parts; palters at five clauses, one leaning; one act names the facility ("care-plan paperwork
the facility has sent over"); one "quietly". [fact] dropped the actor by itself on the strategic secret.

## Run 29: step 3 on the run 28 parts (2026-09-20, 5 Sonnet calls, no retries)

`logs/fourstep_sonnet29.json`; 44,093 chars in, 34,953 out. 4/5 carry the step 2 scene (accountant, sister, payroll
coordinator, planning coordinator) into the [knows] thread as given. Per-thread naming works: two unnamed threads,
the rest a date, a reference number or plausible file names; no internal labels on outsiders' mail. Stakes all new.
Failure: careers x entrusted x commission: step 2's "with the office scheduler" is a function, not a person, so the
plot invented a real client contact asked to confirm a non-existent site visit, refused in writing; implausible and
self-incriminating. Slips: "unprompted" used for a reply (business); one date off the timeline; a redundant forward
(strategic). Proposed, not applied: step 2 "whom it is done with" = a person who can be written to.

## Person A off the [fact] thread; prompt review (2026-09-20, no API calls)

The user's rule: any subset of clues must not give the secret, so [fact] and [conflict] cannot suffice together;
therefore the [fact] email is not addressed to Person A. Applied: plot.md's gate block now says the [fact] thread
shows the fact and nothing of Person A, who is not on it, and that it reaches the mailbox through someone else at the
firm; the [knows] thread is the first place A's hand shows; B is on no thread but [conflict]'s; the gate sentence is
back to "one clue on its own, or any two" (n=4: any one, two or three). plot_checks flags Person A on a [fact]
clue. shapes carrier.fact: four forms on threads A is not on (a record sent to a clerk/benefits/payroll/manager; the
other party writing to someone at the firm; a firm thread between others that mentions it; an event whose
consequences reach someone at the firm). Step 2 [knows]: "it leaves an email: it is done in writing with a person the
actor writes to" (run 29's "office scheduler" failure). All hand simulations rewritten to the new shape and passing:
a county withholding notice to payroll; the facility writing to the sister, who works at the firm; the recruiter to
the manager; the registrar to the tuition-reimbursement coordinator; outside counsel to the director; a hotel
confirmation naming both guests to the assistant who booked it.
Review for conflicts and needless constraints; removed: the [knows] carrier menu (step 2 now fixes the act, whom and
occasion, so a plot menu competed with it); "Nobody except Person A who has seen [fact] is on A's thread with B"
(covered by the gate); the quoting rule for the [knows] clue (impossible once A is off the [fact] thread; the gate's
"with whatever it quotes" covers the rest); the plot's extra [knows] line; email.md "the reference reads the same in
every clue" (no shared reference any more). Aligned: the omission two-thread rule and carrier now speak of the
[knows] thread, not an A-C [fact] thread (A cannot be on it); the plot intro says "nothing short of all three gives
it away" instead of "no single email". Kept on purpose: the AND-gate sentence, B only on [conflict], one part per
clue, the quoting paragraph, per-thread naming, the coin-flip menus for [fact], [conflict] occasion, after, naming.

## Simulation method updated to the model's habits (2026-09-20, no API calls)

scratchpad/sim/profile.md lists 13 habits of the model seen in runs 14-29 that my hand simulations lacked (length and
echo; keeping tails; the actor inside [fact]; menus read literally both ways; quotes as proof; padding; people
misuse; reply dates off the timeline; names that state the matter; commentary in fields; occasion/stake drift; wrong
kind under the label; lists as menus). sim7.py writes answers under those habits against the current prompts and runs
the checks. Code added from it: keeping-word flags on [fact]/[knows] parts (step 2) and threads (step 3); a
[conflict] over 60 words flag; more than three messages in a clue. Replayed over runs 24-29 they fire on real faults
(three keeping-word cases, one padded thread). What the current prompts + code catch: tails, quoting/forwarding to A,
padding, undefined placeholders, dates. What only reading catches: echo and length, literal menus (an invented gossip
thread passes clean), names that state the matter, commentary in fields, wrong-person placeholder reuse, occasion
drift. Main open risk exposed: for life-ground secrets the [fact] must reach a firm person other than A and B, and the
carrier "a thread at the firm between others in which the fact is mentioned" invites implausible gossip; the sound
routes are institutional (payroll, benefits, travel, expenses, security) or the other party at the firm. The Pipeline
tab has the profile and the catch table.

## Fixes from the model-like simulation, and the resimulation (2026-09-20, no API calls)

Applied: the [fact] carrier "a thread at the firm between others in which the fact is mentioned" is removed; the
menu is now the institutional route (a record to the office whose business it is: payroll, benefits, travel,
expenses, security, a manager), the other party writing to the firm on business of their own, and an event whose
consequences reach an office. plot.md: "Every field holds its value and nothing else". New plot checks: a
reference over six words; a [fact]/[knows] subject or reference sharing a content word (five-letter stem) with the
secret; a what_happens over 70 words; "unprompted" assigned but Person B writes first; choices with a gloss.
Resimulation under the model's habits: the careers chain now draws six flags (A on the [fact] thread via a forward,
"confidential", the record writer on the victim's thread, four messages, an off-timeline date, plus the new
reference and subject flags); the family chain under the new menu is plausible (a county withholding notice to
payroll) and draws only the narration and date flags. Replayed over runs 26 and 29 the new checks fire on the real
faults ('Meridian', 'SpinCo', sentence-long references). All clean simulations still pass. Uncaught by code and
left to reading: the echo itself, an unfit assigned option, the actor's doing inside the [fact] text, a defined
placeholder used for the wrong person, wrong kind at step 1.

## Run 30: steps 2 and 3 on the five chains, current prompts (2026-09-20, 10 Sonnet calls, no retries)

`logs/fourstep_sonnet30.json`; 60,130 chars in, 36,040 out. Step 2: all five [knows] are acts with a person and an
occasion; two good, one plausible but leaning (POA address), one contrived (delivery confirmations), one with the
fact inside ("to cover ongoing support payments"); "quietly" twice; palters 70 words with a leaning clause each.
Step 3: A off the [fact] thread obeyed 4/5, with institutional routes found by the model (payroll garnishment
address; registrar to an audit; HR partner to a team lead; recruiter to the manager). Breach: the coin's "event with
consequences" became a misdirected receipt forwarded to A (family strategic) and, in the business chain, an audit
letter forwarded to the victim (caught). New faults: a self-email (E to E); the [knows] thread stating the fact
(facility as address of record; support payments); the omission line turned into a denial when B's question asked
for the thing omitted. Three checks added and replayed: self-email; fact-part words inside the [knows] thread
(read); an omission line that denies (read). Verdicts: careers entrusted commission sound; careers strategic
omission and family dark omission hold with faults; family strategic paltering gate broken via [knows]; business
paltering victim on [fact] chain. Open: the "event with consequences" [fact] carrier misfires; the omission act
under a direct question inviting denial.

## The plot prompt as a briefing (2026-09-20, no API calls)

The user: adding a rule per failure makes the prompt a fence and produces new failures; brief the model instead.
plot.md rewritten: what the job is; why the parts are three and what that asks of the threads (the gate, one
part per clue); five places it breaks most easily, said as awareness (Person A on the [fact] thread; the [knows]
thread explaining itself; words that say hiding; an omission that denies or a palter that lies; quoting); what the
story must satisfy to read as life (people write to those they would, replies short, no self-mail, dates on the
timeline, an unfit option swapped and reported); then the four pieces, the choices, the pattern note, the JSON with
fields as values. Same placeholders (FIRST_PART dropped), same runner and checks. Omission's pattern note shortened.
Fact-word check on the [knows] thread tightened to words the plot adds beyond the step 2 part. All simulations
pass; old prompt in scratchpad/plot_before_briefing.md. Not run.

## Run 31: the briefing prompt on the run 30 parts (2026-09-20, 5 Sonnet calls, no retries)

`logs/fourstep_sonnet31.json`; 45,177 chars in, 36,461 out. Same parts as run 30, prompt changed to the briefing.
1 sound (careers entrusted commission), 3 hold (family strategic paltering: contrived clerical-error [fact] route,
stake dissolves as B holds off the contractor; business paltering: [fact] letter softened to "in progress"; careers
strategic omission: reference/subject say "restructuring"), 1 broken (family dark omission: payroll writes to A to
confirm the withholding order is his, A asks to handle it privately; A on the [fact] thread, caught). Fixed by the
briefing vs run 30: omission no longer a denial; no self-email; victim never on a [fact] chain; no keeping words in
threads; facility no longer named in the [knows] thread. Persisting: "event with consequences" [fact] carrier ->
clerical error (2/2 draws across runs 30-31); reply dates not listed as events (timeline_checks now accepts a reply
within 7 days of a listed message). Not changed: prompts.
Step 3 hand-off verified from the saved run-31 prompts: secret, all three step-2 parts verbatim, the resolved victim
on Person B's line, the actor on Person A's line, the kind and the ground line are all present in every chain.
Coin removed for life-ground chains (user): every menu line is "choose", and the [fact] event carrier (invoices,
renewals, bank or court queries) is offered only for work chains, since twice on a family secret it produced an
invented clerical error. Work chains keep the coin. Sims and stub pass.

## Run 32: briefing prompt, no coin for life chains (2026-09-20, 5 Sonnet calls, no retries)

`logs/fourstep_sonnet32.json`; 45,646 chars in, 36,373 out; run 30 parts. 1 sound (careers entrusted commission,
third clean run), 3 hold, 1 broken. All five [fact] threads correct and A-free (garnishment address to payroll;
facility to benefits under an LTC plan; recruiter to manager; registrar correcting a transcript; counsel to the
division manager); the life chains chose their own routes without the coin. Faults: family dark [knows] thread
names the victim and the keeping (inherited from the run 30 part); family strategic [knows] thread gives the facility
address (third run; the part's "an address other than the family home" invites it); business [knows] thread reports
A's request second-hand, A on no message (caught: holds clue without the holder); strategic omission line ends in
a false reassurance (flagged). Reference check false positive on "Aug 28 / Sep 4 / Sep 11" (slashes count as
words). Conclusion: step 3 now carries the parts faithfully, faults included; the two family faults live in the
step 2 parts.
plot.md tightened (user: duplication and over-explanation). Removed: the gate stated twice (intro); "swap an unfit
option" stated twice; "someone at the firm on every message" (already in the setting); "nobody emails themselves",
"use each placeholder for one person only", "every message date is an event, replies included" (single-failure
lines, code catches them); the stake's occasion sentence; the list of timeline events to include; the "in our
experience" tag. "Reassures" added to the pattern bullet after run 32's "nothing suggests the timeline shifts".
Template 878 -> ~640 words. Sims and stub pass.

## Run 33: the tightened briefing (2026-09-20, 5 Sonnet calls, no retries)

`logs/fourstep_sonnet33.json`. Read by hand for the gate and natural logic: 0 sound, 2 hold (family dark omission:
[fact] message under-states the fact, [knows] carries the keeping from the part; careers strategic omission: line
leans to reassurance again), 3 broken on the [fact] thread (facility writes to A at the office, forwarded to her;
recruiter's mail forwarded to A, no manager placeholder, an invented recipient; registrar writes to HR = the
victim). Run 32 on the same parts had all five [fact] threads right. Cut between the runs and plausibly the cause:
the who-writes-to-whom examples and the field-format sentence (every chain glossed its choices this run). Not
proof at n=5, but consistent. Code: omission check now also catches "nothing" and "unchanged". No prompt change made.
plot.md (user, after the run-33 review): a whole-set check added as part of the job: before answering, read the
threads as the reader would, one at a time and in pairs, with what they quote and who is on them; ask whether the
secret can be told and whether these people would have written this; change the thread rather than explain the
problem away in the timeline. Why step 2 holds and step 3 breaks, recorded: a thread adds a recipient, quoted text
and concrete detail to the part's statement, and the leaks live in those additions (recipient = A or B; the concrete
form of an abstract part = the fact). No code checks added; review is by hand (docs/review_run33.md).
plot.md rewritten (user: a 3/5 failure rate is unacceptable, fix by rewriting): the [fact] thread is given as a
positive route (written by someone other than A to a firm person who is neither A nor B and has ordinary business
with the fact, with five who-writes-to-whom examples; the letter names what it would name in life; it does not pass
through A's hands); "on a thread" defined (sender, recipient, cc, forward; a forward carries the letter); the
[knows] thread concrete about the act and empty of the thing behind it (no address or name that is the fact, no
reason; no hiding words); the cast completed before the threads (the person the fact is about, the other party,
the office, B; no undefined names); the whole-set check kept; the field-format sentence restored. 640 words.
Sims and stub pass. Not run.

## Run 34: the rewritten briefing (2026-09-20, 5 Sonnet calls, no retries), reviewed by hand

`logs/fourstep_sonnet34.json`. Holds: family dark omission (gate holds; but the line "states explicitly that there
are no pre-marriage obligations" is a denial, so the pattern is a lie); business paltering (sound). Fails: family
strategic paltering, pair 2+3, the attorney's "the facility's legal address" (step 2 part, fifth time); careers
entrusted commission, the manager forwards the recruiter's schedule to A (clue 1 alone gives fact + knowledge);
careers strategic omission, the coin's event carrier produced an invoice thread that never states the spin-off, so
all three together do not give the secret. [fact] routing right in 4/5 (vs 2/5 in run 33). Natural logic sound in
all five; stakes land in all five.

## Run 34, step 4: emails on the two chains that hold the gate (2026-09-20, 2 Sonnet calls)

`logs/fourstep_sonnet34.json` (emails on chains 1 and 4); 22,489 chars in, 13,170 out. The email step does its
job: short messages in the mailbox register, replies of a line or two, quoting below, the line kept in the actor's
voice (line_kept 0.65 and 0.97). Faults are upstream. Family/child support: a Person F used in the plot but absent
from the people table was cast by code as a firm employee, so the county caseworker writes from @ironwood.com;
the accountant thread carries the keeping; the reply to the wife states "there are no pre-marriage financial
obligations", a lie next to a listed student loan. Gate: the order names him in full, so clues 1+3 give the secret
without clue 2. Business/degree: the audit letter identifies the employee by case reference only, so no pair gives
the secret and all three do; "my transcript work speaks for itself" survives from the part. Design point recorded:
for a fact about the actor's own life, an any-subset gate needs the [fact] record without the actor's name and the
[knows] act as the link. Page: new Email generation tab.
READMEs updated (2026-09-20): prompts/v2/README.md rewritten to the current pipeline (two axes with Goffman's
kinds quoted from the 1956 monograph, the gated pool, the words, the four steps with fills, the fill files, what is
open); top-level README's Goffman reference, "What generates today" and repository layout point at v2.
Top-level README overwritten from prompts/v2/README.md (user): the v2 pipeline, kinds and pool now sit in the main
README with the still-true sections of the old one (opening, checking, mailbox, running, layout, references); the
pattern table is the three patterns, audience segregation noted as a device. The old README is kept whole at
docs/README_v1.md.

## n=2 prompts assembled (2026-09-20, no API calls)

The user wants to see n=2 results. Step 2 is unchanged (three parts always). Plot fills fixed for two clues:
PLAN_SHAPE says the first thread carries [fact] and [knows] together and the second [conflict], that Person A is
on the first thread and what keeps the gate is that nothing in it is kept from anyone; FEWER_CLUES says "either
clue on its own"; the [fact] paragraph starts "Where [fact] has a thread of its own". The assembled n=2 prompt is
in the scratchpad (plot_n2.md); a hand-written n=2 plot passes the plan and checks. n=3 prompts unchanged in
substance. What n=2 sidesteps: the [fact] letter reaching A, forwards. What carries over: [knows] inviting the
fact, keeping words, omission turning to denial.

## Run 35: steps 2 and 3 at two clues (2026-09-20, 10 Sonnet calls, no retries), reviewed by hand

`logs/fourstep_sonnet35.json`; 65,359 chars in, 68,265 out. Step 2: five parts sets; [knows] acts are fresh
(a hotel booking; a calendar block; a benefits-template question; a reimbursement routing; an accountant transfer
that again states its purpose). Step 3 at n=2: one plot returned no clues (family dark omission; not rebought);
four plots, four gates held: each clue-1 (fact+knows) shows a fact and Person A's act without any keeping, each
clue 2 is an ordinary exchange with B, only together do they say the secret. Best: careers entrusted commission
(recruiter's ref number reused on the calendar block). Faults: clue 1 is two separate threads in 3/4 (an
institutional letter plus a personal exchange), against "a clue is one thread"; the omission line is three
reassurances (a lie) from the step 2 part; a palter of four clauses; one implausible [knows] request (tuition via a
personal payment plan); one 'unprompted' misused; one [knows] event dated after the act.
Three prompt reads fixed (2026-09-20): the entrusted reading's instance list removed again (it had crept back with
the "person the fact is about" fix); the strategic reading's negative clause "not an outside party the plan is
aimed at" dropped, the positive half stands; clues.md reordered so the secret block comes before the three parts'
definitions, with the victim-resolution sentence beside the victim line and "one sentence each, third person, by
role" in the parts heading. Plot at n=2: the plan sentence says the fact+knows clue is one exchange (the record
reaches the person A then writes to, or A's act is a reply on the record's thread) and the [knows] paragraph
allows "on its own thread or sharing the [fact] thread". Prices checked: Opus 5.5 $4/$20 per M on OpenRouter,
Sonnet 4.6 (current preset) $3/$15, Sonnet 5 $2/$10.
Proofread of the assembled step 2 and step 3 (2026-09-20), fixes: (1) the omission act no longer says "covers the
other points" (which produced reassurances); it says the message does what it is for and is silent on the fact,
neither denying, reassuring nor giving a status; the schema frame says "answers or sends what was asked for and is
silent on the fact". (2) The [knows] part definition tightened and its schema frame reduced to the slots, since the
definition was repeated in the frame. (3) The cast block no longer repeats the plot's own "the people" instruction
and the insider line is one clause. (4) Duplicate people paragraph in plot.md cut to one sentence. (5) The [knows]
paragraph in plot.md no longer conflicts with n=2 and says "as the part gives it". (6) The omission plot note speaks
of "Person A's thread with that person" rather than "the [knows] thread", since at n=3 the [knows] thread is an act
with a third person. Sims and stub pass.

## Run 36: Claude Opus 5.5, steps 2 and 3 at three clues (2026-09-20, 10 calls, no retries), reviewed by hand

Preset `or-claude-opus` = anthropic/claude-opus-5.5 added to src/models/api_engine.py. `logs/fourstep_opus36.json`;
60,453 chars in, 34,349 out (about $0.42). Five of five plots hold the AND gate on every clue and every pair, and
all five read as life; the best Sonnet run on these parts was two of five. [fact] routes all institutional and
A-free (school aid office to HR; facility to the sister at the firm; recruiter to manager; insurer's screening to
the risk manager; lead bank to treasury). [knows] acts concrete and reason-free (a subscription redirected to Apt.
114; a car order to the rival's address; standing orders with a Tulsa account; new entity codes at close; evening
courses by personal cheque). Omission is silence; palters true in every clause; the lie is "dental appointment,
coded sick". One plot ordered the parts knows/conflict/fact. Minor: the child-support [fact] part carries the
actor's birth year and marriage.

## Step 4 rewritten, casting from the quiet pool (2026-09-24, no API calls)

Review of the email prompt as assembled (tone and logic), then the rewrite, by the order of the findings. Sequence:
the job is now the first line; the timeline is no longer passed (its events without a message were the outcome,
and the victim's replies narrated it: "I've already forwarded it to the adviser"); the people block is role and
side only, no function labels; the parts gloss is gone; empty reference lines are dropped; the leftover "two
messages about the same matter" sentence is gone. Tone: the style card is the quoting form only (it had stated
quoting as a rule, so every reply quoted; the profile says one message in four carries any quoted block); the
register comes from sample emails: each firm candidate's one real email, and two real outside emails; "what
happens" is "what it says"; Person A's line is given as points (points_of splits the reported-speech sentence at
its that-clauses) under "Person A's points, to make in Person A's own words". Logic: the plot schema gloss says
what_happens is "what the message says, and nothing of what its reader makes of it"; headers are fixed and code
restores them, so the name rule and the missing-people retry are gone. Casting: ten name-and-address pairs per
chain, five firm people from benchmark_pool/quiet_people.json (scripts/quiet_people.py: one email sent, at most one
received, not named in full elsewhere, no role fixed by the local model, firm domain only; 139 usable) and five
minted outsiders from benchmark_pool/fresh_names.json (scripts/fresh_names.py, against the release and the
anonymisation map); the model returns the cast and writes with the names; code checks the cast and assigns what
fails. The pipeline now reads the release (data/release/background_2000.jsonl, Ashford) instead of the regex
sample (Ironwood). Dry test with a simulated answer on the run 36 degree chain: cast check catches a firm role
given an outside name and reassigns it; headers, name forms and checks run through. No model run yet.

Addendum (2026-09-25): the minted outsiders have no mail of their own, so their register comes from the two outside
samples, now chosen by the chain's outsiders: one personal sample (family-word regex) where an outside role is family
or a friend, one business sample (work topics only) for the rest; one email per sender; mailers excluded; on a life
chain the business sample does not follow the topic.

## Run 37, round two: the three empties rebought (2026-09-25, 3 Opus calls, no retries)

Two parsed: family omission (child support) and careers lie (interviews). The third, careers omission (spin-off),
was cut by the API's content filter (finish_reason content_filter) after about 1,000 tokens, mid-letter, nothing
sensitive in the text; with round one's three empties that is four filter events in eight calls on these three
prompts, and two of the chains then went through, so it is stochastic and not by content. Raw answers and finish
reasons now in logs/api_raw.jsonl. Readings in scratchpad/notes37e.json and on the page.

Finding (upstream of step 4): on the two dark secrets about Person A's own life, the child and the degree, [fact]
with [conflict] gives the secret without [knows]. The [fact] letter names Person A (the plot: "she names Person A
with his 1963 date of birth"; the underwriter quoting the registrar about "Ms. Lankin"), and a father named on a
birth certificate, or the writer of a resume, cannot not know the fact, so the omission or the palter is a
concealment on its face. The run 36 pair-by-pair review passed these and was wrong under the any-subset rule. On
the three chains where the fact is about, or done by, someone else (the sister reserved the room; the manager
interviews; the firm plans the spin-off), [knows] is load-bearing and every pair holds. Step 2's "[fact] with
nothing of the actor in it" did not hold (birth year and marriage; "the clerk's personnel file"), and step 3 has to
name the employee for a letter to HR to be a letter. The shape that holds is the run 34 degree chain's: the record
identifies the matter by a reference, and only [knows] ties the reference to Person A. Not fixed yet.

Also seen: the email step invents names for people in no cast (interviewers, passengers, a contractor signing as
"Hal"), and nothing checks them against the corpus; the model wrote Ashford over the plot's Ironwood in one chain
and kept Ironwood in three. Outside samples are on the chain's topic (verified: every chain drew two emails labelled
with the secret's topic; the outside on-topic pool is 5 for careers and 5 for business and finance, 15 for family).

## Commands checked for cost and correctness (2026-09-25, no API calls)

A stub engine (`--engine stub`, src/models/stub_engine.py) replays stored answers so every command runs end to end
for free. Mailbox build in a copy of the repo, `--limit 500 --total 200`: three faults found and fixed. (1) the
sampler's per-topic floor of 100 cannot be met by a 500-email pool; build_mailbox now scales it (limit/40).
(2) the thread map data/topics/mid2tid.json had no producer; sample_dataset builds it by normalized subject when
missing (the released map came from the parent corpus, matches thread-by-thread, merges some same-subject
threads). (3) make_release's must-keep regression phrases exist only in the real 2,000 sample; the check now
applies to phrases the source has. Also: fresh_names read the old map name; src/models imported openai eagerly.
Generation stub runs: careers × entrusted, --facts 1: 13 calls (10 base + 3 plot re-asks, an artifact of
replaying one plot for every pattern); family, --k 1 --facts 3: 39 (30 base + 9). Money guards added:
generate.py chat_json retries once, not four times (a retry is a paid call; Opus returned empty on 4 of 8 step-4
calls in run 37); `--max-calls N` stops a run and saves the state; classify_topics estimates the bill and refuses
more than 5,000 API calls without --allow-big-run (the full pool is about $800 on Opus). Measured prompt sizes and
the cost table are in the README's Running section.

Topic prompt reworded (2026-09-25, user): the classifier's prompt now shows the list's format as [topic name]: [what it covers], no examples,
and asks for the [topic name] exactly as written. The released labels were made with the earlier wording
("each line is a topic name, then what it covers"); a re-run will use this one.

README and corpus converter (2026-09-25): scripts/parse_corpus.py turns the CMU maildir into data/enron/parsed_emails.parquet
with the pipeline's columns and types; checked on 3,000 messages against the parquet the released mailbox was built from:
ids, senders, recipients, dates, paths agree on all, subjects on 2,991, bodies on 2,752 (the rest differ in where the
quoted tail is cut; classify_topics cuts again). README: the corpus folder layout is in Quick start; the cost section
and every money mention are out (user: cost is a personal concern, not README material); data/names now ships with a
sources note (SSA, Census, GeoNames CC BY 4.0), the unused xlsx and zip dropped.

Renamed (2026-09-25, user): the repository folder is joint_secrecy_benchmark (was joint_privacy_benchmark); project name
joint-secrecy-benchmark; README title Joint Secrecy Benchmark. The venv's absolute paths were rewritten in place; the
memory directory was copied to the new project key.

## The tester (2026-09-27, no API calls)

The parent repository's agentic evaluation (enron_benchmark: src/agent, src/inspect_eval, run_inspect_agent_eval.py)
ported as src/tester/ and scripts/test_agent.py, against this repository's format: a sample is the release's threads
plus one chain's planted threads from a generation state file, placed by date, handles e1/t1; controls are the same
mailbox with nothing planted. Same five tools (list_threads, search with model rerank, read with related threads and
an auto-note, segment pages, answer), same gates (n distinct probes, read after search, full scan before an empty
answer), same score (found x match x evidence recall x precision, thread-level), judge prompt prompts/match.md with the
chain's secret, actor and victim as cast. Differences from the parent: no anonymisation step (the release is
anonymised and chains use pseudonyms); no To field (the release has none); BM25 copied into src/tester/retrieval.py;
the legacy text-protocol ReAct loop was not ported. Checked without a model: core gates and score
(tests/test_tester_core.py, 6 tests) and an end-to-end Inspect run on mockllm (turn limit, empty answer, rows.csv).
Not run on a real model yet.

Sampling with per-topic jitter on the GPT-6 Sol labels (user): `sample_dataset.py --total 2000 --jitter 5
--with-text --whole-threads --seed 20260927` gives 2,000 emails, 972 threads, 34 topics at 54 to 64 each (genres
and video gaming are below the 100 floor). Drawn to a scratch file; data/topics/sample.jsonl untouched. A shadowed
import in the sampler's thread-map fallback fixed on the way.

Tester report and cleaning (2026-09-27, user): no product score. The report is three counts: chains where the tester
said yes, chains where the judge accepted the finding as the planted secret, controls where it said yes. rows.csv keeps
the cited threads beside the planted ones. scripts/clean_background.py: the tester in sweep mode (background only, up
to N candidates, "report every fact one person keeps from another") with several models; a thread cited by --agree
models is removed with --apply, recorded beside the release. The unused-name reserve now comes from the anonymisation
pass itself (anonymize_llm.write_unused_names: the pools minus every token in the anonymised text and every pseudonym,
same seed), so pseudonyms and minted names are one list; scripts/fresh_names.py removed. Both tester paths checked on
mockllm; the anonymiser checked in the repository copy.

## Everything on a cheap API model (2026-09-27, openai/gpt-5-mini through OpenRouter, about $0.20 in total)

Four runs to check the code with a real model: generation steps 1 to 4 on one pair (16 calls: three chains with
emails, casts taken as given, lines kept 0.97 to 1.0); the whole mailbox build in a copy of the repository on 60
classified and 20 sampled emails (classify, sample, people, anonymise with the reserve, audit, release with its
regression checks, profile, quiet people); the tester on one chain and one control (budget 8, 300 background
threads: 15 turns, 14 tool calls, a no on both); the background sweep (7 tool calls, an empty answer at the budget);
and the judge on a true and a wrong finding (match and no match). Three faults found and fixed: (1) OpenAI's strict
tool schemas reject an optional parameter, so the segment tool's page number is required, -1 for the next page;
(2) a reasoning model spends its output cap on reasoning and returns nothing, so short answers on API models get
1,500 tokens (engine_factory.answer_tokens) in the classifier, the people and audit passes, quiet_people, and the
tester's rerank, note and judge calls; (3) the sampler's per-topic floor for a tiny pool is now at least 2, not 5.
Also dropped the dollar estimate from the classifier's message.

## Handoff of the mailbox rebuild and the background sweep (2026-09-27, no API calls)

The driver now draws the sample with `--jitter 5` by default (build_mailbox.py --only sample: 2,000 emails in 999 threads,
34 topics at 54 to 64 each with seed 20260910; genres and video gaming stay below the 100 floor). Riccardo runs the
rebuild from the sample stage on (people and audit are one call per email, 2,008 and 2,000; quiet_people one per
candidate) and the sweep with clean_background.py on models of his choice; nothing was run here. Sweep examples now
name the OpenRouter route for GPT-6 Sol (openrouter/openai/gpt-6-sol), since a bare openai/ string goes to OpenAI
directly.

## The AND check on the emails (2026-09-27, stub only)

scripts/subset_check.py, the user's design: blind probers (API models other than the generation model) read every
proper subset of a chain's planted threads and the full set, one call each with nothing else, and answer a simple
question, is there a secret here and what (prompts/probe.md). Each yes goes to the tester's judge (prompts/match.md)
against the answer key. Keep = no subset gives the secret to any prober and the full set gives it to every prober.
Output logs/subset_check.json with every answer and verdict; the state file is not touched. Dry run on the stub over
the four run-37 chains: 28 subset calls per prober, the stub says yes everywhere so all four drop, as it should.
Not run on a real model yet. Earlier checks were not this: the email step's flags are regex checks on the text, and
the September 14 subset probe ran on the one-pass secrets, not on emails.

## The AND check on local Qwen3-32B (2026-09-27, GPUs 4-7, no API calls)

The probe now answers in the tester's form, a candidates list with the secret and its evidence e-handles or an empty
list, so the same judge and the same three counts apply; the probe and judge prompts were cut to the rule and the
format. Run over the four run-37 chains with Qwen3-32B as prober and judge: 28 probe calls, all parsed, 11 of the
24 proper subsets said yes, 28 judge calls. Kept 1 of 4. 00 omission, family (dark secret): clues 1+2 give the secret
(the child from before the marriage, from the [fact] record plus the [knows] act), so the chain fails the gate. 03
paltering, business and finance: clue 2 alone and clue 3 alone each give the false-degree secret. 02 lying, careers:
kept; the two-clue sets that said yes named the wrong keeper and the judge refused them. 01 paltering, family (the
mother's facility): Qwen found nothing even with all three threads; a stronger prober will say whether the chain or the
model is at fault. One judge error: on 03 clues 2+3 the finding named the HR manager as the keeper and Qwen still said
match; the real run's judge is Claude Sonnet. Output logs/subset_check_qwen37.json.

## Step 5: the AND check with fix rounds, from the parent's loop (2026-09-27, stub only)

The parent repository's email step (enron_benchmark scripts/email_generate.py) generates the clue emails, blind-probes
every proper subset and the full set, and on a failure asks a diagnoser that sees the secret for the clue at fault
and one change, which it inserts as a revision block into the next generation pass; the atoms never change, up to
three rounds, then KEPT or DROP. Ported as step 5 of scripts/generate.py: src/andcheck.py holds the check (the
probes in the tester's answer form, the judge, the keep rule) and the diagnosis; prompts/diagnose.md is the
diagnoser, cut to the rule and the format, with our parts [fact] [knows] [conflict] fixed and a `step` field, plot
or emails, that says which step is redone with the change (the parent's one distribute step is our two). Flags
--probers, --matcher, --diagnoser, --rounds on chains, all and the new check command; --engine vllm or stub uses the
one engine for every part; the check's calls count toward --max-calls and go to logs/api_raw.jsonl. The chain's
and_check field holds every round with every answer and verdict and the status; assemble.py and the tester skip
DROP chains. scripts/subset_check.py folded in and removed. Stub runs: check with two rounds on two run-37 chains
(172 check calls, both DROP as the stub leaks everywhere), check only, and all with one fix round.

## Run 38: five secrets end to end on the API (2026-09-27, Opus 5.5 generating, GPT-6 Sol probing, judging and diagnosing, one fix round)

Five pairs, one secret each (careers dark work, personal finance dark life, law entrusted work, medical health entrusted
life, business and finance strategic work), 15 chains at n=3 on the Ashford background. 81 generation calls, 214 check
calls, about $3.5 in all. Result: 11 of 15 chains completed, 2 KEPT (business and finance under commission and under
paltering), 9 DROP, 4 errors.

What the run showed, in order of weight:
1. Anthropic's content filter. 12 of the 81 Opus calls came back empty with finish_reason content_filter, 11 of them on the
   email step; all three medical-health chains (a father's blood-pressure medication kept from the mother) and the
   personal-finance paltering chain died on it, two attempts each. Not a parse problem; the model's output was blocked.
   A fallback model for a filtered email call is the open question.
2. Full-set misses, not leaks, are the main failure: 9 of 12 checked chains had the full set unrecovered at least once.
   The judge's refusals fall in two groups. (a) The keeper: for the entrusted secret (law) every finding named the
   attorney hiding his own suspension, not the paralegal keeping it from the general counsel; for the strategic secret
   the findings named "Ashford management", not the plant manager; the answer key's actor is not who a blind reader sees
   keeping the secret. (b) Detail: "suspended" refused for lacking "practicing on it for months"; the concise judge
   prompt had lost the earlier "vaguer or more detailed wording is fine". Restored as one clause.
3. The fix round worked once and hurt once. Business and finance under commission: the [fact] email carried "keep this
   one close, nothing has been announced", clue 1 alone leaked, the diagnoser named it, the rewrite removed it, KEPT.
   Personal finance under omission: clues 1+2 leaked; the diagnoser replaced the named account owners with an account
   number, which cut the identity link, and the full set then failed: the swing to the opposite failure the prompt warns
   against. Eight of nine diagnoses chose the emails step; the law and careers misses look like plan-level faults that a
   wording change cannot reach.
4. The known dark-secret pair leak again: personal finance under commission leaked on [fact]+[conflict] both rounds.
5. One diagnosis came back empty at the 1,500-token cap (a reasoning model spent it all before the answer); the check's
   API cap is now 4,000. The judge's reason on a refusal was not being kept; it is now.
6. Casting: two chains got firm people named "dq Glisan" and "hb Spinks" (an initials login with the address surname),
   others "shaye Midolo" and "ford.serigny@ashford.com Serigny". The quiet pool has 18 of 139 such forms; the cast draw
   now takes only names of the form First Last, 106 people.
State: logs/generate.json; raw answers in logs/api_raw.jsonl.

After run 38 (2026-09-28, user): three changes. (1) A generation call the content filter empties goes once to a fallback
model, the judge's by default (--fallback, GPT-6 Sol); a plain empty answer is retried once on the generator first.
Recorded per chain. (2) The judge judges the matter, not its measure: figures, dates and durations the secret does not
give, or a detail of the secret the finding leaves out, are fine; the keeper and the victim may be a role or a group the
person belongs to. The judge's reason on a refusal now reaches the diagnoser, so a miss is fed back with what was
missing. (3) Step 1 writes the matter without its measure: no sums, fractions, counts, dates or durations in the secret
sentence; the plot sets those. Not rerun yet.

## Run 39: the same five pairs under the new prompts and the fallback (2026-09-28, Opus 5.5 generating, GPT-6 Sol probing, judging, diagnosing and as fallback, one fix round)

Same plan as run 38; step 1 is not deterministic, so the careers case became a procurement manager with a stake in a
contractor and the medical case a mother refusing a biopsy. 82 generation calls (13 of them on the fallback), 345 check
calls, about $4.60. 15 of 15 chains completed, 4 KEPT (personal finance and careers under omission, careers under
commission, medical under commission), 11 DROP, no errors. Run 38 was 2 KEPT, 9 DROP, 4 errors.

1. The fallback worked: 13 calls were content-filtered (12 emails, 1 plot), every one was resent to GPT-6 Sol and
   parsed; 8 chains have emails partly written by it, and they pass the code checks as Opus's do. The filter is not
   about the medical topic: it hit personal finance (3 chains), business and finance (3), law, careers and medical (1
   each). Roughly one email call in three is filtered on the first attempt.
2. The failure flipped from misses to leaks. Full-set misses fell from 9 chains to 3 (the two medical chains whose
   reader names the mother as the keeper, and one business chain). Round-0 subset leaks rose from 3 chains to 10:
   [fact]+[conflict] in 6 chains, [knows]+[conflict] in 3, [fact]+[knows] in 2, [fact] alone in 2, [conflict] alone
   in 1. The tolerant judge did what it was for on the law and careers chains, and the general secrets matched readings
   that carried the plot's figures.
3. The judge now over-accepts on the keeper. Under the group clause, "Ashford management has decided to close the
   plant but has not yet told the employees" read from the [fact] record alone counts as the plant manager keeping it
   from the crew; and "Kay and Akilah know the account fell" (the brokers) was matched to the husband keeping it from
   his wife. For a strategic secret the [fact] record itself says the plan is unannounced, so clue 1 leaks by
   construction under this judge.
4. The fix round: leak -> pass 3 (every one by de-identifying the actor in the [fact] record, the fix the memory on the
   pair leak names; the diagnoser found it on its own), miss -> leak 3 (the law chains: once the paralegal's knowing was
   made explicit, [knows]+[conflict] gave the secret), leak -> leak 6, miss -> miss 2 (medical: the mother's own
   concealment from her husband is the reading, whatever the daughter's clue says).
5. Diagnoses: 11 emails, 3 plot; the plot-step fixes were the ones that turned a chain (the omission personal-finance
   chain replanned clue 1 as an anonymised statement thread and passed).
Open: the keeper for entrusted and strategic secrets (what a blind reader sees keeping it is the subject, or the group);
the [fact]+[conflict] pair leak as a rule in the plot prompt rather than a fix the diagnoser has to find; the judge's
group clause versus "not yet told".

## Run 39 read through: the judge against the generator, and the fix loop's prompts (2026-09-28, no API calls)

All 125 judged findings read against the keys. The judge was wrong about 8 times: 6 lenient, 2 strict or inconsistent.
Lenient: on the strategic secret, "management has decided to close the plant but has not yet told the employees" read
from the [fact] record alone counted as the plant manager keeping it (4 verdicts across the three business chains);
"the brokers know the account fell" counted as the husband keeping it from his wife (1); "withholds whether it has lost
half its value" from the [conflict] clue alone counted as the loss (1). Strict: the law commission chain's clues 2+3
reading was refused in round 0 and an almost identical one accepted in round 1. The other refusals follow the key: the
entrusted readings name the subject (the attorney, the mother) as the keeper, which is what the emails show. So the drops
are mostly the generator's and the design's; the judge's own fault is the "not yet told" reading of a strategic [fact].

The fix loop, checked on the assembled prompts. (1) The diagnoser got the leaks and the full-set findings with the
judge's reasons, the plan, the emails, the history; it did not get the readers' evidence handles, nor the cast, so it saw
the plan as Person A and the emails as Bria with nothing linking them. Both added. (2) The prompts read cleanly.
(3) The generator did not know enough to avoid an over-fix: the email step regenerated from the plan with a fresh cast,
so the diagnoser's "rewrite e4" and its names meant nothing to it, and it never saw the previous emails or the gate.
Now a redo keeps the cast, the revision block carries what failed and what the readers found, the previous version (the
emails as the readers saw them with their handles, or the plan), the one change, the earlier changes, and the gate in
one line; for the plot step the names in the diagnosis are put back as placeholders. Each round's emails, names and
plan are kept in the state, so a run can be read afterwards.

## Where the reading drifts from the key, step by step, and the loop simulated (2026-09-28, no API calls)

Run 39 traced per chain from the secret through the parts, the plan and what each subset gave the reader. The secret
sentence never changes; what drifts is which concealment the emails make visible, and that is set at steps 1 to 3:
- Step 1, entrusted secrets: the sentence carries the subject's own concealment ("her mother is refusing the biopsy while
  assuring her husband her checkups are clear"; "the attorney has been practicing on a lapsed licence"). The reader
  reports that concealment, whose keeper is the mother or the attorney, not the actor.
- Step 2, [fact] and [knows] break their own rules in three cells: the medical [fact] copies the mother's lie ("she has
  told her husband her checkups came back clear"), so clue 1 alone is a complete secret (the one medical chain whose
  [fact] had no lie in it was KEPT); the careers [fact] names the actor as the owner ("the procurement manager holds a
  silent 15 percent share"), so the record at step 3 names them and [fact]+[conflict] leaks; the finance [knows] states
  the fact's measure ("a large capital loss"), so [knows]+[conflict] leaks.
- Step 3: the finance [fact] record names both spouses (the pair leak on record); the strategic [fact] thread is counsel
  and HR scheduling WARN notices, so "not yet told" is legible from clue 1 alone; the law [fact] thread has the attorney
  saying he will take care of it, which makes him the visible concealer.
- Step 4 adds tells: "keep this one close", a categorical lie ("the crash is in tech stocks we don't own") that clue 1
  exposes without clue 2.
- Step 5: the judge's group clause and, in run 38, its strictness on detail.
The fix loop simulated on a run-39 chain with recording fake models, an emails diagnosis and a plot diagnosis: per
round 14 probes and 8 judge calls, one diagnosis, one generator call for emails (three for plot, two of them the plot
step's own re-ask); the diagnoser's prompt carries the cast section and the evidence handles; the email redo keeps the
cast and, when the generator returns its previous answer, the emails come back identical, so "keep everything else as it
was" is possible; the plot redo carries the previous plan with names put back as placeholders. One finding on the way:
the run-39 state predates the stored draw, so on that state alone a redo would redraw the cast; new runs store it.

## Faults at steps 1 and 2: three levers (2026-09-28, user; stub and simulation only)

(1) The step-2 rules made concrete in prompts/atoms.json: [fact] as a record holds it, the matter and whom it concerns
by a reference, not the actor's name or role, and nothing anyone says, tells or hides about it; [knows] without the
fact or its measure, a sum, a count, a date, a loss. (2) A code check at step 2 with one re-ask (generate.part_flags):
the actor's role in [fact], a telling or assuring verb in [fact], a measure in [knows], hiding words. Over run 39's
15 clue sets it flags 9: the three careers [fact]s naming the procurement manager, two business [fact]s naming the
plant manager, the two medical [fact]s with the mother's lie, and two finance [knows] with "capital loss" and one
careers [knows] with a wire amount. (3) The diagnoser may now send a chain back to step 2 ("clues"), when a part itself
carries more than its piece; the clue prompt then gets the previous parts, the people by placeholder and role, the
readers' findings and the change, the plot and emails are redone from the new parts, and the new parts replace the old
in the secret record. Simulated with fake models on the careers commission chain: clue prompt, plot, emails, second
check, in that order. The parts are no longer described as fixed in prompts/diagnose.md.

## Step 2 alone on run 39's five secrets, under the new rules and gate (2026-09-28, Opus 5.5, 15 calls, about $0.30)

State logs/clues_test.json. All 15 sets filled and distinct, no re-ask needed: none of run 39's step-2 faults recurred.
[fact]s now name the matter by a reference: a family trust whose beneficiary is "Ashford employee ID 4471", "the person
in Ashford employee file P-1147", "site ref. CS-07", "a clinic patient file for a woman in her sixties" with the biopsy
"marked as declined"; the mother's lie is out of every medical [fact]; "with the plant manager's agreement" is out of the
business [fact]s; no [knows] carries a sum or a loss. Two subtler faults remain, now added to the gate: (1) in the
life-ground sets the [fact] still identifies the household ("held in the names of both spouses", "the couple's joint
retirement account", "the patient file for the mother"), so [fact]+[conflict] would still give the secret: 4 of 6 life
sets; (2) two careers [knows] name the contractor the fact concerns ("the Keller Pipeline Services K-1", "the partner's
statement from Ridgeline"), so [knows]+[conflict] would give it; the commission set shows the right form, an act with the
trust and no contractor. Not code-checkable but worth reading for: a [knows] that is itself a hiding act (statements
rerouted "no longer to the house"), and the entrusted [knows] acts about the attorney's signature block or the mother's
breast surgeon, which with the false line alone come close to the secret.

## The model chooses two or three threads (2026-09-28, user; stub only)

Step 2 now ends with the choice: three threads, one part each, when [knows] can be an ordinary act that stands alone
and says nothing of the fact; two when it cannot, and then [fact] and [knows] share one thread, the record reaching the
actor or the actor's act on the record's thread, and [conflict] has its own (the two-thread plan shape from the --vary-n
design). The choice rides in the clue set as n; the chain step takes it, --n forces a count, --vary-n cycles 2 to 4 as
before. The check enumerates two subsets and the full set at n=2. Checked on the stub and in tests; not run on a model
yet, so which secrets the model would put on two threads is still to be seen.

## Delivered on a pair (2026-09-28, user): the leaked set is the item, the prompt choice of threads withdrawn

The model no longer chooses two or three threads at step 2 (that section and field are gone; --n plans a count, --vary-n
cycles). Instead every chain is planned on three, and after a check a chain whose full set fails only because a pair
already gives the secret is delivered on that pair, when the pair holds the [conflict] thread (else there is no
concealment act in the item), every prober recovers it, and no single thread of it does (else the item is one email):
the pair satisfies the gate by itself, the third thread is dropped and recorded, the chain's n becomes 2. No calls: the
subset probes already made decide it. By default it is done before any fix round; --fix-first tries the fix rounds for
the three-thread item first. Applied to run 39's stored checks: 12 of 15 chains delivered (11 on two threads, 3 of them
at round 1 after the fix), against 4 kept; the three chains a fix round had kept on three threads would have gone out
on two at round 0 under the default, which is what --fix-first is for. The three left: the two medical chains where the
reader names the mother, and the business paltering chain where the [fact] thread alone gives the secret. The law
chains go out as [knows]+[conflict]: the paralegal's act and her false line, no record of the licence.

## Quotas, the third part renamed, and the plot prompt made to hold on its own (2026-09-28, user; stub and simulation)

--want-3 N --want-2 M on chains and all: chains are planned on three; while three-thread items are short a leaking
chain goes to the fix rounds before it is delivered on a pair; once the three-thread count is met the rest are planned
on two ([fact] and [knows] in one thread, the plan shape already in plot.md) and the run stops when both counts are
met; a batch of --workers chains at a time. Simulated with fake models: quota short, one diagnosis and one regeneration
then the pair; quota met, or no quota, the pair at once with no extra call. Each kept chain records its source, planned
or pair.
The third part is [concealment], not [conflict] (user: it is the actor's act of concealment toward the victim):
prompts, code, tests and README renamed; state files from before today are read through an alias and a migration on
load, so run 37 and run 39 still open. The slot family carrier_conflict is carrier_concealment.
Default stays three threads, and plot.md now carries the rules the runs taught, so the set should hold without the
loop: the [fact] record names the matter by a reference, not Person A's name, role or household, with the outcome in
the body and not in the subject or the reference, and a decision not yet announced held without a word on who has been
told; [knows] carries the record's reference and not the name of what the record is about, and is an act Person A could
do in the open; Person B's question in the [concealment] thread carries neither the fact nor its measure.

## The wording that mixed [fact] and [knows], fixed in order (2026-09-28, user)

Read from the assembled prompts. (1) plot.md said "[knows], on its own thread or sharing the [fact] thread" under a
three-clue plan; now "on its own thread" with three and "sharing the [fact] thread" with two. (2) The [knows]
definition asked for "the one thing ... that only someone who knows the fact would do" and called it "the reader's
proof"; the act most specific to a fact is the fact, so it now asks for "one ordinary thing the actor does or arranges
that the fact explains: a reader who has the record sees why; a reader without it sees routine". (3) The AND-gate text
said the same a third time, "the act that shows they know"; now "the act the fact explains". (4) plot.md's [fact]
letter "names what it would name in life, the fact included" pulled against the new reference rule; folded into one
sentence with "except the person". (5) The record's recipient is now also "nor the person the fact is about", after the
attorney's own reply made him the visible concealer. (6) "household" joined name and role in the [fact] rule. (7)
email.md: no message says a matter is confidential, asks for discretion, or says what has not been announced. (8) The
schema text for [fact] echoes the rule. Also found on the way: the rename had missed the bare label the code and the
state keys use; done, with the migration on the bare key.

## Proofreading the assembled prompts (2026-09-28, user)

Read as the model gets them, with the fills. Fixed: plot.md's opening summary still said "[knows] is Person A doing
something only someone who knows would do", the wording removed from the clue prompt earlier in the day; a missing comma
made "someone reading one clue on its own, or any two cannot say" misread; the [fact] paragraph's lines rewrapped and
its last clause turned round so "not Person A's name" no longer reads as if Person A were the person the fact concerns;
the people table said Person C is "the insider", and run 39 duly cast the attorney himself as the record's holder, so
Person C is now "not the person the fact is about"; match.md's "the same subject" could read as the subject line, cut;
diagnose.md's step sentence rewrapped. One real fault: for an omission, the plot's line field wrote what the message
leaves out ("It says nothing of his license status") and that reached the email prompt as one of Person A's points to
make; the field now asks for what the message says only, and points_of drops any "says nothing of", "is silent on",
"leaves out" clause before the email step sees it. Left as a proposal: the entrusted kind's reading at step 1 ("a fact
about someone else ...") says nothing about that person's own hiding of it, which is how the medical secret came to
carry the mother's lie; one sentence would settle it.

## The prompts read for order, repetition and manner (2026-09-28, user)

clues.md reordered: the secret, then what the matter is and whom the parts are written to, then how it is kept, then
the three parts, then the gate, then the output; the gate section now states the gate only, since the parts' own
definitions already say what each part leaves out; the sentence on the matter was in the template and in the fills,
now once; the omission act's three "does not" are "no denial, no reassurance, no status". plot.md's rules section
rewritten in one order, each rule once: the gate, the reader, the [fact] thread (recipient, examples, the reference
rule, decisions not yet announced), the [knows] thread (concrete, tied by the record's reference, an act done in the
open), the [concealment] thread, then the read-through; the opening restatement of the three parts, the sentence on
the people table (said twice elsewhere), the subject-line rule (the naming menu has it) and the [knows] line that sat
inside the choices list are gone; "It does not pass through Person A's hands" became "does not reach Person A by copy
or forward"; "a standing between" is "a standing arrangement between". secret.md no longer says the case may sit
anywhere when the ground line has just said where. Checked in the assemblies for both patterns and thread counts.

## Run 40: steps 2 to 4 on the five secrets under the new prompts, no check, no fix (2026-09-28, Opus 5.5, 55 calls, about $1.20)

State logs/run40.json. Step 2: 16 calls, one re-ask on a flag, fixed. Steps 3 and 4: 39 calls, 9 of the 30 first
attempts content-filtered and all 9 resent to GPT-6 Sol; 15 of 15 chains complete, the cast taken as given in all 15.
Read against the gate without a model:
- Held in all 15: Person A on no [fact] thread; the person the fact is about on none either (the attorney and the
  mother are in the people table and off the record's thread, where run 39 had them on it); every record by a reference,
  a registration number, a patient file, an account, a closure file; no email says confidential, asks for discretion or
  mentions what is unannounced (run 39 had several); every omission's points are what the message says; no victim's
  question carries the fact or its measure.
- Residue, by reading: (1) three [knows] acts are rerouting acts, paper statements stopped and sent "only to" the
  husband's address (finance, twice), the mother's clinic statements redirected to the daughter's address (medical);
  the plot prompt calls that a hiding, the clue prompt, where the act is chosen, does not yet. (2) One record names the
  actor: the brokerage's reply "a joint account registered to Javien Solinsky and Lilli Abedin", the rule not followed
  in 1 of 15. (3) The strategic [fact] records carry WARN-notice schedules and "with the site's agreement", which under
  the judge's group clause read as the manager keeping it from the crew from clue 1 alone. (4) The medical paltering
  chain has the father write "all she'll tell me is 'fine'", the mother's assurance from the step-1 sentence surfacing
  in the victim's words; the entrusted sentence at step 1 is still the open item.
- Code flags: the fact dated after the actor's line in two law chains; "the [knows] thread adds words of the fact"
  in four, mostly the shared reference the tie now requires, so that check is over-sensitive; 1998 in three account
  histories, harmless.
Not probed: a check with no fix rounds on these 15 would cost about $1.50 on GPT-6 Sol.

## Run 40 checked: GPT-6 Sol as prober and judge, no fix rounds (2026-09-28, 155 calls, about $1.50)

Kept 9 of 15 with no fix round: 5 on three threads (law paltering, careers commission and omission, business commission,
medical commission), 4 delivered on the [fact]+[concealment] pair (personal finance, all three; business paltering).
Run 39 kept 4 of 15 with one fix round each; run 38 kept 2 of 12. Every drop is a miss, no chain leaked without also
being recoverable, and no subset leaked on [fact] alone or on [knows]+[concealment]: the "nothing about who has been
told" rule held on the strategic records (three clue-1 leaks in run 39, none now) and the rewritten [knows] gave the
fact away with the false line in none (three in run 39). The pair leaks are the identity of the actor in or beside the
record: the brokerage naming the holders, the wife's question sitting beside a record of "the retirement account", the
closure file "with the site's agreement". The six misses: the tie from the reference to the actor is not on the page
(law omission: the roster lists 23816 with nothing saying whose it is; careers paltering: employee ID 4471 in the
register, tender PM-28/01 in [knows], nothing joins them), the reader took the concealment act for the matter (law
commission: "withheld a request for Hyman to sign"), the strategic reader named counsel and HR as the keepers (business
omission), and the two entrusted medical chains: the father's "all she'll tell me is fine" made the mother the keeper
again, and the omission's silence about a weekend visit was too faint to carry the biopsy. The reading before the run
called 9 of 15 right, too dark on the strategic clue-1 leaks and too light on the ties.

## Rerun of the six run-40 misses with reasoning and up to three candidates (2026-09-28, GPT-6 Sol, 59 calls, about $0.30)

--check-reasoning medium and the probe asked for up to three candidates, any match counting. Result 1 of 6 recovered:
the law omission chain, where the reader now tied registration 23816 to the attorney ("Harriet appears to keep from
Jess that Lina's registration 23816 had been listed as inactive"). The other five read as before: the co-sign request,
the record's recipient as the keeper (Akilah, Nena), the mother as the keeper, the specialist search. Two findings about
the test itself: (1) GPT-6 Sol reasons by default, about 250 completion tokens per probe against 36 of answer, and
"medium" moved that to 340, so the flag added little; the raw log's reasoning_chars is near zero because OpenRouter
returns no reasoning text for OpenAI models, and the engine's completion-token count is the measure. (2) Every probe
still returned exactly one candidate, so "up to three" was not taken up; the probe now says "list every fact one
person keeps from another that these emails show, up to three". Not rerun yet.

## The released mailbox installed as the dataset (2026-09-28, user; no API calls)

Riccardo's release mailbox-gpt-6-sol-2026-09-27, checksums verified: 2,000 emails in 1,007 threads over 34 topics,
sampled on the GPT-6 Sol labels with the driver's defaults (seed 20260910, jitter 5), anonymised with GPT-6 Sol on Azure
(replacement seed 910, 19 regression checks, 30 reviewed spans), the firm written as Keystone at keystone.com; one
sweep episode at high effort found one unconfirmed candidate in t_0598 and removed nothing. Installed: data/release/
(corpus and manifest), benchmark_pool/ (fresh_names 5,990; quiet_people 100 candidates, 66 name-consistent;
mailbox_profile; reference_bank; the quiet-people model record), the sample manifest, the model records of the people
and audit passes; the release's audit, validation, provenance, votes and .eval kept locally under results/clean_release/.
The private map is not in the release, so generate.py now takes the firm's domain from the casting pool and its name
from the domain's stem when the map is absent (Keystone, 1,656 mentions in the corpus). The old build's pre-anonymisation
files (real names) moved out of the repository into the session scratch; data/topics/sample_anon.jsonl, the old build's
anonymised sample, removed from the repository. The two tests that hard-coded the old thread count now read it from the
release. Run 39 and run 40 chains were cast from the Ashford build and stay as records; new chains cast from Keystone.
The attachment-name bank the plot step draws from (benchmark_pool/file_bank.json) still held the old build's 24 names;
mailbox_profile.py now builds it from the release, 49 names, and `--only-files` does that alone without the private
map. The two model records of the release's people and audit passes are tracked beside the release.

## Before the dataset run: the casting pool and the cleaning (2026-09-28)

The release's casting pool is 100 people, 82 with a First Last name; run 40 cast 3.4 firm people per chain, so 30
chains need about 100 and 93 about 316. "Each used once" would have emptied the pool inside a 30-chain run, so firm
people may now be cast in more than one chain, the least cast first (USED["people"] is a count); never twice in one
chain, and the tester plants one chain per mailbox, so a person in two chains never meets himself. Minted names and
domains are still one chain each (5,990 names). Stub run of 9 chains: 18 firm castings over 16 people, at most 2 each.

## Thread t_0598 replaced (2026-09-28, user; 4 calls on GPT-6 Sol, cents)

Opus 5.5 and Gemini 3.7 Flash, shown thread t_0598 with the probe prompt, reported the same kept-back letter GPT-6 Sol's
sweep had found (an assistant and a security officer deciding not to pass an ex-employee's angry letter to the CEO), so
under the consensus rule it goes. scripts/replace_thread.py: draws a thread of the same topic and length from the corpus
as the sampler would (labels, thread map, whole thread, two writers, not already in the release by a name-free body
signature), runs the people pass, then the release's own anonymiser held to the release (--firm Keystone
--firm-domain keystone.com, pseudonyms and outside domains from the reserve of unused names, --stats-from the release so
ordinary-word surnames stay words; the first pass turned "on both sides" into "on both agliano" on two emails' worth of
statistics), then the audit; swaps the thread in as t_1008, records the removal and the source ids in the manifest,
keeps the removed thread beside the release, and drops from the reserve every name sharing a token with the new text.
Result: e_002001 and e_002002, a two-message thread on "communication", audit clean, reserve 5,937 names. The private
map of the release was not needed and not touched; the new thread's people are not linked to it, so a person of theirs
who also appears elsewhere in the mailbox would carry two pseudonyms, which the sampler's choice of a quiet thread makes
unlikely.

## The five run-40 drops read by hand, and the fixes at their steps (2026-09-28, user)

Read in full: business omission is recoverable and the reader missed it (the month-to-month coal renewal of CSA-AS07-98
puts the manager in the know); careers paltering and medical paltering are recoverable by inference, with the tie from
the record's reference (employee ID 4471, patient file 4471) to the actor never on the page, and the medical one also
carrying the mother's "fine" through the father; medical omission is weak because the father asks about the weekend, not
the mother's health, where the part had him ask about her appointment; law commission is not established, since nothing
joins registration 48213 to the attorney the paralegal lies about. Fixes at the steps: (1) step 1, the entrusted
reading now ends "The fact is that person's state; what they themselves say or hide about it is no part of the case".
(2) step 3, the plot declares the tie in a `tie` field on the [knows] clue, the prompt names it as the reference by which
the record names whom it concerns, and a code check with one re-ask fires when the [fact] part's reference (a
registration, an id, a file, an account) recurs nowhere in the [knows] thread, or when the [fact] thread's text names
Person A or Person B; skipped for strategic secrets, whose plan file cannot sit in the actor's thread. Replayed over
run 40 it fires on four of the five drops and on the law omission chain, and passes the rest. (3) step 3, an omission's
occasion is the one the part gives. (4) step 4, a re-ask when the [fact] thread's bodies carry the actor's or the
victim's cast name (run 40's brokerage "registered to Javien Solinsky and Lilli Abedin"); replayed, it fires on that
chain alone. (5) the keeper defined the same way in the probe and in the tester's system prompt: the one who, knowing
the fact, writes to the other and leaves it out, denies it or dresses it up; a holder of the record is not keeping it.

## Run 41: the five secrets from step 1 under the new checks, checked with GPT-6 Sol, no fix rounds (2026-09-28, about $3.20)

State logs/run41.json, the Keystone mailbox. Fresh step-1 draws: an engineer's lapsed licence, a college fund lost on
technology stocks, a suspended attorney, a sister's HSV-2 diagnosis kept from her fiancé, a plant closure. The entrusted
sentence held: neither entrusted secret carries the subject's own concealment. 211 calls; 16 of the first plot and email
attempts content-filtered, all resent to the fallback, no chain lost. Kept 10 of 15 (6 on three threads, 4 pairs), 5
dropped, all misses. The step-3 tie check fired once (careers omission) and the re-ask satisfied it; every [knows] clue
but the four pairs' declared a tie; the step-4 record check never fired; run 40's faults did not recur.
The five drops read with Opus 5.5 and Gemini 3.7 Flash on the full set, judged by Sol: Opus recovers all five at its
first candidate, Gemini three. So the drops are the reader's, three ways: (1) the law chains, where Sol reports the
[knows] act (a replacement signer) as the secret and never joins the record's suspended registration to the attorney;
(2) the two medical chains, where Sol returns no candidate at all on an explicit HSV-2 record and a flat lie, and both
other readers find it at once; (3) careers, where Sol and Gemini name the victim by his address, lani.straka, while he
signs Shepherd, and the key had only the signed name. The key now carries the address where it differs from the name,
and the judge may take a person by address. The gate can now take the full set from any prober (--full-any, decide()
FULL_RULE); leaks count from any prober as before. Sol alone as prober and judge is not a strong enough reader for the
gate; the next check should run with a second reader and the any-rule.

## The prompts rewritten for one definition and a reason (2026-09-28, user's review of the page)

User: too many definitions, said twice, and no link from the segmentation to why. plot.md now: the secret, how it is
kept, the kind; "The secret is split into three parts, and each thread carries one:" with the parts each carrying a
one-clause meaning (atoms.json glosses, through parts_text, so diagnose.md gets the same); "In this way the threads
work as an AND gate: ..."; the people; then one paragraph per thread on what it may carry, and the read-through. The
paragraphs that defined the parts a second time, the list of example record writers, and the "four pieces" sentence on
the line field are gone. clues.md the same way: the secret and how it is kept, "Split the secret into three parts ...",
the parts, "In this way the parts work as an AND gate: ...", whom they are written to, the output; the [knows] rule cut
to three sentences and the paltering act to its terms. email.md's opening no longer says where the mail sits, since the
setting line does. diagnose.md no longer restates the parts. Assemblies checked for every pattern and both thread
counts, no placeholder left; the review page rebuilt and republished.

## plot.md: the thread rules folded into the parts, one gate sentence (2026-09-28, user's second review)

User: the "The threads" section repeated what <<PARTS_TEXT>> already said, and the gate line assembled to the same
thing three times ("each thread carries one", "[fact] and [concealment] are never in the same clue", "With three
clues, one part each"). Read against a run-41 assembly: what the section added beyond the parts was the reader rule,
Person A off the [fact] thread, the tie, and two case lines; its "rerouting mail ... is itself a hiding" sentence
contradicted the [knows] part it sat under (the paralegal rerouting the bar's envelopes) and belongs to step 2, where
atoms.json already has it. Now: each gloss carries its thread rule ([fact]: written by someone other than Person A to
someone at the firm with business in it, by a reference; [knows]: carrying the record's reference and nothing else of
the fact; [concealment]: on the occasion the part gives); <<SPLIT>> and <<GATE>> replace FEWER_CLUES, NEVER_TOGETHER,
PLAN_SHAPE and KNOWS_THREAD, one sentence each per clue count, the gate giving the reason it holds; the reader rule is
one sentence after it; <<CASE_RULES>> (case_rules()) shows the kind's plot_rule (kinds.json: the strategic
not-yet-announced line) and the pattern's (patterns.json: the omission and paltering question line, the omission
arrangement line) only to the chain they apply to, and <<PATTERN_RULE>> after the menus is gone. The "The threads"
section and the read-through paragraph are deleted. n is 2 or 3: --n takes 2 or 3, --vary-n alternates them, the "4"
templates and the four-clue plan check are gone. Stub run of 45 chains on both counts, no placeholder left; 19 tests.

## Run 42: steps 2 to 4 on run 41's five secrets under the folded plot prompt, no check, read by hand (2026-09-28, about $1.10)

State logs/run42.json, seeded with run 41's five step-1 secrets. 15 clue calls, no re-ask; 41 plot and email calls,
8 of them content-filtered and resent to the fallback (one plot, seven email sets); one plot re-ask (nobody at the
firm). Every [knows] clue declared a tie and every tie recurs in its thread; no record names Person A or B by first
name. Read thread by thread and pair by pair as a prober would, with the judge's standard (same matter, keeper, kept
from):
- pass on three threads: law paltering, and all three careers chains, where the licence number sits only in the
  record and the actor's thread and the concealment names the engineer without it;
- pass with a miss risk: medical omission, where file 4471 is never tied to the sister by name, only by the actor
  picking up its refills through the wedding;
- [fact]+[concealment] gives it in nine: the record and the concealment share what links them without the [knows]
  thread. The link is the matter's own name for the three strategic chains (Station 7, 12, 4 in both), the bar number
  written into the roster (law omission), the credit-facility closing in both (law commission), the one college fund
  (both finance commission and paltering), the children's surname Faigen in the record (finance omission), and the
  drug acyclovir in the record and the fiancé's question (medical paltering);
- [fact]+[knows] gives keeper and matter in three, where the [knows] act is mail rerouted away from home (finance
  commission and paltering, medical commission): the act itself says something is hidden, and the victim follows from
  "the house" or "the new apartment before her wedding". Five of the fifteen [knows] parts are mail rerouting.
Under the quota policy none of these drops: the nine become pair deliveries. The gate's premise, that a record plus a
false or evasive line does not show the actor knows, is not what the prober tests; a prober lists the pair as a kept
fact whenever the two threads name the same matter and person. So the [concealment] thread must not carry what links
it to the record, and for a strategic secret the record must name the site by reference as it names a person.
Drift at step 4: the finance palter gained "The college account's fine" (a false sentence on a palter) and the
strategic omission gained "That's the picture I have" (a reassurance on an omission), neither in the plot's line.
Cast: the law paltering plot cast Maribeth twice, so one reply comes from another address signed Maribeth. The name
pool holds "Girl Ankenbrandt". The actor-in-record check tests first names only, so the surname passed.
Nothing changed after this run; the fixes it points to are at step 2 (a rerouting flag), step 3 (the reference and
the matter's name kept out of [concealment]; the strategic record by reference, and its tie exemption removed),
step 4 (a surname test; add nothing on the matter beyond Person A's points).

## The code gates removed; the conditions are in the prompts (2026-09-28, user's decision)

User: no code checks; write the conditions into the prompt as a list the model checks before it answers. Each step's
prompt now ends with "Before you answer, check ... against these conditions", one line per condition, and the part
definitions in atoms.json and the glosses are trimmed to definitions so nothing is said twice. Step 2: [fact] names
no one by name, role or household and has no one telling or hiding; [knows] carries no measure, no company or
person the record is about, is not mail, statements or records moved out of sight, and says nothing is hidden. Step
3: the parts sit as laid out, no thread carries [fact] with [concealment]; placeholders and someone at the firm on
every message; the record names whom it concerns by the reference only, not Person A or B or the household; the
[knows] thread carries the reference in its tie field and a message; the [concealment] thread carries neither the
reference nor the record's particulars and names the matter as an outsider would. Step 4: the record's thread has
neither name, first or last, nor the household; a message with Person A's points adds nothing on the matter; one
name per placeholder, none twice. The strategic plot_rule adds: the record names the site by a reference, the
site's name sits in [knows]. Removed from generate.py: part_flags and its regexes and re-ask, the plot re-asks on
the plan, invented names, nobody at the firm and record_faults (with _codes and _thread_text), actor_in_record and
its re-ask. Kept: the plan read from the carries fields with the template when it does not hold (plan_fallback holds
the reason), the clue-count re-ask at step 4, and the passive records (plot_invented, plot_undefined, holds_leak,
isolation, fact_stated, line_kept, plot_checks). 17 tests; stub run of 45 chains on both counts, no placeholder left.

## Every rule of steps 2, 3 and 4 in the check list (2026-09-28, user's request)

User: the same rule-check style for all of steps 2, 3 and 4. The prose above each list now holds only the material
(secret, parts, cast, threads, names, style), the definitions and the reason (the gate); every rule is one item of
"Before you answer, check ... against these conditions". Step 2 adds: one sentence each, third person, people by
role; written to one person, named in [concealment] and the victim field. Step 3 adds: every message dated on an
event of the timeline, every date in the era; every field its value and nothing else (reference, choice,
what_happens); and the case lines (kinds.json and patterns.json plot_rule) are the list's last items. Step 4 adds:
a thread shows only its own messages; nothing confidential, no discretion asked, nothing unannounced said; Person
A's points in Person A's words, meaning kept, nothing beyond them; a reply reads as a reply; headers as planned
with the placeholders. Stub run on both counts, no placeholder left; 17 tests; page rebuilt.

## Proofread of steps 2, 3 and 4 against run 42 (2026-09-28)

User: every check the faults need, easy to follow, nothing twice or scattered, no definition that only confuses.
Out: the source quotes and citations from the pattern line and the paltering act (they stay in patterns.json and
atoms.json's act for the paper); the step-2 title's instruction repeated as a section; the definition of "the
matter"; "the actor's act against what they know:" before the act; "add anyone the threads need" said twice at step
3; the field descriptions said in the check list and again in the schema (the schema keeps them); "Who these people
are in the mailbox"; the naming menu's four-line gloss (now: real subject lines, real file names, a file name only
where the people would use it); "to make in Person A's own words" on the points label (the check says it); the
forward line's old firm code (/HOU/KEY, as the release has it); runs of blank lines in the name samples. In: step
2, [fact] names what it concerns by a reference and [concealment] names the matter as the victim would, without
the record's reference or particulars (run 42's station, drug and college-fund links were made at step 2); step 3,
Person A is not on the [fact] thread, and the [knows] thread says in Person A's words whom or what the reference
belongs to (the medical omission's lost tie); the omission case line adds no denial, reassurance or status (the
strategic omission's "that's the picture I have"). Person C's line: who writes or receives the record. 17 tests;
stub run on both counts, no placeholder left; page rebuilt.

## Run 43: steps 2 to 4 on the five secrets under the proofread prompts, no code gates, no check, read by hand (2026-09-28, about $1.10)

State logs/run43.json, seeded like run 42. 15 clue calls; 38 plot and email calls, 8 content-filtered and resent to
the fallback (three plots, five email sets). Against run 42, by reading: rerouting [knows] acts 7 to 0 (the [knows]
acts are now a co-signer asked for, aid forms requested, a seal reused, a seal block dropped, a colleague asked to
seal, an order cancelled, a short renewal term, a pickup authorisation, a spa booking changed, a refill collected);
the strategic record names the site by a code in all three (G-07, GEN-0417, GS-114) against Station 7, 12, 4 in
run 42; the record's reference in the [concealment] thread 1 to 0; the actor's surname in the record 1 to 0; every
[knows] thread carries the reference and says whose it is (run 42 lost one). The record's dollar figures stay in
the [fact] part, which is allowed.
Verdicts, the judge's standard as before: 11 pass on three threads (law omission, careers omission and medical
commission with no pair even guessable; the rest guessable only, the licence or file number in the record and the
person in the concealment with nothing joining them). 4 carry a pair risk: finance commission and paltering, where
the record's "custodial education account for two minor beneficiaries" and the wife's "kids' college fund" are the
same matter under two names and the only college fund in the mailbox; medical omission, where the record is sent
"ahead of the new coverage" and the concealment is the fiancé's spouse enrolment, the record carrying the
concealment's occasion; law paltering, where the general counsel asks "anything outstanding on Shelby's license
renewal?", closer than an outsider would. No [fact]+[knows] pair gives the victim any more. Run 42 had 5 pass,
9 pair links and 3 [fact]+[knows] links.
What the read turned up beyond the gate: (1) casting: 15 of the 32 firm people cast in this run hold different
roles in different chains (Delia Bexley a paralegal, then general counsel, then benefits; Davian Conser a plant
manager, then procurement; Ilan Polino a husband-accountant, then a pipeline engineer), which the assembled mailbox
would contradict itself on; the pool is reused least-used-first with no role memory. (2) The tie sometimes lands
where no one would write it: a clinic chart number given to a spa, "GEN-0417 is Millbrook Station" to purchasing,
"that's us here at Millbrook" to a buyer. (3) The Sol-fallback plot for the strategic omission is thin: two
single-message threads that restate the parts. (4) Chain 4's [knows] thread opens with a message addressed to both
parents, so the victim is on it; the reply is the husband's alone. (5) The years-out-of-era stat counts phone
number fragments (2046) and a past year in a sentence (since 1994).

## The invented world said once; a test of the content filter prepared (2026-09-29)

User: some Opus calls may be filtered because the prompt says names are put in afterwards, which can read as real people;
say the people are placeholders and never imply a real person or company. The shared setting (patterns.json, steps 3 and
4) now ends "The firm, the people and every address in it are invented."; plot.md's cast line is "Use these people, by
placeholder:". What the two runs show: step 2, no names, 0 of 30 filtered; step 3, placeholders only, 4 of 30; step 4,
names, addresses and sample emails, 12 of 30; by topic the plant-closure chains take 7 of the 16 (both runs' email calls
and one plot), law 5, careers 2, finance 1, medical 1. So names raise the rate and the topic raises it more. The filter
is on the output (empty answer, finish_reason content_filter), so wording changes it only through what the model writes.
A test is ready in the scratchpad (filter_test.py): the eight run-43 prompts that were filtered, sent again as sent and
in the new wording, three samples each, counting content_filter; dry-run on the stub. Not run: needs a yes.

## Run 43 checked with GPT-6 Sol, no fix rounds (2026-09-29, 136 check calls, about $2.30)

`check --rounds 0 --matcher openai/gpt-6-sol` on logs/run43.json. Kept 8 of 15, all on three threads; dropped 7: six
misses on the full set (law omission, finance omission, careers commission and paltering, strategic paltering, medical
paltering) and one single-thread leak (finance paltering: the palter's "with the whole market down this year nobody's
statements look good" gave Sol "the college fund has lost value", which the judge took as the matter).
Against the hand reading (11 pass, 4 pair risks): Sol never took a [fact]+[concealment] pair in any chain, so none of
the four risks showed; the judge refused every [fact]+[knows] candidate for the wrong victim (the guidance counselor,
the sealing colleague, the procurement clerk) and every [knows]+[concealment] candidate for the wrong matter (a refill,
boiler tubes, a co-signature), as designed. Sol's failure is the full set: three chains with no candidate at all (the
law omission, both careers chains, where the record's number sits in the actor's own thread as "my seal", "my number")
and three with the [knows] act reported as the secret (the account's existence, the one-year coal term, the spa
change). The same reader weakness as run 41, where Opus 5.5 recovered all five drops. Sol reads at medium reasoning.
The check's reader, not the generation, decides these six; a second reader on the full set with --full-any, or Sol at
high reasoning, is the next test.

## The six run-43 misses read again on the full set by three readers (2026-09-29, 35 calls, about $1.50)

Scratch script reprobe.py: the full set only, the probe prompt as in the check, Sol the judge. Sol at high reasoning
recovers 2 of 6 (both careers chains); Opus 5.5 and Gemini 3.7 Flash recover 5 of 6 each, at their first candidate.
All three miss the law omission: Opus reads Delia, the general counsel who forwards the roster with her warranty, as
the one keeping the suspension from the insurer, and Kandice's co-signature request as nondisclosure to the outside
firm; the judge refuses both for the people. Sol at high reasoning still reports the [knows] act on the finance and
strategic chains and the spa change on the medical one. So five of Sol's six misses are the reader's, one is a chain
whose victim reads as a participant. Gemini 3.7 Flash reads as well as Opus here at a fifth of the price and is not
the generator; the check should run with Sol and Gemini 3.7 Flash as probers and --full-any.

## Final pass over the pipeline and the fix loop (2026-09-29)

User: a last check that every prompt has the latest fixes, the fix loop included. Step 1 (secret.md) had not: it now has
the same shape as the others, the material, the four fields, then "Before you answer, check the cases against these
conditions" (destructive information, a standing state, concrete and within bounds, no sums or dates in the secret,
people by role); Goffman's quotes and pages leave the prompt (kind_line gives the name and the plain reading; the
quotes stay in kinds.json for the paper). The fix loop: the revision block now sits before the conditions and the
output of the redone step (with_revision), not after the schema; its closing line no longer restates the gate, since
the conditions follow; diagnose.md's leak, miss and step definitions name the new conditions (the [concealment]
thread carrying the record's reference or particulars, the [knows] thread's reference and whose it is, rerouting).
The three redo paths (clues, plot, emails) exercised on the stub with a forced diagnosis: each redone prompt carries
the readers' findings, the previous version and the change before its conditions, no placeholder left; a real
diagnosis prompt assembled from run 43's dropped chain fills every field. README: the step-2 code check paragraph
replaced by the conditions-in-the-prompt sentence; "code checks it" for the cast is now "code puts the names into
the headers"; the dead "people retried" report field removed. 17 tests; stub run end to end on both counts.

## The seven dropped chains of run 43 checked again with Gemini 3.7 Flash as prober, Sol as judge, the any-rule (2026-09-29, 63 calls, about $0.70)

On a copy, logs/run43_gemini.json, so the Sol check stays in logs/run43.json. Kept 6 of 7: the strategic and medical
paltering chains on three threads; the finance paltering and omission and both careers chains delivered on the
[fact]+[concealment] pair, which Gemini reads by itself (the record's "custodial education account for two minor
beneficiaries" against the wife's "kids' college fund"; a lapsed licence number against "my license is current"),
the guess the hand reading called; the law omission still gives nobody anything. Gemini did not take the finance
palter's single thread that Sol took. So a strong reader takes the pairs Sol leaves alone, and the pipeline's answer
to that is the pair delivery. Put together with Sol's round: 8 on three threads by Sol, 2 on three and 4 on pairs by
Gemini, 1 drop, though Gemini did not re-read Sol's eight, where it may find pairs too (the law paltering and finance
commission risks). The check should run both probers from the start, with --full-any.

## Run 44: the first dataset run, 10 secrets, 30 chains, three readers (2026-09-29, 614 calls, about $10)

`all --topics "law,careers,personal finance,family and relationships" --k 1 --facts 12 --rounds 1 --probers openai/gpt-6-sol
--full-probers anthropic/claude-opus-5.5,google/gemini-3.7-flash --matcher openai/gpt-6-sol --full-any`, state
logs/run44.json. Step 1 gave 10 secrets, not 12: the graded pool holds strategic secrets for careers and family and
relationships only, so law and personal finance have two kinds each (5 work, 5 life). Steps 2 to 4: 173 calls, 21
content-filtered and resent to the fallback (3 of 30 at step 2, which had never been filtered before; 18 of 62 at
steps 3 and 4), the invented-world sentence making no visible difference. The check: 441 calls, Sol on the seven
subsets, Opus and Gemini on the full set only (--full-probers, new), the any-rule. Kept 30 of 30: 25 on three threads,
5 on pairs; two fix rounds, both misses, both redone at the emails and kept. Full set read by Opus 29 of 30, Gemini 28,
Sol 21, so the full-set readers decided 9 chains. No [knows] part reroutes mail; no strategic record names its site.
The five pairs: one is [fact]+[concealment] (careers commission, the countersigned offer against "committed to
staying"); four are [knows]+[concealment] (finance paltering and omission, law commission, family paltering), where
Sol read the matter from the actor's act and the concealment together and the judge took it as the matter (a cash-out
refinance and a palter about debts; a filing sent over another's signature and "my license is in good standing"; a
car policy reissued in her name alone and attorney meetings called will updates). Those four items carry no record
thread. The fix rounds: careers commission, "the emails do not establish that he knows about the record", one line
added; careers paltering, "our company" instead of the rival's name and a name mismatch, the emails rewritten.
Cost: generation about $2.50, the check about $7.50.

## keystone30 (2026-09-29)

Run 44's state, mailbox and answer key installed as data/benchmark/keystone30/ (state.json, mailbox.jsonl, answer_key.json,
README.md). assemble.py now places every chain the check kept; the passive records (isolation, holds_leak) no longer
keep a chain out, since the check's readers found no leak where the heuristic saw one (family paltering, chain 1); a
chain with a placeholder left unreplaced is still skipped as unusable. scripts/run_testers.py runs one or more tested
models over a state file with one judge and writes results/tester/table.md; the tester's samples take their kind from
the secret record.
