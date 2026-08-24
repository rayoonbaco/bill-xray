from engine import so_what


def test_power_explanation_finishes_the_thought():
    finding = {
        "actors": ["the Attorney General"],
        "authority_types": ["enforcement", "mandatory_duty"],
        "operative_excerpt": "The Attorney General shall notify the registrant and may enforce the requirements of this section.",
    }
    text, why = so_what.power_explanation(finding)
    assert "Attorney General" in text
    assert "must notify" in text
    assert "investigate, enforce, penalize" in why
    assert "gets or faces a change" not in text


def test_money_explanation_keeps_concrete_amount_and_action():
    finding = {
        "amounts": [{"raw": "$250,000,000", "amount_usd": "250000000"}],
        "categories": ["appropriation", "grant"],
        "fiscal_direction": "funding_or_authority",
        "operative_excerpt": "There is appropriated $250,000,000 to the Secretary for grants to eligible States.",
    }
    text, why = so_what.money_explanation(finding)
    assert "$250,000,000" in text
    assert "eligible States" in text
    assert "who receives it" in why


def test_scrutiny_explanation_leads_with_actual_provision_not_detector_jargon():
    candidate = {
        "labels": ["Narrow Carve-Out"],
        "operative_excerpt": "Except for a hospital located in County X, the limitation applies to every eligible facility.",
        "why_flagged": ["Text contains exception or exemption language that may narrow who is covered."],
        "factors": {"beneficiary_concentration": .78, "fiscal_significance": 0, "scope_surprise": 0, "cross_reference_opacity": 0, "narrow_carve_out": .5},
    }
    text, label, why = so_what.scrutiny_explanation(candidate)
    assert label == "Narrow Carve-Out"
    assert "hospital located in County X" in text
    assert "What stands out:" in why


def test_main_effect_prefers_concrete_power_over_title_translation():
    text, why, kind = so_what.main_effect_from_findings(None, {
        "actors": ["the Secretary"],
        "authority_types": ["rulemaking"],
        "operative_excerpt": "The Secretary shall issue regulations establishing the eligibility standard.",
    })
    assert kind == "power"
    assert "must issue regulations" in text
    assert "shape the rules" in why
