import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_render_blueprint_runs_curated_museum():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "uvicorn app:app --host 0.0.0.0 --port $PORT" in text
    assert "healthCheckPath: /api/health" in text
    assert 'BILL_XRAY_PUBLIC_MUSEUM' in text
    assert 'value: "1"' in text


def test_all_four_curated_analyses_are_verified():
    import json
    for bill_id in ("aca", "ira", "tcja", "obbba"):
        payload = json.loads((ROOT / "data" / "analyses" / f"{bill_id}.json").read_text(encoding="utf-8"))
        assert payload.get("analysis_status") == "verified"
        assert any(panel.get("claims") for panel in payload.get("panels", []))


def test_public_museum_disables_search_and_build_mutations(monkeypatch):
    monkeypatch.setenv("BILL_XRAY_PUBLIC_MUSEUM", "1")
    import app as app_module
    app_module = importlib.reload(app_module)
    client = TestClient(app_module.app)
    assert client.get("/api/search-bills?q=health").status_code == 404
    assert client.post("/api/build/aca").status_code == 404
    assert client.post("/api/search-select", json={"search_token":"123456", "package_id":"BILLS-118hr171ih"}).status_code == 404
    assert client.get("/").status_code == 200
    for bill_id in ("aca", "ira", "tcja", "obbba"):
        response = client.get(f"/bill/{bill_id}")
        assert response.status_code == 200
        assert "VERIFIED ANALYSIS" in response.text
