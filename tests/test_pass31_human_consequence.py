from engine import barrel_scan, human_consequence, meaning


def _anchor(text: str) -> dict:
    return {
        "anchor_id": "a1", "bill_id": "aca", "segment_id": "s1", "section_label": "SEC. 1",
        "location_marker": "lines 1-10", "document_ref": "aca.txt", "source_url": "https://example.gov",
        "source_sha256": "s", "text_sha256": "t", "exact_text": text, "verified": True,
    }


def test_barrel_scan_uses_canonical_actionable_fiscal_signal_not_largest_raw_number():
    anchor = _anchor(
        "SEC. 1. SPECIAL RULE.\nNational health spending is projected to increase to $4,700,000,000,000. "
        "Notwithstanding section 5, only an eligible facility may receive the waiver."
    )
    money = {
        "status": "extracted", "categories": ["tax"], "operative_excerpt": anchor["exact_text"],
        "amounts": [{
            "raw": "$4,700,000,000,000", "amount_usd": "4700000000000",
            "context_excerpt": "National health spending is projected to increase to $4,700,000,000,000.",
            "context_kind": "context_projection", "local_categories": []
        }]
    }
    candidate = barrel_scan.evaluate_anchor(anchor, ["health", "coverage"], money)
    assert candidate is not None
    assert candidate.factors.fiscal_significance == 0.0
    assert all("4,700,000,000,000" not in reason for reason in candidate.why_flagged)


def test_money_meaning_uses_only_canonical_actionable_amount_clause():
    finding = {
        "status": "extracted", "categories": ["tax", "revenue"], "fiscal_direction": "government_receipt",
        "operative_excerpt": "National health spending is projected to increase to $4,700,000,000,000. A tax of $10,000,000,000 is imposed on covered entities.",
        "amounts": [
            {"raw": "$4,700,000,000,000", "amount_usd": "4700000000000", "context_excerpt": "National health spending is projected to increase to $4,700,000,000,000.", "context_kind": "context_projection", "local_categories": []},
            {"raw": "$10,000,000,000", "amount_usd": "10000000000", "context_excerpt": "A tax of $10,000,000,000 is imposed on covered entities.", "context_kind": "statutory_clause", "local_categories": ["tax"]},
        ]
    }
    packet = meaning.from_money(finding)
    assert packet is not None
    assert packet.amounts == ["$10,000,000,000"]
    assert "$4,700,000,000,000" not in (packet.plain_statement or "")


def test_scrutiny_title_neutralizes_potential_rider_label():
    candidate = {
        "labels": ["Potential Rider", "Scope Surprise"],
        "factors": {"scope_surprise": .8, "beneficiary_concentration": 0, "narrow_carve_out": 0, "cross_reference_opacity": 0},
        "operative_excerpt": "A separate demonstration rule applies.",
    }
    public = human_consequence.scrutiny_public(candidate, None, None, "A separate demonstration rule applies.")
    assert public["title"] == "Unexpected provision worth a closer look"
    assert "Potential Rider" not in public["title"]


def test_page2_uses_compact_forensic_ledger_without_new_dashboard_sections():
    from pathlib import Path
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert "What Congress actually did:" in html
    assert "Recipient / payer:" in html
    assert "Still unknown:" in html
    assert "Who or what is affected:" in html
    assert "claim.public_title or claim.barrel_label" in html
    assert "pass31-external" in html


def test_pass31_refresh_tool_exists_and_reuses_intermediates():
    from pathlib import Path
    tool = Path("tools/refresh_showcases_pass31.py").read_text(encoding="utf-8")
    bat = Path("REFRESH_SHOWCASES_PASS31.bat").read_text(encoding="utf-8")
    assert "No GovInfo refetch" in tool
    assert "barrel_scan.scan_bill" in tool
    assert "synthesis.synthesize_bill" in tool
    assert "publish_verified_showcase" in tool
    assert "PASS 31 SHOWCASE REFRESH" in bat
