import hashlib
import json
from dataclasses import asdict

import pytest

from engine.segment import segment_text


def _write_pass2_and_pass3(tmp_path, monkeypatch):
    import engine.citations as citations

    ingested_dir = tmp_path / "ingested"
    segment_dir = tmp_path / "segments"
    anchor_dir = tmp_path / "anchors"
    ingested_dir.mkdir()
    segment_dir.mkdir()

    text = """DIVISION A - TEST\nTITLE I - HEALTH\nSUBTITLE A - PROGRAM\nSEC. 101. SHORT TITLE.\nThis Act may be cited as the Test Act.\nSEC. 102. DEMONSTRATION PROGRAM.\nThe Secretary shall establish a demonstration program.\n"""
    raw = text.encode("utf-8")
    source_sha = hashlib.sha256(raw).hexdigest()
    ingested = {
        "bill_id": "demo",
        "source_filename": "demo.txt",
        "source_format": "txt",
        "source_url": "https://example.test/demo",
        "document_ref": "local:demo.txt",
        "sha256": source_sha,
        "text": text,
    }
    (ingested_dir / "demo.json").write_text(json.dumps(ingested), encoding="utf-8")

    segmented = segment_text(
        "demo",
        text,
        source_document_ref="local:demo.txt",
        source_sha256=source_sha,
    )
    (segment_dir / "demo.json").write_text(
        json.dumps(asdict(segmented), ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.setattr(citations, "INGESTED_DIR", ingested_dir)
    monkeypatch.setattr(citations, "SEGMENT_DIR", segment_dir)
    monkeypatch.setattr(citations, "ANCHOR_DIR", anchor_dir)
    return citations, ingested_dir, segment_dir, anchor_dir


def test_anchor_ids_are_deterministic_and_line_exact(tmp_path, monkeypatch):
    citations, *_ = _write_pass2_and_pass3(tmp_path, monkeypatch)
    first = citations.build_anchor_index("demo")
    second = citations.build_anchor_index("demo", write=False)
    assert [a.anchor_id for a in first.anchors] == [a.anchor_id for a in second.anchors]

    section = next(a for a in first.anchors if a.kind == "section" and a.identifier == "102")
    resolved = citations.resolve_anchor("demo", section.anchor_id)
    assert resolved["verified"] is True
    assert resolved["exact_text"].startswith("SEC. 102. DEMONSTRATION PROGRAM.")
    assert "Secretary shall establish" in resolved["exact_text"]
    assert resolved["location_marker"] == f"canonical lines {section.start_line}-{section.end_line}"


def test_anchor_resolution_detects_source_drift(tmp_path, monkeypatch):
    citations, ingested_dir, *_ = _write_pass2_and_pass3(tmp_path, monkeypatch)
    index = citations.build_anchor_index("demo")
    target = index.anchors[-1]

    payload = json.loads((ingested_dir / "demo.json").read_text(encoding="utf-8"))
    payload["sha256"] = "0" * 64
    (ingested_dir / "demo.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint"):
        citations.resolve_anchor("demo", target.anchor_id)


def test_anchor_build_rejects_stale_segmentation(tmp_path, monkeypatch):
    citations, _, segment_dir, _ = _write_pass2_and_pass3(tmp_path, monkeypatch)
    payload = json.loads((segment_dir / "demo.json").read_text(encoding="utf-8"))
    payload["source_sha256"] = "stale"
    (segment_dir / "demo.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        citations.build_anchor_index("demo")
