"""Pass 27: hostile multi-bill challenge harness.

This module scores finished public analyses and runs a deterministic adversarial corpus
that represents drafting patterns known to stress legislative explanation.  It is a
QA/release instrument, not a political classifier.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import json
import re

from engine import context_prosecutor

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "data" / "analyses"
CHALLENGE_DIR = ROOT / "data" / "challenge"
CHALLENGE_VERSION = "27.0-hostile-context-prosecutor"

@dataclass(frozen=True)
class ChallengeFinding:
    severity: str
    code: str
    message: str
    panel: str | None = None
    anchor_id: str | None = None

@dataclass(frozen=True)
class ChallengeReport:
    schema_version: str
    challenge_version: str
    bill_id: str
    status: str
    score: float
    blocker_count: int
    important_count: int
    acceptable_count: int
    findings: list[ChallengeFinding]
    checks: dict


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _anchor(claim: dict) -> str | None:
    cites = claim.get("citations") or []
    return str(cites[0].get("anchor_id")) if cites and cites[0].get("anchor_id") else None


def _excerpt(claim: dict) -> str:
    cites = claim.get("citations") or []
    return str(cites[0].get("excerpt") or "") if cites else ""


def _generic(text: str) -> bool:
    low = " ".join((text or "").lower().split())
    patterns = (
        "changes authority involving", "changes how revenue works", "changes government authority",
        "this provision changes", "public capacity or access", "government reach", "worth the taxpayer cost or market distortion",
    )
    return any(p in low for p in patterns)


def audit_analysis(bill_id: str, *, write: bool = True) -> ChallengeReport:
    analysis = _load(ANALYSIS_DIR / f"{bill_id}.json")
    if not analysis:
        raise FileNotFoundError(f"Public analysis not found for {bill_id}")
    findings: list[ChallengeFinding] = []
    panels = {p.get("key"): p for p in analysis.get("panels", [])}
    all_claims = [(k, c) for k, p in panels.items() for c in p.get("claims", [])]

    # TRUE / CONTEXT: technically supported is not enough when the excerpt screams that
    # another provision may change the meaning.
    for panel, claim in all_claims:
        text = str(claim.get("text") or "")
        why = str(claim.get("why_it_matters") or "")
        prosecution = context_prosecutor.prosecute(claim_text=text, excerpt=_excerpt(claim), why_it_matters=why)
        if prosecution.severity == "critical":
            findings.append(ChallengeFinding("BLOCKER", prosecution.code, prosecution.reason, panel, _anchor(claim)))
        elif prosecution.severity == "warning":
            findings.append(ChallengeFinding("IMPORTANT", prosecution.code, prosecution.reason, panel, _anchor(claim)))

    # IMPORTANT: front page should not be generic detection language.
    for panel, claim in all_claims:
        if _generic(str(claim.get("text") or "")) or _generic(str(claim.get("why_it_matters") or "")):
            findings.append(ChallengeFinding("IMPORTANT", "GENERIC_EXPLANATION", "The public explanation detects a legislative concept but does not finish the concrete human consequence.", panel, _anchor(claim)))

    # FAIR: advocacy lanes must share an anchor and should not be near duplicates.
    lens = panels.get("left_right_text", {}).get("claims", [])
    by = {c.get("lens"): c for c in lens}
    if set(by) != {"LEFT", "RIGHT", "TEXT"}:
        findings.append(ChallengeFinding("BLOCKER", "LENS_INCOMPLETE", "LEFT | RIGHT | TEXT is incomplete.", "left_right_text"))
    else:
        anchors = {_anchor(by[x]) for x in ("LEFT", "RIGHT", "TEXT")}
        if len(anchors) != 1:
            findings.append(ChallengeFinding("BLOCKER", "LENS_CONTEXT_MISMATCH", "Political lanes are not judging the same statutory proposition.", "left_right_text"))
        left_words = set(re.findall(r"[a-z]{4,}", str(by["LEFT"].get("text", "")).lower()))
        right_words = set(re.findall(r"[a-z]{4,}", str(by["RIGHT"].get("text", "")).lower()))
        union = left_words | right_words
        similarity = len(left_words & right_words) / len(union) if union else 1.0
        if similarity > 0.82:
            findings.append(ChallengeFinding("IMPORTANT", "LENS_NOT_DISTINCT", "LEFT and RIGHT are too similar to represent meaningful competing interpretations.", "left_right_text", _anchor(by["LEFT"])))

    # IMPORTANT / COMPLETE ENOUGH: a scrutiny item needs an actual reason beyond a label.
    for claim in panels.get("barrel_scan", {}).get("claims", []):
        reason = str(claim.get("why_flagged") or "")
        if len(reason.split()) < 8:
            findings.append(ChallengeFinding("IMPORTANT", "SCRUTINY_REASON_THIN", "A high-scrutiny finding does not explain concretely enough why a citizen should ask for an explanation.", "barrel_scan", _anchor(claim)))

    blockers = sum(f.severity == "BLOCKER" for f in findings)
    important = sum(f.severity == "IMPORTANT" for f in findings)
    acceptable = sum(f.severity == "ACCEPTABLE_FOR_V1" for f in findings)
    score = max(0.0, round(1.0 - 0.22 * blockers - 0.06 * important - 0.01 * acceptable, 3))
    status = "fail" if blockers else ("pass_with_findings" if important else "pass")
    checks = {
        "no_context_blockers": not any(f.code == "CONTEXT_MATERIALITY_UNRESOLVED" for f in findings),
        "no_generic_front_page_explanations": not any(f.code == "GENERIC_EXPLANATION" for f in findings),
        "same_proposition_political_lenses": not any(f.code in {"LENS_INCOMPLETE", "LENS_CONTEXT_MISMATCH"} for f in findings),
        "substantive_scrutiny_reasons": not any(f.code == "SCRUTINY_REASON_THIN" for f in findings),
    }
    report = ChallengeReport("27.0", CHALLENGE_VERSION, bill_id, status, score, blockers, important, acceptable, findings, checks)
    if write:
        CHALLENGE_DIR.mkdir(parents=True, exist_ok=True)
        (CHALLENGE_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return report


# Deliberately ugly micro-provisions. These are not claims about real legislation; they
# are deterministic QA fixtures designed to stress drafting patterns across bill types.
ADVERSARIAL_CORPUS = [
    ("plain_duty", "The Secretary shall publish the report annually.", "The Secretary must publish the report annually.", "pass"),
    ("exception", "The Secretary shall publish the report annually, except that subsection (d) shall apply.", "The Secretary must publish the report annually.", "warning"),
    ("notwithstanding", "Notwithstanding section 7, the Attorney General may waive the requirement.", "The Attorney General may waive the requirement.", "warning"),
    ("definition", "Eligible entity has the meaning given in section 4002.", "Eligible entity means the listed applicants.", "warning"),
    ("amendment", "Section 5 is amended by striking paragraph (2) and inserting the following.", "The law changes eligibility.", "warning"),
    ("subject_to", "The grant is available subject to section 12(b).", "The grant is available.", "warning"),
    ("appropriation", "There is appropriated $250,000,000 to the Secretary for grants to eligible States.", "Congress provides $250,000,000 as grants to eligible States.", "pass"),
    ("prohibition", "The Administrator may not disclose personally identifiable information.", "The Administrator cannot disclose personally identifiable information.", "pass"),
]


def run_corpus() -> dict:
    rows = []
    failures = 0
    for name, excerpt, claim, expected in ADVERSARIAL_CORPUS:
        out = context_prosecutor.prosecute(claim_text=claim, excerpt=excerpt)
        actual = "pass" if out.severity == "pass" else "warning" if out.severity == "warning" else "critical"
        ok = actual == expected or (expected == "warning" and actual == "critical")
        failures += 0 if ok else 1
        rows.append({"case": name, "expected": expected, "actual": actual, "ok": ok, "risks": out.risks})
    return {"cases": len(rows), "failures": failures, "passed": failures == 0, "results": rows}


def challenge_status() -> dict:
    out = {"corpus": run_corpus()}
    for path in sorted(CHALLENGE_DIR.glob("*.json")) if CHALLENGE_DIR.exists() else []:
        p = _load(path)
        out[path.stem] = {"status": p.get("status"), "score": p.get("score"), "blocker_count": p.get("blocker_count"), "important_count": p.get("important_count")}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Pass 27 hostile multi-bill/context challenge.")
    parser.add_argument("bill_ids", nargs="*")
    args = parser.parse_args(argv)
    corpus = run_corpus()
    print(f"Adversarial drafting corpus: {corpus['cases']} cases; failures={corpus['failures']}")
    failed = not corpus["passed"]
    for bill_id in args.bill_ids:
        try:
            report = audit_analysis(bill_id)
            print(f"{bill_id}: {report.status}; score={report.score:.3f}; blockers={report.blocker_count}; important={report.important_count}")
            for f in report.findings:
                print(f"  [{f.severity}] {f.code}: {f.message}")
            failed = failed or report.status == "fail"
        except Exception as exc:
            print(f"{bill_id}: ERROR - {exc}")
            failed = True
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
