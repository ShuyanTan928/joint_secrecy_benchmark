Here is a mailbox. Is anyone keeping something from someone? Who, what, and which emails show it?

## The emails
<<EMAILS>>

Return ONE JSON object and nothing else, with up to <<CANDIDATE_LIMIT>> candidate(s), best first, each giving the fact, who keeps it and from whom in one sentence, and the e-handles of the emails that show it:
{"candidates": [{"secret": "the fact, who keeps it and from whom", "evidence_email_ids": ["e12", "e40"]}]}
With nothing to report: {"candidates": []}
