import json
from pathlib import Path

from engine import human_consequence, meaning, semantic_roles, so_what


def _write_anchor(tmp_path: Path, *, bill_id="aca", anchor_id="a1", identifier="100", heading="SEC. 100. TEMPORARY REINSURANCE PROGRAM"):
    d = tmp_path / "citation_anchors"
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "anchors": [
            {"anchor_id": anchor_id, "kind": "section", "identifier": identifier, "heading": heading, "excerpt": heading},
            {"anchor_id": "a2", "kind": "section", "identifier": "200", "heading": "SEC. 200. QUALITY IMPROVEMENT GRANTS", "excerpt": "grants"},
        ]
    }
    (d / f"{bill_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return d


def test_time_period_can_never_be_recipient_or_affected_party(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_roles, "ANCHOR_DIR", _write_anchor(tmp_path))
    finding = {
        "bill_id": "aca", "anchor_id": "a1", "categories": ["appropriation"],
        "fiscal_direction": "funding_or_authority", "timing": ["fiscal year 2014"],
        "operative_excerpt": "(17) for fiscal year 2014, $19,147,000,000;",
        "amounts": [{"raw": "$19,147,000,000", "amount_usd": "19147000000", "context_excerpt": "(17) for fiscal year 2014, $19,147,000,000;", "context_kind": "statutory_clause", "local_categories": ["appropriation"]}],
    }
    packet = meaning.from_money(finding)
    roles = semantic_roles.resolve_money(finding, packet)
    assert roles.recipient is None
    assert roles.target != "fiscal year 2014"
    assert roles.period == "fiscal year 2014"
    fields = human_consequence.money_fields(finding)
    assert fields["fiscal_recipient"] is None
    assert fields["affected_party"] != "fiscal year 2014"
    assert fields["fiscal_period"] == "fiscal year 2014"


def test_carry_out_this_section_is_not_a_recipient(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_roles, "ANCHOR_DIR", _write_anchor(tmp_path))
    finding = {
        "bill_id": "aca", "anchor_id": "a1", "categories": ["appropriation"],
        "fiscal_direction": "funding_or_authority", "timing": [],
        "operative_excerpt": "Congress provides $6,000,000,000 to carry out this section.",
        "amounts": [{"raw": "$6,000,000,000", "amount_usd": "6000000000", "context_excerpt": "Congress provides $6,000,000,000 to carry out this section.", "context_kind": "statutory_clause", "local_categories": ["appropriation"]}],
    }
    fields = human_consequence.money_fields(finding)
    assert fields["fiscal_recipient"] is None
    assert "carry out this section" not in (fields["affected_party"] or "").lower()
    assert "TEMPORARY REINSURANCE PROGRAM" in (fields["fiscal_purpose"] or "")


def test_section_heading_can_supply_labeled_purpose_context_not_fake_recipient(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_roles, "ANCHOR_DIR", _write_anchor(tmp_path))
    finding = {
        "bill_id": "aca", "anchor_id": "a1", "categories": ["funding"],
        "fiscal_direction": "funding_or_authority", "timing": [],
        "operative_excerpt": "$5,000,000,000 is provided for fiscal year 2014.",
        "amounts": [{"raw": "$5,000,000,000", "amount_usd": "5000000000", "context_excerpt": "$5,000,000,000 is provided for fiscal year 2014.", "context_kind": "statutory_clause", "local_categories": ["funding"]}],
    }
    roles = semantic_roles.resolve_money(finding, meaning.from_money(finding))
    assert roles.purpose == "the section titled “TEMPORARY REINSURANCE PROGRAM”"
    assert roles.recipient is None
    assert any("section heading supplies purpose context" in u.lower() for u in roles.unknowns)


def test_internal_same_bill_cross_reference_resolves_heading(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_roles, "ANCHOR_DIR", _write_anchor(tmp_path))
    finding = {
        "bill_id": "aca", "anchor_id": "a1", "categories": ["funding"],
        "fiscal_direction": "funding_or_authority", "timing": [],
        "operative_excerpt": "There is appropriated $10,000,000 to carry out section 200.",
        "amounts": [{"raw": "$10,000,000", "amount_usd": "10000000", "context_excerpt": "There is appropriated $10,000,000 to carry out section 200.", "context_kind": "statutory_clause", "local_categories": ["appropriation"]}],
    }
    roles = semantic_roles.resolve_money(finding, meaning.from_money(finding))
    assert roles.cross_reference_context == "section 200: QUALITY IMPROVEMENT GRANTS"
    assert "QUALITY IMPROVEMENT GRANTS" in (roles.purpose or "")


def test_external_act_cross_reference_stays_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_roles, "ANCHOR_DIR", _write_anchor(tmp_path))
    finding = {
        "bill_id": "aca", "anchor_id": "a1", "categories": ["funding"],
        "fiscal_direction": "funding_or_authority", "timing": [],
        "operative_excerpt": "Section 2105 of the Social Security Act is amended. $10,000,000 is provided.",
        "amounts": [{"raw": "$10,000,000", "amount_usd": "10000000", "context_excerpt": "Section 2105 of the Social Security Act is amended. $10,000,000 is provided.", "context_kind": "statutory_clause", "local_categories": ["funding"]}],
    }
    roles = semantic_roles.resolve_money(finding, meaning.from_money(finding))
    assert roles.cross_reference_context is None
    assert roles.unresolved_cross_reference == "section 2105"
    assert any("not resolved" in u.lower() for u in roles.unknowns)


def test_money_public_explanation_separates_amount_purpose_period_and_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_roles, "ANCHOR_DIR", _write_anchor(tmp_path))
    finding = {
        "bill_id": "aca", "anchor_id": "a1", "status": "extracted", "categories": ["appropriation"],
        "fiscal_direction": "funding_or_authority", "timing": ["fiscal year 2014"],
        "operative_excerpt": "For fiscal year 2014, $19,147,000,000 is appropriated.",
        "amounts": [{"raw": "$19,147,000,000", "amount_usd": "19147000000", "context_excerpt": "For fiscal year 2014, $19,147,000,000 is appropriated.", "context_kind": "statutory_clause", "local_categories": ["appropriation"]}],
        "confidence": .98,
    }
    text, why = so_what.money_explanation(finding)
    assert "$19,147,000,000" in (text or "")
    assert "TEMPORARY REINSURANCE PROGRAM" in (text or "")
    assert "fiscal year 2014" in (why or "")
    assert "recipient" in (why or "").lower()


def test_page2_displays_semantic_roles_without_new_dashboard_boxes():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert "Who acts:" in html
    assert "For what purpose:" in html
    assert "What we still don't know:" in html
    assert 'class="pass31-role-stack"' in html
