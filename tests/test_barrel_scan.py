import hashlib
import json
from dataclasses import asdict

import pytest

from engine.barrel_scan import (
    LABEL_CROSSREF_OPACITY,
    LABEL_NARROW_CARVEOUT,
    LABEL_POTENTIAL_RIDER,
    LABEL_SCOPE_SURPRISE,
    LABEL_SPECIFIC_BENEFICIARY,
    build_topic_profile,
    evaluate_anchor,
)
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


def test_narrow_carveout_is_flagged_without_wrongdoing_claim():
    result = evaluate_anchor(
        _anchor("SEC. 101. HEALTH COVERAGE EXCEPTION.\nNotwithstanding section 20, this requirement shall not apply to a facility located in Example County."),
        ["health", "coverage", "insurance"],
    )
    assert result is not None
    assert LABEL_NARROW_CARVEOUT in result.labels
    assert LABEL_SPECIFIC_BENEFICIARY in result.labels
    assert result.status == "review_candidate"
    assert result.claim_class == "TEXT"
    serialized = json.dumps(asdict(result)).lower()
    assert "corruption" not in serialized
    assert "wrongdoing" not in serialized


def test_cross_reference_opacity_requires_real_cross_reference():
    result = evaluate_anchor(
        _anchor("SEC. 102. SPECIAL RULE.\nThe rule under section 205(a)(3), subject to section 301, and 26 U.S.C. 36B shall apply."),
        ["special", "rule", "coverage"],
    )
    assert result is not None
    assert LABEL_CROSSREF_OPACITY in result.labels
    assert result.factors.cross_reference_opacity >= 0.58


def test_large_money_amount_alone_does_not_become_barrel_candidate():
    result = evaluate_anchor(
        _anchor("SEC. 103. HEALTH GRANTS.\nThere is appropriated $100,000,000,000 for health grants."),
        ["health", "grants", "coverage"],
    )
    assert result is None


def test_topical_distance_alone_does_not_become_potential_rider():
    result = evaluate_anchor(
        _anchor("SEC. 104. SPACE WEATHER.\nThe agency shall publish an annual space weather report."),
        ["health", "coverage", "insurance"],
    )
    assert result is None


def test_potential_rider_requires_distance_plus_independent_signal():
    result = evaluate_anchor(
        _anchor("SEC. 105. SPACEPORT FACILITY.\nNotwithstanding section 20, $5,000,000,000 shall be available only for a facility located in Example County."),
        ["health", "coverage", "insurance", "premium"],
    )
    assert result is not None
    assert LABEL_SCOPE_SURPRISE in result.labels
    assert LABEL_POTENTIAL_RIDER in result.labels
    assert len(result.why_flagged) >= 2


def test_unverified_anchor_is_rejected():
    payload = _anchor("SEC. 106. EXCEPTION.\nThis requirement shall not apply to the specified entity.")
    payload["verified"] = False
    with pytest.raises(ValueError, match="verified Pass 4 anchor"):
        evaluate_anchor(payload, ["health"])


def test_topic_profile_uses_repeated_heading_terms():
    anchors = [
        _anchor("SEC. 101. HEALTH COVERAGE STANDARDS.\nText", anchor_id="a"),
        _anchor("SEC. 102. HEALTH COVERAGE GRANTS.\nText", anchor_id="b"),
        _anchor("SEC. 103. INSURANCE COVERAGE RULES.\nText", anchor_id="c"),
    ]
    profile = build_topic_profile(anchors)
    assert "coverage" in profile
    assert "health" in profile


def test_scan_bill_writes_ranked_section_candidates(tmp_path, monkeypatch):
    import engine.barrel_scan as barrel
    import engine.citations as citations

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    barrel_dir = tmp_path / "barrel"
    for directory in (ingested_dir, segment_dir, anchor_dir, barrel_dir):
        directory.mkdir()

    text = """DIVISION A - HEALTH\nTITLE I - HEALTH COVERAGE\nSEC. 101. HEALTH COVERAGE STANDARDS.\nThe Secretary shall issue health coverage standards.\nSEC. 102. HEALTH COVERAGE GRANTS.\nThe Secretary may award health coverage grants.\nSEC. 103. SPACEPORT FACILITY.\nNotwithstanding section 20, $5,000,000,000 shall be available only for a facility located in Example County.\n"""
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

    monkeypatch.setattr(barrel, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(barrel, "BARREL_DIR", barrel_dir)
    result = barrel.scan_bill("demo")
    assert result.candidate_count == 1
    assert result.candidates[0].section_label == "SEC. 103"
    assert LABEL_POTENTIAL_RIDER in result.candidates[0].labels
    assert result.candidates[0].anchor_id.startswith("bxr-demo-")
    assert (barrel_dir / "demo.json").exists()
