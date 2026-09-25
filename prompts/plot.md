# Lay out the story and the email threads

<<SETTING>>

We are hiding one secret in this mailbox, spread over <<N_CLUES>> clues, each clue one email
thread. Your job is the story behind the threads and the threads themselves; a later step writes
the emails in each person's own voice.

The secret: <<SECRET>>
How it is kept: <<PATTERN>>
Kind of secret: <<KIND>> <<GROUND_LINE>>

The three parts, already decided:
<<PARTS_TEXT>>

The people, by placeholder (real names and addresses are put in afterwards):
<<CAST>>

## How the three threads carry the three parts

The secret is that Person A keeps this fact from Person B. [fact] is the fact with no one hiding
it; [knows] is Person A doing something only someone who knows would do; [conflict] is Person A's
act toward Person B. Together they say the secret; apart they do not, and the threads must keep
it so: someone reading <<FEWER_CLUES>> cannot say that Person A keeps this fact from Person B.
<<NEVER_TOGETHER>> <<PLAN_SHAPE>>

A reader takes anyone who sends, receives, is copied on or is forwarded a message to know what
it says, and takes them to know the whole of what it quotes or forwards. So if a letter reaches
Person A by forward, the reader knows Person A has read it.

Where [fact] has a thread of its own, it is written by someone other than Person A to someone at
the firm who is neither Person A nor Person B and who has ordinary business with the fact. That is how a private
fact sits in a work mailbox without showing that Person A knows it: a recruiter writes to the
candidate; a county office writes to payroll about an employee's wages; a care facility writes
to the sister who signed, or to benefits about a plan; a registrar answers a benefits clerk's
verification; outside counsel writes to the officer who retained them. The letter names what it
would name in life, the fact included; what it does not do is pass through Person A's hands.

[knows], on its own thread or sharing the [fact] thread, is Person A's act as the part gives it,
done with the person the part names. Make the act concrete, the request, the date, the account,
and leave the thing behind it out: no address or name that is the fact, no reason. A reader of
that thread alone sees an ordinary request, and nobody in it writes "quietly" or "keep this
between us": people who hide things do not announce it.

The [conflict] thread keeps the pattern. An omission stays silent even when the question is
pointed; an answer that denies or reassures has become a lie. A palter is true in every clause.

Every person a thread needs is in the people table with a placeholder and a role before the
threads are written.

Each thread is easy to make reasonable on its own; the set is what has to hold. Before you answer,
read the threads you have written as the reader would, one at a time and then in pairs, with
whatever they quote and whoever is on them, and ask whether the secret can be told from what is
there and whether these people would have written this. Where it can, or they would not, change
the thread; do not explain the problem away in the timeline.

## The four pieces

1. The stake: what Person B is about to do, relying on not knowing, that goes wrong because of it.
2. The people: who each placeholder is and whether they work at the firm; add anyone the threads
   need, continuing the letters.
3. The timeline: the dated events, earliest to latest, all in <<ERA>>, each tagged with the part
   it shows where it shows one.
4. The threads, one per clue, each message dated on an event of the timeline: who writes to
   whom, the subject line, and one or two sentences on what the message does. The line field
   gives Person A's message to Person B in substance.

Choices, so that chains do not all take one shape. "Use" means use it unless it cannot fit these
people, then choose another and say so in the choices field; "choose" means pick the one that
fits, or write a better one:
<<MENUS>>
<<PATTERN_RULE>>

Answer with one JSON object. Every field holds its value and nothing else: a reference is the name
a thread uses for the matter, or empty; a choice is the option's first words; what_happens says
what the message says, and nothing of what its reader makes of it.
<<SCHEMA>>
