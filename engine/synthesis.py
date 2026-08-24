"""Pass 14: Five-panel synthesis for Bill X-Ray.

This module is the public-output choke point. It does not rediscover facts and it does
not overrule the Neutral Referee. It ranks already-admissible candidate claims,
keeps a hard three-claim cap per public panel, preserves citation anchors, and refuses
to mark a report verified unless all five canonical panels are complete.

The current prototype can deterministically derive bounded TEXT/DIRECT_EFFECT
candidates from earlier structured passes. LEFT/RIGHT prose is intentionally not
invented here: a publishable advocacy statement must arrive as an explicitly authored
``public_interpretation`` on the corresponding lens packet and remains classified as
INTERPRETATION.
"""
from __future__ import annotations

import argparse
import json
import re
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from engine.schemas import BillAnalysis, Citation, Claim, Panel
from engine import text_referee, so_what, comprehension, meaning, fiscal_materiality, human_consequence

ROOT = Path(__file__).resolve().parents[1]
REFEREE_DIR = ROOT / "data" / "referee"
TRANSLATION_DIR = ROOT / "data" / "translations"
MONEY_DIR = ROOT / "data" / "money"
POWER_DIR = ROOT / "data" / "power"
BARREL_DIR = ROOT / "data" / "barrel_scan"
LEFT_DIR = ROOT / "data" / "left_lens"
RIGHT_DIR = ROOT / "data" / "right_lens"
SYNTHESIS_DIR = ROOT / "data" / "synthesis"
ANALYSIS_DIR = ROOT / "data" / "analyses"
PROVING_GROUND_BILLS = ("aca", "obbba")
SYNTHESIZER_VERSION = "31.4-grandma-test"

PANEL_ORDER = (
    "what_it_really_does",
    "follow_the_money",
    "barrel_scan",
    "who_wins_pays_power",
    "left_right_text",
)
PANEL_TITLES = {
    "what_it_really_does": "What You Should Know",
    "follow_the_money": "Follow the Money",
    "barrel_scan": "What Deserves Scrutiny",
    "who_wins_pays_power": "Who Wins / Who Pays / Who Gets Power",
    "left_right_text": "Left | Right | Text",
}


@dataclass(frozen=True)
class Candidate:
    panel_key: str
    claim: Claim
    score: float
    anchor_id: str
    source_kind: str
    materiality_amount: float = 0.0


@dataclass(frozen=True)
class SynthesisResult:
    schema_version: str
    synthesizer_version: str
    bill_id: str
    analysis_status: str
    candidate_count: int
    selected_count: int
    rejected_count: int
    missing_public_lanes: list[str]
    analysis: dict


def _index(directory: Path, bill_id: str, key: str) -> dict[str, dict]:
    path = directory / f"{bill_id}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["anchor_id"]): item
        for item in payload.get(key, [])
        if item.get("anchor_id")
    }


def _referee(bill_id: str) -> dict[str, dict]:
    return _index(REFEREE_DIR, bill_id, "decisions")


def _citation(decision: dict) -> Citation:
    return Citation(
        bill_id=str(decision["bill_id"]),
        anchor_id=str(decision["anchor_id"]),
        section=str(decision.get("section_label") or decision.get("segment_id") or "Source section"),
        source_url=decision.get("source_url") or None,
        document_ref=decision.get("document_ref") or None,
        excerpt=(decision.get("evidence_snapshot") or {}).get("text_excerpt") or None,
        location_marker=decision.get("location_marker") or None,
    )


def _clean(text: str, limit: int = 420) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip(" ,;:") + "…"


def _public_language_ok(text: str | None) -> bool:
    """Pass 28.1: keep statutory edit-code/legalese off the five-panel surface."""
    if not text:
        return False
    compact = " ".join(str(text).split())
    low = compact.lower()
    legal_markers = (
        "read as follows", "<note", "subsection (", "paragraph (", "clause (",
        "qualified opportunity zone business--", "is amended by", "is amended to",
        "striking", "inserting", "redesignated", "u.s.c.",
    )
    if len(compact) > 340 or any(marker in low for marker in legal_markers):
        return False
    if compact.count("(") >= 4 or compact.count(";") >= 5:
        return False
    return True


def _max_money_amount(finding: dict) -> float:
    # Pass 28.2: selector and auditor share one fiscal-materiality ontology.
    assessment = fiscal_materiality.assess(finding)
    return assessment.amount if assessment.actionable else 0.0


