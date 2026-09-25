# Write the emails

Write the email threads planned below as they would sit in this mailbox in <<ERA>>. Each thread is
planned already: who writes to whom, when, under what subject, and what each message says. You
write the messages.

<<SETTING>>

The people:
<<CAST>>

The threads:
<<PLOTS>>

Each thread shows what its own messages say and nothing from another thread.

Where a message gives Person A's points, make them in Person A's own words and keep their meaning.
Everything else is yours to write, in the voice of whoever sends it and in the way that person
would write to the person they are writing to. A reply reads as a reply: often a line or two,
answering what was asked, without restating the question or announcing what the message does.

Who these people are in the mailbox. Give each person one of the names below: people at the firm
take a firm name, the others take an outside name. Write the messages with those names, greeting
and signing the way the person whose name it is would.
<<NAMES>>

<<MAILBOX_STYLE>>

Answer with one JSON object. The from, to, date and subject of every message are as planned; write
them back as given, with the placeholders. The cast says which name each placeholder has.
{"cast": {"Person A": "the address chosen", "Person B": "..."},
 "clues": [{"i": 1, "messages": [{"from": "Person ?", "to": ["Person ?"], "date": "YYYY-MM-DD", "subject": "...", "body": "..."}]}]}
