from engine import meaning


def test_meaning_clip_never_splits_money_token():
    text = (
        "any taxable year if the average annual gross receipts of such entity for the "
        "3- taxable-year period ending with the taxable year which precedes such taxable "
        "year does not exceed $25,000,000"
    )
    clipped = meaning._clip(text, 180)
    assert clipped.endswith("…")
    assert "$2…" not in clipped
    assert "$" not in clipped  # incomplete amount is omitted, never falsified


def test_tcja_shaped_money_packet_does_not_create_partial_dollar_claim():
    finding = {
        "bill_id": "tcja",
        "anchor_id": "synthetic-tcja-13102",
        "status": "extracted",
        "categories": ["tax", "revenue"],
        "fiscal_direction": "tax_or_revenue_rule",
        "operative_excerpt": (
            "A corporation or partnership meets the gross receipts test of this subsection "
            "for any taxable year if the average annual gross receipts of such entity for the "
            "3- taxable-year period ending with the taxable year which precedes such taxable "
            "year does not exceed $25,000,000."
        ),
        "amounts": [{
            "raw": "$25,000,000",
            "amount_usd": "25000000",
            "context_excerpt": (
                "A corporation or partnership meets the gross receipts test of this subsection "
                "for any taxable year if the average annual gross receipts of such entity for the "
                "3- taxable-year period ending with the taxable year which precedes such taxable "
                "year does not exceed $25,000,000."
            ),
            "context_kind": "statutory_clause",
            "local_categories": ["tax", "revenue"],
        }],
    }
    packet = meaning.from_money(finding)
    assert packet is not None
    assert "$2…" not in (packet.purpose or "")
