from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prebuild_bat_self_bootstraps_and_sets_project_root():
    text = (ROOT / 'PREBUILD_SHOWCASES.bat').read_text(encoding='utf-8')
    assert 'tools\\bootstrap_env.bat' in text
    assert 'set "PYTHONPATH=%ROOT%;%PYTHONPATH%"' in text
    assert 'engine.build_orchestrator' in text


def test_prebuild_python_repairs_direct_script_import_path():
    text = (ROOT / 'tools' / 'prebuild_showcases.py').read_text(encoding='utf-8')
    assert 'Path(__file__).resolve().parents[1]' in text
    assert 'sys.path.insert(0, str(ROOT))' in text
    assert 'from engine.build_orchestrator import build_status, start_build' in text


def test_prebuild_preserves_release_gates_and_attempts_all_four():
    text = (ROOT / 'tools' / 'prebuild_showcases.py').read_text(encoding='utf-8')
    for pair in (
        '("aca", "Affordable Care Act")',
        '("ira", "Inflation Reduction Act")',
        '("tcja", "Tax Cuts and Jobs Act")',
        '("obbba", "One Big Beautiful Bill Act")',
    ):
        assert pair in text
    assert 'REVIEW HOLD' in text
    assert 'Nothing was force-published.' in text
    assert '4 / 4 SHOWCASES READY' in text
    assert 'if not ok:' not in text
