from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cbo_refresh_script_imports_engine_from_non_project_cwd(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "tools" / "refresh_cbo_pass31_6_1.py"
    result = subprocess.run(
        [sys.executable, str(script), "--import-check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS 31.6.1.1 import check: OK" in result.stdout
    assert f"Project root: {root}" in result.stdout
