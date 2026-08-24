from pathlib import Path

def test_pass32_home_intentionally_hides_public_search():
    text=Path('templates/index.html').read_text(encoding='utf-8')
    assert 'Search any bill' not in text
    assert 'data-bill-search-input' not in text
    assert '/static/search_bills.js' not in text

def test_bill_page_still_supports_internal_dynamic_builds():
    text=Path('templates/bill.html').read_text(encoding='utf-8')
    assert "bill_build_status.get('buildable')" in text

def test_search_endpoints_remain_available_for_internal_hardening():
    text=Path('app.py').read_text(encoding='utf-8')
    assert '@app.get("/api/search-bills")' in text
    assert '@app.post("/api/search-select", status_code=201)' in text

def test_bill_page_retains_long_build_progress_surface_for_internal_runs():
    text=Path('templates/bill.html').read_text(encoding='utf-8')
    assert 'data-build-session' in text
    assert 'data-progress-percent' in text
    assert 'data-build-name="{{bill.short_title}}"' in text
