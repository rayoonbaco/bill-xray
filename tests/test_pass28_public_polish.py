from pathlib import Path
from engine import build_orchestrator as bo

ROOT = Path(__file__).resolve().parents[1]


def test_pass28_public_copy_reflects_hostile_context_gate():
    home = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    bill = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert "Context challenged." in home
    assert "hostile context challenge" in bill
    assert "official bill text" in bill
    assert "enacted text" not in bill


def test_pass28_fetch_progress_knows_pipeline_has_19_stages(monkeypatch, tmp_path):
    monkeypatch.setattr(bo, "PROGRESS_DIR", tmp_path)
    progress = bo._product_progress("aca", "fetching")
    assert progress["total_stages"] == 19


def test_pass28_launcher_banner_is_current():
    launcher = (ROOT / "START_BILL_XRAY.bat").read_text(encoding="utf-8")
    assert "BILL X-RAY - PASS 31" in launcher
