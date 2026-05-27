#!/usr/bin/env python3
"""Create or dispatch an isolated Reviewer/Cross-Reviewer job packet."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contract_lint import lint
from goal_state import ar, load_state, save_state
from goal_tick import write_job_packet


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")


def render(project: str, job_id: str, mode: str, mark_running: bool) -> dict[str, Any]:
    script = Path(__file__).with_name("goal_job_dispatch.py")
    cmd = [sys.executable, str(script), "--project", str(Path(project).expanduser().resolve()), "--job-id", job_id, "--mode", mode]
    if mark_running:
        cmd.append("--mark-running")
    proc = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return {"ok": False, "stderr": proc.stderr, "stdout": proc.stdout}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": proc.stdout}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--cross", action="store_true", help="request Cross-Reviewer isolation")
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--mode", choices=["serialized", "subagent"], default="serialized")
    parser.add_argument("--mark-running", action="store_true")
    args = parser.parse_args()

    project = str(Path(args.project).expanduser().resolve())
    base = ar(project)
    state = load_state(project)
    stage = "review_pressure"
    contract = lint(project, stage)
    role = "Cross-Reviewer" if args.cross else "Reviewer"
    job = {
        "schema_version": 1,
        "job_id": f"job_{uuid.uuid4().hex[:12]}",
        "kind": "repair",
        "stage": stage,
        "action": "run_isolated_cross_review" if args.cross else "run_isolated_review",
        "reason": "forced review gate",
        "status": "pending",
        "attempts": 0,
        "max_attempts": 3,
        "created_at": now(),
        "next_retry_at": now(),
        "fallback_action": "downgrade_or_delete_blocking_claims",
    }
    repair_path = base / "repair_queue.jsonl"
    data = rows(repair_path)
    data.append(job)
    write_rows(repair_path, data)
    packet = write_job_packet(base, {**state, "stage": stage, "owner": role}, job, contract, None, "repair_queue.jsonl")
    append_jsonl(
        base / "mailbox.jsonl",
        {"ts": now(), "type": "forced_review", "job_id": job["job_id"], "role": role, "path": str(packet)},
    )
    save_state(project, {**state, "stage": stage, "owner": role, "next_action": job["action"]}, "force_review_packet", {"job": job, "packet": str(packet)})
    dispatch = render(project, job["job_id"], args.mode, args.mark_running) if args.dispatch else None
    print(json.dumps({"action": "force_review_packet", "job": job, "job_packet": str(packet), "dispatch": dispatch}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
