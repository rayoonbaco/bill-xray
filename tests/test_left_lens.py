import hashlib
import json
from dataclasses import asdict

import pytest

from engine.left_lens import build_candidate, build_left_lens
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


def test_left_candidate_is_always_explicit_interpretation():
    candidate = build_candidate(
        _anchor("SEC. 101. HEALTH COVERAGE. The Secretary shall establish health coverage standards."),
        topic_review={
            "expert_domains": ["health"],
            "primary_domain": "health",
            "routing_confidence": 0.93,
            "status": "expert_review_packet_ready",
            "context_needed": [],
        },
    )
    assert candidate.lens == "LEFT"
    assert candidate.claim_class == "INTERPRETATION"
    assert candidate.status == "advocate_packet_ready"
    assert candidate.confidence >= 0.8


def test_health_domain_uses_progressive_health_questions_without_making_claim():
    candidate = build_candidate(
        _anchor("SEC. 102. HEALTH. Health insurance coverage standards apply."),
        topic_review={
            "expert_domains": ["health"],
            "primary_domain": "health",
            "routing_confidence": 0.9,
            "status": "expert_review_packet_ready",
            "context_needed": [],
        },
    )
    assert any("access" in q.lower() or "equitable" in q.lower() for q in candidate.progressive_questions)
    assert "strongest good-faith progressive interpretation" in candidate.strongest_case_instruction
    assert candidate.evidence_snapshot["text_excerpt"]


def test_missing_topic_assignment_forces_context_instead_of_guess():
    candidate = build_candidate(
        _anchor("SEC. 103. SPECIAL RULE. The requirement described above shall apply."),
        topic_review={
            "expert_domains": ["general_legislative"],
            "primary_domain": "general_legislative",
            "routing_confidence": 0.45,
            "status": "needs_human_topic_assignment",
            "context_needed": ["assign a specialist"],
        },
    )
    assert candidate.status == "needs_context"
    assert candidate.confidence < 0.8
    assert any("subject-matter expert" in item for item in candidate.external_evidence_needed)


def test_money_and_power_are_evidence_inputs_not_advocacy_facts():
    candidate = build_candidate(
        _anchor("SEC. 104. GRANT AUTHORITY. The Secretary may award grants of $10,000,000."),
        money_finding={
            "categories": ["grant"],
            "amounts": [{"raw": "$10,000,000", "amount_usd": "10000000"}],
            "percentages": [],
            "fiscal_direction": "funding_or_authority",
            "status": "extracted",
        },
        power_finding={
            "authority_types": ["delegated_discretion"],
            "actors": ["the Secretary"],
            "authority_direction": "assigns_discretion",
            "status": "extracted",
        },
        topic_review={
            "expert_domains": ["health"],
            "primary_domain": "health",
            "routing_confidence": 0.9,
            "status": "expert_review_packet_ready",
            "context_needed": [],
        },
    )
    assert set(candidate.evidence_layers_present) == {"citation_anchor", "money", "power", "topic_review"}
    assert candidate.claim_class == "INTERPRETATION"
    assert any("fiscal/distribution" in item for item in candidate.external_evidence_needed)


def test_barrel_flag_cannot_become_wrongdoing_claim():
    candidate = build_candidate(
        _anchor("SEC. 105. SPECIAL BENEFIT. A special rule applies."),
        barrel_candidate={
            "labels": ["Narrow Carve-Out"],
            "why_flagged": ["A narrow exception appears in the section."],
            "status": "review_candidate",
        },
    )
    assert any("not evidence of favoritism or wrongdoing" in item for item in candidate.external_evidence_needed)
    assert any("corruption" in item.lower() for item in candidate.forbidden_moves)


def test_unverified_anchor_is_rejected():
    payload = _anchor("SEC. 106. DEMO. Text.")
    payload["verified"] = False
    with pytest.raises(ValueError, match="verified Pass 4 anchor"):
        build_candidate(payload)


def test_left_lens_build_writes_section_packets(tmp_path, monkeypatch):
    import engine.left_lens as left
    import engine.citations as citations

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    left_dir = tmp_path / "left"
    topic_dir = tmp_path / "topic"
    for directory in (ingested_dir, segment_dir, anchor_dir, left_dir, topic_dir):
        directory.mkdir()

    text = """TITLE I - HEALTH\nSEC. 101. HEALTH COVERAGE.\nThe Secretary shall establish health insurance coverage standards.\nSEC. 102. TAX CREDIT.\nA refundable tax credit shall be allowed to the taxpayer.\n"""
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
    index = citations.build_anchor_index("demo")

    section_anchors = [a for a in index.anchors if a.kind == "section"]
    topic_payload = {
        "reviews": [
            {
                "anchor_id": section_anchors[0].anchor_id,
                "expert_domains": ["health"],
                "primary_domain": "health",
                "routing_confidence": 0.93,
                "status": "expert_review_packet_ready",
                "context_needed": [],
            },
            {
                "anchor_id": section_anchors[1].anchor_id,
                "expert_domains": ["tax"],
                "primary_domain": "tax",
                "routing_confidence": 0.93,
                "status": "expert_review_packet_ready",
                "context_needed": [],
            },
        ]
    }
    (topic_dir / "demo.json").write_text(json.dumps(topic_payload), encoding="utf-8")

    monkeypatch.setattr(left, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(left, "LEFT_DIR", left_dir)
    monkeypatch.setattr(left, "TOPIC_DIR", topic_dir)
    monkeypatch.setattr(left, "MONEY_DIR", tmp_path / "missing_money")
    monkeypatch.setattr(left, "POWER_DIR", tmp_path / "missing_power")
    monkeypatch.setattr(left, "BARREL_DIR", tmp_path / "missing_barrel")

    result = build_left_lens("demo")
    assert result.candidate_count == 2
    assert result.ready_count == 2
    assert all(item.claim_class == "INTERPRETATION" for item in result.candidates)
    assert (left_dir / "demo.json").exists()
