from pathlib import Path

import pytest

from engine.segment import classify_heading, segment_ingested_bill, segment_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_heading_classifier_recognizes_core_legislative_levels():
    assert classify_heading("DIVISION A - TEST")[0] == "division"
    assert classify_heading("TITLE II—HEALTH")[0] == "title"
    assert classify_heading("SUBTITLE B - TAXES")[0] == "subtitle"
    assert classify_heading("SEC. 101. SHORT TITLE.")[0] == "section"


def test_segmenter_preserves_line_bounded_blocks_and_hierarchy():
    text = (FIXTURES / "sample_structured_bill.txt").read_text(encoding="utf-8")
    result = segment_text("demo", text, source_document_ref="local:demo.txt", source_sha256="abc")
    assert result.segment_count == 7
    sections = [segment for segment in result.segments if segment.kind == "section"]
    assert [section.identifier for section in sections] == ["101", "102", "201"]
    assert "demonstration program" in sections[1].text.lower()
    assert sections[0].start_line == 5
    assert sections[0].end_line == 6
    assert len(sections[0].parent_segment_ids) == 3


def test_new_title_resets_old_subtitle_parent():
    text = (FIXTURES / "sample_structured_bill.txt").read_text(encoding="utf-8")
    result = segment_text("demo", text)
    section_201 = next(segment for segment in result.segments if segment.kind == "section" and segment.identifier == "201")
    parent_ids = " ".join(section_201.parent_segment_ids)
    assert ":subtitle:" not in parent_ids
    assert ":title:II:" in parent_ids


def test_segment_ingested_bill_requires_pass_2_artifact(tmp_path, monkeypatch):
    import engine.segment as segment_module
    monkeypatch.setattr(segment_module, "INGESTED_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        segment_ingested_bill("missing")
