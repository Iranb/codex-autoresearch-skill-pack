#!/usr/bin/env python3
"""Generate blocker simulation cases for autopilot validation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from blocker_triage import classify_typed


CASES = [
    ("infrastructure_failure", "remote experiment runtime failed", "infrastructure_failure", "auto_repairable", "repair_or_reconcile_infrastructure", "operational"),
    ("valid_negative", "matched falsifier refuted the mechanism", "valid_negative", "scientific_transition", "apply_research_decision", "scientific_revision"),
    ("protocol_invalid", "locked evaluator drifted", "protocol_invalid", "auto_repairable", "repair_protocol", "operational"),
    ("import_wait", "PaperNexus graph import queue running", "", "async_wait", "schedule_async_poll", "none"),
    ("review_high_issue", "open high review findings", "", "auto_repairable", "schedule_repair", "operational"),
    ("budget_exceeded", "budget exceeded for proposed experiment", "", "hard_stop", "rollback_or_negative_result_route", "none"),
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
    for name, reason, failure_class, expected_class, expected_action, expected_repair_kind in CASES:
        klass, action, repair_kind = classify_typed(reason, failure_class)
        if (klass, action, repair_kind) != (expected_class, expected_action, expected_repair_kind):
            raise AssertionError(
                {
                    "case": name,
                    "actual": [klass, action, repair_kind],
                    "expected": [expected_class, expected_action, expected_repair_kind],
                }
            )
        row = {
            "ts": now(),
            "stage": "simulation",
            "case": name,
            "reason": reason,
            "failure_class": failure_class or "untyped_legacy_blocker",
            "class": klass,
            "recommended_action": action,
            "repair_kind": repair_kind,
        }
        append_jsonl(base / "blocker_ledger.jsonl", row)
        out.append(row)
    print(json.dumps({"ok": True, "cases": out}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
