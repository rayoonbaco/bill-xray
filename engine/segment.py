"""Pass 3: deterministic structural segmentation of ingested U.S. legislation.

The segmenter does not summarize or interpret the bill. It identifies structural
headings and records line-bounded text blocks so later passes can cite and analyze
small, reviewable statutory units.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
INGESTED_DIR = ROOT / "data" / "ingested"
SEGMENT_DIR = ROOT / "data" / "segments"

LEVELS = {
    "division": 10,
    "title": 20,
    "subtitle": 30,
    "chapter": 40,
    "subchapter": 50,
    "part": 60,
    "subpart": 70,
    "section": 80,
}

HEADING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("division", re.compile(r"^\s*DIVISION\s+([A-Z0-9-]+)\b(?:\s*[-—:.]\s*|\s+)?(.*)$", re.I)),
    ("subtitle", re.compile(r"^\s*SUBTITLE\s+([A-Z0-9-]+)\b(?:\s*[-—:.]\s*|\s+)?(.*)$", re.I)),
    ("subchapter", re.compile(r"^\s*SUBCHAPTER\s+([IVXLCDM0-9A-Z-]+)\b(?:\s*[-—:.]\s*|\s+)?(.*)$", re.I)),
    ("chapter", re.compile(r"^\s*CHAPTER\s+([IVXLCDM0-9A-Z-]+)\b(?:\s*[-—:.]\s*|\s+)?(.*)$", re.I)),
    ("subpart", re.compile(r"^\s*SUBPART\s+([A-Z0-9-]+)\b(?:\s*[-—:.]\s*|\s+)?(.*)$", re.I)),
    ("part", re.compile(r"^\s*PART\s+([IVXLCDM0-9A-Z-]+)\b(?:\s*[-—:.]\s*|\s+)?(.*)$", re.I)),
    ("title", re.compile(r"^\s*TITLE\s+([IVXLCDM0-9A-Z-]+)\b(?:\s*[-—:.]\s*|\s+)?(.*)$", re.I)),
    # A bill section heading must be the structural form "SECTION 1." or "SEC. 1.".
    # Do not treat ordinary statutory cross-references such as "Section 202(c)" or
    # "section 553 of title 5" as new bill sections.  Also match SECTION before SEC
    # semantically by spelling the two forms separately so SECTION 1 does not become
    # the bogus identifier "TION".
    ("section", re.compile(r"^\s*(?:SECTION\s+|SEC\.\s*)([0-9A-Za-z-]+)\.\s*(.*)$", re.I)),
]


@dataclass(frozen=True)
class Segment:
    segment_id: str
    kind: str
    identifier: str
    heading: str
    start_line: int
    end_line: int
    parent_segment_ids: list[str]
    text: str


@dataclass(frozen=True)
class SegmentedBill:
    bill_id: str
    source_document_ref: str
    source_sha256: str
    line_count: int
    segment_count: int
    segments: list[Segment]


def classify_heading(line: str) -> tuple[str, str, str] | None:
    compact = " ".join(line.split())
    for kind, pattern in HEADING_PATTERNS:
        match = pattern.match(compact)
        if match:
            identifier = match.group(1).strip().rstrip(".")
            trailing = match.group(2).strip(" -—:.")
            heading = compact
            return kind, identifier, heading if heading else trailing
    return None


def segment_text(
    bill_id: str,
    text: str,
    *,
    source_document_ref: str = "",
    source_sha256: str = "",
) -> SegmentedBill:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    found: list[dict] = []
    stack: list[tuple[int, str]] = []

    for line_index, line in enumerate(lines, start=1):
        classified = classify_heading(line)
        if not classified:
            continue
        kind, identifier, heading = classified
        level = LEVELS[kind]
        while stack and stack[-1][0] >= level:
            stack.pop()
        segment_id = f"{bill_id}:{kind}:{identifier}:{len(found) + 1}"
        found.append(
            {
                "segment_id": segment_id,
                "kind": kind,
                "identifier": identifier,
                "heading": heading,
                "start_line": line_index,
                "parent_segment_ids": [entry[1] for entry in stack],
            }
        )
        stack.append((level, segment_id))

    segments: list[Segment] = []
    for index, item in enumerate(found):
        start = item["start_line"]
        end = found[index + 1]["start_line"] - 1 if index + 1 < len(found) else len(lines)
        block = "\n".join(lines[start - 1 : end]).strip()
        segments.append(
            Segment(
                segment_id=item["segment_id"],
                kind=item["kind"],
                identifier=item["identifier"],
                heading=item["heading"],
                start_line=start,
                end_line=end,
                parent_segment_ids=item["parent_segment_ids"],
                text=block,
            )
        )

    return SegmentedBill(
        bill_id=bill_id,
        source_document_ref=source_document_ref,
        source_sha256=source_sha256,
        line_count=len(lines),
        segment_count=len(segments),
        segments=segments,
    )


def segment_ingested_bill(bill_id: str, *, write: bool = True) -> SegmentedBill:
    path = INGESTED_DIR / f"{bill_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Ingested bill not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = segment_text(
        bill_id,
        payload["text"],
        source_document_ref=payload.get("document_ref", ""),
        source_sha256=payload.get("sha256", ""),
    )
    if write:
        SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
        out = SEGMENT_DIR / f"{bill_id}.json"
        out.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def segment_available(*, write: bool = True) -> dict[str, list[str]]:
    segmented: list[str] = []
    missing_ingestion: list[str] = []
    failed: list[str] = []
    for bill_id in ("aca", "obbba"):
        if not (INGESTED_DIR / f"{bill_id}.json").exists():
            missing_ingestion.append(bill_id)
            continue
        try:
            segment_ingested_bill(bill_id, write=write)
            segmented.append(bill_id)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            failed.append(bill_id)
    return {"segmented": segmented, "missing_ingestion": missing_ingestion, "failed": failed}


def segment_status() -> dict[str, dict]:
    status: dict[str, dict] = {}
    for bill_id in ("aca", "obbba"):
        ingested_path = INGESTED_DIR / f"{bill_id}.json"
        segment_path = SEGMENT_DIR / f"{bill_id}.json"
        segment_count = 0
        if segment_path.exists():
            try:
                segment_count = int(json.loads(segment_path.read_text(encoding="utf-8")).get("segment_count", 0))
            except (OSError, ValueError, json.JSONDecodeError):
                segment_count = 0
        status[bill_id] = {
            "ingested_present": ingested_path.exists(),
            "segmented_present": segment_path.exists(),
            "segment_count": segment_count,
        }
    return status


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Segment ingested Bill X-Ray legislation")
    parser.add_argument("bill_id", nargs="?", help="bill id, e.g. aca or obbba")
    parser.add_argument("--status", action="store_true", help="show segmentation readiness")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        print(json.dumps(segment_status(), indent=2))
        return 0
    if args.bill_id:
        result = segment_ingested_bill(args.bill_id)
        print(f"Segmented {result.bill_id}: {result.segment_count:,} structural blocks")
        return 0

    result = segment_available()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
