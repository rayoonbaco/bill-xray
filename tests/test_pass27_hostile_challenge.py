from engine.context_prosecutor import prosecute
from engine.challenge import run_corpus


def test_plain_provision_has_no_context_alarm():
    out = prosecute(claim_text="The Secretary must publish the report annually.", excerpt="The Secretary shall publish the report annually.")
    assert out.severity == "pass"


def test_cross_reference_requires_context_review():
    out = prosecute(claim_text="The Secretary must publish the report annually.", excerpt="The Secretary shall publish the report annually, except that subsection (d) shall apply.")
    assert out.severity in {"warning", "critical"}
    assert out.risks


def test_acknowledged_context_reduces_risk():
    raw = prosecute(claim_text="The Attorney General may waive the rule.", excerpt="Notwithstanding section 7, the Attorney General may waive the rule.")
    acknowledged = prosecute(claim_text="The Attorney General may waive the rule.", excerpt="Notwithstanding section 7, the Attorney General may waive the rule.", why_it_matters="Surrounding section 7 may limit the scope.")
    assert acknowledged.context_score < raw.context_score


def test_adversarial_corpus_passes():
    result = run_corpus()
    assert result["passed"] is True
    assert result["cases"] >= 8