def _money_importance_bonus(finding: dict) -> float:
    assessment = fiscal_materiality.assess(finding)
    return assessment.score

def _amounts_rendered(finding: dict) -> list[str]:
    rendered: list[str] = []
    for amount in finding.get("amounts", [])[:3]:
        if isinstance(amount, dict):
            rendered.append(str(amount.get("raw") or amount.get("normalized") or "").strip())
        else:
            rendered.append(str(amount).strip())
    return [item for item in rendered if item]


def _money_text(finding: dict) -> str | None:
    text, _why = so_what.money_explanation(finding)
    return text


def _money_why(finding: dict) -> str | None:
    _text, why = so_what.money_explanation(finding)
    return why


def _power_text(finding: dict) -> str | None:
    text, _why = so_what.power_explanation(finding)
    return text


def _power_why(finding: dict) -> str | None:
    _text, why = so_what.power_explanation(finding)
    return why


def _barrel_text(candidate: dict) -> tuple[str | None, str | None, str | None]:
    return so_what.scrutiny_explanation(candidate)


def _ordinary_explanation(candidate: dict) -> str:
    labels = {str(item) for item in candidate.get("labels", []) if item}
    if "Narrow Carve-Out" in labels or "Highly Specific Beneficiary" in labels:
        return "A narrow rule can be legitimate when lawmakers are fixing a specific problem or defining who is actually eligible. The flag alone does not show favoritism or misconduct."
    if "Potential Rider" in labels or "Scope Surprise" in labels:
        return "Large bills often combine multiple negotiated policies. A surprising topic may have a legitimate legislative reason for being included."
    if "Cross-Reference Opacity" in labels:
        return "Cross-references are common in statutes because Congress often edits existing law instead of rewriting it. Opacity is a reason to inspect, not proof of a bad purpose."
    return "There may be an ordinary policy or drafting explanation. Bill X-Ray flags the pattern for scrutiny; it does not infer motive or wrongdoing."


def _plain_why(anchor_id: str, money: dict, power: dict, barrel: dict) -> str | None:
    parts: list[str] = []
    if anchor_id in money:
        why = _money_why(money.get(anchor_id) or {})
        if why:
            parts.append(why)
    if anchor_id in power:
        why = _power_why(power.get(anchor_id) or {})
        if why:
            parts.append(why)
    if anchor_id in barrel:
        bc = barrel.get(anchor_id) or {}
        if float(bc.get("candidate_score", 0.0)) >= 0.45:
            parts.append("It also triggered an independent scrutiny signal, so it deserves a closer look than routine implementation language.")
    return _clean(" ".join(parts), 320) if parts else None


def _translation_text(translation: dict) -> str | None:
    if translation.get("status") != "translated":
        return None
    text = _clean(translation.get("plain_english") or "")
    if not text:
        return None
    # Pass 18 public-language gate: a mechanically safe translation can still be too
    # source-like for the Kitchen Table Test. Keep it in evidence, not on the main panel.
    legal_noise = (
        "read as follows", "<note", "qualified opportunity zone business--",
        "is amended by", "is amended to", "striking", "inserting",
        "u.s.c.", "subsection (", "paragraph (", "clause (",
    )
    lowered = text.lower()
    # Pass 20: front-page language must read like an explanation, not legislative edit code.
    # The underlying translation remains preserved in evidence even when filtered here.
    if len(text) > 285 or any(token in lowered for token in legal_noise):
        return None
    if re.match(r"^(?:\d+[a-z-]*\([^)]*\)|\d+\s+u\.s\.c\.)", lowered):
        return None
    return text


def _translation_text_for_lens(translation: dict) -> str | None:
    """Return a bounded source-grounded TEXT proposition for Panel 5.

    Panel 5 has a different job from WHAT IT REALLY DOES: it needs a neutral referee
    proposition on the exact same anchor as LEFT and RIGHT. A translation can be too
    source-like for the main public-effects panel yet still be a valid bounded TEXT
    proposition. We therefore keep the translator's own wording, never invent new
    prose here, reject markup-like corruption, and cap display length.
    """
    if translation.get("status") != "translated":
        return None
    raw = " ".join(str(translation.get("plain_english") or "").split())
    if not raw or "<note" in raw.lower():
        return None
    return _clean(raw, 260)


