from pathlib import Path

from engine.segment import classify_heading, segment_text


def test_section_keyword_does_not_get_misparsed_as_identifier_tion():
    hit = classify_heading("SECTION 1. SHORT TITLE.")
    assert hit == ("section", "1", "SECTION 1. SHORT TITLE.")


def test_statutory_cross_references_are_not_bill_structure_headings():
    assert classify_heading("Section 202(c) of the Controlled Substances Act (21 U.S.C. 812(c))") is None
    assert classify_heading("section 201; or") is None
    assert classify_heading("section 553 of title 5, United States Code.") is None


def test_fresh_hr171_structure_is_four_real_bill_sections():
    root = Path(__file__).resolve().parents[1]
    source = root / "data" / "source_documents" / "gpo-118hr171ih.txt"
    if not source.exists():
        return
    result = segment_text("gpo-118hr171ih", source.read_text(encoding="utf-8"))
    sections = [item for item in result.segments if item.kind == "section"]
    assert [item.identifier for item in sections] == ["1", "2", "3", "4"]
    assert sections[0].heading == "SECTION 1. SHORT TITLE."
    assert sections[-1].heading == "SEC. 4. RULEMAKING."
