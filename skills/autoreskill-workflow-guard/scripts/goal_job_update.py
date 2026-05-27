#!/usr/bin/env python3
"""Update .autoreskill repair/async job state after execution."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def queue_path(base: Path, kind: str) -> Path:
    return base / ("async_jobs.jsonl" if kind == "async" else "repair_queue.jsonl")


def update_job(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    data = rows(path)
    changed: dict[str, Any] | None = None
    for row in data:
        if row.get("job_id") != args.job_id:
            continue
        row["status"] = args.status
        row["updated_at"] = now()
        if args.artifact:
            artifacts = list(row.get("artifacts") or [])
            artifacts.extend(args.artifact)
            row["artifacts"] = artifacts
        if args.error:
            row["last_error"] = args.error
        if args.next_action:
            row["next_action"] = args.next_action
        changed = dict(row)
    if changed is None:
        raise SystemExit(f"job not found: {args.job_id}")
    write_rows(path, data)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--kind", choices=["repair", "async"], required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--status", choices=["pending", "running", "retry", "completed", "failed", "superseded"], required=True)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--error", default="")
    parser.add_argument("--next-action", default="")
    args = parser.parse_args()

    base = ar(args.project)
    job = update_job(queue_path(base, args.kind), args)
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": job.get("stage"),
            "action": "job_update",
            "details": {
                "job_id": args.job_id,
                "kind": args.kind,
                "status": args.status,
                "artifacts": args.artifact,
                "error": args.error or None,
                "next_action": args.next_action or None,
            },
        },
    )
    print(json.dumps({"ok": True, "job": job}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
