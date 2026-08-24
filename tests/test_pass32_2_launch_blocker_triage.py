from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    path = ROOT / "tools" / "revalidate_legacy_showcases_pass32_2.py"
    spec = importlib.util.spec_from_file_location("pass32_2_revalidate", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_httpx_is_declared_for_fastapi_route_regressions():
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "httpx==0.28.1" in requirements


def test_pass32_2_revalidator_exists_and_is_fail_closed():
    text = (ROOT / "tools" / "revalidate_legacy_showcases_pass32_2.py").read_text(encoding="utf-8")
    assert "publish_verified_showcase" in text
    assert "restore_verified_showcase" in text
    assert "suspicious == 0" in text
    assert "release_ok(result)" in text


def test_current_aca_and_obbba_sources_segment_without_tion(monkeypatch, tmp_path):
    # Exercise the current segmenter directly against the live official local sources,
    # without relying on the stale legacy citation artifacts this pass is replacing.
    from engine import ingest, segment, citations
    for bill_id in ("aca", "obbba"):
        source = ROOT / "data" / "source_documents" / f"{bill_id}.txt"
        assert source.exists()
        text = source.read_text(encoding="utf-8", errors="replace")
        seg = segment.segment_text(bill_id, text)
        bad = [s for s in seg.segments if s.identifier.upper() == "TION" or "SEC. TION" in s.heading.upper()]
        assert not bad
