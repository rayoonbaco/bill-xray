import json
from pathlib import Path

from engine import showcase_release as sr


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.write_text(str(payload), encoding="utf-8")


def _seed_verified_working_tree(root: Path, bill_id: str = "aca"):
    data = root / "data"
    source = data / "source_documents" / f"{bill_id}.txt"
    _write(source, "official statute text")
    sha = sr._sha256(source)
    _write(data / "ingested" / f"{bill_id}.json", {"source_sha256": sha})
    _write(data / "citation_anchors" / f"{bill_id}.json", {"bill_id": bill_id, "anchors": []})
    _write(data / "analyses" / f"{bill_id}.json", {"analysis_status": "verified", "panels": []})
    _write(data / "red_team" / f"{bill_id}.json", {"status": "pass"})
    _write(data / "citation_audit" / f"{bill_id}.json", {"status": "pass"})
    _write(data / "challenge" / f"{bill_id}.json", {"status": "pass"})
    _write(data / "end_to_end" / f"{bill_id}.json", {"analysis_status": "verified"})
    _write(data / "analysis_cache" / f"{bill_id}.json", {
        "source_sha256": sha,
        "analysis_status": "verified",
        "public_analysis_version": sr.COMPATIBLE_PUBLIC_ANALYSIS_VERSION,
    })
    _write(data / "external_evidence" / f"{bill_id}.json", {"status": "partial"})
    _write(data / "consequence" / f"{bill_id}.json", {"status": "generated"})


def test_verified_working_showcase_is_adopted_into_persistent_store(tmp_path, monkeypatch):
    root = tmp_path / "app"
    store = tmp_path / "persistent"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    _seed_verified_working_tree(root)
    result = sr.restore_verified_showcase("aca")
    assert result["state"] == "verified"
    assert result.get("adopted_from_working_folder") is True
    assert (store / "aca" / "release_manifest.json").exists()


def test_persistent_release_restores_after_application_folder_replacement(tmp_path, monkeypatch):
    root = tmp_path / "app"
    store = tmp_path / "persistent"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    _seed_verified_working_tree(root)
    sr.publish_verified_showcase("aca")
    # Simulate replacing the application folder and losing generated data.
    for rel, path in sr._artifact_specs("aca"):
        if path.exists():
            path.unlink()
    result = sr.restore_verified_showcase("aca")
    assert result["state"] == "verified"
    assert result["restored"] is True
    assert (root / "data" / "analyses" / "aca.json").exists()
    assert (root / "data" / "source_documents" / "aca.txt").exists()


def test_corrupt_persistent_release_fails_closed(tmp_path, monkeypatch):
    root = tmp_path / "app"
    store = tmp_path / "persistent"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    _seed_verified_working_tree(root)
    sr.publish_verified_showcase("aca")
    (store / "aca" / "source_documents" / "aca.txt").write_text("tampered", encoding="utf-8")
    for _, path in sr._artifact_specs("aca"):
        if path.exists():
            path.unlink()
    result = sr.restore_verified_showcase("aca")
    assert result["state"] == "invalid"
    assert result["restored"] is False
    assert "checksum" in result["reason"]


def test_launcher_uses_free_port_selector_and_cache_check():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "START_BILL_XRAY.bat").read_text(encoding="utf-8")
    assert "showcase_cache_check.py" in launcher
    assert "start_runtime.py" in launcher
    runtime = (root / "tools" / "start_runtime.py").read_text(encoding="utf-8")
    assert "choose_free_port" in runtime
    assert "cannot hijack the browser" in runtime
