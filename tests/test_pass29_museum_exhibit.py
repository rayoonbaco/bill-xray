from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_pass32_home_is_focused_on_four_curated_showcases_without_public_search():
    from app import app
    client = TestClient(app)
    html = client.get('/').text
    assert 'Search any bill' not in html
    for title in ('Affordable Care Act','Inflation Reduction Act','Tax Cuts and Jobs Act','One Big Beautiful Bill Act'):
        assert title in html
    assert 'Four major laws. One evidentiary standard.' in html
    assert 'Choose a law to X-Ray' in html


def test_pass32_home_removes_search_runtime_from_public_surface():
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'data-bill-search-input' not in html
    assert '/static/search_bills.js' not in html
    assert 'LIVE DEEP READ · 19 CHECKS' not in html


def test_pass29_result_page_leads_with_essence_money_and_scrutiny():
    html = (ROOT / 'templates' / 'bill.html').read_text(encoding='utf-8')
    assert 'The 3 things to understand first' in html
    assert 'Where does the money go?' in html
    assert 'What stands out?' in html
    assert 'Who benefits, who pays, who gets power?' in html
    assert '<details class="deep-dive">' in html


def test_pass32_assets_are_current():
    from app import app
    client = TestClient(app)
    assert client.get('/api/health').json()['pass'] == '31'
    home = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    bill = (ROOT / 'templates' / 'bill.html').read_text(encoding='utf-8')
    assert '/static/style.css?v=31.6' in home
    assert '/static/evidence_drawer.js?v=33.2' in bill
