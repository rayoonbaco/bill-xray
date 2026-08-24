"""Pass 31.4: Grandma-Test presentation adapter for verified Bill X-Ray claims.

No new inference is created here. This layer does not replace, weaken, or reinterpret the verified source-bound claim.
It converts already-audited semantic metadata into a citizen-facing summary and hides
malformed context labels that are technically source-derived but not useful English.
Every displayed card keeps the original citation anchor and receipt.
"""
from __future__ import annotations

import re
from typing import Any

_BAD_CONTEXT = (
    "this act and that subparagraph",
    "that subparagraph and the",
    "is amended",
    "is redesignated",
    "by striking",
    "by inserting",
)
_META_PREFIXES = (
    "who or what is affected:",
    "type of power or duty:",
    "practical consequence:",
    "still unknown:",
)


def _panels(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p.get("key"): p for p in analysis.get("panels", []) if p.get("key")}


def _claims(panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((panel or {}).get("claims", []))[:3]


def _anchor(claim: dict[str, Any]) -> str | None:
    cites = claim.get("citations") or []
    if not cites:
        return None
    return cites[0].get("anchor_id")


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _sentence(value: object, limit: int = 230) -> str:
    text = _clean(value).strip(" ;,:-")
    if not text:
        return ""
    # Remove duplicated machine labels that sometimes survive in older explanatory prose.
    low = text.lower()
    for prefix in _META_PREFIXES:
        if low.startswith(prefix):
            text = text[len(prefix):].strip()
            low = text.lower()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text.rstrip(" ;,") + ("" if text.endswith((".", "?", "!")) else ".")
    cut = text[:limit]
    for sep in (". ", "; ", ", ", " under ", " together with"):
        pos = cut.rfind(sep)
        if pos >= int(limit * 0.55):
            cut = cut[:pos]
            break
    return cut.rstrip(" ;,:-") + "."


def _useful_context(value: object) -> str | None:
    """Reject source-derived labels that are not meaningful citizen language."""
    text = _clean(value).strip(" ;,:-\"'“”")
    if not text:
        return None
    low = text.lower()
    if any(marker in low for marker in _BAD_CONTEXT):
        return None
    if re.match(r"^\d+[a-z-]*(?:\([^)]*\))+\b", text, re.I):
        return None
    if low.startswith(("section titled “", "the section titled “")):
        inner = text.split("“", 1)[-1].rstrip("”")
        if not _useful_context(inner):
            return None
    if len(text) > 220:
        return None
    if text.endswith((" and the", " of the", " for the", " by the")):
        return None
    return text


def _specific_actor(claim: dict[str, Any]) -> str | None:
    return _useful_context(claim.get("authority_actor") or claim.get("semantic_actor"))


def _action(claim: dict[str, Any]) -> str | None:
    action = _useful_context(claim.get("semantic_action"))
    if not action:
        return None
    # Safe readability normalizations: preserve the operative verb and object, remove only
    # trailing drafting appendages that do not change the stated duty in the card headline.
    action = re.sub(r"\bsubmit to Congress a report\b", "submit a report to Congress", action, flags=re.I)
    action = re.split(r"\s+together with--?", action, maxsplit=1, flags=re.I)[0].strip()
    return action


def _affected(claim: dict[str, Any]) -> str | None:
    return _useful_context(claim.get("authority_target") or claim.get("affected_party"))


def _purpose(claim: dict[str, Any]) -> str | None:
    value = _useful_context(claim.get("fiscal_purpose") or claim.get("semantic_purpose"))
    if not value:
        return None
    low = value.lower().strip(" .;,:-")
    # A drafting action is not a citizen-facing purpose. Keep it unresolved unless
    # another verified semantic layer supplies the actual program/use.
    if low in {"carry out this section", "carry out the section", "implement this section"}:
        return None
    if re.fullmatch(r"(?:to )?carry out (?:this|the) (?:section|subsection|paragraph)", low):
        return None
    return value


def _recipient(claim: dict[str, Any]) -> str | None:
    value = _useful_context(claim.get("fiscal_recipient"))
    if not value:
        return None
    low = value.lower().strip(" .;,:-")
    # Timing belongs in WHEN, never in recipient/payer.
    if re.fullmatch(r"(?:fiscal year|fy)\s+\d{4}(?:[-–]\d{2,4})?", low):
        return None
    if re.fullmatch(r"(?:calendar year|cy)\s+\d{4}", low):
        return None
    return value


def _unknown(claim: dict[str, Any]) -> str | None:
    text = _clean(claim.get("semantic_unknown") or claim.get("missing_context")).strip()
    low = text.lower()
    for prefix in _META_PREFIXES:
        if low.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text or None


def _core_card(claim: dict[str, Any]) -> dict[str, Any]:
    row = dict(claim)
    actor = _specific_actor(claim)
    action = _action(claim)
    affected = _affected(claim)
    purpose = _purpose(claim)
    period = _useful_context(claim.get("semantic_period") or claim.get("fiscal_period"))
    amount = _useful_context(claim.get("fiscal_amount"))

    if actor and action:
        headline = _sentence(f"{actor} {action}", 220)
    elif amount and purpose:
        headline = _sentence(f"This provision involves {amount} for {purpose}", 220)
    else:
        headline = _sentence(claim.get("text"), 220)

    care: list[str] = []
    if affected:
        care.append(f"Affects {affected}.")
    if amount:
        care.append(f"Money involved: {amount}.")
    if period:
        care.append(f"When: {period}.")
    authority_type = _useful_context(claim.get("authority_type"))
    if authority_type:
        care.append(f"Legal effect: {authority_type.lower()}.")

    row.update(
        citizen_headline=headline or "Verified change in the bill.",
        citizen_care=" ".join(care[:3]) or _sentence(claim.get("why_it_matters"), 220),
        citizen_unknown=_unknown(claim),
    )
    return row


def _money_card(claim: dict[str, Any]) -> dict[str, Any]:
    row = dict(claim)
    amount = _useful_context(claim.get("fiscal_amount"))
    mechanism = _useful_context(claim.get("fiscal_mechanism"))
    purpose = _purpose(claim)
    recipient = _recipient(claim)
    period = _useful_context(claim.get("fiscal_period") or claim.get("semantic_period"))

    if amount and mechanism and "tax" in mechanism.lower():
        summary = f"This provision contains an operative tax or revenue rule involving {amount}."
    elif amount and purpose:
        summary = f"This provision sets or provides {amount} for {purpose}."
    elif amount:
        summary = f"This provision sets or governs {amount}; the specific final use is not clear from this clause alone."
    else:
        summary = _sentence(claim.get("text"), 220)

    row.update(
        citizen_summary=_sentence(summary, 230),
        citizen_purpose=purpose or "Not clear from this clause alone.",
        citizen_recipient=recipient or "Not clear from this clause alone.",
        citizen_period=period,
        citizen_unknown=_unknown(claim),
    )
    return row


def _power_card(claim: dict[str, Any]) -> dict[str, Any]:
    row = dict(claim)
    actor = _specific_actor(claim) or "Government actor"
    action = _action(claim)
    affected = _affected(claim)
    authority = _useful_context(claim.get("authority_type"))
    if action:
        summary = _sentence(f"{actor} {action}", 225)
    else:
        summary = _sentence(claim.get("text"), 225)

    consequence = None
    if authority:
        low = authority.lower()
        if "mandatory" in low:
            consequence = "This makes the action a legal duty rather than an optional step."
        elif "prohibition" in low or "limit" in low:
            consequence = "This places a legal limit on what the named government actor may do."
        elif "discretion" in low:
            consequence = "This gives the named government actor discretion within the limits of the provision."
    if affected:
        consequence = (consequence + " " if consequence else "") + f"It affects {affected}."

    row.update(
        citizen_actor=actor,
        citizen_action=action or "The exact action is not clear enough here to shorten safely.",
        citizen_affected=affected or "The immediate target is not clear from this clause alone.",
        citizen_summary=summary,
        citizen_consequence=consequence or _sentence(claim.get("why_it_matters"), 230),
        citizen_unknown=_unknown(claim),
    )
    return row


def _scrutiny_card(claim: dict[str, Any]) -> dict[str, Any]:
    row = dict(claim)
    actor = _specific_actor(claim)
    action = _action(claim)
    affected = _affected(claim)
    purpose = _purpose(claim)
    if actor and action:
        summary = _sentence(f"{actor} {action}", 220)
    else:
        summary = _sentence(claim.get("text"), 220)
    reason = _sentence(claim.get("why_flagged"), 250)
    row.update(
        citizen_summary=summary,
        citizen_actor=actor,
        citizen_affected=affected,
        citizen_purpose=purpose,
        citizen_reason=reason,
        citizen_unknown=_unknown(claim),
    )
    return row


def build(analysis: dict[str, Any]) -> dict[str, Any]:
    panels = _panels(analysis)
    core = [_core_card(c) for c in _claims(panels.get("what_it_really_does"))]
    money = [_money_card(c) for c in _claims(panels.get("follow_the_money"))]
    scrutiny = [_scrutiny_card(c) for c in _claims(panels.get("barrel_scan"))]
    power = [_power_card(c) for c in _claims(panels.get("who_wins_pays_power"))]
    lenses = _claims(panels.get("left_right_text"))

    questions: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for lane, claims in (("Core", core), ("Money", money), ("Power", power), ("Closer look", scrutiny)):
        for claim in claims:
            unknown = _clean(claim.get("citizen_unknown") or claim.get("semantic_unknown") or claim.get("missing_context"))
            if not unknown:
                continue
            key = unknown.casefold()
            if key in seen:
                continue
            seen.add(key)
            questions.append({"lane": lane, "text": unknown, "anchor_id": _anchor(claim)})
            if len(questions) >= 3:
                break
        if len(questions) >= 3:
            break

    return {
        "core": core,
        "money": money,
        "power": power,
        "scrutiny": scrutiny,
        "questions": questions,
        "lenses": lenses,
    }
