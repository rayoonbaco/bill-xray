from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_pass32_home_uses_large_four_exhibit_surface_without_showcase_build_buttons():
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'pass291-home' in html
    assert 'EXHIBIT NOT PREBUILT' in html
    assert 'Prebuild required before launch' in html
    assert 'View completed X-Ray' in html
    showcase = html.split('<section class="showcase')[1]
    assert '<button class="card-action showcase-action"' not in showcase


def test_pass32_home_is_museum_not_live_build_theater():
    home = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    bill = (ROOT / 'templates' / 'bill.html').read_text(encoding='utf-8')
    assert 'data-progress-all-stages' not in home
    assert 'data-progress-all-stages' in bill
    assert 'CURATED PUBLIC EXHIBITS' in home


def test_pass32_release_marker_and_prebuild_helper_present():
    from app import app
    client = TestClient(app)
    payload = client.get('/api/health').json()
    assert payload['pass'] == '31'
    assert payload['release'] == '31'
    assert (ROOT / 'PREBUILD_SHOWCASES.bat').exists()
