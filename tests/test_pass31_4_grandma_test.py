from engine import citizen_view
from pathlib import Path


def _claim(**overrides):
    base = {
        "text": "The Secretary must establish a demonstration project under title XIX of the Social Security Act",
        "citations": [{"anchor_id": "a1"}],
    }
    base.update(overrides)
    return base


def test_grandma_core_prefers_specific_actor_and_action_over_audit_prose():
    analysis = {"panels": [
        {"key": "what_it_really_does", "claims": [_claim(authority_actor="The Secretary of Health and Human Services", semantic_action="must establish a demonstration project", authority_type="mandatory duty", affected_party="hospitals")]},
        {"key": "follow_the_money", "claims": []}, {"key": "barrel_scan", "claims": []},
        {"key": "who_wins_pays_power", "claims": []}, {"key": "left_right_text", "claims": []},
    ]}
    card = citizen_view.build(analysis)["core"][0]
    assert card["citizen_headline"] == "The Secretary of Health and Human Services must establish a demonstration project."
    assert "Who or what is affected:" not in card["citizen_care"]
    assert "Affects hospitals." in card["citizen_care"]


def test_grandma_money_rejects_malformed_section_heading_as_purpose_or_recipient():
    analysis = {"panels": [
        {"key": "what_it_really_does", "claims": []},
        {"key": "follow_the_money", "claims": [_claim(
            fiscal_amount="$19,147,000,000", fiscal_mechanism="funding or spending authority",
            fiscal_purpose='the section titled “2003(a)(1) of this Act and that subparagraph and the”',
            affected_party='the program or activity addressed by “2003(a)(1) of this Act and that subparagraph and the”',
            missing_context="The final recipient or payer is not identifiable from this provision alone.",
        )]},
        {"key": "barrel_scan", "claims": []}, {"key": "who_wins_pays_power", "claims": []}, {"key": "left_right_text", "claims": []},
    ]}
    card = citizen_view.build(analysis)["money"][0]
    assert card["citizen_purpose"] == "Not clear from this clause alone."
    assert card["citizen_recipient"] == "Not clear from this clause alone."
    assert "2003(a)(1)" not in card["citizen_summary"]


def test_grandma_power_turns_authority_type_into_one_plain_so_what_sentence():
    analysis = {"panels": [
        {"key": "what_it_really_does", "claims": []}, {"key": "follow_the_money", "claims": []}, {"key": "barrel_scan", "claims": []},
        {"key": "who_wins_pays_power", "claims": [_claim(
            authority_actor="The Secretary", semantic_action="must not set a minimum performance standard", authority_type="prohibition or limit",
            authority_target="hospital performance scores",
            why_it_matters="Who or what is affected: hospital performance scores. Type of power or duty: prohibition or limit. Practical consequence: repeated machine prose.",
        )]},
        {"key": "left_right_text", "claims": []},
    ]}
    card = citizen_view.build(analysis)["power"][0]
    assert card["citizen_consequence"].startswith("This places a legal limit")
    assert "Who or what is affected:" not in card["citizen_consequence"]
    assert "It affects hospital performance scores." in card["citizen_consequence"]


def test_pass31_4_surface_keeps_same_boxes_and_uses_grandma_language():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert "If you read nothing else, start with these 3 verified changes." in html
    assert "Why it caught our attention:" in html
    assert "What we still need to know:" in html
    assert "THE MONEY" in html and "THE POWER" in html and "THE QUESTIONS" in html and "THE RECEIPTS" in html
    assert "citizen_summary" in html
