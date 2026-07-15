#!/usr/bin/env python3
"""Build a Codex app automation_update payload from EXPERIMENT_MONITOR_PLAN."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V1_MARKER = "[heartbeat-experiment-opportunity-scan-v1]"
V2_START = "[heartbeat-experiment-opportunity-scan-v2:start]"
V2_END = "[heartbeat-experiment-opportunity-scan-v2:end]"
V3_START = "[heartbeat-experiment-opportunity-scan-v3:start]"
V3_END = "[heartbeat-experiment-opportunity-scan-v3:end]"
ACTIVE_QUEUE_STATUSES = {"planned", "submitting", "needs_sync", "running"}
WORKFLOW_QUEUE_HELPER = (
    Path(__file__).resolve().parents[2] / "autoreskill-workflow/scripts/experiment_next_actions.py"
)


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


def rrule_interval(value: Any) -> int | None:
    match = re.search(r"(?:^|;)INTERVAL=(\d+)(?:;|$)", str(value or ""))
    if not match:
        return None
    return bounded_minutes(match.group(1), 5)


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def monitor_plan_semantic_sha256(plan: dict[str, Any]) -> str:
    semantic = json.loads(json.dumps(plan))
    for key in [
        "monitor_plan_revision",
        "monitor_plan_semantic_sha256",
        "prompt",
        "prompt_plan_revision",
        "prompt_plan_sha256",
        "prompt_sha256",
    ]:
        semantic.pop(key, None)
    scheduled = semantic.get("scheduled_wakeup")
    if isinstance(scheduled, dict):
        for key in ["prompt", "prompt_plan_revision", "prompt_plan_sha256", "prompt_sha256"]:
            scheduled.pop(key, None)
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def current_explicit_prompt(plan: dict[str, Any]) -> tuple[str | None, str]:
    revision = plan.get("monitor_plan_revision")
    current_sha256 = monitor_plan_semantic_sha256(plan)
    for label, source in [
        ("plan", plan),
        ("scheduled_wakeup", plan.get("scheduled_wakeup")),
    ]:
        if not isinstance(source, dict) or not present(source.get("prompt")):
            continue
        prompt = str(source.get("prompt"))
        if (
            isinstance(revision, int)
            and source.get("prompt_plan_revision") == revision
            and str(source.get("prompt_plan_sha256") or "") == current_sha256
            and str(source.get("prompt_sha256") or "") == sha256_text(prompt)
        ):
            return prompt, f"explicit_{label}_current"
        return None, f"explicit_{label}_stale"
    return None, "no_explicit_prompt"


def load_workflow_module() -> Any:
    spec = importlib.util.spec_from_file_location("autoreskill_monitor_frontier", WORKFLOW_QUEUE_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {WORKFLOW_QUEUE_HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frontier_state(project: str, queue: dict[str, Any]) -> dict[str, Any]:
    if not queue:
        return {}
    module = load_workflow_module()
    root = Path(project).expanduser().resolve()
    matrix = read_json(root / ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json", {})
    return module.frontier_status(queue, matrix=matrix, project=root)


def strip_opportunity_scan_contract(prompt: str) -> str:
    cleaned = re.sub(
        re.escape(V3_START) + r".*?" + re.escape(V3_END),
        "",
        prompt,
        flags=re.DOTALL,
    ).rstrip()
    cleaned = re.sub(
        re.escape(V2_START) + r".*?" + re.escape(V2_END),
        "",
        cleaned,
        flags=re.DOTALL,
    ).rstrip()
    if V1_MARKER in cleaned:
        cleaned = cleaned.split(V1_MARKER, 1)[0].rstrip()
    return cleaned


def append_opportunity_scan_contract(
    prompt: str,
    admission_scope: str,
    frontier: dict[str, Any],
    queue: dict[str, Any],
    passport: dict[str, Any],
) -> str:
    """Replace prior heartbeat clauses with one current, bounded v3 contract."""

    queue_sha256 = hashlib.sha256(
        json.dumps(queue, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest() if queue else "missing"
    profile_hashes = sorted(
        {
            str(row.get("execution_profile_sha256"))
            for row in queue.get("rows", [])
            if isinstance(row, dict) and present(row.get("execution_profile_sha256"))
        }
    )
    state = {
        "queue_revision": queue.get("queue_revision"),
        "queue_sha256": queue_sha256,
        "admission_scope": admission_scope,
        "program_contract_status": frontier.get("program_contract_status"),
        "program_contract_enforcement_mode": frontier.get("program_contract_enforcement_mode"),
        "program_claim_contract_sha256": frontier.get("program_claim_contract_sha256"),
        "program_scientific_status": frontier.get("program_scientific_status"),
        "launch_frontier_target": frontier.get("launch_frontier_target"),
        "launch_frontier_supply_count": frontier.get("launch_frontier_supply_count"),
        "launch_frontier_deficit": frontier.get("launch_frontier_deficit"),
        "portfolio_capacity_target": frontier.get("portfolio_capacity_target"),
        "method_portfolio_target": frontier.get("method_portfolio_target"),
        "active_method_candidate_count": frontier.get("active_method_candidate_count"),
        "method_portfolio_deficit": frontier.get("method_portfolio_deficit"),
        "diagnostic_active_track_count": frontier.get("diagnostic_active_track_count"),
        "active_nonterminal_track_count": frontier.get("active_nonterminal_track_count"),
        "portfolio_admission_deficit": frontier.get("portfolio_admission_deficit"),
        "portfolio_fillable_candidate_ids": frontier.get("portfolio_fillable_candidate_ids") or [],
        "portfolio_blocker_code": frontier.get("portfolio_blocker_code"),
        "parameter_profile_status_by_track": frontier.get("parameter_profile_status_by_track") or {},
        "parameter_coverage_deficit_by_track_and_dataset": frontier.get("parameter_coverage_deficit_by_track_and_dataset") or {},
        "parameter_blockers": frontier.get("parameter_blockers") or [],
        "seed_only_parameter_substitution_rejected_count": frontier.get("seed_only_substitution_rejected_count"),
        "dataset_coverage_deficit_by_track": frontier.get("dataset_coverage_deficit_by_track") or {},
        "paired_group_incomplete_count": frontier.get("paired_group_incomplete_count"),
        "paired_group_missing_dataset_legs": frontier.get("paired_group_missing_dataset_legs") or {},
        "cross_dataset_full_budget_ready_count": frontier.get("cross_dataset_full_budget_ready_count"),
        "robust_hpo_ready_count": frontier.get("robust_hpo_ready_count"),
        "cross_dataset_blockers": frontier.get("cross_dataset_blockers") or [],
        "fresh_fitting_idle_slots": frontier.get("fresh_fitting_idle_slots"),
        "project_passport_index_sha256": passport.get("index_semantic_sha256"),
        "execution_profile_sha256s": profile_hashes,
    }
    clause = (
        f"{V3_START}\n"
        f"Current control state: {json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
        "On every wake: reconcile backend/terminal evidence; apply hypothesis lifecycle decisions; recompute launch frontier and "
        "portfolio_admission_deficit, method_portfolio_deficit, and per-track parameter/profile deficits; batch-admit the exact "
        "deterministic feasible shortlist subset up to four hypothesis tracks without counting diagnostics as methods; materialize "
        "every dependency-unlocked parameter-probe or paired-dataset validation row; reconcile complete dataset-group HPO trials, "
        "run the ledger-driven Stage 3-6 materializer, and never expose an HPO objective for an incomplete group; refresh capability-enriched resources; claim one fitting assignment, "
        "preflight, durably prepare submit intent, submit once, record receipt/observation, refresh, and repeat until no fitting row "
        "or an explicit safety/budget limit remains. One-submit-then-refresh is a safety boundary, not a one-submit-per-heartbeat cap. "
        "When fresh capability-known idle slots coexist with a positive portfolio deficit and no fillable committed candidate, do not "
        "wait by default: ask WorkflowGuard to dispatch one bounded replenish_experiment_portfolio action when the program claim remains "
        "unresolved, including when zero tracks are active. Before idea generation, commit the changed-basis replenishment_event with "
        "research_decision.py --replenishment --write; preserve any primary selection fingerprint and reuse the canonical evidence source. "
        "Do not otherwise regenerate/rescore the committed shortlist, repeat an unchanged replenishment fingerprint, tune a "
        "terminal-negative mechanism, replace 2-3-value-per-dataset parameter coverage with seeds, use seed as an HPO axis, exceed "
        "three unique seeds, or create work merely to occupy an idle GPU. Baseline calibration may overlap pilot-only scouts but "
        "cannot promote a claim. Freeze the ledger-selected parameter profile before method screening; after initial mechanism "
        "support, cross-dataset validation precedes dataset-group Stage-5 DEHB. "
    )
    if admission_scope == "global":
        clause += (
            "For admission_scope=global, surface fitting ready rows to the global dispatcher; this project monitor must not "
            "claim or physically submit them. "
        )
    else:
        clause += (
            "For admission_scope=project, when current user/autopilot policy authorizes launch, schedule and atomically claim the "
            "first deterministic fitting assignment, submit it through backend preflight, refresh resources, and recompute. "
        )
    clause += (
        "If nothing can launch, record the exact scientific, dependency, identity, budget, writer, or resource rejection before "
        f"updating this same heartbeat.\n{V3_END}"
    )
    base_prompt = strip_opportunity_scan_contract(prompt)
    return base_prompt + "\n\n" + clause


def build_prompt(
    project: str,
    plan: dict[str, Any],
    registry: dict[str, Any],
    queue: dict[str, Any],
    interval: int,
) -> str:
    """Build a fresh heartbeat prompt from the current monitor authority.

    Registry prompts can become stale when a heartbeat cadence is recomputed from
    a newer ETA artifact. Prefer an explicit plan prompt when present; otherwise
    synthesize the prompt from the current plan fields instead of reusing old
    job ids or old interval reasons.
    """

    policy = plan.get("check_interval_policy") if isinstance(plan.get("check_interval_policy"), dict) else {}
    scheduled = plan.get("scheduled_wakeup") if isinstance(plan.get("scheduled_wakeup"), dict) else {}
    job_id = str(plan.get("active_async_job_id") or scheduled.get("job_id") or "").strip()
    stage = str(plan.get("stage") or "experiment").strip()
    due_at = str(plan.get("next_check_at") or plan.get("next_check_after") or scheduled.get("due_at") or "").strip()
    reason = str(
        policy.get("reason")
        or plan.get("last_cadence_reason")
        or registry.get("last_cadence_reason")
        or "dynamic experiment monitor interval"
    ).strip()
    progress = str(plan.get("observed_progress") or plan.get("active_runs_summary") or "").strip()
    signal = str(plan.get("latest_runtime_signal") or plan.get("latest_poll_decision") or "").strip()
    queue_policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    admission_scope = str(queue_policy.get("admission_scope") or "project").strip().lower()
    queue_rows = [row for row in queue.get("rows", []) if isinstance(row, dict)]
    frontier_counts = {
        status: sum(1 for row in queue_rows if str(row.get("status") or "") == status)
        for status in ["ready", "planned", "submitting", "needs_sync", "running"]
    }

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
        f"poll_interval_minutes={interval}, interval_reason={reason}, admission_scope={admission_scope}, "
        f"frontier_ready={frontier_counts['ready']}, frontier_planned={frontier_counts['planned']}, "
        f"frontier_submitting={frontier_counts['submitting']}, frontier_needs_sync={frontier_counts['needs_sync']}, "
        f"frontier_running={frontier_counts['running']}. "
        "Recompute heartbeat interval from live progress, ETA, and stage boundaries on every resume; update this same heartbeat "
        "without creating duplicates. Do not submit PaperNexus graph imports and do not shut down any remote machine automatically."
    )
    if admission_scope == "global":
        prompt += (
            " Reconcile runtime and surface ready rows only; do not claim or submit them from this project monitor. "
            "Physical admission belongs to the global dispatcher using a current hashed first assignment."
        )
    return prompt


def continuation_reasons(queue: dict[str, Any], frontier: dict[str, Any]) -> list[str]:
    rows = [row for row in queue.get("rows", []) if isinstance(row, dict)]
    reasons: list[str] = []
    active = sorted({str(row.get("status") or "") for row in rows} & ACTIVE_QUEUE_STATUSES)
    if active:
        reasons.append("external_or_claimed_queue_work:" + ",".join(active))
    if any(str(row.get("status") or "") == "ready" for row in rows):
        reasons.append("ready_queue_work")
    if int(frontier.get("portfolio_fillable_count") or 0) > 0:
        reasons.append("fillable_portfolio_work")
    return reasons


def verify_readback(expectation: dict[str, Any], readback: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    expected_id = str(expectation.get("automation_id") or "").strip()
    observed_id = str(readback.get("id") or readback.get("automation_id") or "").strip()
    if expected_id and observed_id != expected_id:
        errors.append(f"automation id mismatch: expected {expected_id}, observed {observed_id or '<missing>'}")
    for key in ["name", "rrule"]:
        expected = expectation.get(key)
        if expected is not None and readback.get(key) != expected:
            errors.append(f"{key} mismatch: expected {expected!r}, observed {readback.get(key)!r}")
    expected_status = str(expectation.get("status") or "").upper()
    observed_status = str(readback.get("status") or "").upper()
    if expected_status and observed_status != expected_status:
        errors.append(f"status mismatch: expected {expected_status}, observed {observed_status or '<missing>'}")
    prompt = str(readback.get("prompt") or "")
    expected_prompt_sha256 = str(expectation.get("prompt_sha256") or "")
    if expected_prompt_sha256 and sha256_text(prompt) != expected_prompt_sha256:
        errors.append("prompt_sha256 mismatch")
    if expectation.get("heartbeat_contract_version") == 3 and prompt.count(V3_START) != 1:
        errors.append("readback must contain exactly one heartbeat v3 block")
    return {
        "ok": not errors,
        "errors": errors,
        "observed_prompt_sha256": sha256_text(prompt) if prompt else None,
        "observed_heartbeat_contract_count": prompt.count(V3_START),
    }


def build_payload(
    project: str,
    plan_rel: str,
    current_automation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = ar(project)
    plan = read_json(base / plan_rel, {})
    registry = read_json(base / "automation_registry.json", {})
    queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {})
    passport = read_json(base / "resources/PROJECT_EXECUTION_PASSPORT.json", {})
    missing: list[str] = []
    current_automation = current_automation if isinstance(current_automation, dict) else {}
    if not isinstance(plan, dict) or not plan:
        return {"ok": False, "status": "missing_plan", "missing": [plan_rel], "payload": None}
    if not isinstance(registry, dict):
        registry = {}
    if not isinstance(queue, dict):
        queue = {}

    reuse = plan.get("reuse_policy") if isinstance(plan.get("reuse_policy"), dict) else {}
    policy = plan.get("check_interval_policy") if isinstance(plan.get("check_interval_policy"), dict) else {}
    requested_action = str(reuse.get("action") or "").strip().lower()
    monitor_id = str(
        plan.get("monitor_id")
        or current_automation.get("id")
        or current_automation.get("automation_id")
        or registry.get("automation_id")
        or ""
    ).strip()
    current_id = str(current_automation.get("id") or current_automation.get("automation_id") or "").strip()
    if current_id and monitor_id and current_id != monitor_id:
        missing.append(f"current automation id {current_id} does not match monitor id {monitor_id}")
    selected_interval = policy.get("interval_minutes") or plan.get("poll_interval_minutes") or plan.get("interval_minutes")
    current_interval = rrule_interval(current_automation.get("rrule"))
    actual_interval = bounded_minutes(selected_interval or current_interval, current_interval or 5)
    desired_rrule = f"FREQ=MINUTELY;INTERVAL={actual_interval}"
    explicit_prompt, explicit_status = current_explicit_prompt(plan)
    queue_policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    admission_scope = str(queue_policy.get("admission_scope") or "project").strip().lower()
    frontier = frontier_state(project, queue)
    reasons = continuation_reasons(queue, frontier)
    action = "update" if requested_action in {"pause", "delete"} and reasons else requested_action
    current_prompt = str(current_automation.get("prompt") or "").strip()
    prompt = explicit_prompt or current_prompt or build_prompt(project, plan, registry, queue, actual_interval)
    prompt = append_opportunity_scan_contract(prompt, admission_scope, frontier, queue, passport)
    if explicit_prompt:
        prompt_source = f"{explicit_status}_with_mandatory_opportunity_scan"
    elif current_prompt:
        prompt_source = f"current_automation_readback_after_{explicit_status}_with_mandatory_opportunity_scan"
    else:
        prompt_source = f"synthesized_after_{explicit_status}_with_mandatory_opportunity_scan"
    name = (
        current_automation.get("name")
        or registry.get("automation_name")
        or registry.get("automation_key")
        or f"AutoResearch monitor {plan.get('run_id') or 'run'}"
    )

    for key, value in [("name", name), ("prompt", prompt)]:
        if not present(value):
            missing.append(key)
    if action in {"create", "update"} and not present(desired_rrule):
        missing.append("check_interval_policy.desired_rrule")
    if action in {"update", "pause", "delete"} and not present(monitor_id):
        missing.append("monitor_id for update/pause/delete")

    mode = "create"
    status = "ACTIVE"
    if action == "update":
        mode = "update"
    elif action == "pause":
        mode = "update"
        status = "PAUSED"
    elif action == "delete":
        mode = "delete"
    elif action in {"none", ""}:
        return {
            "ok": True,
            "status": "no_automation_action_required",
            "missing": [],
            "payload": None,
            "reason": "monitor plan has no active create/update/pause action",
        }

    elif action not in {"create", "update", "pause", "delete"}:
        return {
            "ok": False,
            "status": "unsupported_reuse_action",
            "missing": [],
            "payload": None,
            "reuse_action": action,
        }

    payload = {"mode": mode, "kind": "heartbeat", "destination": "thread", "name": name}
    if mode != "delete":
        payload.update({"prompt": prompt, "status": status})
    if mode == "update":
        payload["id"] = monitor_id
    elif mode == "delete":
        payload["id"] = monitor_id
    if status == "ACTIVE" and mode != "delete":
        payload["rrule"] = desired_rrule

    stored_plan_hash = str(plan.get("monitor_plan_semantic_sha256") or "")
    computed_plan_hash = monitor_plan_semantic_sha256(plan)
    return {
        "ok": not missing,
        "status": "ready" if not missing else "incomplete",
        "missing": missing,
        "payload": payload if not missing else None,
        "plan_path": plan_rel,
        "registry_path": "automation_registry.json",
        "reuse_action": requested_action,
        "effective_reuse_action": action,
        "pause_or_delete_overridden": action != requested_action,
        "continuation_reasons": reasons,
        "prompt_source": prompt_source,
        "prompt_sha256": sha256_text(prompt),
        "heartbeat_contract_version": 3,
        "heartbeat_contract_count": prompt.count(V3_START),
        "frontier": frontier,
        "project_passport_index_sha256": passport.get("index_semantic_sha256"),
        "readback_expectation": {
            "automation_id": monitor_id or None,
            "name": name,
            "status": status if mode != "delete" else "DELETED",
            "rrule": desired_rrule if status == "ACTIVE" and mode != "delete" else None,
            "prompt_sha256": sha256_text(prompt) if mode != "delete" else None,
            "heartbeat_contract_version": 3,
        },
        "monitor_plan_revision": plan.get("monitor_plan_revision"),
        "monitor_plan_semantic_sha256": computed_plan_hash,
        "monitor_plan_hash_valid": bool(stored_plan_hash) and stored_plan_hash == computed_plan_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", default="experiment/EXPERIMENT_MONITOR_PLAN.json")
    parser.add_argument("--current-automation", help="JSON readback used to preserve the current managed prompt/name/id")
    parser.add_argument("--expected-payload", help="Previously generated payload result used as immutable readback authority")
    parser.add_argument("--readback", help="JSON state captured after app mutation; mismatches fail closed")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", default="experiment/EXPERIMENT_MONITOR_AUTOMATION_PAYLOAD.json")
    args = parser.parse_args()
    current = read_json(Path(args.current_automation).expanduser().resolve(), {}) if args.current_automation else {}
    out = (
        read_json(Path(args.expected_payload).expanduser().resolve(), {})
        if args.expected_payload
        else build_payload(args.project, args.plan, current)
    )
    if not out:
        out = {"ok": False, "status": "missing_expected_payload", "payload": None}
    if args.readback and out.get("payload"):
        readback = read_json(Path(args.readback).expanduser().resolve(), {})
        verification = verify_readback(out.get("readback_expectation") or {}, readback)
        out["readback_verification"] = verification
        if not verification["ok"]:
            out["ok"] = False
            out["status"] = "readback_mismatch"
    if args.write:
        write_json(ar(args.project) / args.output, out)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
