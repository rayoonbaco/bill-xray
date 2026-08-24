from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_demo_path_exists_and_preserves_reading_order():
    text=(ROOT/'templates'/'bill.html').read_text(encoding='utf-8')
    expected=['href="#core"','href="#money"','href="#power"','href="#attention"','href="#questions"','href="#receipts"']
    assert '90-SECOND X-RAY' in text
    positions=[text.index(x) for x in expected]
    assert positions == sorted(positions)
    for anchor in ['id="core"','id="money"','id="power"','id="attention"','id="questions"','id="receipts"']:
        assert anchor in text

def test_pass316_release_fingerprint_and_assets():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    runtime=(ROOT/'tools'/'start_runtime.py').read_text(encoding='utf-8')
    start=(ROOT/'START_BILL_XRAY.bat').read_text(encoding='utf-8')
    index=(ROOT/'templates'/'index.html').read_text(encoding='utf-8')
    bill=(ROOT/'templates'/'bill.html').read_text(encoding='utf-8')
    assert '"surface_pass": "31.6"' in app
    assert 'EXPECTED_SURFACE_PASS = "31.6"' in runtime
    assert 'Pass 31.6' in runtime
    assert 'PASS 31.6' in start
    assert 'v=31.6' in index and 'v=31.6' in bill

def test_demo_polish_does_not_add_analysis_controls():
    text=(ROOT/'templates'/'bill.html').read_text(encoding='utf-8')
    nav=text[text.index('<nav class="demo-path"'):text.index('</nav>', text.index('<nav class="demo-path"'))]
    assert '<button' not in nav
    assert 'data-build' not in nav
    assert 'data-evidence' not in nav
