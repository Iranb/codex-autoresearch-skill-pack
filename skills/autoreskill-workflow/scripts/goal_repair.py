#!/usr/bin/env python3
"""Force a bounded repair/action packet for the current .autoreskill blocker."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from contract_lint import lint
from goal_state import NEXT_ACTIONS, OWNERS, ar, load_state, save_state
from goal_tick import (
    append_jsonl,
    classify,
    handoff_for_stage,
    iso,
    now,
    queue_job,
    rows,
    write_job_packet,
    write_rows,
)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def force_due(base: Path, job: dict[str, Any]) -> None:
    queue_name = "async_jobs.jsonl" if job.get("kind") == "async" else "repair_queue.jsonl"
    path = base / queue_name
    data = rows(path)
    for row in data:
        if row.get("job_id") != job.get("job_id"):
            continue
        row["status"] = "pending"
        row["next_retry_at"] = iso(now() - timedelta(seconds=1))
        row["next_poll_at"] = iso(now() - timedelta(seconds=1))
        row["updated_at"] = iso(now())
    write_rows(path, data)


def dispatch_prompt(project: str, job_id: str, mode: str, mark_running: bool) -> dict[str, Any]:
    script = Path(__file__).with_name("goal_job_dispatch.py")
    cmd = [sys.executable, str(script), "--project", str(Path(project).expanduser().resolve()), "--job-id", job_id, "--mode", mode]
    if mark_running:
        cmd.append("--mark-running")
    proc = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return {"ok": False, "stdout": proc.stdout, "stderr": proc.stderr, "cmd": cmd}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": proc.stdout, "cmd": cmd}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage")
    parser.add_argument("--reason")
    parser.add_argument("--mode", choices=["serialized", "subagent"], default="serialized")
    parser.add_argument("--dispatch", action="store_true", help="render a prompt immediately")
    parser.add_argument("--mark-running", action="store_true")
    args = parser.parse_args()

    project = str(Path(args.project).expanduser().resolve())
    base = ar(project)
    state = load_state(project)
    if args.stage:
        state["stage"] = args.stage
        state["owner"] = OWNERS.get(args.stage, state.get("owner"))
        state["next_action"] = NEXT_ACTIONS.get(args.stage, state.get("next_action"))
    stage = str(state.get("stage", "init"))
    contract = lint(project, stage)
    if contract["complete"] and not args.reason:
        out = {"action": "no_repair_needed", "stage": stage, "contract": contract}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    reason = args.reason or "; ".join(str(item) for item in contract.get("missing", [])) or f"{stage} contract incomplete"
    klass, recommended_action = classify(reason)
    kind = "async" if klass == "async_wait" else "repair"
    policy = read_json(base / "autopilot_policy.json", {})
    blocker = {
        "schema_version": 1,
        "ts": iso(now()),
        "stage": stage,
        "reason": reason,
        "class": klass,
        "recommended_action": recommended_action,
        "contract": contract,
        "status": "forced_repair",
    }
    append_jsonl(base / "blocker_ledger.jsonl", blocker)

    job = queue_job(base, kind, stage, recommended_action, reason, policy)
    force_due(base, job)
    queue_name = "async_jobs.jsonl" if kind == "async" else "repair_queue.jsonl"
    handoff = None if job.get("_reused") else handoff_for_stage(base, state, contract)
    packet = write_job_packet(base, state, job, contract, blocker, queue_name)

    state["blocking_reason"] = reason
    state["next_action"] = recommended_action
    save_state(
        project,
        state,
        "force_repair_packet",
        {"blocker": blocker, "job": job, "handoff": str(handoff) if handoff else None, "job_packet": str(packet)},
    )

    dispatch = dispatch_prompt(project, str(job["job_id"]), args.mode, args.mark_running) if args.dispatch else None
    print(
        json.dumps(
            {
                "action": "force_repair_packet",
                "blocker": blocker,
                "job": job,
                "handoff": str(handoff) if handoff else None,
                "job_packet": str(packet),
                "dispatch": dispatch,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
