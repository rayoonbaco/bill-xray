from engine import text_referee


def test_text_referee_constructs_from_exact_anchor_without_translator(monkeypatch):
    anchor = {
        "bill_id": "demo",
        "anchor_id": "a1",
        "section_label": "SEC. 101",
        "exact_text": "SEC. 101. PROGRAM. The Secretary shall establish the program. The Secretary may issue rules.",
        "source_sha256": "a" * 64,
        "text_sha256": "b" * 64,
        "location_marker": "canonical lines 1-3",
    }
    monkeypatch.setattr(text_referee.citations, "resolve_anchor", lambda bill_id, anchor_id: {**anchor, "verified": True})
    result = text_referee.construct_text_referee("demo", "a1")
    assert result.status == "constructed"
    assert result.claim_class == "TEXT"
    assert "shall establish the program" in result.text
    assert "progressive" not in result.text.lower()
    assert "conservative" not in result.text.lower()


def test_text_referee_refuses_arbitrary_truncation(monkeypatch):
    huge = "The Secretary shall " + ("apply every condition and limitation " * 30) + "."
    monkeypatch.setattr(text_referee.citations, "resolve_anchor", lambda bill_id, anchor_id: {
        "bill_id":"demo","anchor_id":"a1","section_label":"SEC. 1","exact_text":"SEC. 1. "+huge,
        "source_sha256":"a"*64,"text_sha256":"b"*64,"location_marker":"canonical lines 1-2","verified":True,
    })
    result = text_referee.construct_text_referee("demo", "a1")
    assert result.status == "unusable"
    assert result.text is None
