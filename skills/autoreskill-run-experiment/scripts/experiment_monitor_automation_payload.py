#!/usr/bin/env python3
"""Build a Codex app automation_update payload from EXPERIMENT_MONITOR_PLAN."""

from __future__ import annotations

import argparse
import json
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


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


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
    desired_rrule = policy.get("desired_rrule") or registry.get("desired_rrule")
    prompt = registry.get("prompt")
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
