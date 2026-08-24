from engine import comprehension, meaning


def test_good_power_packet_passes_comprehension_gate():
    packet = meaning.from_power({
        "actors": ["the Attorney General"],
        "authority_types": ["enforcement", "mandatory_duty"],
        "operative_excerpt": "The Attorney General shall notify the registrant and may enforce the requirements of this section.",
    })
    result = comprehension.evaluate_packet(packet)
    assert result.publish is True
    assert result.score >= 6
    assert result.verdict == "PASS_GENUINELY_UNDERSTANDABLE"


def test_generic_authority_language_fails():
    result = comprehension.evaluate_text(
        "The Attorney General has a federal authority provision involving delegated discretion.",
        "Why it matters: this changes the legal job or authority of the Attorney General.",
    )
    assert result.publish is False
    assert result.verdict in {"FAIL_WHY_IT_MATTERS", "FAIL_DETECTED_NOT_EXPLAINED"}


def test_missing_affected_party_is_identified():
    packet = meaning.from_power({
        "actors": ["the Secretary"],
        "authority_types": ["mandatory_duty"],
        "operative_excerpt": "The Secretary shall carry out this section.",
    })
    result = comprehension.evaluate_packet(packet)
    assert result.publish is False
    assert "TO_WHOM_OR_WHAT" in result.failed


def test_money_transfer_with_recipient_and_purpose_passes():
    packet = meaning.from_money({
        "amounts": [{"raw": "$250,000,000", "amount_usd": "250000000"}],
        "categories": ["appropriation", "grant"],
        "fiscal_direction": "funding_or_authority",
        "operative_excerpt": "There is appropriated $250,000,000 to the Secretary for grants to eligible States for treatment programs.",
    })
    result = comprehension.evaluate_packet(packet)
    assert result.publish is True
    assert "TO_WHOM_OR_WHAT" in result.passed


def test_legalese_fails_teenager_gate():
    result = comprehension.evaluate_text(
        "Subparagraph (A) is amended by striking clause (ii) and inserting the following notwithstanding subsection (c).",
        "Why it matters: it changes the rule.",
    )
    assert result.publish is False
    assert "15_YEAR_OLD_TEST" in result.failed
