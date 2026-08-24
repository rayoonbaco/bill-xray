"""Pass 31: human consequence helpers for the public Bill X-Ray surface.

This layer does not invent consequences. It converts already-source-bound money,
power, translation, and scrutiny packets into compact public language. It also makes
Barrel Scan consume the canonical fiscal ontology so contextual dollar figures cannot
masquerade as operative money on the public surface.
"""
from __future__ import annotations

from engine import comprehension, fiscal_materiality, meaning, semantic_roles


def compact(value: object) -> str:
    return " ".join(str(value or "").split())


def clip(value: object, limit: int = 300) -> str:
    text = compact(value)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "; ", ", "):
        pos = cut.rfind(sep)
        if pos >= int(limit * 0.55):
            return cut[:pos].rstrip(" ,;:") + "."
    return cut.rstrip(" ,;:") + "…"


def fiscal_signal(money_finding: dict | None) -> tuple[float, float]:
    """Return (0-1 scrutiny factor, actionable USD amount) from canonical fiscal data."""
    if not money_finding:
        return 0.0, 0.0
    assessment = fiscal_materiality.assess(money_finding)
    if not assessment.actionable:
        return 0.0, 0.0
    return assessment.score, assessment.amount


def money_fields(finding: dict | None) -> dict[str, object]:
    packet = meaning.from_money(finding or {}) if finding else None
    if not packet:
        return {}
    roles = semantic_roles.resolve_money(finding or {}, packet)
    assessment = fiscal_materiality.assess(finding or {})
    amount = None
    if assessment.actionable and assessment.amount > 0:
        amount = f"${assessment.amount:,.0f}"
    direction = str((finding or {}).get("fiscal_direction") or "").strip()
    mechanism_map = {
        "funding_reduction": "rescission / funding reduction",
        "government_receipt": "tax, fee, or federal receipt",
        "receipt_reduction": "tax or fee reduction",
        "funding_or_authority": "funding or spending authority",
        "revenue_or_tax_mechanic": "tax or revenue rule",
        "unspecified": "fiscal rule",
    }
    mechanism = mechanism_map.get(direction, direction.replace("_", " ") if direction else None)
    unknowns = list(roles.unknowns) or list(packet.missing_context[:2])
    return {
        "fiscal_amount": amount,
        "fiscal_mechanism": mechanism,
        "fiscal_recipient": roles.recipient,
        "fiscal_purpose": roles.purpose,
        "fiscal_period": roles.period,
        "affected_party": roles.target,
        "missing_context": " ".join(unknowns[:2]) or None,
        "semantic_actor": roles.actor,
        "semantic_action": roles.action,
        "semantic_purpose": roles.purpose,
        "semantic_period": roles.period,
        "semantic_unknown": " ".join(unknowns[:2]) or None,
    }


def power_fields(finding: dict | None) -> dict[str, object]:
    packet = meaning.from_power(finding or {}) if finding else None
    if not packet:
        return {}
    roles = semantic_roles.resolve_power(finding or {}, packet)
    unknowns = list(roles.unknowns) or list(packet.missing_context[:1])
    return {
        "authority_actor": roles.actor,
        "authority_type": packet.authority_type,
        "authority_target": roles.target,
        "affected_party": roles.target,
        "missing_context": " ".join(unknowns[:1]) or None,
        "semantic_actor": roles.actor,
        "semantic_action": roles.action,
        "semantic_purpose": roles.purpose,
        "semantic_period": roles.period,
        "semantic_unknown": " ".join(unknowns[:1]) or None,
    }


def _title(candidate: dict, money: dict | None, power: dict | None) -> str:
    money_packet = meaning.from_money(money or {}) if money else None
    power_packet = meaning.from_power(power or {}) if power else None
    fiscal = fiscal_materiality.assess(money or {}) if money else None
    if fiscal and fiscal.actionable and money_packet and money_packet.plain_statement:
        if fiscal.bucket == "funding_reduction":
            return "Funding reduction worth a closer look"
        if fiscal.bucket == "revenue_tax":
            return "Tax or revenue change worth a closer look"
        return "Major funding provision worth a closer look"
    if power_packet and power_packet.plain_statement and power_packet.completeness_score >= 0.55:
        if power_packet.authority_type:
            return f"{power_packet.authority_type.title()} change worth a closer look"
        return "Government authority change worth a closer look"
    labels = set(str(x) for x in candidate.get("labels", []) if x)
    if "Highly Specific Beneficiary" in labels:
        return "Narrow eligibility or beneficiary rule"
    if "Narrow Carve-Out" in labels:
        return "Narrow exception worth a closer look"
    if "Scope Surprise" in labels or "Potential Rider" in labels:
        return "Unexpected provision worth a closer look"
    if "Cross-Reference Opacity" in labels:
        return "Cross-referenced rule worth a closer look"
    return "Provision worth a closer look"


def _best_plain(candidate: dict, money: dict | None, power: dict | None, translation: str | None) -> str | None:
    money_packet = meaning.from_money(money or {}) if money else None
    power_packet = meaning.from_power(power or {}) if power else None
    if money_packet:
        roles = semantic_roles.resolve_money(money or {}, money_packet)
        fiscal = fiscal_materiality.assess(money or {})
        if fiscal.actionable and fiscal.amount > 0:
            amount = f"${fiscal.amount:,.0f}"
            if roles.purpose:
                return clip(f"{roles.actor or 'Congress'} sets or provides {amount} for {roles.purpose}.", 285)
            return clip(f"The provision sets or provides {amount}; the final use is not stated clearly enough here to name safely.", 285)
    if power_packet:
        roles = semantic_roles.resolve_power(power or {}, power_packet)
        if roles.actor and roles.action:
            return clip(f"{roles.actor} {roles.action}", 285)
    packets = [p for p in (money_packet, power_packet) if p and p.plain_statement]
    packets.sort(key=lambda p: p.completeness_score, reverse=True)
    for packet in packets:
        if packet.completeness_score >= 0.50 and comprehension.evaluate_packet(packet).publish:
            return clip(packet.plain_statement, 285)
    if translation:
        return clip(translation, 285)
    excerpt = compact(candidate.get("operative_excerpt"))
    if excerpt:
        return clip(excerpt, 285)
    return None


def _why(candidate: dict, money: dict | None) -> str:
    factors = candidate.get("factors") or {}
    parts: list[str] = []
    fiscal = fiscal_materiality.assess(money or {}) if money else None
    if fiscal and fiscal.actionable and fiscal.amount > 0:
        parts.append(f"It contains an operative fiscal amount of ${fiscal.amount:,.0f}.")
    if float(factors.get("beneficiary_concentration", 0.0)) >= 0.50:
        parts.append("The eligibility or beneficiary language is unusually narrow or specific.")
    if float(factors.get("narrow_carve_out", 0.0)) >= 0.50:
        parts.append("It contains an exception, exemption, waiver, limitation, or special rule that changes who is covered.")
    if float(factors.get("cross_reference_opacity", 0.0)) >= 0.44:
        parts.append("Understanding the full effect requires following statutory cross-references.")
    if float(factors.get("scope_surprise", 0.0)) >= 0.58:
        parts.append("Its subject or scope stands out from the bill's repeated section themes when combined with another independent signal.")
    if not parts:
        parts.append("Multiple independent review signals make this less routine than surrounding implementation language.")
    return clip(" ".join(parts), 330)


def scrutiny_public(candidate: dict, money: dict | None, power: dict | None, translation: str | None) -> dict[str, str | None]:
    return {
        "title": _title(candidate, money, power),
        "plain": _best_plain(candidate, money, power, translation),
        "why": _why(candidate, money),
    }
