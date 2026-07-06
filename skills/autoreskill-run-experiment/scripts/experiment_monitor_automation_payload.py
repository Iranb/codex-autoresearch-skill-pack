#!/usr/bin/env python3
"""Build a Codex app automation_update payload from EXPERIMENT_MONITOR_PLAN."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def bounded_minutes(value: Any, default: int, *, minimum: int = 1, maximum: int = 24 * 60) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def interval_until(value: Any, default: int) -> int:
    due_at = parse_datetime(value)
    if due_at is None:
        return bounded_minutes(default, default)
    seconds = int((due_at - datetime.now(timezone.utc)).total_seconds())
    if seconds <= 0:
        return 1
    return bounded_minutes((seconds + 59) // 60, default)


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def build_prompt(project: str, plan: dict[str, Any], registry: dict[str, Any]) -> str:
    """Build a fresh heartbeat prompt from the current monitor authority.

    Registry prompts can become stale when a heartbeat cadence is recomputed from
    a newer ETA artifact. Prefer an explicit plan prompt when present; otherwise
    synthesize the prompt from the current plan fields instead of reusing old
    job ids or old interval reasons.
    """

    for source in [
        plan.get("prompt"),
        (plan.get("scheduled_wakeup") or {}).get("prompt") if isinstance(plan.get("scheduled_wakeup"), dict) else None,
    ]:
        if present(source):
            return str(source)

    policy = plan.get("check_interval_policy") if isinstance(plan.get("check_interval_policy"), dict) else {}
    scheduled = plan.get("scheduled_wakeup") if isinstance(plan.get("scheduled_wakeup"), dict) else {}
    job_id = str(plan.get("active_async_job_id") or scheduled.get("job_id") or "").strip()
    stage = str(plan.get("stage") or "experiment").strip()
    due_at = str(plan.get("next_check_at") or plan.get("next_check_after") or scheduled.get("due_at") or "").strip()
    selected_interval = policy.get("interval_minutes") or plan.get("poll_interval_minutes") or plan.get("interval_minutes")
    interval = interval_until(due_at, bounded_minutes(selected_interval, 5))
    reason = str(
        policy.get("reason")
        or plan.get("last_cadence_reason")
        or registry.get("last_cadence_reason")
        or "dynamic experiment monitor interval"
    ).strip()
    progress = str(plan.get("observed_progress") or plan.get("active_runs_summary") or "").strip()
    signal = str(plan.get("latest_runtime_signal") or plan.get("latest_poll_decision") or "").strip()

    prompt = (
        "Resume AutoResearch async polling for project "
        f"{project}. First run ensure_project_agents.py --project <project>, then goal.py status --project <project>, "
        "goal.py reconcile --project <project> --stale-minutes 60, and goal.py tick --project <project>. "
        "If tick dispatches the target async poll job or a successor experiment poll job, dispatch it serialized through "
        "autoreskill-run-experiment, capture experiment process/GPU/log/result status, sync only lightweight logs/results/predictions "
        "excluding checkpoints/model weights/datasets/raw outputs, update REMOTE_RUN/EXPERIMENT_LEDGER/TRACK_RANKING/"
        "EXPERIMENT_MONITOR_PLAN and monitor artifacts, run relevant lints, update the job, then continue the bounded loop while "
        "locally actionable. "
    )
    if progress:
        prompt += f"Current observed progress: {progress} "
    if signal:
        prompt += f"Latest monitor artifact: {signal}. "
    prompt += (
        f"Target job_id={job_id or '<current experiment poll job>'}, stage={stage}, due_at={due_at or '<from monitor plan>'}, "
        f"poll_interval_minutes={interval}, interval_reason={reason}. "
        "Recompute heartbeat interval from live progress, ETA, and stage boundaries on every resume; update this same heartbeat "
        "without creating duplicates. Do not submit PaperNexus graph imports and do not shut down any remote machine automatically."
    )
    return prompt


def build_payload(project: str, plan_rel: str) -> dict[str, Any]:
    base = ar(project)
    plan = read_json(base / plan_rel, {})
    registry = read_json(base / "automation_registry.json", {})
    missing: list[str] = []
    if not isinstance(plan, dict) or not plan:
        return {"ok": False, "status": "missing_plan", "missing": [plan_rel], "payload": None}
    if not isinstance(registry, dict):
        registry = {}

    reuse = plan.get("reuse_policy") if isinstance(plan.get("reuse_policy"), dict) else {}
    policy = plan.get("check_interval_policy") if isinstance(plan.get("check_interval_policy"), dict) else {}
    action = str(reuse.get("action") or "").strip().lower()
    monitor_id = str(plan.get("monitor_id") or registry.get("automation_id") or "").strip()
    selected_interval = policy.get("interval_minutes") or plan.get("poll_interval_minutes") or plan.get("interval_minutes")
    next_check_at = plan.get("next_check_at") or plan.get("next_check_after")
    actual_interval = interval_until(next_check_at, bounded_minutes(selected_interval, 5))
    desired_rrule = f"FREQ=MINUTELY;INTERVAL={actual_interval}"
    prompt = build_prompt(project, plan, registry)
    name = registry.get("automation_name") or registry.get("automation_key") or f"AutoResearch monitor {plan.get('run_id') or 'run'}"

    for key, value in [("name", name), ("prompt", prompt)]:
        if not present(value):
            missing.append(key)
    if action in {"create", "update"} and not present(desired_rrule):
        missing.append("check_interval_policy.desired_rrule")
    if action in {"update", "pause"} and not present(monitor_id):
        missing.append("monitor_id for update/pause")

    mode = "create"
    status = "ACTIVE"
    if action == "update":
        mode = "update"
    elif action == "pause":
        mode = "update"
        status = "PAUSED"
    elif action in {"none", ""}:
        return {
            "ok": True,
            "status": "no_automation_action_required",
            "missing": [],
            "payload": None,
            "reason": "monitor plan has no active create/update/pause action",
        }

    payload = {
        "mode": mode,
        "kind": "heartbeat",
        "destination": "thread",
        "name": name,
        "prompt": prompt,
        "status": status,
    }
    if mode == "update":
        payload["id"] = monitor_id
    if status == "ACTIVE":
        payload["rrule"] = desired_rrule

    return {
        "ok": not missing,
        "status": "ready" if not missing else "incomplete",
        "missing": missing,
        "payload": payload if not missing else None,
        "plan_path": plan_rel,
        "registry_path": "automation_registry.json",
        "reuse_action": action,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", default="experiment/EXPERIMENT_MONITOR_PLAN.json")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", default="experiment/EXPERIMENT_MONITOR_AUTOMATION_PAYLOAD.json")
    args = parser.parse_args()
    out = build_payload(args.project, args.plan)
    if args.write:
        write_json(ar(args.project) / args.output, out)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
