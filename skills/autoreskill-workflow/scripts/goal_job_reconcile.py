#!/usr/bin/env python3
"""Reconcile stale .autoreskill repair and async jobs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from loop_trace import append_trace


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def reconcile_file(path: Path, stale_after: datetime, dry_run: bool) -> list[dict[str, Any]]:
    data = rows(path)
    changed: list[dict[str, Any]] = []
    for row in data:
        if row.get("status") != "running":
            continue
        updated = parse_ts(row.get("updated_at")) or parse_ts(row.get("created_at"))
        if updated and updated > stale_after:
            continue
        attempts = int(row.get("attempts", 0))
        max_attempts = int(row.get("max_attempts", 3))
        before = dict(row)
        if attempts < max_attempts:
            row["status"] = "retry"
            row["next_retry_at"] = iso(now())
            row["updated_at"] = iso(now())
            row["last_error"] = "stale_running_job_requeued"
        else:
            row["status"] = "failed"
            row["updated_at"] = iso(now())
            row["last_error"] = "stale_running_job_exceeded_attempts"
            row["next_action"] = row.get("fallback_action") or "degrade_or_rollback"
        changed.append({"before": before, "after": dict(row)})
    if changed and not dry_run:
        write_rows(path, data)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stale-minutes", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = ar(args.project)
    stale_after = now() - timedelta(minutes=args.stale_minutes)
    results = {
        "repair": reconcile_file(base / "repair_queue.jsonl", stale_after, args.dry_run),
        "async": reconcile_file(base / "async_jobs.jsonl", stale_after, args.dry_run),
    }
    if not args.dry_run:
        append_jsonl(
            base / "decision_log.jsonl",
            {
                "ts": iso(now()),
                "stage": "workflow_guard",
                "action": "job_reconcile",
                "details": {
                    "stale_minutes": args.stale_minutes,
                    "repair_changed": len(results["repair"]),
                    "async_changed": len(results["async"]),
                },
            },
        )
        changed_count = len(results["repair"]) + len(results["async"])
        if changed_count:
            append_trace(
                base,
                event="job_reconcile",
                stage="workflow_guard",
                authority="scripts/goal_job_reconcile.py",
                decision="stale_jobs_reconciled",
                details={
                    "stale_minutes": args.stale_minutes,
                    "repair_changed": len(results["repair"]),
                    "async_changed": len(results["async"]),
                },
            )
    print(json.dumps({"ok": True, "dry_run": args.dry_run, "changes": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
