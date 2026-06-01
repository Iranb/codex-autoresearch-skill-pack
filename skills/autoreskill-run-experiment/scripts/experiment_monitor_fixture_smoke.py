#!/usr/bin/env python3
"""Run offline fixture smoke tests for adaptive experiment monitor plans."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPTS = ROOT / "autoreskill-run-experiment/scripts"


def run(cmd: list[str], *, expect: int = 0) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"stdout": proc.stdout}
    parsed["returncode"] = proc.returncode
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    if proc.returncode != expect:
        raise AssertionError(f"{cmd} returned {proc.returncode}, expected {expect}: {parsed}")
    return parsed


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def base_project() -> Path:
    root = Path(tempfile.mkdtemp(prefix="autoreskill-monitor-"))
    base = root / ".autoreskill"
    write(
        base / "orchestrator/INNOVATION_PACKET.json",
        {
            "selected_idea_id": "IDEA-001",
            "innovation_mechanism": "fixture mechanism",
            "mechanism_type": "ALGO",
        },
    )
    write(
        base / "planner/EXPERIMENT_REVIEW_PACKET.json",
        {
            "selected_idea_id": "IDEA-001",
            "track_id": "fixture-track",
            "metric_direction": "higher",
        },
    )
    write(
        base / "coder/experiments/fixture/EXPERIMENT_MANIFEST.json",
        {
            "experiment_id": "exp-monitor-fixture",
            "track_id": "fixture-track",
            "selected_idea_id": "IDEA-001",
            "innovation_mechanism": "fixture mechanism",
            "mechanism_type": "ALGO",
            "promotion_stage": "candidate",
            "primary_metric": "accuracy",
            "metric_direction": "higher",
            "dataset": "fixture",
            "data_split": "fixture",
            "evaluate_command": "python evaluate.py",
            "locked_protocol": {"fixture": True},
            "source_snapshot": {"fixture": True},
        },
    )
    return root


def case_running_reuses_monitor() -> dict[str, Any]:
    root = base_project()
    try:
        run(
            [
                sys.executable,
                str(RUN_SCRIPTS / "run_reconcile.py"),
                "--project",
                str(root),
                "--backend",
                "autodl",
                "--status",
                "running",
                "--estimated-remaining-minutes",
                "8",
                "--automation-id",
                "monitor-fixture-1",
            ]
        )
        lint = run([sys.executable, str(RUN_SCRIPTS / "experiment_monitor_plan_lint.py"), "--project", str(root)])
        payload = run([sys.executable, str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"), "--project", str(root), "--write"])
        plan = json.loads((root / ".autoreskill/experiment/EXPERIMENT_MONITOR_PLAN.json").read_text(encoding="utf-8"))
        registry = json.loads((root / ".autoreskill/automation_registry.json").read_text(encoding="utf-8"))
        if plan.get("check_interval_policy", {}).get("interval_minutes") != 8:
            raise AssertionError(f"expected ETA completion wakeup interval 8, got {plan.get('check_interval_policy', {}).get('interval_minutes')}")
        if plan.get("check_interval_policy", {}).get("reason") != "stable_training_estimated_finish_wakeup":
            raise AssertionError(f"expected completion wakeup reason, got {plan.get('check_interval_policy', {}).get('reason')}")
        return {
            "case": "running_reuses_monitor",
            "lint_status": lint.get("status"),
            "interval_minutes": lint.get("interval_minutes"),
            "monitor_id": lint.get("monitor_id"),
            "reuse_action": plan.get("reuse_policy", {}).get("action"),
            "automation_payload_status": payload.get("status"),
            "automation_payload_mode": payload.get("payload", {}).get("mode"),
            "registry_status": registry.get("status"),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_long_eta_not_clamped_to_default() -> dict[str, Any]:
    root = base_project()
    try:
        run(
            [
                sys.executable,
                str(RUN_SCRIPTS / "run_reconcile.py"),
                "--project",
                str(root),
                "--backend",
                "autodl",
                "--status",
                "running",
                "--estimated-remaining-minutes",
                "720",
                "--automation-id",
                "monitor-fixture-1",
            ]
        )
        plan = json.loads((root / ".autoreskill/experiment/EXPERIMENT_MONITOR_PLAN.json").read_text(encoding="utf-8"))
        interval = plan.get("check_interval_policy", {}).get("interval_minutes")
        if interval != 720:
            raise AssertionError(f"expected long ETA interval 720, got {interval}")
        return {
            "case": "long_eta_not_clamped_to_default",
            "interval_minutes": interval,
            "desired_rrule": plan.get("check_interval_policy", {}).get("desired_rrule"),
            "reason": plan.get("check_interval_policy", {}).get("reason"),
            "expected_finish_at_present": bool(plan.get("expected_finish_at")),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_terminal_pauses_monitor() -> dict[str, Any]:
    root = base_project()
    try:
        run(
            [
                sys.executable,
                str(RUN_SCRIPTS / "run_reconcile.py"),
                "--project",
                str(root),
                "--backend",
                "autodl",
                "--status",
                "completed",
                "--automation-id",
                "monitor-fixture-1",
            ]
        )
        lint = run([sys.executable, str(RUN_SCRIPTS / "experiment_monitor_plan_lint.py"), "--project", str(root)])
        payload = run([sys.executable, str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"), "--project", str(root), "--write"])
        plan = json.loads((root / ".autoreskill/experiment/EXPERIMENT_MONITOR_PLAN.json").read_text(encoding="utf-8"))
        return {
            "case": "terminal_pauses_monitor",
            "lint_status": lint.get("status"),
            "interval_minutes": lint.get("interval_minutes"),
            "next_check_after": plan.get("next_check_after"),
            "reuse_action": plan.get("reuse_policy", {}).get("action"),
            "automation_payload_status": payload.get("status"),
            "automation_payload_mode": payload.get("payload", {}).get("mode"),
            "automation_payload_lifecycle": payload.get("payload", {}).get("status"),
            "status": plan.get("status"),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    results = [case_running_reuses_monitor(), case_long_eta_not_clamped_to_default(), case_terminal_pauses_monitor()]
    print(json.dumps({"ok": True, "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
