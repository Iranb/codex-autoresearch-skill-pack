#!/usr/bin/env python3
"""Lint EXPERIMENT_REVIEW_PACKET before experiment launch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hpo_policy_lint import validate_hpo_search_policy


REQUIRED = [
    "track_id",
    "claim_ids",
    "hypothesis",
    "novelty_basis",
    "idea_pool_path",
    "selected_idea_id",
    "idea_generation_scope",
    "pre_idea_evidence_gate_path",
    "innovation_slot_map_path",
    "consumed_innovation_slot_ids",
    "innovation_search_contract",
    "promotion_gate",
    "one_variable_change",
    "baseline_reference",
    "baseline_code",
    "baseline_training_protocol",
    "baseline_eval_protocol",
    "evidence_import_gate",
    "compute_backend",
    "dataset_requirement_inventory",
    "dataset_runtime_plan",
    "path_mapping",
    "stability_seed_policy",
    "evaluation_command",
    "dataset",
    "data_split",
    "primary_metric",
    "secondary_metrics",
    "ablation_plan",
    "falsifiers",
    "stop_rules",
    "compute_budget",
    "expected_artifacts",
    "paperNexus_norms",
    "non_promotion_signals",
]

PLACEHOLDER_VALUES = {
    "baseline_protocol",
    "primary_metric",
    "target_dataset",
    "locked split required before launch",
    "locked evaluation command required before launch",
    "baseline code required before launch",
    "backend required before launch",
    "path mapping required before launch",
}
BACKENDS = {"local_gpu", "autodl_gpu"}
EVIDENCE_GATE_STATUSES = {"passed", "not_required", "async_wait", "blocked"}
TRACK_LAUNCH_STATUSES = {"ready", "blocked", "diagnostic_only", "parked"}
TRACK_EVIDENCE_READY = {"passed", "complete", "completed", "graph_closed", "source_backed", "not_required"}
DATASET_SCALE_CLASSES = {"small_multiclass", "medium_multiclass", "large_full_scale"}
DATASET_SCALE_RANK = {"small_multiclass": 0, "medium_multiclass": 1, "large_full_scale": 2}
LARGE_DATASET_EXCEPTION_REASONS = {"no_smaller_multiclass_proxy", "user_approved_start_large"}
NON_SMALLEST_DATASET_EXCEPTION_REASONS = {
    "user_approved_non_smallest",
    "dataset_invalid_for_selected_claim",
    "no_required_small_dataset_available",
}
DATASET_CLAIM_ROLES = {"method_validation", "ablation", "stress", "confirmation", "final_scale", "comparison_only"}
DATASET_AVAILABILITY_STATUSES = {"available", "missing", "unknown", "invalid_for_claim"}
DATASET_SELECTION_STATUSES = {"selected_first", "deferred", "rejected"}
MAX_STABILITY_RANDOM_SEEDS = 3
MECHANISM_TYPES = {"ALGO", "CODE", "PARAM"}
PROMOTION_STAGES = {"candidate", "ablation", "confirmation"}
VALID_METHOD_SOURCE_ROLES = {
    "near_neighbor",
    "far_neighbor",
    "cross_lane_recombination",
    "proposal_graph_transfer",
    "external_domain_transfer",
    "target_domain_absence_proven",
}
TARGET_DOMAIN_ONLY_ROLES = {"target_domain", "current_field", "target_domain_only"}
INNOVATION_BUNDLE_REQUIRED_KEYS = [
    "name",
    "role",
    "source_role",
    "source_evidence_refs",
    "closest_prior_delta",
    "paper_story_role",
    "validation_plan",
]
PAPER_STORYLINE_REQUIRED_KEYS = [
    "paper_thesis",
    "opening_tension",
    "hidden_cause",
    "method_as_resolution",
    "proof_ladder",
    "reviewer_risk_and_defense",
    "narrative_spine",
]
PROBLEM_PROTOCOL_ROLES = {"problem_definition", "protocol", "benchmark", "evaluation", "metric"}
METHOD_ROLES = {"method_mechanism", "algorithm", "model", "architecture", "training_mechanism"}
PROOF_INTEGRATION_ROLES = {"training_integration", "system_integration", "theory_analysis", "ablation", "validation", "analysis"}
CLONE_SOURCE_TYPES = {
    "git_clone",
    "github_clone",
    "official_repo_snapshot",
    "repo_snapshot",
    "local_git_worktree",
    "paper_official_repo",
}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def resolve_artifact(project: str, raw: str) -> Path:
    root = Path(project).expanduser().resolve()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return root / raw
    return root / ".autoreskill" / path


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["tracks", "rows", "track_plans"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if present(mapping.get(key)):
            return mapping[key]
    return None


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return (
        text in PLACEHOLDER_VALUES
        or "required before launch" in text
        or text.startswith("replace_with")
    )


def normalized_role(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def story_step_count(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if present(item) and not placeholder(item)])
    if not isinstance(value, str):
        return 0
    text = value.replace("\n", " ")
    for sep in ["。", "；", ";", "->", "=>", "|"]:
        text = text.replace(sep, ".")
    return len([part for part in text.split(".") if part.strip()])


def require_nested(mapping: Any, prefix: str, keys: list[str], missing: list[str]) -> None:
    if not isinstance(mapping, dict):
        missing.append(prefix)
        return
    for key in keys:
        value = mapping.get(key)
        if not present(value) or placeholder(value):
            missing.append(f"{prefix}.{key}")


def int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def validate_stability_seed_policy(packet: dict[str, Any], missing: list[str], warnings: list[str]) -> None:
    policy = packet.get("stability_seed_policy")
    prefix = "EXPERIMENT_REVIEW_PACKET.stability_seed_policy"
    require_nested(policy, prefix, ["max_random_seeds", "planned_seed_count", "claim_rule"], missing)
    if not isinstance(policy, dict):
        return

    max_seeds = int_value(policy.get("max_random_seeds"))
    planned = int_value(policy.get("planned_seed_count"))
    if max_seeds is None:
        missing.append(f"{prefix}.max_random_seeds must be numeric")
    elif max_seeds < 1 or max_seeds > MAX_STABILITY_RANDOM_SEEDS:
        missing.append(f"{prefix}.max_random_seeds must be between 1 and {MAX_STABILITY_RANDOM_SEEDS}")
    if planned is None:
        missing.append(f"{prefix}.planned_seed_count must be numeric")
    elif planned < 1 or planned > MAX_STABILITY_RANDOM_SEEDS:
        missing.append(f"{prefix}.planned_seed_count must be between 1 and {MAX_STABILITY_RANDOM_SEEDS}")
    if max_seeds is not None and planned is not None and planned > max_seeds:
        missing.append(f"{prefix}.planned_seed_count must not exceed max_random_seeds")

    for key in ["planned_random_seeds", "random_seeds", "stability_seeds"]:
        value = policy.get(key)
        if isinstance(value, list):
            if len(value) > MAX_STABILITY_RANDOM_SEEDS:
                missing.append(f"{prefix}.{key} must contain at most {MAX_STABILITY_RANDOM_SEEDS} seeds")
            if value and planned is not None and len(value) != planned:
                warnings.append(f"{prefix}.{key} length differs from planned_seed_count")

    for key in ["seed_count", "random_seed_count", "planned_seed_count", "num_seeds", "n_seeds"]:
        value = packet.get(key)
        count = int_value(value)
        if count is not None and count > MAX_STABILITY_RANDOM_SEEDS:
            missing.append(f"EXPERIMENT_REVIEW_PACKET.{key} must be <= {MAX_STABILITY_RANDOM_SEEDS}")


def validate_baseline_code(packet: dict[str, Any], missing: list[str]) -> None:
    baseline_code = packet.get("baseline_code")
    require_nested(
        baseline_code,
        "EXPERIMENT_REVIEW_PACKET.baseline_code",
        ["code_id", "source_type", "source_ref", "revision", "resolved_path", "train_entrypoint", "eval_entrypoint", "selection_rationale"],
        missing,
    )
    if not isinstance(baseline_code, dict):
        return
    if baseline_code.get("locked") is not True:
        missing.append("EXPERIMENT_REVIEW_PACKET.baseline_code.locked must be true")
    source_type = str(baseline_code.get("source_type") or "").lower()
    if source_type in {"", "search", "web_search", "unbounded_search", "unspecified"}:
        missing.append("EXPERIMENT_REVIEW_PACKET.baseline_code.source_type must identify a locked code source, not a search")
    if source_type and source_type not in CLONE_SOURCE_TYPES:
        missing.append("EXPERIMENT_REVIEW_PACKET.baseline_code.source_type must be a git clone/worktree or verified repository snapshot")


def validate_compute_backend(packet: dict[str, Any], missing: list[str]) -> None:
    backend = packet.get("compute_backend")
    require_nested(
        backend,
        "EXPERIMENT_REVIEW_PACKET.compute_backend",
        ["backend", "decision_rationale", "gpu_evidence", "paid_resource_policy"],
        missing,
    )
    if not isinstance(backend, dict):
        return
    backend_name = str(backend.get("backend") or "").strip()
    if backend_name not in BACKENDS:
        missing.append("EXPERIMENT_REVIEW_PACKET.compute_backend.backend must be local_gpu or autodl_gpu")
    if backend_name == "autodl_gpu" and not present(backend.get("autodl_plan_ref")):
        missing.append("EXPERIMENT_REVIEW_PACKET.compute_backend.autodl_plan_ref")


def validate_path_mapping(packet: dict[str, Any], missing: list[str]) -> None:
    mapping = packet.get("path_mapping")
    require_nested(
        mapping,
        "EXPERIMENT_REVIEW_PACKET.path_mapping",
        ["selected_backend", "logical_dataset_id", "code_root", "data_root", "output_dir", "checkpoint_dir", "persistent_output_dir"],
        missing,
    )
    if not isinstance(mapping, dict):
        return
    backend = str((packet.get("compute_backend") or {}).get("backend") or "").strip()
    selected = str(mapping.get("selected_backend") or "").strip()
    if selected not in BACKENDS:
        missing.append("EXPERIMENT_REVIEW_PACKET.path_mapping.selected_backend must be local_gpu or autodl_gpu")
    if backend in BACKENDS and selected and selected != backend:
        missing.append("EXPERIMENT_REVIEW_PACKET.path_mapping.selected_backend must match compute_backend.backend")
    env = mapping.get("env")
    require_nested(env, "EXPERIMENT_REVIEW_PACKET.path_mapping.env", ["DATA_ROOT", "OUTPUT_DIR", "CKPT_DIR"], missing)
    if selected == "autodl_gpu":
        for key in ["data_root", "output_dir", "checkpoint_dir"]:
            value = str(mapping.get(key) or "")
            if value and not value.startswith("/root/autodl-tmp/"):
                missing.append(f"EXPERIMENT_REVIEW_PACKET.path_mapping.{key} must use /root/autodl-tmp for AutoDL live paths")
        persistent = str(mapping.get("persistent_output_dir") or "")
        if persistent and not (
            persistent.startswith("/root/autodl-fs/")
            or persistent.startswith("/root/autodl-nas/")
            or persistent.startswith("s3://")
            or persistent.startswith("gs://")
        ):
            missing.append("EXPERIMENT_REVIEW_PACKET.path_mapping.persistent_output_dir must be durable for AutoDL")


def validate_dataset_runtime_plan(packet: dict[str, Any], missing: list[str], warnings: list[str]) -> None:
    plan = packet.get("dataset_runtime_plan")
    inventory = packet.get("dataset_requirement_inventory") if isinstance(packet.get("dataset_requirement_inventory"), dict) else {}
    require_nested(
        plan,
        "EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan",
        [
            "candidate_datasets",
            "feasibility_first_dataset_id",
            "first_run_scale_class",
            "largest_dataset_id",
            "largest_dataset_deferred",
            "escalation_criteria",
            "runtime_risk",
        ],
        missing,
    )
    if not isinstance(plan, dict):
        return

    candidates = plan.get("candidate_datasets")
    if not isinstance(candidates, list) or not candidates:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.candidate_datasets must be a non-empty list")
        return

    rows_by_id: dict[str, dict[str, Any]] = {}
    largest_rows: list[dict[str, Any]] = []
    for index, row in enumerate(candidates):
        prefix = f"EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.candidate_datasets[{index}]"
        if not isinstance(row, dict):
            missing.append(f"{prefix} must be an object")
            continue
        for key in [
            "dataset_id",
            "scale_class",
            "num_classes",
            "train_samples",
            "eval_samples",
            "epochs_or_steps",
            "estimated_minutes_per_epoch",
            "estimated_walltime_hours",
            "estimated_gpu_hours",
            "estimation_basis",
        ]:
            if not present(row.get(key)) or placeholder(row.get(key)):
                missing.append(f"{prefix}.{key}")
        dataset_id = str(row.get("dataset_id") or "").strip()
        if dataset_id:
            rows_by_id[dataset_id] = row
        scale_class = str(row.get("scale_class") or "").strip()
        if scale_class and scale_class not in DATASET_SCALE_CLASSES:
            missing.append(f"{prefix}.scale_class must be small_multiclass/medium_multiclass/large_full_scale")
        if scale_class == "large_full_scale":
            largest_rows.append(row)
        if present(row.get("num_classes")):
            try:
                if int(row["num_classes"]) < 2:
                    missing.append(f"{prefix}.num_classes must be >= 2 for multi-class feasibility")
            except (TypeError, ValueError):
                missing.append(f"{prefix}.num_classes must be numeric")
        for numeric_key in ["estimated_minutes_per_epoch", "estimated_walltime_hours", "estimated_gpu_hours"]:
            if present(row.get(numeric_key)):
                try:
                    if float(row[numeric_key]) <= 0:
                        missing.append(f"{prefix}.{numeric_key} must be > 0")
                except (TypeError, ValueError):
                    missing.append(f"{prefix}.{numeric_key} must be numeric")

    first_id = str(plan.get("feasibility_first_dataset_id") or "").strip()
    first_row = rows_by_id.get(first_id)
    if first_id and first_row is None:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.feasibility_first_dataset_id must match candidate_datasets[].dataset_id")
    first_scale = str(plan.get("first_run_scale_class") or "").strip()
    if first_scale and first_scale not in DATASET_SCALE_CLASSES:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.first_run_scale_class must be small_multiclass/medium_multiclass/large_full_scale")
    if first_row:
        row_scale = str(first_row.get("scale_class") or "").strip()
        if first_scale and row_scale and first_scale != row_scale:
            missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.first_run_scale_class must match the feasibility-first dataset scale_class")
        if row_scale == "large_full_scale":
            reason = str(plan.get("large_first_exception_reason") or "").strip()
            if reason not in LARGE_DATASET_EXCEPTION_REASONS:
                missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan cannot start feasibility on large_full_scale without large_first_exception_reason=no_smaller_multiclass_proxy or user_approved_start_large")

    largest_id = str(plan.get("largest_dataset_id") or "").strip()
    if largest_id and largest_id not in rows_by_id:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.largest_dataset_id must match candidate_datasets[].dataset_id")
    if largest_rows and plan.get("largest_dataset_deferred") is not True:
        reason = str(plan.get("large_first_exception_reason") or "").strip()
        if reason not in LARGE_DATASET_EXCEPTION_REASONS:
            missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.largest_dataset_deferred must be true unless a large-first exception is recorded")

    selected_dataset = str(packet.get("dataset") or "").strip()
    if selected_dataset and first_id and selected_dataset != first_id:
        warnings.append("EXPERIMENT_REVIEW_PACKET.dataset differs from dataset_runtime_plan.feasibility_first_dataset_id; ensure dataset is the intended first launch target")
    inventory_first = str(inventory.get("method_validation_dataset_id") or "").strip()
    if inventory_first and first_id and inventory_first != first_id:
        reason = str(inventory.get("non_smallest_first_exception_reason") or "").strip()
        if reason not in NON_SMALLEST_DATASET_EXCEPTION_REASONS:
            missing.append("EXPERIMENT_REVIEW_PACKET.dataset_runtime_plan.feasibility_first_dataset_id must match dataset_requirement_inventory.method_validation_dataset_id unless a valid non_smallest_first_exception_reason is recorded")


def validate_dataset_requirement_inventory(packet: dict[str, Any], missing: list[str], warnings: list[str]) -> None:
    inventory = packet.get("dataset_requirement_inventory")
    require_nested(
        inventory,
        "EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory",
        [
            "required_datasets",
            "selection_rule",
            "method_validation_dataset_id",
            "smallest_available_required_dataset_id",
        ],
        missing,
    )
    if not isinstance(inventory, dict):
        return

    required = inventory.get("required_datasets")
    if not isinstance(required, list) or not required:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory.required_datasets must be a non-empty list")
        return

    rows_by_id: dict[str, dict[str, Any]] = {}
    available_required: list[tuple[tuple[float, float, float], dict[str, Any]]] = []
    for index, row in enumerate(required):
        prefix = f"EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory.required_datasets[{index}]"
        if not isinstance(row, dict):
            missing.append(f"{prefix} must be an object")
            continue
        for key in [
            "dataset_id",
            "dataset_name",
            "claim_role",
            "reason_required",
            "baseline_supported",
            "availability",
            "scale_class",
            "num_classes",
            "train_samples",
            "eval_samples",
            "native_protocol_ref",
            "native_epochs_or_steps",
            "native_warmup_or_schedule",
            "data_root_or_probe",
            "selection_status",
        ]:
            if not present(row.get(key)) or placeholder(row.get(key)):
                missing.append(f"{prefix}.{key}")
        dataset_id = str(row.get("dataset_id") or "").strip()
        if dataset_id:
            rows_by_id[dataset_id] = row
        role = str(row.get("claim_role") or "").strip()
        if role and role not in DATASET_CLAIM_ROLES:
            missing.append(f"{prefix}.claim_role must be one of {sorted(DATASET_CLAIM_ROLES)}")
        availability = str(row.get("availability") or "").strip()
        if availability and availability not in DATASET_AVAILABILITY_STATUSES:
            missing.append(f"{prefix}.availability must be one of {sorted(DATASET_AVAILABILITY_STATUSES)}")
        if availability == "available" and not isinstance(row.get("baseline_supported"), bool):
            missing.append(f"{prefix}.baseline_supported must be boolean when availability=available")
        selection_status = str(row.get("selection_status") or "").strip()
        if selection_status and selection_status not in DATASET_SELECTION_STATUSES:
            missing.append(f"{prefix}.selection_status must be one of {sorted(DATASET_SELECTION_STATUSES)}")
        if selection_status == "rejected" and not present(row.get("rejection_reason")):
            missing.append(f"{prefix}.rejection_reason is required when selection_status=rejected")
        scale = str(row.get("scale_class") or "").strip()
        if scale and scale not in DATASET_SCALE_CLASSES:
            missing.append(f"{prefix}.scale_class must be small_multiclass/medium_multiclass/large_full_scale")

        if (
            dataset_id
            and role in {"method_validation", "ablation", "stress"}
            and row.get("baseline_supported") is True
            and availability == "available"
            and selection_status != "rejected"
        ):
            try:
                train_samples = float(row.get("train_samples"))
            except (TypeError, ValueError):
                train_samples = float("inf")
            try:
                gpu_hours = float(row.get("estimated_gpu_hours", float("inf")))
            except (TypeError, ValueError):
                gpu_hours = float("inf")
            rank = (float(DATASET_SCALE_RANK.get(scale, 99)), train_samples, gpu_hours)
            available_required.append((rank, row))

    if not available_required:
        reason = str(inventory.get("non_smallest_first_exception_reason") or "").strip()
        if reason != "no_required_small_dataset_available":
            missing.append("EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory must include at least one available baseline-supported required dataset or record non_smallest_first_exception_reason=no_required_small_dataset_available")
        return

    available_required.sort(key=lambda item: item[0])
    smallest_id = str(available_required[0][1].get("dataset_id") or "").strip()
    recorded_smallest = str(inventory.get("smallest_available_required_dataset_id") or "").strip()
    selected_first = str(inventory.get("method_validation_dataset_id") or "").strip()
    if recorded_smallest and recorded_smallest != smallest_id:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory.smallest_available_required_dataset_id must be the smallest available baseline-supported required dataset")
    if selected_first and selected_first not in rows_by_id:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory.method_validation_dataset_id must match required_datasets[].dataset_id")
    if selected_first and selected_first != smallest_id:
        reason = str(inventory.get("non_smallest_first_exception_reason") or "").strip()
        if reason not in NON_SMALLEST_DATASET_EXCEPTION_REASONS:
            missing.append("EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory.method_validation_dataset_id must choose the smallest available baseline-supported required dataset unless a valid non_smallest_first_exception_reason is recorded")
    selected_rows = [
        str(row.get("dataset_id") or "").strip()
        for row in required
        if isinstance(row, dict) and row.get("selection_status") == "selected_first"
    ]
    if selected_first and selected_rows != [selected_first]:
        missing.append("EXPERIMENT_REVIEW_PACKET.dataset_requirement_inventory must have exactly one selected_first row matching method_validation_dataset_id")


def validate_innovation_contract(packet: dict[str, Any], missing: list[str]) -> None:
    contract = packet.get("innovation_search_contract")
    require_nested(
        contract,
        "EXPERIMENT_REVIEW_PACKET.innovation_search_contract",
        [
            "selected_idea_id",
            "track_id",
            "innovation_mechanism",
            "mechanism_type",
            "primary_method_source_role",
            "neighbor_transfer_mechanism",
            "target_domain_anchor",
            "target_domain_method_overlap_risk",
            "one_variable_change",
            "expected_effect",
            "falsifier",
            "promotion_stage",
        ],
        missing,
    )
    if not isinstance(contract, dict):
        return
    if str(contract.get("mechanism_type") or "").strip().upper() not in MECHANISM_TYPES:
        missing.append("EXPERIMENT_REVIEW_PACKET.innovation_search_contract.mechanism_type must be ALGO, CODE, or PARAM")
    if str(contract.get("promotion_stage") or "").strip().lower() not in PROMOTION_STAGES:
        missing.append("EXPERIMENT_REVIEW_PACKET.innovation_search_contract.promotion_stage must be candidate, ablation, or confirmation")
    source_role = normalized_role(contract.get("primary_method_source_role") or packet.get("primary_method_source_role"))
    if source_role in TARGET_DOMAIN_ONLY_ROLES:
        if not present(contract.get("current_field_absence_evidence") or packet.get("current_field_absence_evidence")):
            missing.append("EXPERIMENT_REVIEW_PACKET.innovation_search_contract.current_field_absence_evidence required for target-domain-only main method")
    elif source_role and source_role not in VALID_METHOD_SOURCE_ROLES:
        missing.append("EXPERIMENT_REVIEW_PACKET.innovation_search_contract.primary_method_source_role must be near/far-neighbor transfer, cross-lane recombination, proposal-graph transfer, external-domain transfer, or target_domain_absence_proven")
    if contract.get("ablation_required") is not True:
        missing.append("EXPERIMENT_REVIEW_PACKET.innovation_search_contract.ablation_required must be true")
    if contract.get("confirmation_required") is not True:
        missing.append("EXPERIMENT_REVIEW_PACKET.innovation_search_contract.confirmation_required must be true")

    gate = packet.get("promotion_gate")
    require_nested(gate, "EXPERIMENT_REVIEW_PACKET.promotion_gate", ["stage", "promotion_requires", "claim_policy"], missing)
    if isinstance(gate, dict) and str(gate.get("stage") or "").strip().lower() not in PROMOTION_STAGES:
        missing.append("EXPERIMENT_REVIEW_PACKET.promotion_gate.stage must be candidate, ablation, or confirmation")


def validate_paper_bundle(packet: dict[str, Any], missing: list[str]) -> None:
    contract = packet.get("innovation_search_contract") if isinstance(packet.get("innovation_search_contract"), dict) else {}
    bundle = first_present(packet, ["paper_innovation_bundle", "innovation_bundle", "three_innovation_bundle"])
    if not present(bundle):
        bundle = contract.get("paper_innovation_bundle") or contract.get("innovation_bundle")
    points = as_list(bundle)
    if len(points) < 3:
        missing.append("EXPERIMENT_REVIEW_PACKET.paper_innovation_bundle must contain at least 3 paper-level innovation points")
        return

    roles: set[str] = set()
    transfer_source_count = 0
    for index, point in enumerate(points):
        prefix = f"EXPERIMENT_REVIEW_PACKET.paper_innovation_bundle[{index}]"
        if not isinstance(point, dict):
            missing.append(f"{prefix} must be an object")
            continue
        for key in INNOVATION_BUNDLE_REQUIRED_KEYS:
            value = point.get(key)
            if not present(value) or placeholder(value):
                missing.append(f"{prefix}.{key}")
        role = normalized_role(point.get("role"))
        source_role = normalized_role(point.get("source_role"))
        if role:
            roles.add(role)
        if source_role in VALID_METHOD_SOURCE_ROLES:
            transfer_source_count += 1
        elif source_role in TARGET_DOMAIN_ONLY_ROLES and not present(point.get("current_field_absence_evidence")):
            missing.append(f"{prefix}.current_field_absence_evidence required for target-domain-only innovation point")

    if not roles & PROBLEM_PROTOCOL_ROLES:
        missing.append("EXPERIMENT_REVIEW_PACKET.paper_innovation_bundle needs a problem/protocol/evaluation innovation point")
    if not roles & METHOD_ROLES:
        missing.append("EXPERIMENT_REVIEW_PACKET.paper_innovation_bundle needs a method/mechanism innovation point")
    if not roles & PROOF_INTEGRATION_ROLES:
        missing.append("EXPERIMENT_REVIEW_PACKET.paper_innovation_bundle needs a training/integration/analysis/validation innovation point")
    if transfer_source_count < 1:
        missing.append("EXPERIMENT_REVIEW_PACKET.paper_innovation_bundle needs at least one near/far/cross-lane or external transfer-backed point")

    storyline = first_present(packet, ["paper_storyline", "storyline_contract", "storyline"])
    if not present(storyline):
        storyline = contract.get("paper_storyline") or contract.get("storyline")
    if not isinstance(storyline, dict):
        missing.append("EXPERIMENT_REVIEW_PACKET.paper_storyline")
        return
    for key in PAPER_STORYLINE_REQUIRED_KEYS:
        value = storyline.get(key)
        if not present(value) or placeholder(value):
            missing.append(f"EXPERIMENT_REVIEW_PACKET.paper_storyline.{key}")
    if story_step_count(storyline.get("narrative_spine")) < 5:
        missing.append("EXPERIMENT_REVIEW_PACKET.paper_storyline.narrative_spine must contain 5-7 sequential story steps")


def validate_evidence_import_gate(packet: dict[str, Any], missing: list[str]) -> None:
    gate = packet.get("evidence_import_gate")
    require_nested(
        gate,
        "EXPERIMENT_REVIEW_PACKET.evidence_import_gate",
        ["status", "reason", "launch_blocked"],
        missing,
    )
    if not isinstance(gate, dict):
        return

    status = str(gate.get("status") or "").strip().lower()
    if status not in EVIDENCE_GATE_STATUSES:
        missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate.status must be passed, not_required, async_wait, or blocked")

    if status in {"passed", "not_required"}:
        if gate.get("launch_blocked") is True:
            missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate.launch_blocked must be false for passed/not_required")
        if not present(gate.get("material_refs")) and not present(gate.get("evidence_ids")):
            missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate.material_refs or evidence_ids")
        if status == "passed" and gate.get("mcp_attempted") is not True:
            missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate.mcp_attempted must be true when status is passed")

    if status in {"async_wait", "blocked"}:
        missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate must pass before launch")
        if gate.get("launch_blocked") is not True:
            missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate.launch_blocked must be true for async_wait/blocked")
        if not present(gate.get("claim_limits")):
            missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate.claim_limits")
        if not present(gate.get("attempts")):
            missing.append("EXPERIMENT_REVIEW_PACKET.evidence_import_gate.attempts")


def degraded_gate_approved(gate: Any) -> bool:
    if not isinstance(gate, dict):
        return False
    if str(gate.get("status") or "").strip().lower() != "degraded_requires_user_approval":
        return False
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return False
    return (
        present(approval.get("approved_by"))
        and present(approval.get("approved_at"))
        and present(approval.get("reason"))
        and present(gate.get("claim_limits") or approval.get("claim_limits"))
    )


def validate_pre_idea_refs(packet: dict[str, Any], project: str, missing: list[str]) -> None:
    for key in ["pre_idea_evidence_gate_path", "innovation_slot_map_path"]:
        value = packet.get(key)
        if not present(value):
            missing.append(f"EXPERIMENT_REVIEW_PACKET.{key}")
            continue
        path = resolve_artifact(project, str(value))
        if not path.exists():
            missing.append(f"EXPERIMENT_REVIEW_PACKET.{key} not found: {value}")
        elif key == "pre_idea_evidence_gate_path":
            gate = read_json(path)
            if not isinstance(gate, dict) or (
                str(gate.get("status") or "").strip().lower() != "passed"
                and not degraded_gate_approved(gate)
            ):
                missing.append("EXPERIMENT_REVIEW_PACKET.pre_idea_evidence_gate_path status passed")
    if not present(packet.get("consumed_innovation_slot_ids")):
        missing.append("EXPERIMENT_REVIEW_PACKET.consumed_innovation_slot_ids")


def validate_track_plan_matrix(project: str, missing: list[str], warnings: list[str]) -> None:
    base = ar(project)
    seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json")
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json")
    if not isinstance(seeds, dict):
        return
    seed_rows = rows_from_payload(seeds)
    if not isinstance(matrix, dict):
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json for IDEA_TRACK_SEEDS")
        return
    rows = rows_from_payload(matrix)
    if not rows:
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json tracks")
        return
    rows_by_track = {str(row.get("track_id")): row for row in rows if present(row.get("track_id"))}
    for seed in seed_rows:
        track_id = str(seed.get("track_id") or "")
        if track_id and track_id not in rows_by_track:
            missing.append(f"TRACK_PLAN_MATRIX missing seed track {track_id}")
    for index, row in enumerate(rows):
        prefix = f"TRACK_PLAN_MATRIX[{index}]"
        for key in [
            "track_id",
            "idea_id",
            "baseline_code",
            "dataset",
            "dataset_runtime_plan_ref",
            "split",
            "primary_metric",
            "metric_direction",
            "eval_command",
            "compute_budget",
            "evidence_closure_status",
            "launch_status",
            "promotion_gate",
        ]:
            if not present(row.get(key)) or placeholder(row.get(key)):
                missing.append(f"{prefix}.{key}")
        status = str(row.get("launch_status") or "").strip().lower()
        if status and status not in TRACK_LAUNCH_STATUSES:
            missing.append(f"{prefix}.launch_status must be ready/blocked/diagnostic_only/parked")
        if status == "ready":
            closure = str(row.get("evidence_closure_status") or "").strip().lower()
            if closure not in TRACK_EVIDENCE_READY:
                missing.append(f"{prefix}.evidence_closure_status must be ready before launch")
            if present(row.get("blocked_reason")):
                missing.append(f"{prefix}.blocked_reason must be empty for ready tracks")
        if status in {"blocked", "diagnostic_only", "parked"} and not present(row.get("blocked_reason")):
            warnings.append(f"{prefix}.blocked_reason recommended for non-ready tracks")


def lint(packet: dict[str, Any] | None, project: str) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    if not packet:
        return {"complete": False, "status": "incomplete", "missing": ["planner/EXPERIMENT_REVIEW_PACKET.json"], "warnings": []}

    for key in REQUIRED:
        if not present(packet.get(key)):
            missing.append(f"EXPERIMENT_REVIEW_PACKET.{key}")

    for key in [
        "baseline_reference",
        "baseline_training_protocol",
        "baseline_eval_protocol",
        "evaluation_command",
        "dataset",
        "data_split",
        "primary_metric",
    ]:
        if placeholder(packet.get(key)):
            missing.append(f"EXPERIMENT_REVIEW_PACKET.{key} is still a placeholder")

    if packet.get("one_variable_change") is not True:
        missing.append("EXPERIMENT_REVIEW_PACKET.one_variable_change must be true")

    validate_baseline_code(packet, missing)
    validate_innovation_contract(packet, missing)
    validate_paper_bundle(packet, missing)
    validate_evidence_import_gate(packet, missing)
    validate_pre_idea_refs(packet, project, missing)
    validate_compute_backend(packet, missing)
    validate_dataset_requirement_inventory(packet, missing, warnings)
    validate_dataset_runtime_plan(packet, missing, warnings)
    validate_path_mapping(packet, missing)
    validate_stability_seed_policy(packet, missing, warnings)
    validate_hpo_search_policy(packet, "EXPERIMENT_REVIEW_PACKET", missing, warnings)
    validate_track_plan_matrix(project, missing, warnings)

    idea_pool_path = packet.get("idea_pool_path") or packet.get("candidate_library_path")
    if present(idea_pool_path):
        if not resolve_artifact(project, str(idea_pool_path)).exists():
            missing.append(f"EXPERIMENT_REVIEW_PACKET.idea_pool_path not found: {idea_pool_path}")

    if not present(packet.get("metric_direction")):
        warnings.append("missing metric_direction; run reconciliation will assume higher-is-better")

    if not present(packet.get("protected_paths")):
        warnings.append("missing protected_paths; hash eval/test/metric files when available")

    if packet.get("candidate_library_path") or packet.get("selected_candidate_id") or packet.get("candidate_generation_scope"):
        warnings.append("legacy candidate_* fields found; use idea_pool_path, selected_idea_id, and idea_generation_scope")

    cost_norms = packet.get("experiment_cost_norms") or packet.get("cost_evidence_gap")
    if not present(cost_norms):
        warnings.append("missing experiment_cost_norms or explicit cost_evidence_gap")

    launch = str(packet.get("launch_status") or packet.get("status") or "").lower()
    if launch and launch not in {"reviewed", "ready", "approved", "pass", "passed"}:
        missing.append("EXPERIMENT_REVIEW_PACKET.status must be reviewed/ready/approved before launch")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--packet")
    args = parser.parse_args()
    path = Path(args.packet).expanduser() if args.packet else ar(args.project) / "planner/EXPERIMENT_REVIEW_PACKET.json"
    out = lint(read_json(path), args.project)
    out["path"] = str(path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
