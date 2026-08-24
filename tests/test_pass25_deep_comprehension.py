from engine import meaning, so_what


def test_meaning_packet_power_extracts_actor_action_and_target():
    packet = meaning.from_power({
        "actors": ["the Attorney General"],
        "authority_types": ["enforcement", "mandatory_duty"],
        "operative_excerpt": "The Attorney General shall notify the registrant and may enforce the requirements of this section.",
    })
    assert packet is not None
    assert packet.actor == "the Attorney General"
    assert packet.action.startswith("must notify the registrant")
    assert packet.target == "registrant"
    assert packet.completeness_score >= .7
    assert packet.plain_statement.startswith("The Attorney General must notify")
    assert "legal duty" in packet.why_it_matters


def test_meaning_packet_money_answers_amount_recipient_and_transfer_form():
    packet = meaning.from_money({
        "amounts": [{"raw": "$250,000,000", "amount_usd": "250000000"}],
        "categories": ["appropriation", "grant"],
        "fiscal_direction": "funding_or_authority",
        "operative_excerpt": "There is appropriated $250,000,000 to the Secretary for grants to eligible States.",
    })
    assert packet is not None
    assert packet.amounts == ["$250,000,000"]
    assert packet.recipient == "eligible States"
    assert packet.plain_statement == "Congress provides $250,000,000 as grants to eligible States."
    assert "who receives it" in packet.why_it_matters


def test_meaning_packet_refuses_to_invent_missing_money_context():
    packet = meaning.from_money({
        "amounts": [{"raw": "$12,000,000", "amount_usd": "12000000"}],
        "categories": ["unclassified_money_amount"],
        "fiscal_direction": "unspecified",
        "status": "needs_fiscal_context",
        "operative_excerpt": "The amount shall be $12,000,000.",
    })
    assert packet is not None
    assert packet.recipient is None
    assert any("recipient" in item.lower() for item in packet.missing_context)
    assert any("fiscal context" in item.lower() for item in packet.missing_context)


def test_best_meaning_prefers_more_complete_packet():
    money = {
        "amounts": [{"raw": "$250,000,000"}],
        "categories": ["appropriation", "grant"],
        "fiscal_direction": "funding_or_authority",
        "operative_excerpt": "There is appropriated $250,000,000 to the Secretary for grants to eligible States.",
    }
    power = {
        "actors": ["the Secretary"],
        "authority_types": ["mandatory_duty"],
        "operative_excerpt": "The Secretary shall carry out this section.",
    }
    packet = meaning.best(money, power)
    assert packet.source_kind == "money"
    assert packet.completeness_score > meaning.from_power(power).completeness_score


def test_public_main_effect_requires_minimum_comprehension():
    text, why, kind = so_what.main_effect_from_findings(None, {
        "actors": [],
        "authority_types": ["delegated_discretion"],
        "operative_excerpt": "May take appropriate action.",
    })
    assert (text, why, kind) == (None, None, None)
