import hashlib
import json
from dataclasses import asdict

import pytest

from engine.power import extract_anchor_payload
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


def test_rulemaking_authority_identifies_actor_and_modality():
    result = extract_anchor_payload(
        _anchor("SEC. 101. RULES.\nThe Secretary shall prescribe regulations to carry out this section.")
    )
    assert result is not None
    assert result.status == "extracted"
    assert result.claim_class == "TEXT"
    assert "rulemaking" in result.authority_types
    assert "mandatory_duty" in result.authority_types
    assert result.actors == ["The Secretary"]
    assert "must" in result.modality
    assert result.authority_direction == "assigns_rulemaking_authority"


def test_discretion_is_not_rewritten_as_mandatory_power():
    result = extract_anchor_payload(
        _anchor("SEC. 102. WAIVER.\nThe Secretary may waive the requirement for good cause.")
    )
    assert result is not None
    assert "waiver_or_exemption" in result.authority_types
    assert "delegated_discretion" in result.authority_types
    assert "may" in result.modality
    assert "must" not in result.modality
    assert result.authority_direction == "creates_or_changes_exception_power"


def test_prohibition_records_limit_without_policy_judgment():
    result = extract_anchor_payload(
        _anchor("SEC. 103. LIMITATION.\nThe Secretary may not disclose the information except as provided by law.")
    )
    assert result is not None
    assert "prohibition_or_limit" in result.authority_types
    assert "may_not" in result.modality
    assert result.claim_class == "TEXT"
    assert "unconstitutional" not in result.operative_excerpt.lower()


def test_creation_of_office_is_structural_authority_change():
    result = extract_anchor_payload(
        _anchor("SEC. 104. OFFICE.\nThere is established in the Department of Health and Human Services an Office of Test Programs.")
    )
    assert result is not None
    assert "appointment_or_structure" in result.authority_types
    assert result.authority_direction == "creates_or_structures_authority"


def test_private_may_language_without_government_actor_routes_to_review():
    result = extract_anchor_payload(
        _anchor("SEC. 105. PRIVATE ACTION.\nA covered person may submit a request for reconsideration.")
    )
    assert result is not None
    assert result.status == "needs_legal_context"
    assert result.review_reason
    assert result.actors == []


def test_non_authority_section_returns_no_finding():
    result = extract_anchor_payload(
        _anchor("SEC. 106. FINDING.\nCongress finds that access to information is important.")
    )
    assert result is None


def test_unverified_anchor_is_rejected():
    payload = _anchor("SEC. 107. RULE.\nThe Secretary shall issue regulations.")
    payload["verified"] = False
    with pytest.raises(ValueError, match="verified Pass 4 anchor"):
        extract_anchor_payload(payload)


def test_cross_reference_routes_candidate_to_legal_context():
    result = extract_anchor_payload(
        _anchor("SEC. 108. AUTHORITY.\nThe Secretary may exercise the authority under section 205 of this Act.")
    )
    assert result is not None
    assert result.status == "needs_legal_context"
    assert "Cross-reference" in (result.review_reason or "")


def test_extract_bill_writes_only_section_level_authority_findings(tmp_path, monkeypatch):
    import engine.citations as citations
    import engine.power as power

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    power_dir = tmp_path / "power"
    for directory in (ingested_dir, segment_dir, anchor_dir, power_dir):
        directory.mkdir()

    text = """DIVISION A - TEST\nTITLE I - GENERAL\nSEC. 101. RULES.\nThe Secretary shall prescribe regulations.\nSEC. 102. REPORT.\nThe Secretary shall submit a report to Congress.\nSEC. 103. FINDING.\nCongress finds that this test exists.\n"""
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

    monkeypatch.setattr(power, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(power, "POWER_DIR", power_dir)
    result = power.extract_bill("demo")
    assert result.finding_count == 2
    assert all(item.anchor_id.startswith("bxr-demo-") for item in result.findings)
    assert all(item.claim_class == "TEXT" for item in result.findings)
    assert (power_dir / "demo.json").exists()