def _text_referee_for_lens(bill_id: str, anchor_id: str, decision: dict) -> tuple[str | None, float, str | None]:
    """Construct Panel 5 TEXT directly from the verified statutory anchor.

    This deliberately does not depend on Pass 5 translation status. The Neutral
    Referee still controls whether TEXT is admissible; construction only supplies a
    bounded source proposition when that lane is allowed.
    """
    if not _allowed(decision, "TEXT"):
        return None, 0.0, "text_not_admissible"
    try:
        statement = text_referee.construct_text_referee(bill_id, anchor_id)
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return None, 0.0, f"text_referee_resolution_failed:{exc}"
    if statement.status != "constructed" or not statement.text:
        return None, 0.0, statement.reason or "text_referee_unusable"
    confidence = min(
        float(statement.confidence),
        float(decision.get("text_lane", {}).get("confidence", 1.0)),
    )
    return statement.text, confidence, None


def _lens_text(packet: dict) -> str | None:
    """Return only explicitly authored advocacy prose.

    Pass 14 never converts prompts, questions, or routing metadata into an argument.
    That would create unsupported political prose. A future model/human execution step
    may populate this field, but its evidence identity must remain unchanged.
    """
    text = packet.get("public_interpretation")
    return _clean(text) if isinstance(text, str) and text.strip() else None


def _allowed(decision: dict, claim_class: str) -> bool:
    if decision.get("status") == "blocked":
        return False
    return claim_class in set(decision.get("admissible_claim_classes", []))


