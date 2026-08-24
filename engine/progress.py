"""Shared stage progress/checkpoint reporting for real Bill X-Ray proving-ground runs.

Pass 21.1 adds product-facing current-stage timing so the web UI can show honest,
weighted progress and a conservative ETA while long real-bill analyses run.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class StageRecord:
    key: str
    label: str
    status: str
    elapsed_seconds: float | None = None
    summary: str | None = None
    error: str | None = None


class StageTracker:
    def __init__(self, bill_id: str, status_dir: Path, total_stages: int):
        self.bill_id = bill_id
        self.status_dir = status_dir
        self.total_stages = total_stages
        self.started = time.monotonic()
        self.records: list[StageRecord] = []
        self.current_stage: str | None = None
        self.current_label: str | None = None
        self.current_index: int | None = None
        self.current_started: float | None = None
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self._write("running")

    @property
    def progress_path(self) -> Path:
        return self.status_dir / f"{self.bill_id}_progress.json"

    def _payload(self, state: str) -> dict[str, Any]:
        completed = sum(1 for record in self.records if record.status == "complete")
        current_elapsed = None
        if self.current_started is not None:
            current_elapsed = round(time.monotonic() - self.current_started, 3)
        return {
            "bill_id": self.bill_id,
            "state": state,
            "current_stage": self.current_stage,
            "current_label": self.current_label,
            "current_stage_index": self.current_index,
            "current_stage_elapsed_seconds": current_elapsed,
            "completed_stages": completed,
            "total_stages": self.total_stages,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "stages": [record.__dict__ for record in self.records],
        }

    def _write(self, state: str) -> None:
        payload = self._payload(state)
        temp = self.progress_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.progress_path)

    def run(self, key: str, label: str, fn: Callable[[], Any], summarize: Callable[[Any], str] | None = None) -> Any:
        index = len(self.records) + 1
        self.current_stage = key
        self.current_label = label
        self.current_index = index
        self.current_started = time.monotonic()
        print(f"[{index:02d}/{self.total_stages:02d}] {label} ...", flush=True)
        self._write("running")
        started = self.current_started
        try:
            result = fn()
        except Exception as exc:
            elapsed = time.monotonic() - started
            self.records.append(StageRecord(key, label, "failed", round(elapsed, 3), error=f"{type(exc).__name__}: {exc}"))
            print(f"      FAILED after {elapsed:.1f}s: {exc}", flush=True)
            self.current_started = None
            self._write("failed")
            raise
        elapsed = time.monotonic() - started
        summary = summarize(result) if summarize else None
        self.records.append(StageRecord(key, label, "complete", round(elapsed, 3), summary=summary))
        suffix = f" — {summary}" if summary else ""
        print(f"      done in {elapsed:.1f}s{suffix}", flush=True)
        self.current_stage = None
        self.current_label = None
        self.current_index = None
        self.current_started = None
        self._write("running")
        return result

    def finish(self, state: str = "complete") -> dict[str, Any]:
        self.current_stage = None
        self.current_label = None
        self.current_index = None
        self.current_started = None
        self._write(state)
        return self._payload(state)
