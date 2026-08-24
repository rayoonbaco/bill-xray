from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_uses_shared_bootstrap_and_waits_for_health():
    launcher = (ROOT / "START_BILL_XRAY.bat").read_text(encoding="utf-8")
    assert "tools\\bootstrap_env.bat" in launcher
    assert "tools\\start_runtime.py" in launcher
    runtime = (ROOT / "tools" / "start_runtime.py").read_text(encoding="utf-8")
    assert "uvicorn" in runtime and "app:app" in runtime
    assert "webbrowser.open" in runtime


def test_shared_bootstrap_rejects_314_and_prefers_311_to_313():
    bootstrap = (ROOT / "tools" / "bootstrap_env.bat").read_text(encoding="utf-8")
    assert "3.11" in bootstrap
    assert "3.12" in bootstrap
    assert "3.13" in bootstrap
    assert "3.14" in bootstrap
    assert "rmdir /s /q" in bootstrap
    assert "--only-binary=:all:" in bootstrap
    assert "Rust or Visual Studio" in bootstrap


def test_smoke_test_uses_same_bootstrap_as_real_launcher():
    smoke = (ROOT / "SMOKE_TEST_BILL_XRAY.bat").read_text(encoding="utf-8")
    assert "tools\\bootstrap_env.bat" in smoke
    assert "tools\\smoke_test.py" in smoke


def test_bill_screen_has_top_and_bottom_library_buttons():
    template = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert template.count("Back to Bill X-Ray") >= 2
    assert template.count('href="/"') >= 2


def test_pass7_compact_desktop_layout_is_encoded_without_huge_type():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    home = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    bill = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert 'class="page-home pass29-home"' in home
    assert 'class="page-bill pass29-bill"' in bill
    assert "overflow-y:hidden" in css
    assert "library-grid{grid-template-columns:repeat(4" in css
    assert "6.8rem" not in css