def collect_candidates(bill_id: str) -> list[Candidate]:
    referee = _referee(bill_id)
    if not referee:
        raise FileNotFoundError(f"Pass 13 referee output not found for {bill_id}")

    translations = _index(TRANSLATION_DIR, bill_id, "translations")
    money = _index(MONEY_DIR, bill_id, "findings")
    power = _index(POWER_DIR, bill_id, "findings")
    barrel = _index(BARREL_DIR, bill_id, "candidates")
    left = _index(LEFT_DIR, bill_id, "candidates")
    right = _index(RIGHT_DIR, bill_id, "candidates")

    candidates: list[Candidate] = []
    for anchor_id, decision in referee.items():
        if decision.get("status") == "blocked":
            continue
        cite = _citation(decision)
        base = float(decision.get("confidence", 0.0))

        translated = translations.get(anchor_id)
        plain = _translation_text(translated or {})
        lens_plain, lens_confidence, _lens_reason = _text_referee_for_lens(bill_id, anchor_id, decision)
        # Pass 24: the main panel prefers a concrete money/power consequence over a
        # merely translatable sentence. Detection is not publication; finish the thought.
        effect_text, effect_why, effect_kind = so_what.main_effect_from_findings(money.get(anchor_id), power.get(anchor_id))
        if effect_text and _public_language_ok(effect_text) and _allowed(decision, "DIRECT_EFFECT"):
            source_packet = power.get(anchor_id) if effect_kind == "power" else money.get(anchor_id)
            confidence = min(float((source_packet or {}).get("confidence", 0.0)), float(decision.get("direct_effect_lane", {}).get("confidence", 1.0)))
            effect_meta = human_consequence.power_fields(source_packet or {}) if effect_kind == "power" else human_consequence.money_fields(source_packet or {})
            effect_claim = Claim(text=effect_text, claim_class="DIRECT_EFFECT", confidence=confidence, citations=[cite], direct_effect=True, plain_explanation=effect_text, why_it_matters=effect_why, semantic_source_kind=effect_kind, **effect_meta)
            effect_bonus = 0.85 + (0.35 * _money_importance_bonus(money.get(anchor_id) or {}) if effect_kind == "money" else 0.30)
            candidates.append(Candidate("what_it_really_does", effect_claim, base + confidence + effect_bonus, anchor_id, f"{effect_kind}_effect"))

        if plain and _allowed(decision, "TEXT"):
            confidence = min(float((translated or {}).get("confidence", 0.0)), float(decision.get("text_lane", {}).get("confidence", 1.0)))
            plain_why = _plain_why(anchor_id, money, power, barrel)
            challenge = comprehension.evaluate_text(plain, plain_why)
            claim = Claim(text=plain, claim_class="TEXT", confidence=confidence, citations=[cite], lens="TEXT", plain_explanation=plain, why_it_matters=plain_why)
            impact_bonus = 0.0
            if anchor_id in money:
                impact_bonus += 0.20 + 0.35 * _money_importance_bonus(money.get(anchor_id) or {})
            if anchor_id in power:
                impact_bonus += 0.20
            if anchor_id in barrel:
                impact_bonus += 0.15 + 0.35 * float((barrel.get(anchor_id) or {}).get("candidate_score", 0.0))
            if challenge.publish:
                candidates.append(Candidate("what_it_really_does", claim, base + confidence + 0.25 + impact_bonus, anchor_id, "translation"))
        if lens_plain:
            lens_claim = Claim(text=lens_plain, claim_class="TEXT", confidence=lens_confidence, citations=[cite], lens="TEXT")
            candidates.append(Candidate("left_right_text", lens_claim, base + lens_confidence + 0.20, anchor_id, "text_referee"))

        mf = money.get(anchor_id)
        money_packet = meaning.from_money(mf or {}) if mf else None
        money_challenge = comprehension.evaluate_packet(money_packet) if money_packet else None
        money_text = _money_text(mf or {})
        if money_text and _public_language_ok(money_text) and money_challenge and money_challenge.publish and _allowed(decision, "DIRECT_EFFECT"):
            confidence = min(float((mf or {}).get("confidence", 0.0)), float(decision.get("direct_effect_lane", {}).get("confidence", 1.0)))
            money_meta = human_consequence.money_fields(mf or {})
            claim = Claim(text=money_text, claim_class="DIRECT_EFFECT", confidence=confidence, citations=[cite], direct_effect=True, plain_explanation=money_text, why_it_matters=_money_why(mf or {}), public_title="Money consequence", **money_meta)
            quantified_bonus = _money_importance_bonus(mf or {})
            candidates.append(Candidate("follow_the_money", claim, base + confidence + quantified_bonus, anchor_id, "money", _max_money_amount(mf or {})))

        pf = power.get(anchor_id)
        power_packet = meaning.from_power(pf or {}) if pf else None
        power_challenge = comprehension.evaluate_packet(power_packet) if power_packet else None
        power_text = _power_text(pf or {})
        if power_text and _public_language_ok(power_text) and power_challenge and power_challenge.publish and _allowed(decision, "DIRECT_EFFECT"):
            confidence = min(float((pf or {}).get("confidence", 0.0)), float(decision.get("direct_effect_lane", {}).get("confidence", 1.0)))
            power_meta = human_consequence.power_fields(pf or {})
            claim = Claim(text=power_text, claim_class="DIRECT_EFFECT", confidence=confidence, citations=[cite], direct_effect=True, plain_explanation=power_text, why_it_matters=_power_why(pf or {}), public_title="Authority consequence", **power_meta)
            candidates.append(Candidate("who_wins_pays_power", claim, base + confidence + 0.15, anchor_id, "power"))

        bc = barrel.get(anchor_id)
        barrel_text, barrel_label, why = _barrel_text(bc or {})
        public_scrutiny = human_consequence.scrutiny_public(bc or {}, mf, pf, plain) if bc else {}
        public_plain = public_scrutiny.get("plain") or barrel_text
        public_why = public_scrutiny.get("why") or why
        if public_plain and _public_language_ok(public_plain) and decision.get("barrel_lane", {}).get("status") == "admissible_as_scrutiny_flag":
            confidence = min(float((bc or {}).get("confidence", 0.0)), float(decision.get("barrel_lane", {}).get("confidence", 1.0)))
            consequence_meta = {}
            consequence_meta.update(human_consequence.money_fields(mf or {}))
            for key, value in human_consequence.power_fields(pf or {}).items():
                if value and not consequence_meta.get(key):
                    consequence_meta[key] = value
            claim = Claim(
                text=public_plain,
                claim_class="DIRECT_EFFECT",
                confidence=confidence,
                citations=[cite],
                barrel_label=barrel_label,
                public_title=public_scrutiny.get("title"),
                why_flagged=public_why,
                direct_effect=True,
                plain_explanation=public_plain,
                why_it_matters="This ranks highly because multiple independent signals make it less routine and more deserving of a public explanation.",
                ordinary_explanation=_ordinary_explanation(bc or {}),
                scrutiny_score=round(float((bc or {}).get("candidate_score", 0.0)) * 100.0, 1),
                **consequence_meta,
            )
            score = base + confidence + float((bc or {}).get("candidate_score", 0.0))
            candidates.append(Candidate("barrel_scan", claim, score, anchor_id, "barrel_scan"))

        for packet, lens in ((left.get(anchor_id), "LEFT"), (right.get(anchor_id), "RIGHT")):
            prose = _lens_text(packet or {})
            lane = decision.get("left_lane" if lens == "LEFT" else "right_lane", {})
            if prose and lane.get("status") == "admissible_as_interpretation" and _allowed(decision, "INTERPRETATION"):
                confidence = min(float((packet or {}).get("confidence", 0.0)), float(lane.get("confidence", 1.0)))
                claim = Claim(text=prose, claim_class="INTERPRETATION", confidence=confidence, citations=[cite], lens=lens)
                candidates.append(Candidate("left_right_text", claim, base + confidence, anchor_id, f"{lens.lower()}_lens"))

    return candidates



