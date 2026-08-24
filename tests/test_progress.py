import json
from engine.progress import StageTracker


def test_stage_tracker_writes_durable_progress_and_timings(tmp_path):
    tracker = StageTracker("demo", tmp_path, 2)
    result = tracker.run("one", "First stage", lambda: 3, lambda x: f"{x} items")
    assert result == 3
    payload = json.loads((tmp_path / "demo_progress.json").read_text())
    assert payload["state"] == "running"
    assert payload["completed_stages"] == 1
    assert payload["stages"][0]["key"] == "one"
    assert payload["stages"][0]["summary"] == "3 items"
    final = tracker.finish("complete")
    assert final["state"] == "complete"


def test_stage_tracker_preserves_failed_stage(tmp_path):
    tracker = StageTracker("demo", tmp_path, 1)
    try:
        tracker.run("bad", "Bad stage", lambda: (_ for _ in ()).throw(ValueError("boom")))
    except ValueError:
        pass
    payload = json.loads((tmp_path / "demo_progress.json").read_text())
    assert payload["state"] == "failed"
    assert payload["stages"][-1]["status"] == "failed"
    assert "boom" in payload["stages"][-1]["error"]
