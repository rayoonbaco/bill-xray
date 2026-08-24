import hashlib
import json
from dataclasses import asdict

import pytest

from engine.money import extract_anchor_payload
from engine.segment import segment_text


def _anchor(exact_text: str, *, anchor_id: str = "bxr-demo") -> dict:
    return {
        "anchor_id": anchor_id,
        "bill_id": "demo",
        "segment_id": "demo:section:101:1",
        "kind": "section",
        "section_label": "SEC. 101",
        "location_marker": "canonical lines 1-2",
        "document_ref": "local:demo.txt",
        "source_url": "https://example.test/demo",
        "source_sha256": "a" * 64,
        "text_sha256": hashlib.sha256(exact_text.encode("utf-8")).hexdigest(),
        "exact_text": exact_text,
        "verified": True,
    }


def test_appropriation_extracts_exact_dollar_amount_and_timing():
    result = extract_anchor_payload(
        _anchor(
            "SEC. 101. APPROPRIATION.\nThere is appropriated $10,000,000 for fiscal year 2027, to remain available until expended."
        )
    )
    assert result is not None
    assert result.status == "extracted"
    assert result.claim_class == "TEXT"
    assert "appropriation" in result.categories
    assert result.amounts[0].raw == "$10,000,000"
    assert result.amounts[0].amount_usd == "10000000"
    assert result.fiscal_direction == "funding_or_authority"
    assert any("fiscal year 2027" in item.lower() for item in result.timing)
    assert any("until expended" in item.lower() for item in result.timing)


def test_rescission_is_not_mislabeled_as_spending():
    result = extract_anchor_payload(
        _anchor("SEC. 102. RESCISSION.\nOf the unobligated balances, $2 million is rescinded.")
    )
    assert result is not None
    assert "rescission" in result.categories
    assert result.amounts[0].amount_usd == "2000000"
    assert result.fiscal_direction == "funding_reduction"


def test_tax_credit_without_dollar_amount_stays_context_review():
    result = extract_anchor_payload(
        _anchor("SEC. 103. CREDIT.\nThe tax credit shall equal 30 percent of qualified expenditures.")
    )
    assert result is not None
    assert "tax" in result.categories
    assert "credit" in result.categories
    assert result.amounts == []
    assert result.percentages == ["30 percent"]
    assert result.status == "needs_fiscal_context"
    assert result.review_reason


def test_non_money_section_returns_no_finding():
    result = extract_anchor_payload(
        _anchor("SEC. 104. REPORT.\nThe Secretary shall submit a report to Congress.")
    )
    assert result is None


def test_unverified_anchor_is_rejected():
    payload = _anchor("SEC. 105. GRANT.\nThe Secretary may award grants of $500,000.")
    payload["verified"] = False
    with pytest.raises(ValueError, match="verified Pass 4 anchor"):
        extract_anchor_payload(payload)


def test_extract_bill_uses_verified_section_anchors_and_writes_artifact(tmp_path, monkeypatch):
    import engine.citations as citations
    import engine.money as money

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    money_dir = tmp_path / "money"
    for directory in (ingested_dir, segment_dir, anchor_dir, money_dir):
        directory.mkdir()

    text = """DIVISION A - TEST\nTITLE I - GENERAL\nSEC. 101. APPROPRIATION.\nThere is appropriated $10,000,000 for fiscal year 2027.\nSEC. 102. REPORT.\nThe Secretary shall submit a report.\nSEC. 103. RESCISSION.\nOf unobligated balances, $2,000,000 is rescinded.\n"""
    source_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ingested = {
        "bill_id": "demo", "source_filename": "demo.txt", "source_format": "txt",
        "source_url": "https://example.test/demo", "document_ref": "local:demo.txt",
        "sha256": source_sha, "text": text,
    }
    (ingested_dir / "demo.json").write_text(json.dumps(ingested), encoding="utf-8")
    segmented = segment_text("demo", text, source_document_ref="local:demo.txt", source_sha256=source_sha)
    (segment_dir / "demo.json").write_text(json.dumps(asdict(segmented)), encoding="utf-8")

    monkeypatch.setattr(citations, "INGESTED_DIR", ingested_dir)
    monkeypatch.setattr(citations, "SEGMENT_DIR", segment_dir)
    monkeypatch.setattr(citations, "ANCHOR_DIR", anchor_dir)
    citations.build_anchor_index("demo")

    monkeypatch.setattr(money, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(money, "MONEY_DIR", money_dir)
    result = money.extract_bill("demo")
    assert result.finding_count == 2
    assert result.quantified_count == 2
    assert {item.fiscal_direction for item in result.findings} == {"funding_or_authority", "funding_reduction"}
    assert all(item.anchor_id.startswith("bxr-demo-") for item in result.findings)
    assert (money_dir / "demo.json").exists()
