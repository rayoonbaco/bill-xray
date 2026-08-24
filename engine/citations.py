"""Pass 4: exact, tamper-evident citation anchors for Bill X-Ray.

Citation anchors are deterministic pointers into the canonical text produced by
Pass 2 and the structural boundaries produced by Pass 3. An anchor is not an
interpretation. It says only: these exact canonical source lines, from this exact
source fingerprint, belong to this structural segment.

Later analysis passes must cite anchors rather than free-typing locations. When an
anchor is resolved, Bill X-Ray re-reads the canonical ingested text and verifies
both the source SHA-256 and the exact anchored-text SHA-256. This makes citation
drift detectable before a claim can be shown as verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
INGESTED_DIR = ROOT / "data" / "ingested"
SEGMENT_DIR = ROOT / "data" / "segments"
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
PROVING_GROUND_BILLS = ("aca", "obbba")


@dataclass(frozen=True)
class CitationAnchor:
    anchor_id: str
    bill_id: str
    segment_id: str
    kind: str
    identifier: str
    heading: str
    section_label: str
    start_line: int
    end_line: int
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str
    excerpt: str


@dataclass(frozen=True)
class CitationAnchorIndex:
    schema_version: str
    bill_id: str
    document_ref: str
    source_url: str
    source_sha256: str
    anchor_count: int
    anchors: list[CitationAnchor]


def _canonical_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _exact_slice(text: str, start_line: int, end_line: int) -> str:
    lines = _canonical_lines(text)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise ValueError(
            f"Invalid citation line range {start_line}-{end_line}; source has {len(lines)} lines"
        )
    return "\n".join(lines[start_line - 1 : end_line])


def _excerpt(text: str, limit: int = 320) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _anchor_id(bill_id: str, source_sha256: str, start_line: int, end_line: int, exact_text: str) -> str:
    material = (
        f"{bill_id}\n{source_sha256}\n{start_line}\n{end_line}\n".encode("utf-8")
        + exact_text.encode("utf-8")
    )
    digest = hashlib.sha256(material).hexdigest()[:16]
    return f"bxr-{bill_id}-L{start_line}-L{end_line}-{digest}"


def _section_label(segment: dict) -> str:
    if segment.get("kind") == "section":
        identifier = str(segment.get("identifier", "")).strip()
        return f"SEC. {identifier}" if identifier else str(segment.get("heading", "SECTION"))
    heading = str(segment.get("heading", "")).strip()
    return heading or str(segment.get("identifier", "structural segment"))


def build_anchor_index(bill_id: str, *, write: bool = True) -> CitationAnchorIndex:
    ingested_path = INGESTED_DIR / f"{bill_id}.json"
    segment_path = SEGMENT_DIR / f"{bill_id}.json"
    if not ingested_path.exists():
        raise FileNotFoundError(f"Ingested bill not found: {ingested_path}")
    if not segment_path.exists():
        raise FileNotFoundError(f"Segmented bill not found: {segment_path}")

    ingested = json.loads(ingested_path.read_text(encoding="utf-8"))
    segmented = json.loads(segment_path.read_text(encoding="utf-8"))
    source_sha = str(ingested.get("sha256", ""))
    if not source_sha:
        raise ValueError("Ingested bill is missing its source SHA-256")
    if segmented.get("source_sha256") != source_sha:
        raise ValueError("Segment artifact does not match the current ingested source fingerprint")

    source_text = str(ingested.get("text", ""))
    anchors: list[CitationAnchor] = []
    for segment in segmented.get("segments", []):
        start_line = int(segment["start_line"])
        end_line = int(segment["end_line"])
        exact_text = _exact_slice(source_text, start_line, end_line)
        text_sha = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
        anchor_id = _anchor_id(bill_id, source_sha, start_line, end_line, exact_text)
        anchors.append(
            CitationAnchor(
                anchor_id=anchor_id,
                bill_id=bill_id,
                segment_id=str(segment["segment_id"]),
                kind=str(segment["kind"]),
                identifier=str(segment["identifier"]),
                heading=str(segment["heading"]),
                section_label=_section_label(segment),
                start_line=start_line,
                end_line=end_line,
                location_marker=f"canonical lines {start_line}-{end_line}",
                document_ref=str(ingested.get("document_ref", "")),
                source_url=str(ingested.get("source_url", "")),
                source_sha256=source_sha,
                text_sha256=text_sha,
                excerpt=_excerpt(exact_text),
            )
        )

    result = CitationAnchorIndex(
        schema_version="4.0",
        bill_id=bill_id,
        document_ref=str(ingested.get("document_ref", "")),
        source_url=str(ingested.get("source_url", "")),
        source_sha256=source_sha,
        anchor_count=len(anchors),
        anchors=anchors,
    )
    if write:
        ANCHOR_DIR.mkdir(parents=True, exist_ok=True)
        out = ANCHOR_DIR / f"{bill_id}.json"
        out.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def build_available(*, write: bool = True) -> dict[str, list[str]]:
    anchored: list[str] = []
    missing_segmentation: list[str] = []
    failed: list[str] = []
    for bill_id in PROVING_GROUND_BILLS:
        if not (SEGMENT_DIR / f"{bill_id}.json").exists():
            missing_segmentation.append(bill_id)
            continue
        try:
            build_anchor_index(bill_id, write=write)
            anchored.append(bill_id)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            failed.append(bill_id)
    return {
        "anchored": anchored,
        "missing_segmentation": missing_segmentation,
        "failed": failed,
    }


def resolve_anchor(bill_id: str, anchor_id: str) -> dict:
    """Resolve and re-verify an anchor against the current canonical ingested text."""
    index_path = ANCHOR_DIR / f"{bill_id}.json"
    ingested_path = INGESTED_DIR / f"{bill_id}.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Citation anchors not found: {index_path}")
    if not ingested_path.exists():
        raise FileNotFoundError(f"Ingested bill not found: {ingested_path}")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    ingested = json.loads(ingested_path.read_text(encoding="utf-8"))
    anchor = next((a for a in index.get("anchors", []) if a.get("anchor_id") == anchor_id), None)
    if anchor is None:
        raise KeyError(f"Unknown citation anchor '{anchor_id}' for bill '{bill_id}'")

    current_source_sha = str(ingested.get("sha256", ""))
    if current_source_sha != anchor.get("source_sha256"):
        raise ValueError("Citation source fingerprint no longer matches the ingested bill")

    exact_text = _exact_slice(
        str(ingested.get("text", "")), int(anchor["start_line"]), int(anchor["end_line"])
    )
    current_text_sha = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
    if current_text_sha != anchor.get("text_sha256"):
        raise ValueError("Citation text fingerprint no longer matches the anchored source lines")

    return {**anchor, "verified": True, "exact_text": exact_text}


def citation_status() -> dict[str, dict]:
    status: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        segment_path = SEGMENT_DIR / f"{bill_id}.json"
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        anchor_count = 0
        source_fingerprint_matches = False
        if anchor_path.exists():
            try:
                anchors = json.loads(anchor_path.read_text(encoding="utf-8"))
                anchor_count = int(anchors.get("anchor_count", 0))
                ingested_path = INGESTED_DIR / f"{bill_id}.json"
                if ingested_path.exists():
                    ingested = json.loads(ingested_path.read_text(encoding="utf-8"))
                    source_fingerprint_matches = anchors.get("source_sha256") == ingested.get("sha256")
            except (OSError, ValueError, json.JSONDecodeError):
                anchor_count = 0
                source_fingerprint_matches = False
        status[bill_id] = {
            "segmented_present": segment_path.exists(),
            "anchors_present": anchor_path.exists(),
            "anchor_count": anchor_count,
            "source_fingerprint_matches": source_fingerprint_matches,
        }
    return status


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build exact Bill X-Ray citation anchors")
    parser.add_argument("bill_id", nargs="?", help="bill id, e.g. aca or obbba")
    parser.add_argument("--status", action="store_true", help="show citation-anchor readiness")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        print(json.dumps(citation_status(), indent=2))
        return 0
    if args.bill_id:
        result = build_anchor_index(args.bill_id)
        print(f"Built {result.anchor_count:,} exact citation anchors for {result.bill_id}")
        return 0

    result = build_available()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
