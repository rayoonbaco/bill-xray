from engine import audit


def test_audit_barrel_scan_human_consequence_wiring(monkeypatch):
    calls = []
    monkeypatch.setattr(audit.human_consequence, 'scrutiny_public', lambda candidate, money, power, translation: calls.append((candidate, money, power, translation)) or {'plain': 'Clear human consequence.'})
    indexes = {
        'barrel': {'a1': {'anchor_id': 'a1'}},
        'money': {'a1': {'anchor_id': 'a1'}},
        'power': {'a1': {'anchor_id': 'a1'}},
        'translations': {'a1': {'plain_english': 'Plain translation'}},
        'left': {},
        'right': {},
    }
    out = audit._upstream_expected('barrel_scan', {'text': 'Clear human consequence.'}, 'a1', indexes)
    assert out == 'Clear human consequence.'
    assert len(calls) == 1


def test_audit_module_exposes_canonical_human_consequence_module():
    assert audit.human_consequence.__name__ == 'engine.human_consequence'
