"""Pass 15: evidence drawer and source-navigation support for Bill X-Ray.

The evidence drawer is a read-only presentation layer over Pass 4 citation anchors.
It never reconstructs or paraphrases source text. Opening evidence re-resolves the
anchor against the current canonical ingested bill so stale source fingerprints fail
closed before exact text is shown.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.citations import resolve_anchor

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "data" / "analyses"
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
PROVING_GROUND_BILLS = ("aca", "obbba")
EVIDENCE_VERSION = "15.0-drawer-navigation"


def _public_document_ref(anchor: dict) -> str:
    """Return a public-safe source label without leaking local filesystem paths."""
    source_url = str(anchor.get("source_url") or "").strip()
    if "govinfo.gov" in source_url.lower():
        return "Official GovInfo source"
    if source_url:
        return "Official source"
    return "Canonical bill source snapshot"


def evidence_payload(bill_id: str, anchor_id: str) -> dict:
    """Return a freshly verified, UI-safe evidence payload for one anchor."""
    anchor = resolve_anchor(bill_id, anchor_id)
    public_document_ref = _public_document_ref(anchor)
    return {
        "schema_version": "15.0",
        "evidence_version": EVIDENCE_VERSION,
        "verified": True,
        "bill_id": anchor["bill_id"],
        "anchor_id": anchor["anchor_id"],
        "section_label": anchor.get("section_label") or anchor.get("heading") or "Source section",
        "heading": anchor.get("heading") or "",
        "kind": anchor.get("kind") or "",
        "identifier": anchor.get("identifier") or "",
        "location_marker": anchor.get("location_marker") or "",
        "document_ref": public_document_ref,
        "source_url": anchor.get("source_url") or "",
        "excerpt": anchor.get("excerpt") or "",
        "exact_text": anchor.get("exact_text") or "",
        "source_sha256": anchor.get("source_sha256") or "",
        "text_sha256": anchor.get("text_sha256") or "",
        "source_navigation": {
            "official_url": anchor.get("source_url") or "",
            "document_ref": public_document_ref,
            "location_marker": anchor.get("location_marker") or "",
            "note": "The exact anchored text above is re-verified against Bill X-Ray's canonical source snapshot before display.",
        },
    }


def evidence_status() -> dict[str, dict]:
    """Report whether each proving-ground bill can support source navigation."""
    status: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        analysis_path = ANALYSIS_DIR / f"{bill_id}.json"
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        analysis_status = "not_generated"
        public_claim_count = 0
        anchored_public_claim_count = 0

        if analysis_path.exists():
            try:
                analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
                analysis_status = str(analysis.get("analysis_status", "not_generated"))
                for panel in analysis.get("panels", []):
                    for claim in panel.get("claims", []):
                        public_claim_count += 1
                        citations = claim.get("citations") or []
                        if citations and citations[0].get("anchor_id"):
                            anchored_public_claim_count += 1
            except (OSError, ValueError, json.JSONDecodeError):
                analysis_status = "unreadable"

        status[bill_id] = {
            "analysis_status": analysis_status,
            "anchors_present": anchor_path.exists(),
            "public_claim_count": public_claim_count,
            "anchored_public_claim_count": anchored_public_claim_count,
            "drawer_ready": (
                analysis_status == "verified"
                and anchor_path.exists()
                and public_claim_count > 0
                and public_claim_count == anchored_public_claim_count
            ),
        }
    return status
