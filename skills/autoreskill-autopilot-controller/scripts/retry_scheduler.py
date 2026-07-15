#!/usr/bin/env python3
"""Manage repair and async queues."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def failure_signature(failure_class: str, action: str, reason: str) -> str:
    normalized_reason = re.sub(r"\s+", " ", reason.strip().lower())
    payload = f"{failure_class.strip().lower()}|{action.strip().lower()}|{normalized_reason}"
    return "failure-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def cmd_add(args: argparse.Namespace) -> None:
    path = queue_path(args.project, args.kind)
    data = rows(path)
    repair_kind = args.repair_kind or ("none" if args.kind == "async" else "operational")
    max_attempts = args.max_attempts if args.max_attempts is not None else (3 if args.kind == "async" else 2)
    signature = args.failure_signature or failure_signature(args.failure_class, args.action, args.reason)
    matching = [row for row in data if row.get("failure_signature") == signature]
    for existing in matching:
        if existing.get("status") in {"pending", "retry", "running"}:
            print(json.dumps({**existing, "idempotent": True}, indent=2, ensure_ascii=False))
            return
    prior_operational = max(
        [int(row.get("operational_attempt") or row.get("attempts") or 0) for row in matching] or [0]
    )
    args.operational_attempt = max(args.operational_attempt, prior_operational)
    if repair_kind == "scientific_revision" and args.scientific_revision > args.max_scientific_revisions:
        raise SystemExit("scientific revision budget exhausted")
    if repair_kind == "operational" and args.operational_attempt >= max_attempts:
        raise SystemExit("operational repair budget exhausted for this failure signature")
    row = {
        "schema_version": 2,
        "job_id": args.job_id or f"job_{uuid.uuid4().hex[:12]}",
        "kind": args.kind,
        "stage": args.stage,
        "action": args.action,
        "reason": args.reason,
        "status": "pending",
        "attempts": 0,
        "max_attempts": max_attempts,
        "failure_class": args.failure_class or "untyped_legacy_blocker",
        "failure_signature": signature,
        "repair_kind": repair_kind,
        "operational_attempt": args.operational_attempt,
        "scientific_revision": args.scientific_revision,
        "max_scientific_revisions": args.max_scientific_revisions,
        "created_at": iso(now()),
        "next_retry_at": iso(now() + timedelta(minutes=args.delay_minutes)),
        "fallback_action": args.fallback_action,
    }
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
            if args.status == "running":
                row["attempts"] = int(row.get("attempts") or 0) + 1
                if row.get("repair_kind") == "operational" and args.operational_attempt is None:
                    row["operational_attempt"] = int(row.get("operational_attempt") or 0) + 1
            if args.error:
                row["last_error"] = args.error
            if args.operational_attempt is not None:
                row["operational_attempt"] = args.operational_attempt
            if args.scientific_revision is not None:
                row["scientific_revision"] = args.scientific_revision
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
    p.add_argument("--failure-class", default="")
    p.add_argument("--failure-signature")
    p.add_argument("--repair-kind", choices=["operational", "scientific_revision", "none"])
    p.add_argument("--operational-attempt", type=int, default=0)
    p.add_argument("--scientific-revision", type=int, default=0)
    p.add_argument("--max-scientific-revisions", type=int, default=2)
    p.add_argument("--job-id")
    p.add_argument("--delay-minutes", type=int, default=5)
    p.add_argument("--max-attempts", type=int)
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
    p.add_argument("--operational-attempt", type=int)
    p.add_argument("--scientific-revision", type=int)
    p.set_defaults(func=cmd_update)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
