"""Pass 5: evidence-preserving plain-English translation for Bill X-Ray.

This module is intentionally conservative. It translates only legal mechanics that
can be tied to a verified Pass 4 citation anchor. It does not infer legislative
intent, political meaning, winners/losers, fiscal effects, or second-order effects.

When the rule engine cannot safely simplify a provision, it returns an explicit
review state instead of manufacturing a fluent explanation. Later model-backed
translation can sit behind the same contract, but it must obey these invariants.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from engine import citations

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
TRANSLATION_DIR = ROOT / "data" / "translations"
PROVING_GROUND_BILLS = ("aca", "obbba")
TRANSLATOR_VERSION = "31.6.2.4-modal-qualifier-integrity"

_SECTION_HEADING = re.compile(r"^(?:SEC(?:TION)?\.?\s+\S+.*)$", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(\[])")

# Qualifiers that materially constrain a legal proposition and therefore must not
# disappear during simplification.
_QUALIFIER_PATTERNS = (
    re.compile(r"\bexcept(?: that)?\b[^.;]*", re.IGNORECASE),
    re.compile(r"\bunless\b[^.;]*", re.IGNORECASE),
    re.compile(r"\bsubject to\b[^.;]*", re.IGNORECASE),
    re.compile(r"\bnotwithstanding\b[^.;]*", re.IGNORECASE),
    re.compile(r"\bprovided(?:,)? that\b[^.;]*", re.IGNORECASE),
    re.compile(r"\bnot later than\b[^.;]*", re.IGNORECASE),
    re.compile(r"\bno later than\b[^.;]*", re.IGNORECASE),
    re.compile(r"\bbeginning (?:on|after|with)\b[^.;]*", re.IGNORECASE),
    re.compile(r"\beffective (?:on|after|for)\b[^.;]*", re.IGNORECASE),
)


@dataclass(frozen=True)
class PlainEnglishTranslation:
    schema_version: str
    translator_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    status: str
    claim_class: str
    confidence: float
    plain_english: str | None
    source_excerpt: str
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str
    preserved_qualifiers: list[str]
    legal_signals: list[str]
    review_reason: str | None


@dataclass(frozen=True)
class TranslationIndex:
    schema_version: str
    bill_id: str
    translator_version: str
    source_sha256: str
    translated_count: int
    review_count: int
    translations: list[PlainEnglishTranslation]


def _body_from_anchor(exact_text: str) -> str:
    lines = [line.strip() for line in exact_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    if lines and _SECTION_HEADING.match(lines[0]):
        lines = lines[1:]
    return " ".join(lines).strip()


def _sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    return parts or [text.strip()]


def _qualifiers(text: str) -> list[str]:
    found: list[str] = []
    for pattern in _QUALIFIER_PATTERNS:
        for match in pattern.finditer(text):
            value = " ".join(match.group(0).split()).strip(" ,")
            if value and value.lower() not in {item.lower() for item in found}:
                found.append(value)
    return found




def _qualifier_integrity_form(text: str) -> str:
    """Normalize only modal rewrites that this translator itself is allowed to make.

    The qualifier gate remains exact for every other token. This prevents a legitimate
    ``shall`` -> ``must`` or ``may`` -> ``is allowed to`` translation from being
    misdiagnosed as a lost qualifier while still failing closed on any substantive drift.
    """
    value = " ".join(str(text or "").split()).lower()
    replacements = (
        (r"\bshall not\b", "__must_not__"),
        (r"\bmust not\b", "__must_not__"),
        (r"\bmay not\b", "__may_not__"),
        (r"\bis not allowed to\b", "__may_not__"),
        (r"\bshall\b", "__must__"),
        (r"\bmust\b", "__must__"),
        (r"\bis allowed to\b", "__may__"),
        (r"\bmay\b", "__may__"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value

def _legal_signals(text: str) -> list[str]:
    checks = (
        ("shall", r"\bshall\b"),
        ("must", r"\bmust\b"),
        ("may", r"\bmay\b"),
        ("may not", r"\bmay not\b"),
        ("prohibition", r"\b(?:prohibit(?:ed|s)?|shall not|must not)\b"),
        ("amendment", r"\b(?:is|are) amended\b|\bamended by\b"),
        ("repeal", r"\b(?:is|are) repealed\b|\brepeal(?:s|ed)?\b"),
        ("definition", r"\bmeans\b|\bincludes\b"),
        ("appropriation", r"\bappropriat(?:e|ed|ion|ions)\b"),
    )
    return [label for label, pattern in checks if re.search(pattern, text, re.IGNORECASE)]


def _translate_sentence(sentence: str) -> tuple[str | None, float, str | None]:
    """Translate only high-confidence statutory constructions.

    The replacements intentionally stay close to the source. This is a floor, not
    the final stylistic ceiling. More ambitious language-model translation must
    later prove that it preserved every legally material constraint.
    """
    original = " ".join(sentence.split())
    lowered = original.lower()

    # Citation/naming provisions are legal mechanics, not substantive program effects.
    cited = re.match(r"^(This (?:Act|title|subtitle|section)) may be cited as (.+?)[.]?$", original, re.IGNORECASE)
    if cited:
        return f"{cited.group(1)} may be called {cited.group(2).rstrip('.') }.", 0.98, None

    if re.search(r"\bshall not\b", original, re.IGNORECASE):
        translated = re.sub(r"\bshall not\b", "must not", original, flags=re.IGNORECASE)
        return translated, 0.97, None

    if re.search(r"\bshall\b", original, re.IGNORECASE):
        translated = re.sub(r"\bshall\b", "must", original, flags=re.IGNORECASE)
        return translated, 0.97, None

    if re.search(r"\bmay not\b", original, re.IGNORECASE):
        translated = re.sub(r"\bmay not\b", "is not allowed to", original, count=1, flags=re.IGNORECASE)
        return translated, 0.94, None

    # Permission: preserve discretion. "May" is not rewritten as "will" or "must."
    may_match = re.match(r"^(.+?)\s+may\s+(.+)$", original, re.IGNORECASE)
    if may_match:
        subject = may_match.group(1).strip()
        action = may_match.group(2).strip()
        return f"{subject} is allowed to {action}", 0.93, None

    amended = re.match(r"^(.+?)\s+(?:is|are) amended by\s+(.+)$", original, re.IGNORECASE)
    if amended:
        return f"{amended.group(1).strip()} is changed by {amended.group(2).strip()}", 0.90, None

    repealed = re.match(r"^(.+?)\s+(?:is|are) repealed[.]?$", original, re.IGNORECASE)
    if repealed:
        return f"{repealed.group(1).strip()} is repealed.", 0.96, None

    # Do not paraphrase definitions or dense cross-reference language with weak rules.
    if " means " in f" {lowered} " or " includes " in f" {lowered} ":
        return None, 0.72, "Definition language requires context-preserving review."
    if re.search(r"\bsection\s+\d+[A-Za-z0-9()\-]*\s+of\b", original, re.IGNORECASE):
        return None, 0.68, "Cross-reference-heavy language requires context-preserving review."

    return None, 0.60, "No high-confidence statutory translation rule matched this language."


def translate_anchor_payload(anchor: dict) -> PlainEnglishTranslation:
    required = (
        "anchor_id", "bill_id", "segment_id", "section_label", "location_marker",
        "document_ref", "source_url", "source_sha256", "text_sha256", "exact_text",
    )
    missing = [key for key in required if key not in anchor]
    if missing:
        raise ValueError(f"Verified anchor is missing required fields: {', '.join(missing)}")
    if not anchor.get("verified"):
        raise ValueError("Plain-English translation requires a verified Pass 4 anchor")

    body = _body_from_anchor(str(anchor["exact_text"]))
    qualifiers = _qualifiers(body)
    signals = _legal_signals(body)
    source_excerpt = " ".join(body.split())[:700]

    if not body:
        return PlainEnglishTranslation(
            schema_version="5.0", translator_version=TRANSLATOR_VERSION,
            bill_id=str(anchor["bill_id"]), anchor_id=str(anchor["anchor_id"]),
            segment_id=str(anchor["segment_id"]), section_label=str(anchor["section_label"]),
            status="needs_expert_review", claim_class="UNKNOWN", confidence=0.20,
            plain_english=None, source_excerpt=source_excerpt,
            location_marker=str(anchor["location_marker"]), document_ref=str(anchor["document_ref"]),
            source_url=str(anchor["source_url"]), source_sha256=str(anchor["source_sha256"]),
            text_sha256=str(anchor["text_sha256"]), preserved_qualifiers=qualifiers,
            legal_signals=signals, review_reason="The anchored segment has no substantive body text."
        )

    translated_parts: list[str] = []
    confidences: list[float] = []
    review_reasons: list[str] = []
    for sentence in _sentences(body):
        translated, confidence, reason = _translate_sentence(sentence)
        if translated is None:
            review_reasons.append(reason or "Review required.")
        else:
            translated_parts.append(translated)
            confidences.append(confidence)

    # A partial translation is not good enough for Bill X-Ray. Every sentence in the
    # anchored body must survive translation, otherwise the unit stays in review.
    if review_reasons or not translated_parts:
        confidence = min(confidences + [0.74]) if confidences else 0.60
        return PlainEnglishTranslation(
            schema_version="5.0", translator_version=TRANSLATOR_VERSION,
            bill_id=str(anchor["bill_id"]), anchor_id=str(anchor["anchor_id"]),
            segment_id=str(anchor["segment_id"]), section_label=str(anchor["section_label"]),
            status="needs_expert_review", claim_class="UNKNOWN", confidence=confidence,
            plain_english=None, source_excerpt=source_excerpt,
            location_marker=str(anchor["location_marker"]), document_ref=str(anchor["document_ref"]),
            source_url=str(anchor["source_url"]), source_sha256=str(anchor["source_sha256"]),
            text_sha256=str(anchor["text_sha256"]), preserved_qualifiers=qualifiers,
            legal_signals=signals, review_reason=" ".join(dict.fromkeys(review_reasons))
        )

    plain = " ".join(translated_parts)
    # Qualifier integrity check: if a qualifier appeared in source, its normalized text
    # must still appear in the candidate. Failure routes the unit to review.
    plain_integrity = _qualifier_integrity_form(plain)
    lost = [q for q in qualifiers if _qualifier_integrity_form(q) not in plain_integrity]
    if lost:
        return PlainEnglishTranslation(
            schema_version="5.0", translator_version=TRANSLATOR_VERSION,
            bill_id=str(anchor["bill_id"]), anchor_id=str(anchor["anchor_id"]),
            segment_id=str(anchor["segment_id"]), section_label=str(anchor["section_label"]),
            status="needs_expert_review", claim_class="UNKNOWN", confidence=0.55,
            plain_english=None, source_excerpt=source_excerpt,
            location_marker=str(anchor["location_marker"]), document_ref=str(anchor["document_ref"]),
            source_url=str(anchor["source_url"]), source_sha256=str(anchor["source_sha256"]),
            text_sha256=str(anchor["text_sha256"]), preserved_qualifiers=qualifiers,
            legal_signals=signals,
            review_reason="Automatic translation would lose a legally material qualifier: " + "; ".join(lost)
        )

    return PlainEnglishTranslation(
        schema_version="5.0", translator_version=TRANSLATOR_VERSION,
        bill_id=str(anchor["bill_id"]), anchor_id=str(anchor["anchor_id"]),
        segment_id=str(anchor["segment_id"]), section_label=str(anchor["section_label"]),
        status="translated", claim_class="TEXT", confidence=min(confidences),
        plain_english=plain, source_excerpt=source_excerpt,
        location_marker=str(anchor["location_marker"]), document_ref=str(anchor["document_ref"]),
        source_url=str(anchor["source_url"]), source_sha256=str(anchor["source_sha256"]),
        text_sha256=str(anchor["text_sha256"]), preserved_qualifiers=qualifiers,
        legal_signals=signals, review_reason=None
    )


def translate_anchor(bill_id: str, anchor_id: str) -> PlainEnglishTranslation:
    anchor = citations.resolve_anchor(bill_id, anchor_id)
    return translate_anchor_payload(anchor)


def translate_bill(bill_id: str, *, write: bool = True) -> TranslationIndex:
    anchor_path = ANCHOR_DIR / f"{bill_id}.json"
    if not anchor_path.exists():
        raise FileNotFoundError(f"Citation anchors not found: {anchor_path}")
    index = json.loads(anchor_path.read_text(encoding="utf-8"))
    translations: list[PlainEnglishTranslation] = []
    for anchor in index.get("anchors", []):
        if anchor.get("kind") != "section":
            continue
        translations.append(translate_anchor(bill_id, str(anchor["anchor_id"])))

    result = TranslationIndex(
        schema_version="5.0",
        bill_id=bill_id,
        translator_version=TRANSLATOR_VERSION,
        source_sha256=str(index.get("source_sha256", "")),
        translated_count=sum(item.status == "translated" for item in translations),
        review_count=sum(item.status != "translated" for item in translations),
        translations=translations,
    )
    if write:
        TRANSLATION_DIR.mkdir(parents=True, exist_ok=True)
        (TRANSLATION_DIR / f"{bill_id}.json").write_text(
            json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return result


def translate_available(*, write: bool = True) -> dict[str, list[str]]:
    translated: list[str] = []
    missing_anchors: list[str] = []
    failed: list[str] = []
    for bill_id in PROVING_GROUND_BILLS:
        if not (ANCHOR_DIR / f"{bill_id}.json").exists():
            missing_anchors.append(bill_id)
            continue
        try:
            translate_bill(bill_id, write=write)
            translated.append(bill_id)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            failed.append(bill_id)
    return {"translated": translated, "missing_anchors": missing_anchors, "failed": failed}


def translator_status() -> dict[str, dict]:
    status: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        translation_path = TRANSLATION_DIR / f"{bill_id}.json"
        translated_count = 0
        review_count = 0
        source_fingerprint_matches = False
        if translation_path.exists():
            try:
                payload = json.loads(translation_path.read_text(encoding="utf-8"))
                translated_count = int(payload.get("translated_count", 0))
                review_count = int(payload.get("review_count", 0))
                if anchor_path.exists():
                    anchors = json.loads(anchor_path.read_text(encoding="utf-8"))
                    source_fingerprint_matches = payload.get("source_sha256") == anchors.get("source_sha256")
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        status[bill_id] = {
            "translator_contract_ready": True,
            "anchors_present": anchor_path.exists(),
            "translations_present": translation_path.exists(),
            "translated_count": translated_count,
            "review_count": review_count,
            "source_fingerprint_matches": source_fingerprint_matches,
        }
    return status


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build conservative Bill X-Ray plain-English translations")
    parser.add_argument("bill_id", nargs="?", help="bill id, e.g. aca or obbba")
    parser.add_argument("--status", action="store_true", help="show translator readiness")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        print(json.dumps(translator_status(), indent=2))
        return 0
    if args.bill_id:
        result = translate_bill(args.bill_id)
        print(
            f"Translated {result.translated_count:,} sections for {result.bill_id}; "
            f"{result.review_count:,} routed to expert review"
        )
        return 0

    result = translate_available()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
