from engine import fiscal_materiality, money


def test_money_extractor_carries_per_amount_provenance():
    text = (
        "SEC. 10106. FINDINGS.\n"
        "National health spending is projected to increase from $2,500,000,000,000 in 2009 "
        "to $4,700,000,000,000 in 2019. "
        "A tax of $10,000,000,000 is imposed on covered entities."
    )
    amounts = money._amounts(text)
    by_amount = {int(x.amount_usd): x for x in amounts}
    assert by_amount[4_700_000_000_000].context_kind == "context_projection"
    assert "projected" in by_amount[4_700_000_000_000].context_excerpt.lower()
    assert by_amount[10_000_000_000].context_kind == "statutory_clause"
    assert "tax" in by_amount[10_000_000_000].local_categories


def test_downstream_materiality_uses_canonical_amount_context_not_truncated_anchor():
    finding = {
        "status": "extracted",
        "categories": ["tax", "revenue"],
        # Deliberately unrelated/truncated anchor excerpt containing tax language.
        "operative_excerpt": "A tax and revenue requirement applies elsewhere in this section.",
        "amounts": [
            {
                "raw": "$4,700,000,000,000",
                "amount_usd": "4700000000000",
                "context_excerpt": "National health spending is projected to increase to $4,700,000,000,000 in 2019.",
                "context_kind": "context_projection",
                "local_categories": [],
            },
            {
                "raw": "$10,000,000,000",
                "amount_usd": "10000000000",
                "context_excerpt": "A tax of $10,000,000,000 is imposed on covered entities.",
                "context_kind": "statutory_clause",
                "local_categories": ["tax"],
            },
        ],
    }
    all_results = fiscal_materiality.assess_all(finding)
    projection = next(x for x in all_results if x.amount == 4_700_000_000_000)
    tax = next(x for x in all_results if x.amount == 10_000_000_000)
    assert projection.actionable is False
    assert projection.provenance == "amount_provenance"
    assert projection.context_kind == "context_projection"
    assert tax.actionable is True
    assert tax.bucket == "revenue_tax"
    best = fiscal_materiality.assess(finding)
    assert best.amount == 10_000_000_000


def test_amount_missing_from_excerpt_fails_closed_instead_of_inheriting_anchor_tax_language():
    finding = {
        "status": "extracted",
        "categories": ["tax"],
        "operative_excerpt": "A tax is imposed elsewhere in this section.",
        "amounts": [{"raw": "$4,700,000,000,000", "amount_usd": "4700000000000"}],
    }
    result = fiscal_materiality.assess(finding)
    assert result.actionable is False
    assert result.provenance == "amount_context_missing"
