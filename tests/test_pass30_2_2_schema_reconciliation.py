import json
from pathlib import Path

from engine import showcase_release as sr


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload), encoding='utf-8')
    else:
        path.write_text(str(payload), encoding='utf-8')


def _seed_realistic(root: Path, bill_id='aca', *, red='pass', challenge='pass', alternate=False):
    data = root / 'data'
    source = data / 'source_documents' / f'{bill_id}.txt'
    _write(source, 'official statute text')
    sha = sr._sha256(source)
    _write(data / 'ingested' / f'{bill_id}.json', {'source_sha256': sha})
    _write(data / 'citation_anchors' / f'{bill_id}.json', {'bill_id': bill_id, 'anchors': [{'id':'x'}]})
    _write(data / 'analyses' / f'{bill_id}.json', {'analysis_status': 'verified', 'panels': []})
    if alternate:
        _write(data / 'red_team' / f'{bill_id}.json', {'status': red, 'critical_count': 0})
        _write(data / 'citation_audit' / f'{bill_id}.json', {'status': 'pass', 'critical_count': 0, 'public_claim_count': 15, 'citations_checked': 15})
        _write(data / 'challenge' / f'{bill_id}.json', {'status': challenge, 'blocker_count': 0})
        _write(data / 'end_to_end' / f'{bill_id}.json', {'analysis_status':'verified','red_team_status':red,'citation_audit_status':'pass','challenge_status':challenge,'source_sha256':sha,'public_claims':15,'citations_reverified':15})
    else:
        _write(data / 'red_team' / f'{bill_id}.json', {'status': red, 'critical_count': 0})
        _write(data / 'citation_audit' / f'{bill_id}.json', {'status': 'pass', 'critical_count': 0, 'public_claim_count': 15, 'citations_checked': 15})
        _write(data / 'challenge' / f'{bill_id}.json', {'status': challenge, 'blocker_count': 0})
        _write(data / 'end_to_end' / f'{bill_id}.json', {'analysis_status':'verified','source_sha256':sha,'red_team_status':red,'citation_audit_status':'pass','challenge_status':challenge,'public_claims':15,'citations_reverified':15})
    return sha


def test_realistic_301_artifact_set_adopts_without_rebuild(tmp_path, monkeypatch):
    root = tmp_path / 'Existing Bill XRay'
    store = tmp_path / 'Persistent Store'
    monkeypatch.setattr(sr, 'ROOT', root)
    monkeypatch.setenv('BILL_XRAY_SHOWCASE_STORE', str(store))
    _seed_realistic(root)
    report = sr.reconcile_working_release('aca')
    assert report['adoptable'] is True
    result = sr.restore_verified_showcase('aca')
    assert result['restored'] is True
    assert result.get('adopted_from_working_folder') is True
    assert (store / 'aca' / 'release_manifest.json').exists()


def test_summary_key_variants_reconcile_but_physical_gate_artifacts_remain_required(tmp_path, monkeypatch):
    root = tmp_path / 'App'
    monkeypatch.setattr(sr, 'ROOT', root)
    _seed_realistic(root, alternate=True)
    assert sr.reconcile_working_release('aca')['adoptable'] is True
    (root/'data'/'challenge'/'aca.json').unlink()
    report = sr.reconcile_working_release('aca')
    assert report['adoptable'] is False
    assert 'challenge' in report['missing_physical_artifacts']


def test_failed_red_team_cannot_be_overridden_by_verified_summary(tmp_path, monkeypatch):
    root = tmp_path / 'App'
    monkeypatch.setattr(sr, 'ROOT', root)
    _seed_realistic(root, red='fail')
    # Deliberately contradictory summary.
    e2e = root/'data'/'end_to_end'/'aca.json'
    payload = json.loads(e2e.read_text())
    payload['red_team_status'] = 'pass'
    e2e.write_text(json.dumps(payload))
    report = sr.reconcile_working_release('aca')
    assert report['adoptable'] is False
    assert 'red_team_passed' in report['failures']


def test_missing_source_and_anchors_are_never_blessed(tmp_path, monkeypatch):
    root = tmp_path / 'App'
    monkeypatch.setattr(sr, 'ROOT', root)
    _seed_realistic(root)
    (root/'data'/'source_documents'/'aca.txt').unlink()
    (root/'data'/'citation_anchors'/'aca.json').unlink()
    report = sr.reconcile_working_release('aca')
    assert report['adoptable'] is False
    assert set(report['missing_physical_artifacts']) >= {'official_source','citation_anchors'}


def test_persistent_release_corruption_fails_closed(tmp_path, monkeypatch):
    root = tmp_path / 'App'
    store = tmp_path / 'Store'
    monkeypatch.setattr(sr, 'ROOT', root)
    monkeypatch.setenv('BILL_XRAY_SHOWCASE_STORE', str(store))
    _seed_realistic(root)
    sr.publish_verified_showcase('aca')
    target = store/'aca'/'source_documents'/'aca.txt'
    target.write_text('tampered')
    status = sr.persistent_release_status('aca')
    assert status['state'] == 'invalid'
    assert status['reason'].startswith('checksum:')
