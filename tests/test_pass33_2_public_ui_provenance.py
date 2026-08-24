import json
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_question_receipt_controls_are_in_normal_flow():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".citizen-question-list .evidence-trigger{position:static" in css


def test_bill_template_uses_public_source_label_and_cache_busts_pass332():
    template = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert '<span>Source</span><code id="evidence-document"></code>' in template
    assert "/static/style.css?v=33.2" in template
    assert "/static/evidence_drawer.js?v=33.2" in template


def test_public_evidence_payload_never_leaks_local_filesystem_path(monkeypatch):
    import engine.evidence as evidence

    anchor = {
        "bill_id": "demo",
        "anchor_id": "a1",
        "section_label": "SEC. 1",
        "location_marker": "canonical lines 1-2",
        "document_ref": "local:C:/PROJECTS/Bill_XRay/data/source_documents/demo.txt",
        "source_url": "https://www.govinfo.gov/content/pkg/DEMO/html/DEMO.htm",
        "excerpt": "Official excerpt",
        "exact_text": "Official exact text",
    }
    monkeypatch.setattr(evidence, "resolve_anchor", lambda bill_id, anchor_id: anchor)
    payload = evidence.evidence_payload("demo", "a1")
    serialized = json.dumps(payload)
    assert payload["document_ref"] == "Official GovInfo source"
    assert payload["source_navigation"]["document_ref"] == "Official GovInfo source"
    assert "C:/PROJECTS" not in serialized
    assert "local:" not in serialized


def test_all_four_public_exhibit_routes_still_render(monkeypatch):
    monkeypatch.setenv("BILL_XRAY_PUBLIC_MUSEUM", "1")
    import importlib
    import app as app_module

    app_module = importlib.reload(app_module)
    client = TestClient(app_module.app)
    for bill_id in ("aca", "ira", "tcja", "obbba"):
        response = client.get(f"/bill/{bill_id}")
        assert response.status_code == 200
        assert "VERIFIED ANALYSIS" in response.text
        assert "data-evidence-trigger" in response.text
        assert 'id="evidence-drawer"' in response.text


def test_expandable_public_context_and_left_right_text_controls_remain_present():
    template = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert "Outside the bill · official context" in template
    assert "Left | Right | Text" in template
    assert template.count("<details") >= 2


def test_live_tcja_evidence_endpoint_uses_public_safe_source_label(monkeypatch):
    monkeypatch.setenv("BILL_XRAY_PUBLIC_MUSEUM", "1")
    import importlib
    import app as app_module

    app_module = importlib.reload(app_module)
    client = TestClient(app_module.app)
    anchor_index = json.loads((ROOT / "data" / "citation_anchors" / "tcja.json").read_text(encoding="utf-8"))
    anchor_id = anchor_index["anchors"][0]["anchor_id"]
    response = client.get(f"/api/evidence/tcja/{anchor_id}")
    assert response.status_code == 200
    body = response.text
    assert "Official GovInfo source" in body
    assert "C:/PROJECTS" not in body
    assert "local:" not in body
