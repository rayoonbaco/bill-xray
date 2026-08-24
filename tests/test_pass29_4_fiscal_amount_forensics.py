from engine import fiscal_materiality


def test_aca_4700b_projection_is_not_actionable_revenue_tax():
    finding = {
        "status": "extracted",
        "categories": ["tax", "revenue"],
        "operative_excerpt": (
            "Health insurance and health care services are a significant part of the national economy. "
            "National health spending is projected to increase from $2,500,000,000,000, or 17.6 percent "
            "of the economy, in 2009 to $4,700,000,000,000 in 2019. Private health insurance spending is "
            "projected to be $854,000,000,000 in 2009. Elsewhere this section discusses a tax requirement."
        ),
        "amounts": [
            {"raw": "$2,500,000,000,000", "amount_usd": "2500000000000"},
            {"raw": "$4,700,000,000,000", "amount_usd": "4700000000000"},
            {"raw": "$854,000,000,000", "amount_usd": "854000000000"},
        ],
    }
    result = fiscal_materiality.assess(finding)
    assert result.actionable is False
    assert result.score == 0.0


def test_amount_level_context_prevents_projection_from_outranking_real_tax_in_same_anchor():
    finding = {
        "status": "extracted",
        "categories": ["tax", "revenue"],
        "operative_excerpt": (
            "National health spending is projected to increase to $4,700,000,000,000 in 2019. "
            "A tax of $10,000,000,000 is imposed on covered entities."
        ),
        "amounts": [
            {"raw": "$4,700,000,000,000", "amount_usd": "4700000000000"},
            {"raw": "$10,000,000,000", "amount_usd": "10000000000"},
        ],
    }
    result = fiscal_materiality.assess(finding)
    assert result.actionable is True
    assert result.amount == 10_000_000_000
    assert result.bucket == "revenue_tax"


def test_genuine_large_tax_remains_actionable():
    finding = {
        "status": "extracted",
        "categories": ["tax"],
        "operative_excerpt": "A tax of $50,000,000,000 is imposed on covered entities.",
        "amounts": [{"raw": "$50,000,000,000", "amount_usd": "50000000000"}],
    }
    result = fiscal_materiality.assess(finding)
    assert result.actionable is True
    assert result.amount == 50_000_000_000
    assert result.directness >= 0.9
