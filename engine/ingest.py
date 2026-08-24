"""Pass 2: deterministic local bill ingestion for Bill X-Ray.

This module reads only local .txt or .xml source documents. It does not summarize,
interpret, or fetch legislation from the network. Every ingested artifact retains
source provenance and a SHA-256 fingerprint of the exact local bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "source_documents"
INGESTED_DIR = ROOT / "data" / "ingested"
SOURCE_MANIFEST = ROOT / "data" / "source_manifest.json"
SUPPORTED_SUFFIXES = {".txt", ".xml"}


@dataclass(frozen=True)
class IngestedBill:
    bill_id: str
    source_filename: str
    source_format: str
    source_url: str
    document_ref: str
    sha256: str
    byte_count: int
    text_length: int
    line_count: int
    ingested_at: str
    text: str


def load_source_manifest(path: Path = SOURCE_MANIFEST) -> dict[str, dict]:
    if not path.exists():
        raise FileNotFoundError(f"Source manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("bills", [])
    return {entry["bill_id"]: entry for entry in entries}


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode source document as UTF-8 or Windows-1252 text")


def _strip_xml_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_to_text(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML source document: {exc}") from exc

    lines: list[str] = []
    block_tags = {
        "division", "title", "subtitle", "chapter", "subchapter", "part", "subpart",
        "section", "subsection", "paragraph", "subparagraph", "clause", "subclause",
        "header", "enum", "heading", "text", "quote", "quoted-block", "toc-entry",
    }

    for elem in root.iter():
        tag = _strip_xml_namespace(str(elem.tag)).lower()
        if tag not in block_tags:
            continue
        content = " ".join("".join(elem.itertext()).split())
        if content and (not lines or content != lines[-1]):
            lines.append(content)

    if not lines:
        fallback = " ".join("".join(root.itertext()).split())
        if fallback:
            lines.append(fallback)
    return "\n".join(lines)


def extract_text(path: Path, raw: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        text = _decode_text(raw)
    elif suffix == ".xml":
        text = _xml_to_text(raw)
    else:
        raise ValueError(f"Unsupported source format '{suffix}'. Use .txt or .xml")

    # Normalize newline representation without rewriting statutory wording.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def ingest_file(bill_id: str, path: Path, source_url: str = "") -> IngestedBill:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Local bill source not found: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported source format '{path.suffix}'. Use .txt or .xml")

    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"Source document is empty: {path}")
    text = extract_text(path, raw)
    if not text:
        raise ValueError(f"No readable legislative text extracted from: {path}")

    return IngestedBill(
        bill_id=bill_id,
        source_filename=path.name,
        source_format=path.suffix.lower().lstrip("."),
        source_url=source_url,
        document_ref=f"local:{path.as_posix()}",
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        text_length=len(text),
        line_count=text.count("\n") + 1,
        ingested_at=datetime.now(timezone.utc).isoformat(),
        text=text,
    )


def ingest_manifest_bill(bill_id: str, *, write: bool = True) -> IngestedBill:
    manifest = load_source_manifest()
    if bill_id not in manifest:
        raise KeyError(f"Unknown bill_id '{bill_id}' in source manifest")
    entry = manifest[bill_id]
    source_path = SOURCE_DIR / entry["local_filename"]
    result = ingest_file(bill_id, source_path, entry.get("source_url", ""))
    if write:
        INGESTED_DIR.mkdir(parents=True, exist_ok=True)
        out = INGESTED_DIR / f"{bill_id}.json"
        out.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def ingest_available(*, write: bool = True) -> dict[str, list[str]]:
    manifest = load_source_manifest()
    ingested: list[str] = []
    missing: list[str] = []
    failed: list[str] = []
    for bill_id, entry in manifest.items():
        source_path = SOURCE_DIR / entry["local_filename"]
        if not source_path.exists():
            missing.append(bill_id)
            continue
        try:
            ingest_manifest_bill(bill_id, write=write)
            ingested.append(bill_id)
        except (ValueError, OSError):
            failed.append(bill_id)
    return {"ingested": ingested, "missing": missing, "failed": failed}


def source_status() -> dict[str, dict]:
    manifest = load_source_manifest()
    status: dict[str, dict] = {}
    for bill_id, entry in manifest.items():
        source_path = SOURCE_DIR / entry["local_filename"]
        ingested_path = INGESTED_DIR / f"{bill_id}.json"
        status[bill_id] = {
            "source_present": source_path.exists(),
            "ingested_present": ingested_path.exists(),
            "local_filename": entry["local_filename"],
            "source_url": entry.get("source_url", ""),
            "official_identifier": entry.get("official_identifier", ""),
            "law_number": entry.get("law_number", ""),
        }
    return status


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest local TXT/XML bill source files")
    parser.add_argument("bill_id", nargs="?", help="bill id from data/source_manifest.json")
    parser.add_argument("--status", action="store_true", help="show source/ingestion readiness")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        print(json.dumps(source_status(), indent=2))
        return 0
    if args.bill_id:
        result = ingest_manifest_bill(args.bill_id)
        print(f"Ingested {result.bill_id}: {result.line_count:,} lines, SHA-256 {result.sha256[:12]}...")
        return 0

    result = ingest_available()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
