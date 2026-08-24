import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_four_curated_showcases_are_static_catalog_entries():
    bills = json.loads((ROOT / 'data' / 'bills.json').read_text(encoding='utf-8'))
    by_id = {row['id']: row for row in bills}
    assert set(('aca','ira','tcja','obbba')).issubset(by_id)
    assert by_id['ira']['status'] == 'Demo target'
    assert by_id['tcja']['status'] == 'Demo target'


def test_ira_and_tcja_have_official_public_law_manifest_entries():
    manifest = json.loads((ROOT / 'data' / 'source_manifest.json').read_text(encoding='utf-8'))
    by_id = {row['bill_id']: row for row in manifest['bills']}
    assert by_id['ira']['law_number'] == 'Public Law 117-169'
    assert by_id['tcja']['law_number'] == 'Public Law 115-97'
    assert 'govinfo.gov' in by_id['ira']['source_url']
    assert 'govinfo.gov' in by_id['tcja']['source_url']


def test_ira_and_tcja_use_normal_generic_pipeline_not_force_publish():
    text = (ROOT / 'engine' / 'build_orchestrator.py').read_text(encoding='utf-8')
    assert '"ira": BuilderSpec("ira", ensure_ira_source, lambda: run_generic("ira"))' in text
    assert '"tcja": BuilderSpec("tcja", ensure_tcja_source, lambda: run_generic("tcja"))' in text
    show = (ROOT / 'engine' / 'showcase_release.py').read_text(encoding='utf-8')
    assert 'SHOWCASE_IDS = ("aca", "ira", "tcja", "obbba")' in show


def test_generic_runner_accepts_curated_manifest_bills_without_search_registration():
    text = (ROOT / 'engine' / 'generic_end_to_end.py').read_text(encoding='utf-8')
    assert 'manifest_entry = ingest.load_source_manifest().get(bill_id)' in text
    assert 'No registered or curated bill' in text