def diagnose_lens_surface(bill_id: str) -> dict:
    """Explain why authored LEFT/RIGHT/TEXT anchors are or are not publishable."""
    referee = _referee(bill_id)
    translations = _index(TRANSLATION_DIR, bill_id, "translations")
    left = _index(LEFT_DIR, bill_id, "candidates")
    right = _index(RIGHT_DIR, bill_id, "candidates")
    authored = sorted(
        aid for aid in set(left) & set(right)
        if _lens_text(left.get(aid, {})) and _lens_text(right.get(aid, {}))
    )
    rows: list[dict] = []
    complete: list[str] = []
    for aid in authored:
        decision = referee.get(aid)
        reasons: list[str] = []
        if not decision:
            reasons.append("no_referee_decision")
        else:
            if decision.get("status") == "blocked":
                reasons.append("referee_blocked")
            if not _allowed(decision, "INTERPRETATION"):
                reasons.append("interpretation_not_admissible")
            if decision.get("left_lane", {}).get("status") != "admissible_as_interpretation":
                reasons.append("left_lane_not_admissible")
            if decision.get("right_lane", {}).get("status") != "admissible_as_interpretation":
                reasons.append("right_lane_not_admissible")
            if not _allowed(decision, "TEXT"):
                reasons.append("text_not_admissible")
        trans = translations.get(aid, {})
        text_status = "not_attempted"
        text_preview = None
        if decision and not reasons:
            text_value, _conf, text_reason = _text_referee_for_lens(bill_id, aid, decision)
            if text_value:
                text_status = "constructed"
                text_preview = _clean(text_value, 160)
            else:
                text_status = "unusable"
                reasons.append(text_reason or "text_referee_unusable")
        elif decision:
            # Even when another lane blocks the trio, report whether TEXT itself could be built.
            text_value, _conf, text_reason = _text_referee_for_lens(bill_id, aid, decision)
            if text_value:
                text_status = "constructed"
                text_preview = _clean(text_value, 160)
            else:
                text_status = "unusable"
                if text_reason and text_reason not in reasons:
                    reasons.append(text_reason)
        if not reasons:
            complete.append(aid)
        rows.append({
            "anchor_id": aid,
            "section_label": (left.get(aid) or {}).get("section_label") or (right.get(aid) or {}).get("section_label") or "",
            "referee_status": (decision or {}).get("status", "missing"),
            "translation_status": trans.get("status", "missing"),
            "text_referee_status": text_status,
            "text_referee_preview": text_preview,
            "complete": not reasons,
            "reasons": reasons,
        })
    return {
        "bill_id": bill_id,
        "authored_pair_count": len(authored),
        "complete_anchor_count": len(complete),
        "complete_anchor_ids": complete,
        "anchors": rows,
    }

def _dedupe_rank(candidates: Iterable[Candidate], limit: int = 3) -> list[Candidate]:
    candidates = list(candidates)
    # Pass 28.1: Follow the Money is a materiality surface. Explicit statutory
    # dollars outrank generic confidence/heuristic score so a small but tidy finding
    # cannot crowd out a much larger quantified provision. Score breaks ties.
    if candidates and all(item.panel_key == "follow_the_money" for item in candidates):
        ordered = sorted(candidates, key=lambda item: (-item.materiality_amount, -item.score, item.anchor_id, item.source_kind))
    else:
        ordered = sorted(candidates, key=lambda item: (-item.score, item.anchor_id, item.source_kind))
    selected: list[Candidate] = []
    seen_text: set[str] = set()
    seen_anchor: set[str] = set()
    for candidate in ordered:
        normalized = re.sub(r"\W+", " ", candidate.claim.text.lower()).strip()
        if normalized in seen_text:
            continue
        # Prefer breadth: one public bullet per anchor per panel unless a special panel
        # such as LEFT|RIGHT|TEXT explicitly needs multiple lanes from the same anchor.
        if candidate.panel_key != "left_right_text" and candidate.anchor_id in seen_anchor:
            continue
        selected.append(candidate)
        seen_text.add(normalized)
        seen_anchor.add(candidate.anchor_id)
        if len(selected) >= limit:
            break
    return selected


