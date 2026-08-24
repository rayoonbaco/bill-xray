from pathlib import Path


def test_generic_runner_persists_audit_before_release_gate():
    root = Path(__file__).resolve().parents[1]
    text = (root / "engine" / "generic_end_to_end.py").read_text(encoding="utf-8")
    persist = text.index('_atomic_write_json(audit.AUDIT_DIR / f"{bill_id}.json", asdict(aud))')
    gate = text.index('release_ok = syn.analysis_status == "verified" and red.status != "fail" and aud.status != "fail" and chal.status != "fail"')
    assert persist < gate
    assert '_persist_failed_audit_bundle(bill_id, aud)' in text
    assert 'Bill_XRay" / "held_builds"' in text


def test_forensic_tool_can_restore_durable_held_bundle():
    root = Path(__file__).resolve().parents[1]
    text = (root / "tools" / "citation_audit_forensics.py").read_text(encoding="utf-8")
    assert '_restore_durable_bundle' in text
    assert 'held_builds' in text
    assert 'Durable held-build bundle also not found' in text


def test_release_gate_is_not_weakened():
    root = Path(__file__).resolve().parents[1]
    text = (root / "engine" / "generic_end_to_end.py").read_text(encoding="utf-8")
    assert 'aud.status != "fail"' in text
