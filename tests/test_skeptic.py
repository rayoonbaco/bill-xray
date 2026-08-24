import json

import pytest

from engine.skeptic import build_packet, build_skeptic_review


def _candidate(lens: str = "LEFT", *, status: str = "advocate_packet_ready", snapshot=None):
    return {
        "bill_id": "demo",
        "anchor_id": "bxr-demo",
        "segment_id": "demo:section:101:1",
        "section_label": "SEC. 101",
        "lens": lens,
        "claim_class": "INTERPRETATION",
        "status": status,
        "confidence": 0.9,
        "evidence_layers_present": ["citation_anchor", "topic_review"],
        "evidence_snapshot": snapshot or {
            "text_excerpt": "The Secretary may establish a grant program.",
            "topic_review": {"primary_domain": "health", "status": "expert_review_packet_ready"},
        },
        "external_evidence_needed": [],
        "location_marker": "canonical lines 1-2",
        "document_ref": "local:demo.txt",
        "source_url": "https://example.test/demo",
        "source_sha256": "a" * 64,
        "text_sha256": "b" * 64,
    }


def test_skeptic_requires_identical_evidence_spine():
    left = _candidate("LEFT")
    right = _candidate("RIGHT")
    packet = build_packet(left, right)
    assert packet.source_symmetry_passed is True
    assert packet.status == "skeptic_packet_ready"
    assert packet.claim_class == "UNKNOWN"
    assert packet.confidence >= 0.8


def test_skeptic_blocks_asymmetric_snapshot():
    left = _candidate("LEFT")
    right = _candidate("RIGHT", snapshot={"text_excerpt": "different"})
    packet = build_packet(left, right)
    assert packet.source_symmetry_passed is False
    assert packet.status == "blocked_asymmetric_record"
    assert any(c["code"] == "ASYMMETRIC_EVIDENCE" for c in packet.challenges)


def test_skeptic_rejects_mismatched_anchor_identity():
    left = _candidate("LEFT")
    right = _candidate("RIGHT")
    right["anchor_id"] = "other-anchor"
    with pytest.raises(ValueError, match="anchor_id"):
        build_packet(left, right)


def test_known_context_gap_is_preserved_not_smoothed_over():
    left = _candidate("LEFT", status="needs_context")
    right = _candidate("RIGHT")
    packet = build_packet(left, right)
    assert packet.status == "skeptic_packet_ready"
    assert packet.confidence < 0.8
    assert any(c["code"] == "KNOWN_CONTEXT_GAP" for c in packet.challenges)


def test_barrel_flag_gets_explicit_overreach_challenge():
    snapshot = {
        "text_excerpt": "A special rule applies.",
        "barrel_scan": {"labels": ["Narrow Carve-Out"], "why_flagged": ["narrow scope"]},
    }
    packet = build_packet(_candidate("LEFT", snapshot=snapshot), _candidate("RIGHT", snapshot=snapshot))
    assert any(c["code"] == "BARREL_FLAG_OVERREACH" for c in packet.challenges)
    assert any("corruption" in move.lower() for move in packet.forbidden_moves)


def test_thin_record_triggers_evidence_concentration_warning():
    left = _candidate("LEFT")
    right = _candidate("RIGHT")
    left["evidence_layers_present"] = ["citation_anchor"]
    right["evidence_layers_present"] = ["citation_anchor"]
    packet = build_packet(left, right)
    assert any(c["code"] == "THIN_EVIDENCE_RECORD" for c in packet.challenges)


def test_external_evidence_needs_are_combined_symmetrically():
    left = _candidate("LEFT")
    right = _candidate("RIGHT")
    left["external_evidence_needed"] = ["Need CBO evidence."]
    right["external_evidence_needed"] = ["Need CBO evidence.", "Need implementation evidence."]
    packet = build_packet(left, right)
    assert "Need CBO evidence." in packet.required_resolutions
    assert "Need implementation evidence." in packet.required_resolutions
    assert any(c["code"] == "EXTERNAL_EVIDENCE_REQUIRED" for c in packet.challenges)


def test_build_skeptic_review_pairs_same_anchor_sets(tmp_path, monkeypatch):
    import engine.skeptic as skeptic

    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    out_dir = tmp_path / "skeptic"
    left_dir.mkdir(); right_dir.mkdir()
    left = _candidate("LEFT")
    right = _candidate("RIGHT")
    (left_dir / "demo.json").write_text(json.dumps({"candidates": [left]}), encoding="utf-8")
    (right_dir / "demo.json").write_text(json.dumps({"candidates": [right]}), encoding="utf-8")
    monkeypatch.setattr(skeptic, "LEFT_DIR", left_dir)
    monkeypatch.setattr(skeptic, "RIGHT_DIR", right_dir)
    monkeypatch.setattr(skeptic, "SKEPTIC_DIR", out_dir)

    result = build_skeptic_review("demo")
    assert result.packet_count == 1
    assert result.ready_count == 1
    assert (out_dir / "demo.json").exists()


def test_build_skeptic_review_refuses_unpaired_advocacy_records(tmp_path, monkeypatch):
    import engine.skeptic as skeptic

    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    left_dir.mkdir(); right_dir.mkdir()
    left = _candidate("LEFT")
    right = _candidate("RIGHT")
    right["anchor_id"] = "another"
    (left_dir / "demo.json").write_text(json.dumps({"candidates": [left]}), encoding="utf-8")
    (right_dir / "demo.json").write_text(json.dumps({"candidates": [right]}), encoding="utf-8")
    monkeypatch.setattr(skeptic, "LEFT_DIR", left_dir)
    monkeypatch.setattr(skeptic, "RIGHT_DIR", right_dir)

    with pytest.raises(ValueError, match="anchor sets differ"):
        build_skeptic_review("demo")
