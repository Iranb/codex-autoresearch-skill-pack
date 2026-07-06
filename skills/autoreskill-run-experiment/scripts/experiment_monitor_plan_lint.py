#!/usr/bin/env python3
"""Lint adaptive experiment monitor plans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ACTIVE_STATES = {
    "queued",
    "submitted",
    "pending",
    "waiting",
    "waiting_for_gpu",
    "waiting_for_gpu_idle",
    "waiting_for_resource",
    "guarded_waiting",
    "resource_wait",
    "launching",
    "provisioning",
    "starting",
    "running",
    "running_or_queued",
    "bjtu_hpc_running_or_queued",
    "running_remote_training_wait",
    "active_resource_wait",
    "active_experiment_monitor",
    "external_live_wait",
    "training",
    "training_active",
    "training_or_queued",
    "parallel_training_active",
    "parallel_training_or_queued",
    "non_bjtu_parallel_training_active",
    "non_bjtu_parallel_training_or_queued",
    "bjtu_parallel_training_active",
    "bjtu_parallel_training_or_queued",
    "bjtu_parallel_retry_running_or_queued",
    "stale",
    "hung",
    "no_progress",
}
TERMINAL_STATES = {"completed", "complete", "done", "succeeded", "success", "failed", "failure", "cancelled", "canceled", "stopped", "timeout", "timed_out", "budget_stopped", "killed"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def lint(project: str, rel: str) -> dict[str, Any]:
    base = ar(project)
    path = base / rel
    payload = read_json(path)
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": [rel], "warnings": [], "path": str(path)}
    for key in [
        "run_id",
        "backend",
        "state",
        "automation_kind",
        "reuse_policy",
        "check_interval_policy",
        "last_check_at",
        "stop_conditions",
        "escalation_conditions",
    ]:
        if not present(payload.get(key)):
            missing.append(key)
    state = str(payload.get("state") or "").strip().lower()
    policy = payload.get("check_interval_policy") if isinstance(payload.get("check_interval_policy"), dict) else {}
    reuse = payload.get("reuse_policy") if isinstance(payload.get("reuse_policy"), dict) else {}
    interval = policy.get("interval_minutes")
    desired_rrule = str(policy.get("desired_rrule") or payload.get("desired_rrule") or "").strip()
    if state in ACTIVE_STATES:
        if not isinstance(interval, int) or interval <= 0:
            missing.append("check_interval_policy.interval_minutes positive integer for active runs")
        elif desired_rrule and desired_rrule != f"FREQ=MINUTELY;INTERVAL={interval}":
            warnings.append("desired_rrule does not match check_interval_policy.interval_minutes")
        if not present(payload.get("next_check_after")):
            missing.append("next_check_after for active runs")
        if reuse.get("reuse_existing_monitor") is not True:
            missing.append("reuse_policy.reuse_existing_monitor=true")
        if reuse.get("no_duplicate_monitor_per_run") is not True:
            missing.append("reuse_policy.no_duplicate_monitor_per_run=true")
        remaining = number(payload.get("estimated_remaining_minutes"))
        status_detail = " ".join(
            str(payload.get(key) or "").lower()
            for key in ["status", "state", "status_detail", "wait_condition", "observed_progress"]
        )
        risky = any(token in status_detail for token in ["startup", "stale", "hung", "no_progress", "stall", "pending"])
        if remaining is not None and remaining > 240 and isinstance(interval, int) and interval <= 30 and not risky:
            warnings.append(
                "stable active run has estimated_remaining_minutes > 240 but interval <= 30; "
                "use a stage-boundary or ETA-based heartbeat unless a startup/stale risk is recorded"
            )
    elif state in TERMINAL_STATES:
        if interval is not None:
            warnings.append("terminal run should pause monitor and clear interval")
    else:
        warnings.append(f"unknown state {state!r}; ensure cadence is intentionally chosen")
    if payload.get("automation_kind") != "heartbeat":
        warnings.append("Codex app monitor should use heartbeat when available")
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(path),
        "state": state,
        "interval_minutes": interval,
        "monitor_id": payload.get("monitor_id"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", default="experiment/EXPERIMENT_MONITOR_PLAN.json")
    args = parser.parse_args()
    out = lint(args.project, args.plan)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
