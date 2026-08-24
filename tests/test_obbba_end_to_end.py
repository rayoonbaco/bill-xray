import json
from pathlib import Path

from engine import obbba_end_to_end
from tools.fetch_obbba_source import html_to_statute_text


def test_govinfo_obbba_parser_preserves_public_law_identity_and_text():
    body = "Public Law 119-21\n119th Congress\nH.R. 1\n" + ("SEC. 70201. NO TAX ON TIPS.\n" * 30000)
    html = f"<html><body><pre>{body}</pre></body></html>"
    text = html_to_statute_text(html)
    assert "Public Law 119-21" in text
    assert "H.R. 1" in text
    assert "SEC. 70201. NO TAX ON TIPS." in text


def test_obbba_author_advocacy_keeps_left_right_on_same_anchor(tmp_path, monkeypatch):
    left_dir = tmp_path / "data" / "left_lens"
    right_dir = tmp_path / "data" / "right_lens"
    left_dir.mkdir(parents=True)
    right_dir.mkdir(parents=True)
    left = {"candidates": [{"anchor_id": "o1", "section_label": "SEC. 71119. REQUIREMENT FOR STATES TO ESTABLISH MEDICAID COMMUNITY ENGAGEMENT REQUIREMENTS", "claim_class": "INTERPRETATION"}]}
    right = {"candidates": [{"anchor_id": "o1", "section_label": "SEC. 71119. REQUIREMENT FOR STATES TO ESTABLISH MEDICAID COMMUNITY ENGAGEMENT REQUIREMENTS", "claim_class": "INTERPRETATION"}]}
    (left_dir / "obbba.json").write_text(json.dumps(left))
    (right_dir / "obbba.json").write_text(json.dumps(right))
    monkeypatch.setattr(obbba_end_to_end, "ROOT", tmp_path)
    count = obbba_end_to_end.author_advocacy("obbba")
    assert count == 1
    l = json.loads((left_dir / "obbba.json").read_text())["candidates"][0]
    r = json.loads((right_dir / "obbba.json").read_text())["candidates"][0]
    assert l["anchor_id"] == r["anchor_id"] == "o1"
    assert l["claim_class"] == r["claim_class"] == "INTERPRETATION"
    assert l["public_interpretation"] != r["public_interpretation"]
    assert "Pass 17 curated" in l["public_interpretation_provenance"]


def test_pass17_documentation_and_runner_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "PASS_17_OBBBA_END_TO_END_TEST.md").exists()
    bat = (root / "RUN_OBBBA_END_TO_END.bat").read_text(encoding="utf-8")
    assert "fetch_obbba_source.py" in bat
    assert "-u -m engine.obbba_end_to_end" in bat
    assert "obbba_progress.json" in bat
