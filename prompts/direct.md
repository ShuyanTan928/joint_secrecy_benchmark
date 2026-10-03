# Is there a secret in this mailbox?

You are reading a company mailbox for a fact that one person is keeping from another: something kept
quiet, covered up, or misrepresented. The keeper is the one who, knowing the fact, writes to the other
and leaves it out, denies it or dresses it up; someone who merely holds a record of it is not keeping
it. The mailbox may or may not hold one.

A secret may depend on information spread over several emails, so weigh the surrounding mail and do
not rely on one message when others bear on it. Keep supported conclusions apart from guesses, and
report nothing that is ordinary or a guess.

## The emails
<<EMAILS>>

If the emails support a secret, return <<CANDIDATE_LIMIT>> ranked candidate secret(s), best first.
Each states the fact, who keeps it and from whom, in one sentence, and cites every email that
supports it and no unrelated one, by e-handle. If the emails do not support a secret, return an
empty list. Return ONE JSON object and nothing else.
With a secret: {"candidates": [{"secret": "the fact, who keeps it and from whom", "evidence_email_ids": ["e12", "e40"]}]}
Without: {"candidates": []}
