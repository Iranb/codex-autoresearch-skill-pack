#!/usr/bin/env python3
"""Classify blockers and append blocker ledger rows."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def base(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def classify(reason: str) -> tuple[str, str]:
    text = reason.lower()
    if any(k in text for k in ["import", "queue", "running", "remote", "async", "wait"]):
        return "async_wait", "schedule_async_poll"
    if any(k in text for k in ["controller_unavailable", "single_seed", "cost_evidence", "provider", "sparse", "stale"]):
        return "degradable", "advance_with_downgrade_or_fallback"
    if any(k in text for k in ["budget", "license", "unsafe", "no_viable", "papernexus_unavailable_without_cached"]):
        return "hard_stop", "rollback_or_negative_result_route"
    return "auto_repairable", "schedule_repair"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--artifact")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    klass, action = classify(args.reason)
    row = {
        "schema_version": 1,
        "ts": now(),
        "stage": args.stage,
        "reason": args.reason,
        "artifact": args.artifact,
        "class": klass,
        "recommended_action": action,
        "status": "triaged",
    }
    if not args.dry_run:
        append_jsonl(base(args.project) / "blocker_ledger.jsonl", row)
    print(json.dumps(row, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
