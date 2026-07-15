#!/usr/bin/env python3
"""Run one atomic /goal tick for portable AutoResearch projects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from contract_lint import lint, validate_terminal_program_decision
from control_plane_lease import acquire as acquire_control_lease
from control_plane_lease import release as release_control_lease
from experiment_next_actions import frontier_status, select_launch_batch
from goal_state import NEXT_ACTIONS, OWNERS, STAGES, ar, load_state, next_stage, save_state
from research_decision import program_recovery_status, replenishment_proposal


SKILLS_ROOT = Path(__file__).resolve().parents[2]
INNOVATION_STORY_STAGES = {"ideation", "idea_gate", "experiment_plan", "analysis", "review_pressure", "writing", "submission_ready"}
PAPER_CODE_TRANSFER_STAGES = {"literature_review", "ideation", "idea_gate", "experiment_plan"}
BASELINE_REPORT_ALIGNMENT_STAGES = {"experiment_plan", "code", "experiment", "analysis", "review_pressure", "writing", "submission_ready"}
CRITICAL_EVALUATOR_STAGES = {"idea_gate", "experiment_plan", "analysis", "review_pressure", "writing", "submission_ready"}
INNOVATION_STORY_FILES = [
    ".autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md",
    ".autoreskill/user_view/innovation_story/01_METHOD_INNOVATION_STORY.md",
    ".autoreskill/user_view/innovation_story/02_CLAIM_EVIDENCE_MAP.md",
]
PAPER_CODE_TRANSFER_FILES = [
    ".autoreskill/survey/PAPER_CODE_SURVEY_PLAN.json",
    ".autoreskill/survey/PAPER_CODE_CANDIDATES.json",
    ".autoreskill/survey/REPO_STATIC_EVIDENCE.json",
    ".autoreskill/survey/CODE_MECHANISM_MAP.json",
    ".autoreskill/ideation/INNOVATION_MIGRATION_MATRIX.json",
    ".autoreskill/user_view/innovation_story/03_CODE_TRANSFER_STORY.md",
]
PAPER_CODE_TRANSFER_ARTIFACTS = [
    "survey/PAPER_CODE_SURVEY_PLAN.json",
    "survey/PAPER_CODE_CANDIDATES.json",
    "survey/REPO_STATIC_EVIDENCE.json",
    "survey/CODE_MECHANISM_MAP.json",
    "ideation/INNOVATION_MIGRATION_MATRIX.json",
]
PAPER_CODE_TOKENS = (
    "paper_code_transfer_lint",
    "paper-code",
    "code survey",
    "code analysis",
    "source code",
    "source-code",
    "repository validation",
    "repo",
    "repos",
    "repository",
    "repositories",
    "github",
    "源码",
    "代码",
    "仓库",
)
PAPER_CODE_INTENT_TOKENS = (
    "survey",
    "analysis",
    "analyze",
    "validation",
    "innovation",
    "transfer",
    "migration",
    "调研",
    "分析",
    "验证",
    "创新",
    "迁移",
)


def script_cmd(skill: str, script: str, args: str = "") -> str:
    script_path = SKILLS_ROOT / skill / "scripts" / script
    cmd = f"python {shlex.quote(str(script_path))}"
    if args:
        cmd = f"{cmd} {args}"
    return cmd


def has_literature_search(calls: list[Any]) -> bool:
    for call in calls:
        if not isinstance(call, dict) or call.get("tool") != "literature_discovery":
            continue
        args = call.get("args")
        if isinstance(args, dict) and args.get("operation") in {"search", "submit"}:
            return True
    return False


def contains_trigger_token(text: str, token: str) -> bool:
    if token.isascii():
        return re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text) is not None
    return token in text


def has_paper_code_transfer_request(base: Path, state: dict[str, Any], job: dict[str, Any], contract: dict[str, Any]) -> bool:
    if any((base / rel).exists() for rel in PAPER_CODE_TRANSFER_ARTIFACTS):
        return True
    text_parts = [
        state.get("goal"),
        state.get("objective"),
        state.get("research_goal"),
        state.get("topic"),
        state.get("next_action"),
        job.get("action"),
        job.get("kind"),
        job.get("reason"),
        job.get("notes"),
        contract.get("contract_source"),
        contract.get("missing"),
        contract.get("warnings"),
    ]
    text = " ".join(
        json.dumps(part, ensure_ascii=False, default=str) if isinstance(part, (dict, list)) else str(part or "")
        for part in text_parts
    ).lower()
    if "paper_code_transfer_lint" in text:
        return True
    return any(contains_trigger_token(text, token) for token in PAPER_CODE_TOKENS) and any(
        contains_trigger_token(text, token) for token in PAPER_CODE_INTENT_TOKENS
    )


def append_unique(items: list[str], additions: list[str]) -> list[str]:
    out = list(items)
    for item in additions:
        if item not in out:
            out.append(item)
    return out


def unique_strings(items: list[Any]) -> list[str]:
    out: list[str] = []
    for item in items:
        text = str(item)
        if text not in out:
            out.append(text)
    return out


def acceptance_contract_for_packet(
    stage: str,
    outputs: list[Any],
    capture_commands: list[Any],
    constraints: list[str],
    acceptance_criteria: list[str],
    *,
    literature_search: bool,
    paper_code_transfer_requested: bool,
) -> dict[str, Any]:
    lint_command = script_cmd("autoreskill-workflow", "contract_lint.py", f"--project <project-root> --stage {stage}")
    lint_commands = [lint_command]
    lint_commands.extend(str(command) for command in capture_commands if "_lint.py" in str(command) or "contract_lint.py" in str(command))

    claim_boundaries = [
        "Claims must be bounded by captured citations, PaperNexus evidence, or matched experiment artifacts.",
        "Unsupported claims must become explicit blockers, downgraded claims, or limitations.",
    ]
    if literature_search:
        claim_boundaries.append("Raw discovery rows are recall evidence only until graph/material evidence is captured.")
    if stage in {"code", "experiment", "analysis", "review_pressure", "writing", "submission_ready"}:
        claim_boundaries.append("Candidate, smoke, or diagnostic runs cannot support effectiveness claims.")
    if paper_code_transfer_requested:
        claim_boundaries.append("Repository evidence can support mechanism feasibility only; performance claims require matched experiments.")

    evaluator_commands: list[str] = []
    if stage in CRITICAL_EVALUATOR_STAGES:
        evaluator_commands.append(
            "Before advancing after claim, selected-idea, promoted-result, or manuscript-readiness changes, prepare an Evaluator handoff with read-only inputs and evaluator-only write scope."
        )

    return {
        "must_produce": unique_strings(outputs),
        "must_pass": unique_strings(lint_commands),
        "must_not_violate": unique_strings(constraints),
        "claim_boundaries": unique_strings(claim_boundaries),
        "evaluator_commands": evaluator_commands,
        "done_when": unique_strings(acceptance_criteria),
    }


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def active_retry_override(base: Path, args: argparse.Namespace) -> dict[str, Any] | None:
    if getattr(args, "force_due_repair", False):
        return {
            "schema_version": 1,
            "enabled": True,
            "kind": "repair",
            "job_id": getattr(args, "force_job_id", None),
            "reason": "cli_force_due_repair",
            "source": "goal_tick_cli",
        }

    path = base / "control" / "ACTIVE_RETRY_OVERRIDE.json"
    data = read_json(path, {})
    if not isinstance(data, dict) or not data.get("enabled", False):
        return None
    expires_at = parse_iso_datetime(data.get("expires_at"))
    if expires_at is not None and expires_at <= now():
        return None
    return data


def retry_override_matches(job: dict[str, Any], override: dict[str, Any] | None, kind: str) -> bool:
    if not override:
        return False
    override_kind = str(override.get("kind") or "repair")
    if override_kind not in {"any", kind}:
        return False
    job_id = override.get("job_id")
    if job_id and str(job.get("job_id")) != str(job_id):
        return False
    stage = override.get("stage")
    if stage and str(job.get("stage")) != str(stage):
        return False
    action = override.get("action")
    if action and str(job.get("action")) != str(action):
        return False
    reason_contains = override.get("reason_contains")
    if reason_contains and str(reason_contains) not in str(job.get("reason") or ""):
        return False
    return True


def bounded_minutes(value: Any, default: int, *, minimum: int = 1, maximum: int = 24 * 60) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def poll_delay_minutes(policy: dict[str, Any], kind: str) -> int:
    if kind == "async":
        return bounded_minutes(policy.get("async_poll_interval_minutes"), 5)
    return bounded_minutes(policy.get("repair_retry_interval_minutes"), 5)


COMPLETE_STATES = {"complete", "completed", "ready", "succeeded", "success", "superseded", "not_required", "not-required", "none", "skipped"}
FAILED_STATES = {"failed", "error", "errored", "cancelled", "canceled"}
RUNNING_STATES = {"running", "processing", "in_progress", "fast-commit", "fast_commit", "semantic", "authoritative-sync", "authoritative_sync"}
QUEUED_STATES = {"pending", "queued", "submitted", "waiting"}
ASYNC_HEARTBEAT_ACTIONS = {"poll_literature_discovery", "poll_graph_import_sync", "poll_experiment_run"}
EXPERIMENT_ACTIVE_STATUSES = {
    "active",
    "queued",
    "pending",
    "submitted",
    "submitting",
    "needs_sync",
    "launching",
    "starting",
    "started",
    "running",
    "processing",
    "in_progress",
    "submitted_running",
    "running_or_queued",
    "bjtu_hpc_running_or_queued",
    "waiting_for_gpu",
    "waiting_for_gpu_idle",
    "waiting_for_resource",
    "guarded_waiting",
    "resource_wait",
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
}
EXPERIMENT_IDLE_STATUSES = {
    "idle",
    "resource_idle",
    "gpu_idle_launch_ready",
    "launch_ready",
    "ready_to_launch",
    "ready_for_launch",
    "repair_ready",
    "no_active_run",
    "no_active_runs",
    "no_live_run",
    "no_live_runs",
    "no_active_task",
    "no_active_tasks",
    "no_active_training",
    "all_runs_terminal",
    "terminal_no_runtime_wait",
    "terminal_no_next_heartbeat",
}
EXPERIMENT_IDLE_MARKERS = (
    "no active run",
    "no active runs",
    "no live run",
    "no live runs",
    "no live track",
    "no active training",
    "no experiment process",
    "no runtime process",
    "all runs terminal",
    "all experiments terminal",
    "gpu idle and no active",
    "resource idle and no active",
)
EXPERIMENT_BUSY_MARKERS = (
    "remains active",
    "remain active",
    "runs remain active",
    "active with",
    "active in",
    "running",
    "training",
    "queued",
    "pending",
    "submitted",
    "launching",
    "starting",
    "waiting_for",
    "waiting for",
    "resource_wait",
    "resource wait",
    "external_live_wait",
    "external live wait",
)
EXPERIMENT_TERMINAL_STATUSES = COMPLETE_STATES | FAILED_STATES | {
    "terminal",
    "done",
    "finished",
    "completed_terminal",
    "completed_terminal_no_summary",
    "completed_terminal_log_metrics_no_summary",
    "completed_terminal_repair01_log_metrics_no_summary",
    "completed_negative_v3_not_promoted",
    "terminal_no_runtime_wait",
    "terminal_no_next_heartbeat",
    "failed_runtime_index_mapping_no_summary",
    "failed_runtime_ulimit_no_summary",
}
EXPERIMENT_FAILURE_DECISIONS = {
    "failed",
    "failure",
    "budget_stopped",
    "not_promoted",
    "rollback_to_best",
    "repair",
    "regressed",
    "regression",
}
EXPERIMENT_REPAIR_ACTIONS = {
    "repair_same_branch",
    "repair",
    "rerun_after_fix",
    "run_ablation_or_confirmation",
    "debug_fix",
    "fix_and_rerun",
}
EXPERIMENT_REBUILD_ACTIONS = {
    "switch_track",
    "leap_idea",
    "rebuild_idea",
    "change_idea",
    "change_innovation",
    "negative_result_route",
}


def parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def normalized_state(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip().lower().replace("-", "_")
        if text:
            return text
    return ""


def import_task_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("taskId") or row.get("task_id") or "").strip()


def import_task_status(row: dict[str, Any]) -> str:
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    return normalized_state(row.get("status"), progress.get("status"))


def import_task_stage(row: dict[str, Any]) -> str:
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    return normalized_state(row.get("phase"), row.get("stage"), progress.get("stage"), progress.get("phase"))


def import_task_percent(row: dict[str, Any]) -> float | None:
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    for value in [row.get("percent"), row.get("stagePercent"), progress.get("percent"), progress.get("stagePercent")]:
        parsed = parse_float(value)
        if parsed is not None:
            return parsed
    return None


def import_task_queue_position(row: dict[str, Any]) -> int | None:
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    for value in [progress.get("queuePosition"), row.get("queuePosition")]:
        parsed = parse_int(value)
        if parsed is not None:
            return parsed
    return None


def import_task_processed_rate_interval(row: dict[str, Any], default: int) -> tuple[int, str] | None:
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    processed = parse_int(progress.get("processedUnits") or row.get("processedUnits"))
    total = parse_int(progress.get("totalUnits") or row.get("totalUnits"))
    percent = import_task_percent(row)
    if total and processed is not None and total > 0:
        remaining_units = max(0, total - processed)
        if remaining_units == 0:
            return bounded_minutes(default / 2, 1), f"selected task has processed {processed}/{total} units; next check follows the next stage boundary"
        observed_units = max(1, processed)
        interval = bounded_minutes((remaining_units / observed_units) * default, default)
        return interval, f"selected task has processed {processed}/{total} units; interval estimated from remaining/processed unit ratio"
    if percent is not None:
        remaining_pct = max(0.0, 100.0 - percent)
        if remaining_pct <= max(1.0, percent * 0.05):
            return bounded_minutes(default / 2, 1), f"selected task is near a progress boundary at {percent:.1f}%; next check follows the boundary"
        interval = bounded_minutes((remaining_pct / max(percent, 1.0)) * default, default)
        return interval, f"selected task progress is {percent:.1f}%; interval estimated from remaining/progress ratio"
    return None


def import_queue_summary(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ["queueSnapshot", "queueSummary", "queue_summary", "summary"]:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def import_status_tasks(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def raw_import_tasks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for key in ["targetTasks", "target_tasks", "selectedTasks", "selected_tasks", "relevantTasks", "relevant_tasks", "tasks", "task"]:
        tasks.extend(import_status_tasks(payload, key))
    for key in ["result", "data", "response", "payload"]:
        value = payload.get(key)
        if isinstance(value, dict):
            tasks.extend(raw_import_tasks(value))
    unique: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for row in tasks:
        task_id = import_task_id(row)
        if task_id:
            unique[task_id] = row
        else:
            anonymous.append(row)
    return [*unique.values(), *anonymous]


def sync_complete(row: dict[str, Any]) -> bool:
    status = normalized_state(row.get("authoritativeSyncStatus"), row.get("authoritativeSync"))
    sync = row.get("authoritativeSync") or row.get("authoritative_sync")
    if isinstance(sync, dict):
        status = normalized_state(sync.get("status"), status)
    result = row.get("result")
    if isinstance(result, dict):
        nested = result.get("authoritativeSync") or result.get("authoritative_sync")
        if isinstance(nested, dict):
            status = normalized_state(nested.get("status"), status)
        status = normalized_state(result.get("authoritativeSyncStatus"), status)
    return status in COMPLETE_STATES


def graph_visible_complete(row: dict[str, Any]) -> bool:
    return normalized_state(row.get("graphVisibilityStatus"), row.get("graphVisibility"), row.get("graph_visible")) in COMPLETE_STATES


def semantic_complete(row: dict[str, Any]) -> bool:
    return normalized_state(row.get("semanticStatus"), row.get("semantic"), row.get("semantic_status")) in COMPLETE_STATES


def import_task_complete(row: dict[str, Any]) -> bool:
    return import_task_status(row) in COMPLETE_STATES and import_task_stage(row) in COMPLETE_STATES


def import_task_failed(row: dict[str, Any]) -> bool:
    return import_task_status(row) in FAILED_STATES or import_task_stage(row) in FAILED_STATES


def graph_import_poll_delay_minutes(base: Path, policy: dict[str, Any], stage: str, action: str, reason: str) -> tuple[int, str]:
    default = bounded_minutes(policy.get("async_poll_interval_minutes"), 5)
    if action != "poll_graph_import_sync" and "import_workflow" not in reason.lower() and "authoritative" not in reason.lower():
        return default, f"default async poll interval from policy: {default} minutes"

    payload = read_json(base / "papernexus/IMPORT_WORKFLOW_STATUS.json", {})
    payload = unwrap_capture(payload)
    if not isinstance(payload, dict) or not payload:
        return default, f"graph import status artifact is missing; use default async poll interval {default} minutes"

    artifact_interval = (
        payload.get("selected_poll_interval_minutes")
        or payload.get("poll_interval_minutes")
        or payload.get("recommended_next_poll_minutes")
    )
    artifact_reason = (
        payload.get("poll_interval_reason")
        or payload.get("poll_interval_decision")
        or payload.get("eta_basis")
    )
    if artifact_interval is not None:
        interval = bounded_minutes(artifact_interval, default)
        reason_text = str(artifact_reason or "dynamic interval recorded by the latest live import_workflow poll").strip()
        return interval, f"latest live graph-import status selected a dynamic {interval}-minute heartbeat: {reason_text}"

    target_tasks = import_status_tasks(payload, "targetTasks") or import_status_tasks(payload, "target_tasks")
    tasks = target_tasks or raw_import_tasks(payload)
    side_effect_tasks = import_status_tasks(payload, "nonSelectedSideEffectImports") + import_status_tasks(payload, "sideEffectImports")
    summary = import_queue_summary(payload)
    active_task_id = str(summary.get("activeTaskId") or summary.get("activeTask") or "").strip()
    active_stage = normalized_state(summary.get("activeStage"), summary.get("activePhase"))
    remaining = parse_int(summary.get("remaining"))
    active_task = next((row for row in [*tasks, *side_effect_tasks] if import_task_id(row) == active_task_id), None)

    if any(import_task_failed(row) for row in tasks):
        return bounded_minutes(default / 2, 1), "selected graph import task failed or was cancelled; schedule the next check sooner than the policy default for repair routing"

    if tasks and all(import_task_complete(row) and graph_visible_complete(row) and semantic_complete(row) and sync_complete(row) for row in tasks):
        return bounded_minutes(default / 2, 1), "all selected graph import tasks appear complete and authoritative-synced; schedule the next check sooner than the policy default so WorkflowGuard can advance or reconcile stale artifacts"

    unsynced = [
        row
        for row in tasks
        if import_task_complete(row) and graph_visible_complete(row) and semantic_complete(row) and not sync_complete(row)
    ]
    if unsynced and len(unsynced) == len(tasks):
        return bounded_minutes(default, 1), "selected tasks are graph-visible but authoritative sync is still pending; use the policy cadence until sync progress is observed"

    running_targets = [
        row
        for row in tasks
        if import_task_status(row) in RUNNING_STATES or import_task_stage(row) in RUNNING_STATES
    ]
    if running_targets:
        stages = {import_task_stage(row) for row in running_targets}
        estimates = [estimate for estimate in (import_task_processed_rate_interval(row, default) for row in running_targets) if estimate]
        if estimates:
            return min(estimates, key=lambda item: item[0])
        if stages.intersection({"fast-commit", "authoritative-sync"}):
            return bounded_minutes(default / 2, 1), "selected graph import task is in final commit/sync; schedule sooner than policy default until a progress-based ETA is available"
        return default, f"selected graph import task is running but lacks unit/progress ETA; use policy default {default} minutes"

    queued_targets = [
        row
        for row in tasks
        if import_task_status(row) in QUEUED_STATES or import_task_stage(row) in QUEUED_STATES
    ]
    if queued_targets:
        positions = [import_task_queue_position(row) for row in queued_targets]
        positions = [position for position in positions if position is not None]
        min_position = min(positions) if positions else None
        running_workers = parse_int(summary.get("running")) or 0
        if min_position is not None:
            estimated_waves = min_position / max(1, running_workers)
            interval = bounded_minutes(default * max(1.0, estimated_waves), default)
            return interval, (
                "selected graph import task is queued; interval estimated from "
                f"queue_position={min_position}, running_workers={running_workers}, policy_default={default}"
            )
        if active_task and import_task_stage(active_task) in {"fast-commit", "authoritative-sync"}:
            estimate = import_task_processed_rate_interval(active_task, default)
            if estimate:
                return estimate
            return bounded_minutes(default / 2, 1), "active import ahead of the selected target is in final commit/sync; schedule sooner than policy default until a progress-based ETA is available"
        return default, f"selected graph import task is queued but queue position is unavailable; use policy default {default} minutes and record the missing queue-position signal"

    if active_task or active_stage:
        if active_stage in {"fast-commit", "authoritative-sync"}:
            if active_task:
                estimate = import_task_processed_rate_interval(active_task, default)
                if estimate:
                    return estimate
            return bounded_minutes(default / 2, 1), "active graph import is in final commit/sync; schedule sooner than policy default until a progress-based ETA is available"

    if remaining is not None and remaining > 10:
        running_workers = parse_int(summary.get("running")) or 0
        interval = bounded_minutes(default * (remaining / max(1, running_workers)), default)
        return interval, (
            "PaperNexus import queue has remaining work and no selected near-terminal task; interval estimated from "
            f"remaining={remaining}, running_workers={running_workers}, policy_default={default}"
        )

    return default, f"graph import state has no stronger signal; use policy default {default} minutes"


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def interval_from_due_at(due_at: Any, default: int) -> int | None:
    parsed = parse_iso_datetime(due_at)
    if parsed is None:
        return None
    seconds = int((parsed - now()).total_seconds())
    if seconds <= 0:
        return None
    return bounded_minutes((seconds + 59) // 60, default)


def poll_decision_from_payload(payload: Any) -> dict[str, Any]:
    payload = unwrap_capture(payload)
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("poll_interval_decision")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in [
            "selected_interval_minutes",
            "interval_minutes",
            "poll_interval_minutes",
            "recommended_next_poll_minutes",
            "desired_rrule",
            "next_check_at",
            "next_check_after",
            "estimated_next_event_at",
            "reason",
            "interval_reason",
            "eta_basis",
            "estimated_remaining_minutes",
            "expected_finish_at",
            "created_at",
            "updated_at",
        ]:
            if key in payload and key not in merged:
                merged[key] = payload[key]
        return merged
    return payload


def dynamic_interval_from_payload(payload: Any, default: int, source: str) -> tuple[int, str] | None:
    decision = poll_decision_from_payload(payload)
    if not decision:
        return None
    interval_value = (
        decision.get("selected_interval_minutes")
        or decision.get("interval_minutes")
        or decision.get("poll_interval_minutes")
        or decision.get("recommended_next_poll_minutes")
    )
    due_interval = interval_from_due_at(
        decision.get("next_check_at")
        or decision.get("next_check_after")
        or decision.get("estimated_next_event_at"),
        default,
    )
    if due_interval is not None:
        interval = due_interval
    elif interval_value is not None:
        interval = bounded_minutes(interval_value, default)
    else:
        return None
    reason_text = str(
        decision.get("reason")
        or decision.get("interval_reason")
        or decision.get("eta_basis")
        or "dynamic interval recorded by experiment monitor"
    ).strip()
    return interval, f"{source} selected a dynamic {interval}-minute experiment heartbeat: {reason_text}"


def latest_experiment_poll_decision(base: Path) -> tuple[dict[str, Any], str] | None:
    plan = read_json(base / "experiment/EXPERIMENT_MONITOR_PLAN.json", {})
    if isinstance(plan, dict):
        for rel_key in [
            "latest_runtime_signal",
            "latest_runtime_poll",
            "latest_poll_decision",
            "latest_status_artifact",
        ]:
            rel = plan.get(rel_key)
            if isinstance(rel, str) and rel.strip():
                payload = read_json(base / rel, {})
                decision = poll_decision_from_payload(payload)
                if isinstance(decision, dict) and decision:
                    return decision, f"experiment monitor plan {rel_key}"
        policy = plan.get("check_interval_policy") if isinstance(plan.get("check_interval_policy"), dict) else {}
        if policy:
            policy_payload = dict(policy)
            if "next_check_at" not in policy_payload:
                policy_payload["next_check_at"] = plan.get("next_check_at") or plan.get("next_check_after")
            return policy_payload, "experiment monitor plan"
        decision = plan.get("poll_interval_decision")
        if isinstance(decision, dict):
            return decision, "experiment monitor plan"

    registry = read_json(base / "automation_registry.json", {})
    if isinstance(registry, dict):
        decision = registry.get("poll_interval_decision")
        if isinstance(decision, dict):
            return decision, "automation registry"
        monitors = registry.get("monitors")
        if isinstance(monitors, dict):
            for row in monitors.values():
                if isinstance(row, dict) and isinstance(row.get("poll_interval_decision"), dict):
                    return row["poll_interval_decision"], "automation registry monitor"
        for rel_key in ["latest_poll_decision", "latest_poll_wait"]:
            rel = registry.get(rel_key)
            if isinstance(rel, str) and rel.strip():
                payload = read_json(base / rel, {})
                if isinstance(payload, dict):
                    return payload, f"automation registry {rel_key}"

    candidates = sorted(
        [*base.glob("coder/experiments/*/*/RUNTIME_POLL_DECISION_*.json"), *base.glob("coder/experiments/*/*/RUNTIME_POLL_WAIT_*.json")],
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    for path in candidates[:5]:
        payload = read_json(path, {})
        if isinstance(payload, dict):
            try:
                rel = path.relative_to(base)
            except ValueError:
                rel = path
            return payload, str(rel)
    return None


def experiment_poll_delay_minutes(base: Path, policy: dict[str, Any], stage: str, action: str, reason: str) -> tuple[int, str]:
    default = bounded_minutes(policy.get("experiment_monitor_default_interval_minutes"), 30, minimum=5)
    if stage != "experiment" or action != "poll_experiment_run":
        return default, f"default async poll interval from policy: {default} minutes"
    latest = latest_experiment_poll_decision(base)
    if latest is None:
        return default, f"experiment monitor artifact is missing; use experiment monitor fallback interval {default} minutes"
    payload, source = latest
    dynamic = dynamic_interval_from_payload(payload, default, source)
    if dynamic is not None:
        return dynamic
    return default, f"latest experiment monitor artifact has no interval; use experiment monitor fallback interval {default} minutes"


def latest_experiment_fixed_due_at(base: Path, stage: str, action: str) -> tuple[datetime | None, datetime | None, str | None]:
    """Return the authoritative next_check_at from the latest experiment monitor.

    Normal async queueing preserves an earlier due time so a poll is not delayed
    accidentally. Experiment monitors are different: a newer live ETA artifact can
    legitimately lengthen the heartbeat after startup risk clears. This helper
    exposes that fixed due time plus the monitor decision timestamp so queue_job
    can distinguish a stale short poll from an intentionally recomputed long wait.
    """

    if stage != "experiment" or action != "poll_experiment_run":
        return None, None, None
    latest = latest_experiment_poll_decision(base)
    if latest is None:
        return None, None, None
    payload, source = latest
    decision = poll_decision_from_payload(payload)
    if not decision:
        return None, None, source
    due_at = None
    for key in ["next_check_at", "next_check_after"]:
        due_at = parse_iso_datetime(decision.get(key))
        if due_at is not None:
            break
    updated_at = None
    for key in ["updated_at", "created_at"]:
        updated_at = parse_iso_datetime(decision.get(key))
        if updated_at is not None:
            break
    return due_at, updated_at, source


def async_poll_delay_minutes(base: Path, policy: dict[str, Any], stage: str, action: str, reason: str) -> tuple[int, str]:
    if action == "poll_graph_import_sync" or ("import_workflow" in reason.lower() and "graph" in reason.lower()):
        return graph_import_poll_delay_minutes(base, policy, stage, action, reason)
    if stage == "experiment" or action == "poll_experiment_run":
        return experiment_poll_delay_minutes(base, policy, stage, action, reason)
    delay = bounded_minutes(policy.get("async_poll_interval_minutes"), 5)
    return delay, f"default async poll interval from policy: {delay} minutes"


def unwrap_capture(payload: Any) -> Any:
    if isinstance(payload, dict) and "payload" in payload:
        return payload["payload"]
    return payload


def nested_get(payload: Any, path: list[str]) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def discovery_run_id(base: Path) -> str | None:
    payload = unwrap_capture(read_json(base / "literature/LITERATURE_DISCOVERY_RUN.json", {}))
    for path in [
        ["runId"],
        ["current", "runId"],
        ["progress", "runId"],
        ["next", "progress", "runId"],
    ]:
        value = nested_get(payload, path)
        if value:
            return str(value)
    return None


def discovery_report_ready(base: Path) -> bool:
    payload = unwrap_capture(read_json(base / "literature/LITERATURE_DISCOVERY_RUN.json", {}))
    for path in [["current", "reportAvailable"], ["reportAvailable"]]:
        if nested_get(payload, path) is True:
            return True
    for path in [["current", "isTerminal"], ["progress", "isTerminal"], ["isTerminal"]]:
        if nested_get(payload, path) is True:
            return True
    status = str(nested_get(payload, ["current", "status"]) or nested_get(payload, ["progress", "status"]) or nested_get(payload, ["status"]) or "").lower()
    stage = str(nested_get(payload, ["current", "stage"]) or nested_get(payload, ["progress", "stage"]) or nested_get(payload, ["stage"]) or "").lower()
    return status in {"completed", "complete", "succeeded", "success", "failed", "error"} or stage in {"completed", "complete", "report_ready"}


def classify_topic_search(base: Path) -> tuple[str, str]:
    has_run = nonempty(base / "literature/LITERATURE_DISCOVERY_RUN.json")
    has_packet = nonempty(base / "literature/LITERATURE_DISCOVERY_PACKET.json")
    if not has_run and not has_packet:
        return "auto_repairable", "submit_literature_discovery"
    if has_run and not has_packet and not discovery_report_ready(base):
        return "async_wait", "poll_literature_discovery"
    if has_run and not has_packet:
        return "auto_repairable", "capture_literature_discovery_report"
    return "auto_repairable", "screen_literature_discovery"


def blocked_evidence_gate_is_local(base: Path) -> bool:
    """Distinguish closed evidence failure from a still-running import/discovery wait."""
    gate_paths = [
        base / "orchestrator/INNOVATION_PACKET.json",
        base / "planner/EXPERIMENT_REVIEW_PACKET.json",
    ]
    gates: list[dict[str, Any]] = []
    for path in gate_paths:
        packet = read_json(path, {})
        gate = packet.get("evidence_import_gate") if isinstance(packet, dict) else None
        if isinstance(gate, dict):
            gates.append(gate)
    if not gates:
        return False
    blocked_statuses = {"blocked", "failed", "not_closed", "blocked_for_launch", "failed_closed"}
    for gate in gates:
        status = str(gate.get("status") or "").strip().lower()
        if status not in blocked_statuses:
            return False
        if gate.get("launch_blocked") is not True:
            return False
        if gate.get("import_submitted") is True:
            return False
    return True


def active_backend_remap_request(base: Path) -> dict[str, Any] | None:
    """Return the latest code-stage backend remap request that needs plan authority."""

    candidates = sorted((base / "coder").glob("BACKEND_REMAP_REQUEST_*.json"))
    for path in reversed(candidates):
        request = read_json(path, {})
        if not isinstance(request, dict):
            continue
        status = str(request.get("status") or "").strip().lower()
        next_action = str(request.get("next_action") or "").strip().lower()
        request_type = str(request.get("request_type") or "").strip().lower()
        if (
            request_type == "experiment_plan_backend_remap"
            and "experiment_plan" in next_action
            and status in {"requires_experiment_plan_authority", "pending", "open"}
        ):
            request["_path"] = str(path.relative_to(base))
            return request

    blocker = read_json(base / "coder/CODE_STAGE_BACKEND_BLOCKER_20260604T111500Z.json", {})
    if isinstance(blocker, dict):
        status = str(blocker.get("status") or "").strip().lower()
        next_action = str(blocker.get("next_action") or "").strip().lower()
        remap_request = str(blocker.get("backend_remap_request") or "").strip()
        if "remap" in status and "experiment_plan" in next_action and remap_request:
            request = read_json(base / remap_request, {})
            if isinstance(request, dict):
                request["_path"] = remap_request
                return request
    return None


def experiment_ledger_entries(base: Path) -> list[dict[str, Any]]:
    ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json", {})
    if not isinstance(ledger, dict):
        return []
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for key in ["entries", "runs", "attempts"]:
        rows_value = ledger.get(key)
        if not isinstance(rows_value, list):
            continue
        for row in rows_value:
            if not isinstance(row, dict):
                continue
            identity = (
                str(row.get("run_id") or row.get("id") or ""),
                str(row.get("status") or ""),
                str(row.get("promotion_decision") or row.get("promotion_status") or ""),
                str(row.get("finished_at") or ""),
                str(row.get("updated_at") or row.get("created_at") or ""),
            )
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(row)
    return merged


def experiment_entry_status(entry: dict[str, Any]) -> str:
    return normalized_state(
        entry.get("promotion_decision"),
        entry.get("promotion_status"),
        entry.get("verdict"),
        entry.get("status"),
    )


def experiment_entry_next_action(entry: dict[str, Any]) -> str:
    return normalized_state(entry.get("next_action"), entry.get("recommended_next_action"), entry.get("route"))


def experiment_next_action_kind(action: str) -> str:
    """Classify free-form experiment next_action strings into guard routes."""

    text = normalized_state(action)
    if not text:
        return ""
    head = text.split(":", 1)[0]
    if head in EXPERIMENT_REPAIR_ACTIONS:
        return "repair"
    if head in EXPERIMENT_REBUILD_ACTIONS:
        return "rebuild"
    rebuild_markers = (
        "switch_track",
        "track_switch",
        "structural_positive_redesign",
        "structural_redesign",
        "positive_redesign",
        "rebuild_idea",
        "change_idea",
        "change_innovation",
        "leap_idea",
        "negative_result_route",
    )
    if any(marker in head for marker in rebuild_markers):
        return "rebuild"
    repair_markers = ("repair", "relaunch", "rerun_after_fix", "fix_and_rerun", "debug_fix")
    if any(marker in head for marker in repair_markers):
        return "repair"
    return ""


def experiment_entry_failure_like(entry: dict[str, Any]) -> bool:
    decision = normalized_state(entry.get("promotion_decision"), entry.get("promotion_status"), entry.get("verdict"))
    status = normalized_state(entry.get("status"))
    spec = normalized_state(entry.get("spec_violation_status"))
    return (
        decision in EXPERIMENT_FAILURE_DECISIONS
        or decision.startswith("not_promoted")
        or status in {"failed", "failure", "budget_stopped", "regressed", "regression", "not_promoted"}
        or status.startswith("not_promoted")
        or spec in {"flagged", "violation", "failed"}
        or experiment_next_action_kind(experiment_entry_next_action(entry)) in {"repair", "rebuild"}
    )


def experiment_entry_promoted(entry: dict[str, Any]) -> bool:
    return experiment_entry_status(entry) in {"promoted", "best", "track_best", "ready", "accepted", "success"}


def experiment_entry_matches_active_selection(entry: dict[str, Any], active: dict[str, set[str]]) -> bool:
    active_ideas = active.get("idea_ids") or set()
    active_tracks = active.get("track_ids") or set()
    idea_id, track_id = experiment_entry_identity(entry)
    if active_ideas and idea_id and idea_id not in active_ideas:
        return False
    if active_tracks and track_id and track_id not in active_tracks:
        return False
    return True


def latest_failed_experiment_entry(base: Path, active_selection: dict[str, set[str]] | None = None) -> dict[str, Any] | None:
    entries = experiment_ledger_entries(base)
    for entry in reversed(entries):
        if active_selection is not None and not experiment_entry_matches_active_selection(entry, active_selection):
            continue
        if experiment_entry_failure_like(entry):
            return entry
    return None


def experiment_entry_identity(entry: dict[str, Any]) -> tuple[str, str]:
    idea_id = str(entry.get("selected_idea_id") or entry.get("idea_id") or "").strip()
    track_id = str(entry.get("track_id") or entry.get("track") or "").strip()
    return idea_id, track_id


def experiment_text_fields(payload: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in [
        "state",
        "status",
        "run_status",
        "decision",
        "next_action",
        "wait_condition",
        "resource_state",
        "resource_verdict",
        "monitor_status",
    ]:
        value = payload.get(key)
        if value is not None:
            fields.append(str(value))
    poll_decision = payload.get("poll_interval_decision")
    if isinstance(poll_decision, dict):
        fields.extend(experiment_text_fields(poll_decision))
    policy = payload.get("check_interval_policy")
    if isinstance(policy, dict):
        fields.extend(experiment_text_fields(policy))
    active_run = payload.get("active_run")
    if isinstance(active_run, dict):
        fields.extend(experiment_text_fields(active_run))
    return fields


def experiment_idle_signal(base: Path) -> dict[str, Any] | None:
    """Return an explicit no-live-experiment signal from the latest monitor state.

    This deliberately requires an overall monitor/status field to say no active
    work exists. A single server/GPU being idle is not enough, because one
    diagnostic endpoint can be idle while the evidence-producing run is active.
    """

    payload_sources: list[tuple[str, dict[str, Any]]] = []
    latest = latest_experiment_poll_decision(base)
    if latest is not None:
        payload, source = latest
        if isinstance(payload, dict):
            payload_sources.append((source, payload))
    plan = read_json(base / "experiment/EXPERIMENT_MONITOR_PLAN.json", {})
    if isinstance(plan, dict) and plan:
        payload_sources.append(("experiment/EXPERIMENT_MONITOR_PLAN.json", plan))
    registry = read_json(base / "automation_registry.json", {})
    if isinstance(registry, dict) and registry:
        payload_sources.append(("automation_registry.json", registry))

    for source, payload in payload_sources:
        fields = experiment_text_fields(payload)
        normalized_fields = [normalized_state(field) for field in fields]
        text_fields = [str(field or "").lower().replace("_", " ") for field in fields]
        if any(normalized in EXPERIMENT_ACTIVE_STATUSES for normalized in normalized_fields):
            return None
        if any(
            marker.replace("_", " ") in text
            for text in text_fields
            for marker in EXPERIMENT_BUSY_MARKERS
        ):
            return None
        for field in fields:
            normalized = normalized_state(field)
            if normalized in EXPERIMENT_IDLE_STATUSES:
                return {
                    "source": source,
                    "field": field,
                    "reason": f"{source} reports experiment monitor state {field!r}",
                }
            text = str(field or "").lower().replace("_", " ")
            if any(marker in text for marker in EXPERIMENT_IDLE_MARKERS):
                return {
                    "source": source,
                    "field": field,
                    "reason": f"{source} reports no active experiment work: {field}",
                }
        active_run_count = payload.get("active_run_count")
        if parse_int(active_run_count) == 0 and payload.get("all_runs_terminal") is True:
            return {
                "source": source,
                "field": "active_run_count=0/all_runs_terminal=true",
                "reason": f"{source} reports all experiment runs terminal and no active run count",
            }
    return None


def active_experiment_run_exists(base: Path) -> bool:
    def is_terminal_status(value: Any) -> bool:
        status = normalized_state(value)
        if not status:
            return False
        if status in EXPERIMENT_TERMINAL_STATUSES:
            return True
        terminal_prefixes = (
            "complete",
            "completed_",
            "failed_",
            "failure_",
            "cancelled_",
            "canceled_",
            "superseded_",
            "terminal_",
            "not_promoted",
        )
        return status.startswith(terminal_prefixes)

    def is_active_status(value: Any) -> bool:
        status = normalized_state(value)
        if is_terminal_status(status):
            return False
        if status in EXPERIMENT_ACTIVE_STATUSES:
            return True
        active_prefixes = (
            "active_",
            "queued_",
            "pending_",
            "submitted_",
            "launching_",
            "starting_",
            "started_",
            "running_",
            "training_",
            "parallel_training",
            "non_bjtu_parallel_training",
            "bjtu_parallel_training",
            "waiting_for_",
            "resource_wait",
            "external_live_wait",
        )
        return status.startswith(active_prefixes)

    if experiment_idle_signal(base):
        return False

    plan = read_json(base / "experiment/EXPERIMENT_MONITOR_PLAN.json", {})
    if isinstance(plan, dict):
        plan_state = normalized_state(plan.get("state"), plan.get("status"))
        poll_decision = latest_experiment_poll_decision(base)
        decision = poll_decision[0] if poll_decision else {}
        decision_status = normalized_state(decision.get("status")) if isinstance(decision, dict) else ""
        if is_terminal_status(plan_state) or is_terminal_status(decision_status):
            return False
        if is_active_status(plan_state):
            return True
        active_run = plan.get("active_run")
        if isinstance(active_run, dict) and is_active_status(active_run.get("status") or active_run.get("run_status")):
            return True
        for task in plan.get("active_background_tasks") or []:
            if isinstance(task, dict) and is_active_status(task.get("status") or task.get("run_status")):
                return True

    for remote_path in sorted(base.glob("coder/experiments/**/REMOTE_RUN.json")):
        remote = read_json(remote_path, {})
        if isinstance(remote, dict) and is_active_status(remote.get("status") or remote.get("run_status")):
            return True
    return False


def parallel_experiment_launch_available(base: Path) -> dict[str, Any] | None:
    """Return the shared scheduler proposal or a signal to refresh resources."""
    queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {})
    if not isinstance(queue, dict):
        return None
    proposal = select_launch_batch(queue)
    if not proposal.get("ok"):
        return None
    if not proposal.get("selected_count") and not proposal.get("requires_resource_refresh"):
        return None
    snapshot = proposal.get("resource_snapshot") if isinstance(proposal.get("resource_snapshot"), dict) else {}
    policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    admission_scope = str(policy.get("admission_scope") or "project").strip().lower()
    return {
        **proposal,
        "admission_scope": admission_scope,
        "global_admission_required": admission_scope == "global",
        "idle_slots": snapshot.get("idle_gpu_slots"),
        "skipped_reasons": [
            f"{item.get('row_id')}: {item.get('reason')}"
            for item in proposal.get("rejected", [])[:5]
            if isinstance(item, dict)
        ],
    }


def experiment_frontier_signal(base: Path) -> dict[str, Any] | None:
    queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {})
    if not isinstance(queue, dict) or not queue:
        return None
    return frontier_status(queue, project=base.parent)


def write_experiment_negative_blocker(base: Path, payload: dict[str, Any]) -> None:
    write_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", payload)


def experiment_launch_candidate(base: Path) -> dict[str, Any] | None:
    active_selection = current_active_selection(base)
    candidates = sorted(base.glob("coder/experiments/**/*CANDIDATE_RUN*.json"))
    for path in reversed(candidates):
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        if not experiment_entry_matches_active_selection(payload, active_selection):
            continue
        protocol_status = normalized_state(payload.get("protocol_status"))
        if protocol_status not in {"baseline_aligned", "pre_registered_feature_protocol"}:
            continue
        if payload.get("diagnostic_only") is True:
            continue
        status = normalized_state(payload.get("status"), payload.get("launch_status"))
        if status in {"completed", "complete", "success", "succeeded", "failed", "cancelled", "canceled"}:
            continue
        result = dict(payload)
        result["_path"] = str(path.relative_to(base))
        return result
    return None


def experiment_failure_route(base: Path) -> dict[str, Any] | None:
    active_selection = current_active_selection(base)
    latest = latest_failed_experiment_entry(base, active_selection)
    if not latest:
        return None
    idea_id, track_id = experiment_entry_identity(latest)
    next_action = experiment_entry_next_action(latest)
    return {
        "route_kind": "adjudicate",
        "required_next_action": "adjudicate_scientific_outcome",
        "status": "scientific_adjudication_required",
        "reason": (
            "legacy or untyped terminal experiment evidence cannot determine whether the cause is operational, "
            "protocol-invalid, scientifically negative, or inconclusive"
        ),
        "selected_idea_id": idea_id,
        "track_id": track_id,
        "failure_class": str(latest.get("failure_class") or "untyped_terminal_outcome").strip(),
        "ledger_next_action": next_action,
        "latest_failure_entry": latest,
    }


def sync_experiment_route_artifacts(base: Path, route: dict[str, Any]) -> None:
    blocker = {
        "schema_version": 2,
        "status": route["status"],
        "created_at": iso(now()),
        "selected_idea_id": route.get("selected_idea_id"),
        "track_id": route.get("track_id"),
        "failure_class": route.get("failure_class"),
        "repair_attempts": route.get("repair_attempts"),
        "max_same_idea_repairs": route.get("max_same_idea_repairs"),
        "required_next_action": route.get("required_next_action"),
        "ledger_next_action": route.get("ledger_next_action"),
        "reason": route.get("reason"),
        "latest_failure_entry": route.get("latest_failure_entry"),
    }
    write_experiment_negative_blocker(base, blocker)


def latest_typed_experiment_outcome(base: Path) -> dict[str, Any] | None:
    ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json", {})
    entries = ledger.get("entries") if isinstance(ledger, dict) else None
    if not isinstance(entries, list):
        return None
    active_selection = current_active_selection(base)
    for row in reversed(entries):
        if not isinstance(row, dict) or not row.get("outcome_class"):
            continue
        if not experiment_entry_matches_active_selection(row, active_selection):
            continue
        if str(row.get("scientific_outcome_status") or "") in {
            "accepted",
            "pending_decision",
            "awaiting_adjudication",
        }:
            return row
    return None


def all_recorded_tracks_terminal(base: Path) -> bool:
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {})
    states = ledger.get("track_states") if isinstance(ledger, dict) else None
    if not isinstance(states, list) or not states:
        return False
    return all(
        isinstance(row, dict)
        and str(row.get("lifecycle_status") or "").strip().lower() in {"retired", "concluded", "refuted", "terminal"}
        for row in states
    )


def automatic_portfolio_replenishment_allowed(base: Path, frontier: dict[str, Any]) -> bool:
    """Allow capacity-triggered research only for an unresolved bounded paper route."""

    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {})
    if str(program.get("enforcement_mode") or "legacy") == "enforced":
        return replenishment_proposal(base, frontier).get("complete") is True

    if str(frontier.get("portfolio_blocker_code") or "") != "shortlist_missing_or_exhausted":
        return False
    if int(frontier.get("portfolio_admission_deficit") or 0) <= 0:
        return False
    if int(frontier.get("active_nonterminal_track_count") or 0) <= 0:
        return False
    if int(frontier.get("fresh_fitting_idle_slots") or 0) <= 0:
        return False
    if all_recorded_tracks_terminal(base):
        return False

    state = read_json(base / "goal_state.json", {})
    policy = read_json(base / "autopilot_policy.json", {})
    autonomy = str(state.get("autonomy_level") or policy.get("autonomy_level") or "").strip()
    goal_type = str(state.get("goal_type") or policy.get("goal_type") or "paper_producing_top_tier").strip()
    if autonomy != "full_auto_bounded" or not goal_type.startswith("paper_producing_"):
        return False
    return policy.get("allow_autonomous_candidate_replenishment") is not False


def classify(stage: str, reason: str, base: Path) -> tuple[str, str]:
    if stage == "topic_search":
        return classify_topic_search(base)
    text = reason.lower()
    if stage == "experiment":
        typed = latest_typed_experiment_outcome(base)
        if typed:
            outcome_class = str(typed.get("outcome_class") or "")
            outcome_status = str(typed.get("scientific_outcome_status") or "")
            if outcome_status in {"pending_decision", "awaiting_adjudication"}:
                return "auto_repairable", "apply_research_decision"
            if outcome_class == "infrastructure_failure":
                return "auto_repairable", "repair_or_reconcile_infrastructure"
            if outcome_class == "implementation_failure":
                return "auto_repairable", "refine_implementation"
            if outcome_class == "protocol_invalid":
                return "auto_repairable", "repair_experiment_protocol"
            if all_recorded_tracks_terminal(base):
                return "auto_repairable", "write_terminal_program_decision"
            if outcome_class == "valid_positive_candidate":
                return "auto_repairable", "queue_ablation_or_confirmation"
            return "auto_repairable", "reconcile_scientific_transition"
        frontier = experiment_frontier_signal(base)
        if frontier and frontier.get("portfolio_actionable"):
            return "auto_repairable", "batch_fill_experiment_portfolio"
        if frontier and int(frontier.get("portfolio_admission_deficit") or 0) > 0:
            portfolio_blocker = str(frontier.get("portfolio_blocker_code") or "")
            if automatic_portfolio_replenishment_allowed(base, frontier):
                return "auto_repairable", "replenish_experiment_portfolio"
            if portfolio_blocker in {"shortlist_candidates_blocked", "no_set_feasible_shortlist_candidate"}:
                return "hard_stop", "portfolio_admission_requires_scientific_repair"
        if frontier and frontier.get("frontier_underfilled"):
            blocker = str(frontier.get("frontier_blocker_code") or "")
            if frontier.get("frontier_actionable") and blocker in {
                "missing_track_packet",
                "admissible_frontier_deficit",
            }:
                return "auto_repairable", "materialize_experiment_frontier"
            if blocker == "scientific_dependency_wait":
                if active_experiment_run_exists(base):
                    return "async_wait", "poll_experiment_run"
                return "hard_stop", "scientific_dependency_without_live_run"
            if blocker == "no_admissible_frontier_candidate" and not active_experiment_run_exists(base):
                return "hard_stop", "no_admissible_experiment_frontier"
        parallel = parallel_experiment_launch_available(base)
        if parallel and parallel.get("global_admission_required"):
            return "hard_stop", "global_admission_required"
    if stage == "code" and active_backend_remap_request(base):
        return "hard_stop", "rollback_to_experiment_plan_backend_remap"
    if "selected_negative_evidence:" in text:
        if stage in {"experiment_plan", "code"}:
            return "hard_stop", "rollback_to_idea_gate_after_selected_negative_evidence"
        return "auto_repairable", "repair_idea_gate_or_return_to_ideation"
    if "selected_projection_alignment:" in text:
        if stage == "code":
            return "hard_stop", "rollback_to_experiment_plan_projection_repair"
        return "auto_repairable", "repair_selected_projection_alignment"
    if stage == "graph_build":
        if "unsubmitted graph_import papers" in text or "submitted graph_import" in text:
            return "auto_repairable", "submit_graph_import_tasks"
        if "queued/running" in text or "authoritative graph sync not complete" in text:
            return "async_wait", "poll_graph_import_sync"
        if "incomplete graph_import papers" in text or "authoritative graph sync incomplete for graph_import papers" in text:
            return "async_wait", "poll_graph_import_sync"
        if "taskids/relevanttaskids" in text or "task rows or explicit graph_visible" in text:
            return "auto_repairable", "submit_graph_import_tasks"
        if "graph_build_decision" in text:
            return "auto_repairable", "write_graph_build_decision"
    if stage == "literature_review":
        if any(name in text for name in ["sota_matrix", "gap_synthesis", "citation_queue"]):
            return "auto_repairable", "write_literature_review"
    if stage in {"ideation", "idea_gate", "experiment_plan"}:
        if "evidence_import_gate" in text and blocked_evidence_gate_is_local(base):
            return "auto_repairable", "degrade_or_rollback_evidence_gate"
        ideation_artifact_gap = any(
            name in text
            for name in [
                "abstract_screening_audit",
                "paper_selection_scorecard_lint",
                "pre_idea_breadth_lint",
                "idea_pool_lint",
                "idea_scorecard_lint",
                "split_reading_evidence_pack_lint",
                "literature_discovery_triage.json discovery_attempted",
            ]
        )
        if stage == "ideation" and ideation_artifact_gap:
            return "auto_repairable", "run_papernexus_ideation"
        if stage == "idea_gate" and ideation_artifact_gap:
            return "auto_repairable", "repair_idea_gate_or_return_to_ideation"
        local_queue_artifact = any(name in text for name in ["citation_queue", "idea_track_seeds", "experiment_idea_pool"])
        if local_queue_artifact and not any(name in text for name in ["import_workflow", "remote", "async", "authoritative", "sync"]):
            return "auto_repairable", "schedule_repair"
    if stage == "experiment" and ("promoted best_run" in text or "ready_for_analysis" in text):
        if active_experiment_run_exists(base):
            parallel = parallel_experiment_launch_available(base)
            if parallel and parallel.get("global_admission_required"):
                return "hard_stop", "global_admission_required"
            if parallel:
                return "auto_repairable", "launch_parallel_experiment"
            return "async_wait", "poll_experiment_run"
        negative_blocker = read_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", {})
        status = str(negative_blocker.get("status") or "").strip().lower() if isinstance(negative_blocker, dict) else ""
        if status in {
            "blocked_without_promoted_evidence",
            "no_promoted_evidence",
            "negative_result_route",
            "change_idea_or_innovation_required",
            "two_repairs_without_improvement",
        } and not route_stale_for_active_selection(negative_blocker, current_active_selection(base)):
            return "hard_stop", "rollback_or_negative_result_route"
        failure_route = experiment_failure_route(base)
        if failure_route:
            sync_experiment_route_artifacts(base, failure_route)
            return "auto_repairable", "adjudicate_scientific_outcome"
        launch_candidate = experiment_launch_candidate(base)
        negative_blocker = read_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", {})
        status = str(negative_blocker.get("status") or "").strip().lower() if isinstance(negative_blocker, dict) else ""
        if status in {
            "blocked_without_promoted_evidence",
            "no_promoted_evidence",
            "negative_result_route",
            "change_idea_or_innovation_required",
            "two_repairs_without_improvement",
        }:
            if launch_candidate and not experiment_entry_matches_active_selection(
                negative_blocker,
                current_active_selection(base),
            ):
                return "auto_repairable", "launch_or_reconcile_experiment"
            return "hard_stop", "rollback_or_negative_result_route"
        if launch_candidate:
            return "auto_repairable", "launch_or_reconcile_experiment"
    if "literature_discovery" in text and discovery_run_id(base) and not discovery_report_ready(base):
        return "async_wait", "poll_literature_discovery"
    if any(key in text for key in ["import_workflow", "authoritative", "graph sync", "fast_commit", "fast-commit"]):
        if any(wait_key in text for wait_key in ["pending", "queued", "running", "incomplete", "not complete", "sync"]):
            return "async_wait", "poll_graph_import_sync"
        return "auto_repairable", "schedule_repair"
    if any(key in text for key in ["queue", "queued", "running", "remote", "async", "wait"]):
        return "auto_repairable", "schedule_repair"
    if any(key in text for key in ["controller_unavailable", "single_seed", "cost_evidence", "provider", "sparse", "stale"]):
        return "degradable", "advance_with_downgrade_or_fallback"
    if any(key in text for key in ["budget", "license", "unsafe", "no_viable", "papernexus_unavailable_without_cached"]):
        return "hard_stop", "rollback_or_negative_result_route"
    return "auto_repairable", "schedule_repair"


def next_due_job(
    queue: list[dict[str, Any]],
    *,
    include_running: bool = False,
    kind: str = "repair",
    retry_override: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    current = now()
    eligible_statuses = {"pending", "retry"}
    if include_running:
        eligible_statuses.add("running")
    for row in queue:
        if row.get("status") not in eligible_statuses:
            continue
        if retry_override_matches(row, retry_override, kind):
            overridden = dict(row)
            overridden["_retry_override"] = {
                "source": retry_override.get("source") or retry_override.get("reason") or "active_retry_override",
                "reason": retry_override.get("reason") or retry_override.get("override_reason"),
            }
            return overridden
        retry_at = str(row.get("next_retry_at") or row.get("next_poll_at") or "")
        if not retry_at:
            return row
        try:
            if datetime.fromisoformat(retry_at) <= current:
                return row
        except ValueError:
            return row
    return None


def repair_metadata(base: Path, kind: str, stage: str, action: str, reason: str) -> dict[str, Any]:
    outcome = latest_typed_experiment_outcome(base) if stage == "experiment" else None
    failure_class = str((outcome or {}).get("outcome_class") or "untyped_contract_blocker")
    scientific_actions = {
        "apply_research_decision",
        "reconcile_scientific_transition",
        "write_terminal_program_decision",
        "queue_ablation_or_confirmation",
        "recover_replenishment_route",
    }
    repair_kind = "none" if kind == "async" else "scientific_revision" if action in scientific_actions else "operational"
    normalized_reason = re.sub(r"\s+", " ", reason.strip().lower())
    signature_payload = f"{failure_class}|{stage}|{action}|{normalized_reason}"
    return {
        "failure_class": failure_class,
        "failure_signature": "failure-" + hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()[:16],
        "repair_kind": repair_kind,
        "operational_attempt": int((outcome or {}).get("operational_attempt") or 0),
        "scientific_revision": int((outcome or {}).get("scientific_revision") or 0),
        "max_scientific_revisions": 2,
    }


def mark_job_running(base: Path, queue_name: str, job: dict[str, Any]) -> None:
    path = base / queue_name
    data = rows(path)
    for row in data:
        if row.get("job_id") == job.get("job_id"):
            row["status"] = "running"
            row["attempts"] = int(row.get("attempts", 0)) + 1
            if row.get("repair_kind") == "operational":
                row["operational_attempt"] = int(row.get("operational_attempt") or 0) + 1
            row["updated_at"] = iso(now())
    write_rows(path, data)


def job_contract(project: str, job: dict[str, Any]) -> dict[str, Any]:
    stage = str(job.get("stage", "init"))
    if stage == "idea_gate" and str(job.get("action") or "") == "recover_replenishment_route":
        recovery = program_recovery_status(ar(project))
        return {
            "complete": False,
            "stage": stage,
            "contract_source": "program_recovery_status",
            "missing": [str(recovery.get("reason") or "replacement program recovery incomplete")],
            "program_recovery": recovery,
        }
    return lint(project, stage)


def queue_job(base: Path, kind: str, stage: str, action: str, reason: str, policy: dict[str, Any]) -> dict[str, Any]:
    queue_name = "async_jobs.jsonl" if kind == "async" else "repair_queue.jsonl"
    path = base / queue_name
    data = rows(path)
    delay_key = "next_poll_at" if kind == "async" else "next_retry_at"
    current = now()
    metadata = repair_metadata(base, kind, stage, action, reason)
    if kind == "async":
        delay_minutes, delay_reason = async_poll_delay_minutes(base, policy, stage, action, reason)
    else:
        delay_minutes = poll_delay_minutes(policy, kind)
        delay_reason = (
            "ready immediately for goal/full_auto_bounded local repair; "
            f"retry interval from policy applies after failed attempts: {delay_minutes} minutes"
        )
    for row in data:
        if row.get("failure_signature") != metadata["failure_signature"]:
            continue
        if int(row.get("attempts") or 0) >= int(row.get("max_attempts") or (3 if kind == "async" else 2)):
            existing = dict(row)
            existing["_reused"] = True
            existing["_budget_exhausted"] = True
            existing["_reuse_reason"] = "failure-signature retry budget exhausted"
            return existing
    for row in data:
        if (
            row.get("status") in {"pending", "retry", "running"}
            and row.get("stage") == stage
            and row.get("action") == action
            and (row.get("failure_signature") == metadata["failure_signature"] or row.get("reason") == reason)
        ):
            if kind == "async":
                existing_due_at = parse_iso_datetime(row.get(delay_key))
                fixed_due_at, fixed_decision_at, fixed_source = latest_experiment_fixed_due_at(base, stage, action)
                proposed_due_at = fixed_due_at or (current + timedelta(minutes=delay_minutes))
                row_updated_at = parse_iso_datetime(row.get("updated_at"))
                row_interval_changed = (
                    bounded_minutes(row.get("poll_interval_minutes"), delay_minutes) != delay_minutes
                    or str(row.get("poll_interval_reason") or "").strip() != delay_reason
                )
                row["poll_interval_minutes"] = delay_minutes
                row["poll_interval_reason"] = delay_reason
                row["updated_at"] = iso(current)
                if existing_due_at is None or existing_due_at <= current:
                    row[delay_key] = iso(proposed_due_at)
                    row["poll_due_update_reason"] = "existing async poll was due or invalid; rescheduled from latest live interval"
                elif proposed_due_at < existing_due_at:
                    row[delay_key] = iso(proposed_due_at)
                    row["poll_due_update_reason"] = "latest live interval advanced the async poll earlier"
                elif (
                    fixed_due_at is not None
                    and fixed_due_at > existing_due_at
                    and (
                        fixed_decision_at is None
                        or row_updated_at is None
                        or fixed_decision_at > row_updated_at
                        or row_interval_changed
                    )
                ):
                    row[delay_key] = iso(fixed_due_at)
                    row["poll_due_update_reason"] = (
                        f"latest authoritative experiment monitor decision from {fixed_source or 'monitor plan'} "
                        "moved the async poll later"
                    )
                else:
                    row[delay_key] = iso(existing_due_at)
                    row["poll_due_update_reason"] = "preserved existing future async poll; queued wait must not postpone due time"
                write_rows(path, data)
            elif row.get("status") == "pending" and int(row.get("attempts", 0) or 0) == 0:
                row[delay_key] = iso(current)
                row["retry_interval_minutes"] = delay_minutes
                row["retry_interval_reason"] = delay_reason
                row["updated_at"] = iso(current)
                write_rows(path, data)
            existing = dict(row)
            existing["_reused"] = True
            return existing
        if (
            row.get("status") == "failed"
            and row.get("stage") == stage
            and row.get("action") == action
            and (row.get("failure_signature") == metadata["failure_signature"] or row.get("reason") == reason)
        ):
            retry_at = parse_iso_datetime(row.get(delay_key))
            if retry_at is not None and retry_at > current:
                existing = dict(row)
                existing["_reused"] = True
                existing["_reuse_reason"] = "matching failed job is in backoff; suppress duplicate immediate queue"
                return existing
    next_due_at = current + timedelta(minutes=delay_minutes) if kind == "async" else current
    row = {
        "schema_version": 2,
        "job_id": f"job_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "stage": stage,
        "action": action,
        "reason": reason,
        "status": "pending",
        "attempts": 0,
        "max_attempts": (
            3
            if kind == "async"
            else min(
                2,
                int(
                    policy.get(
                        "max_operational_attempts_per_signature",
                        policy.get("max_repair_attempts_per_blocker", 2),
                    )
                ),
            )
        ),
        "created_at": iso(current),
        delay_key: iso(next_due_at),
        "fallback_action": "degrade_or_rollback",
        **metadata,
    }
    if kind == "async":
        row["poll_interval_minutes"] = delay_minutes
        row["poll_interval_reason"] = delay_reason
    else:
        row["retry_interval_minutes"] = delay_minutes
        row["retry_interval_reason"] = delay_reason
    data.append(row)
    write_rows(path, data)
    created = dict(row)
    created["_reused"] = False
    return created


def literature_discovery_wait_signal(base: Path) -> dict[str, str]:
    if nonempty(base / "literature/LITERATURE_DISCOVERY_PACKET.json"):
        return {
            "state": "terminal",
            "reason": "literature discovery packet already exists; capture/screening is local work",
        }
    run_id = discovery_run_id(base)
    if not run_id:
        return {
            "state": "missing_source",
            "reason": "literature discovery wait has no recorded run id",
        }
    if discovery_report_ready(base):
        return {
            "state": "terminal",
            "reason": "literature discovery report is terminal/ready; capture the report locally",
        }
    return {
        "state": "active",
        "reason": f"PaperNexus literature discovery run {run_id} is still external",
    }


def import_count(payload: dict[str, Any], *names: str) -> int | None:
    for name in names:
        parsed = parse_int(payload.get(name))
        if parsed is not None:
            return parsed
    return None


def graph_import_wait_signal(base: Path) -> dict[str, str]:
    payload = unwrap_capture(read_json(base / "papernexus/IMPORT_WORKFLOW_STATUS.json", {}))
    if not isinstance(payload, dict) or not payload:
        return {
            "state": "missing_source",
            "reason": "PaperNexus import_workflow status artifact is missing",
        }

    target_tasks = (
        import_status_tasks(payload, "targetTasks")
        or import_status_tasks(payload, "target_tasks")
        or import_status_tasks(payload, "selectedTasks")
        or import_status_tasks(payload, "selected_tasks")
    )
    tasks = target_tasks or raw_import_tasks(payload)
    if tasks:
        if any(import_task_failed(row) for row in tasks):
            return {
                "state": "local_actionable",
                "reason": "selected PaperNexus graph import task failed or was cancelled; repair/degrade locally",
            }
        if all(import_task_complete(row) and graph_visible_complete(row) and semantic_complete(row) and sync_complete(row) for row in tasks):
            return {
                "state": "terminal",
                "reason": "all selected PaperNexus graph import tasks are complete, graph-visible, semantic-ready, and authoritative-synced",
            }
        if any(
            import_task_status(row) in RUNNING_STATES
            or import_task_stage(row) in RUNNING_STATES
            or import_task_status(row) in QUEUED_STATES
            or import_task_stage(row) in QUEUED_STATES
            for row in tasks
        ):
            return {
                "state": "active",
                "reason": "selected PaperNexus graph import task is queued or running",
            }
        if any(import_task_complete(row) and graph_visible_complete(row) and semantic_complete(row) and not sync_complete(row) for row in tasks):
            return {
                "state": "active",
                "reason": "selected PaperNexus graph import task is waiting for authoritative sync",
            }
        if any(import_task_id(row) for row in tasks):
            return {
                "state": "active",
                "reason": "selected PaperNexus graph import task ids exist but terminal status is not recorded yet",
            }

    planned = import_count(payload, "effective_planned_import_count", "effectivePlannedImportCount", "planned_import_count", "plannedImportCount")
    submitted = import_count(payload, "submitted_import_count", "submittedImportCount")
    completed = import_count(payload, "completed_import_count", "completedImportCount")
    synced = import_count(payload, "authoritative_sync_completed_count", "authoritativeSyncCompletedCount")
    if planned and submitted is not None and submitted < planned:
        return {
            "state": "local_actionable",
            "reason": "PaperNexus graph import has planned papers that are not submitted yet",
        }
    if planned and completed is not None and completed < planned:
        return {
            "state": "active",
            "reason": "PaperNexus graph import has submitted tasks that are not complete yet",
        }
    if planned and synced is not None and synced < planned:
        return {
            "state": "active",
            "reason": "PaperNexus graph import is complete but authoritative sync is not complete yet",
        }
    if planned and completed == planned and (synced is None or synced == planned):
        return {
            "state": "terminal",
            "reason": "PaperNexus graph import counts are terminal for the planned selected imports",
        }

    summary = import_queue_summary(payload)
    summary_state = normalized_state(
        summary.get("status"),
        summary.get("state"),
        summary.get("phase"),
        summary.get("activeStage"),
        summary.get("activePhase"),
    )
    payload_state = normalized_state(payload.get("status"), payload.get("state"), payload.get("verdict"))
    combined_state = summary_state or payload_state
    remaining = parse_int(summary.get("remaining"))
    running = parse_int(summary.get("running"))
    queued = parse_int(summary.get("queued") or summary.get("pending"))
    if combined_state in RUNNING_STATES or combined_state in QUEUED_STATES:
        return {
            "state": "active",
            "reason": f"PaperNexus import_workflow reports external state {combined_state}",
        }
    if any(value is not None and value > 0 for value in [remaining, running, queued]):
        return {
            "state": "active",
            "reason": "PaperNexus import_workflow queue summary still has remaining, running, or queued work",
        }
    if combined_state in COMPLETE_STATES or payload.get("complete") is True:
        return {
            "state": "terminal",
            "reason": "PaperNexus import_workflow status is terminal/complete",
        }
    if combined_state in FAILED_STATES:
        return {
            "state": "local_actionable",
            "reason": f"PaperNexus import_workflow status is {combined_state}; repair/degrade locally",
        }
    return {
        "state": "missing_source",
        "reason": "PaperNexus import_workflow status has no selected live wait signal",
    }


def async_wait_gate(
    base: Path,
    stage: str,
    action: str,
    reason: str,
    *,
    job: dict[str, Any] | None = None,
    current_stage: str | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del contract
    if action not in ASYNC_HEARTBEAT_ACTIONS:
        return {
            "allowed": False,
            "wait_kind": "none",
            "decision": "denied_not_external_wait",
            "reason": f"{action or 'missing action'} is not an allowed heartbeat action",
        }
    job_stage = str(job.get("stage") or stage) if isinstance(job, dict) else stage
    if current_stage and job_stage and job_stage != current_stage:
        return {
            "allowed": False,
            "wait_kind": "none",
            "decision": "superseded_no_longer_required",
            "reason": f"async wait belongs to stage {job_stage}, but current stage is {current_stage}",
        }
    if action == "poll_literature_discovery":
        signal = literature_discovery_wait_signal(base)
        if signal["state"] == "active":
            return {
                "allowed": True,
                "wait_kind": "papernexus_literature_discovery",
                "decision": "allowed_external_wait",
                "reason": signal["reason"],
            }
        decision = "superseded_terminal" if signal["state"] == "terminal" else "denied_local_actionable"
        return {
            "allowed": False,
            "wait_kind": "papernexus_literature_discovery",
            "decision": decision,
            "reason": signal["reason"],
        }
    if action == "poll_graph_import_sync":
        signal = graph_import_wait_signal(base)
        if signal["state"] == "active":
            return {
                "allowed": True,
                "wait_kind": "papernexus_graph_import_sync",
                "decision": "allowed_external_wait",
                "reason": signal["reason"],
            }
        decision = "superseded_terminal" if signal["state"] == "terminal" else "denied_local_actionable"
        return {
            "allowed": False,
            "wait_kind": "papernexus_graph_import_sync",
            "decision": decision,
            "reason": signal["reason"],
        }
    if action == "poll_experiment_run":
        if stage != "experiment":
            return {
                "allowed": False,
                "wait_kind": "experiment_runtime_or_resource",
                "decision": "superseded_no_longer_required",
                "reason": "experiment runtime heartbeat is only valid in the experiment stage",
            }
        idle = experiment_idle_signal(base)
        if idle:
            return {
                "allowed": False,
                "wait_kind": "experiment_runtime_or_resource",
                "decision": "superseded_terminal",
                "reason": f"latest experiment monitor reports no active live experiment: {idle.get('reason')}",
            }
        if active_experiment_run_exists(base):
            parallel = parallel_experiment_launch_available(base)
            if parallel:
                return {
                    "allowed": False,
                    "wait_kind": "experiment_runtime_or_resource",
                    "decision": "denied_local_parallel_launch_available",
                    "reason": (
                        "active experiment runtime exists, but independent ready experiment rows require a local resource-fit check before waiting: "
                        f"scheduler_reason={parallel.get('reason')}, selected_row_ids={parallel.get('selected_row_ids')}, "
                        f"idle_slots={parallel.get('idle_slots')}, requires_resource_refresh={parallel.get('requires_resource_refresh')}"
                    ),
                }
            return {
                "allowed": True,
                "wait_kind": "experiment_runtime_or_resource",
                "decision": "allowed_external_wait",
                "reason": "active experiment runtime or resource wait exists",
            }
        return {
            "allowed": False,
            "wait_kind": "experiment_runtime_or_resource",
            "decision": "denied_local_actionable",
            "reason": "WorkflowGuard found no active experiment run; local launch, repair, or stage advancement can proceed",
        }
    return {
        "allowed": False,
        "wait_kind": "none",
        "decision": "denied_not_external_wait",
        "reason": "unknown async wait action",
    }


def async_wait_allowed(
    stage: str,
    action: str,
    reason: str,
    base: Path | None = None,
    *,
    job: dict[str, Any] | None = None,
    current_stage: str | None = None,
    contract: dict[str, Any] | None = None,
) -> bool:
    if base is not None:
        return bool(
            async_wait_gate(
                base,
                stage,
                action,
                reason,
                job=job,
                current_stage=current_stage,
                contract=contract,
            ).get("allowed")
        )
    if action not in ASYNC_HEARTBEAT_ACTIONS:
        return False
    if action == "poll_literature_discovery":
        return True
    if action == "poll_graph_import_sync":
        return True
    if action == "poll_experiment_run":
        return stage == "experiment"
    return False


def supersede_async_job(base: Path, job: dict[str, Any], reason: str) -> None:
    path = base / "async_jobs.jsonl"
    data = rows(path)
    for row in data:
        if row.get("job_id") == job.get("job_id"):
            row["status"] = "superseded"
            row["updated_at"] = iso(now())
            row["superseded_reason"] = reason
    write_rows(path, data)
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": iso(now()),
            "stage": job.get("stage"),
            "action": "supersede_async_wait",
            "details": {
                "job_id": job.get("job_id"),
                "job_action": job.get("action"),
                "reason": reason,
            },
        },
    )


def supersede_matching_async_jobs(
    base: Path,
    stage: str,
    action: str,
    reason: str | None,
    superseded_reason: str,
) -> int:
    path = base / "async_jobs.jsonl"
    data = rows(path)
    count = 0
    current = now()
    for row in data:
        if (
            row.get("status") in {"pending", "retry", "running"}
            and row.get("stage") == stage
            and row.get("action") == action
            and (reason is None or row.get("reason") == reason)
        ):
            row["status"] = "superseded"
            row["updated_at"] = iso(current)
            row["superseded_reason"] = superseded_reason
            count += 1
    if count:
        write_rows(path, data)
        append_jsonl(
            base / "decision_log.jsonl",
            {
                "ts": iso(current),
                "stage": stage,
                "action": "supersede_matching_async_waits",
                "details": {
                    "job_action": action,
                    "matched_reason": reason,
                    "count": count,
                    "reason": superseded_reason,
                },
            },
        )
    return count


def obsolete_async_wait_reason(
    base: Path,
    job: dict[str, Any],
    *,
    current_stage: str | None = None,
    gate: dict[str, Any] | None = None,
) -> str | None:
    stage = str(job.get("stage") or "")
    action = str(job.get("action") or "")
    gate = gate or async_wait_gate(
        base,
        stage,
        action,
        str(job.get("reason") or ""),
        job=job,
        current_stage=current_stage,
    )
    if not gate.get("allowed"):
        return (
            "obsolete async wait superseded because it is not the current external blocker: "
            f"{gate.get('reason')}"
        )
    if action != "poll_experiment_run":
        return None
    idle = experiment_idle_signal(base)
    if idle:
        return (
            "obsolete experiment async wait superseded because latest monitor reports no active live experiment: "
            f"{idle.get('reason')}"
        )
    if not active_experiment_run_exists(base):
        return (
            "obsolete experiment async wait superseded because WorkflowGuard found no active experiment run; "
            "local launch, repair, or stage advancement can proceed without another poll heartbeat"
        )
    return None


def supersede_repair_job(base: Path, job: dict[str, Any], reason: str) -> None:
    path = base / "repair_queue.jsonl"
    data = rows(path)
    for row in data:
        if row.get("job_id") == job.get("job_id"):
            row["status"] = "superseded"
            row["updated_at"] = iso(now())
            row["superseded_reason"] = reason
    write_rows(path, data)
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": iso(now()),
            "stage": job.get("stage"),
            "action": "supersede_repair_job",
            "details": {
                "job_id": job.get("job_id"),
                "job_action": job.get("action"),
                "reason": reason,
            },
        },
    )


def obsolete_experiment_repair_reason(base: Path, job: dict[str, Any]) -> str | None:
    if str(job.get("stage") or "") != "experiment":
        return None
    action = str(job.get("action") or "")
    negative_blocker = read_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", {})
    blocker_status = (
        str(negative_blocker.get("status") or "").strip().lower()
        if isinstance(negative_blocker, dict)
        else ""
    )
    if action in {"launch_or_reconcile_experiment", "launch_parallel_experiment", "repair_failed_experiment", "schedule_repair"} and blocker_status in {
        "blocked_without_promoted_evidence",
        "no_promoted_evidence",
        "negative_result_route",
        "change_idea_or_innovation_required",
        "two_repairs_without_improvement",
    } and not route_stale_for_active_selection(negative_blocker, current_active_selection(base)):
        return (
            "obsolete experiment repair superseded because coder/EXPERIMENT_NEGATIVE_BLOCKER.json "
            f"already requests negative-result routing: status={blocker_status}"
        )
    if action == "launch_parallel_experiment":
        if parallel_experiment_launch_available(base):
            return None
        return (
            "obsolete parallel experiment launch repair superseded because no independent ready queue row "
            "currently fits the non-blocked resource/dependency constraints"
        )
    if action != "launch_or_reconcile_experiment":
        return None
    if active_experiment_run_exists(base):
        return None
    failure_route = experiment_failure_route(base)
    if not failure_route:
        return None
    sync_experiment_route_artifacts(base, failure_route)
    route_kind = str(failure_route.get("route_kind") or "")
    required = str(failure_route.get("required_next_action") or "")
    return (
        "obsolete generic experiment launch repair superseded by latest terminal experiment triage: "
        f"route_kind={route_kind}, required_next_action={required}"
    )


def contract_reason(contract: dict[str, Any], stage: str) -> str:
    return "; ".join(str(item) for item in contract.get("missing", [])) or f"{stage} contract incomplete"


def reason_snippet(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def obsolete_repair_reason(project: str, base: Path, state: dict[str, Any], job: dict[str, Any]) -> str | None:
    """Return why a queued repair should not be dispatched anymore.

    Repairs are concrete packets for one observed contract failure. In
    full_auto_bounded runs, a prior agent can repair the artifact state and
    leave an older pending/running repair behind. Dispatching that stale packet
    before re-reading the current contract makes the workflow appear stuck on a
    previous idea/track. Prefer superseding the stale packet and letting the
    normal contract triage below queue a fresh repair if one is still needed.
    """

    current_stage = str(state.get("stage") or "init")
    job_stage = str(job.get("stage") or current_stage)
    if job_stage != current_stage:
        return (
            f"obsolete repair for stage {job_stage} superseded because current workflow stage is "
            f"{current_stage}"
        )

    if current_stage == "idea_gate":
        recovery = program_recovery_status(base)
        recovery_action = str(recovery.get("action") or "")
        if recovery.get("applicable") and recovery.get("class") == "auto_repairable":
            if str(job.get("action") or "") != recovery_action:
                return (
                    "obsolete idea-gate repair superseded by the current replacement-program recovery phase: "
                    f"phase={recovery.get('phase')}, action={recovery_action}"
                )
            return None

    contract = job_contract(project, job)
    if contract.get("complete"):
        return f"obsolete repair superseded because current {job_stage} contract is complete"

    current_reason = contract_reason(contract, job_stage)
    job_reason = str(job.get("reason") or "")
    if job_reason and current_reason and job_reason != current_reason:
        return (
            "obsolete repair superseded because the live contract blocker changed; "
            f"old={reason_snippet(job_reason)}; current={reason_snippet(current_reason)}"
        )

    return obsolete_experiment_repair_reason(base, job)


def minutes_until(value: str, fallback: int) -> int:
    try:
        due_at = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback
    seconds = int((due_at - now()).total_seconds())
    if seconds <= 0:
        # A due/overdue async wait can occur near a heartbeat boundary before
        # goal_tick dispatches a packet. Do not collapse progress-dependent
        # experiment monitors into 1-minute busy polling; preserve the live
        # stage/ETA interval already stored on the job.
        return bounded_minutes(fallback, fallback)
    return max(1, (seconds + 59) // 60)


def async_wakeup_recommendation(project: str, job: dict[str, Any], reason: str) -> dict[str, Any]:
    due_at = str(job.get("next_poll_at") or "")
    interval_minutes = bounded_minutes(job.get("poll_interval_minutes"), 5)
    interval_reason = str(job.get("poll_interval_reason") or "default async poll interval").strip()
    resume_minutes = minutes_until(due_at, interval_minutes)
    stage = str(job.get("stage") or "current")
    job_id = str(job.get("job_id") or "")
    prompt = (
        "Resume AutoResearch async polling for project "
        f"{project}. Run goal.py status, goal.py reconcile --stale-minutes 60, then goal.py tick. "
        "If tick dispatches this async poll job, execute the rendered packet through the named child skill, "
        "capture PaperNexus progress/report artifacts, update the job, and then run the bounded continuation loop while progress is locally actionable. "
        "If the external wait is terminal, superseded, or locally actionable and you delete the heartbeat, do not stop at cleanup; run status, reconcile, and tick again, then continue one bounded successor cycle if local work is exposed. "
        "The loop budget is max_tick_actions=5 or about 10 minutes of active work; stop at hard_stop, queued_async_wait, repair_already_queued without a due packet, external live wait with no eligible parallel experiment launch, terminal completion, user/budget/credential gate, or budget exhaustion. "
        "If PaperNexus discovery/import is still running, do not sleep in-thread; record the status and create or update the next heartbeat from the new tick output. "
        "For PaperNexus graph import waits, recompute the interval from live graph status: queued depth, active fast-commit percent, authoritative-sync state, terminal completion, and stale wait condition. "
        f"Target job_id={job_id}, stage={stage}, due_at={due_at}, poll_interval_minutes={interval_minutes}, interval_reason={interval_reason}, blocker={reason}"
    )
    return {
        "recommended": True,
        "tool": "codex_app.automation_update",
        "kind": "heartbeat",
        "destination": "thread",
        "heartbeat_scope": "external_async_wait",
        "interval_minutes": resume_minutes,
        "name": f"AutoResearch async poll: {stage}",
        "prompt": prompt,
        "job_id": job_id,
        "stage": stage,
        "due_at": due_at,
    }


def continuation_wakeup_recommendation(project: str, from_stage: str, to_stage: str) -> dict[str, Any]:
    prompt = (
        "Continue AutoResearch full_auto_bounded workflow for project "
        f"{project}. Run goal.py status, goal.py reconcile --stale-minutes 60, then goal.py tick. "
        "If tick returns a ready repair or async job, dispatch it through the named child skill, "
        "write the required artifacts, update the job, and then continue the bounded loop while progress is locally actionable. "
        "If a stale heartbeat is deleted as cleanup, immediately run status, reconcile, and tick again before deciding to stop. "
        "The loop budget is max_tick_actions=5 or about 10 minutes of active work; stop at hard_stop, queued_async_wait, repair_already_queued without a due packet, external live wait with no eligible parallel experiment launch, terminal completion, user/budget/credential gate, or budget exhaustion. "
        "If tick returns queued_async_wait, create or update the async heartbeat from its wakeup recommendation. "
        "Do not sleep in-thread and do not treat raw literature discovery rows as graph-grounded evidence. "
        f"Continuation target: advanced from {from_stage} to {to_stage}."
    )
    return {
        "recommended": False,
        "tool": "codex_app.automation_update",
        "kind": "continuation_hint",
        "destination": "thread",
        "interval_minutes": 1,
        "name": f"AutoResearch continuation: {to_stage}",
        "prompt": prompt,
        "stage": to_stage,
        "from_stage": from_stage,
    }


def evidence_source_mode(base: Path | None) -> str:
    """Resolve papernexus, external_material, or an explicit unknown mode."""
    if base is None:
        return "papernexus"
    gate_path = base / "ideation/PRE_IDEA_EVIDENCE_GATE.json"
    if gate_path.exists():
        gate = read_json(gate_path, {})
        if not isinstance(gate, dict):
            return "unknown"
        mode = str(gate.get("evidence_source_mode") or "").strip()
        return mode if mode in {"papernexus", "external_material"} else ("papernexus" if not mode else "unknown")
    campaign_path = base / "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
    if campaign_path.exists():
        campaign = read_json(campaign_path, {})
        if not isinstance(campaign, dict):
            return "unknown"
        if campaign.get("source_mode") == "external_material" and campaign.get("papernexus_used") is False:
            return "external_material"
        return "unknown"
    return "papernexus"


def external_material_route(base: Path | None) -> bool:
    return evidence_source_mode(base) == "external_material"


def safe_external_gate_ref(base: Path, raw_ref: Any) -> Path | None:
    ref = str(raw_ref or "").strip()
    relative = Path(ref)
    if not ref or relative.is_absolute() or ".." in relative.parts or "\\" in ref:
        return None
    try:
        resolved = (base / relative).resolve()
        resolved.relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def committed_external_gate(base: Path | None) -> bool:
    if base is None:
        return False
    gate = read_json(base / "ideation/PRE_IDEA_EVIDENCE_GATE.json", {})
    if not (
        isinstance(gate, dict)
        and gate.get("evidence_source_mode") == "external_material"
        and gate.get("status") == "passed"
    ):
        return False
    if (
        gate.get("lane_attempts_satisfied") is not True
        or gate.get("screening_completed") is not True
        or gate.get("allowed_next_action") != "generate_experiment_idea_pool"
        or gate.get("commit_layout") != "content_addressed_v1"
        or gate.get("campaign_ref") != "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
    ):
        return False

    campaign_path = base / "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
    campaign_sha = str(gate.get("campaign_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", campaign_sha) or not campaign_path.is_file():
        return False
    if hashlib.sha256(campaign_path.read_bytes()).hexdigest() != campaign_sha:
        return False
    campaign = read_json(campaign_path, {})
    campaign_id = str(gate.get("campaign_id") or "").strip()
    campaign_revision = gate.get("campaign_revision")
    if not (
        isinstance(campaign, dict)
        and campaign.get("source_mode") == "external_material"
        and campaign.get("papernexus_used") is False
        and campaign.get("campaign_id") == campaign_id
        and campaign.get("campaign_revision") == campaign_revision
        and campaign_id
        and isinstance(campaign_revision, int)
        and not isinstance(campaign_revision, bool)
        and campaign_revision >= 1
    ):
        return False

    lint_sha = str(gate.get("lint_sha256") or "").strip().lower()
    slot_sha = str(gate.get("slot_map_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", lint_sha) or not re.fullmatch(r"[0-9a-f]{64}", slot_sha):
        return False
    lint_ref = str(gate.get("lint_ref") or "")
    slot_ref = str(gate.get("innovation_slot_map_path") or "")
    if lint_ref != f"ideation/committed/NON_PAPERNEXUS_IDEA_LINT.{lint_sha}.json":
        return False
    if slot_ref != f"ideation/committed/INNOVATION_SLOT_MAP.{slot_sha}.json":
        return False
    if gate.get("slot_map_ref") != slot_ref:
        return False
    lint_path = safe_external_gate_ref(base, lint_ref)
    slot_path = safe_external_gate_ref(base, slot_ref)
    if lint_path is None or slot_path is None or not lint_path.is_file() or not slot_path.is_file():
        return False
    if hashlib.sha256(lint_path.read_bytes()).hexdigest() != lint_sha:
        return False
    if hashlib.sha256(slot_path.read_bytes()).hexdigest() != slot_sha:
        return False
    lint_payload = read_json(lint_path, {})
    slot_payload = read_json(slot_path, {})
    if not isinstance(lint_payload, dict) or not isinstance(slot_payload, dict):
        return False
    expected_lint = {
        "complete": True,
        "status": "passed",
        "campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign_id,
        "campaign_revision": campaign_revision,
        "slot_map_ref": slot_ref,
        "slot_map_sha256": slot_sha,
    }
    if any(lint_payload.get(key) != value for key, value in expected_lint.items()):
        return False
    expected_slot = {
        "source_mode": "external_material",
        "campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign_id,
        "campaign_revision": campaign_revision,
    }
    if any(slot_payload.get(key) != value for key, value in expected_slot.items()):
        return False
    admitted = gate.get("admitted_candidate_ids")
    return isinstance(admitted, list) and admitted == lint_payload.get("admitted_candidate_ids")


def execution_spec(stage: str, state: dict[str, Any], contract: dict[str, Any], job: dict[str, Any] | None = None, base: Path | None = None) -> dict[str, Any]:
    corpus = (state.get("paperNexus") or {}).get("corpus")
    goal_topic = state.get("goal") or state.get("objective") or ""
    job_action = str((job or {}).get("action") or "")
    run_id = discovery_run_id(base) if base is not None else None
    broad_metadata_discovery = {
        "depth": "deep",
        "searchMode": "deep",
        "planningMode": "llm_augmented",
        "llmQueryPlanner": True,
        "citationExpansion": True,
        "openAlexRelatedExpansion": True,
        "maxCandidates": 10000,
        "maxQueries": 48,
        "maxQueriesPerProvider": 8,
        "maxResultsPerQuery": 150,
        "maxLlmQueries": 16,
        "maxCitationSeeds": 24,
        "maxCitationsPerSeed": 50,
        "maxRelatedPerSeed": 50,
        "maxEntityQueries": 48,
        "maxExtractedEntities": 160,
        "maxSeedEntities": 100,
        "maxSeedPapers": 50,
        "maxSeedQueries": 40,
        "papersCoolMaxQueries": 48,
        "pasaMaxQueries": 20,
        "providerConcurrency": 4,
        "retryCount": 5,
        "timeoutMs": 300000,
        "searchBudgetMs": 300000,
        "preferMarkdown": True,
        "generateArxivMarkdownSources": True,
        "allowDownloads": False,
        "importBatchEnabled": True,
        "importBatchInitialTasks": 4,
        "importBatchMaxTasks": 16,
        "importBatchProgressive": True,
        "importResolved": False,
        "processImports": False,
        "returnPartial": True,
        "persist": True,
        "asyncLifecycle": "submit_progress_report",
    }
    lane_topics = {
        "target_domain": (
            f"{goal_topic}\n\n"
            "Search lane: target_domain. Focus on closest priors, SOTA methods already present in the current field, "
            "baselines, datasets, metrics, protocols, limitations, future work, negative evidence, and reviewer overlap risk."
        ),
        "near_neighbor": (
            f"{goal_topic}\n\n"
            "Search lane: near_neighbor. Focus on adjacent tasks with similar evaluation pressure "
            "but different mechanisms, assumptions, optimization routes, or continual/open-world settings that could become the primary method source."
        ),
        "far_neighbor": (
            f"{goal_topic}\n\n"
            "Search lane: far_neighbor. Focus on transferable mechanisms from domain-agnostic challenges "
            "such as identity preservation, non-stationarity, streaming discovery, memory, novelty calibration, "
            "and duplicate prevention that could become the primary method source or story bridge."
        ),
    }
    common = {
        "inputs": [
            ".autoreskill/goal_state.json",
            ".autoreskill/memory.md",
            ".autoreskill/evidence_cart.jsonl",
        ],
        "missing": contract.get("missing", []),
    }
    topic_search_spec = {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Submit broad PaperNexus literature discovery for the research goal and capture the server-side run id before waiting.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "plan", "corpus": corpus}},
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": goal_topic, **broad_metadata_discovery}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_run --input <mcp-submit-result.json> --stage topic_search --source papernexus-remote.literature_discovery --status submitted --evidence-note \"topic search broad discovery submitted\" --tag topic_search --tag literature_discovery --tag async_submit",
                )
            ],
            "outputs": [".autoreskill/literature/LITERATURE_DISCOVERY_RUN.json"],
        }
    if job_action in {"poll_literature_discovery", "schedule_async_poll"} and run_id:
        topic_search_spec = {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Poll the submitted PaperNexus literature discovery run; when the report is available, capture it and screen candidates.",
            "mcp_calls": [
                {"tool": "literature_discovery_progress", "args": {"corpus": corpus, "runId": run_id, "pollIntervalMinutes": 5, "staleAfterMinutes": 10}},
                {"tool": "literature_discovery", "args": {"operation": "report", "corpus": corpus, "runId": run_id}},
                {"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 20}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_run --input <progress-result.json> --stage topic_search --source papernexus-remote.literature_discovery_progress --status running --evidence-note \"topic search discovery progress\" --tag topic_search --tag literature_discovery --tag async_progress",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_packet --input <report-result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note \"topic search broad discovery report\" --tag topic_search --tag literature_discovery",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    "--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage topic_search",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind import_workflow_status --input <import-workflow-queue-result.json> --stage topic_search --source papernexus-remote.import_workflow --tag topic_search --tag import_workflow",
                ),
            ],
            "outputs": [
                ".autoreskill/literature/LITERATURE_DISCOVERY_RUN.json",
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
                ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json",
            ],
        }
    elif job_action in {"capture_literature_discovery_report", "screen_literature_discovery"}:
        report_call = {"tool": "literature_discovery", "args": {"operation": "report", "corpus": corpus, "runId": run_id or "<runId from .autoreskill/literature/LITERATURE_DISCOVERY_RUN.json>"}}
        topic_search_spec = {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Capture the completed PaperNexus discovery report if needed, then screen candidates into a scorecard and graph import plan.",
            "mcp_calls": [] if job_action == "screen_literature_discovery" else [report_call],
            "capture": [
                *(
                    [
                        script_cmd(
                            "autoreskill-papernexus-innovation",
                            "papernexus_artifact_capture.py",
                            "--project <project-root> --kind literature_discovery_packet --input <report-result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note \"topic search broad discovery report\" --tag topic_search --tag literature_discovery",
                        )
                    ]
                    if job_action == "capture_literature_discovery_report"
                    else []
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    "--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage topic_search",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "paper_selection_scorecard_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "graph_import_plan_lint.py",
                    "--project <project-root>",
                ),
            ],
            "outputs": [
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
            ],
        }

    specs: dict[str, dict[str, Any]] = {
        "topic_search": topic_search_spec,
        "graph_build": {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Submit or poll PaperNexus import/material tasks for selected graph import plan papers. Every actionable GRAPH_IMPORT_PLAN selected_papers row with import_action=import/supplement must receive a submitted import_workflow task and reach completed/stage=completed plus authoritative sync before graph_build can complete. If exact source discovery, OA/index checks, and PaperNexus pdfUrl/sourcePath/serverFilePath attempts are exhausted for selected rows with no server-acceptable full text, record them as source_limited_exceptions and write GRAPH_BUILD_DECISION decision=advance_with_source_limited_exceptions with source_backed_graph_claim_scope=imported_only and claim_limits; those rows must not count as graph-grounded evidence. Split-reading/material evidence may satisfy material_view rows only.",
            "mcp_calls": [
                {"tool": "list_corpora", "args": {}},
                {"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 20}},
                {
                    "tool": "import_workflow",
                    "args": {
                        "operation": "submit",
                        "corpus": corpus,
                        "identifiers": "<repeat for every remaining actionable GRAPH_IMPORT_PLAN selected_papers import_action=import/supplement with DOI/arxivId/PMID/PMCID/ISBN/ISSN; continue progressive batches until submitted_import_count equals effective_planned_import_count; capture taskIds and idempotency keys; route exhausted no-fulltext rows to source_limited_exceptions instead of retrying empty metadata-only imports>",
                        "processingProfile": "fast-md-background-semantic",
                        "completionPolicy": "graph-visible",
                        "importExecutionMode": "dag",
                        "preferMarkdown": True,
                        "generateArxivMarkdownSources": True,
                        "llmContextWindowTokens": 1000000,
                        "llmExtractionStrategy": "long-context-first",
                        "llmLongContextMaxPapersPerCall": 10,
                        "llmBatchConcurrency": 2,
                        "importBatchEnabled": True,
                        "importBatchInitialTasks": 4,
                        "importBatchMaxTasks": 16,
                        "importBatchProgressive": True,
                        "trigger": "graph_build_selected_import_plan",
                    },
                },
                {"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 50}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_probe_record.py",
                    "--project <project-root> --callable true --corpus <corpus> --corpora-json <list-corpora-result.json>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind import_workflow_status --input <import-workflow-result.json> --stage graph_build --source papernexus-remote.import_workflow --tag graph --tag import_workflow",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind graph_build_decision --input <decision.json> --stage graph_build --source WorkflowGuard --status complete",
                ),
            ],
            "outputs": [".autoreskill/graph/GRAPH_BUILD_DECISION.json", ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json"],
        },
        "frontier_mapping": {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Build frontier, gap, source-transfer, negative-evidence, and experiment norm materials from PaperNexus; trigger follow-up literature discovery when material packs leave missing gap/limitation/transfer roles.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: frontier mapping, limitations, failure modes, negative evidence, transfer sources, and experiment norms.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
                {"tool": "agent_materials", "args": {"operation": "experiment_cost_materials", "corpus": corpus}},
                {"tool": "research_lookup", "args": {"operation": "interdisciplinary_potential", "corpus": corpus}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind research_material_pack --input <mcp-result.json> --stage frontier_mapping --source papernexus-remote.agent_materials --evidence-note \"frontier material evidence\" --tag frontier",
                )
            ],
            "outputs": [".autoreskill/papernexus/research_material_pack.json"],
        },
        "ideation": {
            "skill": "autoreskill-ideation-panel",
            "role": "Researcher",
            "goal": "After the pre-idea evidence gate passes, generate 8-12 lightweight causal hypothesis cards by default; 6-15 is allowed only with an explicit breadth or niche-topic exception. Ground them in screened target-, near-, and far-neighbor PaperNexus evidence, reject duplicate causal signatures, and keep one-variable intervention, mechanism, predicted pattern, falsifier, alternative explanation, and cheapest discriminator explicit. Deepen only the top 3-5 candidates, then construct one core scientific contribution plus only necessary evidence-backed supports and one coherent paper storyline.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": lane_topics["target_domain"], **broad_metadata_discovery}},
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": lane_topics["near_neighbor"], **broad_metadata_discovery}},
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": lane_topics["far_neighbor"], **broad_metadata_discovery}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "pre_idea_discovery_plan.py",
                    "--project <project-root> --topic \"<topic>\" --target-domain \"<target-domain>\"",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_packet --input <mcp-result.json> --stage ideation --source papernexus-remote.literature_discovery --evidence-note \"Ideation broad metadata-only literature discovery\" --tag ideation --tag literature_discovery",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    "--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage ideation",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "pre_idea_discovery_config_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "paper_selection_scorecard_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "pre_idea_breadth_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "graph_import_plan_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "import_workflow_status_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "split_reading_evidence_pack_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-ideation-panel",
                    "pre_idea_evidence_gate_lint.py",
                    "--project <project-root> --write-gate",
                ),
                script_cmd(
                    "autoreskill-experiment-plan",
                    "idea_pool_lint.py",
                    "--project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json",
                ),
                script_cmd("autoreskill-ideation-panel", "idea_scorecard_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage ideation"),
            ],
            "outputs": [
                ".autoreskill/literature/PRE_IDEA_DISCOVERY_PLAN.json",
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/literature/TARGET_DOMAIN_DISCOVERY_PACKET.json",
                ".autoreskill/literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
                ".autoreskill/literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
                ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json",
                ".autoreskill/papernexus/SPLIT_READING_EVIDENCE_PACK.json",
                ".autoreskill/ideation/INNOVATION_SLOT_MAP.json",
                ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.md",
                ".autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md",
            ],
        },
        "literature_review": {
            "skill": "autoreskill-literature-review",
            "role": "Researcher",
            "goal": "Convert discovery and PaperNexus evidence into SOTA matrix, gap synthesis, and citation queue. If SOTA, baseline, dataset, metric, venue, or citation coverage is thin, trigger targeted PaperNexus literature discovery before declaring the review complete.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: SOTA matrix, related work, baseline/dataset/metric anchors, target-venue context, and citation queue closure.", **broad_metadata_discovery}},
                {"tool": "research_briefing", "args": {"operation": "research_brief", "corpus": corpus}},
                {"tool": "research_briefing", "args": {"operation": "evidence_chain", "corpus": corpus}},
            ],
            "capture": [],
            "outputs": [
                ".autoreskill/literature/SOTA_MATRIX.md",
                ".autoreskill/literature/GAP_SYNTHESIS.md",
                ".autoreskill/literature/CITATION_QUEUE.json",
            ],
        },
        "idea_gate": {
            "skill": "autoreskill-ideation-panel",
            "role": "Reviewer",
            "goal": "Pairwise-compare the deeply reviewed shortlist by novelty separation, falsifiability, decision value, feasibility, and evidence quality. Select one paper thesis, assign lifecycle decisions to every idea, and seed one primary plus two alternates by default with a hard maximum of four active tracks. Require one defensible core scientific contribution and reject renamed mechanisms or optional supports presented as novelty. Trigger targeted PaperNexus discovery only for unresolved closest-prior, overlap, negative-evidence, or transfer-bridge blockers.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: selected/top idea novelty gate, closest priors, overlap risk, negative evidence, and transfer-bridge validation.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-ideation-panel", "idea_scorecard_lint.py", "--project <project-root>"),
                script_cmd(
                    "autoreskill-experiment-plan",
                    "idea_pool_lint.py",
                    "--project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json --require-selected",
                ),
                script_cmd("autoreskill-ideation-panel", "idea_track_seeds.py", "--project <project-root> --check"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage idea_gate"),
            ],
            "outputs": [
                ".autoreskill/ideation/TOURNAMENT_SCOREBOARD.json",
                ".autoreskill/ideation/TOP3_DIRECTION_SUMMARY.md",
                ".autoreskill/reviewer/IDEA_GATE_REVIEW.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
                ".autoreskill/ideation/IDEA_DECISION_LEDGER_AUDIT.json",
                ".autoreskill/ideation/IDEA_TRACK_SEEDS.json",
                ".autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md",
            ],
        },
        "experiment_plan": {
            "skill": "autoreskill-experiment-plan",
            "role": "Orchestrator",
            "goal": "Materialize INNOVATION_PACKET, TRACK_PLAN_MATRIX, and EXPERIMENT_REVIEW_PACKET from the selected thesis. Preserve one core contribution and each track's causal signature, prediction, falsifier, alternative explanation, four outcome routes, belief state, and decision-changing experiment. Use bounded B/I/E search under the locked protocol, cap stability at three total random seeds including scouts, plan cross-dataset single-mechanism evidence before supported combinations, and attach hard launch identity plus acquisition class to every ready queue row.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: selected idea experiment-plan closure, novelty risk, baseline/protocol/metric norms, negative evidence, and current-field absence evidence if the method is target-domain-only.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
                {"tool": "agent_materials", "args": {"operation": "closest_prior_materials", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-experiment-plan", "track_plan_matrix.py", "--project <project-root> --check"),
                script_cmd("autoreskill-experiment-plan", "prelaunch_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-experiment-plan", "innovation_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", "--project <project-root> --stage experiment_plan"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage experiment_plan"),
            ],
            "outputs": [
                ".autoreskill/orchestrator/INNOVATION_PACKET.json",
                ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json",
                ".autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json",
                *INNOVATION_STORY_FILES,
            ],
        },
        "code": {
            "skill": "autoreskill-implement-experiment",
            "role": "Coder",
            "goal": "Audit the locked baseline code and dataset, stage/upload the bundle through the selected SSH/local-GPU or AutoDL backend, implement comparable baseline/proposed real experiment entrypoints, and produce real-data or real-feature smoke proof.",
            "mcp_calls": [],
            "capture": [
                script_cmd("autoreskill-implement-experiment", "baseline_clone_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-implement-experiment", "experiment_drift_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", "--project <project-root> --stage code"),
                script_cmd(
                    "autoreskill-implement-experiment",
                    "experiment_real_readiness_lint.py",
                    "--project <project-root>",
                ),
            ],
            "outputs": [
                ".autoreskill/coder/EXPERIMENT_INDEX.md",
                ".autoreskill/coder/experiments/**/EXPERIMENT_MANIFEST.json",
                ".autoreskill/coder/experiments/**/BASELINE_DATA_AUDIT.json",
                ".autoreskill/coder/experiments/**/REMOTE_UPLOAD.json",
                ".autoreskill/coder/experiments/**/REMOTE_RUN.json",
                ".autoreskill/coder/experiments/**/logs/real_*",
            ],
        },
        "experiment": {
            "skill": "autoreskill-run-experiment",
            "role": "Coder",
            "goal": "Claim ready queue rows atomically, launch independent rows up to verified resource limits, and reconcile runtime truth without treating one running row as a global barrier. Preserve full selection, track, branch, queue, and launch identity. For every terminal run, retain canonical results and record a typed SCIENTIFIC_OUTCOME: operational defects do not change belief, protocol-invalid evidence is quarantined, valid negative or inconclusive evidence updates the track rather than triggering code repair, and positive candidates require linked ablation or confirmation before promotion.",
            "mcp_calls": [],
            "capture": [
                script_cmd("autoreskill-implement-experiment", "baseline_clone_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-run-experiment", "baseline_protocol_launch_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", "--project <project-root> --stage experiment"),
            ],
            "outputs": [".autoreskill/coder/EXPERIMENT_LEDGER.json", ".autoreskill/coder/TRACK_RANKING.json", ".autoreskill/coder/EXPERIMENT_INDEX.md"],
        },
        "analysis": {
            "skill": "autoreskill-analyze-results",
            "role": "Analyzer",
            "goal": "Convert canonical experiment evidence and applied track decisions into the claim-evidence matrix, verdicts, idea outcome summary, unsupported claims, and narrative report. A positive paper needs one accepted evidence-backed core scientific contribution; optional supports count only when counterfactually necessary, while parameter tuning, diagnostics, and engineering do not count. A validated terminal negative/inconclusive program may complete with no promoted run and no effective positive contribution, but must set improvement_claim_allowed=false and preserve explicit claim limits. Keep the post-analysis uncertainty self-audit and trigger targeted literature work only for a concrete evidence or framing gap.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: post-result claim repair, contradictory evidence, negative results, limitations, failure modes, and mechanism diagnosis.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-analyze-results", "best_run_selector.py", "--project <project-root> --check"),
                script_cmd("autoreskill-analyze-results", "analysis_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", "--project <project-root> --stage analysis"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage analysis"),
            ],
            "outputs": [
                ".autoreskill/analyzer/BEST_RUN_SELECTION.json",
                ".autoreskill/analyzer/SCORE_VERIFICATION.json",
                ".autoreskill/analyzer/SPEC_VIOLATION_AUDIT.json",
                ".autoreskill/analyzer/IDEA_OUTCOME_SUMMARY.json",
                ".autoreskill/analyzer/CLAIM_EVIDENCE_MATRIX.md",
                ".autoreskill/analyzer/TRACK_VERDICTS.md",
                ".autoreskill/analyzer/UNSUPPORTED_CLAIMS.md",
                ".autoreskill/analyzer/NARRATIVE_REPORT.md",
                *INNOVATION_STORY_FILES,
            ],
        },
        "review_pressure": {
            "skill": "autoreskill-review-gate",
            "role": "Reviewer",
            "goal": "Run multi-round isolated review and close or downgrade blocking findings. Produce at least two complete review-repair cycles covering novelty, soundness/method, experiment/statistics, clarity/writing, and reproducibility/limitations. Write REVIEW_FINDINGS, REVIEW_REPAIR_LEDGER, and MULTI_ROUND_REVIEW_GATE; do not pass review_pressure while high/critical blockers remain open. Trigger targeted PaperNexus discovery for reviewer objections about novelty, related work, missing baselines, missing citations, protocol norms, threat models, or unsupported significance.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: reviewer-pressure repair for novelty, related work, missing baselines/citations, protocol norms, threat models, and significance claims.", **broad_metadata_discovery}},
                {"tool": "research_briefing", "args": {"operation": "evidence_chain", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-review-gate", "review_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-review-gate", "citation_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", "--project <project-root> --stage review_pressure"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage review_pressure"),
            ],
            "outputs": [
                ".autoreskill/reviewer/REVIEW_FINDINGS.json",
                ".autoreskill/reviewer/REVIEW_REPAIR_LEDGER.json",
                ".autoreskill/reviewer/MULTI_ROUND_REVIEW_GATE.json",
                *INNOVATION_STORY_FILES,
            ],
        },
        "writing": {
            "skill": "autoreskill-paper-write",
            "role": "Academic Writer",
            "goal": "Write only from approved claims and IDEA_OUTCOME_SUMMARY. Center one accepted core scientific contribution when positive evidence exists; do not promote parameter tuning, rejected tracks, unsupported future work, or claim-downgraded material. Terminal negative/inconclusive programs may report bounded negative evidence and limitations but no improvement claim. Run numeric, statistical, citation, and presentation forensics; AIS style impressions remain zero-weight.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: manuscript related-work and citation closure, closest-prior contrast, must-cite papers, and claim support.", **broad_metadata_discovery}},
                {"tool": "research_briefing", "args": {"operation": "research_brief", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", "--project <project-root> --stage writing"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage writing"),
                script_cmd("autoreskill-workflow", "paper_forensics_lint.py", "--project <project-root> --stage writing"),
            ],
            "outputs": [
                ".autoreskill/paper/main.tex",
                ".autoreskill/paper/write_package.json",
                ".autoreskill/paper/PAPER_FORENSICS_REPORT.json",
                ".autoreskill/paper/PAPER_CLAIM_LEDGER.json",
                *INNOVATION_STORY_FILES,
            ],
        },
        "submission_ready": {
            "skill": "autoreskill-review-gate",
            "role": "WorkflowGuard",
            "goal": "Verify final package, citations, venue constraints, paper forensics, core-contribution evidence, and the multi-round review gate. Positive manuscripts require one accepted core scientific contribution; terminal negative/inconclusive manuscripts require explicit claim downgrade and no improvement claim. Do not mark submission_ready while claim verification, forensics, citation integrity, or unresolved high/critical review findings fail.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: final citation/source verification and unresolved bibliography blockers before submission.", **broad_metadata_discovery}},
            ],
            "capture": [
                script_cmd("autoreskill-review-gate", "review_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-review-gate", "citation_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", "--project <project-root> --stage submission_ready"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage submission_ready"),
                script_cmd("autoreskill-workflow", "paper_forensics_lint.py", "--project <project-root> --stage submission_ready"),
            ],
            "outputs": [
                ".autoreskill/paper/main.tex",
                ".autoreskill/paper/main.pdf",
                ".autoreskill/paper/PAPER_FORENSICS_REPORT.json",
                ".autoreskill/submission_ready.json",
                ".autoreskill/reviewer/MULTI_ROUND_REVIEW_GATE.json",
                ".autoreskill/reviewer/REVIEW_REPAIR_LEDGER.json",
                *INNOVATION_STORY_FILES,
            ],
        },
    }
    fallback_role = OWNERS.get(stage, "Researcher")
    spec = specs.get(
        stage,
        {
            "skill": f"autoreskill-{stage.replace('_', '-')}",
            "role": fallback_role,
            "goal": f"Satisfy the {stage} contract using the stage-specific autoreskill.",
            "mcp_calls": [],
            "capture": [],
            "outputs": contract.get("missing", []),
        },
    )
    source_mode = evidence_source_mode(base)
    external_route = source_mode == "external_material"
    if source_mode == "unknown" and stage in {"ideation", "idea_gate", "experiment_plan", "experiment"}:
        spec = {
            "skill": "autoreskill-workflow",
            "role": "WorkflowGuard",
            "goal": (
                "Stop and reconcile the unknown or conflicting evidence source mode. Do not invoke PaperNexus, "
                "materialize an external campaign, claim a GPU, prepare a launch intent, or advance the stage until "
                "the canonical pre-idea gate and campaign source declarations select one supported route."
            ),
            "mcp_calls": [],
            "capture": [],
            "outputs": [],
        }
        spec.update(common)
        return spec
    if (
        external_route
        and stage in {"idea_gate", "experiment_plan", "experiment"}
        and not committed_external_gate(base)
    ):
        spec = {
            "skill": "autoreskill-gpu-idea-validation",
            "role": "WorkflowGuard",
            "goal": (
                "Repair the torn or stale external-material pre-idea commit before continuing this later stage. "
                "Revalidate the campaign, require NON_PAPERNEXUS_IDEA_LINT.complete=true, and materialize the "
                "content-addressed lint and slot map with compare-and-swap. Do not invoke PaperNexus, select or "
                "plan an idea, claim resources, record preflight, prepare launch intent, or launch work until the "
                "full committed gate and all bound hashes validate."
            ),
            "mcp_calls": [],
            "capture": [
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "idea_campaign.py",
                    "check --project <project-root> --write-result",
                ),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "idea_campaign.py",
                    "materialize --project <project-root> --expected-current-gate-sha256 <current-gate-sha256-or-absent>",
                ),
            ],
            "outputs": [
                ".autoreskill/ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
                ".autoreskill/ideation/committed/NON_PAPERNEXUS_IDEA_LINT.*.json",
                ".autoreskill/ideation/committed/INNOVATION_SLOT_MAP.*.json",
                ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
            ],
        }
        spec.update(common)
        return spec
    if stage == "ideation" and external_route:
        if not committed_external_gate(base):
            spec = {
                "skill": "autoreskill-gpu-idea-validation",
                "role": "Researcher",
                "goal": (
                    "Construct or repair the explicit non-PaperNexus external-material campaign with the "
                    "ResearchStudio-Idea Phase 0-4 contract. Validate evidence readiness, explicit lineage and "
                    "structural gaps, counted gap closures, mechanism-level collision, five-check audit, independent "
                    "implementability, and protected pilot commitments. Then materialize only the pre-idea gate and "
                    "slot map with compare-and-swap. Do not invoke PaperNexus or advance canonical selection state."
                ),
                "mcp_calls": [],
                "capture": [
                    script_cmd(
                        "autoreskill-gpu-idea-validation",
                        "idea_campaign.py",
                        "check --project <project-root> --write-result",
                    ),
                    script_cmd(
                        "autoreskill-gpu-idea-validation",
                        "idea_campaign.py",
                        "materialize --project <project-root> --expected-current-gate-sha256 <sha256-or-absent>",
                    ),
                ],
                "outputs": [
                    ".autoreskill/ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
                    ".autoreskill/ideation/committed/NON_PAPERNEXUS_IDEA_LINT.*.json",
                    ".autoreskill/ideation/committed/INNOVATION_SLOT_MAP.*.json",
                    ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
                ],
            }
        else:
            spec = dict(spec)
            spec["goal"] = (
                "Consume the committed external-material campaign and passed pre-idea gate without invoking "
                "PaperNexus. Generate the canonical 8-12 idea pool, debate and score 3-5 deep candidates, preserve "
                "campaign/candidate/commitment identity, and produce no more than four admitted tracks under the "
                "normal ideation-panel authority."
            )
            spec["mcp_calls"] = []
            spec["capture"] = [
                script_cmd("autoreskill-gpu-idea-validation", "idea_campaign.py", "check --project <project-root>"),
                script_cmd("autoreskill-ideation-panel", "pre_idea_evidence_gate_lint.py", "--project <project-root>"),
                script_cmd(
                    "autoreskill-experiment-plan",
                    "idea_pool_lint.py",
                    "--project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json",
                ),
                script_cmd("autoreskill-ideation-panel", "idea_scorecard_lint.py", "--project <project-root>"),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "external_alignment_lint.py",
                    "--project <project-root> --stage ideation",
                ),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage ideation"),
            ]
            spec["outputs"] = [
                ".autoreskill/ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
                ".autoreskill/ideation/committed/NON_PAPERNEXUS_IDEA_LINT.*.json",
                ".autoreskill/ideation/committed/INNOVATION_SLOT_MAP.*.json",
                ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.md",
                ".autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md",
            ]
    elif stage == "idea_gate" and external_route:
        spec = dict(spec)
        spec["goal"] = (
            "Pairwise-review the external-material shortlist under the canonical idea-gate authority without "
            "PaperNexus calls. Preserve exact campaign, candidate, fragment, track, and protected-commitment "
            "identity; require the independent panel design review and external alignment before selection."
        )
        spec["mcp_calls"] = []
        spec["capture"] = append_unique(
            list(spec.get("capture") or []),
            [
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "idea_campaign.py",
                    "template --kind panel-design-review",
                ),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "idea_campaign.py",
                    "write-panel-design-review --project <project-root> --input <absolute-independent-panel-review.json> --expected-current-panel-sha256 <current-panel-sha256-or-absent>",
                ),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "external_alignment_lint.py",
                    "--project <project-root> --stage idea_gate",
                )
            ],
        )
    elif stage == "experiment_plan" and external_route:
        spec = dict(spec)
        spec["goal"] = (
            "Materialize the reviewed external-material thesis into canonical innovation/review packets without "
            "PaperNexus calls or fabricated provenance. Preserve distinct campaign candidate, idea fragment, and "
            "track identities plus the exact protected commitment, local_gpu compute class, and reviewed execution route."
        )
        spec["mcp_calls"] = []
        spec["capture"] = append_unique(
            list(spec.get("capture") or []),
            [
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "external_alignment_lint.py",
                    "--project <project-root> --stage experiment_plan",
                )
            ],
        )
    if stage == "idea_gate" and job_action == "recover_replenishment_route":
        spec = dict(spec)
        spec["skill"] = "autoreskill-workflow"
        spec["goal"] = (
            "Recover one project-nonterminal replenishment route as a local, idempotent scientific-control transaction. "
            "Start with research_decision.py --program-recovery-status --check and execute only the reported missing phases. "
            "Phase 1, when the current contract is superseded: use the direct-user authorization from "
            "REPLENISHMENT_INTERVENTION_REQUEST.json to name one unresolved paper decision, draft a genuinely changed-basis "
            "algorithmic/non-evaluator PROGRAM_CLAIM_CONTRACT, complete role-separated novelty, implementability, and scientific-contract "
            "review, then CAS-commit only when the approving review hash and authorized cap match. Phase 2: run "
            "research_decision.py --activate-program-revision --check and then --write; archive the old terminal route, quarantine old "
            "selection authority, and never restore a retired candidate. Phase 3: run one --replenishment --write only if no event exists "
            "for the current basis, then generate exactly one 8-12-card pool, merge equal causal_signature values, and screen one 3-5 item "
            "shortlist. Bind EXPERIMENT_IDEA_POOL and IDEA_NOVELTY_VENUE_SCORECARD to active_program_revision.program_revision_id and "
            "program_claim_contract_sha256. When an unchanged-basis event already exists, materialize its missing supply without consuming "
            "another transaction. Do not infer or raise a budget, generate IDEA_TRACK_SEEDS, admit a track, select or change a primary, write experiment rows, call resource APIs, "
            "launch jobs, or change any paper claim in this repair. Values 0 and exhausted budgets remain hard stops."
        )
        spec["mcp_calls"] = []
        spec["capture"] = append_unique(
            list(spec.get("capture") or []),
            [
                script_cmd("autoreskill-workflow", "research_decision.py", "--project <project-root> --program-recovery-status --check"),
                script_cmd("autoreskill-workflow", "program_claim_contract.py", "check --project <project-root> --require-replacement-authority"),
                script_cmd("autoreskill-workflow", "research_decision.py", "--project <project-root> --activate-program-revision --check"),
                script_cmd("autoreskill-workflow", "research_decision.py", "--project <project-root> --activate-program-revision --write"),
                script_cmd("autoreskill-workflow", "research_decision.py", "--project <project-root> --replenishment --write"),
                script_cmd("autoreskill-experiment-plan", "idea_pool_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-ideation-panel", "idea_scorecard_lint.py", "--project <project-root>"),
            ],
        )
        spec["outputs"] = append_unique(
            list(spec.get("outputs") or []),
            [
                ".autoreskill/control/UNRESOLVED_PAPER_DECISION*.json",
                ".autoreskill/control/PROGRAM_CLAIM_CONTRACT_REPLACEMENT_DRAFT*.json",
                ".autoreskill/reviewer/PROGRAM_CLAIM_CONTRACT_REPLACEMENT_REVIEW*.json",
                ".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json",
                ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                ".autoreskill/decision_log.jsonl",
            ],
        )
    if stage == "experiment" and job_action in {"repair_failed_experiment", "adjudicate_scientific_outcome"}:
        spec = dict(spec)
        spec["goal"] = (
            "Adjudicate the latest untyped terminal run before any relaunch. Read the locked track hypothesis, REMOTE_RUN, canonical result, evaluator/spec/protocol evidence, and selection identity; write SCIENTIFIC_OUTCOME.json with one allowed outcome class and run research_decision.py --check. "
            "Only infrastructure or implementation defects may enter bounded operational repair, protocol-invalid runs must be quarantined, and valid negative or inconclusive outcomes must update belief and follow their predeclared scientific route. Absence of improvement is not evidence of a code defect."
        )
    if stage == "experiment" and job_action in {
        "apply_research_decision",
        "reconcile_scientific_transition",
        "write_terminal_program_decision",
        "queue_ablation_or_confirmation",
    }:
        spec = dict(spec)
        if job_action == "write_terminal_program_decision":
            spec["goal"] = (
                "Validate that every active track is terminal, no launchable or live queue row remains, and every terminal run has an applied scientific outcome. "
                "Run research_decision.py --all-terminal --check, then --write only when it passes; reconcile the experiment ledger. "
                "A negative or inconclusive program must set improvement_claim_allowed=false and carry explicit claim downgrade before advancing."
            )
        elif job_action == "queue_ablation_or_confirmation":
            spec["goal"] = (
                "Treat the positive result as candidate evidence only. Reconcile its scientific decision, then queue the linked ablation or confirmation under the same locked protocol and current selection identity; do not promote it directly."
            )
        else:
            spec["goal"] = (
                "Read the latest SCIENTIFIC_OUTCOME.json and canonical result, run research_decision.py --check for its stable run id, and apply it once with --write when valid. "
                "Regenerate the track matrix and experiment queue from the updated belief/lifecycle state; do not launch work in this decision step."
            )
        spec["capture"] = append_unique(
            list(spec.get("capture") or []),
            [
                script_cmd("autoreskill-workflow", "research_decision.py", "--project <project-root> --run-id <run-id> --check"),
                script_cmd("autoreskill-run-experiment", "dataset_group_hpo.py", "reconcile --project <project-root> --write"),
                script_cmd("autoreskill-workflow", "stage_transition_materialize.py", "--project <project-root> --dry-run"),
                script_cmd("autoreskill-workflow", "stage_transition_materialize.py", "--project <project-root> --expected-queue-revision <dry-run-queue-revision>"),
                script_cmd("autoreskill-workflow", "experiment_next_actions.py", "check --project <project-root>"),
            ],
        )
        spec["outputs"] = append_unique(
            list(spec.get("outputs") or []),
            [
                ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
                ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json",
                ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json",
                ".autoreskill/coder/EXPERIMENT_LEDGER.json",
            ],
        )
    if stage == "experiment" and job_action == "replenish_experiment_portfolio":
        spec = dict(spec)
        spec["skill"] = "autoreskill-workflow"
        spec["goal"] = (
            "Replenish hypothesis supply without reselecting the current primary or changing any live run identity. "
            "First rerun frontier, then run research_decision.py --replenishment --write. This ledger transaction must "
            "authorize the current changed basis before generation; if it rejects or is idempotent, stop this action. "
            "The enforced gate requires a full_auto_bounded paper goal, positive method_admission_deficit, no fillable "
            "committed method candidate for the active program revision, no "
            "decision-bearing ready/live row, unresolved program status, remaining contract budget, and no terminal closure. "
            "Zero active tracks are eligible when these conditions hold. After authorization, preserve the active "
            "selection_fingerprint, reuse the canonical evidence_source_mode and existing audited corpus, and record the "
            "shortlist-exhausted/invalid/superseded lifecycle trigger through existing decision authorities. Reuse raw hits, "
            "static code evidence, and reviewed decisions before any search; run only targeted incremental discovery needed "
            "to close named evidence roles. Generate 8-12 lightweight causal hypothesis cards once, merge equal "
            "causal_signature candidates, deterministically screen one 3-5 item shortlist, and emit track seeds for the "
            "new shortlist supply revision. Do not change the selected primary, admit tracks, write experiment rows, submit "
            "jobs, create a parallel schema, or repeat the action when its lifecycle/evidence/resource fingerprint is unchanged. "
            "The next bounded tick owns batch admission and minimum pilot packet materialization."
        )
        spec["capture"] = append_unique(
            list(spec.get("capture") or []),
            [
                script_cmd("autoreskill-workflow", "experiment_next_actions.py", "frontier --project <project-root>"),
                script_cmd("autoreskill-workflow", "research_decision.py", "--project <project-root> --replenishment --write"),
                script_cmd("autoreskill-ideation-panel", "pre_idea_evidence_gate_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-experiment-plan", "idea_pool_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-ideation-panel", "idea_scorecard_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-ideation-panel", "idea_track_seeds.py", "--project <project-root> --check"),
            ],
        )
        spec["outputs"] = append_unique(
            list(spec.get("outputs") or []),
            [
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                ".autoreskill/ideation/IDEA_TRACK_SEEDS.json",
                ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
                ".autoreskill/decision_log.jsonl",
            ],
        )
    if stage == "experiment" and job_action in {"materialize_experiment_frontier", "batch_fill_experiment_portfolio"}:
        spec = dict(spec)
        spec["skill"] = "autoreskill-workflow" if job_action == "batch_fill_experiment_portfolio" else "autoreskill-experiment-plan"
        if job_action == "batch_fill_experiment_portfolio":
            spec["goal"] = (
                "Consume the exact portfolio_fillable_candidate_ids from the committed shortlist in one synchronous, "
                "journaled batch. Run portfolio_batch.py in dry-run mode, then apply the same operation id after source "
                "hashes still match. Do not regenerate/rescore ideas, exceed four nonterminal tracks, submit jobs, or "
                "promote alternate pilot evidence."
            )
        else:
            spec["goal"] = (
                "Close the current bounded launch-frontier deficit synchronously. Materialize only admitted per-track "
                "packets and packet-enumerated, dependency-unlocked rows; alternates remain pilot_only. Do not infer work "
                "from idle GPU count, add random seeds, submit a backend job, or create an experiment heartbeat."
            )
        materialize_commands = (
            [
                script_cmd("autoreskill-workflow", "portfolio_batch.py", "--project <project-root> --dry-run"),
                script_cmd("autoreskill-workflow", "portfolio_batch.py", "--project <project-root> --operation-id <dry-run-operation-id>"),
            ]
            if job_action == "batch_fill_experiment_portfolio"
            else [
                script_cmd("autoreskill-experiment-plan", "experiment_materialize.py", "--project <project-root> --all-admitted"),
                script_cmd("autoreskill-experiment-plan", "track_plan_matrix.py", "--project <project-root>"),
                script_cmd("autoreskill-run-experiment", "dataset_group_hpo.py", "reconcile --project <project-root> --write"),
                script_cmd("autoreskill-workflow", "stage_transition_materialize.py", "--project <project-root> --dry-run"),
                script_cmd("autoreskill-workflow", "stage_transition_materialize.py", "--project <project-root> --expected-queue-revision <dry-run-queue-revision>"),
            ]
        )
        spec["capture"] = append_unique(
            list(spec.get("capture") or []),
            materialize_commands + [
                script_cmd("autoreskill-workflow", "experiment_next_actions.py", "frontier --project <project-root>"),
                script_cmd("autoreskill-workflow", "experiment_next_actions.py", "check --project <project-root>"),
            ],
        )
        spec["outputs"] = append_unique(
            list(spec.get("outputs") or []),
            [
                ".autoreskill/orchestrator/tracks/*/INNOVATION_PACKET.json",
                ".autoreskill/planner/tracks/*/EXPERIMENT_REVIEW_PACKET.json",
                ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json",
                ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json",
            ],
        )
    if stage == "experiment" and job_action in {
        "repair_or_reconcile_infrastructure",
        "refine_implementation",
        "repair_experiment_protocol",
    }:
        spec = dict(spec)
        spec["goal"] = (
            "Repair only the typed operational defect recorded by the latest SCIENTIFIC_OUTCOME. Preserve hypothesis belief, selection identity, and the locked scientific comparison. "
            "Use the same failure_signature for retries, stop after two operational attempts by default, and do not reinterpret an invalid run as scientific evidence."
        )
        spec["capture"] = append_unique(
            list(spec.get("capture") or []),
            [
                script_cmd("autoreskill-run-experiment", "baseline_protocol_launch_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-implement-experiment", "baseline_clone_lint.py", "--project <project-root>"),
            ],
        )
        spec["outputs"] = append_unique(
            list(spec.get("outputs") or []),
            [
                ".autoreskill/coder/EXPERIMENT_FAILURE_ANALYSIS.json",
                ".autoreskill/coder/EXPERIMENT_NEGATIVE_BLOCKER.json",
                ".autoreskill/coder/EXPERIMENT_LEDGER.json",
                ".autoreskill/coder/TRACK_RANKING.json",
                ".autoreskill/coder/experiments/**/REMOTE_RUN.json",
                ".autoreskill/coder/experiments/**/results/*",
            ],
        )
    if stage == "experiment" and job_action == "launch_parallel_experiment":
        spec = dict(spec)
        if external_route:
            spec["goal"] = (
                "Do not invent an experiment to fill an idle GPU. Reconcile the canonical queue, normalize a fresh "
                "captured SSH/BJTU resource observation, schedule read-only, and process only the first deterministic "
                "external-material pilot assignment for the current revision. Bind its row and physical pool atomically "
                "with claim-assignment, preserve the candidate protected commitment, verify the derived budget and exact "
                "one-GPU launch spec, run route-specific preflight, and persist the queue submit intent before any remote "
                "side effect. A scan, schedule, lease, preflight, or intent is not launch permission; all current-action, "
                "project-policy, and backend-policy authorities must pass. Release unlaunched failures, stale the snapshot, "
                "record the receipt and authoritative observation, refresh, and reschedule. Never preclaim a batch, "
                "kill/preempt work, or retry an ambiguous prepared attempt."
            )
        else:
            spec["goal"] = (
                "Do not treat the currently running experiment as a project-wide barrier. "
                "Read .autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json, reconcile submitting/needs_sync/running rows, "
                "refresh live GPU/HPC resource pools with the backend skill or gpu-idle-scan, persist that snapshot, and run experiment_next_actions.py schedule. "
                "Use only its deterministic ready-row assignments: scientific admission precedes resource placement, acquisition priority does not globally block lower-priority work from otherwise incompatible idle pools, and no experiment may be invented to fill a GPU. "
                "Atomically claim only the current first assignment with its expected queue revision and this worker owner; only the lease winner may launch. Verify project/capability profile fit, run exact backend preflight, persist submit intent before the side effect, record the native receipt, and accept running/terminal state only from authoritative observation. "
                "Then refresh resource evidence and repeat until no fitting row or the bounded wake cap remains. Never retry an ambiguous prepared attempt. Release only an unlaunched lease or one with explicit no-live-run proof. "
                "For BJTU, admit one physical submission per fresh snapshot/preflight/verification checkpoint, then refresh before the next assignment. If no row fits, preserve the scheduler rejection reasons and only then allow the normal experiment heartbeat to wait."
            )
        claim_command = (
            script_cmd(
                "autoreskill-workflow",
                "experiment_next_actions.py",
                "claim-assignment --project <project-root> --row-id <row-id> --pool-id <pool-id> --owner <thread-or-worker-id> --expected-revision <queue-revision>",
            )
            if external_route
            else script_cmd(
                "autoreskill-workflow",
                "experiment_next_actions.py",
                "claim --project <project-root> --row-id <row-id> --owner <thread-or-worker-id> --expected-revision <queue-revision>",
            )
        )
        if external_route:
            spec["capture"] = [
                script_cmd("autoreskill-workflow", "experiment_next_actions.py", "check --project <project-root>"),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "resource_adapter.py",
                    "normalize-for-row --project <project-root> --row-id <row-id> --input <absolute-route-matched-captured-resource-observation.json> --output <absolute-resource-snapshot-proposal.json>",
                ),
                script_cmd(
                    "autoreskill-workflow",
                    "experiment_next_actions.py",
                    "commit-resource-snapshot --project <project-root> --input <absolute-resource-snapshot-proposal.json> --owner <thread-or-worker-id> --expected-revision <queue-revision-before-snapshot-commit>",
                ),
                script_cmd("autoreskill-workflow", "experiment_next_actions.py", "schedule --project <project-root>"),
                claim_command,
                script_cmd("autoreskill-implement-experiment", "baseline_clone_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-run-experiment", "baseline_protocol_launch_lint.py", "--project <project-root>"),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "resource_adapter.py",
                    "launch-spec-digest --input <absolute-launch-spec.json>",
                ),
                script_cmd(
                    "autoreskill-workflow",
                    "experiment_next_actions.py",
                    "record-backend-preflight --project <project-root> --row-id <row-id> --owner <thread-or-worker-id> --expected-revision <queue-revision-after-claim> --input <absolute-route-specific-backend-preflight.json>",
                ),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "resource_adapter.py",
                    "budget-check --project <project-root> --candidate-id <external-candidate-id> --reserve-gpu-hours <hours>",
                ),
                script_cmd(
                    "autoreskill-gpu-idea-validation",
                    "resource_adapter.py",
                    "prepare-launch-intent --project <project-root> --row-id <row-id> --pool-id <pool-id> --run-dir <project-root>/.autoreskill/coder/experiments/<track-id>/<experiment-id> --launch-spec <absolute-launch-spec.json> --approval-ref <current-action-approval-ref>",
                ),
                script_cmd("autoreskill-workflow", "experiment_next_actions.py", "render --project <project-root>"),
            ]
        else:
            spec["capture"] = append_unique(
                list(spec.get("capture") or []),
                [
                    script_cmd("autoreskill-workflow", "experiment_next_actions.py", "check --project <project-root>"),
                    script_cmd("autoreskill-workflow", "experiment_next_actions.py", "schedule --project <project-root>"),
                    claim_command,
                    script_cmd("autoreskill-implement-experiment", "baseline_clone_lint.py", "--project <project-root>"),
                    script_cmd("autoreskill-run-experiment", "baseline_protocol_launch_lint.py", "--project <project-root>"),
                    script_cmd("autoreskill-workflow", "experiment_next_actions.py", "render --project <project-root>"),
                ],
            )
        spec["outputs"] = append_unique(
            list(spec.get("outputs") or []),
            [
                ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json",
                ".autoreskill/experiment/RESOURCE_SNAPSHOT_PROPOSAL.json",
                ".autoreskill/experiment/BACKEND_PREFLIGHT.json",
                ".autoreskill/coder/EXPERIMENT_LEDGER.json",
                ".autoreskill/coder/EXPERIMENT_INDEX.md",
                ".autoreskill/coder/experiments/**/REMOTE_RUN.json",
            ],
        )
    spec.update(common)
    return spec


def write_job_packet(
    base: Path,
    state: dict[str, Any],
    job: dict[str, Any],
    contract: dict[str, Any],
    blocker: dict[str, Any] | None,
    queue_name: str,
) -> Path:
    stage = str(job.get("stage") or state.get("stage", "init"))
    spec = execution_spec(stage, state, contract, job, base)
    mcp_calls = list(spec["mcp_calls"])
    capture_commands = list(spec["capture"])
    outputs = list(spec["outputs"])
    literature_search = has_literature_search(mcp_calls)
    paper_code_transfer_requested = stage in PAPER_CODE_TRANSFER_STAGES and has_paper_code_transfer_request(base, state, job, contract)
    if literature_search:
        corpus = (state.get("paperNexus") or {}).get("corpus")
        if not any(isinstance(call, dict) and call.get("tool") == "import_workflow" for call in mcp_calls):
            mcp_calls.append({"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 20}})
        if not any("--kind literature_discovery_packet" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    f"--project <project-root> --kind literature_discovery_packet --input <mcp-result.json> --stage {stage} --source papernexus-remote.literature_discovery --evidence-note \"{stage} literature discovery evidence\" --tag {stage} --tag literature_discovery",
                )
            )
        if not any("--kind import_workflow_status" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    f"--project <project-root> --kind import_workflow_status --input <import-workflow-queue-or-wait-result.json> --stage {stage} --source papernexus-remote.import_workflow --tag {stage} --tag import_workflow",
                )
            )
        if not any("discovery_metadata_triage.py" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    f"--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage {stage}",
                )
            )
        if not any("import_workflow_status_lint.py" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "import_workflow_status_lint.py",
                    "--project <project-root>",
                )
            )
        outputs = append_unique(
            outputs,
            [
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
                ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json",
                ".autoreskill/papernexus/SPLIT_READING_EVIDENCE_PACK.json",
            ],
        )
    if stage in INNOVATION_STORY_STAGES:
        outputs = append_unique(outputs, INNOVATION_STORY_FILES if stage not in {"ideation", "idea_gate"} else [INNOVATION_STORY_FILES[0]])
        if not any("innovation_story_lint.py" in command for command in capture_commands):
            capture_commands.append(script_cmd("autoreskill-workflow", "innovation_story_lint.py", f"--project <project-root> --stage {stage}"))
    if paper_code_transfer_requested:
        outputs = append_unique(outputs, PAPER_CODE_TRANSFER_FILES)
        if not any("paper_code_transfer_lint.py" in command for command in capture_commands):
            capture_commands.append(script_cmd("autoreskill-workflow", "paper_code_transfer_lint.py", "--project <project-root>"))
    if stage in BASELINE_REPORT_ALIGNMENT_STAGES:
        if not any("baseline_report_alignment_lint.py" in command for command in capture_commands):
            capture_commands.append(script_cmd("autoreskill-workflow", "baseline_report_alignment_lint.py", f"--project <project-root> --stage {stage}"))
    if stage in {"writing", "submission_ready"}:
        if not any("paper_forensics_lint.py" in command for command in capture_commands):
            capture_commands.append(script_cmd("autoreskill-workflow", "paper_forensics_lint.py", f"--project <project-root> --stage {stage}"))
        outputs = append_unique(
            outputs,
            [
                ".autoreskill/paper/PAPER_CLAIM_LEDGER.json",
                ".autoreskill/paper/PAPER_FORENSICS_FINDINGS.json",
                ".autoreskill/paper/PAPER_FORENSICS_REPORT.json",
                ".autoreskill/paper/PAPER_FORENSICS_REPORT.md",
                ".autoreskill/paper/AIS_STYLE_IMPRESSIONS.json",
            ],
        )
    packet_source_mode = evidence_source_mode(base)
    if packet_source_mode == "unknown" and stage in {"ideation", "idea_gate", "experiment_plan", "experiment"}:
        constraints = [
            "Fail closed: the evidence source mode is unknown or conflicting.",
            "Do not invoke PaperNexus, materialize external evidence, claim resources, prepare intent, launch, or advance state.",
            "Reconcile the canonical gate/campaign source declaration before dispatching a scientific child skill.",
        ]
    elif packet_source_mode == "external_material" and stage in {"ideation", "idea_gate", "experiment_plan", "experiment"}:
        constraints = [
            "Do not invoke PaperNexus or relabel PaperNexus artifacts as external_material for this campaign.",
            "Preserve the committed external campaign, candidate, fragment, track, and protected-commitment identity chain.",
            "Do not invent citations, evidence, experiment results, resource availability, or launch authority.",
            "After producing artifacts, rerun the relevant external alignment and stage linters before marking this job complete.",
        ]
    else:
        constraints = [
            "Use PaperNexus live graph work only through papernexus-remote MCP.",
            "Do not use local PaperNexus CLI, raw HTTP, local graph files, local MCP, or SSH graph commands as substitutes.",
            "Do not invent citations, evidence, or experiment results.",
            "After producing artifacts, rerun the relevant linter before marking this job complete.",
        ]
    acceptance_criteria = [
        "Required outputs exist under .autoreskill/",
        "contract_lint.py or the stage linter reports complete",
        "decision_log.jsonl records the produced artifact or explicit blocker",
    ]
    if stage in {"writing", "submission_ready"}:
        acceptance_criteria.append("paper_forensics_lint.py reports complete with no blocking verdict-bearing findings; AIS impressions remain zero-weight")
    if literature_search:
        constraints.extend(
            [
                "Treat literature_discovery submit/report or targeted search results as recall only, not graph-grounded evidence.",
                "For broad or long-running discovery/import work, prefer literature_discovery operation=submit plus progress/report polling; do not lose server-side state to an MCP client timeout.",
                "After every useful discovery result, screen candidates into papernexus/PAPER_SELECTION_SCORECARD.json and reject duplicates, weak relevance, unresolved sources, survey noise, and generic benchmark-only papers.",
                "Build papernexus/GRAPH_IMPORT_PLAN.json from selected usable papers, then request PaperNexus import/supplement/material-view or split-reading evidence before using those papers for novelty, baseline, mechanism, limitation, or citation claims.",
                "Use PaperNexus import_workflow queue_progress/status/wait for every actionable GRAPH_IMPORT_PLAN selected_papers row with import_action=import/supplement; capture papernexus/IMPORT_WORKFLOW_STATUS.json and require submitted_import_count, completed_import_count, and authoritative_sync_completed_count to equal effective_planned_import_count before treating imported graph_import papers as graph-visible. If exact source discovery/OA checks/PaperNexus source attempts are exhausted, record source_limited_exception_keys and claim limits; those exception rows are not graph-grounded evidence and may only be metadata-screened background until later imported.",
                "Do not use split-reading/material evidence to satisfy import_action=import/supplement rows. Split-reading/material evidence may satisfy material_view rows only.",
                "Use progressive import batching defaults unless the server overrides them: importBatchEnabled=true, importBatchInitialTasks=4, importBatchMaxTasks=16, importBatchProgressive=true.",
                "A fast commit with authoritativeSync pending is an async wait condition, not graph-grounded evidence closure.",
            ]
        )
        acceptance_criteria.extend(
            [
                "Raw discovery candidates are screened before any graph/material evidence claim",
                "Selected usable papers have explicit graph_import, split_read_only, watchlist, or rejection decisions",
                "IMPORT_WORKFLOW_STATUS.json records planned/effective-planned/submitted/completed/authoritative-sync counts, taskIds/batchIds, missing unsubmitted/incomplete/unsynced keys for actionable selected import tasks, and source_limited_exception_keys when no server-acceptable full text can be obtained",
                "Graph/material import, authoritative-sync wait, or split-reading blockers are recorded instead of silently treating raw search rows as evidence",
            ]
        )
    if stage in INNOVATION_STORY_STAGES:
        constraints.extend(
            [
                "Maintain the project-bound user-facing innovation story under .autoreskill/user_view/innovation_story/.",
                "Write the story as a narrative persuasion design, not a bullet list of modules or contribution points.",
                "Keep 00_STORYLINE_DESIGN.md focused on reader belief shift, opening tension, hidden cause, method-as-resolution, proof ladder, figures, reviewer risk, and final narrative spine.",
                "Keep 01_METHOD_INNOVATION_STORY.md focused on how the method grows from current-field pressure plus near/far-neighbor or cross-lane transfer mechanisms.",
                "Keep 02_CLAIM_EVIDENCE_MAP.md focused on which paper claims are supported, limited, downgraded, or still waiting for evidence.",
            ]
        )
        acceptance_criteria.extend(
            [
                "innovation_story_lint.py reports complete for this stage",
                "The user-facing innovation story explains the paper storyline and method logic rather than only listing innovation points",
            ]
        )
    if stage in {"ideation", "idea_gate", "experiment_plan"}:
        constraints.extend(
            [
                "Require one falsifiable core scientific contribution; supporting contributions are optional and count only when removing them invalidates the core claim.",
                "Validation, analysis, parameter tuning, and engineering support cannot be relabeled as independent scientific contributions.",
                "At least one innovation point must be grounded in near-neighbor, far-neighbor, proposal-graph, external-domain, or cross-lane transfer evidence unless current-field absence evidence is explicitly source-backed.",
                "The storyline must explain the opening tension, hidden cause, method-as-resolution, proof ladder, reviewer risk/defense, and a sequential narrative spine.",
            ]
        )
        acceptance_criteria.extend(
            [
                "Machine-readable artifacts preserve the core contribution, causal hypothesis, and complete storyline",
                "Every counted supporting scientific contribution records counterfactual necessity",
            ]
        )
    if paper_code_transfer_requested:
        constraints.extend(
            [
                "When the goal or packet requires code survey, preserve the three-layer audit trail: raw paper/code candidates, repository static evidence, and reviewed transfer decisions.",
                "Do not treat repository existence, GitHub stars, project pages, benchmark-only repos, or README-level matches as innovation evidence.",
                "Static source-code evidence can support feasibility, active-code-path, and mechanism-transfer claims only; performance claims require matched experiment artifacts.",
                "Migrated code ideas must record source mechanism, target-task adaptation, required code/protocol changes, novelty/overlap risk, evidence boundary, and validation/falsification route before selection or launch planning.",
            ]
        )
        acceptance_criteria.extend(
            [
                "paper_code_transfer_lint.py reports complete when paper-code survey is required",
                "CODE_MECHANISM_MAP.json and INNOVATION_MIGRATION_MATRIX.json distinguish direct-transfer, needs-adaptation, diagnostic-only, parked, killed, and source-limited ideas",
            ]
        )
    if stage in BASELINE_REPORT_ALIGNMENT_STAGES:
        constraints.extend(
            [
                "Use paper-reported baseline metrics as the primary numerical authority when a paper-backed baseline exists.",
                "Local or reproduced baseline metrics are diagnostic-only unless the project records an internal no-paper-report ablation boundary.",
                "Do not mark a run promoted, ready for analysis, or manuscript-supporting unless baseline_report_alignment_lint.py passes for this stage.",
            ]
        )
        acceptance_criteria.append("baseline_report_alignment_lint.py reports complete for the current stage")
    if stage == "experiment" and str(job.get("action") or "") in {"repair_failed_experiment", "adjudicate_scientific_outcome"}:
        constraints.extend(
            [
                "Write SCIENTIFIC_OUTCOME.json against canonical evidence and the predeclared falsifier before choosing repair, pivot, retire, scope, or confirmation.",
                "Operational retries preserve scientific belief and stop after two attempts for the same failure signature by default.",
                "Scientific revisions use their separate per-track budget; valid negative evidence is never repaired as code solely because the score did not improve.",
                "Candidate-supported or diagnostic-only results are not promoted evidence.",
            ]
        )
        acceptance_criteria.extend(
            [
                "SCIENTIFIC_OUTCOME.json records identity, validity gates, outcome class, belief effect, and recommended transition",
                "EXPERIMENT_LEDGER.json preserves the applied decision and separate operational/scientific counters",
                "No launch occurs during scientific adjudication",
            ]
        )
    acceptance_contract = acceptance_contract_for_packet(
        stage,
        outputs,
        capture_commands,
        constraints,
        acceptance_criteria,
        literature_search=literature_search,
        paper_code_transfer_requested=paper_code_transfer_requested,
    )
    allowed_writes = stage_write_scopes(stage)
    if packet_source_mode == "unknown" and stage in {"ideation", "idea_gate", "experiment_plan", "experiment"}:
        allowed_writes = []
    elif packet_source_mode == "external_material":
        allowed_writes = [path for path in allowed_writes if path != ".autoreskill/papernexus/"]
        if spec["skill"] == "autoreskill-gpu-idea-validation" and stage == "ideation":
            allowed_writes = [
                ".autoreskill/ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
                ".autoreskill/ideation/committed/",
                ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
                ".autoreskill/evidence_cart.jsonl",
                ".autoreskill/artifacts_index.json",
            ]
    path = base / "job_packets" / f"{job['job_id']}.json"
    packet = {
        "schema_version": 1,
        "created_at": iso(now()),
        "job_id": job["job_id"],
        "job_kind": job.get("kind"),
        "queue": queue_name,
        "stage": stage,
        "status": "ready_for_execution",
        "skill": spec["skill"],
        "role": spec["role"],
        "goal": spec["goal"],
        "reason": job.get("reason"),
        "blocker": blocker,
        "inputs": spec["inputs"],
        "missing": spec["missing"],
        "mcp_calls": mcp_calls,
        "capture_commands": capture_commands,
        "allowed_writes": allowed_writes,
        "constraints": constraints,
        "outputs": outputs,
        "acceptance_contract": acceptance_contract,
        "acceptance_criteria": acceptance_criteria,
    }
    write_json(path, packet)
    append_jsonl(
        base / "mailbox.jsonl",
        {
            "ts": iso(now()),
            "type": "job_packet",
            "job_id": job["job_id"],
            "stage": stage,
            "to": spec["role"],
            "skill": spec["skill"],
            "path": str(path),
        },
    )
    return path


def stage_write_scopes(stage: str) -> list[str]:
    common = [
        ".autoreskill/evidence_cart.jsonl",
        ".autoreskill/artifacts_index.json",
    ]
    scopes = {
        "init": [
            ".autoreskill/goal_state.json",
            ".autoreskill/autopilot_policy.json",
            ".autoreskill/capabilities.json",
            ".autoreskill/memory.md",
            ".autoreskill/decision_log.jsonl",
            ".autoreskill/repair_queue.jsonl",
            ".autoreskill/async_jobs.jsonl",
        ],
        "topic_search": [".autoreskill/literature/", ".autoreskill/papernexus/"],
        "graph_build": [".autoreskill/graph/", ".autoreskill/papernexus/"],
        "frontier_mapping": [".autoreskill/papernexus/", ".autoreskill/literature/", ".autoreskill/ideation/"],
        "literature_review": [".autoreskill/literature/", ".autoreskill/papernexus/"],
        "ideation": [".autoreskill/ideation/", ".autoreskill/papernexus/", ".autoreskill/literature/", ".autoreskill/user_view/"],
        "idea_gate": [".autoreskill/ideation/", ".autoreskill/reviewer/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "experiment_plan": [".autoreskill/orchestrator/", ".autoreskill/planner/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "code": [".autoreskill/coder/"],
        "experiment": [".autoreskill/coder/", ".autoreskill/experiment/"],
        "analysis": [".autoreskill/analyzer/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "review_pressure": [".autoreskill/reviewer/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "writing": [".autoreskill/paper/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "submission_ready": [".autoreskill/paper/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/submission_ready.json", ".autoreskill/user_view/"],
    }
    stage_scopes = scopes.get(stage, [f".autoreskill/{stage}/"])
    return [*stage_scopes, *common]


def handoff_for_stage(base: Path, state: dict[str, Any], contract: dict[str, Any]) -> Path:
    stage = str(state.get("stage", "init"))
    owner = str(state.get("owner") or OWNERS.get(stage, "Researcher"))
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    path = base / "handoffs" / f"{stamp}__WorkflowGuard__to__{owner.replace(' ', '')}.json"
    packet = {
        "schema_version": 1,
        "created_at": iso(now()),
        "from": "WorkflowGuard",
        "to": owner,
        "stage": stage,
        "goal": f"Satisfy the {stage} contract without changing upstream evidence or protocol.",
        "inputs": [
            ".autoreskill/goal_state.json",
            ".autoreskill/memory.md",
            ".autoreskill/evidence_cart.jsonl",
        ],
        "missing": contract.get("missing", []),
        "allowed_writes": stage_write_scopes(stage),
        "constraints": [
            "Use PaperNexus live graph work only through papernexus-remote MCP.",
            "Do not invent citations, evidence, or experiment results.",
            "Write machine-readable artifacts when the stage contract defines them.",
        ],
        "outputs": contract.get("missing", []),
        "acceptance_criteria": [
            "contract_lint.py reports complete for the current stage",
            "decision_log.jsonl records the produced artifact or blocker",
        ],
    }
    write_json(path, packet)
    return path


def complete_current_stage(project: str, state: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    stage = str(state.get("stage", "init"))
    if stage == STAGES[-1]:
        state["next_action"] = "workflow_complete"
        state["blocking_reason"] = None
        save_state(project, state, "terminal_complete", {"contract": contract})
        return {"action": "terminal_complete", "stage": stage, "contract": contract}

    new_stage = next_stage(stage)
    state.update(
        {
            "stage": new_stage,
            "owner": OWNERS.get(new_stage, state.get("owner")),
            "next_action": NEXT_ACTIONS.get(new_stage),
            "blocking_reason": None,
        }
    )
    save_state(project, state, "advance_after_contract", {"from": stage, "to": new_stage, "contract": contract})
    return {
        "action": "advanced",
        "from": stage,
        "to": new_stage,
        "contract": contract,
        "continue_now": str(state.get("autonomy_level") or "") == "full_auto_bounded",
        "heartbeat_decision": "not_created_local_progress_available",
    }


def terminal_program_route(base: Path) -> dict[str, Any] | None:
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {})
    decision = ledger.get("program_decision") if isinstance(ledger, dict) else None
    if not isinstance(decision, dict):
        return None
    missing, _, _ = validate_terminal_program_decision(base, decision)
    return None if missing else decision


def supersede_terminal_experiment_jobs(base: Path, decision: dict[str, Any]) -> None:
    reason = f"terminal scientific program decision {decision.get('decision_id')} supersedes experiment repair/wait"
    for job in rows(base / "repair_queue.jsonl"):
        if str(job.get("stage") or "") == "experiment" and str(job.get("status") or "") in {"pending", "retry", "running"}:
            supersede_repair_job(base, job, reason)
    for job in rows(base / "async_jobs.jsonl"):
        if str(job.get("stage") or "") == "experiment" and str(job.get("status") or "") in {"pending", "retry", "running"}:
            supersede_async_job(base, job, reason)


def current_active_selection(base: Path) -> dict[str, set[str]]:
    """Return active selected idea/track ids from current planning artifacts."""

    idea_ids: set[str] = set()
    track_ids: set[str] = set()
    for rel in ["planner/EXPERIMENT_REVIEW_PACKET.json", "orchestrator/INNOVATION_PACKET.json"]:
        payload = read_json(base / rel, {})
        if not isinstance(payload, dict):
            continue
        for key in ["selected_idea_id", "selected_idea_fragment_id", "idea_id"]:
            value = payload.get(key)
            if value:
                idea_ids.add(str(value))
        value = payload.get("track_id")
        if value:
            track_ids.add(str(value))

    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {})
    for row in payload_rows(matrix):
        if not isinstance(row, dict):
            continue
        launch_status = str(row.get("launch_status") or "").lower()
        if launch_status != "ready" and row.get("selected_for_review") is not True:
            continue
        if row.get("idea_id"):
            idea_ids.add(str(row["idea_id"]))
        if row.get("track_id"):
            track_ids.add(str(row["track_id"]))
    return {"idea_ids": idea_ids, "track_ids": track_ids}


def idea_gate_active_selection(base: Path) -> dict[str, set[str]]:
    """Return the active idea/track selection from idea-gate authorities.

    During a negative-result rollback to idea_gate, downstream experiment_plan/code
    artifacts still describe the failed track until the next stage rewrites them.
    The reentry repair gate must therefore read idea_gate authorities first.
    """

    idea_ids: set[str] = set()
    track_ids: set[str] = set()
    for rel in [
        "ideation/IDEA_TRACK_SEEDS.json",
        "ideation/IDEA_DECISION_LEDGER.json",
        "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
        "ideation/EXPERIMENT_IDEA_POOL.json",
    ]:
        payload = read_json(base / rel, {})
        if not isinstance(payload, dict):
            continue
        for key in ["selected_primary_idea_id", "selected_idea_id"]:
            value = payload.get(key)
            if value:
                idea_ids.add(str(value))
        tracks = payload.get("tracks")
        if isinstance(tracks, list):
            for row in tracks:
                if not isinstance(row, dict):
                    continue
                if str(row.get("track_role") or "").strip().lower() == "primary":
                    if row.get("idea_id"):
                        idea_ids.add(str(row["idea_id"]))
                    if row.get("track_id"):
                        track_ids.add(str(row["track_id"]))
    return {"idea_ids": idea_ids, "track_ids": track_ids}


def payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["tracks", "rows", "track_plans"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def route_stale_for_active_selection(route: dict[str, Any], active: dict[str, set[str]]) -> bool:
    """True when a negative-result route refers to a failed idea/track that is no longer active."""

    active_ideas = active.get("idea_ids") or set()
    active_tracks = active.get("track_ids") or set()
    nested_selection: dict[str, Any] = {}
    for key in ["failed_selection", "selection", "current_selection"]:
        value = route.get(key)
        if isinstance(value, dict):
            nested_selection.update(value)
    route_idea = (
        route.get("selected_idea_id")
        or route.get("idea_id")
        or nested_selection.get("selected_idea_id")
        or nested_selection.get("idea_id")
    )
    route_track = (
        route.get("selected_track_id")
        or route.get("track_id")
        or nested_selection.get("selected_track_id")
        or nested_selection.get("track_id")
    )
    if (active_ideas or active_tracks) and not (route_idea or route_track):
        return True
    if route_idea and active_ideas and str(route_idea) not in active_ideas:
        return True
    if route_track and active_tracks and str(route_track) not in active_tracks:
        return True
    return False


def negative_result_rollback_target(base: Path) -> dict[str, Any] | None:
    """Return an explicit rollback target from project route authority artifacts."""

    active_selection = current_active_selection(base)
    blocker = read_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", {})
    if isinstance(blocker, dict) and str(blocker.get("status") or "").strip().lower() in {
        "change_idea_or_innovation_required",
        "two_repairs_without_improvement",
    } and not route_stale_for_active_selection(blocker, active_selection):
        target = str(blocker.get("target_stage") or "idea_gate")
        if target not in STAGES:
            target = "idea_gate"
        return {
            "target_stage": target,
            "next_action": blocker.get("next_action") or NEXT_ACTIONS.get(target),
            "source": "coder/EXPERIMENT_NEGATIVE_BLOCKER.json",
            "decision": "change_idea_or_innovation_after_two_repairs",
            "reason": blocker.get("reason") or "legacy route requires a new causal hypothesis after bounded scientific revisions",
            "required_reentry_conditions": [
                "Update IDEA_DECISION_LEDGER.json for the failed idea lifecycle.",
                "Select an alternate track or change one causal assumption before returning to experiment_plan.",
                "Do not relaunch the same falsified hypothesis under a renamed method or parameter-only change.",
            ],
        }

    positive_routes = sorted(base.glob("orchestrator/POSITIVE_ONLY_STRUCTURAL_LEAP_ROUTE*.json"))
    for path in reversed(positive_routes):
        positive_route = read_json(path, {})
        if (
            isinstance(positive_route, dict)
            and positive_route.get("target_stage_after_decision") in STAGES
            and not route_stale_for_active_selection(positive_route, active_selection)
        ):
            target = str(positive_route["target_stage_after_decision"])
            return {
                "target_stage": target,
                "next_action": positive_route.get("next_action") or NEXT_ACTIONS.get(target),
                "source": str(path.relative_to(base)),
                "decision": positive_route.get("decision"),
                "reason": positive_route.get("reason"),
                "required_reentry_conditions": positive_route.get("required_reentry_conditions", []),
            }

    evidence_route = read_json(base / "orchestrator/EVIDENCE_GATE_ROUTE_DECISION.json", {})
    if (
        isinstance(evidence_route, dict)
        and evidence_route.get("target_stage_after_decision") in STAGES
        and not route_stale_for_active_selection(evidence_route, active_selection)
    ):
        target = str(evidence_route["target_stage_after_decision"])
        return {
            "target_stage": target,
            "next_action": evidence_route.get("next_action") or evidence_route.get("workflowguard_action") or NEXT_ACTIONS.get(target),
            "source": "orchestrator/EVIDENCE_GATE_ROUTE_DECISION.json",
            "decision": evidence_route.get("decision"),
            "reason": evidence_route.get("reason"),
            "required_reentry_conditions": evidence_route.get("required_reentry_conditions", []),
        }

    negative_route = read_json(base / "orchestrator/NEGATIVE_RESULT_ROUTE_DECISION.json", {})
    required_replan = negative_route.get("required_replan") if isinstance(negative_route, dict) else None
    if (
        isinstance(required_replan, dict)
        and required_replan.get("stage") in STAGES
        and not route_stale_for_active_selection(negative_route, active_selection)
    ):
        target = str(required_replan["stage"])
        return {
            "target_stage": target,
            "next_action": required_replan.get("next_action") or NEXT_ACTIONS.get(target),
            "source": "orchestrator/NEGATIVE_RESULT_ROUTE_DECISION.json",
            "decision": negative_route.get("decision"),
            "reason": negative_route.get("reason"),
            "required_reentry_conditions": required_replan.get("requirements", []),
        }

    rollback_route = read_json(base / "orchestrator/TRACK_SWITCH_ROLLBACK_DECISION.json", {})
    if (
        isinstance(rollback_route, dict)
        and rollback_route.get("decision") == "rollback_to_experiment_plan"
        and not route_stale_for_active_selection(rollback_route, active_selection)
    ):
        target = "experiment_plan"
        return {
            "target_stage": target,
            "next_action": NEXT_ACTIONS.get(target),
            "source": "orchestrator/TRACK_SWITCH_ROLLBACK_DECISION.json",
            "decision": rollback_route.get("decision"),
            "reason": rollback_route.get("trigger_reason"),
            "required_reentry_conditions": rollback_route.get("required_rewrite", []),
        }

    return None


def negative_result_rollback_is_pending(base: Path, target: dict[str, Any]) -> bool:
    guard = read_json(base / "orchestrator/NEGATIVE_ROUTE_ROLLBACK_APPLIED.json", {})
    if not isinstance(guard, dict):
        return False
    if guard.get("status") != "awaiting_reentry_repair":
        return False
    route = guard.get("route")
    if not isinstance(route, dict):
        return True
    return route.get("source") == target.get("source") and route.get("target_stage") == target.get("target_stage")


def negative_reentry_repair_required(base: Path) -> dict[str, Any] | None:
    """Return the active positive-only reentry gate when the failed idea/track is still selected."""

    guard = read_json(base / "orchestrator/NEGATIVE_ROUTE_ROLLBACK_APPLIED.json", {})
    if not isinstance(guard, dict) or guard.get("status") != "awaiting_reentry_repair":
        return None
    route = guard.get("route")
    if not isinstance(route, dict):
        return None
    blocker = read_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", {})
    if not isinstance(blocker, dict):
        return None
    if str(blocker.get("status") or "").strip().lower() not in {
        "change_idea_or_innovation_required",
        "two_repairs_without_improvement",
    }:
        return None
    failed_idea = blocker.get("selected_idea_id") or blocker.get("idea_id")
    failed_track = blocker.get("track_id")
    target_stage = str(route.get("target_stage") or blocker.get("target_stage") or "idea_gate")
    if target_stage not in STAGES:
        target_stage = "idea_gate"
    active_selection = current_active_selection(base)
    if target_stage == "idea_gate":
        gate_selection = idea_gate_active_selection(base)
        gate_ideas = gate_selection.get("idea_ids") or set()
        gate_tracks = gate_selection.get("track_ids") or set()
        material_idea_change = bool(failed_idea and gate_ideas and str(failed_idea) not in gate_ideas)
        material_track_change = bool(failed_track and gate_tracks and str(failed_track) not in gate_tracks)
        if material_idea_change or material_track_change:
            return None
        if gate_ideas or gate_tracks:
            active_selection = gate_selection
    elif route_stale_for_active_selection(blocker, active_selection):
        return None
    return {
        "schema_version": 1,
        "status": "reentry_repair_required",
        "target_stage": target_stage,
        "source": route.get("source") or "orchestrator/NEGATIVE_ROUTE_ROLLBACK_APPLIED.json",
        "failed_idea_id": failed_idea,
        "failed_track_id": failed_track,
        "active_idea_ids": sorted(active_selection.get("idea_ids") or []),
        "active_track_ids": sorted(active_selection.get("track_ids") or []),
        "reason": (
            f"positive-only reentry has not materially changed the failed selection "
            f"{failed_idea}/{failed_track}; select an alternate track or change one causal assumption before continuing"
        ),
        "required_reentry_conditions": route.get("required_reentry_conditions")
        or [
            "Update IDEA_DECISION_LEDGER.json for the failed idea lifecycle.",
            "Select an alternate track or change one causal assumption before returning to experiment_plan.",
        ],
    }


def apply_negative_reentry_gate(contract: dict[str, Any], reentry: dict[str, Any]) -> dict[str, Any]:
    patched = dict(contract)
    missing = list(patched.get("missing") or [])
    missing.append(f"positive_only_reentry_gate: {reentry['reason']}")
    patched["complete"] = False
    patched["status"] = "incomplete"
    patched["missing"] = missing
    details = dict(patched.get("details") or {})
    details["positive_only_reentry_gate"] = reentry
    patched["details"] = details
    return patched


def positive_only_rollback_allowed(base: Path, policy: dict[str, Any], target: dict[str, Any] | None) -> bool:
    """Allow rollback to an upstream positive route without enabling negative-result writing."""

    if policy.get("allow_negative_result_route") is True:
        return True
    if not isinstance(target, dict) or target.get("target_stage") not in {"ideation", "idea_gate", "experiment_plan"}:
        return False
    if target.get("decision") == "change_idea_or_innovation_after_two_repairs":
        return policy.get("disable_negative_result_rebuild") is not True

    directive_paths = sorted(base.glob("orchestrator/USER_DIRECTIVE_POSITIVE_ONLY*.json"))
    directives = [read_json(path, {}) for path in directive_paths]
    has_positive_only_directive = any(
        isinstance(row, dict)
        and (
            row.get("directive") == "negative_result_manuscript_forbidden"
            or row.get("policy_effects", {}).get("writing_requires_promoted_positive_evidence") is True
        )
        for row in directives
    )
    if not has_positive_only_directive:
        return False

    blocker = read_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", {})
    routing_paths = sorted(base.glob("coder/POSITIVE_ONLY_EXPERIMENT_ROUTING*.json"))
    routing_docs = [read_json(path, {}) for path in routing_paths]
    route_requires_positive_reentry = (
        isinstance(blocker, dict)
        and blocker.get("negative_result_manuscript_allowed") is False
        and str(blocker.get("required_next_action") or "").startswith("rollback_to_")
    ) or any(
        isinstance(row, dict)
        and row.get("policy", {}).get("negative_result_manuscript_allowed") is False
        and row.get("positive_only_routing", {}).get("recommended_workflow_action")
        == "rollback_to_ideation_or_experiment_plan_for_structural_leap_positive_only"
        for row in routing_docs
    )
    return route_requires_positive_reentry


def apply_negative_result_rollback(project: str, state: dict[str, Any], blocker: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    previous_stage = str(state.get("stage", "unknown"))
    new_stage = str(target["target_stage"])
    state.update(
        {
            "stage": new_stage,
            "owner": OWNERS.get(new_stage, state.get("owner")),
            "next_action": target.get("next_action") or NEXT_ACTIONS.get(new_stage),
            "blocking_reason": target.get("reason") or blocker.get("reason"),
        }
    )
    details = {
        "from": previous_stage,
        "to": new_stage,
        "blocker": blocker,
        "route": target,
    }
    write_json(
        ar(project) / "orchestrator/NEGATIVE_ROUTE_ROLLBACK_APPLIED.json",
        {
            "schema_version": 1,
            "status": "awaiting_reentry_repair",
            "applied_at": iso(now()),
            "from": previous_stage,
            "to": new_stage,
            "route": target,
            "reentry_policy": "Do not apply the same negative/evidence-gate rollback again until the selected evidence gate, replacement-prior plan, or track-switch plan is materially repaired.",
        },
    )
    save_state(project, state, "rollback_after_negative_result_route", details)
    out = {
        "action": "rollback",
        "from": previous_stage,
        "to": new_stage,
        "route": target,
        "blocker": blocker,
        "continue_now": str(state.get("autonomy_level") or "") == "full_auto_bounded",
        "heartbeat_decision": "not_created_local_progress_available",
    }
    return out


def backend_remap_rollback_target(base: Path) -> dict[str, Any] | None:
    request = active_backend_remap_request(base)
    if not request:
        return None
    target = "experiment_plan"
    candidate = request.get("candidate_backend") if isinstance(request.get("candidate_backend"), dict) else {}
    selected = request.get("selected_backend") if isinstance(request.get("selected_backend"), dict) else {}
    return {
        "target_stage": target,
        "next_action": NEXT_ACTIONS.get(target),
        "source": request.get("_path") or "coder/BACKEND_REMAP_REQUEST.json",
        "decision": "rollback_to_experiment_plan_backend_remap",
        "reason": request.get("reason")
        or "Selected code-stage backend is unreachable and implementation cannot change compute_backend/path_mapping.",
        "required_reentry_conditions": request.get("required_plan_updates", []),
        "selected_backend": selected,
        "candidate_backend": candidate,
    }


def backend_remap_rollback_is_pending(base: Path, target: dict[str, Any]) -> bool:
    guard = read_json(base / "orchestrator/BACKEND_REMAP_ROLLBACK_APPLIED.json", {})
    if not isinstance(guard, dict):
        return False
    if guard.get("status") != "awaiting_experiment_plan_remap":
        return False
    route = guard.get("route")
    if not isinstance(route, dict):
        return True
    return route.get("source") == target.get("source") and route.get("target_stage") == target.get("target_stage")


def apply_backend_remap_rollback(project: str, state: dict[str, Any], blocker: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    previous_stage = str(state.get("stage", "unknown"))
    new_stage = str(target["target_stage"])
    state.update(
        {
            "stage": new_stage,
            "owner": OWNERS.get(new_stage, state.get("owner")),
            "next_action": target.get("next_action") or NEXT_ACTIONS.get(new_stage),
            "blocking_reason": target.get("reason") or blocker.get("reason"),
        }
    )
    details = {
        "from": previous_stage,
        "to": new_stage,
        "blocker": blocker,
        "route": target,
    }
    write_json(
        ar(project) / "orchestrator/BACKEND_REMAP_ROLLBACK_APPLIED.json",
        {
            "schema_version": 1,
            "status": "awaiting_experiment_plan_remap",
            "applied_at": iso(now()),
            "from": previous_stage,
            "to": new_stage,
            "route": target,
            "reentry_policy": "Do not return to code until EXPERIMENT_REVIEW_PACKET, INNOVATION_PACKET or path_mapping authority records the selected backend remap and code-stage REMOTE_UPLOAD/REMOTE_RUN targets are updated accordingly.",
        },
    )
    save_state(project, state, "rollback_after_backend_remap_request", details)
    out = {
        "action": "rollback",
        "from": previous_stage,
        "to": new_stage,
        "route": target,
        "blocker": blocker,
        "continue_now": str(state.get("autonomy_level") or "") == "full_auto_bounded",
        "heartbeat_decision": "not_created_local_progress_available",
    }
    return out


def selected_projection_rollback_target(base: Path) -> dict[str, Any]:
    gate_selection = idea_gate_active_selection(base)
    return {
        "target_stage": "experiment_plan",
        "next_action": NEXT_ACTIONS.get("experiment_plan"),
        "source": "contract_lint:selected_projection_alignment",
        "decision": "rollback_to_experiment_plan_projection_repair",
        "reason": (
            "Downstream planning/code authorities do not project the current idea-gate "
            "selected primary idea/track."
        ),
        "active_idea_ids": sorted(gate_selection.get("idea_ids") or []),
        "active_track_ids": sorted(gate_selection.get("track_ids") or []),
        "required_reentry_conditions": [
            "Rewrite INNOVATION_PACKET.json and EXPERIMENT_REVIEW_PACKET.json from the current IDEA_DECISION_LEDGER/IDEA_TRACK_SEEDS selection.",
            "Regenerate TRACK_PLAN_MATRIX.json so launch-ready or selected-for-review rows match the current selected primary idea/track.",
            "Keep historical failed/not-promoted REMOTE_RUN and ledger rows as audit evidence only; do not use them as active code readiness for the new selection.",
        ],
    }


def projection_rollback_is_pending(base: Path, target: dict[str, Any]) -> bool:
    guard = read_json(base / "orchestrator/SELECTED_PROJECTION_ROLLBACK_APPLIED.json", {})
    if not isinstance(guard, dict):
        return False
    if guard.get("status") != "awaiting_experiment_plan_projection_repair":
        return False
    route = guard.get("route")
    if not isinstance(route, dict):
        return True
    return route.get("decision") == target.get("decision") and route.get("target_stage") == target.get("target_stage")


def apply_selected_projection_rollback(project: str, state: dict[str, Any], blocker: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    previous_stage = str(state.get("stage", "unknown"))
    new_stage = str(target["target_stage"])
    state.update(
        {
            "stage": new_stage,
            "owner": OWNERS.get(new_stage, state.get("owner")),
            "next_action": target.get("next_action") or NEXT_ACTIONS.get(new_stage),
            "blocking_reason": target.get("reason") or blocker.get("reason"),
        }
    )
    details = {
        "from": previous_stage,
        "to": new_stage,
        "blocker": blocker,
        "route": target,
    }
    write_json(
        ar(project) / "orchestrator/SELECTED_PROJECTION_ROLLBACK_APPLIED.json",
        {
            "schema_version": 1,
            "status": "awaiting_experiment_plan_projection_repair",
            "applied_at": iso(now()),
            "from": previous_stage,
            "to": new_stage,
            "route": target,
            "reentry_policy": (
                "Do not return to code until INNOVATION_PACKET, EXPERIMENT_REVIEW_PACKET, "
                "TRACK_PLAN_MATRIX, and active implementation/readiness rows align with "
                "the current idea-gate selected primary idea/track."
            ),
        },
    )
    save_state(project, state, "rollback_after_selected_projection_drift", details)
    return {
        "action": "rollback",
        "from": previous_stage,
        "to": new_stage,
        "route": target,
        "blocker": blocker,
        "continue_now": str(state.get("autonomy_level") or "") == "full_auto_bounded",
        "heartbeat_decision": "not_created_local_progress_available",
    }


def selected_negative_evidence_rollback_target(base: Path) -> dict[str, Any]:
    gate_selection = idea_gate_active_selection(base)
    return {
        "target_stage": "idea_gate",
        "next_action": NEXT_ACTIONS.get("idea_gate"),
        "source": "contract_lint:selected_negative_evidence",
        "decision": "rollback_to_idea_gate_after_selected_negative_evidence",
        "reason": (
            "The current idea-gate selected primary idea/track already has terminal "
            "not-promoted experiment evidence and lacks an explicit launch-blocked "
            "non-equivalent reentry authority."
        ),
        "active_idea_ids": sorted(gate_selection.get("idea_ids") or []),
        "active_track_ids": sorted(gate_selection.get("track_ids") or []),
        "required_reentry_conditions": [
            "Update IDEA_DECISION_LEDGER.json so the failed selected idea/track is parked or killed with failure_class and next_action.",
            "Select a non-equivalent alternate track or change one causal assumption using evidence.",
            "Do not make a positive improvement claim; a validated all-terminal program may report bounded negative evidence.",
            "Do not return to experiment_plan/code until the new selected idea has no unresolved same-track terminal negative evidence.",
        ],
    }


def selected_negative_evidence_rollback_is_pending(base: Path, target: dict[str, Any]) -> bool:
    guard = read_json(base / "orchestrator/SELECTED_NEGATIVE_EVIDENCE_ROLLBACK_APPLIED.json", {})
    if not isinstance(guard, dict):
        return False
    if guard.get("status") != "awaiting_idea_gate_reselection":
        return False
    route = guard.get("route")
    if not isinstance(route, dict):
        return True
    return route.get("decision") == target.get("decision") and route.get("target_stage") == target.get("target_stage")


def apply_selected_negative_evidence_rollback(project: str, state: dict[str, Any], blocker: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    previous_stage = str(state.get("stage", "unknown"))
    new_stage = str(target["target_stage"])
    state.update(
        {
            "stage": new_stage,
            "owner": OWNERS.get(new_stage, state.get("owner")),
            "next_action": target.get("next_action") or NEXT_ACTIONS.get(new_stage),
            "blocking_reason": target.get("reason") or blocker.get("reason"),
        }
    )
    details = {
        "from": previous_stage,
        "to": new_stage,
        "blocker": blocker,
        "route": target,
    }
    write_json(
        ar(project) / "orchestrator/SELECTED_NEGATIVE_EVIDENCE_ROLLBACK_APPLIED.json",
        {
            "schema_version": 1,
            "status": "awaiting_idea_gate_reselection",
            "applied_at": iso(now()),
            "from": previous_stage,
            "to": new_stage,
            "route": target,
            "reentry_policy": (
                "Do not return to experiment_plan until idea-gate authorities select a "
                "non-equivalent idea/track or record explicit launch-blocked reentry "
                "after the terminal negative evidence."
            ),
        },
    )
    save_state(project, state, "rollback_after_selected_negative_evidence", details)
    return {
        "action": "rollback",
        "from": previous_stage,
        "to": new_stage,
        "route": target,
        "blocker": blocker,
        "continue_now": str(state.get("autonomy_level") or "") == "full_auto_bounded",
        "heartbeat_decision": "not_created_local_progress_available",
    }


def run_tick_owned(args: argparse.Namespace) -> None:
    base = ar(args.project)
    state = load_state(args.project)
    policy = read_json(base / "autopilot_policy.json", {})
    repair_queue = rows(base / "repair_queue.jsonl")
    async_queue = rows(base / "async_jobs.jsonl")
    retry_override = active_retry_override(base, args)
    current_stage = str(state.get("stage", "init"))
    program_route = terminal_program_route(base) if current_stage == "experiment" else None
    if program_route:
        supersede_terminal_experiment_jobs(base, program_route)
        repair_queue = rows(base / "repair_queue.jsonl")
        async_queue = rows(base / "async_jobs.jsonl")
        if program_route.get("target_stage") == "idea_gate":
            state.update(
                {
                    "stage": "idea_gate",
                    "owner": OWNERS.get("idea_gate", state.get("owner")),
                    "next_action": NEXT_ACTIONS.get("idea_gate"),
                    "blocking_reason": None,
                }
            )
            save_state(
                args.project,
                state,
                "terminal_program_route",
                {"from": "experiment", "to": "idea_gate", "program_decision": program_route},
            )
            print(
                json.dumps(
                    {
                        "action": "terminal_program_route",
                        "from": "experiment",
                        "to": "idea_gate",
                        "program_decision": program_route,
                        "heartbeat_decision": "not_created_local_progress_available",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return

    due_async = next_due_job(async_queue, include_running=True, kind="async", retry_override=retry_override)
    while due_async:
        gate = async_wait_gate(
            base,
            str(due_async.get("stage") or ""),
            str(due_async.get("action") or ""),
            str(due_async.get("reason") or ""),
            job=due_async,
            current_stage=current_stage,
        )
        obsolete_reason = obsolete_async_wait_reason(base, due_async, current_stage=current_stage, gate=gate)
        if obsolete_reason:
            supersede_async_job(base, due_async, obsolete_reason)
        else:
            due_async["wait_kind"] = gate.get("wait_kind")
            due_async["heartbeat_decision"] = gate.get("decision")
            due_async["heartbeat_decision_reason"] = gate.get("reason")
            break
        async_queue = rows(base / "async_jobs.jsonl")
        due_async = next_due_job(async_queue, include_running=True, kind="async", retry_override=retry_override)

    due_repair = next_due_job(repair_queue, include_running=True, kind="repair", retry_override=retry_override)
    while due_repair:
        obsolete_reason = obsolete_repair_reason(args.project, base, state, due_repair)
        if not obsolete_reason:
            break
        supersede_repair_job(base, due_repair, obsolete_reason)
        repair_queue = rows(base / "repair_queue.jsonl")
        due_repair = next_due_job(repair_queue, include_running=True, kind="repair", retry_override=retry_override)
    if due_repair:
        mark_job_running(base, "repair_queue.jsonl", due_repair)
        packet = write_job_packet(base, state, due_repair, job_contract(args.project, due_repair), None, "repair_queue.jsonl")
        save_state(args.project, state, "dispatch_repair", {"job": due_repair, "job_packet": str(packet)})
        print(json.dumps({"action": "dispatch_repair", "job": due_repair, "job_packet": str(packet)}, indent=2, ensure_ascii=False))
        return

    stage = current_stage
    contract = lint(args.project, stage)
    reentry_repair = negative_reentry_repair_required(base)
    if reentry_repair and stage == reentry_repair.get("target_stage"):
        contract = apply_negative_reentry_gate(contract, reentry_repair)
    recovery = program_recovery_status(base) if stage == "idea_gate" else {"applicable": False}
    if contract["complete"] and not recovery.get("applicable"):
        print(json.dumps(complete_current_stage(args.project, state, contract), indent=2, ensure_ascii=False))
        return

    if recovery.get("applicable"):
        reason = str(recovery.get("reason") or "replacement program recovery incomplete")
        klass = str(recovery.get("class") or "hard_stop")
        recommended_action = str(recovery.get("action") or "repair_replenishment_authority")
        contract = {
            **contract,
            "complete": False,
            "missing": [reason],
            "contract_source": "program_recovery_status",
            "program_recovery": recovery,
        }
    else:
        reason = contract_reason(contract, stage)
        klass, recommended_action = classify(stage, reason, base)
    blocker = {
        "schema_version": 1,
        "ts": iso(now()),
        "stage": stage,
        "reason": reason,
        "class": klass,
        "recommended_action": recommended_action,
        "contract": contract,
        "status": "triaged",
    }

    async_gate: dict[str, Any] | None = None
    if klass == "async_wait":
        async_gate = async_wait_gate(base, stage, recommended_action, reason, current_stage=current_stage, contract=contract)
        if async_gate.get("allowed"):
            blocker["heartbeat_decision"] = async_gate.get("decision")
            blocker["heartbeat_decision_reason"] = async_gate.get("reason")
            blocker["wait_kind"] = async_gate.get("wait_kind")
        else:
            klass = "auto_repairable"
            recommended_action = "schedule_repair"
            blocker["class"] = klass
            blocker["recommended_action"] = recommended_action
            blocker["heartbeat_decision"] = "not_created_not_external_wait"
            blocker["heartbeat_decision_reason"] = async_gate.get("reason")

    if klass != "async_wait" and due_async:
        due_stage = str(due_async.get("stage") or "")
        due_action = str(due_async.get("action") or "")
        if due_stage == stage and due_action in ASYNC_HEARTBEAT_ACTIONS:
            due_async["heartbeat_decision"] = "not_dispatched_local_progress_available"
            due_async["heartbeat_decision_reason"] = reason

    blocker.update(repair_metadata(base, "async" if klass == "async_wait" else "repair", stage, recommended_action, reason))

    append_jsonl(base / "blocker_ledger.jsonl", blocker)

    if klass == "hard_stop":
        if recommended_action == "rollback_to_experiment_plan_backend_remap" and stage == "code":
            target = backend_remap_rollback_target(base)
            if target and not backend_remap_rollback_is_pending(base, target):
                print(json.dumps(apply_backend_remap_rollback(args.project, state, blocker, target), indent=2, ensure_ascii=False))
                return
        if recommended_action == "rollback_to_experiment_plan_projection_repair" and stage == "code":
            target = selected_projection_rollback_target(base)
            if target and not projection_rollback_is_pending(base, target):
                print(json.dumps(apply_selected_projection_rollback(args.project, state, blocker, target), indent=2, ensure_ascii=False))
                return
        if recommended_action == "rollback_to_idea_gate_after_selected_negative_evidence" and stage in {"experiment_plan", "code"}:
            target = selected_negative_evidence_rollback_target(base)
            if target and not selected_negative_evidence_rollback_is_pending(base, target):
                print(json.dumps(apply_selected_negative_evidence_rollback(args.project, state, blocker, target), indent=2, ensure_ascii=False))
                return
        if (
            recommended_action == "rollback_or_negative_result_route"
            and stage == "experiment"
        ):
            target = negative_result_rollback_target(base)
            if (
                target
                and positive_only_rollback_allowed(base, policy, target)
                and (
                    not negative_result_rollback_is_pending(base, target)
                    or negative_reentry_repair_required(base)
                )
            ):
                print(json.dumps(apply_negative_result_rollback(args.project, state, blocker, target), indent=2, ensure_ascii=False))
                return
        state["blocking_reason"] = reason
        state["next_action"] = recommended_action
        save_state(args.project, state, "hard_stop", blocker)
        print(json.dumps({"action": "hard_stop", "blocker": blocker}, indent=2, ensure_ascii=False))
        return

    if klass == "async_wait":
        if due_async and str(due_async.get("stage") or "") == stage and str(due_async.get("action") or "") == recommended_action:
            mark_job_running(base, "async_jobs.jsonl", due_async)
            packet = write_job_packet(base, state, due_async, job_contract(args.project, due_async), blocker, "async_jobs.jsonl")
            save_state(args.project, state, "dispatch_async_poll", {"blocker": blocker, "job": due_async, "job_packet": str(packet)})
            print(
                json.dumps(
                    {"action": "dispatch_async_poll", "blocker": blocker, "job": due_async, "job_packet": str(packet)},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        if due_async:
            supersede_async_job(
                base,
                due_async,
                (
                    "async wait superseded because the current contract selected a different external blocker: "
                    f"{recommended_action}"
                ),
            )
        job = queue_job(base, "async", stage, recommended_action, reason, policy)
        if async_gate is not None:
            job["wait_kind"] = async_gate.get("wait_kind")
            job["heartbeat_decision"] = async_gate.get("decision")
            job["heartbeat_decision_reason"] = async_gate.get("reason")
        packet = None if job.get("_reused") else write_job_packet(base, state, job, contract, blocker, "async_jobs.jsonl")
        wakeup = async_wakeup_recommendation(args.project, job, reason)
        state["blocking_reason"] = reason
        state["next_action"] = recommended_action
        save_state(
            args.project,
            state,
            "queued_async_wait",
            {"blocker": blocker, "job": job, "job_packet": str(packet) if packet else None, "wakeup": wakeup},
        )
        print(
            json.dumps(
                {
                    "action": "queued_async_wait",
                    "blocker": blocker,
                    "job": job,
                    "job_packet": str(packet) if packet else None,
                    "wakeup": wakeup,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if (
        stage == "experiment"
        and recommended_action in {"launch_or_reconcile_experiment", "launch_parallel_experiment", "repair_failed_experiment", "schedule_repair"}
        and not active_experiment_run_exists(base)
    ):
        supersede_matching_async_jobs(
            base,
            stage,
            "poll_experiment_run",
            None,
            (
                "experiment async poll superseded because no active experiment runtime remains; "
                "WorkflowGuard can use local evidence to launch, repair, or advance instead of waiting for heartbeat"
            ),
        )

    job = queue_job(base, "repair", stage, recommended_action, reason, policy)
    if job.get("_budget_exhausted"):
        fallback = (
            "write_terminal_program_decision"
            if job.get("repair_kind") == "scientific_revision" and all_recorded_tracks_terminal(base)
            else "retire_or_pivot_track"
            if job.get("repair_kind") == "scientific_revision"
            else "rollback_or_request_intervention"
        )
        state["blocking_reason"] = f"{reason}; {job.get('_reuse_reason')}"
        state["next_action"] = fallback
        save_state(args.project, state, "repair_budget_exhausted", {"blocker": blocker, "job": job, "fallback": fallback})
        print(
            json.dumps(
                {"action": "repair_budget_exhausted", "blocker": blocker, "job": job, "next_action": fallback},
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    handoff = None if job.get("_reused") else handoff_for_stage(base, state, contract)
    packet = None if job.get("_reused") else write_job_packet(base, state, job, contract, blocker, "repair_queue.jsonl")
    action = "repair_already_queued" if job.get("_reused") else "queued_repair_handoff"
    state["blocking_reason"] = reason
    state["next_action"] = recommended_action
    save_state(
        args.project,
        state,
        action,
        {"blocker": blocker, "job": job, "handoff": str(handoff) if handoff else None, "job_packet": str(packet) if packet else None},
    )
    print(
        json.dumps(
            {
                "action": action,
                "blocker": blocker,
                "job": job,
                "handoff": str(handoff) if handoff else None,
                "job_packet": str(packet) if packet else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def run_tick(args: argparse.Namespace) -> None:
    owner = str(
        getattr(args, "control_owner", None)
        or os.environ.get("AUTOSKILL_CONTROL_OWNER")
        or f"goal-tick:{os.getpid()}"
    ).strip()
    lease_args = argparse.Namespace(
        project=args.project,
        lease_file=None,
        scope="project-control",
        owner=owner,
        operation="goal_tick",
        ttl_minutes=int(getattr(args, "control_lease_minutes", 10)),
        reason="goal tick control-plane mutation complete",
    )
    code, lease = acquire_control_lease(lease_args)
    if code != 0:
        print(
            json.dumps(
                {
                    "action": "project_control_busy",
                    "owner": owner,
                    "lease": lease,
                    "heartbeat_decision": "not_created_control_plane_busy",
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    try:
        run_tick_owned(args)
    finally:
        release_control_lease(lease_args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--force-due-repair",
        action="store_true",
        help="dispatch a matching pending/retry repair immediately, bypassing next_retry_at after a human/resource update",
    )
    parser.add_argument(
        "--force-job-id",
        help="limit --force-due-repair or ACTIVE_RETRY_OVERRIDE dispatch to one job id",
    )
    parser.add_argument("--control-owner", help="Stable project-control lease owner for this tick.")
    parser.add_argument("--control-lease-minutes", type=int, default=10)
    args = parser.parse_args()
    run_tick(args)


if __name__ == "__main__":
    main()
