"""Pass 19: hallucination and citation audit for Bill X-Ray.

This is a read-only release gate over the finished public report. It does not improve,
rewrite, or reinterpret a claim. It independently re-resolves every public citation
against the canonical source, verifies citation metadata, checks that each published
sentence is reproducible from the upstream artifact that earned publication, and
checks numeric fidelity against the anchored statute.
"""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from dataclasses import asdict, dataclass
from pathlib import Path

from engine import synthesis, text_referee, so_what, human_consequence
from engine.citations import resolve_anchor
from engine.schemas import BillAnalysis

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "data" / "analyses"
TRANSLATION_DIR = ROOT / "data" / "translations"
MONEY_DIR = ROOT / "data" / "money"
POWER_DIR = ROOT / "data" / "power"
BARREL_DIR = ROOT / "data" / "barrel_scan"
LEFT_DIR = ROOT / "data" / "left_lens"
RIGHT_DIR = ROOT / "data" / "right_lens"
AUDIT_DIR = ROOT / "data" / "citation_audit"
PROVING_GROUND_BILLS = ("aca", "obbba")
AUDIT_VERSION = "31.6.2.2-lens-provenance-reconciliation"


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    code: str
    message: str
    panel: str | None = None
    anchor_id: str | None = None


@dataclass(frozen=True)
class AuditReport:
    schema_version: str
    audit_version: str
    bill_id: str
    status: str
    public_claim_count: int
    citations_checked: int
    upstream_claims_reproduced: int
    critical_count: int
    warning_count: int
    findings: list[AuditFinding]
    checks: dict


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _index(directory: Path, bill_id: str, key: str) -> dict[str, dict]:
    payload = _load(directory / f"{bill_id}.json")
    return {str(x["anchor_id"]): x for x in payload.get(key, []) if x.get("anchor_id")}


def _first_anchor(claim: dict) -> str | None:
    citations = claim.get("citations") or []
    if not citations:
        return None
    return citations[0].get("anchor_id") or None


def _normalize(text: object) -> str:
    return " ".join(str(text or "").split())


