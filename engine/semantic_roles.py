"""Pass 31.2: conservative semantic-role and internal cross-reference resolver.

The public surface must not confuse time, money, verbs, and entities.  This module
normalizes already source-bound findings into mutually exclusive human roles and may
use the current section heading (or a resolvable same-bill section cross-reference)
as context.  It never turns an unresolved cross-reference into a factual claim.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_DIR = ROOT / "data" / "citation_anchors"

_TIME = re.compile(r"\b(?:fiscal\s+year|calendar\s+year|fy\s*\d{2,4}|20\d{2}|19\d{2}|preceding\s+calendar\s+year)\b", re.I)
_MONEY = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:trillion|billion|million|thousand))?", re.I)
_GENERIC_ACTION = re.compile(
    r"^(?:carry out (?:this|the) section|implement (?:this|the) section|this section|such section|"
    r"the program|such program|fiscal year\s+\d{4}|calendar year\s+\d{4})$",
    re.I,
)
_SECTION_REF = re.compile(r"\bsection\s+([0-9A-Za-z-]+)(?:\([^)]+\))*\b", re.I)
_EXTERNAL_ACT = re.compile(r"\bof\s+the\s+(?:Social Security|Internal Revenue|Public Health Service|Employee Retirement Income Security)\s+Act\b", re.I)


@dataclass(frozen=True)
class RoleResolution:
    actor: str | None = None
    action: str | None = None
    target: str | None = None
    purpose: str | None = None
    recipient: str | None = None
    period: str | None = None
    section_context: str | None = None
    cross_reference_context: str | None = None
    unresolved_cross_reference: str | None = None
    unknowns: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compact(value: object) -> str:
    return " ".join(str(value or "").split())


def _attr(packet: object | None, name: str) -> str | None:
    value = getattr(packet, name, None) if packet is not None else None
    value = compact(value)
    return value or None


def is_time(value: object) -> bool:
    text = compact(value)
    return bool(text and _TIME.search(text) and len(text) <= 90)


def is_money(value: object) -> bool:
    text = compact(value)
    return bool(text and _MONEY.fullmatch(text.strip(" .;,:")))


def is_generic_action(value: object) -> bool:
    text = compact(value).strip(" .;,:-")
    return bool(text and _GENERIC_ACTION.fullmatch(text))


def _role_safe(value: object, role: str) -> str | None:
    text = compact(value).strip(" .;,:-")
    if not text:
        return None
    if role in {"recipient", "target"}:
        if is_time(text) or is_money(text) or is_generic_action(text):
            return None
    if role == "purpose":
        if is_time(text) or is_money(text) or is_generic_action(text):
            return None
    if role == "actor" and (is_time(text) or is_money(text)):
        return None
    return text


def _anchor_context(finding: dict) -> dict[str, str]:
    bill_id = compact(finding.get("bill_id"))
    anchor_id = compact(finding.get("anchor_id"))
    if not bill_id or not anchor_id:
        return {}
    path = ANCHOR_DIR / f"{bill_id}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    anchor = next((a for a in payload.get("anchors", []) if compact(a.get("anchor_id")) == anchor_id), None)
    if not anchor:
        return {}
    return {
        "heading": compact(anchor.get("heading")),
        "identifier": compact(anchor.get("identifier")),
        "kind": compact(anchor.get("kind")),
        "excerpt": compact(anchor.get("excerpt")),
    }


def _heading_label(heading: str) -> str | None:
    text = compact(heading)
    if not text:
        return None
    text = re.sub(r"^(?:SEC\.?|SECTION)\s*[0-9A-Za-z-]+\.?\s*", "", text, flags=re.I).strip(" -—:.")
    if not text or text.lower() in {"definitions", "effective date", "table of contents"}:
        return None
    return text


def _internal_cross_reference(finding: dict, clause: str) -> tuple[str | None, str | None]:
    """Return (resolved heading context, unresolved label).

    Only same-bill section references are resolved. References explicitly naming another
    Act are preserved as unresolved context so the public layer does not invent meaning.
    """
    text = compact(clause)
    if not text:
        return None, None
    match = _SECTION_REF.search(text)
    if not match:
        return None, None
    identifier = compact(match.group(1))
    label = f"section {identifier}"
    if _EXTERNAL_ACT.search(text):
        return None, label
    bill_id = compact(finding.get("bill_id"))
    if not bill_id:
        return None, label
    path = ANCHOR_DIR / f"{bill_id}.json"
    if not path.exists():
        return None, label
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, label
    matches = [a for a in payload.get("anchors", []) if compact(a.get("kind")).lower() == "section" and compact(a.get("identifier")).lower() == identifier.lower()]
    if len(matches) != 1:
        return None, label
    heading = _heading_label(compact(matches[0].get("heading")))
    return (f"{label}: {heading}" if heading else label), None


def resolve_money(finding: dict, packet: object | None) -> RoleResolution:
    context = _anchor_context(finding)
    heading = _heading_label(context.get("heading", ""))
    clause = compact(getattr(packet, "plain_statement", None)) or compact(finding.get("operative_excerpt"))

    recipient = _role_safe(_attr(packet, "recipient"), "recipient")
    target = _role_safe(_attr(packet, "target"), "target")
    purpose = _role_safe(_attr(packet, "purpose"), "purpose")
    actor = _role_safe(_attr(packet, "actor"), "actor")
    action = _role_safe(_attr(packet, "action"), "action")

    # Appropriations/funding are acts of Congress when the clause contains no explicit
    # executive actor. This is a description of what the statute does, not a recipient guess.
    categories = {compact(x).lower() for x in finding.get("categories", []) if compact(x)}
    direction = compact(finding.get("fiscal_direction")).lower()
    if not actor and (categories & {"appropriation", "funding", "grant", "subsidy", "transfer"} or direction == "funding_or_authority"):
        actor = "Congress"

    resolved_ref, unresolved_ref = _internal_cross_reference(finding, compact(finding.get("operative_excerpt")))
    if not purpose:
        if resolved_ref:
            purpose = f"the program or rule described in {resolved_ref}"
        elif heading:
            purpose = f"the section titled “{heading}”"

    if not target:
        target = recipient
    if not target and heading:
        target = f"the program or activity addressed by “{heading}”"

    timing = [compact(x) for x in finding.get("timing", []) if compact(x)]
    period = "; ".join(timing[:2]) or None

    unknowns: list[str] = []
    if not recipient:
        unknowns.append("The final recipient or payer is not identifiable from this provision alone.")
    if not _role_safe(_attr(packet, "purpose"), "purpose"):
        if heading:
            unknowns.append("The section heading supplies purpose context, but the operative clause does not state a more specific final use.")
        else:
            unknowns.append("The final use of the money is not stated clearly enough to name safely.")
    if unresolved_ref:
        unknowns.append(f"The clause points to {unresolved_ref}; that cross-reference is not resolved as a same-bill section here.")

    return RoleResolution(
        actor=actor,
        action=action,
        target=target,
        purpose=purpose,
        recipient=recipient,
        period=period,
        section_context=heading,
        cross_reference_context=resolved_ref,
        unresolved_cross_reference=unresolved_ref,
        unknowns=tuple(unknowns),
    )


def resolve_power(finding: dict, packet: object | None) -> RoleResolution:
    context = _anchor_context(finding)
    heading = _heading_label(context.get("heading", ""))
    actors = [_role_safe(x, "actor") for x in finding.get("actors", [])]
    actors = [x for x in actors if x]
    actor = _role_safe(_attr(packet, "actor"), "actor")
    # Prefer the most specific source-bound actor name (e.g. Secretary of HHS over "the Secretary").
    if actors:
        actor = max(actors + ([actor] if actor else []), key=lambda x: len(x))
    target = _role_safe(_attr(packet, "target"), "target")
    action = _role_safe(_attr(packet, "action"), "action")
    resolved_ref, unresolved_ref = _internal_cross_reference(finding, compact(finding.get("operative_excerpt")))
    if not target and heading:
        target = f"the program or activity addressed by “{heading}”"
    unknowns: list[str] = []
    if not target:
        unknowns.append("The immediate affected person, entity, or program is not explicit enough to name safely.")
    if unresolved_ref:
        unknowns.append(f"The clause points to {unresolved_ref}; the full effect depends on that unresolved cross-reference.")
    return RoleResolution(
        actor=actor,
        action=action,
        target=target,
        purpose=resolved_ref or (f"the section titled “{heading}”" if heading else None),
        section_context=heading,
        cross_reference_context=resolved_ref,
        unresolved_cross_reference=unresolved_ref,
        unknowns=tuple(unknowns),
    )
