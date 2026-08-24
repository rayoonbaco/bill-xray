import hashlib
import json
from dataclasses import asdict

import pytest

from engine.segment import segment_text
from engine.translator import translate_anchor_payload


def _anchor(exact_text: str, *, anchor_id: str = "bxr-demo") -> dict:
    return {
        "anchor_id": anchor_id,
        "bill_id": "demo",
        "segment_id": "demo:section:102:1",
        "section_label": "SEC. 102",
        "location_marker": "canonical lines 5-6",
        "document_ref": "local:demo.txt",
        "source_url": "https://example.test/demo",
        "source_sha256": "a" * 64,
        "text_sha256": hashlib.sha256(exact_text.encode("utf-8")).hexdigest(),
        "exact_text": exact_text,
        "verified": True,
    }


def test_shall_becomes_must_without_inventing_effects():
    result = translate_anchor_payload(
        _anchor("SEC. 102. DEMONSTRATION PROGRAM.\nThe Secretary shall establish a demonstration program.")
    )
    assert result.status == "translated"
    assert result.claim_class == "TEXT"
    assert result.confidence >= 0.95
    assert result.plain_english == "The Secretary must establish a demonstration program."
    assert "benefit" not in result.plain_english.lower()
    assert "intent" not in result.plain_english.lower()


def test_may_preserves_discretion():
    result = translate_anchor_payload(
        _anchor("SEC. 201. AUTHORITY.\nThe Administrator may issue regulations.")
    )
    assert result.status == "translated"
    assert result.plain_english == "The Administrator is allowed to issue regulations."
    assert "must" not in result.plain_english.lower()


def test_material_qualifier_is_preserved():
    result = translate_anchor_payload(
        _anchor(
            "SEC. 301. DEADLINE.\nThe Secretary shall issue guidance not later than January 1, 2030."
        )
    )
    assert result.status == "translated"
    assert result.preserved_qualifiers == ["not later than January 1, 2030"]
    assert "not later than January 1, 2030" in result.plain_english


def test_unknown_language_routes_to_review_instead_of_guessing():
    result = translate_anchor_payload(
        _anchor("SEC. 401. FORMULA.\nThe applicable percentage equals the benchmark percentage adjusted under subsection (c).")
    )
    assert result.status == "needs_expert_review"
    assert result.plain_english is None
    assert result.claim_class == "UNKNOWN"
    assert result.confidence < 0.8
    assert result.review_reason


def test_unverified_anchor_is_rejected():
    payload = _anchor("SEC. 1. TEST.\nThe Secretary shall act.")
    payload["verified"] = False
    with pytest.raises(ValueError, match="verified Pass 4 anchor"):
        translate_anchor_payload(payload)


def test_translate_bill_uses_only_verified_section_anchors(tmp_path, monkeypatch):
    import engine.citations as citations
    import engine.translator as translator

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    translation_dir = tmp_path / "translations"
    for directory in (ingested_dir, segment_dir, anchor_dir, translation_dir):
        directory.mkdir()

    text = """DIVISION A - TEST\nTITLE I - GENERAL\nSEC. 101. PROGRAM.\nThe Secretary shall establish a program.\nSEC. 102. AUTHORITY.\nThe Administrator may issue regulations.\n"""
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

    monkeypatch.setattr(translator, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(translator, "TRANSLATION_DIR", translation_dir)
    result = translator.translate_bill("demo")
    assert result.translated_count == 2
    assert result.review_count == 0
    assert len(result.translations) == 2
    assert all(item.anchor_id.startswith("bxr-demo-") for item in result.translations)
    assert (translation_dir / "demo.json").exists()
