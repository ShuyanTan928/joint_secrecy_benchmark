"""The AND check: subset enumeration, the keep rule, the answer form and the revision block, without a model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.andcheck import candidates_of, check, decide, findings_text, reduce_to_subset, revise_block, subsets   # noqa: E402


def test_subsets_cover_every_nonempty_set_with_the_full_set_last():
    s = subsets(3)
    assert len(s) == 7 and s[-1] == (0, 1, 2) and len(set(s)) == 7
    assert subsets(2) == [(0,), (1,), (0, 1)]


def test_keep_needs_no_subset_leak_and_the_full_set_from_every_prober():
    full = {(0,): False, (1,): False, (0, 1): True}
    assert decide({"a": full, "b": full}, 2)["keep"]
    d = decide({"a": full, "b": {(0,): True, (1,): False, (0, 1): True}}, 2)
    assert not d["keep"] and d["leaks"] == [{"model": "b", "threads": [0]}]
    d = decide({"a": full, "b": {(0,): False, (1,): False, (0, 1): False}}, 2)
    assert not d["keep"] and d["full_set"] == {"a": True, "b": False}
    assert not decide({}, 2)["keep"]
    import src.andcheck as ac
    ac.FULL_RULE = "any"
    try:
        assert decide({"a": full, "b": {(0,): False, (1,): False, (0, 1): False}}, 2)["keep"]          # one reader is enough under "any"
        assert not decide({"a": {(0,): True, (1,): False, (0, 1): True}, "b": full}, 2)["keep"]         # a leak from any reader still counts
    finally:
        ac.FULL_RULE = "all"


def test_candidates_take_the_testers_form_and_an_empty_list_is_a_no():
    assert candidates_of({"candidates": []}) == [] and candidates_of(None) == [] and candidates_of({"candidates": [{"secret": " "}]}) == []
    assert candidates_of({"candidates": [{"secret": "a child kept from the wife", "evidence_email_ids": ["e1", "e3"]}]}) == \
        [{"secret": "a child kept from the wife", "evidence_email_ids": ["e1", "e3"]}]


def test_revision_block_names_the_change_and_the_history():
    assert revise_block({"change": ""}, []) == ""
    report = {"full_set": {"p": True}, "calls": [{"prober": "p", "threads": [0], "full_set": False, "correct": 1, "candidates": [{"secret": "the child", "evidence_email_ids": ["e1"]}]}]}
    b = revise_block({"why": "clue 1 names the outcome", "change": "use a bare reference", "step": "plot"}, ["move Person A off the record"], report, "clue 1: the record")
    assert "## Revise" in b and "use a bare reference" in b and "move Person A off the record" in b
    assert "clues [1] alone, p: the child (from e1)" in b and "The previous version:\nclue 1: the record" in b and "keep everything else as it was" in b


def test_findings_text_lists_leaks_by_clue_number_and_the_full_set():
    report = {"calls": [{"prober": "p", "threads": [0], "full_set": False, "correct": 1, "candidates": [{"secret": "the child"}]},
                        {"prober": "p", "threads": [1], "full_set": False, "correct": 0, "candidates": []},
                        {"prober": "p", "threads": [0, 1], "full_set": True, "correct": 0, "candidates": [{"secret": "something else"}], "judge_reason": "a different matter"}]}
    leaks, full = findings_text(report)
    assert leaks == "- clues [1] alone, p: the child" and full == "- p: something else (the judge: a different matter)"


def test_a_chain_is_delivered_on_a_pair_that_holds_the_gate_by_itself():
    def rep(matches):
        calls = []
        for size in (1, 2, 3):
            for t in __import__("itertools").combinations(range(3), size):
                calls.append({"prober": "p", "threads": list(t), "full_set": size == 3, "correct": int(t in matches), "candidates": []})
        return {"calls": calls}
    assert reduce_to_subset(rep({(0, 2), (0, 1, 2)}), 3, conflict=2) == [0, 2]            # fact + conflict give it, singles do not
    assert reduce_to_subset(rep({(0, 1), (0, 1, 2)}), 3, conflict=2) is None               # a pair without the conflict thread is no item
    assert reduce_to_subset(rep({(2,), (0, 2), (0, 1, 2)}), 3, conflict=2) is None          # a single thread gives it: no
    assert reduce_to_subset(rep({(0, 2), (1, 2), (0, 1, 2)}), 3, conflict=2, fact=0) == [0, 2]   # both pairs: the one with the record
    assert reduce_to_subset(rep({(0, 1, 2)}), 3, conflict=2) is None


def test_n_for_is_three_unless_forced_or_varied():
    import generate as g
    assert g.n_for(0, 0, False) == 3 and g.n_for(0, 0, False, force=2) == 2 and g.n_for(1, 1, True) == 2 and g.n_for(0, 1, True) == 3


def test_the_quota_decides_between_fixing_and_delivering_on_a_pair():
    import generate as g
    g.QUOTA[3], g.QUOTA[2] = 2, 2; g.TALLY[3], g.TALLY[2] = 0, 0
    assert g.short(3) and g.short(2)
    g.TALLY[3] = 2
    assert not g.short(3) and g.short(2)
    g.QUOTA[3], g.QUOTA[2] = 0, 0
    assert g.short(3) and g.short(2)


def test_an_omissions_points_drop_what_it_leaves_out():
    import generate as g
    pts = g.points_of("Here is the year-end attorney credentials summary for the renewal: each attorney's admission date and CLE hours, Person C's included. It says nothing of his license status or the filings he has signed")
    assert pts == ["Here is the year-end attorney credentials summary for the renewal: each attorney's admission date and CLE hours, Person C's included"]
    assert g.points_of("Person A tells Person B that the money is safe, and that he checks it weekly") == ["the money is safe", "he checks it weekly"]


def test_a_full_set_only_reader_reads_nothing_but_the_full_set():
    seen = []
    class Eng: pass
    def ask(eng, prompt):
        seen.append(eng.name)
        return '{"candidates": []}' if "keeps from" not in prompt else '{"match": false, "reason": "x"}'
    a, b = Eng(), Eng(); a.name, b.name = "a", "b"
    threads = [[{"id": "p1", "from": "x@y", "date": "2001-01-01", "subject": "s", "body": "t"}] for _ in range(3)]
    rep = check(threads, {"secret": "s", "actor": "A", "victim": "B"}, {"a": a, "b": b}, a, ask, full_only=frozenset({"b"}))
    assert seen.count("a") == 7 and seen.count("b") == 1
    assert [c["threads"] for c in rep["calls"] if c["prober"] == "b"] == [[0, 1, 2]]


def test_the_mail_client_form_wraps_and_keeps_each_writers_habit():
    import generate as g
    saved = g.RELEASE_BY_ID
    try:
        g.RELEASE_BY_ID = {"s1": {"own_body": "We met on Friday.  The draft is attached.  Call me."}, "s2": {"own_body": "Got it. Will do. Thanks."}}
        draw = {"firm": [{"addr": "a.one@keystone.com", "email_id": "s1"}, {"addr": "b.two@keystone.com", "email_id": "s2"}], "outside": []}
        long = "No. I told Mr. Varo the U.S. office would wait. " * 4
        quoted = "\n\n    B Two <b.two@keystone.com>\n    03/12/2001 10:00 AM\n         To: A One <a.one@keystone.com>\n\nFirst point. Second point."
        em = {"clues": [{"i": 1, "messages": [{"from": "A One <a.one@keystone.com>", "body": long + quoted}]}]}
        body = g.mailbox_form(em, draw)["clues"][0]["messages"][0]["body"]
        own, rest = body.split("    B Two", 1)
        assert all(len(l) <= 76 for l in own.split("\n"))
        assert "No.  I told Mr. Varo the U.S. office" in own.replace("\n", " ")      # a sentence end doubled; a title and a dotted form not
        assert "First point. Second point." in rest                                   # the quoted writer types one space
    finally:
        g.RELEASE_BY_ID = saved
