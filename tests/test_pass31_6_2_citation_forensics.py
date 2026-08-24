from pathlib import Path
import tools.citation_audit_forensics as forensic


def test_forensic_origin_classifies_known_release_failures():
    assert forensic._origin("PUBLIC_TEXT_NOT_REPRODUCIBLE") == "synthesis/upstream text provenance"
    assert forensic._origin("SEMANTIC_PROVENANCE_DRIFT") == "semantic-role provenance wiring"
    assert forensic._origin("NOVEL_NUMBER") == "numeric fidelity / factual wording"


def test_forensic_launcher_exists_and_targets_fentanyl_acceptance_bill():
    root = Path(__file__).resolve().parents[1]
    text = (root / "RUN_CITATION_FORENSICS_PASS31_6_2.bat").read_text(encoding="utf-8")
    assert "citation_audit_forensics.py gpo-118hr171ih" in text
    assert "bootstrap_env.bat" in text


def test_generic_runner_prints_audit_findings_without_changing_gate():
    root = Path(__file__).resolve().parents[1]
    text = (root / "engine" / "generic_end_to_end.py").read_text(encoding="utf-8")
    assert "citation audit findings:" in text
    assert "release_ok = syn.analysis_status == \"verified\" and red.status != \"fail\" and aud.status != \"fail\" and chal.status != \"fail\"" in text
