from pathlib import Path

from engine import citizen_view


def _cite(anchor="a1"):
    return [{"anchor_id": anchor}]


def test_verified_language_cannot_be_misread_as_bill_endorsement():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert "VERIFIED ANALYSIS" in html
    assert "not an endorsement of the bill" in html
    assert "VERIFIED X-RAY" not in html


def test_attention_score_is_not_presented_as_probability_of_wrongdoing():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert "Attention {{claim.scrutiny_score|round|int}}/100" in html
    assert "not a probability of corruption, illegality, or fraud" in html
    assert "/100 scrutiny" not in html


def test_unresolved_fiscal_roles_remain_unresolved_instead_of_guessed():
    analysis = {
        "panels": [
            {"key": "follow_the_money", "claims": [{
                "text": "$6,000,000,000 to carry out this section.",
                "fiscal_amount": "$6,000,000,000",
                "fiscal_purpose": "carry out this section",
                "fiscal_recipient": "fiscal year 2014",
                "citations": _cite(),
            }]}
        ]
    }
    card = citizen_view.build(analysis)["money"][0]
    assert card["citizen_purpose"] == "Not clear from this clause alone."
    assert card["citizen_recipient"] == "Not clear from this clause alone."


def test_public_cards_keep_receipt_controls_and_canonical_anchor_contract():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert 'data-evidence-trigger' in html
    assert 'data-anchor-id="{{claim.citations[0].anchor_id}}"' in html
    assert "THE RECEIPTS" in html
    assert "No important factual claim without a path back to the original language." in html


def test_no_controversy_is_manufactured_when_scrutiny_is_empty():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert "No scrutiny candidate survived the referee." in html
    assert "does not manufacture controversy" in html


def test_deeper_context_remains_optional_progressive_disclosure():
    html = Path("templates/bill.html").read_text(encoding="utf-8")
    assert '<details class="pass30-external pass31-external">' in html
    assert '<details class="deep-dive">' in html
    assert "Left | Right | Text" in html


def test_surface_version_is_explicit_without_breaking_stable_engine_contract():
    app = Path("app.py").read_text(encoding="utf-8")
    bill = Path("templates/bill.html").read_text(encoding="utf-8")
    index = Path("templates/index.html").read_text(encoding="utf-8")
    launcher = Path("tools/start_runtime.py").read_text(encoding="utf-8")
    assert '"surface_pass": "31.5"' in app
    assert "v=31.5" in bill
    assert "v=31.6" in index
    assert "Pass 31.5" in launcher
