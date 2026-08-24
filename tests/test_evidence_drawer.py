import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from engine.segment import segment_text

ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path, monkeypatch):
    import engine.citations as citations
    import engine.evidence as evidence

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    analysis_dir = tmp_path / "analyses"
    for directory in (ingested_dir, segment_dir, anchor_dir, analysis_dir):
        directory.mkdir()

    text = "SEC. 101. TEST PROGRAM.\nThe Secretary shall establish the program.\n"
    source_sha = hashlib.sha256(text.encode()).hexdigest()
    ingested = {
        "bill_id": "demo", "sha256": source_sha, "text": text,
        "document_ref": "local:demo.txt", "source_url": "https://example.test/demo",
    }
    (ingested_dir / "demo.json").write_text(json.dumps(ingested), encoding="utf-8")
    segmented = segment_text("demo", text, source_document_ref="local:demo.txt", source_sha256=source_sha)
    (segment_dir / "demo.json").write_text(json.dumps(asdict(segmented)), encoding="utf-8")

    monkeypatch.setattr(citations, "INGESTED_DIR", ingested_dir)
    monkeypatch.setattr(citations, "SEGMENT_DIR", segment_dir)
    monkeypatch.setattr(citations, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(evidence, "resolve_anchor", citations.resolve_anchor)
    monkeypatch.setattr(evidence, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(evidence, "ANALYSIS_DIR", analysis_dir)
    index = citations.build_anchor_index("demo")
    return evidence, citations, index.anchors[0], ingested_dir, analysis_dir


def test_evidence_payload_re_resolves_exact_source_text(tmp_path, monkeypatch):
    evidence, _, anchor, _, _ = _fixture(tmp_path, monkeypatch)
    payload = evidence.evidence_payload("demo", anchor.anchor_id)
    assert payload["verified"] is True
    assert payload["anchor_id"] == anchor.anchor_id
    assert "Secretary shall establish" in payload["exact_text"]
    assert payload["source_navigation"]["official_url"] == "https://example.test/demo"


def test_evidence_payload_fails_closed_on_source_drift(tmp_path, monkeypatch):
    evidence, _, anchor, ingested_dir, _ = _fixture(tmp_path, monkeypatch)
    payload = json.loads((ingested_dir / "demo.json").read_text())
    payload["sha256"] = "0" * 64
    (ingested_dir / "demo.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        evidence.evidence_payload("demo", anchor.anchor_id)


def test_bill_template_has_one_click_evidence_controls_and_single_drawer():
    template = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert "data-evidence-trigger" in template
    assert 'id="evidence-drawer"' in template
    assert 'id="evidence-exact-text"' in template
    assert "Open official source" in template
    assert "Return to summary" in template
    assert template.count('data-evidence-close') >= 2


def test_drawer_script_fetches_verified_anchor_endpoint_and_supports_escape():
    script = (ROOT / "static" / "evidence_drawer.js").read_text(encoding="utf-8")
    assert "/api/evidence/" in script
    assert "encodeURIComponent" in script
    assert "event.key === 'Escape'" in script
    assert "target.focus()" in script
    assert "closest('[data-evidence-close]')" in script
    assert "closeDrawer(event)" in script
    assert "event.preventDefault()" in script
    assert "backdrop.setAttribute('aria-hidden', 'true')" in script
    assert "textContent" in script


def test_evidence_drawer_is_overlay_not_a_second_report_page():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".evidence-drawer{position:fixed" in css
    assert ".evidence-backdrop{position:fixed" in css
    assert ".evidence-open{overflow:hidden}" in css


def test_bill_template_cache_busts_evidence_drawer_after_navigation_fix():
    template = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert "/static/evidence_drawer.js?v=33.2" in template
