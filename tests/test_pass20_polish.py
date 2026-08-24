from pathlib import Path

from engine.synthesis import _translation_text, _money_text

ROOT = Path(__file__).resolve().parents[1]

def test_front_page_filters_legislative_edit_code():
    packet = {"status":"translated", "plain_english":"26 U.S.C. 123 is amended by striking $5 and inserting $10."}
    assert _translation_text(packet) is None

def test_front_page_keeps_plain_english_effect():
    packet = {"status":"translated", "plain_english":"The Secretary must make $285,000,000 available for this program each fiscal year."}
    assert _translation_text(packet) == packet["plain_english"]

def test_money_copy_is_public_facing_not_extractor_jargon():
    text = _money_text({"categories":["appropriation"], "amounts":[{"raw":"$5,000,000,000"}], "timing":[]})
    assert "$5,000,000,000" in text
    assert "appropriation" in text
    assert "this section contains" not in text.lower()
    assert "contains" not in text.lower()

def test_pass20_surface_markers_exist():
    bill = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    home = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "SCRUTINY, NOT ACCUSATION" in bill
    assert "Did you read the bill? We did." in home
    assert (ROOT / "static" / "favicon.svg").exists()
    assert (ROOT / "render.yaml").exists()
