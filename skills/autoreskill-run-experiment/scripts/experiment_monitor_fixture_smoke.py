#!/usr/bin/env python3
"""Run offline fixture smoke tests for adaptive experiment monitor plans."""

from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPTS = ROOT / "autoreskill-run-experiment/scripts"
OPPORTUNITY_SCAN_MARKER = "[heartbeat-experiment-opportunity-scan-v3:start]"


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
        prompt = str(payload.get("payload", {}).get("prompt") or "")
        if (
            OPPORTUNITY_SCAN_MARKER not in prompt
            or "exact deterministic feasible shortlist subset" not in prompt
            or "replenish_experiment_portfolio" not in prompt
            or "zero tracks are active" not in prompt
            or "research_decision.py --replenishment --write" not in prompt
        ):
            raise AssertionError(f"mandatory heartbeat opportunity scan missing: {prompt}")
        if prompt.count(OPPORTUNITY_SCAN_MARKER) != 1:
            raise AssertionError(f"heartbeat v2 contract must appear exactly once: {prompt}")
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


def case_pause_is_overridden_by_live_queue() -> dict[str, Any]:
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
                "monitor-fixture-live-queue",
            ]
        )
        base = root / ".autoreskill"
        write(
            base / "experiment/NEXT_EXPERIMENT_QUEUE.json",
            {"policy": {"admission_scope": "project"}, "rows": [{"id": "live", "status": "running"}]},
        )
        current_path = base / "control/current_automation.json"
        write(
            current_path,
            {
                "id": "monitor-fixture-live-queue",
                "name": "fixture live monitor",
                "prompt": "CURRENT APP PROMPT",
                "status": "ACTIVE",
                "rrule": "FREQ=MINUTELY;INTERVAL=20",
            },
        )
        payload = run(
            [
                sys.executable,
                str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"),
                "--project",
                str(root),
                "--current-automation",
                str(current_path),
            ]
        )
        rendered = payload.get("payload") or {}
        if rendered.get("mode") != "update" or rendered.get("status") != "ACTIVE":
            raise AssertionError(f"live queue did not override stale pause: {payload}")
        if rendered.get("rrule") != "FREQ=MINUTELY;INTERVAL=20":
            raise AssertionError(f"current active cadence was not preserved: {payload}")
        if not payload.get("pause_or_delete_overridden") or "external_or_claimed_queue_work:running" not in payload.get(
            "continuation_reasons", []
        ):
            raise AssertionError(f"override evidence missing: {payload}")
        if not str(rendered.get("prompt") or "").startswith("CURRENT APP PROMPT"):
            raise AssertionError(f"current managed prompt was not preserved: {payload}")
        return {
            "case": "pause_is_overridden_by_live_queue",
            "effective_action": payload.get("effective_reuse_action"),
            "rrule": rendered.get("rrule"),
            "continuation_reasons": payload.get("continuation_reasons"),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_readback_verification() -> dict[str, Any]:
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
                "9",
                "--automation-id",
                "monitor-fixture-readback",
            ]
        )
        generated = run(
            [
                sys.executable,
                str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"),
                "--project",
                str(root),
                "--write",
            ]
        )
        payload = generated["payload"]
        expected_path = root / ".autoreskill/experiment/EXPERIMENT_MONITOR_AUTOMATION_PAYLOAD.json"
        readback_path = root / ".autoreskill/control/readback.json"
        write(
            readback_path,
            {
                "id": payload["id"],
                "name": payload["name"],
                "prompt": payload["prompt"],
                "status": payload["status"],
                "rrule": payload["rrule"],
            },
        )
        verified = run(
            [
                sys.executable,
                str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"),
                "--project",
                str(root),
                "--expected-payload",
                str(expected_path),
                "--readback",
                str(readback_path),
            ]
        )
        if not verified.get("readback_verification", {}).get("ok"):
            raise AssertionError(f"matching readback did not verify: {verified}")
        bad = json.loads(readback_path.read_text(encoding="utf-8"))
        bad["prompt"] += " drift"
        write(readback_path, bad)
        rejected = run(
            [
                sys.executable,
                str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"),
                "--project",
                str(root),
                "--expected-payload",
                str(expected_path),
                "--readback",
                str(readback_path),
            ],
            expect=1,
        )
        if rejected.get("status") != "readback_mismatch":
            raise AssertionError(f"drifted readback did not fail closed: {rejected}")
        return {"case": "readback_verification", "verified": True, "drift_status": rejected.get("status")}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_prompt_revision_gate() -> dict[str, Any]:
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
                "12",
                "--automation-id",
                "monitor-fixture-prompt",
            ]
        )
        base = root / ".autoreskill"
        plan_path = base / "experiment/EXPERIMENT_MONITOR_PLAN.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        stale_prompt = "STALE PROMPT MUST NOT SURVIVE"
        plan.update(
            {
                "prompt": stale_prompt,
                "prompt_plan_revision": int(plan["monitor_plan_revision"]) - 1,
                "prompt_plan_sha256": plan["monitor_plan_semantic_sha256"],
                "prompt_sha256": hashlib.sha256(stale_prompt.encode("utf-8")).hexdigest(),
            }
        )
        write(plan_path, plan)
        write(
            base / "experiment/NEXT_EXPERIMENT_QUEUE.json",
            {
                "policy": {"admission_scope": "global"},
                "rows": [
                    {"id": "ready-global", "status": "ready"},
                    {"id": "running-global", "status": "running"},
                ],
            },
        )
        stale = run([sys.executable, str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"), "--project", str(root)])
        synthesized = str(stale.get("payload", {}).get("prompt") or "")
        if stale_prompt in synthesized:
            raise AssertionError("stale explicit prompt was reused")
        if "admission_scope=global" not in synthesized or "do not claim or submit" not in synthesized:
            raise AssertionError(f"global monitor ownership was not synthesized: {synthesized}")
        if OPPORTUNITY_SCAN_MARKER not in synthesized or "global dispatcher" not in synthesized:
            raise AssertionError(f"global opportunity scan was not synthesized: {synthesized}")

        current_prompt = "CURRENT REVISION-BOUND PROMPT"
        plan["prompt"] = current_prompt
        plan["prompt_plan_revision"] = plan["monitor_plan_revision"]
        plan["prompt_plan_sha256"] = plan["monitor_plan_semantic_sha256"]
        plan["prompt_sha256"] = hashlib.sha256(current_prompt.encode("utf-8")).hexdigest()
        write(plan_path, plan)
        current = run([sys.executable, str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"), "--project", str(root)])
        current_payload_prompt = str(current.get("payload", {}).get("prompt") or "")
        if not current_payload_prompt.startswith(current_prompt) or OPPORTUNITY_SCAN_MARKER not in current_payload_prompt:
            raise AssertionError(f"current explicit prompt was not accepted and augmented: {current}")
        return {
            "case": "prompt_revision_gate",
            "stale_prompt_source": stale.get("prompt_source"),
            "current_prompt_source": current.get("prompt_source"),
            "global_scope_synthesized": True,
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_delete_and_unknown_fail_closed() -> dict[str, Any]:
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
                "monitor-fixture-delete",
            ]
        )
        plan_path = root / ".autoreskill/experiment/EXPERIMENT_MONITOR_PLAN.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan.setdefault("reuse_policy", {})["action"] = "delete"
        write(plan_path, plan)
        deleted = run([sys.executable, str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"), "--project", str(root)])
        if deleted.get("payload", {}).get("mode") != "delete" or "rrule" in deleted.get("payload", {}):
            raise AssertionError(f"delete action was not mapped exactly: {deleted}")
        plan.setdefault("reuse_policy", {})["action"] = "mystery"
        write(plan_path, plan)
        unknown = run(
            [sys.executable, str(RUN_SCRIPTS / "experiment_monitor_automation_payload.py"), "--project", str(root)],
            expect=1,
        )
        if unknown.get("status") != "unsupported_reuse_action" or unknown.get("payload") is not None:
            raise AssertionError(f"unknown action did not fail closed: {unknown}")
        return {"case": "delete_and_unknown_fail_closed", "delete_mode": "delete", "unknown_status": unknown.get("status")}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    results = [
        case_running_reuses_monitor(),
        case_long_eta_not_clamped_to_default(),
        case_terminal_pauses_monitor(),
        case_pause_is_overridden_by_live_queue(),
        case_readback_verification(),
        case_prompt_revision_gate(),
        case_delete_and_unknown_fail_closed(),
    ]
    print(json.dumps({"ok": True, "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