def assemble_analysis(bill_id: str, candidates: list[Candidate]) -> BillAnalysis:
    grouped = {key: [c for c in candidates if c.panel_key == key] for key in PANEL_ORDER}
    panels: list[Panel] = []
    missing: list[str] = []

    for key in PANEL_ORDER:
        if key == "left_right_text":
            selected = []
            by_anchor: dict[str, dict[str, Candidate]] = {}
            for candidate in grouped[key]:
                if candidate.claim.lens in {"LEFT", "RIGHT", "TEXT"}:
                    by_anchor.setdefault(candidate.anchor_id, {})[candidate.claim.lens] = candidate
            complete = []
            for anchor_id, lanes in by_anchor.items():
                if all(lens in lanes for lens in ("LEFT", "RIGHT", "TEXT")):
                    score = sum(lanes[lens].score for lens in ("LEFT", "RIGHT", "TEXT")) / 3.0
                    complete.append((score, anchor_id, lanes))
            if complete:
                _, _, lanes = sorted(complete, key=lambda row: (-row[0], row[1]))[0]
                selected = [lanes[lens] for lens in ("LEFT", "RIGHT", "TEXT")]
            else:
                lane_missing = []
                for lens in ("LEFT", "RIGHT", "TEXT"):
                    if not any(c.claim.lens == lens for c in grouped[key]):
                        lane_missing.append(f"left_right_text:{lens}")
                if lane_missing:
                    missing.extend(lane_missing)
                else:
                    missing.append("left_right_text:unaligned_evidence")
        else:
            selected = _dedupe_rank(grouped[key], 3)
            if key == "what_it_really_does" and not selected:
                missing.append(key)
        panels.append(Panel(key=key, title=PANEL_TITLES[key], claims=[item.claim for item in selected]))

    status = "verified" if not missing else "draft"
    return BillAnalysis(bill_id=bill_id, analysis_status=status, panels=panels)


def synthesize_bill(bill_id: str, *, write: bool = True) -> SynthesisResult:
    candidates = collect_candidates(bill_id)
    analysis = assemble_analysis(bill_id, candidates)
    selected_count = sum(len(panel.claims) for panel in analysis.panels)
    missing: list[str] = []
    for panel in analysis.panels:
        if panel.key == "what_it_really_does" and not panel.claims:
            missing.append(panel.key)
    lens_panel = next((p for p in analysis.panels if p.key == "left_right_text"), None)
    if lens_panel:
        present = {claim.lens for claim in lens_panel.claims}
        for lens in ("LEFT", "RIGHT", "TEXT"):
            if lens not in present:
                missing.append(f"left_right_text:{lens}")

    result = SynthesisResult(
        schema_version="26.0",
        synthesizer_version=SYNTHESIZER_VERSION,
        bill_id=bill_id,
        analysis_status=analysis.analysis_status,
        candidate_count=len(candidates),
        selected_count=selected_count,
        rejected_count=max(0, len(candidates) - selected_count),
        missing_public_lanes=list(dict.fromkeys(missing)),
        analysis=analysis.model_dump(mode="json"),
    )
    if write:
        SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        (SYNTHESIS_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        (ANALYSIS_DIR / f"{bill_id}.json").write_text(json.dumps(result.analysis, indent=2), encoding="utf-8")
    return result


def synthesis_status() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        path = SYNTHESIS_DIR / f"{bill_id}.json"
        state: dict[str, object] = {
            "synthesis_ready": False,
            "analysis_status": "not_generated",
            "candidate_count": 0,
            "selected_count": 0,
            "missing_public_lanes": list(PANEL_ORDER),
            "synthesizer_version": SYNTHESIZER_VERSION,
        }
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            state.update({
                "synthesis_ready": payload.get("analysis_status") == "verified",
                "analysis_status": payload.get("analysis_status", "draft"),
                "candidate_count": int(payload.get("candidate_count", 0)),
                "selected_count": int(payload.get("selected_count", 0)),
                "missing_public_lanes": list(payload.get("missing_public_lanes", [])),
            })
        result[bill_id] = state
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Pass 14 five-panel public synthesis.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            result = synthesize_bill(bill_id)
            print(
                f"{bill_id}: {result.analysis_status}; {result.selected_count} public claims selected; "
                f"missing lanes: {', '.join(result.missing_public_lanes) or 'none'}"
            )
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
