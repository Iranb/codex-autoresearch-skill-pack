#!/usr/bin/env python3
"""Record a real Codex sub-agent result against a job packet."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loop_trace import append_trace


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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def update_queue(base: Path, queue_name: str, job_id: str, status: str, artifacts: list[str], error: str) -> None:
    path = base / queue_name
    data = rows(path)
    for row in data:
        if row.get("job_id") != job_id:
            continue
        row["status"] = status
        row["updated_at"] = now()
        if artifacts:
            row["artifacts"] = sorted(set(list(row.get("artifacts") or []) + artifacts))
        if error:
            row["last_error"] = error
    write_rows(path, data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--status", choices=["completed", "failed", "retry"], required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--error", default="")
    args = parser.parse_args()

    base = ar(args.project)
    packet_path = base / "job_packets" / f"{args.job_id}.json"
    packet = read_json(packet_path)
    queue_name = str(packet.get("queue") or ("async_jobs.jsonl" if packet.get("job_kind") == "async" else "repair_queue.jsonl"))
    packet["subagent_result"] = {
        "agent_id": args.agent_id,
        "status": args.status,
        "summary": args.summary,
        "artifacts": args.artifact,
        "error": args.error or None,
        "recorded_at": now(),
    }
    packet["status"] = "subagent_completed" if args.status == "completed" else f"subagent_{args.status}"
    write_json(packet_path, packet)
    update_queue(base, queue_name, args.job_id, args.status, args.artifact, args.error)
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": packet.get("stage"),
            "action": "subagent_result",
            "details": {**packet["subagent_result"], "job_id": args.job_id, "queue": queue_name},
        },
    )
    append_trace(
        base,
        event="subagent_result",
        stage=str(packet.get("stage") or ""),
        job_id=args.job_id,
        authority="scripts/goal_subagent_result.py",
        decision=args.status,
        evidence_refs=args.artifact,
        reason=args.error or args.summary,
        details={
            "agent_id": args.agent_id,
            "queue": queue_name,
            "status": args.status,
            "summary": args.summary,
            "error": args.error or None,
        },
    )
    print(json.dumps({"ok": True, "packet": str(packet_path), "queue": queue_name}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
