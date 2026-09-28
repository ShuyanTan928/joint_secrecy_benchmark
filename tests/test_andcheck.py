"""The AND check: subset enumeration, the keep rule, the answer form and the revision block, without a model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.andcheck import candidates_of, decide, findings_text, reduce_to_subset, revise_block, subsets   # noqa: E402


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


def test_candidates_take_the_testers_form_and_an_empty_list_is_a_no():
    assert candidates_of({"candidates": []}) == [] and candidates_of(None) == [] and candidates_of({"candidates": [{"secret": " "}]}) == []
    assert candidates_of({"candidates": [{"secret": "a child kept from the wife", "evidence_email_ids": ["e1", "e3"]}]}) == \
        [{"secret": "a child kept from the wife", "evidence_email_ids": ["e1", "e3"]}]


def test_revision_block_names_the_change_and_the_history():
    assert revise_block({"change": ""}, []) == ""
    report = {"full_set": {"p": True}, "calls": [{"prober": "p", "threads": [0], "full_set": False, "correct": 1, "candidates": [{"secret": "the child", "evidence_email_ids": ["e1"]}]}]}
    b = revise_block({"why": "clue 1 names the outcome", "change": "use a bare reference", "step": "plot"}, ["move Person A off the record"], report, "clue 1: the record")
    assert "## Revise" in b and "use a bare reference" in b and "move Person A off the record" in b
    assert "clues [1] alone, p: the child (from e1)" in b and "The previous version:\nclue 1: the record" in b and "no smaller set does" in b


def test_findings_text_lists_leaks_by_clue_number_and_the_full_set():
    report = {"calls": [{"prober": "p", "threads": [0], "full_set": False, "correct": 1, "candidates": [{"secret": "the child"}]},
                        {"prober": "p", "threads": [1], "full_set": False, "correct": 0, "candidates": []},
                        {"prober": "p", "threads": [0, 1], "full_set": True, "correct": 0, "candidates": [{"secret": "something else"}], "judge_reason": "a different matter"}]}
    leaks, full = findings_text(report)
    assert leaks == "- clues [1] alone, p: the child" and full == "- p: something else (the judge: a different matter)"


def test_step_two_flags_catch_the_run_39_faults():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import generate as g
    lab = ("fact", "knows", "concealment")
    s = {"actor": "the procurement manager, who is trusted as an impartial judge of bids"}
    out = {lab[0]: "Ashford's pipeline maintenance procurement manager holds a silent 15 percent share in Gulf Coast.",
           lab[1]: "The manager writes to the tax preparer asking that a large capital loss be carried forward.", lab[2]: "The manager tells compliance there is no interest."}
    flags = g.part_flags(s, out, lab)
    assert any("names the actor by role" in f for f in flags) and any("measure" in f for f in flags)
    out2 = {lab[0]: "The mother has a lump; she has told her husband that her checkups came back clear.", lab[1]: "The daughter asks the imaging desk which Saturday slots are open.", lab[2]: "x"}
    assert any("telling or assuring" in f for f in g.part_flags({"actor": "the daughter"}, out2, lab))
    clean = {lab[0]: "A silent 15 percent share in Gulf Coast Pipeline Services is held by the member named on its K-1 schedule.",
             lab[1]: "The manager mails the family's accountant the year-end partner distribution statement from Gulf Coast.", lab[2]: "x"}
    assert g.part_flags(s, clean, lab) == []


def test_step_two_flags_catch_the_household_and_the_shared_company_name():
    import generate as g
    lab = ("fact", "knows", "concealment")
    s = {"actor": "a husband who handles the money", "ground": "life"}
    out = {lab[0]: "Joint retirement account no. 4471, held in the names of both spouses, was moved into internet stocks.", lab[1]: "The husband asks that statements for account no. 4471 go to his office email.", lab[2]: "x"}
    assert any("household" in f for f in g.part_flags(s, out, lab))
    s2 = {"actor": "a procurement manager at Ashford", "ground": "work"}
    out2 = {lab[0]: "The register of Keller Pipeline Services records a 15 percent interest held through the Delaney Family Trust, account ending 4471.",
            lab[1]: "The manager asks the accountant to include the Keller Pipeline Services K-1 issued to the Delaney Family Trust.", lab[2]: "x"}
    assert any("Keller Pipeline Services" in f for f in g.part_flags(s2, out2, lab))
    out3 = dict(out2, **{lab[1]: "The manager asks the accountant to include the K-1 issued to the Delaney Family Trust, account ending 4471."})
    assert g.part_flags(s2, out3, lab) == []


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
    assert g.n_for(0, 0, False) == 3 and g.n_for(0, 0, False, force=2) == 2 and g.n_for(1, 1, True) == 4


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
