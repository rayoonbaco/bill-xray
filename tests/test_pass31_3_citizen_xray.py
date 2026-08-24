from engine import citizen_view
from pathlib import Path


def _claim(text, unknown=None, anchor="a1"):
    return {"text": text, "semantic_unknown": unknown, "citations": [{"anchor_id": anchor}]}


def test_citizen_view_reorders_existing_verified_panels_without_new_inference():
    analysis = {"analysis_status": "verified", "panels": [
        {"key": "what_it_really_does", "claims": [_claim("core")]},
        {"key": "follow_the_money", "claims": [_claim("money", "recipient not identified", "m1")]},
        {"key": "barrel_scan", "claims": [_claim("scrutiny", "cross-reference unresolved", "s1")]},
        {"key": "who_wins_pays_power", "claims": [_claim("power", None, "p1")]},
        {"key": "left_right_text", "claims": [_claim("left"), _claim("right"), _claim("text")]},
    ]}
    view = citizen_view.build(analysis)
    assert view["core"][0]["text"] == "core"
    assert view["money"][0]["text"] == "money"
    assert view["power"][0]["text"] == "power"
    assert view["scrutiny"][0]["text"] == "scrutiny"
    assert [q["text"] for q in view["questions"]] == ["recipient not identified", "cross-reference unresolved"]


def test_citizen_questions_are_deduplicated_and_capped():
    dup = "Final recipient is not identified."
    analysis = {"panels": [
        {"key": "what_it_really_does", "claims": []},
        {"key": "follow_the_money", "claims": [_claim("m1", dup, "1"), _claim("m2", dup, "2"), _claim("m3", "q2", "3")]},
        {"key": "barrel_scan", "claims": [_claim("s1", "q3", "4"), _claim("s2", "q4", "5")]},
        {"key": "who_wins_pays_power", "claims": []},
        {"key": "left_right_text", "claims": []},
    ]}
    view = citizen_view.build(analysis)
    assert len(view["questions"]) == 3
    assert [q["text"] for q in view["questions"]] == [dup, "q2", "q3"]


def test_page2_is_citizen_first_and_keeps_receipts_and_restraint():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    for phrase in [
        "If you read nothing else, here is what this bill actually does.",
        "THE MONEY", "THE POWER", "WHAT DESERVES A CLOSER LOOK", "THE QUESTIONS", "THE RECEIPTS",
        "Scrutiny is not accusation.", "Show the receipt", "Missing context is shown as a limitation",
    ]:
        assert phrase in html
    assert "consequence-evidence coverage" not in html
    assert "Left | Right | Text" in html
    assert "Outside the bill · official context" in html


def test_pass31_3_is_presentation_only():
    source = Path("engine/citizen_view.py").read_text(encoding="utf-8")
    assert "No new inference" in source
    assert "fiscal_materiality" not in source
    assert "semantic_roles" not in source
    assert Path("PASS_31_3_CITIZENS_XRAY.md").exists()
