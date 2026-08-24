from __future__ import annotations

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "migrate_showcases_pass31_1.py"
spec = importlib.util.spec_from_file_location("pass31_1_1_migration", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


def test_segmented_logical_name_maps_to_real_segments_directory():
    path = mod._artifact_path("segmented", "aca")
    assert path.parent.name == "segments"
    assert path.name == "aca.json"


def test_segmentation_handshake_requires_positive_blocks(monkeypatch, tmp_path):
    path = tmp_path / "data" / "segments" / "aca.json"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(mod, "_artifact_path", lambda group, bill_id: path)

    path.write_text(json.dumps({"segment_count": 0, "segments": []}), encoding="utf-8")
    failed = mod._validate_recovered_artifact("segmented", "aca")
    assert failed["valid"] is False

    path.write_text(json.dumps({"segment_count": 2, "segments": [{"x": 1}, {"x": 2}]}), encoding="utf-8")
    passed = mod._validate_recovered_artifact("segmented", "aca")
    assert passed["valid"] is True
    assert "segment_count=2" in passed["detail"]


def test_recovered_segmentation_is_rediscovered_immediately(monkeypatch, tmp_path):
    root = tmp_path
    seg_path = root / "data" / "segments" / "aca.json"
    monkeypatch.setattr(mod, "_artifact_path", lambda group, bill_id: seg_path if group == "segmented" else root / "data" / group / f"{bill_id}.json")

    def build():
        seg_path.parent.mkdir(parents=True, exist_ok=True)
        seg_path.write_text(json.dumps({"segment_count": 1, "segments": [{"segment_id": "s1"}]}), encoding="utf-8")
        return object()

    result = mod._run_if_missing("segmented", "aca", build, "structural segmentation")
    assert result is not None
    assert seg_path.exists()
    assert mod._validate_recovered_artifact("segmented", "aca")["valid"] is True
