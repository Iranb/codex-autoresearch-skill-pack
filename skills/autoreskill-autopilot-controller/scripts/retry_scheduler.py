#!/usr/bin/env python3
"""Manage repair and async queues."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def base(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def queue_path(project: str, kind: str) -> Path:
    return base(project) / ("async_jobs.jsonl" if kind == "async" else "repair_queue.jsonl")


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")


def cmd_add(args: argparse.Namespace) -> None:
    path = queue_path(args.project, args.kind)
    row = {
        "schema_version": 1,
        "job_id": args.job_id or f"job_{uuid.uuid4().hex[:12]}",
        "kind": args.kind,
        "stage": args.stage,
        "action": args.action,
        "reason": args.reason,
        "status": "pending",
        "attempts": 0,
        "max_attempts": args.max_attempts,
        "created_at": iso(now()),
        "next_retry_at": iso(now() + timedelta(minutes=args.delay_minutes)),
        "fallback_action": args.fallback_action,
    }
    data = rows(path)
    data.append(row)
    write_rows(path, data)
    print(json.dumps(row, indent=2, ensure_ascii=False))


def cmd_list(args: argparse.Namespace) -> None:
    data = rows(queue_path(args.project, args.kind))
    if args.status:
        data = [row for row in data if row.get("status") == args.status]
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_update(args: argparse.Namespace) -> None:
    path = queue_path(args.project, args.kind)
    data = rows(path)
    changed = False
    for row in data:
        if row.get("job_id") == args.job_id:
            row["status"] = args.status
            row["updated_at"] = iso(now())
            if args.error:
                row["last_error"] = args.error
            changed = True
    if not changed:
        raise SystemExit(f"job not found: {args.job_id}")
    write_rows(path, data)
    print(json.dumps({"ok": True, "job_id": args.job_id, "status": args.status}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add")
    p.add_argument("--project", required=True)
    p.add_argument("--kind", choices=["repair", "async"], required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--reason", default="")
    p.add_argument("--job-id")
    p.add_argument("--delay-minutes", type=int, default=5)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--fallback-action", default="degrade_or_rollback")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list")
    p.add_argument("--project", required=True)
    p.add_argument("--kind", choices=["repair", "async"], required=True)
    p.add_argument("--status")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("update")
    p.add_argument("--project", required=True)
    p.add_argument("--kind", choices=["repair", "async"], required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--error")
    p.set_defaults(func=cmd_update)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
