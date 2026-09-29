# Write the emails

The threads below are planned: who writes to whom, when, under what subject, and what each message
says. Write the messages.

<<SETTING>>

The people:
<<CAST>>

The threads:
<<PLOTS>>

Everything but Person A's points is yours to write, in the voice of whoever sends it and in the way
that person would write to the person they are writing to. This is office and home mail of 2001, and
it reads like the samples below: some messages are a line dashed off with no greeting, some run long
and carry other business, dashes and dots are common, and people name the places, schools and shops
they mean.

Give each person one of the names below: people at the firm a firm name, the others an outside name.
Write the messages with those names, greeting and signing as the person whose name it is would.
<<NAMES>>

<<MAILBOX_STYLE>>

Before you answer, check the messages against these conditions:
- each thread shows what its own messages say and nothing from another thread;
- no message says a matter is confidential, asks for discretion, or says what has not been announced;
- where a message gives Person A's points, they are in Person A's own words with their meaning kept,
  and the message says nothing on the matter beyond them;
- a message gets to its point: a reply answers what was asked, often in a line or two; a sender
  introduces themself only to a stranger; nobody tells a reader what the reader already knows;
- a reference appears where and as the people on the thread would write it: in a subject line, on a
  form, beside a name, in passing;
- what Person B goes on to do comes up in passing, as it would between these two people;
- the record's thread names neither Person A nor Person B by any name, first or last, nor anyone of
  their household;
- each placeholder has one name from the lists, and no name is used twice;
- the from, to, date and subject of every message are as planned, written back with the placeholders.

Answer with one JSON object. The cast says which name each placeholder has.
{"cast": {"Person A": "the address chosen", "Person B": "..."},
 "clues": [{"i": 1, "messages": [{"from": "Person ?", "to": ["Person ?"], "date": "YYYY-MM-DD", "subject": "...", "body": "..."}]}]}
