import json
from pathlib import Path

from engine import aca_end_to_end
from tools.fetch_aca_source import html_to_statute_text


def test_govinfo_html_parser_preserves_identity_and_text():
    body = "Public Law 111-148\nPatient Protection and Affordable Care Act\n" + ("SEC. 1. TEST.\n" * 45000)
    html = f"<html><body><pre>{body}</pre></body></html>"
    text = html_to_statute_text(html)
    assert "Public Law 111-148" in text
    assert "Patient Protection and Affordable Care Act" in text
    assert "SEC. 1. TEST." in text


def test_author_advocacy_keeps_left_right_on_same_anchor(tmp_path, monkeypatch):
    left_dir = tmp_path / "data" / "left_lens"; right_dir = tmp_path / "data" / "right_lens"
    left_dir.mkdir(parents=True); right_dir.mkdir(parents=True)
    left = {"candidates": [{"anchor_id":"a1","section_label":"SEC. 1401. PREMIUM TAX CREDIT","claim_class":"INTERPRETATION"}]}
    right = {"candidates": [{"anchor_id":"a1","section_label":"SEC. 1401. PREMIUM TAX CREDIT","claim_class":"INTERPRETATION"}]}
    (left_dir/'aca.json').write_text(json.dumps(left))
    (right_dir/'aca.json').write_text(json.dumps(right))
    monkeypatch.setattr(aca_end_to_end, 'ROOT', tmp_path)
    count = aca_end_to_end.author_advocacy('aca')
    assert count == 1
    l = json.loads((left_dir/'aca.json').read_text())['candidates'][0]
    r = json.loads((right_dir/'aca.json').read_text())['candidates'][0]
    assert l['anchor_id'] == r['anchor_id'] == 'a1'
    assert l['claim_class'] == r['claim_class'] == 'INTERPRETATION'
    assert l['public_interpretation'] != r['public_interpretation']
    assert 'curated proving-ground' in l['public_interpretation_provenance']


def test_pass16_documentation_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'PASS_16_ACA_END_TO_END_TEST.md').exists()
    bat = (root / 'RUN_ACA_END_TO_END.bat').read_text(encoding='utf-8')
    assert 'fetch_aca_source.py' in bat
    assert '-u -m engine.aca_end_to_end' in bat
    assert 'aca_progress.json' in bat
