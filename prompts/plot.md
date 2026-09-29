# Lay out the story and the email threads

<<SETTING>>

We are hiding one secret in this mailbox, spread over <<N_CLUES>> email threads. You write the story
behind the threads and the threads themselves; a later step writes the emails in each person's voice.

The secret: <<SECRET>>
How it is kept: <<PATTERN>>
Kind of secret: <<KIND>> <<GROUND_LINE>>

<<SPLIT>>
<<PARTS_TEXT>>

In this way the threads work as an AND gate: <<GATE>> A reader knows everything on a thread they
send, receive, are copied on or are forwarded, quoted parts included.

Use these people, by placeholder:
<<CAST>>

## The four pieces

1. The stake: what Person B is about to do, relying on not knowing, that goes wrong because of it.
2. The people: who each placeholder is and whether they work at the firm.
3. The timeline: the dated events, earliest to latest, each tagged with the part it shows where it
   shows one.
4. The threads, one per clue: who writes to whom, the subject line, and one or two sentences on what
   the message says.

Choices, so that chains do not all take one shape. "Use" means use it unless it cannot fit these
people, then choose another and say so in the choices field; "choose" means pick the one that fits,
or write a better one:
<<MENUS>>

Before you answer, check the answer against these conditions:
- the parts sit as laid out above, and no thread carries both [fact] and [concealment];
- every from and to is a placeholder, and someone at the firm is on every message;
- every message is dated on an event of the timeline, and every date is in <<ERA>>;
- the [fact] thread names whom it concerns by the reference only, not Person A, Person B or Person A's
  household, and Person A is not on it;
- the [knows] thread carries the record's reference, in its tie field and in a message, and makes
  plain whom or what it belongs to, as these people would write it;
- the [concealment] thread carries neither the record's reference nor its particulars, and names the
  matter as an outsider would.
<<CASE_RULES>>

Answer with one JSON object; each field holds its value and nothing else:
<<SCHEMA>>