def _number_value(raw: str) -> str:
    """Canonicalize a numeric spelling without changing its semantic type."""
    try:
        value = Decimal(raw.replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return raw.replace(",", "").strip()
    # Decimal normalization avoids false drift from 10 vs 10.0 while keeping exact value.
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _numeric_signatures(text: str) -> set[tuple[str, str]]:
    """Return semantic numeric signatures from public/source text.

    Pass 19 originally compared raw numeric spellings. Real GovInfo text can format the
    same value as ``$ 10,000`` while a source-bound extractor renders ``$10,000``; it can
    likewise spell ``10 percent`` where public text uses ``10%``. Those are formatting
    differences, not hallucinated numbers. We therefore preserve *type* (money, percent,
    generic number) while canonicalizing spacing, commas, decimal zeros, and percent spelling.
    """
    text = str(text or "")
    spans: list[tuple[int, int]] = []
    out: set[tuple[str, str]] = set()

    patterns = (
        ("money", re.compile(r"(?<![A-Za-z])\$\s*(\d[\d,]*(?:\.\d+)?)")),
        ("percent", re.compile(r"(?<![A-Za-z])(\d[\d,]*(?:\.\d+)?)\s*(?:%|percent\b)", re.I)),
    )
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            out.add((kind, _number_value(match.group(1))))
            spans.append(match.span())

    def covered(start: int, end: int) -> bool:
        return any(start >= a and end <= b for a, b in spans)

    generic = re.compile(r"(?<![A-Za-z$])(\d[\d,]*(?:\.\d+)?)(?!\s*(?:%|percent\b))", re.I)
    for match in generic.finditer(text):
        if not covered(*match.span()):
            out.add(("number", _number_value(match.group(1))))
    return out


def _upstream_expected(panel_key: str, claim: dict, anchor_id: str, indexes: dict[str, dict[str, dict]]) -> str | None:
    lens = claim.get("lens")
    if panel_key == "left_right_text" and lens == "LEFT":
        # Synthesis deliberately applies its bounded public-text transformation to
        # authored lens prose before publication. Reproduce that exact deterministic
        # transformation here rather than comparing the public claim to the longer
        # pre-synthesis artifact. This preserves a strict equality gate: any drift
        # after the approved synthesis transform still fails closed.
        return synthesis._lens_text(indexes["left"].get(anchor_id, {}))
    if panel_key == "left_right_text" and lens == "RIGHT":
        return synthesis._lens_text(indexes["right"].get(anchor_id, {}))
    if panel_key == "left_right_text" and lens == "TEXT":
        try:
            return text_referee.construct_text_referee(str(claim.get("citations", [{}])[0].get("bill_id") or ""), anchor_id).text
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            return None
    if panel_key == "what_it_really_does":
        published = _normalize(claim.get("text"))
        options = [
            synthesis._translation_text(indexes["translations"].get(anchor_id, {})),
            so_what.power_explanation(indexes["power"].get(anchor_id, {}))[0],
            so_what.money_explanation(indexes["money"].get(anchor_id, {}))[0],
        ]
        for option in options:
            if option and _normalize(option) == published:
                return option
        return next((x for x in options if x), None)
    if panel_key == "follow_the_money":
        return synthesis._money_text(indexes["money"].get(anchor_id, {}))
    if panel_key == "who_wins_pays_power":
        return synthesis._power_text(indexes["power"].get(anchor_id, {}))
    if panel_key == "barrel_scan":
        translation = synthesis._translation_text(indexes["translations"].get(anchor_id, {}))
        public = human_consequence.scrutiny_public(
            indexes["barrel"].get(anchor_id, {}),
            indexes["money"].get(anchor_id, {}),
            indexes["power"].get(anchor_id, {}),
            translation,
        )
        return public.get("plain")
    return None



def _semantic_expected(panel_key: str, anchor_id: str, indexes: dict[str, dict[str, dict]], claim: dict | None = None) -> dict[str, object]:
    """Regenerate Pass-31 semantic display metadata from canonical upstream artifacts.

    These fields are not free prose. If synthesis publishes actor/target/purpose/period
    metadata, the audit must be able to independently regenerate the same values.
    Missing public metadata is allowed for historical/non-semantic claims; drift in a
    field that *is* published is a release-blocking provenance failure.
    """
    if panel_key == "what_it_really_does":
        # Pass 31.4.1: CORE semantic roles must be regenerated from the exact
        # canonical object that supplied them during synthesis. The source-kind
        # marker is provenance routing metadata; the values themselves are
        # independently regenerated here and still require exact agreement.
        source_kind = str((claim or {}).get("semantic_source_kind") or "").strip().lower()
        if source_kind == "money":
            return human_consequence.money_fields(indexes["money"].get(anchor_id, {}))
        if source_kind == "power":
            return human_consequence.power_fields(indexes["power"].get(anchor_id, {}))
        return {}
    if panel_key == "follow_the_money":
        return human_consequence.money_fields(indexes["money"].get(anchor_id, {}))
    if panel_key == "who_wins_pays_power":
        return human_consequence.power_fields(indexes["power"].get(anchor_id, {}))
    if panel_key == "barrel_scan":
        out = dict(human_consequence.money_fields(indexes["money"].get(anchor_id, {})))
        for key, value in human_consequence.power_fields(indexes["power"].get(anchor_id, {})).items():
            if value and not out.get(key):
                out[key] = value
        return out
    return {}


def _semantic_public_fields(claim: dict) -> dict[str, object]:
    keys = (
        "affected_party", "fiscal_amount", "fiscal_mechanism", "fiscal_recipient",
        "fiscal_purpose", "fiscal_period", "missing_context", "authority_actor",
        "authority_type", "authority_target", "semantic_actor", "semantic_action",
        "semantic_purpose", "semantic_period", "semantic_unknown",
    )
    return {key: claim.get(key) for key in keys if claim.get(key) is not None}

def audit_bill(bill_id: str, *, write: bool = True) -> AuditReport:
    analysis_path = ANALYSIS_DIR / f"{bill_id}.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"Public analysis not found: {analysis_path}")
    raw_analysis = _load(analysis_path)
    # Re-run the strict Pass 1/14 schema at the release boundary.
    BillAnalysis.model_validate(raw_analysis)

    indexes = {
        "translations": _index(TRANSLATION_DIR, bill_id, "translations"),
        "money": _index(MONEY_DIR, bill_id, "findings"),
        "power": _index(POWER_DIR, bill_id, "findings"),
        "barrel": _index(BARREL_DIR, bill_id, "candidates"),
        "left": _index(LEFT_DIR, bill_id, "candidates"),
        "right": _index(RIGHT_DIR, bill_id, "candidates"),
    }

    findings: list[AuditFinding] = []
    public_claim_count = 0
    citations_checked = 0
    reproduced = 0

    for panel in raw_analysis.get("panels", []):
        panel_key = str(panel.get("key") or "")
        for claim in panel.get("claims", []):
            public_claim_count += 1
            citations = claim.get("citations") or []
            if len(citations) != 1:
                findings.append(AuditFinding("critical", "CITATION_CARDINALITY", "A public V1 claim must resolve through exactly one stable statutory anchor.", panel_key, _first_anchor(claim)))
                continue
            citation = citations[0]
            anchor_id = citation.get("anchor_id")
            if not anchor_id:
                findings.append(AuditFinding("critical", "MISSING_ANCHOR", "A public claim has no Pass 4 anchor ID.", panel_key, None))
                continue
            try:
                resolved = resolve_anchor(bill_id, str(anchor_id))
                citations_checked += 1
            except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
                findings.append(AuditFinding("critical", "ANCHOR_RESOLUTION_FAILED", f"The public citation no longer resolves cleanly: {exc}", panel_key, str(anchor_id)))
                continue

            # Citation metadata shown to the user must agree with the canonical anchor.
            expected_meta = {
                "bill_id": resolved.get("bill_id"),
                "section": resolved.get("section_label"),
                "document_ref": resolved.get("document_ref"),
                "location_marker": resolved.get("location_marker"),
            }
            for field, expected in expected_meta.items():
                actual = citation.get(field)
                if expected and _normalize(actual) != _normalize(expected):
                    findings.append(AuditFinding("critical", "CITATION_METADATA_DRIFT", f"Citation {field} does not match the canonical anchor. public={actual!r}; canonical={expected!r}.", panel_key, str(anchor_id)))

            source_url = str(resolved.get("source_url") or "")
            cited_url = str(citation.get("source_url") or "")
            if source_url and cited_url and source_url.rstrip("/") != cited_url.rstrip("/"):
                findings.append(AuditFinding("critical", "CITATION_URL_DRIFT", f"Citation source URL does not match the canonical anchor. public={cited_url!r}; canonical={source_url!r}.", panel_key, str(anchor_id)))

            # The public sentence must be exactly reproducible from the artifact that synthesis used.
            expected_text = _upstream_expected(panel_key, claim, str(anchor_id), indexes)
            if not expected_text:
                findings.append(AuditFinding("critical", "UPSTREAM_PROVENANCE_MISSING", "The public claim cannot be reproduced from its expected upstream evidence artifact.", panel_key, str(anchor_id)))
            elif _normalize(expected_text) != _normalize(claim.get("text")):
                findings.append(AuditFinding("critical", "PUBLIC_TEXT_NOT_REPRODUCIBLE", "Published wording differs from the source-bound upstream artifact that earned publication.", panel_key, str(anchor_id)))
            else:
                reproduced += 1

            # Pass 31.2.1: semantic display roles are release-bound provenance, too.
            # If synthesis publishes a role field, independently regenerate it from the
            # canonical money/power artifact and require exact normalized agreement.
            expected_semantics = _semantic_expected(panel_key, str(anchor_id), indexes, claim)
            for field, actual in _semantic_public_fields(claim).items():
                expected = expected_semantics.get(field)
                if _normalize(actual) != _normalize(expected):
                    findings.append(AuditFinding(
                        "critical",
                        "SEMANTIC_PROVENANCE_DRIFT",
                        f"Published semantic role {field} cannot be reproduced from the canonical upstream artifact. public={actual!r}; canonical={expected!r}.",
                        panel_key,
                        str(anchor_id),
                    ))

            # Hallucination tripwire: factual lanes may not introduce numbers absent from exact text.
            if claim.get("claim_class") in {"TEXT", "DIRECT_EFFECT"} and panel_key != "barrel_scan":
                claim_nums = _numeric_signatures(str(claim.get("text") or ""))
                source_nums = _numeric_signatures(str(resolved.get("exact_text") or ""))
                novel = sorted(claim_nums - source_nums)
                if novel:
                    rendered = ", ".join(f"{kind}:{value}" for kind, value in novel[:5])
                    findings.append(AuditFinding("critical", "NOVEL_NUMBER", f"A factual public claim introduces numeric value(s) not present with the same semantic type in its anchored statutory text: {rendered}.", panel_key, str(anchor_id)))

            # Stored excerpts are display aids only, but if present they must remain source-derived.
            excerpt = _normalize(citation.get("excerpt"))
            if excerpt and excerpt not in _normalize(resolved.get("exact_text")):
                findings.append(AuditFinding("warning", "EXCERPT_NOT_EXACT_SUBSTRING", "Stored citation excerpt is not an exact normalized substring of the re-verified anchor text.", panel_key, str(anchor_id)))

    critical = sum(f.severity == "critical" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    status = "fail" if critical else ("pass_with_warnings" if warnings else "pass")
    checks = {
        "schema_valid": True,
        "all_public_claims_cited": citations_checked == public_claim_count,
        "all_citations_reverified": citations_checked == public_claim_count,
        "all_public_text_reproducible": reproduced == public_claim_count,
        "no_novel_factual_numbers": not any(f.code == "NOVEL_NUMBER" for f in findings),
        "no_citation_metadata_drift": not any(f.code in {"CITATION_METADATA_DRIFT", "CITATION_URL_DRIFT"} for f in findings),
        "semantic_roles_reproducible": not any(f.code == "SEMANTIC_PROVENANCE_DRIFT" for f in findings),
    }
    report = AuditReport(
        schema_version="19.1",
        audit_version=AUDIT_VERSION,
        bill_id=bill_id,
        status=status,
        public_claim_count=public_claim_count,
        citations_checked=citations_checked,
        upstream_claims_reproduced=reproduced,
        critical_count=critical,
        warning_count=warnings,
        findings=findings,
        checks=checks,
    )
    if write:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        (AUDIT_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def audit_status() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        path = AUDIT_DIR / f"{bill_id}.json"
        if not path.exists():
            out[bill_id] = {"audit_ready": False, "status": "not_run", "critical_count": 0, "warning_count": 0}
            continue
        payload = _load(path)
        out[bill_id] = {
            "audit_ready": payload.get("status") in {"pass", "pass_with_warnings"},
            "status": payload.get("status", "fail"),
            "public_claim_count": payload.get("public_claim_count", 0),
            "citations_checked": payload.get("citations_checked", 0),
            "upstream_claims_reproduced": payload.get("upstream_claims_reproduced", 0),
            "critical_count": payload.get("critical_count", 0),
            "warning_count": payload.get("warning_count", 0),
            "checks": payload.get("checks", {}),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Pass 19 hallucination/citation release audit.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            report = audit_bill(bill_id)
            print(f"{bill_id}: {report.status}; public={report.public_claim_count}; citations={report.citations_checked}; reproduced={report.upstream_claims_reproduced}; critical={report.critical_count}; warnings={report.warning_count}")
            for finding in report.findings:
                where = f" panel={finding.panel}" if finding.panel else ""
                anchor = f" anchor={finding.anchor_id}" if finding.anchor_id else ""
                print(f"  [{finding.severity.upper()}] {finding.code}{where}{anchor}: {finding.message}")
            failed = failed or report.status == "fail"
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
