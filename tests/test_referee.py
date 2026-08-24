import json

import pytest

from engine.referee import build_decision, build_referee_review


def _advocate(lens: str, *, status="advocate_packet_ready", snapshot=None, layers=None):
    return {
        "bill_id": "demo",
        "anchor_id": "anchor-1",
        "segment_id": "section-1",
        "section_label": "SEC. 101.",
        "lens": lens,
        "claim_class": "INTERPRETATION",
        "status": status,
        "confidence": 0.86,
        "evidence_layers_present": layers or ["citation_anchor", "money", "power"],
        "evidence_snapshot": snapshot or {
            "text_excerpt": "The Secretary shall establish a grant program.",
            "money": {"categories": ["grant"], "status": "finding_ready"},
            "power": {"authority_types": ["mandatory_duty"], "status": "finding_ready"},
        },
        "external_evidence_needed": [],
        "location_marker": "lines 1-3",
        "document_ref": "local:demo.txt",
        "source_url": "https://example.test/demo",
        "source_sha256": "a" * 64,
        "text_sha256": "b" * 64,
    }


def _skeptic(*, symmetry=True, challenges=None, required=None):
    return {
        "bill_id": "demo",
        "anchor_id": "anchor-1",
        "segment_id": "section-1",
        "section_label": "SEC. 101.",
        "source_symmetry_passed": symmetry,
        "challenges": challenges or [],
        "required_resolutions": required or [],
        "location_marker": "lines 1-3",
        "document_ref": "local:demo.txt",
        "source_url": "https://example.test/demo",
        "source_sha256": "a" * 64,
        "text_sha256": "b" * 64,
    }


def test_referee_does_not_average_left_and_right():
    decision = build_decision(_advocate("LEFT"), _advocate("RIGHT"), _skeptic())
    assert decision.status == "synthesis_ready"
    assert decision.left_lane["claim_class"] == "INTERPRETATION"
    assert decision.right_lane["claim_class"] == "INTERPRETATION"
    assert decision.text_lane["claim_class"] == "TEXT"
    assert any("false middle" in move.lower() for move in decision.forbidden_moves)


def test_referee_allows_bounded_direct_effect_when_mechanic_exists():
    decision = build_decision(_advocate("LEFT"), _advocate("RIGHT"), _skeptic())
    assert decision.direct_effect_lane["status"] == "admissible_with_bounds"
    assert decision.direct_effect_lane["claim_class"] == "DIRECT_EFFECT"
    assert "DIRECT_EFFECT" in decision.admissible_claim_classes


def test_referee_refuses_likely_effect_without_external_evidence():
    decision = build_decision(_advocate("LEFT"), _advocate("RIGHT"), _skeptic())
    assert decision.likely_effect_lane["status"] == "needs_external_evidence"
    assert "LIKELY_EFFECT" in decision.prohibited_claim_classes


def test_referee_blocks_asymmetric_record():
    decision = build_decision(_advocate("LEFT"), _advocate("RIGHT"), _skeptic(symmetry=False))
    assert decision.status == "blocked"
    assert decision.source_symmetry_passed is False
    assert decision.text_lane["status"] == "blocked"


def test_referee_preserves_high_severity_context_gap():
    challenges = [{
        "code": "KNOWN_CONTEXT_GAP",
        "severity": "high",
        "message": "Fiscal context is missing.",
        "resolution": "Obtain authoritative fiscal evidence.",
    }]
    decision = build_decision(
        _advocate("LEFT", status="needs_context"),
        _advocate("RIGHT", status="needs_context"),
        _skeptic(challenges=challenges, required=["Obtain authoritative fiscal evidence."]),
    )
    assert decision.status == "needs_context"
    assert decision.confidence < 0.8
    assert "Obtain authoritative fiscal evidence." in decision.required_before_publication


def test_barrel_scan_is_only_a_scrutiny_flag():
    snapshot = {
        "text_excerpt": "A special rule applies.",
        "barrel_scan": {"labels": ["Narrow Carve-Out"], "why_flagged": ["narrow scope"]},
    }
    layers = ["citation_anchor", "barrel_scan"]
    decision = build_decision(
        _advocate("LEFT", snapshot=snapshot, layers=layers),
        _advocate("RIGHT", snapshot=snapshot, layers=layers),
        _skeptic(),
    )
    assert decision.barrel_lane["status"] == "admissible_as_scrutiny_flag"
    assert "misconduct" in decision.barrel_lane["reason"].lower() or "corruption" in " ".join(decision.forbidden_moves).lower()


def test_referee_rejects_mismatched_identity():
    right = _advocate("RIGHT")
    right["text_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="text_sha256"):
        build_decision(_advocate("LEFT"), right, _skeptic())


def test_build_referee_review_requires_identical_anchor_sets(tmp_path, monkeypatch):
    import engine.referee as referee

    left_dir = tmp_path / "left"; left_dir.mkdir()
    right_dir = tmp_path / "right"; right_dir.mkdir()
    skeptic_dir = tmp_path / "skeptic"; skeptic_dir.mkdir()
    out_dir = tmp_path / "referee"

    left = _advocate("LEFT")
    right = _advocate("RIGHT")
    skeptic = _skeptic()
    (left_dir / "demo.json").write_text(json.dumps({"candidates": [left]}), encoding="utf-8")
    (right_dir / "demo.json").write_text(json.dumps({"candidates": [right]}), encoding="utf-8")
    (skeptic_dir / "demo.json").write_text(json.dumps({"packets": [skeptic]}), encoding="utf-8")

    monkeypatch.setattr(referee, "LEFT_DIR", left_dir)
    monkeypatch.setattr(referee, "RIGHT_DIR", right_dir)
    monkeypatch.setattr(referee, "SKEPTIC_DIR", skeptic_dir)
    monkeypatch.setattr(referee, "REFEREE_DIR", out_dir)

    result = build_referee_review("demo")
    assert result.decision_count == 1
    assert result.synthesis_ready_count == 1
    assert (out_dir / "demo.json").exists()


def test_build_referee_review_blocks_anchor_set_mismatch(tmp_path, monkeypatch):
    import engine.referee as referee

    left_dir = tmp_path / "left"; left_dir.mkdir()
    right_dir = tmp_path / "right"; right_dir.mkdir()
    skeptic_dir = tmp_path / "skeptic"; skeptic_dir.mkdir()

    left = _advocate("LEFT")
    right = _advocate("RIGHT")
    skeptic = _skeptic()
    skeptic["anchor_id"] = "different"
    (left_dir / "demo.json").write_text(json.dumps({"candidates": [left]}), encoding="utf-8")
    (right_dir / "demo.json").write_text(json.dumps({"candidates": [right]}), encoding="utf-8")
    (skeptic_dir / "demo.json").write_text(json.dumps({"packets": [skeptic]}), encoding="utf-8")

    monkeypatch.setattr(referee, "LEFT_DIR", left_dir)
    monkeypatch.setattr(referee, "RIGHT_DIR", right_dir)
    monkeypatch.setattr(referee, "SKEPTIC_DIR", skeptic_dir)

    with pytest.raises(ValueError, match="anchor sets"):
        build_referee_review("demo")
