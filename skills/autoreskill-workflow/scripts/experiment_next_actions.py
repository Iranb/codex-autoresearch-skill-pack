#!/usr/bin/env python3
"""Manage AutoResearch experiment next-action queues and wiki dashboards.

The project-local JSON queue is the planning authority. Rendered Markdown is a
human dashboard only; it never completes stages, promotes claims, or submits
jobs.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import itertools
import json
import math
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from parameter_transfer import (
    VALID_PROBE_KINDS,
    program_contract_binding,
    required_dataset_ids,
    stable_hash as parameter_stable_hash,
    validate_frozen_profile,
    validate_parameter_probe_rows,
    validate_parameter_transfer_contract,
)


DEFAULT_WIKI_ROOT = Path(
    os.environ.get(
        "AUTORESEARCH_WIKI_ROOT",
        str(Path.home() / "Documents" / "001-WIKI" / "mypaper"),
    )
).expanduser()
DEFAULT_GLOBAL_DASHBOARD = DEFAULT_WIKI_ROOT / "autoresearch/00-实验总控/active_experiment_next_actions.md"
QUEUE_REL = Path(".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json")
CONFIG_REL = Path(".autoreskill/experiment/EXPERIMENT_PLANNER_CONFIG.json")
AUTOPILOT_REL = Path(".autoreskill/autopilot_policy.json")
PROJECT_CONTROL_LEASE_REL = Path(".autoreskill/control/PROJECT_CONTROL_LEASE.json")

VALID_STATUSES = {
    "candidate",
    "ready",
    "planned",
    "submitting",
    "running",
    "needs_sync",
    "terminal_positive",
    "terminal_negative",
    "blocked",
    "dropped",
    "superseded",
}
VALID_ROLES = {
    "baseline_anchor",
    "single_innovation",
    "combo",
    "stability",
    "adapter_unblock",
    "monitor_sync",
    "negative_control",
    "parameter_probe",
    "baseline_calibration",
}
VALID_COMPARISONS = {
    "vs paper-reported baseline",
    "vs reproduced baseline",
    "vs matched reproduced baseline",
    "paper-report comparison not established",
}
VALID_LAUNCH_MODES = {"first_use", "repeated_variant", "monitor_only", "claim_promotion"}
REQUIRED_ROW_FIELDS = {"id", "priority", "status", "role", "dataset", "next_action", "updated_at"}
STRICT_LAUNCH_STATUSES = {"ready", "planned", "submitting", "running", "needs_sync"}
ACQUISITION_CLASSES = [
    "repair_validity",
    "resolve_competing_hypotheses",
    "falsify_core_mechanism",
    "close_required_claim",
    "confirm_generalization",
    "optimize_supported_mechanism",
    "resource_fill_diagnostic",
]
ACQUISITION_ORDER = {value: index for index, value in enumerate(ACQUISITION_CLASSES)}
OUTCOME_ROUTE_KEYS = ["positive", "negative", "inconclusive", "invalid"]
RAPID_OUTCOME_ROUTE_KEYS = [
    "valid_positive_candidate",
    "valid_negative",
    "valid_inconclusive",
    "infrastructure_failure",
    "implementation_failure",
    "protocol_invalid",
]
EXECUTION_ROUTES = {"local", "ssh", "bjtu_hpc"}
AVAILABLE_POOL_STATUSES = {"", "available", "idle", "ready", "partial"}
BLOCKED_POOL_STATUSES = {
    "blocked",
    "blocked_pending",
    "pending",
    "queued",
    "full",
    "stale",
    "unreachable",
    "auth_invalid",
    "disabled",
    "blocked_shared_limit",
}
VALID_EVIDENCE_TIERS = {"pilot_only", "claim_eligible"}
VALID_CLAIM_ROLES = {
    "method_candidate",
    "method_control",
    "diagnostic_only",
    "baseline_support",
    "protocol_support",
}
EXTERNAL_CAMPAIGN_REF = "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LAUNCH_IDENTITY_FIELDS = [
    "selected_idea_id",
    "track_id",
    "branch_id",
    "launch_identity_hash",
    "track_plan_ref",
    "causal_signature",
    "decision_class",
    "why_now",
    "claim_target",
    "hypothesis_prediction",
    "falsifier",
    "expected_decision_change",
    "baseline_anchor",
    "comparison_source",
    "protocol",
    "metric_policy_ref",
    "resource_request",
    "mutex_group",
    "parallel_safe",
    "evidence_paths",
]
TERMINAL_MUTATION_STATUSES = {
    "terminal_positive",
    "terminal_negative",
    "needs_sync",
    "blocked",
    "dropped",
    "superseded",
}
STATUS_ORDER = {
    "ready": 0,
    "planned": 1,
    "submitting": 2,
    "needs_sync": 3,
    "running": 4,
    "candidate": 5,
    "blocked": 6,
    "terminal_positive": 7,
    "terminal_negative": 8,
    "superseded": 9,
    "dropped": 10,
}

PORTFOLIO_TERMINAL_LIFECYCLES = {
    "parked",
    "killed",
    "retired",
    "refuted",
    "terminal",
    "terminal_positive",
    "terminal_negative",
    "dropped",
    "superseded",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, errors: list[str] | None = None) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        if errors is not None:
            errors.append(f"invalid JSON in {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        if errors is not None:
            errors.append(f"JSON root must be an object in {path}")
        return {}
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@contextmanager
def queue_lock(queue_path: Path) -> Any:
    lock_path = queue_path.with_suffix(queue_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def project_root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def project_slug(project: Path) -> str:
    return project.name or "autoreskill-project"


def infer_direction(project: Path) -> str:
    text = str(project)
    slug = project_slug(project)
    ordered = [
        ("ContinueGCD", "ContinueGCD"),
        ("DomainGCD", "DomainGCD"),
        ("GCD2OWR", "GCD2OWR"),
        ("03-GCD", "GCD"),
        ("GCD", "GCD"),
        ("SAGE", "SAGE"),
    ]
    for needle, direction in ordered:
        if needle in text or needle in slug:
            return direction
    clean = re.sub(r"^\d+-", "", slug).strip()
    return clean or slug


def direction_experiment_dir(wiki_root: Path, direction: str) -> Path:
    root = wiki_root / direction
    numbered = root / "03-创新点"
    legacy = root / "创新点"
    if numbered.exists():
        return numbered
    if legacy.exists():
        return legacy
    return numbered


def default_project_dashboard(project: Path, wiki_root: Path, direction: str) -> Path:
    return direction_experiment_dir(wiki_root, direction) / f"AutoResearch-{project_slug(project)}" / "NEXT_EXPERIMENT_ACTIONS.md"


def load_autopilot_config(project: Path, errors: list[str] | None = None) -> dict[str, Any]:
    autopilot = read_json(project / AUTOPILOT_REL, errors)
    config = autopilot.get("experiment_next_actions")
    return config if isinstance(config, dict) else {}


def merged_config(
    project: Path,
    direction_arg: str | None = None,
    wiki_root_arg: str | None = None,
    wiki_path_arg: str | None = None,
    global_path_arg: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    existing = read_json(project / CONFIG_REL, errors)
    autopilot = load_autopilot_config(project, errors)

    wiki_root = Path(
        str(
            wiki_root_arg
            or existing.get("wiki_root")
            or autopilot.get("wiki_root")
            or DEFAULT_WIKI_ROOT
        )
    ).expanduser()
    direction = str(direction_arg or existing.get("direction") or autopilot.get("direction") or infer_direction(project))
    wiki_path_value = wiki_path_arg or existing.get("project_dashboard_path") or autopilot.get("project_dashboard_path")
    project_dashboard = Path(str(wiki_path_value)).expanduser() if wiki_path_value else default_project_dashboard(project, wiki_root, direction)
    global_value = global_path_arg or existing.get("global_dashboard_path") or autopilot.get("global_dashboard_path")
    global_dashboard = Path(str(global_value)).expanduser() if global_value else DEFAULT_GLOBAL_DASHBOARD

    return {
        "schema_version": 1,
        "project_root": str(project),
        "project_slug": project_slug(project),
        "direction": direction,
        "wiki_root": str(wiki_root),
        "project_dashboard_path": str(project_dashboard),
        "global_dashboard_path": str(global_dashboard),
    }


def default_queue(project: Path, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "queue_revision": 0,
        "updated_at": now_iso(),
        "project_root": str(project),
        "project_slug": project_slug(project),
        "direction": config["direction"],
        "wiki": {
            "wiki_root": config["wiki_root"],
            "project_dashboard_path": config["project_dashboard_path"],
            "global_dashboard_path": config["global_dashboard_path"],
        },
        "policy": {
            "max_random_seed_count": 3,
            "target_dataset_count_min": 2,
            "max_active_combo_candidates_per_dataset": 3,
            "single_innovation_multi_dataset_first": True,
            "combo_requires_effective_components": True,
            "parallel_launches_enabled": True,
            "parallelism_mode": "elastic_bounded",
            "max_new_launches_per_cycle": "auto",
            "absolute_max_new_launches_per_cycle": 16,
            "max_gpu_slots_in_flight": None,
            "max_gpu_hours_in_flight": None,
            "portfolio_capacity_target": 4,
            "method_portfolio_target": 2,
            "portfolio_gpu_hour_budget": None,
            "ready_frontier_multiplier": 2,
            "max_ready_frontier_rows": 32,
            "pending_scope": "resource_pool",
            "admission_scope": "project",
            "require_resource_fit_before_wait": True,
            "acquisition_class_order": ACQUISITION_CLASSES,
            "default_lease_minutes": 30,
            "comparison_labels": sorted(VALID_COMPARISONS),
            "update_triggers": [
                "terminal_result",
                "first_usable_metric",
                "failure_or_crash",
                "user_objective_change",
                "explicit_queue_maintenance",
            ],
            "planning_only": True,
            "wiki_is_rendered_view_only": True,
        },
        "rows": [],
        "decision_log": [
            {
                "timestamp": now_iso(),
                "decision": "initialized experiment next-action queue",
                "rationale": "Create recoverable planning state without changing stage authority.",
                "evidence_paths": [],
            }
        ],
    }


def load_queue(project: Path, errors: list[str] | None = None) -> dict[str, Any]:
    return read_json(project / QUEUE_REL, errors)


def truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def row_blocker_present(row: dict[str, Any]) -> bool:
    blocker = row.get("blocker")
    if blocker is None:
        return False
    if isinstance(blocker, str):
        return bool(blocker.strip())
    if isinstance(blocker, (list, tuple, set, dict)):
        return bool(blocker)
    return True


def numeric(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def decision_target_refs(row: dict[str, Any]) -> list[str]:
    return sorted(set(as_str_list(row.get("decision_target_refs"))))


def estimated_gpu_hours(row: dict[str, Any]) -> float | None:
    request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    value = row.get("estimated_gpu_hours")
    if value is None:
        value = request.get("estimated_gpu_hours")
    parsed = numeric(value, -1.0)
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def requested_gpu_count(row: dict[str, Any]) -> int:
    request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    parsed = numeric(request.get("gpu_count"), 1.0)
    if parsed < 1 or not float(parsed).is_integer():
        return 1
    return int(parsed)


def row_priority(row: dict[str, Any]) -> tuple[int, float, float, float, int, str]:
    raw = row.get("priority", 9999)
    priority = numeric(raw, 9999.0)
    status = str(row.get("status") or "")
    decision_class = str(row.get("decision_class") or "")
    if str(row.get("role") or "") == "monitor_sync" and not decision_class:
        decision_class = "repair_validity"
    impact = max(1, len(decision_target_refs(row)))
    cost_value = estimated_gpu_hours(row)
    cost = cost_value if cost_value is not None else numeric(row.get("estimated_cost"), 9999.0)
    return (
        ACQUISITION_ORDER.get(decision_class, len(ACQUISITION_CLASSES)),
        -impact,
        cost,
        priority,
        STATUS_ORDER.get(status, 99),
        str(row.get("id") or ""),
    )


def positive_int(value: Any, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            return default
        parsed = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\+?\d+", value.strip()):
        parsed = int(value)
    else:
        return default
    return parsed if parsed > 0 else default


def nonnegative_int(value: Any, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            return default
        parsed = int(value)
    elif isinstance(value, str) and re.fullmatch(r"\+?\d+", value.strip()):
        parsed = int(value)
    else:
        return default
    return parsed if parsed >= 0 else default


def dependency_rejection(row: dict[str, Any], rows_by_id: dict[str, dict[str, Any]]) -> str | None:
    terminal = {"terminal_positive", "terminal_negative", "superseded"}
    for ref in as_str_list(row.get("depends_on_rows")):
        source = rows_by_id.get(ref)
        if source is None:
            return f"missing dependency row {ref}"
        if str(source.get("status") or "") not in terminal:
            return f"dependency row {ref} is not terminal"
    unlock = row.get("unlock_rules") if isinstance(row.get("unlock_rules"), dict) else {}
    for ref in as_str_list(unlock.get("requires_positive_rows")):
        source = rows_by_id.get(ref)
        if source is None or str(source.get("status") or "") != "terminal_positive":
            return f"positive gate {ref} is not terminal_positive"
    for ref in as_str_list(unlock.get("requires_nonnegative_rows")):
        source = rows_by_id.get(ref)
        if source is None or str(source.get("status") or "") not in {"terminal_positive", "superseded"}:
            return f"nonnegative gate {ref} lacks supported evidence"
    return None


def pool_launch_slots(pool: dict[str, Any]) -> int:
    for key in ("launch_slots", "available_gpu_slots", "idle_gpu_count", "free_gpu_count"):
        if key not in pool or pool.get(key) is None:
            continue
        parsed = nonnegative_int(pool.get(key))
        return parsed if parsed is not None else 0
    return 0


def pool_free_vram_mb(pool: dict[str, Any]) -> float | None:
    for key in ("free_vram_mb", "vram_free_mb", "min_free_mib", "free_memory_mib"):
        if pool.get(key) is None:
            continue
        parsed = numeric(pool.get(key), -1.0)
        if parsed >= 0:
            return parsed
    return None


def resource_pools(queue: dict[str, Any]) -> tuple[list[dict[str, Any]], bool, bool]:
    snapshot = queue.get("resource_snapshot") if isinstance(queue.get("resource_snapshot"), dict) else {}
    raw_pools = snapshot.get("pools")
    if isinstance(raw_pools, list) and raw_pools:
        pools = [dict(item) for item in raw_pools if isinstance(item, dict)]
        return pools, True, False
    policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    for key in ("available_gpu_slots", "idle_gpu_count", "free_gpu_count", "launch_slots"):
        value = snapshot.get(key) if key in snapshot else policy.get(key)
        if value is None:
            continue
        slots = nonnegative_int(value, 0) or 0
        return (
            [
                {
                    "pool_id": "aggregate-compatibility-pool",
                    "status": "available" if slots > 0 else "full",
                    "launch_slots": slots,
                    "fit_confidence": "aggregate_unverified",
                }
            ],
            False,
            False,
        )
    return [], False, True


def requested_backends(request: dict[str, Any]) -> set[str]:
    values = as_str_list(request.get("backend_allowlist"))
    if not values:
        values = as_str_list(request.get("backend"))
    return {value.strip().lower() for value in values if value.strip() and value.strip().lower() not in {"any", "auto"}}


def row_execution_route(row: dict[str, Any]) -> str:
    external = row.get("external_identity") if isinstance(row.get("external_identity"), dict) else {}
    request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    return str(
        row.get("execution_route")
        or external.get("execution_route")
        or request.get("execution_route")
        or ""
    ).strip().lower()


def canonical_outcome_routes(value: Any) -> dict[str, Any]:
    """Project either canonical four-way or rapid six-way routes without losing invalid subroutes."""
    if not isinstance(value, dict):
        return {}
    if all(truthy(value.get(key)) for key in OUTCOME_ROUTE_KEYS):
        return {key: value.get(key) for key in OUTCOME_ROUTE_KEYS}
    if all(truthy(value.get(key)) for key in RAPID_OUTCOME_ROUTE_KEYS):
        return {
            "positive": value.get("valid_positive_candidate"),
            "negative": value.get("valid_negative"),
            "inconclusive": value.get("valid_inconclusive"),
            "invalid": {
                "infrastructure_failure": value.get("infrastructure_failure"),
                "implementation_failure": value.get("implementation_failure"),
                "protocol_invalid": value.get("protocol_invalid"),
            },
        }
    return dict(value)


def pool_fit_rejection(
    row: dict[str, Any],
    pool: dict[str, Any],
    remaining_slots: int,
    shared_blocked_refs: set[str],
    detailed_pools: bool,
) -> str | None:
    status = str(pool.get("status") or "").strip().lower()
    if status in BLOCKED_POOL_STATUSES or status not in AVAILABLE_POOL_STATUSES:
        return f"pool status {status or 'unknown'} is not available"
    shared_ref = str(pool.get("shared_limit_ref") or "").strip()
    if shared_ref and shared_ref in shared_blocked_refs:
        return f"shared limit {shared_ref} is blocked"

    request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    route = row_execution_route(row)
    request_backend = str(request.get("backend") or "").strip().lower()
    if route and request_backend != route:
        return f"resource_request.backend {request_backend or '<missing>'} does not exactly match execution_route {route}"
    gpu_count = requested_gpu_count(row)
    if gpu_count > remaining_slots:
        return f"needs {gpu_count} GPU slots but pool has {remaining_slots}"

    pool_id = str(pool.get("pool_id") or "").strip()
    requested_pool = str(request.get("pool_id") or request.get("resource_pool_id") or "").strip()
    if requested_pool and pool_id != requested_pool:
        return f"pool_id {pool_id or '<missing>'} does not match {requested_pool}"

    aggregate = not detailed_pools
    backends = requested_backends(request)
    pool_backend = str(pool.get("backend") or "").strip().lower()
    pool_route = str(pool.get("execution_route") or pool_backend).strip().lower()
    if route and pool_route != route and not aggregate:
        return f"pool execution_route {pool_route or '<missing>'} does not match {route}"
    if backends and pool_backend not in backends and not aggregate:
        return f"backend {pool_backend or '<missing>'} is not in {sorted(backends)}"

    for request_key, pool_keys in (
        ("host_ref", ("host_ref", "host")),
        ("host", ("host_ref", "host")),
        ("account_ref", ("account_ref", "account")),
        ("account", ("account_ref", "account")),
    ):
        expected = str(request.get(request_key) or "").strip()
        if not expected:
            continue
        observed = {str(pool.get(key) or "").strip() for key in pool_keys}
        if expected not in observed and not aggregate:
            return f"{request_key} {expected} does not match pool"

    min_vram = None
    for key in ("min_vram_mb", "min_free_mib", "min_free_mb"):
        if request.get(key) is not None:
            min_vram = numeric(request.get(key), -1.0)
            break
    free_vram = pool_free_vram_mb(pool)
    if min_vram is not None and min_vram >= 0:
        if free_vram is None and detailed_pools:
            return "pool does not report free VRAM"
        if free_vram is not None and free_vram < min_vram:
            return f"needs {min_vram:g} MiB but pool reports {free_vram:g} MiB"

    models = {value.lower() for value in as_str_list(request.get("gpu_model_allowlist"))}
    if not models:
        models = {value.lower() for value in as_str_list(request.get("gpu_model"))}
    pool_model = str(pool.get("gpu_model") or "").strip().lower()
    if models and pool_model not in models and not aggregate:
        return f"GPU model {pool_model or '<missing>'} is not in {sorted(models)}"

    required_capabilities = {
        value.strip().lower()
        for value in as_str_list(request.get("required_capabilities"))
        if value.strip()
    }
    pool_capabilities = {
        value.strip().lower()
        for value in as_str_list(pool.get("capabilities"))
        if value.strip()
    }
    missing = sorted(required_capabilities - pool_capabilities)
    if missing and not aggregate:
        return f"missing capabilities {missing}"

    execution_profile_sha256 = str(row.get("execution_profile_sha256") or "").strip().lower()
    if pool.get("capability_enforced") is True and not aggregate:
        if not SHA256_RE.fullmatch(execution_profile_sha256):
            return "row lacks a valid execution_profile_sha256 for a capability-enforced pool"
        satisfied_profiles = {
            value.strip().lower()
            for value in as_str_list(
                pool.get("execution_profile_sha256s")
                or pool.get("satisfied_execution_profile_sha256s")
            )
            if value.strip()
        }
        if execution_profile_sha256 not in satisfied_profiles:
            return "pool capability passport does not satisfy the row execution profile"

    exclusive = str(
        request.get("exclusive_resource_id")
        or request.get("gpu_uuid")
        or request.get("gpu_id")
        or request.get("device")
        or ""
    ).strip()
    if exclusive and detailed_pools:
        pool_resources = {
            str(value)
            for value in as_str_list(pool.get("resource_ids"))
            + as_str_list(pool.get("gpu_uuids"))
            + as_str_list(pool.get("gpu_ids"))
        }
        if pool_resources and exclusive not in pool_resources:
            return f"exclusive resource {exclusive} is absent from pool"
    return None


def select_launch_batch(queue: dict[str, Any], project: Path | None = None) -> dict[str, Any]:
    """Return a deterministic, read-only launch proposal for one queue snapshot."""

    validation = validate_queue(queue, project)
    if not validation["ok"]:
        return {
            "ok": False,
            "reason": "queue_validation_failed",
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "candidate_count": 0,
            "selected_count": 0,
            "selected_row_ids": [],
            "assignments": [],
            "rejected": [],
        }

    policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    rows = [item for item in queue.get("rows", []) if isinstance(item, dict)]
    rows_by_id = {str(row.get("id") or ""): row for row in rows if str(row.get("id") or "").strip()}
    active_statuses = {"planned", "submitting", "running", "needs_sync"}
    active_rows = [row for row in rows if str(row.get("status") or "") in active_statuses]
    active_mutexes = {
        str(row.get("mutex_group") or "").strip()
        for row in active_rows
        if str(row.get("mutex_group") or "").strip()
    }
    active_identities = {
        str(row.get("launch_identity_hash") or "").strip()
        for row in active_rows
        if str(row.get("launch_identity_hash") or "").strip()
    }
    active_slots = sum(requested_gpu_count(row) for row in active_rows)
    active_hours_values = [estimated_gpu_hours(row) for row in active_rows]
    active_hours = sum(value for value in active_hours_values if value is not None)
    active_hours_unknown = any(value is None for value in active_hours_values)

    max_slots = positive_int(policy.get("max_gpu_slots_in_flight"))
    if max_slots is None:
        max_slots = positive_int(policy.get("max_parallel_gpu_runs"))
    remaining_slot_budget = max(0, max_slots - active_slots) if max_slots is not None else None
    max_hours_raw = policy.get("max_gpu_hours_in_flight")
    max_hours = numeric(max_hours_raw, -1.0) if max_hours_raw is not None else None
    if max_hours is not None and max_hours < 0:
        max_hours = None
    remaining_hour_budget = None if max_hours is None else max(0.0, max_hours - active_hours)

    absolute_cap = positive_int(policy.get("absolute_max_new_launches_per_cycle"), 16) or 16
    max_new_raw = policy.get("max_new_launches_per_cycle", "auto")
    max_new_override = positive_int(max_new_raw)
    batch_cap = min(absolute_cap, max_new_override) if max_new_override is not None else absolute_cap

    rejected: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    for row in sorted(rows, key=row_priority):
        row_id = str(row.get("id") or "<row>")
        status = str(row.get("status") or "")
        role = str(row.get("role") or "")
        launch_mode = str(row.get("launch_mode") or "")
        if status != "ready":
            continue
        if role == "monitor_sync" or launch_mode == "monitor_only":
            continue
        if row_blocker_present(row):
            rejected.append({"row_id": row_id, "reason": "blocker_present"})
            continue
        if truthy(row.get("lease_owner")):
            rejected.append({"row_id": row_id, "reason": "ready_row_has_lease"})
            continue
        dependency_error = dependency_rejection(row, rows_by_id)
        if dependency_error:
            rejected.append({"row_id": row_id, "reason": dependency_error})
            continue
        identity = str(row.get("launch_identity_hash") or "").strip()
        if identity and identity in active_identities:
            rejected.append({"row_id": row_id, "reason": "duplicate_active_launch_identity"})
            continue
        candidates.append(row)

    if policy.get("parallel_launches_enabled", True) is False:
        return {
            "ok": True,
            "reason": "parallel_launches_disabled",
            "queue_revision": queue.get("queue_revision"),
            "candidate_count": len(candidates),
            "selected_count": 0,
            "selected_row_ids": [],
            "assignments": [],
            "rejected": rejected,
            "warnings": validation["warnings"],
            "requires_resource_refresh": False,
        }

    snapshot = queue.get("resource_snapshot") if isinstance(queue.get("resource_snapshot"), dict) else {}
    snapshot_status = str(snapshot.get("status") or "").strip().lower()
    snapshot_stale = (
        snapshot.get("stale") is True
        or snapshot.get("fresh") is False
        or snapshot_status in {"stale", "expired"}
    )
    pools, detailed_pools, snapshot_missing = resource_pools(queue)
    shared_blocked_refs = {
        str(pool.get("shared_limit_ref") or "").strip()
        for pool in pools
        if str(pool.get("shared_limit_ref") or "").strip()
        and (
            pool.get("shared_limit_blocked") is True
            or str(pool.get("blocked_scope") or "").strip().lower() == "shared_limit"
            or str(pool.get("status") or "").strip().lower() == "blocked_shared_limit"
        )
    }
    remaining_by_pool = {
        str(pool.get("pool_id") or f"pool-{index}"): pool_launch_slots(pool)
        for index, pool in enumerate(pools)
    }
    total_idle_slots = sum(remaining_by_pool.values())
    warnings = list(validation["warnings"])
    if max_hours is not None and active_hours_unknown:
        warnings.append("max_gpu_hours_in_flight is configured but an active row lacks estimated_gpu_hours; no new GPU-hour margin is trusted")
        remaining_hour_budget = 0.0

    if snapshot_missing or snapshot_stale:
        return {
            "ok": True,
            "reason": (
                "resource_snapshot_stale"
                if candidates and snapshot_stale
                else "resource_snapshot_required"
                if candidates
                else "no_admissible_ready_rows"
            ),
            "queue_revision": queue.get("queue_revision"),
            "candidate_count": len(candidates),
            "selected_count": 0,
            "selected_row_ids": [],
            "assignments": [],
            "rejected": rejected,
            "warnings": warnings,
            "requires_resource_refresh": bool(candidates),
            "limits": {
                "batch_cap": batch_cap,
                "active_gpu_slots": active_slots,
                "remaining_gpu_slots_in_flight": remaining_slot_budget,
                "remaining_gpu_hours_in_flight": remaining_hour_budget,
            },
        }

    selected: list[dict[str, Any]] = []
    selected_mutexes: set[str] = set()
    selected_identities: set[str] = set()
    selected_slots = 0
    selected_hours = 0.0
    serial_selected = False
    for candidate_index, row in enumerate(candidates):
        row_id = str(row.get("id") or "<row>")
        if len(selected) >= batch_cap:
            rejected.append({"row_id": row_id, "reason": "new_launch_safety_cap_reached"})
            continue
        gpu_count = requested_gpu_count(row)
        if remaining_slot_budget is not None and selected_slots + gpu_count > remaining_slot_budget:
            rejected.append({"row_id": row_id, "reason": "max_gpu_slots_in_flight_reached"})
            continue
        row_hours = estimated_gpu_hours(row)
        if remaining_hour_budget is not None:
            if row_hours is None:
                rejected.append({"row_id": row_id, "reason": "estimated_gpu_hours_required_by_budget"})
                continue
            if selected_hours + row_hours > remaining_hour_budget:
                rejected.append({"row_id": row_id, "reason": "max_gpu_hours_in_flight_reached"})
                continue

        serial = row.get("parallel_safe") is False or row.get("requires_serial") is True
        if serial and (active_rows or selected):
            rejected.append({"row_id": row_id, "reason": "serial_row_requires_empty_project_execution_set"})
            continue
        if serial_selected:
            rejected.append({"row_id": row_id, "reason": "selected_serial_row_blocks_parallel_launch"})
            continue
        mutex = str(row.get("mutex_group") or "").strip()
        if mutex and (mutex in active_mutexes or mutex in selected_mutexes):
            rejected.append({"row_id": row_id, "reason": f"mutex_group {mutex} is active"})
            continue
        identity = str(row.get("launch_identity_hash") or "").strip()
        if identity and identity in selected_identities:
            rejected.append({"row_id": row_id, "reason": "duplicate_selected_launch_identity"})
            continue

        fitting: list[tuple[tuple[int, float, float, float, str], str, dict[str, Any]]] = []
        fit_reasons: list[str] = []
        for index, pool in enumerate(pools):
            pool_id = str(pool.get("pool_id") or f"pool-{index}")
            remaining = remaining_by_pool.get(pool_id, 0)
            reason = pool_fit_rejection(row, pool, remaining, shared_blocked_refs, detailed_pools)
            if reason:
                fit_reasons.append(f"{pool_id}: {reason}")
                continue
            free_vram = pool_free_vram_mb(pool)
            request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
            min_vram = numeric(
                request.get("min_vram_mb", request.get("min_free_mib", request.get("min_free_mb"))),
                0.0,
            )
            vram_slack = (free_vram - min_vram) if free_vram is not None else float("inf")
            simulated_remaining = dict(remaining_by_pool)
            simulated_remaining[pool_id] = remaining - gpu_count
            future_unplaceable = 0
            future_scarcity = 0.0
            remaining_batch_rows = max(0, batch_cap - len(selected) - 1)
            for future_row in candidates[candidate_index + 1 : candidate_index + 1 + remaining_batch_rows]:
                future_fit_count = 0
                for future_index, future_pool in enumerate(pools):
                    future_pool_id = str(future_pool.get("pool_id") or f"pool-{future_index}")
                    future_reason = pool_fit_rejection(
                        future_row,
                        future_pool,
                        simulated_remaining.get(future_pool_id, 0),
                        shared_blocked_refs,
                        detailed_pools,
                    )
                    if future_reason is None:
                        future_fit_count += 1
                if future_fit_count == 0:
                    future_unplaceable += 1
                else:
                    future_scarcity += requested_gpu_count(future_row) / future_fit_count
            fitting.append(
                (
                    (future_unplaceable, future_scarcity, remaining - gpu_count, vram_slack, pool_id),
                    pool_id,
                    pool,
                )
            )
        if not fitting:
            reason = "no_compatible_resource_pool"
            if fit_reasons:
                reason += ": " + "; ".join(fit_reasons[:3])
            rejected.append({"row_id": row_id, "reason": reason})
            continue

        _, pool_id, pool = min(fitting, key=lambda item: item[0])
        remaining_by_pool[pool_id] -= gpu_count
        selected_slots += gpu_count
        if row_hours is not None:
            selected_hours += row_hours
        if mutex:
            selected_mutexes.add(mutex)
        if identity:
            selected_identities.add(identity)
        if serial:
            serial_selected = True
        selected.append(
            {
                "row_id": row_id,
                "pool_id": pool_id,
                "backend": pool.get("backend"),
                "account_ref": pool.get("account_ref") or pool.get("account"),
                "host_ref": pool.get("host_ref") or pool.get("host"),
                "gpu_count": gpu_count,
                "decision_class": row.get("decision_class"),
                "decision_target_refs": decision_target_refs(row),
                "estimated_gpu_hours": row_hours,
                "fit_confidence": pool.get("fit_confidence") or ("verified_snapshot" if detailed_pools else "aggregate_unverified"),
                "requires_fresh_backend_preflight": True,
            }
        )

    selected_ids = [item["row_id"] for item in selected]
    selected_gpu_slots = sum(int(item["gpu_count"]) for item in selected)
    if total_idle_slots > selected_gpu_slots and len(candidates) <= len(selected):
        warnings.append(
            "underfilled_ready_frontier: compatible idle capacity remains but no additional scientifically admissible ready row exists; do not invent GPU-fill work"
        )
    stale_pool_present = any(str(pool.get("status") or "").strip().lower() in {"stale", "expired"} for pool in pools)
    requires_resource_refresh = bool(candidates and not selected and stale_pool_present)
    reason = (
        "selected"
        if selected
        else "no_admissible_ready_rows"
        if not candidates
        else "resource_snapshot_stale"
        if requires_resource_refresh
        else "no_compatible_or_budgeted_capacity"
    )
    return {
        "ok": True,
        "reason": reason,
        "queue_revision": queue.get("queue_revision"),
        "parallelism_mode": policy.get("parallelism_mode", "legacy"),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "selected_row_ids": selected_ids,
        "assignments": selected,
        "rejected": rejected,
        "warnings": warnings,
        "requires_resource_refresh": requires_resource_refresh,
        "resource_snapshot": {
            "detailed_pools": detailed_pools,
            "pool_count": len(pools),
            "idle_gpu_slots": total_idle_slots,
            "remaining_gpu_slots": sum(remaining_by_pool.values()),
            "blocked_shared_limit_refs": sorted(shared_blocked_refs),
        },
        "limits": {
            "batch_cap": batch_cap,
            "active_gpu_slots": active_slots,
            "selected_gpu_slots": selected_gpu_slots,
            "remaining_gpu_slots_in_flight": remaining_slot_budget,
            "active_estimated_gpu_hours": active_hours,
            "selected_estimated_gpu_hours": selected_hours,
            "remaining_gpu_hours_in_flight": remaining_hour_budget,
        },
    }


def admitted_matrix_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = {
        "selected_primary",
        "alternate_track",
        "risk_repair_track",
        "advance_with_constraints",
        "alternate",
    }
    terminal = {"parked", "killed", "retired", "refuted", "terminal"}
    out: list[dict[str, Any]] = []
    rows = payload_rows(matrix)
    for row in rows:
        lifecycle = str(row.get("idea_lifecycle_status") or "").strip().lower()
        role = str(row.get("track_role") or "").strip().lower()
        belief = str((row.get("hypothesis_contract") or {}).get("belief_state") or "").strip().lower()
        legacy_primary = matrix.get("schema_version") == 2 and (
            row.get("selected_for_review") is True
            or role == "primary"
            or (
                len(rows) == 1
                and role not in {"alternate", "risk_repair"}
                and lifecycle not in {"alternate_track", "risk_repair_track"}
            )
        )
        if belief in terminal or lifecycle in terminal:
            continue
        if lifecycle in allowed or legacy_primary:
            out.append(row)
    return out


def scorecard_rows(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["rows", "ideas", "scores", "scorecard"]:
        value = scorecard.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def idea_pool_rows(pool: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["ideas", "rows", "candidates"]:
        value = pool.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def shortlist_ids(scorecard: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ["shortlisted_idea_ids", "top_track_recommendations", "top_recommendations"]:
        value = scorecard.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            idea_id = item.get("idea_id") or item.get("id") if isinstance(item, dict) else item
            normalized = str(idea_id or "").strip()
            if normalized and normalized not in out:
                out.append(normalized)
    return out


def normalized_causal_signature(*rows: dict[str, Any]) -> str:
    for row in rows:
        if not isinstance(row, dict):
            continue
        contract = row.get("hypothesis_contract") if isinstance(row.get("hypothesis_contract"), dict) else {}
        explicit = row.get("causal_signature") or contract.get("causal_signature")
        if truthy(explicit):
            return re.sub(r"[^a-z0-9]+", " ", str(explicit).strip().lower()).strip()
        values = [
            row.get("intervention") or contract.get("intervention"),
            row.get("mechanism") or contract.get("mechanism"),
            row.get("predicted_pattern") or contract.get("predicted_pattern"),
        ]
        if all(truthy(value) for value in values):
            return " | ".join(
                re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()
                for value in values
            )
    return ""


def candidate_gpu_hours(row: dict[str, Any], idea: dict[str, Any]) -> float | None:
    track_spec = idea.get("track_seed_spec") if isinstance(idea.get("track_seed_spec"), dict) else {}
    for value in [
        row.get("estimated_falsifier_gpu_hours"),
        row.get("estimated_gpu_hours"),
        row.get("minimum_pilot_gpu_hours"),
        idea.get("estimated_falsifier_gpu_hours"),
        idea.get("estimated_gpu_hours"),
        track_spec.get("estimated_falsifier_gpu_hours"),
        track_spec.get("estimated_gpu_hours"),
    ]:
        parsed = numeric(value, math.nan)
        if math.isfinite(parsed) and parsed > 0:
            return parsed
    return None


def candidate_decision_targets(row: dict[str, Any], idea: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in [row, idea]:
        for key in ["unique_decision_targets", "decision_target_refs", "competing_hypotheses_resolved"]:
            for value in as_str_list(source.get(key)):
                if value not in values:
                    values.append(value)
        scalar = source.get("decision_target") or source.get("claim_target")
        if truthy(scalar) and str(scalar) not in values:
            values.append(str(scalar))
    return values


def portfolio_ranking_tuple(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        0 if candidate.get("changes_core_claim") is True else 1,
        -int(candidate.get("competing_hypotheses_resolved_count") or 0),
        -float(candidate.get("validation_density") or 0.0),
        float(candidate.get("estimated_falsifier_gpu_hours") or math.inf),
        -int(candidate.get("reusable_invariant_count") or 0),
        int(candidate.get("reviewer_risk_count") or 0),
        str(candidate.get("idea_id") or ""),
    )


def portfolio_status(queue: dict[str, Any], matrix: dict[str, Any], project: Path | None) -> dict[str, Any]:
    """Return deterministic shortlist supply independently from launch-row demand."""

    policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    capacity_target = positive_int(policy.get("portfolio_capacity_target"), 4) or 4
    capacity_target = min(4, capacity_target)
    scorecard: dict[str, Any] = {}
    pool: dict[str, Any] = {}
    ledger: dict[str, Any] = {}
    seeds: dict[str, Any] = {}
    program: dict[str, Any] = {}
    if project is not None:
        scorecard = read_json(project / ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json")
        pool = read_json(project / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json")
        ledger = read_json(project / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json")
        seeds = read_json(project / ".autoreskill/ideation/IDEA_TRACK_SEEDS.json")
        program = read_json(project / ".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json")
    enforcement_mode = str(program.get("enforcement_mode") or "legacy").strip().lower()
    rows = [row for row in queue.get("rows", []) if isinstance(row, dict)]
    active_statuses = {"ready", "planned", "submitting", "needs_sync", "running"}
    active_all_track_ids = {
        str(row.get("track_id") or "").strip()
        for row in rows
        if str(row.get("status") or "") in active_statuses
        and str(row.get("track_id") or "").strip()
    }
    active_hypothesis_track_ids = {
        str(row.get("track_id") or "").strip()
        for row in rows
        if str(row.get("status") or "") in active_statuses
        and str(row.get("track_id") or "").strip()
        and str(row.get("claim_role") or "") in {"method_candidate", "method_control"}
    }
    active_method_track_ids = {
        str(row.get("track_id") or "").strip()
        for row in rows
        if str(row.get("status") or "") in active_statuses
        and str(row.get("track_id") or "").strip()
        and str(row.get("claim_role") or "") == "method_candidate"
    }
    active_diagnostic_track_ids = {
        str(row.get("track_id") or "").strip()
        for row in rows
        if str(row.get("status") or "") in active_statuses
        and str(row.get("track_id") or "").strip()
        and str(row.get("claim_role") or "") in {"diagnostic_only", "baseline_support", "protocol_support"}
    }
    active_idea_ids: set[str] = set()
    active_all_signatures: set[str] = set()
    active_hypothesis_signatures: set[str] = set()
    active_gpu_hours_by_track: dict[str, float] = {}
    for row in admitted_matrix_rows(matrix):
        track_id = str(row.get("track_id") or "").strip()
        idea_id = str(row.get("idea_id") or row.get("selected_idea_id") or "").strip()
        claim_role = str(row.get("claim_role") or "").strip()
        if track_id:
            active_all_track_ids.add(track_id)
        if track_id and claim_role in {"method_candidate", "method_control"}:
            active_hypothesis_track_ids.add(track_id)
        if track_id and claim_role == "method_candidate":
            active_method_track_ids.add(track_id)
        if track_id and claim_role in {"diagnostic_only", "baseline_support", "protocol_support"}:
            active_diagnostic_track_ids.add(track_id)
        if idea_id:
            active_idea_ids.add(idea_id)
        signature = normalized_causal_signature(row)
        if signature:
            active_all_signatures.add(signature)
            if claim_role in {"method_candidate", "method_control"}:
                active_hypothesis_signatures.add(signature)
        cost = numeric(row.get("estimated_track_gpu_hours"), math.nan)
        if track_id and math.isfinite(cost) and cost > 0:
            active_gpu_hours_by_track[track_id] = cost

    search_budget = program.get("search_budget") if isinstance(program.get("search_budget"), dict) else {}
    method_target = positive_int(
        search_budget.get("method_portfolio_target") or policy.get("method_portfolio_target"),
        2,
    ) or 2
    method_target = min(capacity_target, method_target)
    seed_track_by_idea: dict[str, str] = {}
    seed_signature_by_idea: dict[str, str] = {}
    for seed in payload_rows(seeds):
        track_id = str(seed.get("track_id") or "").strip()
        idea_id = str(seed.get("idea_id") or "").strip()
        if idea_id:
            seed_track_by_idea[idea_id] = track_id
        claim_role = str(seed.get("claim_role") or "").strip()
        if track_id:
            active_all_track_ids.add(track_id)
        if track_id and claim_role in {"method_candidate", "method_control"}:
            active_hypothesis_track_ids.add(track_id)
        if track_id and claim_role == "method_candidate":
            active_method_track_ids.add(track_id)
        if track_id and claim_role in {"diagnostic_only", "baseline_support", "protocol_support"}:
            active_diagnostic_track_ids.add(track_id)
        if idea_id:
            active_idea_ids.add(idea_id)
        signature = normalized_causal_signature(seed)
        if signature:
            active_all_signatures.add(signature)
            if claim_role in {"method_candidate", "method_control"}:
                active_hypothesis_signatures.add(signature)
            if idea_id:
                seed_signature_by_idea[idea_id] = signature

    terminal_idea_ids: set[str] = set()
    for row in payload_rows(ledger):
        lifecycle = str(row.get("lifecycle_status") or row.get("status") or "").strip().lower()
        if lifecycle in PORTFOLIO_TERMINAL_LIFECYCLES:
            idea_id = str(row.get("idea_id") or row.get("selected_idea_id") or "").strip()
            if idea_id:
                terminal_idea_ids.add(idea_id)

    for idea_id in terminal_idea_ids:
        active_idea_ids.discard(idea_id)
        track_id = seed_track_by_idea.get(idea_id)
        if track_id:
            active_all_track_ids.discard(track_id)
            active_hypothesis_track_ids.discard(track_id)
            active_method_track_ids.discard(track_id)
            active_diagnostic_track_ids.discard(track_id)
        signature = seed_signature_by_idea.get(idea_id)
        if signature:
            active_all_signatures.discard(signature)
            active_hypothesis_signatures.discard(signature)

    active_track_ids = (
        active_hypothesis_track_ids if enforcement_mode == "enforced" else active_all_track_ids
    )
    active_signatures = (
        active_hypothesis_signatures if enforcement_mode == "enforced" else active_all_signatures
    )
    deficit = max(0, capacity_target - len(active_track_ids))
    shortlisted = shortlist_ids(scorecard)
    row_by_id = {
        str(row.get("id") or row.get("idea_id") or "").strip(): row
        for row in scorecard_rows(scorecard)
        if str(row.get("id") or row.get("idea_id") or "").strip()
    }
    idea_by_id = {
        str(row.get("id") or row.get("idea_id") or "").strip(): row
        for row in idea_pool_rows(pool)
        if str(row.get("id") or row.get("idea_id") or "").strip()
    }
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    allowed_dispositions = {"advance", "advance_with_constraints", "risk_repair"}
    for idea_id in shortlisted:
        row = row_by_id.get(idea_id, {})
        idea = idea_by_id.get(idea_id, {})
        reasons: list[str] = []
        if idea_id in active_idea_ids:
            reasons.append("already_active")
        if idea_id in terminal_idea_ids:
            reasons.append("terminal_lifecycle")
        disposition = str(
            row.get("promotion_recommendation")
            or row.get("recommended_track_action")
            or idea.get("promotion_recommendation")
            or ""
        ).strip().lower()
        claim_role = str(row.get("claim_role") or idea.get("claim_role") or "").strip()
        if claim_role and claim_role not in {"method_candidate", "method_control"}:
            reasons.append("non_hypothesis_portfolio_claim_role")
        if disposition not in allowed_dispositions:
            reasons.append("not_admissible_disposition")
        signature = normalized_causal_signature(row, idea)
        if not signature:
            reasons.append("missing_causal_signature")
        elif signature in active_signatures:
            reasons.append("causal_duplicate_active")
        blockers = as_str_list(row.get("hard_gate_blockers") or idea.get("hard_gate_blockers"))
        if blockers or row.get("portfolio_eligible") is False or idea.get("portfolio_eligible") is False:
            reasons.append("scientific_hard_gate")
        gpu_hours = candidate_gpu_hours(row, idea)
        if gpu_hours is None:
            reasons.append("missing_positive_falsifier_gpu_hours")
        decision_targets = candidate_decision_targets(row, idea)
        if not decision_targets:
            reasons.append("missing_decision_target")
        cheapest = idea.get("cheapest_discriminating_experiment") or row.get("cheapest_discriminating_experiment")
        if not truthy(cheapest):
            reasons.append("missing_cheapest_discriminator")
        if reasons:
            rejected.append({"idea_id": idea_id, "reasons": sorted(set(reasons))})
            continue
        reviewer_risks = as_str_list(
            row.get("reviewer_risks")
            or row.get("reviewer_attack_surface")
            or idea.get("reviewer_risks")
            or idea.get("red_line_risks")
        )
        reuse_refs = as_str_list(row.get("reusable_invariant_refs") or idea.get("reusable_invariant_refs"))
        resolved_count = positive_int(row.get("competing_hypotheses_resolved_count"), None)
        if resolved_count is None:
            resolved_count = len(as_str_list(row.get("competing_hypotheses_resolved"))) or len(decision_targets)
        candidate = {
            "idea_id": idea_id,
            "claim_role": claim_role or "method_candidate",
            "causal_signature": signature,
            "mutex_groups": sorted(set(as_str_list(row.get("mutex_groups") or idea.get("mutex_groups")))),
            "changes_core_claim": row.get("changes_core_claim") is True or idea.get("changes_core_claim") is True,
            "unique_decision_targets": decision_targets,
            "unique_decision_target_count": len(decision_targets),
            "competing_hypotheses_resolved_count": resolved_count,
            "estimated_falsifier_gpu_hours": gpu_hours,
            "validation_density": len(decision_targets) / float(gpu_hours),
            "reusable_invariant_refs": reuse_refs,
            "reusable_invariant_count": len(reuse_refs),
            "reviewer_risks": reviewer_risks,
            "reviewer_risk_count": len(reviewer_risks),
            "disposition": disposition,
            "cheapest_discriminating_experiment": cheapest,
        }
        candidate["ranking_tuple"] = list(portfolio_ranking_tuple(candidate))
        eligible.append(candidate)
    eligible.sort(key=portfolio_ranking_tuple)

    budget = numeric(policy.get("portfolio_gpu_hour_budget"), math.nan)
    remaining_budget = budget - sum(active_gpu_hours_by_track.values()) if math.isfinite(budget) else math.inf
    def subset_feasible(candidates: tuple[dict[str, Any], ...]) -> bool:
        signatures = set(active_signatures)
        mutexes: set[str] = set()
        gpu_hours = 0.0
        for candidate in candidates:
            signature = str(candidate.get("causal_signature") or "")
            candidate_mutexes = set(as_str_list(candidate.get("mutex_groups")))
            cost = float(candidate.get("estimated_falsifier_gpu_hours") or math.inf)
            if signature in signatures or candidate_mutexes & mutexes:
                return False
            signatures.add(signature)
            mutexes.update(candidate_mutexes)
            gpu_hours += cost
        return gpu_hours <= remaining_budget

    feasible_subsets: list[tuple[dict[str, Any], ...]] = []
    for size in range(0, min(deficit, len(eligible)) + 1):
        feasible_subsets.extend(
            subset for subset in itertools.combinations(eligible, size) if subset_feasible(subset)
        )

    method_deficit = max(0, method_target - len(active_method_track_ids))

    def subset_objective(candidates: tuple[dict[str, Any], ...]) -> tuple[Any, ...]:
        ranked = tuple(sorted((portfolio_ranking_tuple(item) for item in candidates)))
        total = sum(float(item.get("estimated_falsifier_gpu_hours") or math.inf) for item in candidates)
        ids = tuple(sorted(str(item.get("idea_id") or "") for item in candidates))
        method_count = sum(1 for item in candidates if item.get("claim_role") == "method_candidate")
        residual_method_deficit = max(0, method_deficit - method_count)
        return (-len(candidates), residual_method_deficit, ranked, total, ids)

    selected = list(min(feasible_subsets, key=subset_objective)) if feasible_subsets else []
    selected.sort(key=portfolio_ranking_tuple)
    selected_gpu_hours = sum(float(item.get("estimated_falsifier_gpu_hours") or 0.0) for item in selected)
    selected_ids_set = {str(item.get("idea_id") or "") for item in selected}
    selected_signatures = set(active_signatures) | {str(item.get("causal_signature") or "") for item in selected}
    selected_mutexes = {
        value
        for item in selected
        for value in as_str_list(item.get("mutex_groups"))
    }
    for candidate in eligible:
        candidate_id = str(candidate.get("idea_id") or "")
        if candidate_id in selected_ids_set:
            continue
        signature = str(candidate.get("causal_signature") or "")
        mutexes = set(as_str_list(candidate.get("mutex_groups")))
        cost = float(candidate.get("estimated_falsifier_gpu_hours") or math.inf)
        reasons: list[str] = []
        if signature in selected_signatures:
            reasons.append("causal_duplicate_batch")
        if mutexes & selected_mutexes:
            reasons.append("pairwise_mutex_conflict")
        if selected_gpu_hours + cost > remaining_budget:
            reasons.append("portfolio_gpu_hour_budget")
        if not reasons:
            reasons.append("dominated_by_deterministic_set_objective")
        rejected.append({"idea_id": candidate_id, "reasons": reasons})

    fillable_ids = [str(candidate["idea_id"]) for candidate in selected]
    method_fillable_ids = [
        str(candidate["idea_id"])
        for candidate in selected
        if candidate.get("claim_role") == "method_candidate"
    ]
    if deficit <= 0:
        blocker = "portfolio_capacity_satisfied"
    elif fillable_ids:
        blocker = "portfolio_admission_deficit"
    elif not shortlisted:
        blocker = "shortlist_missing_or_exhausted"
    elif eligible:
        blocker = "no_set_feasible_shortlist_candidate"
    else:
        blocker = "shortlist_candidates_blocked"
    return {
        "portfolio_capacity_target": capacity_target,
        "method_portfolio_target": method_target,
        "portfolio_enforcement_mode": enforcement_mode,
        "active_method_candidate_count": len(active_method_track_ids),
        "method_active_track_count": len(active_method_track_ids),
        "active_method_candidate_track_ids": sorted(active_method_track_ids),
        "method_portfolio_deficit": method_deficit,
        "method_admission_deficit": method_deficit,
        "method_portfolio_fillable_candidate_ids": method_fillable_ids,
        "method_fillable_candidate_ids": method_fillable_ids,
        "diagnostic_active_track_count": len(active_diagnostic_track_ids),
        "diagnostic_active_track_ids": sorted(active_diagnostic_track_ids),
        "active_nonterminal_track_count": len(active_track_ids),
        "active_nonterminal_track_ids": sorted(active_track_ids),
        "portfolio_admission_deficit": deficit,
        "eligible_shortlist_candidate_ids": [str(item["idea_id"]) for item in eligible],
        "portfolio_fillable_candidate_ids": fillable_ids,
        "portfolio_fillable_count": len(fillable_ids),
        "portfolio_actionable": bool(fillable_ids),
        "portfolio_blocker_code": blocker,
        "portfolio_selected_gpu_hours": selected_gpu_hours,
        "portfolio_remaining_gpu_hour_budget": remaining_budget if math.isfinite(remaining_budget) else None,
        "portfolio_candidates": eligible,
        "portfolio_rejections": sorted(rejected, key=lambda item: str(item.get("idea_id") or "")),
        "selection_revision": scorecard.get("selection_revision") or scorecard.get("selection_fingerprint"),
        "shadow_active_nonterminal_track_count": len(active_hypothesis_track_ids),
        "shadow_portfolio_admission_deficit": max(0, capacity_target - len(active_hypothesis_track_ids)),
    }


def _frontier_candidate_key(candidate: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(candidate.get(field) or "").strip()
        for field in ["decision_target", "track_id", "dataset", "protocol", "variant", "seed_profile"]
    )


def admissible_frontier_candidates(
    matrix: dict[str, Any],
    queue: dict[str, Any],
    project: Path | None = None,
) -> dict[str, Any]:
    """Return only packet-enumerated, dependency-unlocked frontier candidates."""

    rows = [row for row in queue.get("rows", []) if isinstance(row, dict)]
    rows_by_id = {str(row.get("id") or ""): row for row in rows}
    active_statuses = {"ready", "planned", "submitting", "running", "needs_sync"}
    active_tracks = {
        str(row.get("track_id") or "")
        for row in rows
        if str(row.get("status") or "") in active_statuses
    }
    candidates: list[dict[str, Any]] = []
    dependency_blocked: list[dict[str, Any]] = []
    missing_packet_tracks: list[str] = []
    seen: set[tuple[str, ...]] = set()
    blocked_seen: set[tuple[str, ...]] = set()

    for plan_row in admitted_matrix_rows(matrix):
        launch_status = str(plan_row.get("launch_status") or "").strip().lower()
        if plan_row.get("planning_admitted") is not True and launch_status in {
            "blocked",
            "frozen",
            "paused",
            "scoped_no_new_pilot",
        }:
            continue
        track_id = str(plan_row.get("track_id") or "").strip()
        if not track_id:
            continue
        review_ref = str(plan_row.get("review_packet_ref") or "").strip()
        review: dict[str, Any] = {}
        if project is not None and review_ref:
            review = read_json(project / ".autoreskill" / review_ref)
        if not isinstance(review, dict):
            review = {}
        packet_ready = bool(review) and plan_row.get("planning_admitted") is True
        if not packet_ready:
            missing_packet_tracks.append(track_id)
        if track_id not in active_tracks:
            minimum = review.get("minimum_pilot") or plan_row.get("minimum_pilot")
            if truthy(minimum):
                candidate = {
                    "candidate_kind": "cheapest_track_discriminator",
                    "track_id": track_id,
                    "decision_target": str(plan_row.get("idea_decision_ref") or track_id),
                    "dataset": str(plan_row.get("dataset") or review.get("dataset") or ""),
                    "protocol": str(plan_row.get("review_packet_sha256") or ""),
                    "variant": "minimum_pilot",
                    "seed_profile": "bounded_first_pilot",
                    "source_ref": review_ref or str(plan_row.get("source_seed_path") or ""),
                    "requires_packet_materialization": not packet_ready,
                }
                key = _frontier_candidate_key(candidate)
                if key not in seen:
                    seen.add(key)
                    candidates.append(candidate)

        enumerated = review.get("frontier_candidates")
        if not isinstance(enumerated, list):
            enumerated = review.get("declared_next_experiments")
        if not isinstance(enumerated, list):
            enumerated = []
        for index, raw in enumerate(enumerated):
            if not isinstance(raw, dict):
                continue
            dependencies = as_str_list(raw.get("depends_on_rows") or raw.get("dependencies"))
            unsatisfied = [
                ref
                for ref in dependencies
                if str(rows_by_id.get(ref, {}).get("status") or "")
                not in {"terminal_positive", "terminal_negative", "superseded"}
            ]
            candidate = {
                "candidate_kind": str(raw.get("kind") or raw.get("role") or "declared_packet_candidate"),
                "track_id": track_id,
                "decision_target": str(raw.get("decision_target") or raw.get("decision_target_ref") or f"{track_id}:{index}"),
                "dataset": str(raw.get("dataset") or review.get("dataset") or ""),
                "protocol": str(raw.get("protocol") or plan_row.get("review_packet_sha256") or ""),
                "variant": str(raw.get("variant") or raw.get("id") or index),
                "seed_profile": str(raw.get("seed_profile") or "bounded_declared"),
                "source_ref": f"{review_ref}:frontier_candidates[{index}]",
                "depends_on_rows": dependencies,
            }
            if unsatisfied:
                candidate["unsatisfied_dependencies"] = unsatisfied
                key = _frontier_candidate_key(candidate)
                if key not in blocked_seen:
                    blocked_seen.add(key)
                    dependency_blocked.append(candidate)
                continue
            key = _frontier_candidate_key(candidate)
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)
    candidates.sort(key=lambda item: (_frontier_candidate_key(item), str(item.get("candidate_kind") or "")))
    return {
        "candidates": candidates,
        "dependency_blocked": dependency_blocked,
        "missing_packet_track_ids": sorted(set(missing_packet_tracks)),
    }


def parameter_frontier_status(
    project: Path | None,
    matrix: dict[str, Any],
    queue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project frozen-profile readiness without creating another planning authority."""

    if project is None:
        return {
            "parameter_profile_status_by_track": {},
            "parameter_coverage_deficit_by_track_and_dataset": {},
            "parameter_blockers": [],
            "parameter_probe_ready_count": 0,
            "parameter_scale_audit_pending_count": 0,
            "parameter_calibration_group_incomplete_count": 0,
            "seed_only_substitution_rejected_count": 0,
        }
    base = project / ".autoreskill"
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json")
    if str(program.get("claim_scope") or "") != "cross_dataset_method":
        return {
            "parameter_profile_status_by_track": {},
            "parameter_coverage_deficit_by_track_and_dataset": {},
            "parameter_blockers": [],
            "parameter_probe_ready_count": 0,
            "parameter_scale_audit_pending_count": 0,
            "parameter_calibration_group_incomplete_count": 0,
            "seed_only_substitution_rejected_count": 0,
        }
    queue_rows = [row for row in (queue or {}).get("rows", []) if isinstance(row, dict)]
    probe_ready_count = sum(
        1
        for row in queue_rows
        if row.get("stage2_role") == "stage2_parameter_probe"
        and str(row.get("status") or "") == "ready"
    )
    scale_audit_pending_count = sum(
        1
        for row in queue_rows
        if row.get("stage2_role") == "stage2_parameter_probe"
        and str(row.get("parameter_probe_kind") or "") == "scale_audit"
        and str(row.get("status") or "") in STRICT_LAUNCH_STATUSES
    )
    incomplete_groups: set[str] = set()
    seed_only_tracks: set[str] = set()
    statuses: dict[str, str] = {}
    deficits: dict[str, dict[str, int]] = {}
    blockers: list[dict[str, Any]] = []
    for plan_row in admitted_matrix_rows(matrix):
        if str(plan_row.get("claim_role") or "") != "method_candidate":
            continue
        track_id = str(plan_row.get("track_id") or "").strip()
        if not track_id:
            continue
        review = read_json(base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json")
        contract = review.get("parameter_transfer_contract") if isinstance(review, dict) else None
        status = str(review.get("parameter_profile_status") or "missing") if isinstance(review, dict) else "missing"
        statuses[track_id] = status
        datasets = required_dataset_ids(program, review if isinstance(review, dict) else plan_row)
        validation = validate_parameter_transfer_contract(contract, datasets) if isinstance(contract, dict) else {
            "complete": False,
            "errors": ["parameter_transfer_contract_missing"],
            "coverage_deficit_by_dataset": {dataset_id: 2 for dataset_id in datasets},
        }
        coverage = validation.get("coverage_deficit_by_dataset") or {}
        materialization_deficit: dict[str, int] = {str(key): int(value) for key, value in coverage.items()}
        probe_rows = [
            row
            for row in queue_rows
            if str(row.get("track_id") or "") == track_id
            and row.get("stage2_role") == "stage2_parameter_probe"
            and str(row.get("status") or "") not in {"dropped", "superseded"}
        ]
        if isinstance(contract, dict) and status != "frozen":
            candidates = contract.get("candidate_values_by_dataset")
            if isinstance(candidates, dict):
                for dataset_id in datasets:
                    expected_values = {
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        for value in candidates.get(dataset_id, [])
                    }
                    dataset_rows = [
                        row
                        for row in probe_rows
                        if str(row.get("dataset_id") or row.get("dataset") or "") == dataset_id
                    ]
                    represented_values = {
                        json.dumps(row.get("parameter_value"), ensure_ascii=False, sort_keys=True)
                        for row in dataset_rows
                        if row.get("parameter_value") is not None
                    }
                    missing_values = expected_values - represented_values
                    materialization_deficit[dataset_id] = max(
                        int(materialization_deficit.get(dataset_id) or 0),
                        len(missing_values),
                    )
                    seeds = {
                        str(row.get("seed"))
                        for row in dataset_rows
                        if row.get("seed") is not None
                    }
                    if len(represented_values) < 2 and len(seeds) > 1:
                        seed_only_tracks.add(track_id)
                        blockers.append({"track_id": track_id, "code": "seed_only_parameter_substitution"})
                group_id = str(contract.get("parameter_calibration_group_id") or track_id)
                all_expected_materialized = all(value == 0 for value in materialization_deficit.values())
                all_terminal = bool(probe_rows) and all(
                    str(row.get("status") or "") in {"terminal_positive", "terminal_negative"}
                    for row in probe_rows
                )
                if not all_expected_materialized or not all_terminal:
                    incomplete_groups.add(group_id)
        if any(value > 0 for value in materialization_deficit.values()):
            deficits[track_id] = materialization_deficit
            blockers.append({"track_id": track_id, "code": "innovation_parameter_coverage_incomplete"})
        for error in validation.get("errors") or []:
            blockers.append({"track_id": track_id, "code": str(error)})
        if status == "frozen" and isinstance(contract, dict):
            profile_ref = str(review.get("frozen_parameter_profile_ref") or "")
            profile = read_json(base / profile_ref) if profile_ref else {}
            profile_validation = validate_frozen_profile(profile, contract, datasets)
            for error in profile_validation.get("errors") or []:
                blockers.append({"track_id": track_id, "code": str(error)})
        elif status != "not_required":
            blockers.append({"track_id": track_id, "code": f"parameter_profile_{status}"})
    unique = {
        (str(item.get("track_id") or ""), str(item.get("code") or "")): item
        for item in blockers
    }
    return {
        "parameter_profile_status_by_track": statuses,
        "parameter_coverage_deficit_by_track_and_dataset": deficits,
        "parameter_value_deficit_by_dataset": deficits,
        "parameter_blockers": [unique[key] for key in sorted(unique)],
        "parameter_probe_ready_count": probe_ready_count,
        "parameter_scale_audit_pending_count": scale_audit_pending_count,
        "parameter_calibration_group_incomplete_count": len(incomplete_groups),
        "seed_only_substitution_rejected_count": len(seed_only_tracks),
    }


def cross_dataset_frontier_status(
    project: Path | None,
    matrix: dict[str, Any],
    queue: dict[str, Any],
) -> dict[str, Any]:
    """Report paired dataset coverage without creating queue or lifecycle state."""

    empty = {
        "dataset_coverage_deficit_by_track": {},
        "paired_group_incomplete_count": 0,
        "paired_group_missing_dataset_legs": {},
        "paired_group_unresolved_legs": {},
        "cross_dataset_decision_pending_count": 0,
        "cross_dataset_full_budget_ready_count": 0,
        "robust_hpo_ready_count": 0,
        "innovation_parameter_coverage_status_by_track": {},
        "cross_dataset_blockers": [],
    }
    if project is None:
        return empty
    base = project / ".autoreskill"
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json")
    if str(program.get("claim_scope") or "") != "cross_dataset_method":
        return empty
    required = required_dataset_ids(program)
    rows = [row for row in queue.get("rows", []) if isinstance(row, dict)]
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
    decided_groups = {
        str(row.get("paired_dataset_group_id") or "")
        for row in ledger.get("cross_dataset_decisions", [])
        if isinstance(row, dict) and str(row.get("paired_dataset_group_id") or "")
    }
    deficits: dict[str, list[str]] = {}
    missing_by_group: dict[str, list[str]] = {}
    unresolved_by_group: dict[str, list[str]] = {}
    coverage_status: dict[str, str] = {}
    blockers: list[dict[str, str]] = []
    for plan_row in admitted_matrix_rows(matrix):
        if str(plan_row.get("claim_role") or "") != "method_candidate":
            continue
        track_id = str(plan_row.get("track_id") or "").strip()
        if not track_id:
            continue
        review = read_json(base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json")
        track_required = required_dataset_ids(program, review if isinstance(review, dict) else plan_row) or required
        track_rows = [
            row for row in rows
            if str(row.get("track_id") or "") == track_id
            and str(row.get("status") or "") not in {"dropped", "superseded"}
        ]
        method_rows = [row for row in track_rows if row.get("stage2_role") == "stage2_method_screen"]
        observed = {
            str(row.get("dataset_id") or row.get("dataset") or "")
            for row in method_rows
        }
        missing = sorted(set(track_required) - observed)
        if missing:
            deficits[track_id] = missing
            blockers.append({"track_id": track_id, "code": "paired_stage2_leg_missing"})
        groups = {
            str(row.get("paired_dataset_group_id") or "")
            for row in method_rows
            if str(row.get("paired_dataset_group_id") or "")
        }
        if method_rows and not groups:
            groups = {f"unbound:{track_id}"}
        for group_id in groups:
            group_rows = [
                row for row in method_rows
                if group_id.startswith("unbound:")
                or str(row.get("paired_dataset_group_id") or "") == group_id
            ]
            group_datasets = {
                str(row.get("dataset_id") or row.get("dataset") or "")
                for row in group_rows
            }
            group_missing = sorted(set(track_required) - group_datasets)
            if group_missing:
                missing_by_group[group_id] = group_missing
            unresolved_legs = sorted(
                str(row.get("dataset_id") or row.get("dataset") or "")
                for row in group_rows
                if str(row.get("status") or "") not in {"terminal_positive", "terminal_negative"}
            )
            if not group_missing and (unresolved_legs or group_id not in decided_groups):
                unresolved_by_group[group_id] = unresolved_legs or ["scientific_decision_pending"]
                blockers.append({"track_id": track_id, "code": "paired_stage2_group_unresolved"})
        profile_status = str(review.get("parameter_profile_status") or "missing") if isinstance(review, dict) else "missing"
        coverage_status[track_id] = "complete" if profile_status == "frozen" else "incomplete"
        if profile_status != "frozen":
            blockers.append({"track_id": track_id, "code": "parameter_profile_not_frozen"})
    full_budget_ready = sum(
        1
        for row in rows
        if row.get("validation_stage") in {3, 4}
        and str(row.get("claim_scope") or "") == "cross_dataset_method"
        and str(row.get("status") or "") == "ready"
    )
    hpo_ready = sum(
        1
        for row in rows
        if row.get("validation_stage") == 5
        and str(row.get("claim_scope") or "") == "cross_dataset_method"
        and str(row.get("status") or "") == "ready"
    )
    unique_blockers = {
        (item["track_id"], item["code"]): item
        for item in blockers
    }
    return {
        "dataset_coverage_deficit_by_track": deficits,
        "paired_group_incomplete_count": len(set(missing_by_group) | set(unresolved_by_group)),
        "paired_group_missing_dataset_legs": missing_by_group,
        "paired_group_unresolved_legs": unresolved_by_group,
        "cross_dataset_decision_pending_count": sum(
            1 for values in unresolved_by_group.values() if values == ["scientific_decision_pending"]
        ),
        "cross_dataset_full_budget_ready_count": full_budget_ready,
        "robust_hpo_ready_count": hpo_ready,
        "innovation_parameter_coverage_status_by_track": coverage_status,
        "cross_dataset_blockers": [unique_blockers[key] for key in sorted(unique_blockers)],
    }


def frontier_status(
    queue: dict[str, Any],
    matrix: dict[str, Any] | None = None,
    project: Path | None = None,
) -> dict[str, Any]:
    """Compute a bounded planning signal without creating or mutating queue rows."""

    matrix = matrix or (
        read_json(project / ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json")
        if project is not None
        else {}
    )
    if not isinstance(matrix, dict):
        matrix = {}
    policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    rows = [row for row in queue.get("rows", []) if isinstance(row, dict)]
    decision_rows = [
        row
        for row in rows
        if str(row.get("role") or "") != "monitor_sync"
        and str(row.get("launch_mode") or "") != "monitor_only"
    ]
    ready = [row for row in decision_rows if str(row.get("status") or "") == "ready"]
    reserved = [row for row in decision_rows if str(row.get("status") or "") == "planned"]
    submitting = [row for row in decision_rows if str(row.get("status") or "") == "submitting"]
    syncing = [row for row in decision_rows if str(row.get("status") or "") == "needs_sync"]
    running = [row for row in decision_rows if str(row.get("status") or "") == "running"]
    supply_count = len(ready) + len(reserved) + len(submitting) + len(syncing) + len(running)
    admitted = admitted_matrix_rows(matrix)

    snapshot = queue.get("resource_snapshot") if isinstance(queue.get("resource_snapshot"), dict) else {}
    snapshot_fresh = not (
        snapshot.get("stale") is True
        or snapshot.get("fresh") is False
        or str(snapshot.get("status") or "").strip().lower() in {"stale", "expired"}
    )
    pools, _, snapshot_missing = resource_pools(queue)
    fresh_idle_slots = sum(pool_launch_slots(pool) for pool in pools) if snapshot_fresh and not snapshot_missing else 0
    inflight_slots = sum(requested_gpu_count(row) for row in reserved + submitting + syncing + running)
    absolute_cap = positive_int(policy.get("absolute_max_new_launches_per_cycle"), 16) or 16
    capacity_basis = min(absolute_cap, max(len(admitted), fresh_idle_slots, inflight_slots))
    candidate_result = admissible_frontier_candidates(matrix, queue, project)
    candidates = candidate_result["candidates"]
    dependency_blocked = candidate_result["dependency_blocked"]
    # Dependency-locked packet candidates count toward unresolved planning
    # demand, but never toward actionable supply.
    admissible_budget = supply_count + len(candidates) + len(dependency_blocked)
    multiplier = positive_int(policy.get("ready_frontier_multiplier"), 2) or 2
    max_rows = positive_int(policy.get("max_ready_frontier_rows"), 32) or 32
    target = min(max_rows, multiplier * capacity_basis, admissible_budget)
    deficit = max(0, target - supply_count)
    missing_packet_tracks = candidate_result["missing_packet_track_ids"]
    candidate_track_ids = sorted({str(item.get("track_id")) for item in candidates if item.get("track_id")})
    if deficit <= 0:
        blocker = "frontier_satisfied"
        actionable = False
    elif missing_packet_tracks:
        blocker = "missing_track_packet"
        actionable = True
    elif candidates:
        blocker = "admissible_frontier_deficit"
        actionable = True
    elif dependency_blocked:
        blocker = "scientific_dependency_wait"
        actionable = False
    elif not admitted:
        blocker = "no_admitted_track"
        actionable = False
    else:
        blocker = "no_admissible_frontier_candidate"
        actionable = False
    portfolio = portfolio_status(queue, matrix, project)
    raw_parameter_status = parameter_frontier_status(project, matrix, queue)
    raw_cross_dataset_status = cross_dataset_frontier_status(project, matrix, queue)
    program: dict[str, Any] = {}
    ledger: dict[str, Any] = {}
    if project is not None:
        program = read_json(project / ".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json")
        ledger = read_json(project / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json")
    program_status = str(program.get("contract_status") or "missing")
    program_mode = str(program.get("enforcement_mode") or "legacy")
    program_scientific_status = str(ledger.get("program_scientific_status") or "unresolved")
    parameter_empty = {
        "parameter_profile_status_by_track": {},
        "parameter_coverage_deficit_by_track_and_dataset": {},
        "parameter_value_deficit_by_dataset": {},
        "parameter_blockers": [],
        "parameter_probe_ready_count": 0,
        "parameter_scale_audit_pending_count": 0,
        "parameter_calibration_group_incomplete_count": 0,
        "seed_only_substitution_rejected_count": 0,
    }
    cross_empty = {
        "dataset_coverage_deficit_by_track": {},
        "paired_group_incomplete_count": 0,
        "paired_group_missing_dataset_legs": {},
        "paired_group_unresolved_legs": {},
        "cross_dataset_decision_pending_count": 0,
        "cross_dataset_full_budget_ready_count": 0,
        "robust_hpo_ready_count": 0,
        "innovation_parameter_coverage_status_by_track": {},
        "cross_dataset_blockers": [],
    }
    shadow_projection: dict[str, Any] = {}
    if program_mode == "enforced":
        parameter_status = raw_parameter_status
        cross_dataset_status = raw_cross_dataset_status
    else:
        parameter_status = parameter_empty
        cross_dataset_status = cross_empty
        if program_mode == "shadow":
            shadow_projection = {
                "shadow_parameter_status": raw_parameter_status,
                "shadow_cross_dataset_status": raw_cross_dataset_status,
                "shadow_enforcement_would_block": bool(
                    raw_parameter_status.get("parameter_blockers")
                    or raw_cross_dataset_status.get("cross_dataset_blockers")
                ),
            }
    coverage_actionable = bool(
        parameter_status.get("parameter_coverage_deficit_by_track_and_dataset")
        or cross_dataset_status.get("dataset_coverage_deficit_by_track")
    )
    launch = {
        "launch_frontier_target": target,
        "launch_frontier_ready_count": len(ready),
        "launch_frontier_reserved_count": len(reserved),
        "launch_frontier_submitting_count": len(submitting),
        "launch_frontier_syncing_count": len(syncing),
        "launch_frontier_running_count": len(running),
        "launch_frontier_supply_count": supply_count,
        "launch_frontier_deficit": deficit,
        "launch_frontier_underfilled": deficit > 0,
        "launch_frontier_actionable": actionable,
        "launch_frontier_blocker_code": blocker,
    }
    return {
        **launch,
        **portfolio,
        **parameter_status,
        **cross_dataset_status,
        **shadow_projection,
        "program_contract_status": program_status,
        "program_contract_enforcement_mode": program_mode,
        "program_claim_contract_sha256": program.get("semantic_sha256"),
        "program_scientific_status": program_scientific_status,
        "workflow_actionable": bool(
            actionable
            or portfolio.get("portfolio_actionable")
            or coverage_actionable
            or int(cross_dataset_status.get("cross_dataset_decision_pending_count") or 0) > 0
        ),
        "workflow_satisfied": bool(
            not actionable
            and not portfolio.get("portfolio_actionable")
            and deficit <= 0
            and int(portfolio.get("portfolio_admission_deficit") or 0) <= 0
            and int(portfolio.get("method_admission_deficit") or 0) <= 0
            and not parameter_status.get("parameter_coverage_deficit_by_track_and_dataset")
            and not cross_dataset_status.get("dataset_coverage_deficit_by_track")
            and int(cross_dataset_status.get("paired_group_incomplete_count") or 0) <= 0
        ),
        # One-cycle compatibility aliases. They retain launch-frontier meaning.
        "frontier_target": target,
        "frontier_ready_count": len(ready),
        "frontier_reserved_count": len(reserved),
        "frontier_submitting_count": len(submitting),
        "frontier_syncing_count": len(syncing),
        "frontier_running_count": len(running),
        "frontier_supply_count": supply_count,
        "frontier_deficit": deficit,
        "frontier_underfilled": deficit > 0,
        "frontier_actionable": actionable,
        "frontier_blocker_code": blocker,
        "candidate_track_ids": candidate_track_ids,
        "missing_packet_track_ids": missing_packet_tracks,
        "admitted_nonterminal_track_count": len(admitted),
        "fresh_fitting_idle_slots": fresh_idle_slots,
        "current_decision_bearing_inflight_slots": inflight_slots,
        "current_and_unresolved_admissible_row_budget": admissible_budget,
        "admissible_candidates": candidates,
        "dependency_blocked_candidates": dependency_blocked,
    }


def shared_resource_snapshot_errors(snapshot: dict[str, Any]) -> list[str]:
    """Validate the fresh, detailed snapshot required by global admission."""

    errors: list[str] = []
    if not isinstance(snapshot, dict) or not snapshot:
        return ["shared resource snapshot is missing or empty"]
    if snapshot.get("fresh") is not True or snapshot.get("stale") is not False:
        errors.append("shared resource snapshot must set fresh=true and stale=false")
    if str(snapshot.get("status") or "").strip().lower() != "fresh":
        errors.append("shared resource snapshot must have status=fresh")
    checked_at = strict_aware_time(snapshot.get("checked_at"))
    if checked_at is None:
        errors.append("shared resource snapshot checked_at must be timezone-aware")
    else:
        age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
        if age_seconds < -60 or age_seconds > 600:
            errors.append("shared resource snapshot checked_at is stale or implausibly future-dated")
    pools = snapshot.get("pools")
    if not isinstance(pools, list) or not pools:
        errors.append("shared resource snapshot requires at least one detailed pool")
        return errors
    seen_pool_ids: set[str] = set()
    for index, pool in enumerate(pools):
        if not isinstance(pool, dict):
            errors.append(f"shared resource snapshot pools[{index}] must be an object")
            continue
        pool_id = str(pool.get("pool_id") or "").strip()
        if not pool_id:
            errors.append(f"shared resource snapshot pools[{index}].pool_id is required")
        elif pool_id in seen_pool_ids:
            errors.append(f"shared resource snapshot contains duplicate pool_id {pool_id}")
        seen_pool_ids.add(pool_id)
        if nonnegative_int(pool.get("launch_slots")) is None:
            errors.append(f"shared resource pool {pool_id or index} launch_slots must be a nonnegative integer")
    return errors


def schedule_semantic_sha256(schedule: dict[str, Any]) -> str:
    payload = copy.deepcopy(schedule)
    payload.pop("ok", None)
    payload.pop("generated_at", None)
    payload.pop("global_schedule_sha256", None)
    return canonical_payload_sha256(payload)


def assignment_semantic_sha256(assignment: dict[str, Any]) -> str:
    payload = copy.deepcopy(assignment)
    payload.pop("assignment_sha256", None)
    return canonical_payload_sha256(payload)


def concrete_pool_resource_ids(pool: dict[str, Any]) -> list[str]:
    resource_ids = as_str_list(pool.get("resource_ids"))
    if resource_ids:
        return [f"resource:{value}" for value in resource_ids]
    gpu_uuids = as_str_list(pool.get("gpu_uuids"))
    if gpu_uuids:
        return [f"gpu_uuid:{value}" for value in gpu_uuids]
    gpu_ids = as_str_list(pool.get("gpu_ids"))
    if not gpu_ids:
        return []
    namespace = str(
        pool.get("host_ref")
        or pool.get("host")
        or pool.get("account_ref")
        or pool.get("account")
        or pool.get("pool_id")
        or "pool"
    )
    return [f"gpu_id:{namespace}:{value}" for value in gpu_ids]


def project_control_lease_busy(project: Path, owner: str | None = None) -> dict[str, Any] | None:
    lease_path = project / PROJECT_CONTROL_LEASE_REL
    lease = read_json(lease_path)
    expires_at = parse_time(lease.get("expires_at"))
    if not lease or expires_at is None or expires_at <= datetime.now(timezone.utc):
        return None
    lease_owner = str(lease.get("owner_id") or "").strip()
    if owner and lease_owner == owner:
        return None
    return {
        "reason": "project_control_busy",
        "project": str(project),
        "lease_path": str(lease_path),
        "owner_id": lease_owner,
        "operation": lease.get("operation"),
        "expires_at": lease.get("expires_at"),
    }


def select_global_launch_batch(
    project_queues: list[tuple[Path, dict[str, Any]]],
    resource_snapshot: dict[str, Any],
    *,
    resource_snapshot_ref: str | None = None,
    excluded_projects: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a deterministic cross-project proposal without claiming resources."""

    snapshot_errors = shared_resource_snapshot_errors(resource_snapshot)
    if snapshot_errors:
        return {
            "ok": False,
            "reason": "resource_snapshot_invalid",
            "errors": snapshot_errors,
            "assignments": [],
            "rejections": [],
            "requires_resource_refresh": True,
        }

    snapshot_sha256 = canonical_payload_sha256(resource_snapshot)
    pools = [copy.deepcopy(pool) for pool in resource_snapshot.get("pools", []) if isinstance(pool, dict)]
    remaining_by_pool = {
        str(pool.get("pool_id") or f"pool-{index}"): pool_launch_slots(pool)
        for index, pool in enumerate(pools)
    }
    shared_blocked_refs = {
        str(pool.get("shared_limit_ref") or "").strip()
        for pool in pools
        if str(pool.get("shared_limit_ref") or "").strip()
        and (
            pool.get("shared_limit_blocked") is True
            or str(pool.get("blocked_scope") or "").strip().lower() == "shared_limit"
            or str(pool.get("status") or "").strip().lower() == "blocked_shared_limit"
        )
    }
    exclusions = excluded_projects or {}
    project_records: list[dict[str, Any]] = []
    frontier_summaries: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    candidates_by_class: dict[int, dict[str, list[dict[str, Any]]]] = {}

    for project, queue in sorted(project_queues, key=lambda item: str(item[0].resolve())):
        project = project.resolve()
        project_key = str(project)
        queue_path = project / QUEUE_REL
        queue_sha256 = canonical_payload_sha256(queue)
        policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
        scope = str(policy.get("admission_scope") or "project").strip().lower()
        record = {
            "project": project_key,
            "queue_path": str(queue_path),
            "queue_revision": queue.get("queue_revision"),
            "queue_sha256": queue_sha256,
            "admission_scope": scope,
            "project_priority": numeric(policy.get("project_priority"), 100.0),
        }
        project_records.append(record)
        frontier = frontier_status(queue, project=project)
        frontier_summaries.append({"project": project_key, **frontier})
        if project_key in exclusions:
            record["status"] = "project_control_busy"
            rejections.append(exclusions[project_key])
            continue
        if scope != "global":
            record["status"] = "project_admission_scope_required"
            rejections.append(
                {
                    "project": project_key,
                    "reason": "project_admission_scope_required",
                    "detail": "schedule-global only admits queues with policy.admission_scope=global",
                }
            )
            continue

        queue_copy = copy.deepcopy(queue)
        queue_copy["resource_snapshot"] = copy.deepcopy(resource_snapshot)
        local = select_launch_batch(queue_copy, project)
        if not local.get("ok"):
            record["status"] = "queue_validation_failed"
            rejections.append(
                {
                    "project": project_key,
                    "reason": "queue_validation_failed",
                    "errors": local.get("errors") or [],
                }
            )
            continue
        record["status"] = "eligible"
        rows_by_id = {
            str(row.get("id") or ""): row
            for row in queue.get("rows", [])
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        }
        active_rows = [
            row
            for row in rows_by_id.values()
            if str(row.get("status") or "") in {"planned", "submitting", "running", "needs_sync"}
        ]
        current_load = sum(requested_gpu_count(row) for row in active_rows)
        selected_rows = []
        for local_assignment in local.get("assignments") or []:
            if not isinstance(local_assignment, dict):
                continue
            row = rows_by_id.get(str(local_assignment.get("row_id") or ""))
            if row is None:
                continue
            selected_rows.append(
                {
                    "project": project_key,
                    "queue_path": str(queue_path),
                    "queue_revision": queue.get("queue_revision"),
                    "queue_sha256": queue_sha256,
                    "project_priority": record["project_priority"],
                    "current_project_gpu_slot_load": current_load,
                    "row": row,
                }
            )
        for rejected in local.get("rejected") or []:
            if isinstance(rejected, dict):
                rejections.append({"project": project_key, **rejected})
        for candidate in sorted(selected_rows, key=lambda item: row_priority(item["row"])):
            row = candidate["row"]
            decision_class = str(row.get("decision_class") or "")
            class_rank = ACQUISITION_ORDER.get(decision_class, len(ACQUISITION_CLASSES))
            candidates_by_class.setdefault(class_rank, {}).setdefault(project_key, []).append(candidate)

    assignments: list[dict[str, Any]] = []
    assigned_slots_by_project: dict[str, int] = {}
    allocated_resource_ids: set[str] = set()
    for class_rank in sorted(candidates_by_class):
        project_candidates = candidates_by_class[class_rank]
        while any(project_candidates.values()):
            choices: list[tuple[tuple[Any, ...], str, dict[str, Any]]] = []
            for project_key, items in project_candidates.items():
                if not items:
                    continue
                candidate = items[0]
                row = candidate["row"]
                cost = estimated_gpu_hours(row)
                choices.append(
                    (
                        (
                            candidate["current_project_gpu_slot_load"]
                            + assigned_slots_by_project.get(project_key, 0),
                            -len(decision_target_refs(row)),
                            cost if cost is not None else float("inf"),
                            candidate["project_priority"],
                            numeric(row.get("priority"), 9999.0),
                            project_key,
                            str(row.get("id") or ""),
                        ),
                        project_key,
                        candidate,
                    )
                )
            if not choices:
                break
            _, project_key, candidate = min(choices, key=lambda item: item[0])
            project_candidates[project_key].pop(0)
            row = candidate["row"]
            row_id = str(row.get("id") or "")
            gpu_count = requested_gpu_count(row)
            fitting: list[tuple[tuple[Any, ...], str, dict[str, Any], list[str]]] = []
            fit_reasons: list[str] = []
            for index, pool in enumerate(pools):
                pool_id = str(pool.get("pool_id") or f"pool-{index}")
                remaining = remaining_by_pool.get(pool_id, 0)
                fit_error = pool_fit_rejection(row, pool, remaining, shared_blocked_refs, True)
                if fit_error:
                    fit_reasons.append(f"{pool_id}: {fit_error}")
                    continue
                concrete_ids = concrete_pool_resource_ids(pool)
                available_ids = [value for value in concrete_ids if value not in allocated_resource_ids]
                if concrete_ids and len(available_ids) < gpu_count:
                    fit_reasons.append(f"{pool_id}: concrete resource ids are exhausted")
                    continue
                request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
                free_vram = pool_free_vram_mb(pool)
                min_vram = numeric(
                    request.get("min_vram_mb", request.get("min_free_mib", request.get("min_free_mb"))),
                    0.0,
                )
                vram_slack = (free_vram - min_vram) if free_vram is not None else float("inf")
                fitting.append(
                    (
                        (remaining - gpu_count, vram_slack, pool_id),
                        pool_id,
                        pool,
                        available_ids[:gpu_count],
                    )
                )
            if not fitting:
                rejections.append(
                    {
                        "project": project_key,
                        "row_id": row_id,
                        "reason": "no_global_compatible_resource_pool",
                        "details": fit_reasons[:5],
                    }
                )
                continue
            _, pool_id, pool, concrete_ids = min(fitting, key=lambda item: item[0])
            remaining_by_pool[pool_id] -= gpu_count
            allocated_resource_ids.update(concrete_ids)
            assigned_slots_by_project[project_key] = assigned_slots_by_project.get(project_key, 0) + gpu_count
            assignments.append(
                {
                    "assignment_index": len(assignments),
                    "claimable_first": False,
                    "project": project_key,
                    "queue_path": candidate["queue_path"],
                    "queue_revision": candidate["queue_revision"],
                    "queue_sha256": candidate["queue_sha256"],
                    "row_id": row_id,
                    "track_id": row.get("track_id"),
                    "track_role": row.get("track_role"),
                    "evidence_tier": row.get("evidence_tier"),
                    "pool_id": pool_id,
                    "backend": pool.get("backend"),
                    "execution_route": pool.get("execution_route") or pool.get("backend"),
                    "account_ref": pool.get("account_ref") or pool.get("account"),
                    "host_ref": pool.get("host_ref") or pool.get("host"),
                    "node_ref": pool.get("node_ref"),
                    "gpu_count": gpu_count,
                    "allocated_resource_ids": concrete_ids,
                    "decision_class": row.get("decision_class"),
                    "decision_target_refs": decision_target_refs(row),
                    "estimated_gpu_hours": estimated_gpu_hours(row),
                    "fit_confidence": pool.get("fit_confidence") or "verified_snapshot",
                    "resource_snapshot_sha256": snapshot_sha256,
                    "requires_fresh_backend_preflight": True,
                }
            )

    if assignments:
        assignments[0]["claimable_first"] = True
    for assignment in assignments:
        assignment["assignment_sha256"] = assignment_semantic_sha256(assignment)
    schedule = {
        "schema_version": 1,
        "kind": "global_resource_schedule",
        "generated_at": now_iso(),
        "resource_snapshot_ref": resource_snapshot_ref or str(resource_snapshot.get("source_ref") or ""),
        "resource_snapshot_sha256": snapshot_sha256,
        "resource_snapshot_checked_at": resource_snapshot.get("checked_at"),
        "projects": project_records,
        "frontier_summaries": frontier_summaries,
        "assignments": assignments,
        "rejections": sorted(
            rejections,
            key=lambda item: (
                str(item.get("project") or ""),
                str(item.get("row_id") or ""),
                str(item.get("reason") or ""),
            ),
        ),
        "remaining_pool_slots": remaining_by_pool,
        "requires_resource_refresh": bool(assignments),
        "reason": "selected" if assignments else "no_admissible_global_assignment",
        "authority_boundary": "read-only proposal; only the first hashed assignment may be claimed",
    }
    schedule["global_schedule_sha256"] = schedule_semantic_sha256(schedule)
    return {"ok": True, **schedule}


def selection_ref(payload: dict[str, Any]) -> str:
    return str(payload.get("selection_fingerprint") or payload.get("selected_primary_ref") or "").strip()


def payload_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["tracks", "rows", "track_plans", "decisions"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def strict_launch_errors(row: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    for field in LAUNCH_IDENTITY_FIELDS:
        if field == "parallel_safe":
            if not isinstance(row.get(field), bool):
                errors.append(f"{prefix}: {field} must be explicit boolean for launch")
        elif not truthy(row.get(field)):
            errors.append(f"{prefix}: missing launch identity field {field}")
    if not selection_ref(row):
        errors.append(f"{prefix}: missing launch identity field selection_fingerprint or selected_primary_ref")
    decision_class = str(row.get("decision_class") or "")
    if decision_class and decision_class not in ACQUISITION_ORDER:
        errors.append(f"{prefix}: invalid decision_class {decision_class!r}")
    routes = canonical_outcome_routes(row.get("outcome_routes"))
    if not routes:
        errors.append(f"{prefix}: missing launch identity field outcome_routes")
    else:
        for key in OUTCOME_ROUTE_KEYS:
            if not truthy(routes.get(key)):
                errors.append(f"{prefix}: outcome_routes.{key} is required for launch")

    external = row.get("external_identity") if isinstance(row.get("external_identity"), dict) else {}

    def external_value(field: str) -> Any:
        return row.get(field) if truthy(row.get(field)) else external.get(field)

    external_mode = str(row.get("evidence_source_mode") or external.get("evidence_source_mode") or "").strip()
    external_fields_present = any(
        truthy(external_value(field))
        for field in (
            "external_campaign_ref",
            "external_campaign_sha256",
            "external_candidate_id",
            "protected_commitment_sha256",
        )
    )
    if external_mode == "external_material" or external_fields_present:
        campaign_ref = str(external_value("external_campaign_ref") or "").strip()
        campaign_sha = str(external_value("external_campaign_sha256") or "").strip()
        candidate_id = str(external_value("external_candidate_id") or "").strip()
        commitment_sha = str(external_value("protected_commitment_sha256") or "").strip()
        if campaign_ref != EXTERNAL_CAMPAIGN_REF:
            errors.append(f"{prefix}: external_campaign_ref must be {EXTERNAL_CAMPAIGN_REF}")
        if not SHA256_RE.fullmatch(campaign_sha):
            errors.append(f"{prefix}: external_campaign_sha256 must be a lowercase 64-hex digest")
        if not candidate_id:
            errors.append(f"{prefix}: external_candidate_id is required for external_material launch")
        if not SHA256_RE.fullmatch(commitment_sha):
            errors.append(f"{prefix}: protected_commitment_sha256 must be a lowercase 64-hex digest")
        if candidate_id and candidate_id in {
            str(row.get("selected_idea_id") or "").strip(),
            str(row.get("track_id") or "").strip(),
        }:
            errors.append(
                f"{prefix}: external_candidate_id must remain distinct from selected_idea_id and track_id"
            )
        route = row_execution_route(row)
        request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
        request_backend = str(request.get("backend") or "").strip().lower()
        if route not in EXECUTION_ROUTES:
            errors.append(f"{prefix}: external_material execution_route must be one of {sorted(EXECUTION_ROUTES)}")
        if request_backend != route:
            errors.append(
                f"{prefix}: resource_request.backend must exactly match execution_route for external_material launch"
            )
    return errors


def project_authority_errors(project: Path, row: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    base = project / ".autoreskill"
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json")
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json")
    track_id = str(row.get("track_id") or "")
    idea_id = str(row.get("selected_idea_id") or "")
    branch_id = str(row.get("branch_id") or "")
    row_ref = selection_ref(row)

    if not matrix:
        errors.append(f"{prefix}: track plan authority is missing")
        return errors
    matrix_rows = payload_rows(matrix)
    matching = [item for item in matrix_rows if str(item.get("track_id") or "") == track_id]
    if not matching:
        errors.append(f"{prefix}: track_id {track_id!r} is absent from TRACK_PLAN_MATRIX.json")
        return errors
    plan_row = matching[-1]
    if matrix.get("schema_version") == 3 and plan_row.get("planning_admitted") is not True:
        errors.append(f"{prefix}: TRACK_PLAN_MATRIX track is not planning_admitted")
    if str(plan_row.get("idea_id") or "") != idea_id:
        errors.append(f"{prefix}: selected_idea_id does not match TRACK_PLAN_MATRIX track")
    if truthy(plan_row.get("branch_id")) and str(plan_row.get("branch_id")) != branch_id:
        errors.append(f"{prefix}: branch_id does not match TRACK_PLAN_MATRIX track")
    contract = plan_row.get("hypothesis_contract") if isinstance(plan_row.get("hypothesis_contract"), dict) else {}
    if truthy(contract.get("causal_signature")) and str(contract.get("causal_signature")) != str(row.get("causal_signature")):
        errors.append(f"{prefix}: causal_signature does not match TRACK_PLAN_MATRIX hypothesis contract")
    expected_refs = [selection_ref(matrix), selection_ref(plan_row), selection_ref(ledger)]
    for item in payload_rows(ledger):
        if str(item.get("idea_id") or "") == idea_id and selection_ref(item):
            expected_refs.append(selection_ref(item))
    expected_refs = [value for value in expected_refs if value]
    if expected_refs and row_ref not in set(expected_refs):
        errors.append(f"{prefix}: stale selection fingerprint; expected one of {sorted(set(expected_refs))}")
    lifecycle = str(plan_row.get("idea_lifecycle_status") or "").strip().lower()
    belief = str(contract.get("belief_state") or "").strip().lower()
    if lifecycle in {"parked", "killed", "retired"} or belief in {"refuted", "retired"}:
        errors.append(f"{prefix}: selected track is terminal or parked")
    plan_role = str(plan_row.get("track_role") or "").strip().lower()
    if plan_role and str(row.get("track_role") or "").strip().lower() != plan_role:
        errors.append(f"{prefix}: track_role must match TRACK_PLAN_MATRIX track")
    plan_ceiling = str(plan_row.get("evidence_tier_ceiling") or "").strip()
    if plan_ceiling and str(row.get("evidence_tier_ceiling") or "").strip() != plan_ceiling:
        errors.append(f"{prefix}: evidence_tier_ceiling must match TRACK_PLAN_MATRIX track")
    plan_claim_role = str(plan_row.get("claim_role") or "").strip()
    row_claim_role = str(row.get("claim_role") or "").strip()
    if plan_claim_role and row_claim_role != plan_claim_role:
        errors.append(f"{prefix}: claim_role must match TRACK_PLAN_MATRIX track")
    if row_claim_role and row_claim_role not in VALID_CLAIM_ROLES:
        errors.append(f"{prefix}: invalid claim_role {row_claim_role!r}")

    program_mode = str(program.get("enforcement_mode") or "legacy").strip().lower()
    program_scope = str(program.get("claim_scope") or "dataset_specific").strip().lower()
    if program_mode == "enforced":
        binding = program_contract_binding(program)
        for field, expected in binding.items():
            if row.get(field) != expected:
                errors.append(f"{prefix}: {field} does not match PROGRAM_CLAIM_CONTRACT.json")
        if program_scope == "cross_dataset_method" and row_claim_role == "method_candidate":
            review = read_json(base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json")
            parameter_contract = review.get("parameter_transfer_contract") if isinstance(review, dict) else None
            datasets = required_dataset_ids(program, review if isinstance(review, dict) else plan_row)
            validation = validate_parameter_transfer_contract(parameter_contract, datasets)
            if not validation["complete"]:
                errors.extend(f"{prefix}: {item}" for item in validation.get("errors") or [])
            expected_parameter_hash = str(
                parameter_contract.get("parameter_transfer_contract_sha256")
                if isinstance(parameter_contract, dict)
                else ""
            )
            if str(row.get("parameter_transfer_contract_sha256") or "") != expected_parameter_hash:
                errors.append(f"{prefix}: parameter_transfer_contract_sha256 is stale or missing")
            stage = row.get("validation_stage")
            stage2_role = str(row.get("stage2_role") or "")
            requires_profile = stage2_role == "stage2_method_screen" or (
                isinstance(stage, int) and not isinstance(stage, bool) and stage >= 3
            )
            if requires_profile and isinstance(parameter_contract, dict):
                profile_ref = str(row.get("frozen_parameter_profile_ref") or review.get("frozen_parameter_profile_ref") or "")
                profile = read_json(base / profile_ref) if profile_ref else {}
                profile_validation = validate_frozen_profile(profile, parameter_contract, datasets)
                if not profile_validation["complete"]:
                    errors.extend(f"{prefix}: {item}" for item in profile_validation.get("errors") or [])
                expected_profile_hash = str(profile.get("frozen_parameter_profile_sha256") or "")
                if str(row.get("frozen_parameter_profile_sha256") or "") != expected_profile_hash:
                    errors.append(f"{prefix}: frozen_parameter_profile_sha256 is stale or missing")
    is_primary = plan_role == "primary" or (
        matrix.get("schema_version") == 2
        and (
            plan_row.get("selected_for_review") is True
            or str(ledger.get("selected_primary_idea_id") or "") == idea_id
        )
    )
    if not is_primary:
        if plan_row.get("planning_admitted") is not True:
            errors.append(f"{prefix}: alternate track is not planning_admitted")
        if plan_ceiling != "pilot_only":
            errors.append(f"{prefix}: alternate track must have evidence_tier_ceiling=pilot_only")
        if str(row.get("evidence_tier") or "").strip() != "pilot_only" or row.get("claim_eligible") is not False:
            errors.append(f"{prefix}: alternate queue row must remain non-claim-bearing pilot_only evidence")
        if str(row.get("launch_mode") or "").strip() == "claim_promotion":
            errors.append(f"{prefix}: alternate queue row cannot use claim_promotion launch mode")
        if str(row.get("decision_class") or "").strip() == "close_required_claim":
            errors.append(f"{prefix}: alternate queue row cannot close a required claim")
    return errors


def submit_state_errors(row: dict[str, Any], prefix: str, status: str) -> list[str]:
    """Validate durable submit state without interpreting backend truth."""

    errors: list[str] = []
    if status not in {"submitting", "needs_sync", "running"}:
        return errors
    intent = row.get("backend_submit_intent") if isinstance(row.get("backend_submit_intent"), dict) else {}
    if not intent:
        return [f"{prefix}: status submitting requires backend_submit_intent"] if status == "submitting" else []
    intent_sha256 = canonical_payload_sha256(intent)
    if str(row.get("backend_submit_intent_sha256") or "") != intent_sha256:
        errors.append(f"{prefix}: backend_submit_intent_sha256 does not match the stored intent")
    for field in [
        "submit_attempt_id",
        "backend_idempotency_key",
        "anonymous_trace_id",
        "launch_identity_hash",
        "script_or_command_sha256",
        "preflight_sha256",
        "pool_id",
        "execution_route",
    ]:
        if not truthy(intent.get(field)):
            errors.append(f"{prefix}: backend_submit_intent.{field} is required")
    if str(intent.get("launch_identity_hash") or "") != str(row.get("launch_identity_hash") or ""):
        errors.append(f"{prefix}: backend_submit_intent launch identity conflicts with the row")

    receipt = row.get("backend_submit_receipt") if isinstance(row.get("backend_submit_receipt"), dict) else {}
    observations = [item for item in row.get("backend_observations", []) if isinstance(item, dict)]
    native_observation = next(
        (
            item
            for item in reversed(observations)
            if truthy(item.get("native_id"))
            and str(item.get("submit_attempt_id") or "") == str(intent.get("submit_attempt_id") or "")
            and str(item.get("anonymous_trace_id") or "") == str(intent.get("anonymous_trace_id") or "")
        ),
        None,
    )
    if receipt:
        if str(row.get("backend_submit_receipt_sha256") or "") != canonical_payload_sha256(receipt):
            errors.append(f"{prefix}: backend_submit_receipt_sha256 does not match the stored receipt")
        for field in ["submit_attempt_id", "backend_idempotency_key", "anonymous_trace_id", "launch_identity_hash"]:
            if str(receipt.get(field) or "") != str(intent.get(field) or ""):
                errors.append(f"{prefix}: backend_submit_receipt.{field} conflicts with the intent")
    if status == "submitting" and receipt:
        errors.append(f"{prefix}: a row with a submit receipt must not remain submitting")
    if status in {"needs_sync", "running"} and not receipt and native_observation is None:
        errors.append(f"{prefix}: status {status} requires a submit receipt or native-id backend observation")
    if status == "running" and not isinstance(row.get("resource_allocation"), dict):
        errors.append(f"{prefix}: running submit state requires resource_allocation")
    return errors


def validation_stage_errors(row: dict[str, Any], prefix: str, status: str) -> list[str]:
    errors: list[str] = []
    if row.get("validation_stage") is None:
        return errors
    stage = row.get("validation_stage")
    if isinstance(stage, bool) or not isinstance(stage, int) or not 0 <= stage <= 7:
        return [f"{prefix}: validation_stage must be an integer from 0 through 7"]
    active = status in STRICT_LAUNCH_STATUSES
    prerequisites = as_str_list(row.get("validation_prerequisites"))
    reused = as_str_list(row.get("reused_canonical_evidence_refs"))
    if active and stage > 0 and not prerequisites and not reused:
        errors.append(f"{prefix}: active validation stage {stage} requires prerequisites or reused canonical evidence")
    evidence_tier = str(row.get("evidence_tier") or "").strip()
    if active and stage in {0, 1} and evidence_tier == "claim_eligible":
        errors.append(f"{prefix}: validation stage {stage} cannot be claim_eligible")
    if active and stage == 2:
        if evidence_tier != "pilot_only":
            errors.append(f"{prefix}: validation stage 2 must remain pilot_only")
        seed_count = row.get("seed_count")
        seeds = row.get("seeds") if isinstance(row.get("seeds"), list) else []
        if seed_count not in {None, 1} or len(seeds) > 1:
            errors.append(f"{prefix}: validation stage 2 uses exactly one random seed")
        stage2_role = str(row.get("stage2_role") or "").strip()
        has_parameter_identity = truthy(row.get("parameter_transfer_contract_sha256"))
        if has_parameter_identity and stage2_role not in {"stage2_parameter_probe", "stage2_method_screen"}:
            errors.append(f"{prefix}: parameter-aware Stage 2 requires stage2_role")
        if stage2_role == "stage2_parameter_probe":
            if str(row.get("role") or "") != "parameter_probe":
                errors.append(f"{prefix}: stage2_parameter_probe requires role=parameter_probe")
            for field in ["parameter_probe_kind", "parameter_calibration_group_id", "parameter_value"]:
                if not truthy(row.get(field)):
                    errors.append(f"{prefix}: stage2_parameter_probe requires {field}")
            if str(row.get("parameter_probe_kind") or "") not in VALID_PROBE_KINDS:
                errors.append(f"{prefix}: parameter_probe_kind is invalid")
            if isinstance(row.get("seed"), (list, dict)) or not truthy(row.get("seed")):
                errors.append(f"{prefix}: stage2_parameter_probe requires one scalar seed")
            if str(row.get("parameter_profile_status") or "") not in {"audit_pending", "calibrating"}:
                errors.append(f"{prefix}: parameter probe requires audit_pending or calibrating profile status")
        if stage2_role == "stage2_method_screen":
            if str(row.get("parameter_profile_status") or "") != "frozen":
                errors.append(f"{prefix}: stage2_method_screen requires a frozen parameter profile")
            for field in ["frozen_parameter_profile_ref", "frozen_parameter_profile_sha256", "paired_dataset_group_id"]:
                if not truthy(row.get(field)):
                    errors.append(f"{prefix}: stage2_method_screen requires {field}")
    if active and stage >= 3 and truthy(row.get("parameter_transfer_contract_sha256")):
        if str(row.get("parameter_profile_status") or "") != "frozen":
            errors.append(f"{prefix}: Stage {stage} requires parameter_profile_status=frozen")
        for field in ["frozen_parameter_profile_ref", "frozen_parameter_profile_sha256"]:
            if not truthy(row.get(field)):
                errors.append(f"{prefix}: Stage {stage} requires {field}")
    if active and stage == 5:
        if str(row.get("tuning_target") or "").strip().lower() != "mechanism_parameterization":
            errors.append(f"{prefix}: validation stage 5 is only mechanism_parameterization")
        for field in [
            "sensitivity_question",
            "eligible_belief_states",
            "current_belief_state",
            "baseline_freeze_or_calibration_ref",
            "remaining_hpo_gpu_hours",
        ]:
            if not truthy(row.get(field)):
                errors.append(f"{prefix}: validation stage 5 requires {field}")
        belief = str(row.get("current_belief_state") or "").strip().lower()
        eligible = {value.strip().lower() for value in as_str_list(row.get("eligible_belief_states"))}
        if belief and belief not in eligible:
            errors.append(f"{prefix}: current_belief_state is not Stage-5 eligible")
        if belief in {"terminal_negative", "refuted", "retired", "killed"}:
            errors.append(f"{prefix}: a terminal-negative mechanism cannot enter Stage 5")
        hpo = row.get("hpo_search_policy") if isinstance(row.get("hpo_search_policy"), dict) else {}
        dimensions = (
            hpo.get("search_space_audit", {}).get("dimensions")
            if isinstance(hpo.get("search_space_audit"), dict)
            else None
        )
        if not isinstance(dimensions, list) or not 3 <= len(dimensions) <= 6:
            errors.append(f"{prefix}: validation stage 5 requires a bounded 3-6 dimensional search space")
        if str(row.get("claim_scope") or "") == "cross_dataset_method":
            group_hpo = hpo.get("dataset_group_hpo") if isinstance(hpo.get("dataset_group_hpo"), dict) else {}
            dataset_ids = as_str_list(group_hpo.get("required_dataset_ids"))
            if len(set(dataset_ids)) < 2:
                errors.append(f"{prefix}: cross-dataset Stage 5 requires at least two dataset-group legs")
            if group_hpo.get("robust_objective") != "maximin_signed_delta":
                errors.append(f"{prefix}: cross-dataset Stage 5 requires maximin_signed_delta")
            if group_hpo.get("incomplete_trial_is_infeasible") is not True:
                errors.append(f"{prefix}: incomplete cross-dataset HPO trials must be infeasible")
            required_dataset_set = set(dataset_ids)
            for ref_field in ["stage2_support_ref_by_dataset", "full_budget_support_ref_by_dataset"]:
                refs = group_hpo.get(ref_field) if isinstance(group_hpo.get(ref_field), dict) else {}
                if set(str(key) for key in refs) != required_dataset_set or any(
                    not truthy(value) for value in refs.values()
                ):
                    errors.append(f"{prefix}: cross-dataset Stage 5 requires complete {ref_field}")
            floors = (
                group_hpo.get("no_regression_constraints_by_dataset")
                if isinstance(group_hpo.get("no_regression_constraints_by_dataset"), dict)
                else {}
            )
            if set(str(key) for key in floors) != required_dataset_set or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))
                for value in floors.values()
            ):
                errors.append(f"{prefix}: cross-dataset Stage 5 requires one finite no-regression floor per dataset")
            for hash_field in ["frozen_parameter_profile_sha256", "parameter_transfer_contract_sha256"]:
                if not SHA256_RE.fullmatch(str(group_hpo.get(hash_field) or "").strip().lower()):
                    errors.append(f"{prefix}: cross-dataset Stage 5 requires {hash_field}")
    if active and stage == 6:
        if not truthy(row.get("baseline_freeze_ref")):
            errors.append(f"{prefix}: validation stage 6 requires baseline_freeze_ref")
        if str(row.get("comparison_source") or "") != "vs matched reproduced baseline":
            errors.append(f"{prefix}: validation stage 6 requires a matched reproduced baseline comparison")
        seeds = as_str_list(row.get("seeds"))
        if not seeds or len(set(seeds)) > 3:
            errors.append(f"{prefix}: validation stage 6 requires one to three unique paired seeds")
        seed_count = row.get("seed_count")
        if seed_count is not None and (isinstance(seed_count, bool) or seed_count != len(set(seeds))):
            errors.append(f"{prefix}: validation stage 6 seed_count must match the unique paired seeds")
        if not truthy(row.get("experiment_family_id")) or not truthy(row.get("replication_group_id")):
            errors.append(f"{prefix}: validation stage 6 requires experiment_family_id and replication_group_id")
    if active and stage == 7:
        if str(row.get("role") or "") != "combo":
            errors.append(f"{prefix}: validation stage 7 must use role=combo")
        if not as_str_list(row.get("component_innovation_ids")):
            errors.append(f"{prefix}: validation stage 7 requires component_innovation_ids")
        if not as_str_list(row.get("supported_component_row_refs")):
            errors.append(f"{prefix}: validation stage 7 requires supported_component_row_refs")
        strategy = str(row.get("combination_search_strategy") or "").strip().lower()
        if strategy not in {"greedy", "beam"}:
            errors.append(f"{prefix}: validation stage 7 requires bounded greedy or beam search")
        if positive_int(row.get("combination_candidate_budget")) is None:
            errors.append(f"{prefix}: validation stage 7 requires a positive combination_candidate_budget")
    return errors


def validate_queue(queue: dict[str, Any], project: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {
        "row_count": 0,
        "ready_count": 0,
        "submitting_count": 0,
        "running_count": 0,
        "needs_sync_count": 0,
        "parallel_ready_count": 0,
        "launch_running_count": 0,
        "migration_required": False,
    }

    if not queue:
        errors.append("NEXT_EXPERIMENT_QUEUE.json is missing or empty")
        return {"ok": False, "errors": errors, "warnings": warnings, "details": details}

    schema_version = queue.get("schema_version")
    if schema_version not in {1, 2}:
        errors.append("schema_version must be 1 or 2")
    strict_schema = schema_version == 2
    if schema_version == 1:
        details["migration_required"] = True
        warnings.append("schema_version=1 is readable legacy state; migrate before the next ready/running transition")
    if strict_schema and (not isinstance(queue.get("queue_revision"), int) or isinstance(queue.get("queue_revision"), bool)):
        errors.append("queue_revision must be an integer for schema_version=2")

    rows = queue.get("rows")
    if not isinstance(rows, list):
        errors.append("rows must be a list")
        rows = []

    policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    max_seed = positive_int(policy.get("max_random_seed_count", 3))
    if max_seed is None or max_seed > 3:
        errors.append("policy.max_random_seed_count must be a positive integer <= 3")
    target_dataset_min = policy.get("target_dataset_count_min", 2)
    if not isinstance(target_dataset_min, (int, float)) or target_dataset_min < 1:
        target_dataset_min = 2
    max_active_combo = policy.get("max_active_combo_candidates_per_dataset", 3)
    if not isinstance(max_active_combo, (int, float)) or max_active_combo < 1:
        max_active_combo = 3
    max_new_launches = policy.get("max_new_launches_per_cycle", "auto")
    if str(max_new_launches).strip().lower() != "auto" and positive_int(max_new_launches) is None:
        errors.append("policy.max_new_launches_per_cycle must be 'auto' or a positive integer")
    if positive_int(policy.get("absolute_max_new_launches_per_cycle", 16)) is None:
        errors.append("policy.absolute_max_new_launches_per_cycle must be a positive integer")
    max_slots_in_flight = policy.get("max_gpu_slots_in_flight")
    if max_slots_in_flight is not None and positive_int(max_slots_in_flight) is None:
        errors.append("policy.max_gpu_slots_in_flight must be a positive integer when configured")
    max_hours_in_flight = policy.get("max_gpu_hours_in_flight")
    if max_hours_in_flight is not None:
        parsed_hours = numeric(max_hours_in_flight, -1.0)
        if isinstance(max_hours_in_flight, bool) or not math.isfinite(parsed_hours) or parsed_hours <= 0:
            errors.append("policy.max_gpu_hours_in_flight must be a positive finite number when configured")
    portfolio_capacity = positive_int(policy.get("portfolio_capacity_target", 4))
    if portfolio_capacity is None or portfolio_capacity > 4:
        errors.append("policy.portfolio_capacity_target must be a positive integer <= 4")
    method_portfolio_target = positive_int(policy.get("method_portfolio_target", 2))
    if method_portfolio_target is None or (
        portfolio_capacity is not None and method_portfolio_target > portfolio_capacity
    ):
        errors.append("policy.method_portfolio_target must be positive and <= portfolio_capacity_target")
    portfolio_budget = policy.get("portfolio_gpu_hour_budget")
    if portfolio_budget is not None:
        parsed_budget = numeric(portfolio_budget, -1.0)
        if isinstance(portfolio_budget, bool) or not math.isfinite(parsed_budget) or parsed_budget <= 0:
            errors.append("policy.portfolio_gpu_hour_budget must be a positive finite number when configured")
    if positive_int(policy.get("ready_frontier_multiplier", 2)) is None:
        errors.append("policy.ready_frontier_multiplier must be a positive integer")
    if positive_int(policy.get("max_ready_frontier_rows", 32)) is None:
        errors.append("policy.max_ready_frontier_rows must be a positive integer")
    pending_scope = str(policy.get("pending_scope") or "resource_pool")
    if pending_scope not in {"resource_pool", "shared_limit", "global_legacy"}:
        errors.append("policy.pending_scope must be resource_pool, shared_limit, or global_legacy")
    admission_scope = str(policy.get("admission_scope") or "project").strip().lower()
    if admission_scope not in {"project", "global"}:
        errors.append("policy.admission_scope must be project or global")

    program: dict[str, Any] = {}
    if project is not None:
        program = read_json(project / ".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json")
    if str(program.get("enforcement_mode") or "legacy") == "enforced":
        binding = program_contract_binding(program)
        for field, expected in binding.items():
            if queue.get(field) != expected:
                errors.append(f"queue.{field} does not match PROGRAM_CLAIM_CONTRACT.json")
        search_budget = program.get("search_budget") if isinstance(program.get("search_budget"), dict) else {}
        promotion = program.get("promotion_rule") if isinstance(program.get("promotion_rule"), dict) else {}
        projections = {
            "portfolio_capacity_target": search_budget.get("portfolio_capacity_target"),
            "method_portfolio_target": search_budget.get("method_portfolio_target"),
            "max_random_seed_count": promotion.get("max_random_seeds"),
            "portfolio_gpu_hour_budget": search_budget.get("gpu_hour_budget"),
        }
        for field, expected in projections.items():
            if policy.get(field) != expected:
                errors.append(f"policy.{field} must equal the enforced program-claim projection")

    snapshot = queue.get("resource_snapshot") if isinstance(queue.get("resource_snapshot"), dict) else {}
    pools = snapshot.get("pools")
    if pools is not None and not isinstance(pools, list):
        errors.append("resource_snapshot.pools must be a list when present")
        pools = []
    seen_pool_ids: set[str] = set()
    for index, pool in enumerate(pools or []):
        if not isinstance(pool, dict):
            errors.append(f"resource_snapshot.pools[{index}] must be an object")
            continue
        pool_id = str(pool.get("pool_id") or "").strip()
        if not pool_id:
            errors.append(f"resource_snapshot.pools[{index}]: pool_id is required")
        elif pool_id in seen_pool_ids:
            errors.append(f"resource_snapshot.pools[{index}]: duplicate pool_id {pool_id}")
        seen_pool_ids.add(pool_id)
        status = str(pool.get("status") or "").strip().lower()
        if status not in AVAILABLE_POOL_STATUSES | BLOCKED_POOL_STATUSES:
            errors.append(f"resource_snapshot.pools[{index}]: unsupported status {status!r}")
        slots_value = pool.get("launch_slots")
        if slots_value is not None and nonnegative_int(slots_value) is None:
            errors.append(f"resource_snapshot.pools[{index}]: launch_slots must be a nonnegative integer")
        for compatibility_key in ("available_gpu_slots", "idle_gpu_count", "free_gpu_count"):
            compatibility_value = pool.get(compatibility_key)
            if compatibility_value is not None and nonnegative_int(compatibility_value) is None:
                errors.append(
                    f"resource_snapshot.pools[{index}]: {compatibility_key} must be a nonnegative integer"
                )
        profile_hashes = pool.get("execution_profile_sha256s")
        if pool.get("capability_enforced") is True:
            if not isinstance(profile_hashes, list):
                errors.append(
                    f"resource_snapshot.pools[{index}]: capability_enforced pool requires execution_profile_sha256s list"
                )
            elif any(not SHA256_RE.fullmatch(str(value or "").strip().lower()) for value in profile_hashes):
                errors.append(
                    f"resource_snapshot.pools[{index}]: execution_profile_sha256s must contain lowercase 64-hex digests"
                )

    for compatibility_key in ("available_gpu_slots", "idle_gpu_count", "free_gpu_count", "launch_slots"):
        compatibility_value = snapshot.get(compatibility_key)
        if compatibility_value is not None and nonnegative_int(compatibility_value) is None:
            errors.append(f"resource_snapshot.{compatibility_key} must be a nonnegative integer")

    seen_ids: set[str] = set()
    rows_by_id: dict[str, dict[str, Any]] = {}
    single_datasets_by_innovation: dict[str, set[str]] = {}
    active_combo_count_by_dataset: dict[str, int] = {}
    family_seeds: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"rows[{index}] must be an object")
            continue
        prefix = str(row.get("id") or f"rows[{index}]")
        missing = sorted(field for field in REQUIRED_ROW_FIELDS if not truthy(row.get(field)))
        for field in missing:
            errors.append(f"{prefix}: missing required field {field}")

        row_id = str(row.get("id") or "")
        if row_id:
            if row_id in seen_ids:
                errors.append(f"{row_id}: duplicate row id")
            seen_ids.add(row_id)
            rows_by_id[row_id] = row

        status = str(row.get("status") or "")
        role = str(row.get("role") or "")
        if status and status not in VALID_STATUSES:
            errors.append(f"{prefix}: invalid status {status!r}")
        if role and role not in VALID_ROLES:
            errors.append(f"{prefix}: invalid role {role!r}")

        try:
            float(row.get("priority"))
        except (TypeError, ValueError):
            errors.append(f"{prefix}: priority must be numeric")

        comparison = row.get("comparison_source")
        if truthy(comparison) and str(comparison) not in VALID_COMPARISONS:
            errors.append(f"{prefix}: invalid comparison_source {comparison!r}")

        launch_mode = row.get("launch_mode")
        if truthy(launch_mode) and str(launch_mode) not in VALID_LAUNCH_MODES:
            errors.append(f"{prefix}: invalid launch_mode {launch_mode!r}")

        is_launch_row = role != "monitor_sync" and str(launch_mode or "") != "monitor_only"
        if is_launch_row and status in STRICT_LAUNCH_STATUSES:
            launch_errors = strict_launch_errors(row, prefix)
            if strict_schema:
                errors.extend(launch_errors)
                if project is not None and not launch_errors:
                    errors.extend(project_authority_errors(project, row, prefix))
            elif launch_errors:
                details["migration_required"] = True
                warnings.extend(f"legacy migration: {item}" for item in launch_errors)
        if is_launch_row and status in {"ready", "planned"}:
            if not truthy(row.get("resource_request")):
                warnings.append(f"{prefix}: ready launch row should record resource_request")
            if row.get("parallel_safe") is False or row.get("requires_serial") is True:
                warnings.append(f"{prefix}: ready launch row is marked serial and cannot fill idle GPUs while another row runs")
            elif not row_blocker_present(row):
                details["parallel_ready_count"] += 1
        if is_launch_row and status == "running":
            details["launch_running_count"] += 1
            if not truthy(row.get("resource_allocation")):
                warnings.append(f"{prefix}: running launch row should record resource_allocation")
        if strict_schema and is_launch_row and status in {"planned", "submitting", "needs_sync", "running"}:
            for field in ["lease_owner", "lease_acquired_at", "lease_expires_at"]:
                if not truthy(row.get(field)):
                    errors.append(f"{prefix}: {field} required for leased launch row")
        execution_profile_sha256 = str(row.get("execution_profile_sha256") or "").strip().lower()
        if execution_profile_sha256 and not SHA256_RE.fullmatch(execution_profile_sha256):
            errors.append(f"{prefix}: execution_profile_sha256 must be a lowercase 64-hex digest")
        errors.extend(submit_state_errors(row, prefix, status))
        errors.extend(validation_stage_errors(row, prefix, status))
        if status in {"needs_sync", "running"} and not isinstance(row.get("backend_submit_intent"), dict):
            warnings.append(
                f"{prefix}: legacy {status} row has no durable submit intent; reconcile it before any retry or release"
            )

        seed_count = row.get("seed_count")
        if isinstance(seed_count, (int, float)) and seed_count > 3:
            errors.append(f"{prefix}: seed_count must be <= 3")
        seeds = row.get("seeds")
        if isinstance(seeds, list) and len(seeds) > 3:
            errors.append(f"{prefix}: seeds list must contain at most 3 seeds")
        request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
        if truthy(row.get("resource_request")) and not isinstance(row.get("resource_request"), dict):
            errors.append(f"{prefix}: resource_request must be an object")
        gpu_count = request.get("gpu_count")
        if gpu_count is not None and positive_int(gpu_count) is None:
            errors.append(f"{prefix}: resource_request.gpu_count must be a positive integer")
        row_hours = estimated_gpu_hours(row)
        if (row.get("estimated_gpu_hours") is not None or request.get("estimated_gpu_hours") is not None) and row_hours is None:
            errors.append(f"{prefix}: estimated_gpu_hours must be nonnegative")

        evidence_tier = str(row.get("evidence_tier") or "").strip()
        if evidence_tier and evidence_tier not in VALID_EVIDENCE_TIERS:
            errors.append(f"{prefix}: evidence_tier must be pilot_only or claim_eligible")
        claim_closing = str(row.get("decision_class") or "") == "close_required_claim" or str(row.get("launch_mode") or "") == "claim_promotion"
        baseline_calibration = role == "baseline_calibration" or str(row.get("tuning_target") or "") == "baseline_calibration"
        if evidence_tier == "pilot_only" and claim_closing and not baseline_calibration:
            errors.append(f"{prefix}: pilot_only evidence cannot close or promote a claim")
        if baseline_calibration:
            if evidence_tier != "pilot_only":
                errors.append(f"{prefix}: baseline_calibration must remain pilot_only")
            if row.get("validation_stage") == 5:
                errors.append(f"{prefix}: baseline_calibration is separate work and must not use innovation validation_stage=5")
        if evidence_tier == "claim_eligible" and claim_closing and not truthy(row.get("baseline_freeze_ref")):
            errors.append(f"{prefix}: claim-eligible claim closure requires baseline_freeze_ref")
        refs = row.get("decision_target_refs")
        if refs is not None and not isinstance(refs, (str, list, tuple, set)):
            errors.append(f"{prefix}: decision_target_refs must be a string or list")
        if is_launch_row and status in STRICT_LAUNCH_STATUSES and not decision_target_refs(row):
            warnings.append(f"{prefix}: add decision_target_refs so scheduler impact is artifact-derived")

        family_id = str(row.get("experiment_family_id") or "").strip()
        replication_group = str(row.get("replication_group_id") or "").strip()
        row_seeds = as_str_list(row.get("seeds"))
        for key in ("seed", "random_seed"):
            if row.get(key) is not None:
                row_seeds.extend(as_str_list(row.get(key)))
        if replication_group and not family_id:
            warnings.append(f"{prefix}: replication_group_id should be paired with experiment_family_id for the three-seed cap")
        if family_id and row_seeds and status not in {"dropped", "superseded"}:
            family_seeds.setdefault(family_id, set()).update(row_seeds)

        unlock = row.get("unlock_rules") if isinstance(row.get("unlock_rules"), dict) else {}
        active_status = status in {"ready", "planned", "submitting", "running", "needs_sync", "terminal_positive"}
        if role == "single_innovation" and active_status:
            innovation_id = str(row.get("innovation_id") or row.get("variant") or "").strip()
            if not truthy(row.get("innovation_id")):
                warnings.append(f"{prefix}: single_innovation row should record innovation_id")
            dataset = str(row.get("dataset") or "").strip()
            if innovation_id and dataset:
                single_datasets_by_innovation.setdefault(innovation_id, set()).add(dataset)
            if status in {"ready", "planned", "submitting", "running"} and not truthy(row.get("baseline_anchor")):
                warnings.append(f"{prefix}: single_innovation row should record baseline_anchor")
            if status in {"ready", "planned", "submitting", "running"} and not truthy(row.get("comparison_source")):
                warnings.append(f"{prefix}: single_innovation row should record comparison_source")
        if role == "combo" and status in {"ready", "planned", "submitting", "running"}:
            has_gate = truthy(unlock.get("requires_positive_rows")) or truthy(unlock.get("requires_nonnegative_rows"))
            if not has_gate and row.get("allow_ungated_combo") is not True:
                warnings.append(f"{prefix}: combo row should name positive/nonnegative single-innovation gates")
            if not truthy(row.get("component_innovation_ids")):
                warnings.append(f"{prefix}: combo row should record component_innovation_ids")
            dataset = str(row.get("dataset") or "").strip()
            if dataset:
                active_combo_count_by_dataset[dataset] = active_combo_count_by_dataset.get(dataset, 0) + 1
        if status == "running" and not truthy(row.get("owner_thread_id")):
            warnings.append(f"{prefix}: running row should record owner_thread_id")
        if status in {"running", "needs_sync", "terminal_positive", "terminal_negative"} and not truthy(row.get("evidence_paths")):
            warnings.append(f"{prefix}: status {status} should link evidence_paths")

        details["row_count"] += 1
        if status == "ready":
            details["ready_count"] += 1
        elif status == "submitting":
            details["submitting_count"] += 1
        elif status == "running":
            details["running_count"] += 1
        elif status == "needs_sync":
            details["needs_sync_count"] += 1

    for row in rows_by_id.values():
        role = str(row.get("role") or "")
        status = str(row.get("status") or "")
        if role != "combo" or status not in {"ready", "planned", "submitting", "running"}:
            continue
        prefix = str(row.get("id") or "")
        unlock = row.get("unlock_rules") if isinstance(row.get("unlock_rules"), dict) else {}
        for field in ("requires_positive_rows", "requires_nonnegative_rows"):
            for ref in as_str_list(unlock.get(field)):
                source = rows_by_id.get(ref)
                if source is None:
                    target = errors if strict_schema else warnings
                    target.append(f"{prefix}: {field} references missing row {ref}")
                    continue
                if str(source.get("role") or "") != "single_innovation":
                    target = errors if strict_schema else warnings
                    target.append(f"{prefix}: {field} should reference single_innovation row {ref}")
                if field == "requires_positive_rows" and str(source.get("status") or "") != "terminal_positive":
                    warnings.append(
                        f"{prefix}: positive component gate {ref} is not terminal_positive; scheduler will keep this row blocked"
                    )
                if field == "requires_nonnegative_rows" and str(source.get("status") or "") not in {"terminal_positive", "superseded"}:
                    warnings.append(
                        f"{prefix}: nonnegative component gate {ref} lacks supported evidence; scheduler will keep this row blocked"
                    )

        if row.get("validation_stage") == 7 and status in STRICT_LAUNCH_STATUSES:
            for ref in as_str_list(row.get("supported_component_row_refs")):
                source = rows_by_id.get(ref)
                if source is None:
                    errors.append(f"{prefix}: supported component row {ref} is missing")
                elif str(source.get("role") or "") != "single_innovation" or str(source.get("status") or "") != "terminal_positive":
                    errors.append(f"{prefix}: supported component row {ref} must be terminal_positive single_innovation evidence")

    for row in rows_by_id.values():
        status = str(row.get("status") or "")
        role = str(row.get("role") or "")
        launch_mode = str(row.get("launch_mode") or "")
        if status not in {"ready", "planned"} or role == "monitor_sync" or launch_mode == "monitor_only":
            continue
        prefix = str(row.get("id") or "")
        refs = as_str_list(row.get("depends_on_rows"))
        unlock = row.get("unlock_rules") if isinstance(row.get("unlock_rules"), dict) else {}
        refs.extend(as_str_list(unlock.get("requires_positive_rows")))
        refs.extend(as_str_list(unlock.get("requires_nonnegative_rows")))
        for ref in refs:
            source = rows_by_id.get(ref)
            if source is None:
                target = errors if strict_schema else warnings
                target.append(f"{prefix}: dependency references missing row {ref}")
                continue
            if str(source.get("status") or "") not in {"terminal_positive", "terminal_negative", "superseded"}:
                warnings.append(f"{prefix}: dependency row {ref} is not terminal yet; scheduler will reject only this row")

    rows_by_track: dict[str, list[dict[str, Any]]] = {}
    for row in rows_by_id.values():
        track_id = str(row.get("track_id") or "").strip()
        if track_id:
            rows_by_track.setdefault(track_id, []).append(row)
    for track_id, track_rows in rows_by_track.items():
        terminal_negative_stage = any(
            str(item.get("status") or "") == "terminal_negative"
            and isinstance(item.get("validation_stage"), int)
            and int(item.get("validation_stage")) >= 2
            for item in track_rows
        )
        stage4_supported = any(
            item.get("validation_stage") == 4
            and str(item.get("status") or "") in {"terminal_positive", "superseded"}
            for item in track_rows
        )
        stage4_open = any(
            item.get("validation_stage") == 4
            and str(item.get("status") or "") in STRICT_LAUNCH_STATUSES
            for item in track_rows
        )
        for item in track_rows:
            stage = item.get("validation_stage")
            status = str(item.get("status") or "")
            if status not in STRICT_LAUNCH_STATUSES or stage not in {5, 6}:
                continue
            prefix = str(item.get("id") or track_id)
            if terminal_negative_stage:
                errors.append(f"{prefix}: terminal-negative track cannot materialize Stage {stage}")
            if stage == 5 and not stage4_supported and not as_str_list(item.get("reused_cross_dataset_evidence_refs")):
                errors.append(f"{prefix}: Stage 5 requires Stage-4 support or explicit reused cross-dataset evidence")
            if stage == 5 and stage4_open:
                errors.append(f"{prefix}: open Stage-4 cross-dataset work outranks Stage-5 HPO")

    if strict_schema:
        for row in rows_by_id.values():
            if str(row.get("status") or "") not in STRICT_LAUNCH_STATUSES:
                continue
            if str(row.get("decision_class") or "") == "optimize_supported_mechanism":
                refs = as_str_list(row.get("mechanism_support_refs"))
                if not refs:
                    errors.append(f"{row.get('id')}: optimize_supported_mechanism requires mechanism_support_refs")
                for ref in refs:
                    source = rows_by_id.get(ref)
                    if source is None or str(source.get("status") or "") != "terminal_positive":
                        errors.append(f"{row.get('id')}: mechanism support ref {ref} is not terminal_positive")

    if details["launch_running_count"] and details["parallel_ready_count"]:
        warnings.append(
            "running experiment rows coexist with independent ready launch rows; do not create a project-level experiment wait until resource fit is checked"
        )

    if policy.get("single_innovation_multi_dataset_first", True) is not False:
        for innovation_id, datasets in sorted(single_datasets_by_innovation.items()):
            if len(datasets) < int(target_dataset_min):
                warnings.append(
                    f"{innovation_id}: single_innovation coverage spans {len(datasets)} dataset(s); "
                    f"generalization/best-performance claims need at least {int(target_dataset_min)} or explicit claim_limits"
                )

    for dataset, count in sorted(active_combo_count_by_dataset.items()):
        if count > int(max_active_combo):
            warnings.append(
                f"{dataset}: {count} active combo candidates exceed policy.max_active_combo_candidates_per_dataset={int(max_active_combo)}"
            )

    for family_id, unique_seeds in sorted(family_seeds.items()):
        if len(unique_seeds) > 3:
            errors.append(
                f"experiment_family_id {family_id}: {len(unique_seeds)} unique random seeds exceed the hard maximum of 3"
            )

    if (
        project is not None
        and str(program.get("enforcement_mode") or "legacy") == "enforced"
        and str(program.get("claim_scope") or "") == "cross_dataset_method"
    ):
        required_datasets = required_dataset_ids(program)
        matrix = read_json(project / ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json")
        for plan_row in admitted_matrix_rows(matrix):
            if str(plan_row.get("claim_role") or "") != "method_candidate":
                continue
            track_id = str(plan_row.get("track_id") or "").strip()
            track_rows = [
                row for row in rows_by_id.values()
                if str(row.get("track_id") or "") == track_id
                and str(row.get("status") or "") not in {"dropped", "superseded"}
            ]
            probe_rows = [row for row in track_rows if row.get("stage2_role") == "stage2_parameter_probe"]
            if probe_rows:
                review = read_json(
                    project / f".autoreskill/planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json"
                )
                contract = review.get("parameter_transfer_contract") if isinstance(review, dict) else None
                if isinstance(contract, dict):
                    probe_validation = validate_parameter_probe_rows(probe_rows, contract, required_datasets)
                    errors.extend(
                        f"track {track_id}: {item}" for item in probe_validation.get("errors") or []
                    )

        confirmation_groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows_by_id.values():
            if row.get("validation_stage") != 6 or str(row.get("status") or "") in {"dropped", "superseded"}:
                continue
            group_id = str(row.get("crossed_confirmation_group_id") or "").strip()
            if str(row.get("status") or "") in STRICT_LAUNCH_STATUSES and not group_id:
                errors.append(f"{row.get('id')}: Stage 6 requires crossed_confirmation_group_id")
            if group_id:
                confirmation_groups.setdefault(group_id, []).append(row)
        for group_id, group_rows in sorted(confirmation_groups.items()):
            if not any(str(row.get("status") or "") in STRICT_LAUNCH_STATUSES for row in group_rows):
                continue
            registered_sets = {
                tuple(sorted(set(as_str_list(row.get("registered_seed_set") or row.get("seeds")))))
                for row in group_rows
            }
            if len(registered_sets) != 1 or not next(iter(registered_sets), ()):
                errors.append(f"crossed confirmation {group_id}: one non-empty registered seed set is required")
                continue
            registered = next(iter(registered_sets))
            if len(registered) > 3:
                errors.append(f"crossed confirmation {group_id}: seed set exceeds three")
            profile_hashes = {
                str(row.get("frozen_parameter_profile_sha256") or "")
                for row in group_rows
            }
            if len(profile_hashes) != 1 or not next(iter(profile_hashes), ""):
                errors.append(f"crossed confirmation {group_id}: one frozen parameter profile is required")
            transfer_hashes = {
                str(row.get("parameter_transfer_contract_sha256") or "")
                for row in group_rows
            }
            if len(transfer_hashes) != 1 or not next(iter(transfer_hashes), ""):
                errors.append(f"crossed confirmation {group_id}: one parameter-transfer contract is required")
            if any(str(row.get("parameter_profile_status") or "") != "frozen" for row in group_rows):
                errors.append(f"crossed confirmation {group_id}: every cell must bind a frozen parameter profile")
            observed: set[tuple[str, str, str]] = set()
            for row in group_rows:
                dataset_id = str(row.get("dataset_id") or row.get("dataset") or "").strip()
                arm = str(row.get("confirmation_arm") or "").strip()
                row_seeds = as_str_list(row.get("seeds") or row.get("seed"))
                if arm not in {"baseline", "method"}:
                    errors.append(f"{row.get('id')}: confirmation_arm must be baseline or method")
                    continue
                for seed in row_seeds:
                    observed.add((dataset_id, seed, arm))
            expected = {
                (dataset_id, seed, arm)
                for dataset_id in required_datasets
                for seed in registered
                for arm in ("baseline", "method")
            }
            missing_cells = sorted(expected - observed)
            if missing_cells:
                errors.append(
                    f"crossed confirmation {group_id}: incomplete dataset-by-seed-by-arm matrix ({len(missing_cells)} missing cells)"
                )

        hpo_groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows_by_id.values():
            if row.get("validation_stage") != 5 or str(row.get("status") or "") in {"dropped", "superseded"}:
                continue
            group_id = str(row.get("dataset_group_trial_id") or "").strip()
            if str(row.get("status") or "") in STRICT_LAUNCH_STATUSES and not group_id:
                errors.append(f"{row.get('id')}: Stage-5 dataset-group row requires dataset_group_trial_id")
            if group_id:
                hpo_groups.setdefault(group_id, []).append(row)
        for group_id, group_rows in sorted(hpo_groups.items()):
            if not any(str(row.get("status") or "") in STRICT_LAUNCH_STATUSES for row in group_rows):
                continue
            exemplar = group_rows[0]
            hpo = exemplar.get("hpo_search_policy") if isinstance(exemplar.get("hpo_search_policy"), dict) else {}
            group = hpo.get("dataset_group_hpo") if isinstance(hpo.get("dataset_group_hpo"), dict) else {}
            required = set(as_str_list(group.get("required_dataset_ids")))
            observed = {str(row.get("dataset_id") or row.get("dataset") or "") for row in group_rows}
            if observed != required:
                errors.append(f"dataset-group HPO {group_id}: active trial must contain exactly every required dataset leg")
            config_hashes = {str(row.get("dataset_group_trial_config_sha256") or "") for row in group_rows}
            if len(config_hashes) != 1 or not SHA256_RE.fullmatch(next(iter(config_hashes), "")):
                errors.append(f"dataset-group HPO {group_id}: one shared configuration SHA-256 is required")
            rung_names = {str(row.get("hpo_rung_name") or "") for row in group_rows}
            fractions = {str(row.get("hpo_resource_fraction") or "") for row in group_rows}
            seeds = {str(row.get("seed") or "") for row in group_rows}
            if len(rung_names) != 1 or not next(iter(rung_names), ""):
                errors.append(f"dataset-group HPO {group_id}: one shared rung is required")
            if len(fractions) != 1 or numeric(next(iter(fractions), None), -1.0) <= 0:
                errors.append(f"dataset-group HPO {group_id}: one positive shared resource fraction is required")
            if len(seeds) != 1:
                errors.append(f"dataset-group HPO {group_id}: every dataset leg must use the same fixed scout seed")

    max_frontier = positive_int(policy.get("max_ready_frontier_rows"), 32) or 32
    if details["ready_count"] > max_frontier:
        warnings.append(
            f"ready frontier has {details['ready_count']} rows, exceeding policy.max_ready_frontier_rows={max_frontier}; retain only justified near-term decisions"
        )

    if project is not None:
        queue_project = queue.get("project_root")
        if truthy(queue_project) and Path(str(queue_project)).expanduser().resolve() != project:
            warnings.append(f"queue project_root differs from selected project: {queue_project}")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "details": details}


def parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def lease_expired(row: dict[str, Any]) -> bool:
    expires = parse_time(row.get("lease_expires_at"))
    return expires is None or expires <= datetime.now(timezone.utc)


def matching_live_run(project: Path, row: dict[str, Any]) -> dict[str, Any] | None:
    live_statuses = {"submitted", "queued", "pending", "launching", "running", "active", "monitoring"}
    row_id = str(row.get("id") or "")
    identity = str(row.get("launch_identity_hash") or "")
    candidates: list[Path] = []
    explicit = row.get("remote_run_ref")
    if truthy(explicit):
        path = Path(str(explicit)).expanduser()
        candidates.append(path if path.is_absolute() else project / path)
    coder = project / ".autoreskill/coder/experiments"
    if coder.exists():
        candidates.extend(coder.rglob("REMOTE_RUN.json"))
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        payload = read_json(resolved)
        if not payload:
            continue
        payload_row = str(payload.get("queue_row_id") or payload.get("next_action_row_id") or "")
        payload_identity = str(payload.get("launch_identity_hash") or "")
        if not ((row_id and payload_row == row_id) or (identity and payload_identity == identity)):
            continue
        status = str(payload.get("status") or payload.get("scheduler_status") or "").strip().lower()
        if status in live_statuses:
            return {"path": str(resolved), "status": status}
    return None


def launch_was_started(row: dict[str, Any]) -> bool:
    return any(
        truthy(row.get(key))
        for key in [
            "remote_run_ref",
            "run_id",
            "launch_started_at",
            "resource_allocation",
            "backend_submit_intent",
            "backend_submit_receipt",
        ]
    )


def backend_reconciled_no_live(row: dict[str, Any]) -> bool:
    evidence = row.get("backend_reconcile") if isinstance(row.get("backend_reconcile"), dict) else {}
    return str(evidence.get("status") or "").strip().lower() in {"no_live_run", "not_launched", "terminal"} and truthy(
        evidence.get("checked_at")
    )


def mutation_error(code: str, message: str, **details: Any) -> tuple[int, dict[str, Any]]:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return 1, payload


def canonical_payload_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def global_claim_context(
    args: argparse.Namespace,
    project: Path,
    queue: dict[str, Any],
    row_id: str,
    pool_id: str,
    owner: str,
) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
    required = {
        "global_plan": getattr(args, "global_plan", None),
        "global_schedule_sha256": getattr(args, "global_schedule_sha256", None),
        "assignment_sha256": getattr(args, "assignment_sha256", None),
        "global_lease_file": getattr(args, "global_lease_file", None),
    }
    missing = [key for key, value in required.items() if not truthy(value)]
    if missing:
        return None, mutation_error(
            "global_authority_missing",
            "admission_scope=global requires a hashed schedule, first assignment, and global lease",
            missing=missing,
        )
    plan_path = Path(str(required["global_plan"])).expanduser().resolve()
    try:
        plan, _ = strict_json_object(plan_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return None, mutation_error("global_plan_invalid", f"cannot read strict global schedule: {exc}")
    if plan.get("kind") != "global_resource_schedule" or plan.get("schema_version") != 1:
        return None, mutation_error("global_plan_invalid", "global schedule kind/schema is unsupported")
    computed_schedule_sha = schedule_semantic_sha256(plan)
    declared_schedule_sha = str(plan.get("global_schedule_sha256") or "").strip().lower()
    requested_schedule_sha = str(required["global_schedule_sha256"] or "").strip().lower()
    if not SHA256_RE.fullmatch(requested_schedule_sha) or not (
        requested_schedule_sha == declared_schedule_sha == computed_schedule_sha
    ):
        return None, mutation_error(
            "global_schedule_stale",
            "global schedule hash does not match its canonical content",
            requested=requested_schedule_sha,
            declared=declared_schedule_sha,
            computed=computed_schedule_sha,
        )

    assignments = [item for item in plan.get("assignments", []) if isinstance(item, dict)]
    claimable = [item for item in assignments if item.get("claimable_first") is True]
    if len(claimable) != 1 or not assignments or assignments[0] is not claimable[0]:
        return None, mutation_error(
            "global_plan_invalid",
            "global schedule must mark exactly its first assignment claimable_first=true",
        )
    assignment = claimable[0]
    computed_assignment_sha = assignment_semantic_sha256(assignment)
    declared_assignment_sha = str(assignment.get("assignment_sha256") or "").strip().lower()
    requested_assignment_sha = str(required["assignment_sha256"] or "").strip().lower()
    if not SHA256_RE.fullmatch(requested_assignment_sha) or not (
        requested_assignment_sha == declared_assignment_sha == computed_assignment_sha
    ):
        return None, mutation_error(
            "global_assignment_stale",
            "global assignment hash does not match its canonical content",
            requested=requested_assignment_sha,
            declared=declared_assignment_sha,
            computed=computed_assignment_sha,
        )
    if Path(str(assignment.get("project") or "")).expanduser().resolve() != project:
        return None, mutation_error("global_assignment_conflict", "first assignment targets another project")
    if str(assignment.get("row_id") or "") != row_id or str(assignment.get("pool_id") or "") != pool_id:
        return None, mutation_error(
            "global_assignment_conflict",
            "requested row/pool is not the first global assignment",
            first_project=assignment.get("project"),
            first_row_id=assignment.get("row_id"),
            first_pool_id=assignment.get("pool_id"),
        )
    current_queue_sha = canonical_payload_sha256(queue)
    if assignment.get("queue_revision") != queue.get("queue_revision") or str(
        assignment.get("queue_sha256") or ""
    ) != current_queue_sha:
        return None, mutation_error(
            "global_queue_stale",
            "project queue revision or canonical hash changed after global scheduling",
            scheduled_revision=assignment.get("queue_revision"),
            current_revision=queue.get("queue_revision"),
            scheduled_sha256=assignment.get("queue_sha256"),
            current_sha256=current_queue_sha,
        )

    lease_path = Path(str(required["global_lease_file"])).expanduser().resolve()
    lease = read_json(lease_path)
    lease_expiry = parse_time(lease.get("expires_at"))
    if (
        not lease
        or str(lease.get("scope") or "") != "global-admission"
        or str(lease.get("owner_id") or "") != owner
        or lease_expiry is None
        or lease_expiry <= datetime.now(timezone.utc)
    ):
        return None, mutation_error(
            "global_lease_conflict",
            "caller does not own a live global admission lease",
            lease_path=str(lease_path),
            lease_owner=lease.get("owner_id"),
            lease_expiry=lease.get("expires_at"),
        )
    project_lease = read_json(project / PROJECT_CONTROL_LEASE_REL)
    project_expiry = parse_time(project_lease.get("expires_at"))
    if (
        not project_lease
        or str(project_lease.get("scope") or "") != "project-control"
        or str(project_lease.get("owner_id") or "") != owner
        or project_expiry is None
        or project_expiry <= datetime.now(timezone.utc)
    ):
        return None, mutation_error(
            "project_control_lease_conflict",
            "global assignment claim requires the same owner to hold the live project control lease",
            lease_path=str(project / PROJECT_CONTROL_LEASE_REL),
            lease_owner=project_lease.get("owner_id"),
            lease_expiry=project_lease.get("expires_at"),
        )

    snapshot_ref = str(plan.get("resource_snapshot_ref") or "").strip()
    if not snapshot_ref:
        return None, mutation_error("global_snapshot_missing", "global schedule lacks resource_snapshot_ref")
    snapshot_path = Path(snapshot_ref).expanduser()
    if not snapshot_path.is_absolute():
        snapshot_path = (plan_path.parent / snapshot_path).resolve()
    else:
        snapshot_path = snapshot_path.resolve()
    try:
        snapshot_payload, _ = strict_json_object(snapshot_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return None, mutation_error("global_snapshot_invalid", f"cannot read strict shared snapshot: {exc}")
    snapshot = snapshot_payload.get("resource_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = snapshot_payload
    snapshot_errors = shared_resource_snapshot_errors(snapshot)
    snapshot_sha = canonical_payload_sha256(snapshot)
    scheduled_snapshot_sha = str(plan.get("resource_snapshot_sha256") or "").strip().lower()
    if snapshot_errors or snapshot_sha != scheduled_snapshot_sha or snapshot_sha != str(
        assignment.get("resource_snapshot_sha256") or ""
    ):
        return None, mutation_error(
            "global_snapshot_stale",
            "shared resource snapshot changed, expired, or failed validation",
            errors=snapshot_errors,
            scheduled_sha256=scheduled_snapshot_sha,
            current_sha256=snapshot_sha,
        )
    pool = next(
        (
            item
            for item in snapshot.get("pools", [])
            if isinstance(item, dict) and str(item.get("pool_id") or "") == pool_id
        ),
        None,
    )
    if pool is None:
        return None, mutation_error("global_pool_missing", "first-assignment resource pool disappeared")
    assigned_ids = as_str_list(assignment.get("allocated_resource_ids"))
    if assigned_ids and not set(assigned_ids).issubset(set(concrete_pool_resource_ids(pool))):
        return None, mutation_error("global_resource_conflict", "assignment concrete resource ids no longer match the pool")
    return {
        "plan": plan,
        "plan_path": plan_path,
        "schedule_sha256": computed_schedule_sha,
        "assignment": assignment,
        "assignment_sha256": computed_assignment_sha,
        "snapshot": copy.deepcopy(snapshot),
        "snapshot_path": snapshot_path,
        "snapshot_sha256": snapshot_sha,
        "pool": copy.deepcopy(pool),
        "global_lease_path": lease_path,
        "allocated_resource_ids": assigned_ids,
    }, None


def strict_json_object(path: Path) -> tuple[dict[str, Any], str]:
    def reject_nonfinite(token: str) -> None:
        raise ValueError(f"non-finite JSON number {token!r} is forbidden")

    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"), parse_constant=reject_nonfinite)
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload, hashlib.sha256(raw).hexdigest()


def strict_aware_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def path_ref(path: Path, project: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(project).as_posix()
    except ValueError:
        return str(resolved)


def normalized_snapshot_for_commit(
    proposal: dict[str, Any], project: Path, proposal_path: Path, proposal_sha256: str
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if proposal.get("schema_version") != 1:
        errors.append("resource proposal schema_version must be 1")
    if proposal.get("kind") != "proposed_resource_snapshot":
        errors.append("resource proposal kind must be proposed_resource_snapshot")
    route = str(proposal.get("execution_route") or "").strip().lower()
    if route not in EXECUTION_ROUTES:
        errors.append(f"resource proposal execution_route must be one of {sorted(EXECUTION_ROUTES)}")
    for field in ("source_kind", "source_ref", "source_sha256", "checked_at"):
        if not truthy(proposal.get(field)):
            errors.append(f"resource proposal {field} is required")
    source_sha = str(proposal.get("source_sha256") or "").strip().lower()
    if source_sha and not SHA256_RE.fullmatch(source_sha):
        errors.append("resource proposal source_sha256 must be a lowercase 64-hex digest")
    checked_at = strict_aware_time(proposal.get("checked_at"))
    if checked_at is None:
        errors.append("resource proposal checked_at must be a timezone-aware ISO timestamp")
    fresh = proposal.get("fresh")
    stale = proposal.get("stale")
    status = str(proposal.get("status") or "").strip().lower()
    if not isinstance(fresh, bool) or not isinstance(stale, bool):
        errors.append("resource proposal fresh and stale must be explicit booleans")
    elif fresh == stale:
        errors.append("resource proposal fresh and stale must be logical opposites")
    if fresh is True and status != "fresh":
        errors.append("fresh resource proposal must have status=fresh")
    if fresh is False and status not in {"stale", "unknown", "expired"}:
        errors.append("non-fresh resource proposal must have status stale, unknown, or expired")
    if fresh is True and checked_at is not None:
        age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
        if age_seconds < -60 or age_seconds > 600:
            errors.append("fresh resource proposal checked_at is stale or implausibly future-dated")

    pools = proposal.get("pools")
    if not isinstance(pools, list):
        errors.append("resource proposal pools must be a list")
        pools = []
    seen: set[str] = set()
    for index, pool in enumerate(pools):
        if not isinstance(pool, dict):
            errors.append(f"resource proposal pools[{index}] must be an object")
            continue
        pool_id = str(pool.get("pool_id") or "").strip()
        if not pool_id:
            errors.append(f"resource proposal pools[{index}].pool_id is required")
        elif pool_id in seen:
            errors.append(f"resource proposal contains duplicate pool_id {pool_id}")
        seen.add(pool_id)
        pool_backend = str(pool.get("backend") or "").strip().lower()
        pool_route = str(pool.get("execution_route") or pool_backend).strip().lower()
        if route and pool_backend != route:
            errors.append(f"resource proposal pool {pool_id or index} backend must exactly match execution_route {route}")
        if route and pool_route != route:
            errors.append(f"resource proposal pool {pool_id or index} execution_route must match {route}")
        if nonnegative_int(pool.get("launch_slots")) is None:
            errors.append(f"resource proposal pool {pool_id or index} launch_slots must be a nonnegative integer")
        for field in ("source_ref", "source_sha256"):
            if truthy(pool.get(field)) and str(pool.get(field)) != str(proposal.get(field)):
                errors.append(f"resource proposal pool {pool_id or index} {field} must match the snapshot source")

    snapshot = dict(proposal)
    snapshot["proposal_ref"] = path_ref(proposal_path, project)
    snapshot["proposal_sha256"] = proposal_sha256
    snapshot["committed_at"] = now_iso()
    snapshot["authority_boundary"] = (
        "canonical queue resource observation only; assignment, preflight, intent, and launch remain separate authorities"
    )
    return snapshot, errors


def append_queue_event(queue: dict[str, Any], payload: dict[str, Any]) -> None:
    log = queue.setdefault("decision_log", [])
    if not isinstance(log, list):
        log = []
        queue["decision_log"] = log
    log.append({"timestamp": now_iso(), **payload, "queue_revision": queue.get("queue_revision")})


def set_policy(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    project = project_root(args.project)
    queue_path = project / QUEUE_REL
    requested_scope = str(args.admission_scope or "").strip().lower()
    requested_capacity = args.portfolio_capacity_target
    if not requested_scope and requested_capacity is None:
        return mutation_error(
            "policy_change_empty",
            "set-policy requires --admission-scope or --portfolio-capacity-target",
        )
    if requested_scope and requested_scope not in {"project", "global"}:
        return mutation_error("policy_invalid", "admission_scope must be project or global")
    if requested_capacity is not None and (requested_capacity < 1 or requested_capacity > 4):
        return mutation_error("policy_invalid", "portfolio_capacity_target must be an integer from 1 through 4")

    with queue_lock(queue_path):
        queue = load_queue(project)
        if not queue:
            return mutation_error("queue_missing", "NEXT_EXPERIMENT_QUEUE.json is missing")
        if queue.get("schema_version") != 2:
            return mutation_error("migration_required", "queue mutations require schema_version=2")
        current_revision = queue.get("queue_revision")
        if args.expected_revision != current_revision:
            return mutation_error(
                "stale_plan",
                "queue revision changed before policy update",
                expected_revision=args.expected_revision,
                current_revision=current_revision,
            )
        program = read_json(project / ".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json")
        if str(program.get("enforcement_mode") or "legacy") == "enforced" and requested_capacity is not None:
            expected_capacity = (
                program.get("search_budget", {}).get("portfolio_capacity_target")
                if isinstance(program.get("search_budget"), dict)
                else None
            )
            if requested_capacity != expected_capacity:
                return mutation_error(
                    "program_contract_conflict",
                    "portfolio capacity is owned by the enforced program claim contract",
                    requested=requested_capacity,
                    expected=expected_capacity,
                )

        policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
        before = {
            "admission_scope": str(policy.get("admission_scope") or "project"),
            "portfolio_capacity_target": positive_int(policy.get("portfolio_capacity_target"), 4) or 4,
        }
        target_scope = requested_scope or before["admission_scope"]
        if target_scope != before["admission_scope"]:
            authority_rows = [
                str(row.get("id") or "")
                for row in queue.get("rows", [])
                if isinstance(row, dict)
                and str(row.get("status") or "") in {"planned", "submitting", "needs_sync", "running"}
            ]
            if authority_rows:
                return mutation_error(
                    "active_authority_conflict",
                    "reconcile active allocation or backend-authority rows before changing admission_scope",
                    row_ids=authority_rows,
                )

        policy["admission_scope"] = target_scope
        policy["portfolio_capacity_target"] = (
            requested_capacity if requested_capacity is not None else before["portfolio_capacity_target"]
        )
        after = {
            "admission_scope": policy["admission_scope"],
            "portfolio_capacity_target": policy["portfolio_capacity_target"],
        }
        if after == before:
            return 0, {
                "ok": True,
                "action": "set-policy",
                "changed": False,
                "queue_revision": current_revision,
                "policy": after,
            }

        timestamp = now_iso()
        queue["policy"] = policy
        queue["queue_revision"] = int(current_revision or 0) + 1
        queue["updated_at"] = timestamp
        append_queue_event(
            queue,
            {
                "decision": "queue_set_policy",
                "rationale": str(args.reason),
                "owner": str(args.owner).strip(),
                "before": before,
                "after": after,
            },
        )
        atomic_write_json(queue_path, queue)
        return 0, {
            "ok": True,
            "action": "set-policy",
            "changed": True,
            "queue_revision": queue.get("queue_revision"),
            "policy": after,
        }


def commit_resource_snapshot(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    project = project_root(args.project)
    queue_path = project / QUEUE_REL
    proposal_path = Path(args.input).expanduser().resolve()
    try:
        proposal, proposal_sha256 = strict_json_object(proposal_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return mutation_error("resource_proposal_invalid", f"cannot read strict resource proposal: {exc}")
    snapshot, proposal_errors = normalized_snapshot_for_commit(proposal, project, proposal_path, proposal_sha256)
    if proposal_errors:
        return mutation_error("resource_proposal_invalid", "resource proposal failed validation", errors=proposal_errors)

    with queue_lock(queue_path):
        queue = load_queue(project)
        if not queue:
            return mutation_error("queue_missing", "NEXT_EXPERIMENT_QUEUE.json is missing")
        if queue.get("schema_version") != 2:
            return mutation_error("migration_required", "queue mutations require schema_version=2")
        current_revision = queue.get("queue_revision")
        if args.expected_revision != current_revision:
            return mutation_error(
                "stale_plan",
                "queue revision changed before resource snapshot commit",
                expected_revision=args.expected_revision,
                current_revision=current_revision,
            )
        timestamp = now_iso()
        snapshot["committed_at"] = timestamp
        snapshot["committed_by"] = str(args.owner).strip()
        queue["resource_snapshot"] = snapshot
        queue["queue_revision"] = int(current_revision or 0) + 1
        queue["updated_at"] = timestamp
        append_queue_event(
            queue,
            {
                "decision": "queue_commit_resource_snapshot",
                "rationale": str(args.reason),
                "owner": str(args.owner).strip(),
                "proposal_ref": snapshot.get("proposal_ref"),
                "proposal_sha256": proposal_sha256,
                "resource_snapshot_sha256": canonical_payload_sha256(snapshot),
                "execution_route": snapshot.get("execution_route"),
            },
        )
        atomic_write_json(queue_path, queue)
        return 0, {
            "ok": True,
            "action": "commit-resource-snapshot",
            "queue_revision": queue.get("queue_revision"),
            "proposal_ref": snapshot.get("proposal_ref"),
            "proposal_sha256": proposal_sha256,
            "resource_snapshot_sha256": canonical_payload_sha256(snapshot),
            "execution_route": snapshot.get("execution_route"),
            "fresh": snapshot.get("fresh"),
            "pool_count": len(snapshot.get("pools") or []),
        }


def validate_preflight_record(
    row: dict[str, Any], allocation: dict[str, Any], preflight: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    route = str(allocation.get("execution_route") or allocation.get("backend") or "").strip().lower()
    row_route = row_execution_route(row)
    request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    request_backend = str(request.get("backend") or "").strip().lower()
    allocation_backend = str(allocation.get("backend") or "").strip().lower()
    if route not in EXECUTION_ROUTES:
        errors.append("planned allocation has an unsupported execution_route")
    if row_route != route or request_backend != route or allocation_backend != route:
        errors.append("row execution_route, resource_request.backend, and allocation backend/route must match exactly")
    if str(preflight.get("status") or "").strip().lower() != "passed":
        errors.append("backend_preflight.status must be passed")
    checked_at = strict_aware_time(preflight.get("checked_at"))
    if checked_at is None:
        errors.append("backend_preflight.checked_at must be a timezone-aware ISO timestamp")
    else:
        age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
        if age_seconds < -60 or age_seconds > 600:
            errors.append("backend_preflight is stale or implausibly future-dated")
    if str(preflight.get("pool_id") or "") != str(allocation.get("pool_id") or ""):
        errors.append("backend_preflight.pool_id must match the planned allocation")
    if str(preflight.get("execution_route") or "").strip().lower() != route:
        errors.append("backend_preflight.execution_route must match the planned allocation")
    launch_spec_sha = str(preflight.get("launch_spec_sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(launch_spec_sha):
        errors.append("backend_preflight.launch_spec_sha256 must be a lowercase 64-hex digest")
    snapshot_sha = str(preflight.get("resource_snapshot_sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(snapshot_sha) or snapshot_sha != str(allocation.get("resource_snapshot_sha256") or ""):
        errors.append("backend_preflight.resource_snapshot_sha256 must match the claimed snapshot")
    if route == "ssh":
        gpu_uuids = as_str_list(allocation.get("gpu_uuids"))
        if len(gpu_uuids) != 1:
            errors.append("SSH preflight requires exactly one assigned physical GPU UUID")
        elif str(preflight.get("assigned_gpu_uuid") or "") != gpu_uuids[0]:
            errors.append("SSH preflight assigned_gpu_uuid must match the planned allocation")
        if preflight.get("assigned_gpu_idle") is not True or preflight.get("full_process_visibility") is not True:
            errors.append("SSH preflight requires assigned_gpu_idle=true and full_process_visibility=true")
    elif route == "bjtu_hpc":
        if preflight.get("exact_script_checks_passed") is not True:
            errors.append("BJTU preflight requires exact_script_checks_passed=true")
        if preflight.get("sbatch_test_only_passed") is not True:
            errors.append("BJTU preflight requires sbatch_test_only_passed=true")
        if preflight.get("no_queued") is not True:
            errors.append("BJTU preflight requires no_queued=true")
        if nonnegative_int(preflight.get("requested_gpus")) != 1:
            errors.append("BJTU preflight requires requested_gpus=1")
    return errors


def record_backend_preflight(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    project = project_root(args.project)
    queue_path = project / QUEUE_REL
    input_path = Path(args.input).expanduser().resolve()
    try:
        payload, input_sha256 = strict_json_object(input_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return mutation_error("backend_preflight_invalid", f"cannot read strict backend preflight: {exc}")
    preflight = payload.get("backend_preflight") if isinstance(payload.get("backend_preflight"), dict) else payload

    with queue_lock(queue_path):
        queue = load_queue(project)
        if not queue:
            return mutation_error("queue_missing", "NEXT_EXPERIMENT_QUEUE.json is missing")
        if queue.get("schema_version") != 2:
            return mutation_error("migration_required", "queue mutations require schema_version=2")
        current_revision = queue.get("queue_revision")
        if args.expected_revision != current_revision:
            return mutation_error(
                "stale_plan",
                "queue revision changed before backend preflight record",
                expected_revision=args.expected_revision,
                current_revision=current_revision,
            )
        row = find_row(queue, str(args.row_id).strip())
        if row is None:
            return mutation_error("row_missing", f"queue row {args.row_id!r} does not exist")
        if str(row.get("status") or "") != "planned":
            return mutation_error("status_conflict", "backend preflight requires a planned queue row")
        owner = str(args.owner).strip()
        if str(row.get("lease_owner") or "") != owner:
            return mutation_error("lease_conflict", "only the live claim-assignment owner may record backend preflight")
        if lease_expired(row):
            return mutation_error("lease_expired", "backend preflight cannot be recorded under an expired lease")
        allocation = row.get("planned_resource_allocation")
        if not isinstance(allocation, dict):
            return mutation_error("allocation_missing", "planned row lacks planned_resource_allocation")
        errors = validate_preflight_record(row, allocation, preflight)
        if errors:
            return mutation_error("backend_preflight_invalid", "backend preflight failed exact binding", errors=errors)

        timestamp = now_iso()
        row["backend_preflight"] = dict(preflight)
        row["backend_preflight_ref"] = path_ref(input_path, project)
        row["backend_preflight_input_sha256"] = input_sha256
        row["backend_preflight_sha256"] = canonical_payload_sha256(preflight)
        allocation["backend_preflight_recorded"] = True
        allocation["backend_preflight_sha256"] = row["backend_preflight_sha256"]
        row["row_revision"] = int(row.get("row_revision") or 0) + 1
        row["updated_at"] = timestamp
        queue["queue_revision"] = int(current_revision or 0) + 1
        queue["updated_at"] = timestamp
        append_queue_event(
            queue,
            {
                "decision": "queue_record_backend_preflight",
                "rationale": str(args.reason),
                "owner": owner,
                "row_id": row.get("id"),
                "row_revision": row.get("row_revision"),
                "pool_id": allocation.get("pool_id"),
                "execution_route": allocation.get("execution_route"),
                "backend_preflight_sha256": row.get("backend_preflight_sha256"),
            },
        )
        atomic_write_json(queue_path, queue)
        return 0, {
            "ok": True,
            "action": "record-backend-preflight",
            "row_id": row.get("id"),
            "pool_id": allocation.get("pool_id"),
            "execution_route": allocation.get("execution_route"),
            "queue_revision": queue.get("queue_revision"),
            "row_revision": row.get("row_revision"),
            "backend_preflight_sha256": row.get("backend_preflight_sha256"),
        }


def submit_identity_errors(
    row: dict[str, Any], allocation: dict[str, Any], intent: dict[str, Any], current_revision: int
) -> list[str]:
    errors: list[str] = []
    required = [
        "submit_attempt_id",
        "backend_idempotency_key",
        "anonymous_trace_id",
        "launch_identity_hash",
        "script_or_command_sha256",
        "preflight_sha256",
        "pool_id",
        "execution_route",
    ]
    for field in required:
        if not truthy(intent.get(field)):
            errors.append(f"submit_intent.{field} is required")
    for field in ["launch_identity_hash", "script_or_command_sha256", "preflight_sha256"]:
        if truthy(intent.get(field)) and not SHA256_RE.fullmatch(str(intent.get(field) or "").strip().lower()):
            errors.append(f"submit_intent.{field} must be a lowercase 64-hex digest")
    if str(intent.get("launch_identity_hash") or "") != str(row.get("launch_identity_hash") or ""):
        errors.append("submit_intent.launch_identity_hash must match the queue row")
    if str(intent.get("preflight_sha256") or "") != str(row.get("backend_preflight_sha256") or ""):
        errors.append("submit_intent.preflight_sha256 must match the recorded backend preflight")
    if intent.get("queue_revision") != current_revision:
        errors.append("submit_intent.queue_revision must match the current queue revision")
    if str(intent.get("pool_id") or "") != str(allocation.get("pool_id") or ""):
        errors.append("submit_intent.pool_id must match the planned allocation")
    route = str(allocation.get("execution_route") or allocation.get("backend") or "").strip().lower()
    if str(intent.get("execution_route") or "").strip().lower() != route:
        errors.append("submit_intent.execution_route must match the planned allocation")
    embedding = intent.get("trace_embedding") if isinstance(intent.get("trace_embedding"), dict) else {}
    surface = str(embedding.get("surface") or "").strip().lower()
    embedded_trace = str(embedding.get("anonymous_trace_id") or "")
    if embedded_trace != str(intent.get("anonymous_trace_id") or ""):
        errors.append("submit_intent.trace_embedding must bind the anonymous trace id")
    if route == "bjtu_hpc" and surface not in {"slurm_job_name", "slurm_comment", "slurm_environment"}:
        errors.append("BJTU submit intent must embed the trace in Slurm job name, comment, or environment")
    if route == "ssh" and surface not in {"process_identity", "session_identity", "log_identity"}:
        errors.append("SSH submit intent must embed the trace in process, session, or log identity")
    lookup = intent.get("lookup_strategy") if isinstance(intent.get("lookup_strategy"), dict) else {}
    if not as_str_list(lookup.get("search_fields")):
        errors.append("submit_intent.lookup_strategy.search_fields is required")
    return errors


def mutate_submit_artifact(args: argparse.Namespace, action: str) -> tuple[int, dict[str, Any]]:
    project = project_root(args.project)
    queue_path = project / QUEUE_REL
    input_path = Path(args.input).expanduser().resolve()
    try:
        payload, input_sha256 = strict_json_object(input_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return mutation_error(f"{action}_invalid", f"cannot read strict submit artifact: {exc}")
    key = {
        "prepare-backend-submit": "submit_intent",
        "abort-backend-submit": "submit_abort",
        "record-backend-submit": "submit_receipt",
        "record-backend-observation": "backend_observation",
    }[action]
    artifact = payload.get(key) if isinstance(payload.get(key), dict) else payload
    artifact_sha256 = canonical_payload_sha256(artifact)
    owner = str(args.owner).strip()
    row_id = str(args.row_id).strip()

    with queue_lock(queue_path):
        queue = load_queue(project)
        if not queue:
            return mutation_error("queue_missing", "NEXT_EXPERIMENT_QUEUE.json is missing")
        if queue.get("schema_version") != 2:
            return mutation_error("migration_required", "queue mutations require schema_version=2")
        row = find_row(queue, row_id)
        if row is None:
            return mutation_error("row_missing", f"queue row {row_id!r} does not exist")
        current_revision = int(queue.get("queue_revision") or 0)

        stored_hash_field = {
            "prepare-backend-submit": "backend_submit_intent_sha256",
            "record-backend-submit": "backend_submit_receipt_sha256",
            "record-backend-observation": "backend_observation_sha256",
        }.get(action)
        if stored_hash_field and str(row.get(stored_hash_field) or "") == artifact_sha256:
            return 0, {
                "ok": True,
                "idempotent": True,
                "action": action,
                "row_id": row_id,
                "status": row.get("status"),
                "queue_revision": current_revision,
                stored_hash_field: artifact_sha256,
            }
        if args.expected_revision != current_revision:
            return mutation_error(
                "stale_plan",
                "queue revision changed before submit artifact mutation",
                expected_revision=args.expected_revision,
                current_revision=current_revision,
            )
        if str(row.get("lease_owner") or "") != owner:
            return mutation_error("lease_conflict", "only the current assignment owner may mutate submit state")
        if lease_expired(row):
            return mutation_error("lease_expired", "submit state cannot mutate under an expired lease")
        allocation = row.get("planned_resource_allocation")
        if not isinstance(allocation, dict):
            return mutation_error("allocation_missing", "queue row lacks planned_resource_allocation")
        old_status = str(row.get("status") or "")
        timestamp = now_iso()

        if action == "prepare-backend-submit":
            if old_status != "planned":
                return mutation_error("status_conflict", "prepare-backend-submit requires a planned row")
            if not isinstance(row.get("backend_preflight"), dict) or not truthy(row.get("backend_preflight_sha256")):
                return mutation_error("preflight_missing", "prepare-backend-submit requires a recorded backend preflight")
            errors = submit_identity_errors(row, allocation, artifact, current_revision)
            for other in queue.get("rows") or []:
                if not isinstance(other, dict) or other is row:
                    continue
                other_intent = other.get("backend_submit_intent") if isinstance(other.get("backend_submit_intent"), dict) else {}
                if str(other_intent.get("backend_idempotency_key") or "") == str(artifact.get("backend_idempotency_key") or ""):
                    errors.append("submit_intent.backend_idempotency_key is already used by another row")
                if str(other_intent.get("submit_attempt_id") or "") == str(artifact.get("submit_attempt_id") or ""):
                    errors.append("submit_intent.submit_attempt_id is already used by another row")
            if errors:
                return mutation_error("submit_intent_invalid", "submit intent failed exact binding", errors=errors)
            row["backend_submit_intent"] = dict(artifact)
            row["backend_submit_intent_ref"] = path_ref(input_path, project)
            row["backend_submit_intent_input_sha256"] = input_sha256
            row["backend_submit_intent_sha256"] = artifact_sha256
            row["submit_prepared_at"] = timestamp
            row["status"] = "submitting"
        elif action == "abort-backend-submit":
            if old_status != "submitting":
                return mutation_error("status_conflict", "abort-backend-submit requires a submitting row")
            intent = row.get("backend_submit_intent") if isinstance(row.get("backend_submit_intent"), dict) else {}
            if str(artifact.get("submit_attempt_id") or "") != str(intent.get("submit_attempt_id") or ""):
                return mutation_error("submit_abort_invalid", "submit_abort.submit_attempt_id must match the prepared attempt")
            if artifact.get("command_started") is not False:
                return mutation_error("submit_abort_invalid", "submit abort requires command_started=false")
            if not truthy(artifact.get("evidence_ref")) or strict_aware_time(artifact.get("checked_at")) is None:
                return mutation_error("submit_abort_invalid", "submit abort requires evidence_ref and aware checked_at")
            if truthy(row.get("backend_submit_receipt")):
                return mutation_error("submit_abort_invalid", "a received backend submit cannot be aborted to planned")
            row.setdefault("aborted_submit_attempts", []).append(
                {
                    "intent": intent,
                    "intent_sha256": row.get("backend_submit_intent_sha256"),
                    "abort": artifact,
                    "abort_sha256": artifact_sha256,
                    "aborted_at": timestamp,
                }
            )
            for field in [
                "backend_submit_intent",
                "backend_submit_intent_ref",
                "backend_submit_intent_input_sha256",
                "backend_submit_intent_sha256",
                "submit_prepared_at",
            ]:
                row.pop(field, None)
            row["status"] = "planned"
        elif action == "record-backend-submit":
            if old_status not in {"submitting", "needs_sync"}:
                return mutation_error("status_conflict", "record-backend-submit requires a prepared submitting row")
            intent = row.get("backend_submit_intent") if isinstance(row.get("backend_submit_intent"), dict) else {}
            errors: list[str] = []
            for field in [
                "submit_attempt_id",
                "backend_idempotency_key",
                "anonymous_trace_id",
                "launch_identity_hash",
                "script_or_command_sha256",
                "preflight_sha256",
                "pool_id",
                "execution_route",
                "native_id",
                "accepted_at",
                "evidence_ref",
            ]:
                if not truthy(artifact.get(field)):
                    errors.append(f"submit_receipt.{field} is required")
            for field in [
                "submit_attempt_id",
                "backend_idempotency_key",
                "anonymous_trace_id",
                "launch_identity_hash",
                "script_or_command_sha256",
                "preflight_sha256",
                "pool_id",
                "execution_route",
            ]:
                if str(artifact.get(field) or "") != str(intent.get(field) or ""):
                    errors.append(f"submit_receipt.{field} must match the prepared intent")
            if strict_aware_time(artifact.get("accepted_at")) is None:
                errors.append("submit_receipt.accepted_at must be a timezone-aware timestamp")
            if errors:
                return mutation_error("submit_receipt_invalid", "submit receipt failed exact binding", errors=errors)
            row["backend_submit_receipt"] = dict(artifact)
            row["backend_submit_receipt_ref"] = path_ref(input_path, project)
            row["backend_submit_receipt_input_sha256"] = input_sha256
            row["backend_submit_receipt_sha256"] = artifact_sha256
            row["launch_started_at"] = artifact.get("accepted_at")
            row["native_backend_id"] = artifact.get("native_id")
            row["status"] = "needs_sync"
        elif action == "record-backend-observation":
            if old_status not in {"submitting", "needs_sync", "running"}:
                return mutation_error("status_conflict", "backend observation requires submitting, needs_sync, or running")
            intent = row.get("backend_submit_intent") if isinstance(row.get("backend_submit_intent"), dict) else {}
            receipt = row.get("backend_submit_receipt") if isinstance(row.get("backend_submit_receipt"), dict) else {}
            errors = []
            for field in ["submit_attempt_id", "anonymous_trace_id", "backend_state", "observed_at", "evidence_ref"]:
                if not truthy(artifact.get(field)):
                    errors.append(f"backend_observation.{field} is required")
            for field in ["submit_attempt_id", "anonymous_trace_id"]:
                if str(artifact.get(field) or "") != str(intent.get(field) or ""):
                    errors.append(f"backend_observation.{field} must match the prepared intent")
            if receipt and truthy(artifact.get("native_id")) and str(artifact.get("native_id")) != str(receipt.get("native_id")):
                errors.append("backend_observation.native_id conflicts with the submit receipt")
            if strict_aware_time(artifact.get("observed_at")) is None:
                errors.append("backend_observation.observed_at must be a timezone-aware timestamp")
            backend_state = str(artifact.get("backend_state") or "").strip().lower()
            allowed_states = {"unknown", "not_found", "pending", "running", "completed", "failed", "cancelled"}
            if backend_state not in allowed_states:
                errors.append(f"backend_observation.backend_state must be one of {sorted(allowed_states)}")
            if backend_state not in {"unknown", "not_found"} and not truthy(artifact.get("native_id")):
                errors.append("backend_observation.native_id is required for an authoritative non-unknown state")
            if errors:
                return mutation_error("backend_observation_invalid", "backend observation failed exact binding", errors=errors)
            observations = row.setdefault("backend_observations", [])
            if not isinstance(observations, list):
                observations = []
                row["backend_observations"] = observations
            observations.append({**artifact, "observation_sha256": artifact_sha256})
            row["backend_observation_sha256"] = artifact_sha256
            row["backend_observation_ref"] = path_ref(input_path, project)
            if truthy(artifact.get("native_id")):
                row["native_backend_id"] = artifact.get("native_id")
            if backend_state in {"pending", "running"}:
                row["status"] = "running"
                row["resource_allocation"] = copy.deepcopy(allocation)
            elif backend_state in {"failed", "cancelled"}:
                row["status"] = "blocked"
                row["backend_reconcile"] = {
                    "status": "terminal",
                    "checked_at": artifact.get("observed_at"),
                    "evidence_ref": artifact.get("evidence_ref"),
                }
            elif backend_state == "completed":
                row["status"] = "needs_sync"
            elif old_status == "running":
                row["status"] = "running"
            elif receipt:
                row["status"] = "needs_sync"
            else:
                row["status"] = "submitting"
        else:
            return mutation_error("unsupported_action", action)

        row["row_revision"] = int(row.get("row_revision") or 0) + 1
        row["updated_at"] = timestamp
        queue["queue_revision"] = current_revision + 1
        queue["updated_at"] = timestamp
        append_queue_event(
            queue,
            {
                "decision": "queue_" + action.replace("-", "_"),
                "rationale": str(args.reason),
                "owner": owner,
                "row_id": row_id,
                "old_status": old_status,
                "new_status": row.get("status"),
                "artifact_ref": path_ref(input_path, project),
                "artifact_sha256": artifact_sha256,
                "submit_attempt_id": (
                    artifact.get("submit_attempt_id")
                    or (row.get("backend_submit_intent") or {}).get("submit_attempt_id")
                ),
            },
        )
        atomic_write_json(queue_path, queue)
        return 0, {
            "ok": True,
            "idempotent": False,
            "action": action,
            "row_id": row_id,
            "old_status": old_status,
            "status": row.get("status"),
            "queue_revision": queue.get("queue_revision"),
            "row_revision": row.get("row_revision"),
            "artifact_sha256": artifact_sha256,
            "submit_attempt_id": (
                artifact.get("submit_attempt_id")
                or (row.get("backend_submit_intent") or {}).get("submit_attempt_id")
            ),
            "native_id": row.get("native_backend_id"),
        }


def exact_resource_pool(queue: dict[str, Any], pool_id: str) -> dict[str, Any] | None:
    snapshot = queue.get("resource_snapshot") if isinstance(queue.get("resource_snapshot"), dict) else {}
    pools = snapshot.get("pools") if isinstance(snapshot.get("pools"), list) else []
    for pool in pools:
        if isinstance(pool, dict) and str(pool.get("pool_id") or "") == pool_id:
            return pool
    return None


def find_row(queue: dict[str, Any], row_id: str) -> dict[str, Any] | None:
    for row in queue.get("rows", []) if isinstance(queue.get("rows"), list) else []:
        if isinstance(row, dict) and str(row.get("id") or "") == row_id:
            return row
    return None


def append_queue_decision(
    queue: dict[str, Any], row: dict[str, Any], action: str, old_status: str, owner: str, reason: str
) -> None:
    log = queue.setdefault("decision_log", [])
    if not isinstance(log, list):
        log = []
        queue["decision_log"] = log
    log.append(
        {
            "timestamp": now_iso(),
            "decision": f"queue_{action}",
            "rationale": reason,
            "row_id": row.get("id"),
            "old_status": old_status,
            "new_status": row.get("status"),
            "owner": owner,
            "queue_revision": queue.get("queue_revision"),
            "row_revision": row.get("row_revision"),
            "evidence_paths": row.get("evidence_paths") or [],
        }
    )


def mutate_queue(args: argparse.Namespace, action: str) -> tuple[int, dict[str, Any]]:
    project = project_root(args.project)
    queue_path = project / QUEUE_REL
    owner = str(args.owner).strip()
    row_id = str(args.row_id).strip()
    with queue_lock(queue_path):
        queue = load_queue(project)
        if not queue:
            return mutation_error("queue_missing", "NEXT_EXPERIMENT_QUEUE.json is missing")
        if queue.get("schema_version") != 2:
            return mutation_error("migration_required", "queue mutations require schema_version=2")
        policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
        admission_scope = str(policy.get("admission_scope") or "project").strip().lower()
        row = find_row(queue, row_id)
        if row is None:
            return mutation_error("row_missing", f"queue row {row_id!r} does not exist")
        current_revision = queue.get("queue_revision")
        expected = getattr(args, "expected_revision", None)

        if action == "claim" and str(row.get("lease_owner") or "") == owner and str(row.get("status") or "") in {"planned", "submitting", "needs_sync", "running"}:
            return 0, {
                "ok": True,
                "idempotent": True,
                "action": action,
                "row_id": row_id,
                "status": row.get("status"),
                "queue_revision": current_revision,
                "row_revision": row.get("row_revision", 0),
                "lease_owner": owner,
                "lease_expires_at": row.get("lease_expires_at"),
            }
        if action == "claim-assignment" and str(row.get("lease_owner") or "") == owner and str(row.get("status") or "") in {"planned", "submitting", "needs_sync", "running"}:
            allocation = row.get("planned_resource_allocation")
            requested_pool = str(getattr(args, "pool_id", "") or "").strip()
            same_global_authority = admission_scope != "global" or (
                isinstance(allocation, dict)
                and str(allocation.get("global_schedule_sha256") or "")
                == str(getattr(args, "global_schedule_sha256", "") or "")
                and str(allocation.get("assignment_sha256") or "")
                == str(getattr(args, "assignment_sha256", "") or "")
            )
            if (
                isinstance(allocation, dict)
                and str(allocation.get("pool_id") or "") == requested_pool
                and same_global_authority
            ):
                return 0, {
                    "ok": True,
                    "idempotent": True,
                    "action": action,
                    "row_id": row_id,
                    "pool_id": requested_pool,
                    "status": row.get("status"),
                    "queue_revision": current_revision,
                    "row_revision": row.get("row_revision", 0),
                    "lease_owner": owner,
                    "lease_expires_at": row.get("lease_expires_at"),
                    "planned_resource_allocation": allocation,
                }
            return mutation_error(
                "assignment_conflict",
                "same-owner idempotence requires identical row, pool, schedule, and assignment hashes",
                requested_pool_id=requested_pool,
                planned_pool_id=allocation.get("pool_id") if isinstance(allocation, dict) else None,
            )
        if expected is not None and expected != current_revision:
            return mutation_error(
                "stale_plan",
                "queue revision changed before mutation",
                expected_revision=expected,
                current_revision=current_revision,
            )

        old_status = str(row.get("status") or "")
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
        reason = str(getattr(args, "reason", "") or action)

        if action == "claim-assignment":
            if old_status != "ready":
                return mutation_error("status_conflict", f"cannot claim an assignment for row in status {old_status!r}")
            requested_pool = str(getattr(args, "pool_id", "") or "").strip()
            if not requested_pool:
                return mutation_error("pool_missing", "claim-assignment requires a nonempty pool id")
            global_context: dict[str, Any] | None = None
            if admission_scope == "global":
                global_context, global_error = global_claim_context(
                    args,
                    project,
                    queue,
                    row_id,
                    requested_pool,
                    owner,
                )
                if global_error is not None:
                    return global_error
                first = dict(global_context["assignment"])
                queue["resource_snapshot"] = copy.deepcopy(global_context["snapshot"])
            else:
                scheduled = select_launch_batch(queue, project)
                if not scheduled.get("ok"):
                    return mutation_error(
                        "assignment_unavailable",
                        "queue validation failed while recomputing the deterministic assignment",
                        schedule=scheduled,
                    )
                assignments = scheduled.get("assignments") if isinstance(scheduled.get("assignments"), list) else []
                if not assignments:
                    return mutation_error(
                        "assignment_unavailable",
                        "no deterministic assignment is currently launchable",
                        schedule_reason=scheduled.get("reason"),
                        requires_resource_refresh=scheduled.get("requires_resource_refresh"),
                        rejected=scheduled.get("rejected") or [],
                    )
                first = assignments[0] if isinstance(assignments[0], dict) else {}
            first_row_id = str(first.get("row_id") or "")
            first_pool_id = str(first.get("pool_id") or "")
            if first_row_id != row_id or first_pool_id != requested_pool:
                return mutation_error(
                    "assignment_conflict",
                    "requested row and pool are not the current first deterministic assignment",
                    requested_row_id=row_id,
                    requested_pool_id=requested_pool,
                    first_row_id=first_row_id,
                    first_pool_id=first_pool_id,
                    queue_revision=current_revision,
                )
            if str(first.get("fit_confidence") or "") == "aggregate_unverified":
                return mutation_error(
                    "pool_unverified",
                    "claim-assignment requires a detailed physical/account resource pool, not aggregate fallback capacity",
                )
            pool = exact_resource_pool(queue, requested_pool)
            if pool is None:
                return mutation_error("pool_missing", "scheduled physical resource pool disappeared before the atomic claim")
            route = row_execution_route(row)
            pool_backend = str(pool.get("backend") or "").strip().lower()
            pool_route = str(pool.get("execution_route") or pool_backend).strip().lower()
            request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
            request_backend = str(request.get("backend") or "").strip().lower()
            if route and (request_backend != route or pool_backend != route or pool_route != route):
                return mutation_error(
                    "route_identity_mismatch",
                    "resource_request backend, execution route, and selected pool must match exactly",
                    execution_route=route,
                    request_backend=request_backend,
                    pool_backend=pool_backend,
                    pool_execution_route=pool_route,
                )
            slots_before = pool_launch_slots(pool)
            gpu_count = nonnegative_int(first.get("gpu_count"), 0) or 0
            if gpu_count <= 0 or slots_before < gpu_count:
                return mutation_error(
                    "capacity_conflict",
                    "scheduled pool no longer has enough explicit launch slots",
                    pool_id=requested_pool,
                    launch_slots=slots_before,
                    gpu_count=gpu_count,
                )
            lease_minutes = int(getattr(args, "lease_minutes", 30))
            if lease_minutes <= 0:
                return mutation_error("lease_invalid", "lease_minutes must be positive")

            snapshot = queue.get("resource_snapshot") if isinstance(queue.get("resource_snapshot"), dict) else {}
            snapshot_sha256 = (
                str(global_context.get("snapshot_sha256") or "")
                if global_context is not None
                else canonical_payload_sha256(snapshot)
            )
            slots_after = slots_before - gpu_count
            concrete_ids = (
                list(global_context.get("allocated_resource_ids") or [])
                if global_context is not None
                else concrete_pool_resource_ids(pool)[:gpu_count]
            )
            allocation = {
                "pool_id": requested_pool,
                "backend": first.get("backend") or pool.get("backend"),
                "execution_route": route or pool.get("execution_route") or first.get("backend") or pool.get("backend"),
                "account_ref": first.get("account_ref") or pool.get("account_ref") or pool.get("account"),
                "host_ref": first.get("host_ref") or pool.get("host_ref") or pool.get("host"),
                "node_ref": first.get("node_ref") or pool.get("node_ref"),
                "gpu_uuids": as_str_list(pool.get("gpu_uuids")),
                "resource_ids": as_str_list(pool.get("resource_ids")),
                "allocated_resource_ids": concrete_ids,
                "gpu_count": gpu_count,
                "estimated_gpu_hours": first.get("estimated_gpu_hours"),
                "fit_confidence": first.get("fit_confidence"),
                "project_execution_passport_index_sha256": row.get(
                    "project_execution_passport_index_sha256"
                ),
                "execution_profile_id": row.get("execution_profile_id"),
                "execution_profile_sha256": row.get("execution_profile_sha256"),
                "requires_fresh_backend_preflight": True,
                "resource_snapshot_sha256": snapshot_sha256,
                "resource_snapshot_source_ref": snapshot.get("source_ref"),
                "resource_snapshot_source_sha256": snapshot.get("source_sha256"),
                "resource_snapshot_checked_at": snapshot.get("checked_at"),
                "launch_slots_before": slots_before,
                "launch_slots_after": slots_after,
                "claimed_at": timestamp.isoformat(),
            }
            if global_context is not None:
                allocation.update(
                    {
                        "admission_scope": "global",
                        "global_plan_ref": str(global_context.get("plan_path")),
                        "global_schedule_sha256": global_context.get("schedule_sha256"),
                        "assignment_sha256": global_context.get("assignment_sha256"),
                        "global_lease_file": str(global_context.get("global_lease_path")),
                    }
                )
            else:
                allocation["admission_scope"] = "project"
            row["status"] = "planned"
            row["lease_owner"] = owner
            row["owner_thread_id"] = owner
            row["lease_acquired_at"] = timestamp.isoformat()
            row["lease_expires_at"] = (timestamp + timedelta(minutes=lease_minutes)).isoformat()
            row["planned_resource_allocation"] = allocation
            projected_routes = canonical_outcome_routes(row.get("outcome_routes"))
            if all(truthy(projected_routes.get(key)) for key in OUTCOME_ROUTE_KEYS):
                row["outcome_routes"] = projected_routes

            pool["launch_slots"] = slots_after
            if slots_after == 0:
                pool["status"] = "full"
            pool["last_claimed_at"] = timestamp.isoformat()
            pool["last_claimed_row_id"] = row_id
            snapshot["status"] = "stale"
            snapshot["fresh"] = False
            snapshot["stale"] = True
            snapshot["stale_at"] = timestamp.isoformat()
            snapshot["stale_reason"] = "assignment_claimed_requires_backend_refresh"
            snapshot["last_assignment_claim"] = {
                "row_id": row_id,
                "pool_id": requested_pool,
                "owner": owner,
                "gpu_count": gpu_count,
                "launch_slots_before": slots_before,
                "launch_slots_after": slots_after,
            }
            if global_context is not None:
                snapshot["last_assignment_claim"].update(
                    {
                        "global_schedule_sha256": global_context.get("schedule_sha256"),
                        "assignment_sha256": global_context.get("assignment_sha256"),
                    }
                )
        elif action == "claim":
            if old_status not in {"ready", "planned", "running"}:
                return mutation_error("status_conflict", f"cannot claim row in status {old_status!r}")
            row_errors = strict_launch_errors(row, row_id) + project_authority_errors(project, row, row_id)
            if row_errors:
                return mutation_error("identity_missing", "row is not launch-ready", errors=row_errors)
            existing_owner = str(row.get("lease_owner") or "")
            if existing_owner and existing_owner != owner and not lease_expired(row):
                return mutation_error("lease_conflict", "row has a live lease", lease_owner=existing_owner)
            if existing_owner and existing_owner != owner and lease_expired(row):
                live = matching_live_run(project, row)
                if live:
                    return mutation_error("lease_conflict", "expired lease still has a live backend run", backend=live)
                if launch_was_started(row) and not backend_reconciled_no_live(row):
                    return mutation_error(
                        "backend_reconcile_required",
                        "expired launched row needs explicit backend no-live evidence before re-claim",
                    )
            lease_minutes = int(getattr(args, "lease_minutes", 30))
            if lease_minutes <= 0:
                return mutation_error("lease_invalid", "lease_minutes must be positive")
            row["status"] = "planned"
            row["lease_owner"] = owner
            row["owner_thread_id"] = owner
            row["lease_acquired_at"] = timestamp.isoformat()
            row["lease_expires_at"] = (timestamp + timedelta(minutes=lease_minutes)).isoformat()
        elif action == "renew":
            if old_status not in {"planned", "submitting", "needs_sync", "running"}:
                return mutation_error("status_conflict", f"cannot renew row in status {old_status!r}")
            if str(row.get("lease_owner") or "") != owner:
                return mutation_error("lease_conflict", "only the current lease owner can renew")
            lease_minutes = int(getattr(args, "lease_minutes", 30))
            if lease_minutes <= 0:
                return mutation_error("lease_invalid", "lease_minutes must be positive")
            row["lease_expires_at"] = (timestamp + timedelta(minutes=lease_minutes)).isoformat()
        elif action == "release":
            if old_status not in {"planned", "running"}:
                return mutation_error("status_conflict", f"cannot release row in status {old_status!r}")
            if str(row.get("lease_owner") or "") != owner:
                return mutation_error("lease_conflict", "only the current lease owner can release")
            if launch_was_started(row):
                live = matching_live_run(project, row)
                if live:
                    return mutation_error("backend_live", "release does not cancel a live backend run", backend=live)
                if not backend_reconciled_no_live(row):
                    return mutation_error("backend_reconcile_required", "launched row needs explicit backend reconciliation before release")
            planned_allocation = row.get("planned_resource_allocation") if isinstance(row.get("planned_resource_allocation"), dict) else None
            row["status"] = "ready"
            for field in ["lease_owner", "lease_acquired_at", "lease_expires_at", "planned_resource_allocation"]:
                row.pop(field, None)
            if str(row.get("owner_thread_id") or "") == owner:
                row.pop("owner_thread_id", None)
            if planned_allocation is not None:
                snapshot = queue.get("resource_snapshot") if isinstance(queue.get("resource_snapshot"), dict) else {}
                snapshot["status"] = "stale"
                snapshot["fresh"] = False
                snapshot["stale"] = True
                snapshot["stale_at"] = timestamp.isoformat()
                snapshot["stale_reason"] = "assignment_released_requires_backend_refresh"
                snapshot["last_assignment_release"] = {
                    "row_id": row_id,
                    "pool_id": planned_allocation.get("pool_id"),
                    "owner": owner,
                    "released_at": timestamp.isoformat(),
                    "capacity_restored_without_refresh": False,
                }
        elif action == "complete":
            target_status = str(args.status)
            if target_status not in TERMINAL_MUTATION_STATUSES:
                return mutation_error("status_conflict", f"unsupported completion status {target_status!r}")
            lease_owner = str(row.get("lease_owner") or "")
            if lease_owner and lease_owner != owner:
                return mutation_error("lease_conflict", "only the current lease owner can complete")
            evidence = str(args.evidence).strip()
            if not evidence:
                return mutation_error("evidence_missing", "complete requires an evidence path")
            paths = row.get("evidence_paths") if isinstance(row.get("evidence_paths"), list) else []
            if evidence not in paths:
                paths.append(evidence)
            row["evidence_paths"] = paths
            row["status"] = target_status
            row["completed_at"] = timestamp.isoformat()
            for field in ["lease_owner", "lease_acquired_at", "lease_expires_at"]:
                row.pop(field, None)
        else:
            return mutation_error("unsupported_action", action)

        row["row_revision"] = int(row.get("row_revision") or 0) + 1
        row["updated_at"] = timestamp.isoformat()
        queue["queue_revision"] = int(queue.get("queue_revision") or 0) + 1
        queue["updated_at"] = timestamp.isoformat()
        append_queue_decision(queue, row, action, old_status, owner, reason)
        atomic_write_json(queue_path, queue)
        return 0, {
            "ok": True,
            "idempotent": False,
            "action": action,
            "row_id": row_id,
            "old_status": old_status,
            "status": row.get("status"),
            "queue_revision": queue.get("queue_revision"),
            "row_revision": row.get("row_revision"),
            "lease_owner": row.get("lease_owner"),
            "lease_expires_at": row.get("lease_expires_at"),
            "planned_resource_allocation": row.get("planned_resource_allocation"),
        }


def md(value: Any) -> str:
    text = str(value if value is not None else "").replace("\n", " ").strip()
    text = text.replace("|", "\\|")
    return text


def compact_paths(value: Any, limit: int = 3) -> str:
    if not isinstance(value, list) or not value:
        return ""
    shown = [str(item) for item in value[:limit]]
    if len(value) > limit:
        shown.append(f"+{len(value) - limit} more")
    return "<br>".join(md(item) for item in shown)


def innovation_label(row: dict[str, Any]) -> str:
    innovation_id = str(row.get("innovation_id") or "").strip()
    if innovation_id:
        return innovation_id
    components = as_str_list(row.get("component_innovation_ids"))
    return "+".join(components)


def resource_label(row: dict[str, Any]) -> str:
    source = row.get("resource_allocation") if isinstance(row.get("resource_allocation"), dict) else None
    if source is None:
        source = (
            row.get("planned_resource_allocation")
            if isinstance(row.get("planned_resource_allocation"), dict)
            else None
        )
    if source is None:
        source = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    parts = []
    for key in ("backend", "host", "account", "gpu_id", "gpu_uuid", "gpu_count"):
        value = str(source.get(key) or "").strip()
        if value:
            parts.append(f"{key}={value}")
    mutex = str(row.get("mutex_group") or "").strip()
    if mutex:
        parts.append(f"mutex={mutex}")
    return ", ".join(parts)


def queue_rows(queue: dict[str, Any]) -> list[dict[str, Any]]:
    rows = queue.get("rows")
    if not isinstance(rows, list):
        return []
    return sorted([row for row in rows if isinstance(row, dict)], key=row_priority)


def render_project_markdown(queue: dict[str, Any], queue_path: Path) -> str:
    validation = validate_queue(queue)
    wiki = queue.get("wiki") if isinstance(queue.get("wiki"), dict) else {}
    policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
    project = Path(str(queue.get("project_root") or queue_path.parents[2])).expanduser().resolve()
    frontier = frontier_status(queue, project=project)
    control_lease = project_control_lease_busy(project)
    lines: list[str] = [
        "# NEXT_EXPERIMENT_ACTIONS",
        "",
        "> Generated from `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json`. Edit the JSON queue, then re-render. This page is a dashboard only; it does not complete stages, promote claims, or submit jobs.",
        "",
        f"- Generated at: `{now_iso()}`",
        f"- Project: `{md(queue.get('project_root'))}`",
        f"- Direction: `{md(queue.get('direction'))}`",
        f"- Queue: `{md(queue_path)}`",
        f"- Dashboard: `{md(wiki.get('project_dashboard_path'))}`",
        f"- Validation: `{'PASS' if validation['ok'] else 'FAIL'}`",
        f"- Admission scope: `{md(policy.get('admission_scope') or 'project')}`",
        f"- Program claim: status `{md(frontier['program_contract_status'])}`, mode `{md(frontier['program_contract_enforcement_mode'])}`, scientific status `{md(frontier['program_scientific_status'])}`, hash `{md(frontier.get('program_claim_contract_sha256') or 'none')}`",
        f"- Project control owner: `{md((control_lease or {}).get('owner_id') or 'none')}`",
        f"- Launch frontier: target `{frontier['launch_frontier_target']}`, supply `{frontier['launch_frontier_supply_count']}`, deficit `{frontier['launch_frontier_deficit']}`, blocker `{md(frontier['launch_frontier_blocker_code'])}`",
        f"- Ready frontier (compatibility alias): `{frontier['frontier_ready_count']}` / `{frontier['frontier_target']}`",
        f"- Portfolio: target `{frontier['portfolio_capacity_target']}`, active `{frontier['active_nonterminal_track_count']}`, admission deficit `{frontier['portfolio_admission_deficit']}`, fillable `{frontier['portfolio_fillable_count']}`, blocker `{md(frontier['portfolio_blocker_code'])}`",
        f"- Method portfolio: target `{frontier['method_portfolio_target']}`, active `{frontier['active_method_candidate_count']}`, deficit `{frontier['method_portfolio_deficit']}`, fillable `{len(frontier['method_portfolio_fillable_candidate_ids'])}`",
        f"- Diagnostic/control tracks: `{frontier['diagnostic_active_track_count']}`",
        f"- Fillable candidates: `{md(', '.join(frontier['portfolio_fillable_candidate_ids']) or 'none')}`",
        f"- Parameter profiles: `{md(json.dumps(frontier['parameter_profile_status_by_track'], ensure_ascii=False, sort_keys=True))}`",
        f"- Parameter value deficits: `{md(json.dumps(frontier['parameter_coverage_deficit_by_track_and_dataset'], ensure_ascii=False, sort_keys=True))}`",
        f"- Parameter groups: ready probes `{frontier['parameter_probe_ready_count']}`, incomplete calibration groups `{frontier['parameter_calibration_group_incomplete_count']}`, pending scale audits `{frontier['parameter_scale_audit_pending_count']}`",
        f"- Parameter blockers: `{md(json.dumps(frontier['parameter_blockers'], ensure_ascii=False, sort_keys=True))}`",
        f"- Dataset coverage deficits: `{md(json.dumps(frontier['dataset_coverage_deficit_by_track'], ensure_ascii=False, sort_keys=True))}`",
        f"- Paired Stage-2 groups: incomplete `{frontier['paired_group_incomplete_count']}`; full-budget ready `{frontier['cross_dataset_full_budget_ready_count']}`; robust HPO ready `{frontier['robust_hpo_ready_count']}`",
        "",
        "## Decision Rules",
        "",
        "- Choose by paper evidence gap, not GPU utilization.",
        "- First cover best single-innovation performance across target datasets; then test the best unlocked combinations.",
        "- Prioritize terminal/first-metric/failure sync before new submissions.",
        "- A running row is not a global barrier; launch independent ready rows when resource_request fits idle GPUs/resources.",
        "- Run combo rows only after their named single-innovation gates are non-negative, unless explicitly marked diagnostic.",
        "- Avoid exhaustive combo search; keep only the strongest compatible candidates active per dataset.",
        "- Keep comparison labels explicit: paper-reported, reproduced, matched reproduced, or not established.",
        "- Random-seed stability validation is capped at three seeds.",
        "- Use backend skills for Slurm/SSH submission and live queue safety.",
        "",
    ]
    if validation["errors"]:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {md(item)}" for item in validation["errors"])
        lines.append("")
    if validation["warnings"]:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {md(item)}" for item in validation["warnings"])
        lines.append("")

    lines.extend(
        [
            "## Queue",
            "",
            "| P | ID | Status | Role | Track | Track Role | Evidence Ceiling | Dataset | Innovation/Components | Resource | Variant | Next Action | Blocker | Owner | Evidence |",
            "|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    rows = queue_rows(queue)
    if rows:
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        md(row.get("priority")),
                        md(row.get("id")),
                        md(row.get("status")),
                        md(row.get("role")),
                        md(row.get("track_id")),
                        md(row.get("track_role")),
                        md(row.get("evidence_tier_ceiling") or row.get("evidence_tier")),
                        md(row.get("dataset")),
                        md(innovation_label(row)),
                        md(resource_label(row)),
                        md(row.get("variant")),
                        md(row.get("next_action")),
                        md(row.get("blocker")),
                        md(row.get("owner_thread_id")),
                        compact_paths(row.get("evidence_paths")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("|  |  |  |  |  |  |  |  |  |  |  | No rows yet. Add rows to the JSON queue. |  |  |  |")
    lines.append("")

    decision_log = queue.get("decision_log")
    if isinstance(decision_log, list) and decision_log:
        lines.extend(["## Decision Log", ""])
        for item in decision_log[-10:]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{md(item.get('timestamp'))}` {md(item.get('decision'))}: {md(item.get('rationale'))}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_global_markdown(project_queues: list[tuple[Path, dict[str, Any]]]) -> str:
    lines: list[str] = [
        "# Active Experiment Next Actions",
        "",
        "> Generated rollup from project-local `NEXT_EXPERIMENT_QUEUE.json` files. Project queues remain the planning authority.",
        "",
        f"- Generated at: `{now_iso()}`",
        "",
        "## Project Control",
        "",
        "| Project | Admission Scope | Method Active/Target | Method Deficit | Paired Incomplete | Frontier Target | Supply | Deficit | Blocker | Control Owner |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for project, queue in project_queues:
        project_name = str(queue.get("project_slug") or project.name)
        policy = queue.get("policy") if isinstance(queue.get("policy"), dict) else {}
        frontier = frontier_status(queue, project=project)
        control_lease = project_control_lease_busy(project)
        lines.append(
            "| "
            + " | ".join(
                [
                    md(project_name),
                    md(policy.get("admission_scope") or "project"),
                    md(f"{frontier.get('method_active_track_count')}/{frontier.get('method_portfolio_target')}"),
                    md(frontier.get("method_admission_deficit")),
                    md(frontier.get("paired_group_incomplete_count")),
                    md(frontier.get("frontier_target")),
                    md(frontier.get("frontier_supply_count")),
                    md(frontier.get("frontier_deficit")),
                    md(frontier.get("frontier_blocker_code")),
                    md((control_lease or {}).get("owner_id") or "none"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Active Rows",
            "",
            "| P | Project | Direction | ID | Status | Role | Track | Track Role | Evidence Ceiling | Dataset | Variant | Next Action | Blocker |",
            "|---:|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    rows_added = 0
    for project, queue in project_queues:
        project_name = str(queue.get("project_slug") or project.name)
        direction = str(queue.get("direction") or infer_direction(project))
        for row in queue_rows(queue):
            if str(row.get("status")) in {"dropped", "superseded"}:
                continue
            rows_added += 1
            lines.append(
                "| "
                + " | ".join(
                    [
                        md(row.get("priority")),
                        md(project_name),
                        md(direction),
                        md(row.get("id")),
                        md(row.get("status")),
                        md(row.get("role")),
                        md(row.get("track_id")),
                        md(row.get("track_role")),
                        md(row.get("evidence_tier_ceiling") or row.get("evidence_tier")),
                        md(row.get("dataset")),
                        md(row.get("variant")),
                        md(row.get("next_action")),
                        md(row.get("blocker")),
                    ]
                )
                + " |"
            )
    if rows_added == 0:
        lines.append("|  |  |  |  |  |  |  |  |  |  |  | No active rows found. |  |")
    return "\n".join(lines).rstrip() + "\n"


def cmd_init(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    errors: list[str] = []
    config = merged_config(project, args.direction, args.wiki_root, args.wiki_path, args.global_path, errors)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    config_path = project / CONFIG_REL
    queue_path = project / QUEUE_REL
    should_write_config = not config_path.exists() or any(
        [args.direction, args.wiki_root, args.wiki_path, args.global_path]
    )
    if should_write_config:
        write_json(config_path, config)

    if queue_path.exists():
        queue = read_json(queue_path, errors)
        created_queue = False
    else:
        queue = default_queue(project, config)
        write_json(queue_path, queue)
        created_queue = True

    out_path = Path(str(args.out or queue.get("wiki", {}).get("project_dashboard_path") or config["project_dashboard_path"]))
    write_text(out_path, render_project_markdown(queue, queue_path))
    validation = validate_queue(queue, project)
    result = {
        "ok": validation["ok"] and not errors,
        "created_queue": created_queue,
        "config_path": str(config_path),
        "queue_path": str(queue_path),
        "dashboard_path": str(out_path),
        "validation": validation,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_check(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    errors: list[str] = []
    queue = load_queue(project, errors)
    validation = validate_queue(queue, project)
    frontier = frontier_status(queue, project=project) if queue else {}
    payload = {
        "ok": validation["ok"] and not errors,
        "queue_path": str(project / QUEUE_REL),
        "errors": errors + validation["errors"],
        "warnings": validation["warnings"],
        "details": validation["details"],
        "frontier": frontier,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def cmd_schedule(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    errors: list[str] = []
    queue = load_queue(project, errors)
    if errors or not queue:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "queue_missing_or_invalid",
                    "errors": errors or ["NEXT_EXPERIMENT_QUEUE.json is missing or empty"],
                    "selected_count": 0,
                    "selected_row_ids": [],
                    "assignments": [],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    payload = select_launch_batch(queue, project)
    payload["frontier"] = frontier_status(queue, project=project)
    payload["queue_path"] = str(project / QUEUE_REL)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def cmd_frontier(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    errors: list[str] = []
    queue = load_queue(project, errors)
    if errors or not queue:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "queue_missing_or_invalid",
                    "errors": errors or ["NEXT_EXPERIMENT_QUEUE.json is missing or empty"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    validation = validate_queue(queue, project)
    payload = {
        "ok": validation["ok"],
        "queue_path": str(project / QUEUE_REL),
        "queue_revision": queue.get("queue_revision"),
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        **frontier_status(queue, project=project),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def cmd_schedule_global(args: argparse.Namespace) -> int:
    snapshot_path = Path(args.resource_snapshot).expanduser().resolve()
    try:
        snapshot_payload, _ = strict_json_object(snapshot_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "ok": False,
            "reason": "resource_snapshot_invalid",
            "errors": [f"cannot read strict shared resource snapshot: {exc}"],
            "assignments": [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    snapshot = snapshot_payload.get("resource_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = snapshot_payload

    project_queues: list[tuple[Path, dict[str, Any]]] = []
    exclusions: dict[str, dict[str, Any]] = {}
    input_errors: list[str] = []
    seen_projects: set[Path] = set()
    for value in args.project:
        project = project_root(value)
        if project in seen_projects:
            input_errors.append(f"duplicate project root: {project}")
            continue
        seen_projects.add(project)
        errors: list[str] = []
        queue = load_queue(project, errors)
        if errors or not queue:
            input_errors.extend(f"{project}: {error}" for error in (errors or ["queue missing or empty"]))
            continue
        project_queues.append((project, queue))
        busy = project_control_lease_busy(project, str(args.owner or "").strip())
        if busy:
            exclusions[str(project)] = busy
    if not project_queues:
        payload = {
            "ok": False,
            "reason": "no_readable_project_queue",
            "errors": input_errors or ["no project queue was supplied"],
            "assignments": [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    payload = select_global_launch_batch(
        project_queues,
        snapshot,
        resource_snapshot_ref=str(snapshot_path),
        excluded_projects=exclusions,
    )
    if input_errors:
        payload.setdefault("warnings", []).extend(input_errors)
    if payload.get("ok"):
        out_path = Path(args.out).expanduser().resolve()
        atomic_write_json(out_path, payload)
        payload["out_path"] = str(out_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def cmd_render(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    errors: list[str] = []
    config = merged_config(project, args.direction, args.wiki_root, args.wiki_path, args.global_path, errors)
    queue = load_queue(project, errors)
    validation = validate_queue(queue, project)
    if errors or not queue:
        print(json.dumps({"ok": False, "errors": errors + validation["errors"]}, ensure_ascii=False, indent=2))
        return 1
    wiki = queue.get("wiki") if isinstance(queue.get("wiki"), dict) else {}
    out_path = Path(str(args.out or wiki.get("project_dashboard_path") or config["project_dashboard_path"]))
    write_text(out_path, render_project_markdown(queue, project / QUEUE_REL))
    payload = {
        "ok": validation["ok"],
        "dashboard_path": str(out_path),
        "queue_path": str(project / QUEUE_REL),
        "errors": validation["errors"],
        "warnings": validation["warnings"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if validation["ok"] else 1


def cmd_render_global(args: argparse.Namespace) -> int:
    errors: list[str] = []
    project_queues: list[tuple[Path, dict[str, Any]]] = []
    warnings: list[str] = []
    for value in args.project:
        project = project_root(value)
        queue = load_queue(project, errors)
        validation = validate_queue(queue, project)
        if validation["errors"]:
            errors.extend(f"{project}: {error}" for error in validation["errors"])
        warnings.extend(f"{project}: {warning}" for warning in validation["warnings"])
        if queue:
            project_queues.append((project, queue))
    out_path = Path(str(args.out or DEFAULT_GLOBAL_DASHBOARD)).expanduser()
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 1
    write_text(out_path, render_global_markdown(project_queues))
    print(
        json.dumps(
            {
                "ok": True,
                "dashboard_path": str(out_path),
                "project_count": len(project_queues),
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def emit_mutation(args: argparse.Namespace, action: str) -> int:
    code, payload = mutate_queue(args, action)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def cmd_claim(args: argparse.Namespace) -> int:
    return emit_mutation(args, "claim")


def cmd_claim_assignment(args: argparse.Namespace) -> int:
    return emit_mutation(args, "claim-assignment")


def cmd_renew(args: argparse.Namespace) -> int:
    return emit_mutation(args, "renew")


def cmd_release(args: argparse.Namespace) -> int:
    return emit_mutation(args, "release")


def cmd_complete(args: argparse.Namespace) -> int:
    return emit_mutation(args, "complete")


def cmd_commit_resource_snapshot(args: argparse.Namespace) -> int:
    code, payload = commit_resource_snapshot(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def cmd_set_policy(args: argparse.Namespace) -> int:
    code, payload = set_policy(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def cmd_record_backend_preflight(args: argparse.Namespace) -> int:
    code, payload = record_backend_preflight(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def cmd_prepare_backend_submit(args: argparse.Namespace) -> int:
    code, payload = mutate_submit_artifact(args, "prepare-backend-submit")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def cmd_abort_backend_submit(args: argparse.Namespace) -> int:
    code, payload = mutate_submit_artifact(args, "abort-backend-submit")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def cmd_record_backend_submit(args: argparse.Namespace) -> int:
    code, payload = mutate_submit_artifact(args, "record-backend-submit")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def cmd_record_backend_observation(args: argparse.Namespace) -> int:
    code, payload = mutate_submit_artifact(args, "record-backend-observation")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create project-local next-action queue and render dashboard.")
    init.add_argument("--project", required=True, help="Project root.")
    init.add_argument("--direction", help="Research direction, for example ContinueGCD.")
    init.add_argument("--wiki-root", help="Wiki root. Defaults to the user's mypaper directory.")
    init.add_argument("--wiki-path", help="Project dashboard path override.")
    init.add_argument("--global-path", help="Global dashboard path override.")
    init.add_argument("--out", help="Render path override for this invocation.")
    init.set_defaults(func=cmd_init)

    check = sub.add_parser("check", help="Validate project-local next-action queue.")
    check.add_argument("--project", required=True, help="Project root.")
    check.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    check.set_defaults(func=cmd_check)

    schedule = sub.add_parser("schedule", help="Dry-run deterministic row-to-resource assignment without claiming or launching.")
    schedule.add_argument("--project", required=True, help="Project root.")
    schedule.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    schedule.set_defaults(func=cmd_schedule)

    frontier = sub.add_parser("frontier", help="Compute bounded ready-frontier target and planning deficit without mutation.")
    frontier.add_argument("--project", required=True, help="Project root.")
    frontier.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    frontier.set_defaults(func=cmd_frontier)

    schedule_global = sub.add_parser(
        "schedule-global",
        help="Dry-run deterministic cross-project assignment against one fresh shared snapshot.",
    )
    schedule_global.add_argument("--project", action="append", required=True, help="Project root. Repeatable.")
    schedule_global.add_argument("--resource-snapshot", required=True, help="Fresh normalized shared resource snapshot JSON.")
    schedule_global.add_argument("--out", required=True, help="Output path for the ephemeral hashed schedule.")
    schedule_global.add_argument("--owner", default="global-scheduler", help="Read-only scheduler identity for project-lease exclusion.")
    schedule_global.set_defaults(func=cmd_schedule_global)

    render = sub.add_parser("render", help="Render project queue to Markdown dashboard.")
    render.add_argument("--project", required=True, help="Project root.")
    render.add_argument("--direction", help="Direction override for default path resolution.")
    render.add_argument("--wiki-root", help="Wiki root override.")
    render.add_argument("--wiki-path", help="Project dashboard path override.")
    render.add_argument("--global-path", help="Global dashboard path override.")
    render.add_argument("--out", help="Output Markdown path.")
    render.set_defaults(func=cmd_render)

    global_parser = sub.add_parser("render-global", help="Render a global rollup from one or more project queues.")
    global_parser.add_argument("--project", action="append", required=True, help="Project root. Repeatable.")
    global_parser.add_argument("--out", help="Output Markdown path.")
    global_parser.set_defaults(func=cmd_render_global)

    set_policy_parser = sub.add_parser(
        "set-policy",
        help="CAS-update local admission scope or bounded portfolio capacity without editing queue JSON.",
    )
    set_policy_parser.add_argument("--project", required=True)
    set_policy_parser.add_argument("--expected-revision", type=int, required=True)
    set_policy_parser.add_argument("--admission-scope", choices=["project", "global"])
    set_policy_parser.add_argument("--portfolio-capacity-target", type=int)
    set_policy_parser.add_argument("--owner", default="workflow-controller")
    set_policy_parser.add_argument("--reason", required=True)
    set_policy_parser.set_defaults(func=cmd_set_policy)

    commit_snapshot = sub.add_parser(
        "commit-resource-snapshot",
        help="Atomically install one normalized resource proposal under queue revision CAS.",
    )
    commit_snapshot.add_argument("--project", required=True)
    commit_snapshot.add_argument("--input", required=True, help="Normalized proposed_resource_snapshot JSON.")
    commit_snapshot.add_argument("--expected-revision", type=int, required=True)
    commit_snapshot.add_argument("--owner", default="resource-observer")
    commit_snapshot.add_argument("--reason", default="commit captured resource observation")
    commit_snapshot.set_defaults(func=cmd_commit_resource_snapshot)

    claim = sub.add_parser("claim", help="Atomically claim a launch-ready row for one local worker.")
    claim.add_argument("--project", required=True)
    claim.add_argument("--row-id", required=True)
    claim.add_argument("--owner", required=True)
    claim.add_argument("--expected-revision", type=int, required=True)
    claim.add_argument("--lease-minutes", type=int, default=30)
    claim.add_argument("--reason", default="claim decision-bearing row")
    claim.set_defaults(func=cmd_claim)

    claim_assignment = sub.add_parser(
        "claim-assignment",
        help="Atomically bind the first deterministic row and detailed resource pool without launching.",
    )
    claim_assignment.add_argument("--project", required=True)
    claim_assignment.add_argument("--row-id", required=True)
    claim_assignment.add_argument("--pool-id", required=True)
    claim_assignment.add_argument("--owner", required=True)
    claim_assignment.add_argument("--expected-revision", type=int, required=True)
    claim_assignment.add_argument("--lease-minutes", type=int, default=30)
    claim_assignment.add_argument("--global-plan", help="Current global schedule JSON; required in global admission mode.")
    claim_assignment.add_argument("--global-schedule-sha256", help="Canonical current global schedule hash.")
    claim_assignment.add_argument("--assignment-sha256", help="Canonical first-assignment hash.")
    claim_assignment.add_argument("--global-lease-file", help="Live global admission lease owned by --owner.")
    claim_assignment.add_argument("--reason", default="atomically claim first deterministic row and resource assignment")
    claim_assignment.set_defaults(func=cmd_claim_assignment)

    preflight = sub.add_parser(
        "record-backend-preflight",
        help="Atomically bind a fresh route-specific backend preflight to one planned row.",
    )
    preflight.add_argument("--project", required=True)
    preflight.add_argument("--row-id", required=True)
    preflight.add_argument("--owner", required=True)
    preflight.add_argument("--expected-revision", type=int, required=True)
    preflight.add_argument("--input", required=True, help="Backend preflight JSON or {backend_preflight: {...}}.")
    preflight.add_argument("--reason", default="record exact route-specific backend preflight")
    preflight.set_defaults(func=cmd_record_backend_preflight)

    for command, help_text, default_reason, func in [
        (
            "prepare-backend-submit",
            "Durably record an exact backend-searchable submit intent before any backend command.",
            "prepare one backend submit attempt before the side effect",
            cmd_prepare_backend_submit,
        ),
        (
            "abort-backend-submit",
            "Return a prepared attempt to planned only with proof that the backend command never started.",
            "abort a submit attempt proven not started",
            cmd_abort_backend_submit,
        ),
        (
            "record-backend-submit",
            "Bind one native backend receipt to a prepared submit attempt.",
            "record native backend acceptance receipt",
            cmd_record_backend_submit,
        ),
        (
            "record-backend-observation",
            "Apply one authoritative backend observation to a prepared or accepted attempt.",
            "reconcile authoritative backend state",
            cmd_record_backend_observation,
        ),
    ]:
        mutation = sub.add_parser(command, help=help_text)
        mutation.add_argument("--project", required=True)
        mutation.add_argument("--row-id", required=True)
        mutation.add_argument("--owner", required=True)
        mutation.add_argument("--expected-revision", type=int, required=True)
        mutation.add_argument("--input", required=True)
        mutation.add_argument("--reason", default=default_reason)
        mutation.set_defaults(func=func)

    renew = sub.add_parser("renew", help="Renew a lease owned by the same local worker.")
    renew.add_argument("--project", required=True)
    renew.add_argument("--row-id", required=True)
    renew.add_argument("--owner", required=True)
    renew.add_argument("--expected-revision", type=int)
    renew.add_argument("--lease-minutes", type=int, default=30)
    renew.add_argument("--reason", default="renew queue lease")
    renew.set_defaults(func=cmd_renew)

    release = sub.add_parser("release", help="Release an unlaunched or reconciled row without canceling backend work.")
    release.add_argument("--project", required=True)
    release.add_argument("--row-id", required=True)
    release.add_argument("--owner", required=True)
    release.add_argument("--expected-revision", type=int)
    release.add_argument("--reason", required=True)
    release.set_defaults(func=cmd_release)

    complete = sub.add_parser("complete", help="Record a terminal queue status with evidence.")
    complete.add_argument("--project", required=True)
    complete.add_argument("--row-id", required=True)
    complete.add_argument("--owner", required=True)
    complete.add_argument("--expected-revision", type=int)
    complete.add_argument("--status", required=True, choices=sorted(TERMINAL_MUTATION_STATUSES))
    complete.add_argument("--evidence", required=True)
    complete.add_argument("--reason", default="reconcile terminal queue status")
    complete.set_defaults(func=cmd_complete)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
