from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "migrate_showcases_pass31_1.py"
spec = importlib.util.spec_from_file_location("pass31_1_migration", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_verified_persistent_release_is_restored_before_rebuild(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(mod, "persistent_release_status", lambda bill_id: {"state": "verified", "store": str(tmp_path / bill_id)})
    monkeypatch.setattr(mod, "restore_verified_showcase", lambda bill_id: calls.append(("restore", bill_id)) or {"copied": 7})

    existing = {g: True for g in mod.BASE}
    monkeypatch.setattr(mod, "_artifact_path", lambda group, bill_id: type("P", (), {"exists": lambda self: existing[group]})())

    mod.recover_base("aca")
    assert calls == [("restore", "aca")]


def test_missing_base_artifacts_are_rebuilt_in_dependency_order(monkeypatch):
    calls = []
    state = {g: False for g in mod.BASE}
    state["source_documents"] = True

    class FakePath:
        def __init__(self, group): self.group = group
        def exists(self): return state[self.group]

    monkeypatch.setattr(mod, "persistent_release_status", lambda bill_id: {"state": "missing"})
    monkeypatch.setattr(mod, "_artifact_path", lambda group, bill_id: FakePath(group))

    def builder(group):
        def _fn(*args, **kwargs):
            calls.append(group)
            state[group] = True
            return object()
        return _fn

    monkeypatch.setattr(mod.ingest, "ingest_manifest_bill", builder("ingested"))
    monkeypatch.setattr(mod.segment, "segment_ingested_bill", builder("segmented"))
    monkeypatch.setattr(mod.citations, "build_anchor_index", builder("citation_anchors"))
    monkeypatch.setattr(mod.translator, "translate_bill", builder("translations"))
    monkeypatch.setattr(mod.money, "extract_bill", builder("money"))
    monkeypatch.setattr(mod.power, "extract_bill", builder("power"))

    mod.recover_base("aca")
    assert calls == ["ingested", "segmented", "citation_anchors", "translations", "money", "power"]


def test_failed_pass31_chain_does_not_publish(monkeypatch):
    monkeypatch.setattr(mod, "inventory", lambda bill_id: {"bill_id": bill_id, "persistent": {"state": "verified", "store": "x"}, "local": {g: True for g in mod.BASE + mod.DEPENDENT}})
    monkeypatch.setattr(mod, "_print_inventory", lambda report: None)
    monkeypatch.setattr(mod, "recover_base", lambda bill_id: None)
    monkeypatch.setattr(mod, "rebuild_pass31_dependents", lambda bill_id: {"release_ok": False})
    published = []
    monkeypatch.setattr(mod, "publish_verified_showcase", lambda bill_id: published.append(bill_id))
    try:
        mod.migrate_one("aca")
        assert False, "expected safe stop"
    except RuntimeError as exc:
        assert "remains untouched" in str(exc)
    assert published == []


def test_successful_pass31_chain_publishes_only_after_gate(monkeypatch):
    events = []
    monkeypatch.setattr(mod, "inventory", lambda bill_id: {"bill_id": bill_id, "persistent": {"state": "verified", "store": "x"}, "local": {g: True for g in mod.BASE + mod.DEPENDENT}})
    monkeypatch.setattr(mod, "_print_inventory", lambda report: None)
    monkeypatch.setattr(mod, "recover_base", lambda bill_id: events.append("recover"))
    monkeypatch.setattr(mod, "rebuild_pass31_dependents", lambda bill_id: events.append("gates") or {"release_ok": True, "analysis_status": "verified"})
    monkeypatch.setattr(mod, "publish_verified_showcase", lambda bill_id: events.append("publish") or {"store": "persistent", "status": "published"})
    result = mod.migrate_one("aca")
    assert events == ["recover", "gates", "publish"]
    assert result["published"]["status"] == "published"


def test_bat_and_pass_doc_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "MIGRATE_SHOWCASES_PASS31_1.bat").exists()
    assert (root / "PASS_31_1_DURABLE_INTERMEDIATE_RECOVERY_ATOMIC_MIGRATION.md").exists()
