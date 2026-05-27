#!/usr/bin/env python3
"""Generate blocker simulation cases for autopilot validation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from blocker_triage import classify


CASES = [
    ("missing_negative_evidence", "negative evidence missing"),
    ("import_wait", "PaperNexus import queue running"),
    ("dry_run_fail", "dry-run failed three times"),
    ("review_high_issue", "open high review findings"),
    ("budget_exceeded", "budget exceeded for proposed experiment"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    out = []
    for name, reason in CASES:
        klass, action = classify(reason)
        row = {"ts": now(), "stage": "simulation", "case": name, "reason": reason, "class": klass, "recommended_action": action}
        append_jsonl(base / "blocker_ledger.jsonl", row)
        out.append(row)
    print(json.dumps({"ok": True, "cases": out}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
