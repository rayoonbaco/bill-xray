import hashlib
from pathlib import Path

import pytest

from engine.ingest import extract_text, ingest_file, load_source_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def test_txt_ingestion_preserves_provenance_and_fingerprint():
    path = FIXTURES / "sample_bill.txt"
    raw = path.read_bytes()
    result = ingest_file("demo", path, "https://example.gov/demo")
    assert result.bill_id == "demo"
    assert result.source_format == "txt"
    assert result.source_url == "https://example.gov/demo"
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert "SECTION 1. SHORT TITLE." in result.text
    assert result.line_count >= 5


def test_xml_ingestion_extracts_readable_legislative_text():
    path = FIXTURES / "sample_bill.xml"
    result = ingest_file("demo", path)
    assert result.source_format == "xml"
    assert "SECTION 1. SHORT TITLE." in result.text
    assert "demonstration program" in result.text


def test_ingestion_rejects_unsupported_format(tmp_path):
    path = tmp_path / "bill.pdf"
    path.write_bytes(b"not a bill")
    with pytest.raises(ValueError):
        ingest_file("demo", path)


def test_ingestion_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest_file("demo", tmp_path / "missing.txt")


def test_manifest_pins_two_proving_ground_bills():
    manifest = load_source_manifest()
    assert {"aca", "ira", "tcja", "obbba"}.issubset(set(manifest))
    assert manifest["aca"]["law_number"] == "Public Law 111-148"
    assert manifest["obbba"]["law_number"] == "Public Law 119-21"
