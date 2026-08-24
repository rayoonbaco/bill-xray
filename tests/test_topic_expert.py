import hashlib
import json
from dataclasses import asdict

import pytest

from engine.topic_expert import build_review, route_domains, review_bill
from engine.segment import segment_text


def _anchor(text: str, anchor_id: str = "bxr-demo") -> dict:
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
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "exact_text": text,
        "verified": True,
    }


def test_health_section_routes_to_health_expert():
    scores, domains, confidence, needs_human = route_domains(
        "SEC. 101. HEALTH COVERAGE. The Secretary shall establish health insurance coverage standards for hospitals and patients."
    )
    assert domains[0] == "health"
    assert confidence >= 0.8
    assert needs_human is False
    assert scores[0].matched_terms


def test_cross_domain_section_can_route_to_multiple_experts():
    _scores, domains, confidence, _needs_human = route_domains(
        "SEC. 102. HEALTH TAX CREDIT. A refundable tax credit is allowed for health insurance coverage and hospital plan premiums."
    )
    assert "health" in domains
    assert "tax" in domains
    assert len(domains) >= 2
    assert confidence >= 0.84


def test_bill_label_is_not_forced_onto_each_section():
    _scores, domains, _confidence, _needs_human = route_domains(
        "SEC. 103. SEMICONDUCTOR CYBERSECURITY. The agency shall establish cybersecurity standards for semiconductor facilities and digital systems."
    )
    assert domains[0] == "technology"
    assert "health" not in domains


def test_unclear_section_is_sent_to_human_topic_assignment():
    review = build_review(_anchor("SEC. 104. SPECIAL RULE. The requirement described above shall apply."))
    assert review.primary_domain == "general_legislative"
    assert review.status == "needs_human_topic_assignment"
    assert review.claim_class == "UNKNOWN"
    assert review.routing_confidence < 0.8


def test_prior_evidence_layers_are_joined_without_becoming_claims():
    review = build_review(
        _anchor("SEC. 105. HEALTH GRANT AUTHORITY. The Secretary may award health grants."),
        money_finding={"money_types": ["grant"], "amounts": [], "status": "needs_fiscal_context"},
        power_finding={"authority_types": ["delegated_discretion"], "actors": ["the Secretary"], "authority_direction": "assigns_discretion", "status": "extracted"},
        barrel_candidate={"labels": ["Scope Surprise"], "why_flagged": ["topic distance"], "status": "review_candidate"},
    )
    assert set(review.evidence_layers_present) == {"citation_anchor", "money", "power", "barrel_scan"}
    assert review.claim_class == "UNKNOWN"
    assert any("fiscal context" in item.lower() for item in review.context_needed)
    assert any("wrongdoing" in item.lower() for item in review.context_needed)


def test_unverified_anchor_is_rejected():
    payload = _anchor("SEC. 106. HEALTH. Health coverage applies.")
    payload["verified"] = False
    with pytest.raises(ValueError, match="verified Pass 4 anchor"):
        build_review(payload)


def test_review_questions_follow_selected_domain():
    review = build_review(_anchor("SEC. 107. TAX CREDIT. A refundable tax credit shall be allowed to the taxpayer."))
    assert review.primary_domain == "tax"
    assert any("tax base" in item.lower() for item in review.review_questions)
    assert all("progressive" not in item.lower() and "conservative" not in item.lower() for item in review.review_questions)


def test_review_bill_writes_section_level_packets_and_multi_expert_count(tmp_path, monkeypatch):
    import engine.topic_expert as topic
    import engine.citations as citations

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    topic_dir = tmp_path / "topic"
    for directory in (ingested_dir, segment_dir, anchor_dir, topic_dir):
        directory.mkdir()

    text = """TITLE I - MIXED POLICY\nSEC. 101. HEALTH COVERAGE.\nThe Secretary shall establish health insurance coverage standards for hospitals.\nSEC. 102. HEALTH TAX CREDIT.\nA refundable tax credit is allowed for health insurance coverage premiums.\n"""
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

    monkeypatch.setattr(topic, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(topic, "TOPIC_DIR", topic_dir)
    monkeypatch.setattr(topic, "MONEY_DIR", tmp_path / "missing_money")
    monkeypatch.setattr(topic, "POWER_DIR", tmp_path / "missing_power")
    monkeypatch.setattr(topic, "BARREL_DIR", tmp_path / "missing_barrel")
    result = review_bill("demo")
    assert result.review_count == 2
    assert result.multi_expert_count >= 1
    assert result.reviews[0].anchor_id.startswith("bxr-demo-")
    assert (topic_dir / "demo.json").exists()
