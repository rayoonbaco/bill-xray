from tools.wait_and_open import health_url_for_target


def test_report_target_health_checks_server_root_not_report_path():
    assert (
        health_url_for_target("http://127.0.0.1:8000/bill/obbba")
        == "http://127.0.0.1:8000/api/health"
    )


def test_aca_report_target_uses_same_root_health_endpoint():
    assert (
        health_url_for_target("http://127.0.0.1:8000/bill/aca")
        == "http://127.0.0.1:8000/api/health"
    )


def test_home_target_health_checks_server_root():
    assert (
        health_url_for_target("http://127.0.0.1:8000/")
        == "http://127.0.0.1:8000/api/health"
    )
