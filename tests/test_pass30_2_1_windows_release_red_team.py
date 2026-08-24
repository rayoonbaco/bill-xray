import json
import socket
from pathlib import Path

from engine import showcase_release as sr
from tools.start_runtime import choose_free_port


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.write_text(str(payload), encoding="utf-8")


def _seed_verified(root: Path, bill_id: str):
    data = root / "data"
    source = data / "source_documents" / f"{bill_id}.txt"
    _write(source, "official statute text")
    sha = sr._sha256(source)
    _write(data / "ingested" / f"{bill_id}.json", {"sha256": sha})
    _write(data / "citation_anchors" / f"{bill_id}.json", {"bill_id": bill_id, "anchors": []})
    _write(data / "analyses" / f"{bill_id}.json", {"analysis_status": "verified"})
    _write(data / "red_team" / f"{bill_id}.json", {"status": "pass", "critical_count": 0})
    _write(data / "citation_audit" / f"{bill_id}.json", {"status": "pass", "critical_count": 0, "public_claim_count": 15, "citations_checked": 15})
    _write(data / "challenge" / f"{bill_id}.json", {"status": "pass", "blocker_count": 0})
    _write(data / "end_to_end" / f"{bill_id}.json", {"analysis_status": "verified", "source_sha256": sha})


def test_chalkboard_clean_install_has_no_false_verified_showcase(tmp_path, monkeypatch):
    root = tmp_path / "Clean Install" / "Bill XRay"
    store = tmp_path / "Local App Data" / "Bill XRay" / "showcase releases"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    result = sr.restore_verified_showcase("aca")
    assert result["restored"] is False
    assert result["state"] == "missing"


def test_chalkboard_upgrade_adopts_existing_verified_artifacts_without_cache_manifest(tmp_path, monkeypatch):
    root = tmp_path / "Existing Project"
    store = tmp_path / "Persistent Store"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    _seed_verified(root, "aca")
    result = sr.restore_verified_showcase("aca")
    assert result["restored"] is True
    assert result.get("adopted_from_working_folder") is True
    assert (store / "aca" / "release_manifest.json").exists()


def test_chalkboard_stale_server_forces_different_port():
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    occupied = blocker.getsockname()[1]
    blocker.listen(1)
    try:
        chosen = choose_free_port(occupied, 2)
        assert chosen == occupied + 1
    finally:
        blocker.close()


def test_chalkboard_persistent_cache_survives_project_replacement(tmp_path, monkeypatch):
    root = tmp_path / "App Folder"
    store = tmp_path / "Persistent Store"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    _seed_verified(root, "aca")
    sr.publish_verified_showcase("aca")
    # Simulate total generated-data loss during an app replacement.
    import shutil
    shutil.rmtree(root / "data")
    restored = sr.restore_verified_showcase("aca")
    assert restored["restored"] is True
    assert (root / "data" / "analyses" / "aca.json").exists()


def test_chalkboard_partial_corruption_never_blesses_bad_exhibit(tmp_path, monkeypatch):
    root = tmp_path / "App"
    store = tmp_path / "Persistent"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    _seed_verified(root, "aca")
    _seed_verified(root, "obbba")
    sr.publish_verified_showcase("aca")
    sr.publish_verified_showcase("obbba")
    # Corrupt only OBBBA and remove local artifacts to force persistent validation.
    (store / "obbba" / "source_documents" / "obbba.txt").write_text("tampered", encoding="utf-8")
    import shutil
    shutil.rmtree(root / "data")
    aca = sr.restore_verified_showcase("aca")
    obbba = sr.restore_verified_showcase("obbba")
    assert aca["restored"] is True
    assert obbba["restored"] is False
    assert obbba["state"] == "invalid"


def test_chalkboard_windows_paths_with_spaces_are_normal_paths(tmp_path, monkeypatch):
    root = tmp_path / "Ray Gomez Projects" / "Bill XRay 30.2.2"
    store = tmp_path / "Local App Data" / "Bill XRay" / "showcase releases"
    monkeypatch.setattr(sr, "ROOT", root)
    monkeypatch.setenv("BILL_XRAY_SHOWCASE_STORE", str(store))
    _seed_verified(root, "aca")
    result = sr.restore_verified_showcase("aca")
    assert result["restored"] is True
    assert " " in str(store)
