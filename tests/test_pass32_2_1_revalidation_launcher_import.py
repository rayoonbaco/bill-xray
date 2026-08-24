from __future__ import annotations

import os
import runpy
from pathlib import Path


def test_revalidator_bootstraps_project_root_when_launched_from_elsewhere(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "tools" / "revalidate_legacy_showcases_pass32_2.py"
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        namespace = runpy.run_path(str(script), run_name="pass32_2_1_import_probe")
    finally:
        os.chdir(old_cwd)
    assert namespace["ROOT"] == Path(__file__).resolve().parents[1]
    assert "run_aca" in namespace
    assert "run_obbba" in namespace
