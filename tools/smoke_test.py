"""One-click smoke test for every Bill X-Ray pass implemented so far."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"


def fetch(path: str, timeout: float = 3.0) -> tuple[int, str]:
    with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")


def wait_for_server(process: subprocess.Popen, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early with code {process.returncode}")
        try:
            status, body = fetch("/api/health", timeout=1.0)
            if status == 200 and json.loads(body).get("status") == "ok":
                return
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Server did not become healthy: {last_error}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    print("[1/35] PASS 1 - schemas and evidence rules")
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=ROOT, check=False
    )
    if test_result.returncode != 0:
        return test_result.returncode

    print("[2/35] PASS 2 - local TXT/XML ingestion contract")
    print("[3/35] PASS 3 - deterministic structural segmentation")
    print("[4/35] PASS 4 - exact citation anchors and drift detection")
    print("[5/35] PASS 5 - evidence-preserving plain-English translator")
    print("[6/35] PASS 6 - source-bound money extractor")
    print("[7/35] PASS 7 - source-bound power / authority extractor")
    print("[8/35] PASS 8 - evidence-bound Barrel Scan candidate detector")
    print("[9/35] PASS 9 - dynamic provision-level topic-expert review")
    print("[10/35] PASS 10 - source-bound progressive advocacy review")
    print("[11/35] PASS 11 - source-bound conservative advocacy review")
    print("[12/35] PASS 12 - paired Investigative Skeptic review")
    print("[13/35] PASS 13 - Neutral Referee evidence adjudication")
    print("[14/35] PASS 14 - referee-bound five-panel public synthesis")
    print("[15/35] PASS 15 - one-click evidence drawer and source navigation")
    print("[16/35] PASS 16 - ACA full-chain proving-ground harness")
    print("[17/35] PASS 17 - OBBBA full-chain proving-ground harness + shared progress checkpoints")
    print("[18/35] PASS 18 - political-bias + selection-quality red team")
    print("[19/35] PASS 19 - hallucination + citation release audit")
    print("[20/35] PASS 19.2 - LEFT | RIGHT | TEXT lane diagnosis + repair")
    print("[21/35] PASS 19.3 - independent same-anchor TEXT referee construction")
    print("[22/35] PASS 20 - V1 public polish, favicon, and deployment readiness")
    print("[23/35] PASS 21 - product-facing build orchestrator + ACA parity")
    print("[24/35] PASS 21.1 - weighted build progress + persistent verified cache")
    print("[25/35] PASS 21.3 - cache forensics + historical verified-build adoption")
    print("[26/35] PASS 22 - official GovInfo search, exact-version selection, and generic build handoff")
    print("[27/35] PASS 23 - plain-English public-intelligence ranking")
    print("[28/35] PASS 24 - concrete So What intelligence and public-effect ranking")
    print("[29/35] PASS 25 - structured source-bound deep comprehension")
    print("[30/35] PASS 25.1 - comprehension challenge gate and weak-explanation suppression")
    print("[31/43] PASS 26 - concrete money flow, affected parties, and substantive paired lenses")
    print("[32/43] PASS 27 - hostile multi-bill challenge + Context Prosecutor")
    print("[33/43] PASS 28 - hostile-test fixes + public-product polish")
    print("[34/43] PASS 28.1 - materiality ranking, legalese suppression, and hold safety")
    print("[35/43] PASS 28.2 - fiscal materiality comparator reconciled with selector")
    print("[36/43] PASS 29 - focused museum-exhibit home + answer-first report")
    print("[37/43] PASS 29.1 - prebuilt exhibits + full-screen investigation theater")
    print("[38/43] PASS 30 - external evidence + consequence engine")
    print("[39/43] PASS 30.1 - canonical fiscal-object provenance")
    print("[40/43] PASS 30.2 - persistent showcase handoff + stale-server isolation")
    print("[41/43] PASS 30.2.1 - Windows release red team + handoff repair")
    print("[42/43] PASS 31 - human consequence + fiscal forensics")
    print("[43/44] PASS 31.5 - hostile citizen trust, score, unknown, and receipt tests")
    print("[44/45] PASS 31.6.1 - deterministic CBO discovery + fail-open context refresh")
    print("[45/45] LIVE LAUNCH - server, focused showcase, and readiness APIs")

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(process)
        status, health_body = fetch("/api/health")
        health = json.loads(health_body)
        require(status == 200, "Health endpoint did not return HTTP 200")
        require(health.get("pass") == "31" and health.get("release") == "31", "Health endpoint is not reporting Pass 31 release")

        status, home = fetch("/")
        require(status == 200, "Home screen did not return HTTP 200")
        require("BILL X-RAY" in home, "Home screen is missing the BILL X-RAY identity")
        require("Did you read the bill? We did." in home, "Pass 20 home-screen promise did not render")
        require("See a completed X-Ray" in home, "Pass 29 showcase did not render")
        require("Search any bill" in home and "data-bill-search-input" in home, "Pass 22 bill search did not render")
        require('data-showcase-id="aca"' in home and 'data-showcase-id="obbba"' in home, "Both prebuilt showcase exhibits must render")
        require('Dodd-Frank' not in home, "Pass 29 home must not render the old catalog grid")
        require('class="page-home pass29-home"' in home, "Pass 29 focused home layout marker is missing")
        require("data-build-session" in home and "data-progress-percent" in home, "Pass 21.1 progress session did not render")
        require("Context challenged." in home, "Pass 28 public trust marker did not render")
        require((ROOT / "MIGRATE_SHOWCASES_PASS31_1.bat").exists(), "Pass 31.1 safe-migration launcher is missing")
        require((ROOT / "tools" / "migrate_showcases_pass31_1.py").exists(), "Pass 31.1 recovery/migration engine is missing")
        require((ROOT / "MIGRATE_SHOWCASES_PASS31_2_1.bat").exists(), "Pass 31.2.1 semantic-provenance migration launcher is missing")
        require((ROOT / "PASS_31_2_1_SEMANTIC_PROVENANCE_AUDIT_RECONCILIATION.md").exists(), "Pass 31.2.1 doctrine file is missing")
        require((ROOT / "PASS_31_3_CITIZENS_XRAY.md").exists(), "Pass 31.3 Citizen X-Ray doctrine file is missing")
        require((ROOT / "engine" / "citizen_view.py").exists(), "Pass 31.3 Citizen X-Ray presentation adapter is missing")
        require((ROOT / "PASS_31_5_HOSTILE_CITIZEN_TEST.md").exists(), "Pass 31.5 hostile citizen doctrine file is missing")
        require((ROOT / "PASS_31_6_1_CBO_RETRIEVAL_REPAIR.md").exists(), "Pass 31.6.1 CBO repair doctrine file is missing")
        require((ROOT / "REFRESH_CBO_PASS31_6_1.bat").exists(), "Pass 31.6.1 CBO refresh launcher is missing")
        ext_source = (ROOT / "engine" / "external_evidence.py").read_text(encoding="utf-8")
        require("CBO_COST_ESTIMATES" in ext_source and "CBO_CONGRESS_XML" in ext_source and "_cbo_discovery" in ext_source, "Pass 31.6.1 CBO deterministic discovery paths are missing")


        status, forensic_body = fetch("/api/cache-forensics/aca")
        forensic = json.loads(forensic_body)
        require(status == 200 and "checks" in forensic and "failures" in forensic, "Pass 21.3 cache-forensics endpoint failed")

        status, aca_build_body = fetch("/api/build-status/aca")
        aca_build = json.loads(aca_build_body)
        require(status == 200 and aca_build.get("buildable") is True, "ACA product build status is not wired")
        status, obbba_build_body = fetch("/api/build-status/obbba")
        obbba_build = json.loads(obbba_build_body)
        require(status == 200 and obbba_build.get("buildable") is True, "OBBBA product build status is not wired")
        status, catalog_build_body = fetch("/api/build-status/dodd-frank")
        catalog_build = json.loads(catalog_build_body)
        require(status == 200 and catalog_build.get("buildable") is False, "Unwired catalog bill must report an explicit catalog-only state")
        status, build_js = fetch("/static/build_controls.js")
        require(status == 200 and "/api/build/" in build_js and "/api/build-status/" in build_js, "Pass 21 build-control script failed")
        require("eta_label" in build_js and "data-progress-all-stages" in home and "STAGES" in build_js, "Pass 29.1 full-stage progress theater failed")
        require("LIVE DEEP READ · 19 CHECKS" in home and "['external'" in build_js and "['consequence'" in build_js, "Pass 30 external/consequence stages missing")
        status, search_js = fetch("/static/search_bills.js")
        require(status == 200 and "/api/search-bills" in search_js and "/api/search-select" in search_js, "Pass 22 search-control script failed")

        status, bill_page = fetch("/bill/aca")
        require(status == 200, "ACA agent screen did not return HTTP 200")
        require(bill_page.count("Back to Bill X-Ray") >= 2, "Result screen must have clear top and bottom navigation")
        require('class="page-bill pass29-bill"' in bill_page, "Pass 29 answer-first bill layout marker is missing")
        require("The finished X-Ray will answer five human questions." in bill_page or "If you read nothing else, here is what this bill actually does." in bill_page, "Citizen-first result/empty state did not render")

        template_text = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
        require("OUTSIDE THE BILL · OFFICIAL CONTEXT" in template_text and "Three lanes, never blended" in template_text, "Pass 30 external evidence surface missing")
        require("claim-list" in template_text, "Verified public-claim renderer is missing")
        require("No scrutiny candidate survived the referee." in template_text, "No-filler Barrel Scan state is missing")
        synthesis_source = (ROOT / "engine" / "synthesis.py").read_text(encoding="utf-8")
        require("public_interpretation" in synthesis_source, "Pass 14 advocacy publication gate is missing")
        require("limit: int = 3" in synthesis_source, "Pass 14 hard public-claim cap is missing")
        require("_text_referee_for_lens" in synthesis_source, "Pass 19.3 TEXT-referee gate is missing")
        require("diagnose_lens_surface" in synthesis_source, "Pass 19.2 lens diagnostics are missing")
        meaning_source = (ROOT / "engine" / "meaning.py").read_text(encoding="utf-8")
        require("class MeaningPacket" in meaning_source and "missing_context" in meaning_source, "Pass 25 structured meaning packet is missing")
        require("completeness_score" in meaning_source, "Pass 25 comprehension quality gate is missing")
        pass26_source = (ROOT / "engine" / "pass26_intelligence.py").read_text(encoding="utf-8")
        require("Direct recipient named in the text" in pass26_source, "Pass 26 money-flow explanation is missing")
        require("substantive_lens_pair" in pass26_source, "Pass 26 same-effect political lens builder is missing")
        require("is amended by" in synthesis_source and "u.s.c." in synthesis_source, "Pass 20 public-legalese filter is missing")
        require("SCRUTINY, NOT ACCUSATION" in template_text, "Pass 20 Barrel Scan framing is missing")
        require("VERIFIED ANALYSIS" in template_text and "not an endorsement of the bill" in template_text, "Pass 31.5 verified-analysis clarification is missing")
        require("Attention {{claim.scrutiny_score|round|int}}/100" in template_text and "not a probability of corruption, illegality, or fraud" in template_text, "Pass 31.5 attention-score clarification is missing")
        require("hostile context challenge" in template_text and "official bill text" in template_text, "Pass 28 public verification language is missing")
        require((ROOT / "static" / "favicon.svg").exists(), "Pass 20 favicon is missing")
        text_referee_source = (ROOT / "engine" / "text_referee.py").read_text(encoding="utf-8")
        require("construct_text_referee" in text_referee_source, "Pass 19.3 TEXT referee constructor is missing")
        require("extractive" in text_referee_source.lower(), "Pass 19.3 TEXT referee must remain extractive/source-bound")
        require("data-evidence-trigger" in template_text, "Pass 15 evidence controls are missing")
        require("id=\"evidence-drawer\"" in template_text, "Pass 15 evidence drawer is missing")
        status, drawer_js = fetch("/static/evidence_drawer.js")
        require(status == 200 and "/api/evidence/" in drawer_js, "Pass 15 evidence drawer script failed")

        for endpoint, label in (
            ("/api/source-status", "source"),
            ("/api/segment-status", "segment"),
            ("/api/citation-status", "citation"),
            ("/api/translator-status", "translator"),
            ("/api/money-status", "money"),
            ("/api/power-status", "power"),
            ("/api/barrel-status", "barrel"),
            ("/api/topic-status", "topic"),
            ("/api/left-status", "left"),
            ("/api/right-status", "right"),
            ("/api/skeptic-status", "skeptic"),
            ("/api/referee-status", "referee"),
            ("/api/synthesis-status", "synthesis"),
            ("/api/evidence-status", "evidence"),
            ("/api/aca-status", "aca_end_to_end"),
            ("/api/obbba-status", "obbba_end_to_end"),
            ("/api/red-team-status", "red_team"),
            ("/api/audit-status", "audit"),
            ("/api/challenge-status", "challenge"),
        ):
            status, body = fetch(endpoint)
            require(status == 200, f"{label.title()}-status API failed")
            payload = json.loads(body)
            if label == "aca_end_to_end":
                require(set(payload) == {"aca"}, "ACA end-to-end status must report the ACA proving ground")
            elif label == "obbba_end_to_end":
                require(set(payload) == {"obbba"}, "OBBBA end-to-end status must report the OBBBA proving ground")
            elif label == "red_team":
                require(set(payload) == {"aca", "obbba"}, "Red-team status lost the proving-ground bills")
            elif label == "audit":
                require(set(payload) == {"aca", "obbba"}, "Audit status lost the proving-ground bills")
            elif label == "challenge":
                require(payload.get("corpus", {}).get("passed") is True, "Pass 27 adversarial drafting corpus failed")
            else:
                require(set(payload) == {"aca", "obbba"}, f"{label.title()} status lost the proving-ground bills")

        print("\nALL BILL X-RAY SMOKE CHECKS PASSED.")
        return 0
    except Exception as exc:
        print(f"\nSMOKE TEST FAILURE: {exc}")
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
