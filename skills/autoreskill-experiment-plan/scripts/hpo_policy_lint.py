"""Validation helpers for resource-constrained DEHB HPO policy."""

from __future__ import annotations

import re
from typing import Any


HPO_ENABLED_METHODS = {"dehb_resource_constrained", "dehb_lite", "dehb"}
HPO_NOT_APPLICABLE_METHODS = {"not_applicable", "none", "disabled", "manual_fixed"}
HPO_FORBIDDEN_METHODS = {
    "grid",
    "grid_search",
    "linear_grid",
    "manual_linear",
    "line_search",
    "coordinate_descent",
    "one_factor_at_a_time",
    "seed_sweep",
}
HPO_RESOURCE_AXES = {"epochs", "epoch", "steps", "training_steps", "data_fraction", "subset_fraction"}
HPO_BUDGET_TIERS = {"micro", "small", "standard"}
HPO_DIMENSION_TYPES = {"categorical", "ordinal", "integer", "float", "log_float", "boolean"}
HPO_TUNING_TARGETS = {"baseline_calibration", "mechanism_parameterization"}
MAX_SEARCH_DIMENSIONS = 6
MAX_SCOUT_TRIALS_WITHOUT_APPROVAL = 48
MAX_FULL_TRIALS_WITHOUT_APPROVAL = 3
MAX_CONFIRMATION_SEEDS = 3
SWEEP_KEYS = {
    "sweep",
    "target_sweep",
    "parameter_sweep",
    "hparam_sweep",
    "hyperparameter_sweep",
    "hyperparameter_search",
    "parameter_search",
    "search_space",
}


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value)
    return None


def float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def require_nested(mapping: Any, prefix: str, keys: list[str], missing: list[str]) -> None:
    if not isinstance(mapping, dict):
        missing.append(prefix)
        return
    for key in keys:
        if not present(mapping.get(key)):
            missing.append(f"{prefix}.{key}")


def mechanism_type(packet: dict[str, Any]) -> str:
    contract = as_dict(packet.get("innovation_search_contract"))
    return str(contract.get("mechanism_type") or packet.get("mechanism_type") or "").strip().upper()


def hpo_policy(packet: dict[str, Any]) -> dict[str, Any]:
    contract = as_dict(packet.get("innovation_search_contract"))
    return as_dict(packet.get("hpo_search_policy")) or as_dict(contract.get("hpo_search_policy"))


def declares_target_sweep(packet: dict[str, Any]) -> bool:
    contract = as_dict(packet.get("innovation_search_contract"))
    for container in [packet, contract]:
        for key in SWEEP_KEYS:
            if present(container.get(key)):
                return True
    return False


def _validate_trial_budget(policy: dict[str, Any], prefix: str, missing: list[str], warnings: list[str]) -> None:
    budget = policy.get("trial_budget")
    require_nested(budget, f"{prefix}.trial_budget", ["max_scout_trials", "max_full_budget_trials"], missing)
    if not isinstance(budget, dict):
        return

    scout = int_value(budget.get("max_scout_trials"))
    full = int_value(budget.get("max_full_budget_trials"))
    approved = budget.get("user_approved_higher_budget") is True
    if scout is None or scout < 1:
        missing.append(f"{prefix}.trial_budget.max_scout_trials must be a positive integer")
    elif scout > MAX_SCOUT_TRIALS_WITHOUT_APPROVAL and not approved:
        missing.append(f"{prefix}.trial_budget.max_scout_trials > {MAX_SCOUT_TRIALS_WITHOUT_APPROVAL} requires user_approved_higher_budget=true")
    elif scout > 24 and not approved:
        warnings.append(f"{prefix}.trial_budget.max_scout_trials exceeds the small-budget default; verify GPU cost")
    if full is None or full < 1:
        missing.append(f"{prefix}.trial_budget.max_full_budget_trials must be a positive integer")
    elif full > MAX_FULL_TRIALS_WITHOUT_APPROVAL and not approved:
        missing.append(f"{prefix}.trial_budget.max_full_budget_trials > {MAX_FULL_TRIALS_WITHOUT_APPROVAL} requires user_approved_higher_budget=true")
    elif full > 2 and not approved:
        warnings.append(f"{prefix}.trial_budget.max_full_budget_trials exceeds the resource-limited default")


def _validate_rungs(policy: dict[str, Any], prefix: str, missing: list[str], warnings: list[str]) -> None:
    rungs = policy.get("rungs")
    if not isinstance(rungs, list) or len(rungs) < 2:
        missing.append(f"{prefix}.rungs must contain at least two Hyperband rungs")
        return
    if len(rungs) > 3:
        warnings.append(f"{prefix}.rungs has more than three rungs; resource-limited default is 2-3")

    fractions: list[float] = []
    for index, rung in enumerate(rungs):
        row = as_dict(rung)
        row_prefix = f"{prefix}.rungs[{index}]"
        if not row:
            missing.append(row_prefix)
            continue
        frac = float_value(row.get("resource_fraction") or row.get("fraction"))
        if frac is None:
            missing.append(f"{row_prefix}.resource_fraction")
        elif frac <= 0 or frac > 1:
            missing.append(f"{row_prefix}.resource_fraction must be in (0, 1]")
        else:
            fractions.append(frac)
        if not present(row.get("promotion")):
            warnings.append(f"{row_prefix}.promotion recommended")
    if fractions and fractions != sorted(fractions):
        missing.append(f"{prefix}.rungs must be sorted by increasing resource_fraction")
    if fractions and max(fractions) < 1.0:
        missing.append(f"{prefix}.rungs must include a full-resource rung with resource_fraction=1.0")
    if fractions and min(fractions) < 0.05:
        warnings.append(f"{prefix}.rungs minimum resource_fraction < 0.05 may be too noisy for promotion decisions")


def _validate_seed_policy(policy: dict[str, Any], prefix: str, missing: list[str]) -> None:
    seed_policy = policy.get("seed_policy")
    require_nested(
        seed_policy,
        f"{prefix}.seed_policy",
        ["seed_is_search_axis", "scout_random_seed_count", "matched_seed_protocol"],
        missing,
    )
    if not isinstance(seed_policy, dict):
        return
    if seed_policy.get("seed_is_search_axis") is not False:
        missing.append(f"{prefix}.seed_policy.seed_is_search_axis must be false")
    if seed_policy.get("matched_seed_protocol") is not True:
        missing.append(f"{prefix}.seed_policy.matched_seed_protocol must be true")
    scout_count = int_value(seed_policy.get("scout_random_seed_count"))
    if scout_count != 1:
        missing.append(f"{prefix}.seed_policy.scout_random_seed_count must be 1")
    # The confirmation-only key is a read alias; the enforced limit covers scout plus confirmation.
    max_total = int_value(
        seed_policy.get("max_total_random_seeds", seed_policy.get("max_confirmation_random_seeds"))
    )
    if max_total is None or max_total < 1 or max_total > MAX_CONFIRMATION_SEEDS:
        missing.append(f"{prefix}.seed_policy.max_total_random_seeds must be between 1 and {MAX_CONFIRMATION_SEEDS}")


def _validate_search_space(policy: dict[str, Any], prefix: str, missing: list[str], warnings: list[str]) -> None:
    audit = policy.get("search_space_audit")
    require_nested(audit, f"{prefix}.search_space_audit", ["protected_axes", "dimensions"], missing)
    if not isinstance(audit, dict):
        return

    max_dims = int_value(audit.get("max_search_dimensions"))
    if max_dims is None:
        max_dims = MAX_SEARCH_DIMENSIONS
        warnings.append(f"{prefix}.search_space_audit.max_search_dimensions missing; assuming {MAX_SEARCH_DIMENSIONS}")
    elif max_dims < 1 or max_dims > MAX_SEARCH_DIMENSIONS:
        missing.append(f"{prefix}.search_space_audit.max_search_dimensions must be 1..{MAX_SEARCH_DIMENSIONS}")

    protected = [normalized(axis) for axis in audit.get("protected_axes", [])] if isinstance(audit.get("protected_axes"), list) else []
    if not any(axis in protected for axis in ["seed", "random_seed"]):
        missing.append(f"{prefix}.search_space_audit.protected_axes must include random_seed")
    if not any(axis in protected for axis in ["dataset", "split", "data_split"]):
        missing.append(f"{prefix}.search_space_audit.protected_axes must include dataset or split")
    if not any(axis in protected for axis in ["baseline", "backbone", "checkpoint", "metric"]):
        missing.append(f"{prefix}.search_space_audit.protected_axes must include baseline/backbone/checkpoint/metric")

    dimensions = audit.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        missing.append(f"{prefix}.search_space_audit.dimensions must be a non-empty list")
        return
    if max_dims is not None and len(dimensions) > max_dims:
        missing.append(f"{prefix}.search_space_audit.dimensions exceeds max_search_dimensions")
    for index, dimension in enumerate(dimensions):
        row = as_dict(dimension)
        row_prefix = f"{prefix}.search_space_audit.dimensions[{index}]"
        require_nested(row, row_prefix, ["name", "type", "bounds_or_choices", "default_or_prior", "rationale"], missing)
        dim_type = normalized(row.get("type"))
        if dim_type and dim_type not in HPO_DIMENSION_TYPES:
            missing.append(f"{row_prefix}.type must be one of {sorted(HPO_DIMENSION_TYPES)}")
        name = normalized(row.get("name"))
        if name in {"seed", "random_seed", "dataset", "split", "data_split", "baseline", "metric", "eval_command"}:
            missing.append(f"{row_prefix}.name cannot be a protected axis")
        if dim_type == "float" and any(token in name for token in ["lr", "lambda", "weight", "temperature", "tau", "threshold", "reg"]):
            warnings.append(f"{row_prefix}.type should usually be log_float for multiplicative scales")


def _validate_promotion(policy: dict[str, Any], prefix: str, missing: list[str], warnings: list[str]) -> None:
    promotion = policy.get("promotion_rule")
    require_nested(promotion, f"{prefix}.promotion_rule", ["promote_top_k", "full_resource_before_candidate"], missing)
    if not isinstance(promotion, dict):
        return
    top_k = int_value(promotion.get("promote_top_k"))
    max_top_k = int_value(promotion.get("max_promote_top_k")) or 2
    if top_k is None or top_k < 1:
        missing.append(f"{prefix}.promotion_rule.promote_top_k must be a positive integer")
    elif top_k > 2:
        missing.append(f"{prefix}.promotion_rule.promote_top_k must be <= 2 by default")
    if max_top_k > 2:
        warnings.append(f"{prefix}.promotion_rule.max_promote_top_k > 2 requires explicit cost justification")
    if promotion.get("full_resource_before_candidate") is not True:
        missing.append(f"{prefix}.promotion_rule.full_resource_before_candidate must be true")


def _validate_execution(policy: dict[str, Any], prefix: str, missing: list[str]) -> None:
    execution = policy.get("execution_policy")
    require_nested(
        execution,
        f"{prefix}.execution_policy",
        [
            "mode",
            "max_concurrent_scouts",
            "max_concurrent_full_budget_trials",
            "promotions_require_comparable_rung_metrics",
        ],
        missing,
    )
    if not isinstance(execution, dict):
        return
    if normalized(execution.get("mode")) != "elastic_async":
        missing.append(f"{prefix}.execution_policy.mode must be elastic_async")
    max_scouts = execution.get("max_concurrent_scouts")
    if normalized(max_scouts) != "auto" and (int_value(max_scouts) is None or int_value(max_scouts) < 1):
        missing.append(f"{prefix}.execution_policy.max_concurrent_scouts must be auto or a positive integer")
    scout_budget = int_value(as_dict(policy.get("trial_budget")).get("max_scout_trials"))
    if int_value(max_scouts) is not None and scout_budget is not None and int_value(max_scouts) > scout_budget:
        missing.append(f"{prefix}.execution_policy.max_concurrent_scouts cannot exceed max_scout_trials")
    max_full = int_value(execution.get("max_concurrent_full_budget_trials"))
    if max_full is None or max_full < 1 or max_full > MAX_FULL_TRIALS_WITHOUT_APPROVAL:
        missing.append(
            f"{prefix}.execution_policy.max_concurrent_full_budget_trials must be between 1 and {MAX_FULL_TRIALS_WITHOUT_APPROVAL}"
        )
    full_budget = int_value(as_dict(policy.get("trial_budget")).get("max_full_budget_trials"))
    if max_full is not None and full_budget is not None and max_full > full_budget:
        missing.append(f"{prefix}.execution_policy.max_concurrent_full_budget_trials cannot exceed max_full_budget_trials")
    if execution.get("promotions_require_comparable_rung_metrics") is not True:
        missing.append(f"{prefix}.execution_policy.promotions_require_comparable_rung_metrics must be true")


def validate_hpo_search_policy(packet: dict[str, Any], packet_label: str, missing: list[str], warnings: list[str]) -> None:
    mtype = mechanism_type(packet)
    requires_hpo = mtype == "PARAM" or declares_target_sweep(packet)
    policy = hpo_policy(packet)
    prefix = f"{packet_label}.hpo_search_policy"

    if requires_hpo and not policy:
        missing.append(f"{prefix} required for PARAM mechanisms or target sweeps")
        return
    if not policy:
        return

    method = normalized(policy.get("search_method") or policy.get("method"))
    if not method:
        missing.append(f"{prefix}.search_method")
        return
    if method in HPO_FORBIDDEN_METHODS:
        missing.append(f"{prefix}.search_method={method} is forbidden; use dehb_resource_constrained for PARAM search")
    if method in HPO_NOT_APPLICABLE_METHODS:
        if requires_hpo:
            missing.append(f"{prefix}.search_method cannot be {method} for PARAM mechanisms or target sweeps")
        return
    if method not in HPO_ENABLED_METHODS:
        missing.append(f"{prefix}.search_method must be dehb_resource_constrained/dehb_lite/dehb or not_applicable")
        return
    if mtype == "PARAM" and method != "dehb_resource_constrained":
        warnings.append(f"{prefix}.search_method should be dehb_resource_constrained for resource-limited PARAM search")

    require_nested(
        policy,
        prefix,
        [
            "search_role",
            "tuning_target",
            "budget_tier",
            "resource_axis",
            "trial_budget",
            "rungs",
            "search_space_audit",
            "seed_policy",
            "promotion_rule",
            "execution_policy",
            "kill_condition",
            "claim_boundary",
        ],
        missing,
    )
    role = normalized(policy.get("search_role"))
    if mtype == "PARAM" and role != "param":
        missing.append(f"{prefix}.search_role must be PARAM for PARAM mechanisms")
    tuning_target = normalized(policy.get("tuning_target"))
    if tuning_target not in HPO_TUNING_TARGETS:
        missing.append(f"{prefix}.tuning_target must be baseline_calibration or mechanism_parameterization")
    if tuning_target == "baseline_calibration":
        calibration = policy.get("baseline_calibration_policy")
        require_nested(
            calibration,
            f"{prefix}.baseline_calibration_policy",
            [
                "validation_only_search",
                "freeze_before_claim_promotion",
                "equal_or_shared_tuning_budget",
                "provisional_overlap_evidence_tier",
            ],
            missing,
        )
        if isinstance(calibration, dict):
            for key in ("validation_only_search", "freeze_before_claim_promotion", "equal_or_shared_tuning_budget"):
                if calibration.get(key) is not True:
                    missing.append(f"{prefix}.baseline_calibration_policy.{key} must be true")
            if normalized(calibration.get("provisional_overlap_evidence_tier")) != "pilot_only":
                missing.append(
                    f"{prefix}.baseline_calibration_policy.provisional_overlap_evidence_tier must be pilot_only"
                )
        if policy.get("validation_stage") == 5:
            missing.append(f"{prefix}.baseline_calibration must not use innovation validation_stage=5")
        if present(policy.get("evidence_tier")) and normalized(policy.get("evidence_tier")) != "pilot_only":
            missing.append(f"{prefix}.baseline_calibration evidence_tier must be pilot_only")
        if not present(policy.get("work_kind")):
            warnings.append(f"{prefix}.work_kind=baseline_calibration recommended for scheduler separation")
        elif normalized(policy.get("work_kind")) != "baseline_calibration":
            missing.append(f"{prefix}.work_kind must be baseline_calibration")
    elif tuning_target == "mechanism_parameterization":
        activation = normalized(policy.get("activation_status") or "pending_support")
        if activation not in {"pending_support", "eligible"}:
            missing.append(f"{prefix}.activation_status must be pending_support or eligible")
        if activation == "eligible":
            for key in [
                "sensitivity_question",
                "eligible_belief_states",
                "current_belief_state",
                "baseline_freeze_or_calibration_ref",
                "remaining_gpu_hours",
            ]:
                if not present(policy.get(key)):
                    missing.append(f"{prefix}.{key} required when activation_status=eligible")
            eligible_states = {
                normalized(value)
                for value in policy.get("eligible_belief_states", [])
                if present(value)
            } if isinstance(policy.get("eligible_belief_states"), list) else set()
            current_state = normalized(policy.get("current_belief_state"))
            if current_state and current_state not in eligible_states:
                missing.append(f"{prefix}.current_belief_state must be listed in eligible_belief_states")
            if current_state in {"terminal_negative", "refuted", "retired", "killed"}:
                missing.append(f"{prefix}.terminal-negative mechanism cannot activate HPO")
            remaining = float_value(policy.get("remaining_gpu_hours"))
            if remaining is None or remaining <= 0:
                missing.append(f"{prefix}.remaining_gpu_hours must be positive when activation_status=eligible")
            total_budget = float_value(as_dict(policy.get("trial_budget")).get("max_total_gpu_hours"))
            if total_budget is None or total_budget <= 0:
                missing.append(
                    f"{prefix}.trial_budget.max_total_gpu_hours must be positive when activation_status=eligible"
                )
            elif remaining is not None and remaining > total_budget:
                missing.append(f"{prefix}.remaining_gpu_hours cannot exceed trial_budget.max_total_gpu_hours")
            dimensions = as_dict(policy.get("search_space_audit")).get("dimensions")
            if not isinstance(dimensions, list) or not 3 <= len(dimensions) <= MAX_SEARCH_DIMENSIONS:
                missing.append(f"{prefix}.eligible Stage-5 search must declare 3..{MAX_SEARCH_DIMENSIONS} dimensions")
            dataset_group = as_dict(policy.get("dataset_group_hpo"))
            require_nested(
                dataset_group,
                f"{prefix}.dataset_group_hpo",
                [
                    "required_dataset_ids",
                    "stage2_support_ref_by_dataset",
                    "full_budget_support_ref_by_dataset",
                    "frozen_parameter_profile_sha256",
                    "parameter_transfer_contract_sha256",
                    "fixed_scout_seed",
                    "robust_objective",
                    "no_regression_constraints_by_dataset",
                    "incomplete_trial_is_infeasible",
                ],
                missing,
            )
            required_datasets = dataset_group.get("required_dataset_ids")
            if not isinstance(required_datasets, list) or len({str(value) for value in required_datasets}) < 2:
                missing.append(f"{prefix}.dataset_group_hpo.required_dataset_ids must contain at least two datasets")
                required_datasets = []
            required_dataset_set = {str(value) for value in required_datasets}
            for ref_field in ["stage2_support_ref_by_dataset", "full_budget_support_ref_by_dataset"]:
                refs = dataset_group.get(ref_field)
                if not isinstance(refs, dict) or set(str(key) for key in refs) != required_dataset_set:
                    missing.append(
                        f"{prefix}.dataset_group_hpo.{ref_field} must contain exactly every required dataset"
                    )
                elif any(not present(value) for value in refs.values()):
                    missing.append(f"{prefix}.dataset_group_hpo.{ref_field} values must be non-empty refs")
            if normalized(dataset_group.get("robust_objective")) != "maximin_signed_delta":
                missing.append(f"{prefix}.dataset_group_hpo.robust_objective must be maximin_signed_delta")
            if dataset_group.get("incomplete_trial_is_infeasible") is not True:
                missing.append(f"{prefix}.dataset_group_hpo.incomplete_trial_is_infeasible must be true")
            if int_value(dataset_group.get("fixed_scout_seed")) is None:
                missing.append(f"{prefix}.dataset_group_hpo.fixed_scout_seed must be one integer seed")
            for hash_field in ["frozen_parameter_profile_sha256", "parameter_transfer_contract_sha256"]:
                digest = str(dataset_group.get(hash_field) or "").strip().lower()
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    missing.append(f"{prefix}.dataset_group_hpo.{hash_field} must be a lowercase SHA-256")
            floors = dataset_group.get("no_regression_constraints_by_dataset")
            if not isinstance(floors, dict) or set(str(key) for key in floors) != required_dataset_set:
                missing.append(
                    f"{prefix}.dataset_group_hpo.no_regression_constraints_by_dataset must cover every required dataset"
                )
            elif any(float_value(value) is None for value in floors.values()):
                missing.append(
                    f"{prefix}.dataset_group_hpo.no_regression_constraints_by_dataset values must be numeric"
                )
            dimensions = as_dict(policy.get("search_space_audit")).get("dimensions")
            dataset_tokens = {normalized(value) for value in required_dataset_set if normalized(value)}
            for index, dimension in enumerate(dimensions if isinstance(dimensions, list) else []):
                name = normalized(as_dict(dimension).get("name"))
                if (
                    "by_dataset" in name
                    or "dataset_specific" in name
                    or any(name.startswith(f"{token}_") or name.endswith(f"_{token}") for token in dataset_tokens)
                ):
                    missing.append(
                        f"{prefix}.search_space_audit.dimensions[{index}].name may not encode a dataset-specific scalar"
                    )
            if normalized(policy.get("parameter_profile_status")) != "frozen":
                missing.append(f"{prefix}.parameter_profile_status must be frozen before Stage-5 HPO")
    tier = normalized(policy.get("budget_tier"))
    if tier and tier not in HPO_BUDGET_TIERS:
        missing.append(f"{prefix}.budget_tier must be micro/small/standard")
    axis = normalized(policy.get("resource_axis"))
    if axis not in HPO_RESOURCE_AXES:
        missing.append(f"{prefix}.resource_axis must be epochs, steps, or data_fraction")
    if "seed" in axis:
        missing.append(f"{prefix}.resource_axis must not be seed count")

    _validate_trial_budget(policy, prefix, missing, warnings)
    _validate_rungs(policy, prefix, missing, warnings)
    _validate_seed_policy(policy, prefix, missing)
    _validate_search_space(policy, prefix, missing, warnings)
    _validate_promotion(policy, prefix, missing, warnings)
    _validate_execution(policy, prefix, missing)


def default_hpo_search_policy(mechanism: str) -> dict[str, Any]:
    if str(mechanism or "").strip().upper() != "PARAM":
        return {
            "search_method": "not_applicable",
            "search_role": "not_applicable",
            "reason": "No PARAM mechanism or target sweep was declared.",
        }
    return {
        "search_method": "dehb_resource_constrained",
        "search_role": "PARAM",
        "tuning_target": "mechanism_parameterization",
        "activation_status": "pending_support",
        "budget_tier": "micro",
        "resource_axis": "epochs",
        "trial_budget": {
            "max_scout_trials": 12,
            "max_full_budget_trials": 1,
            "max_total_gpu_hours": 0,
            "user_approved_higher_budget": False,
        },
        "rungs": [
            {"name": "r0", "resource_fraction": 0.1, "promotion": "top_fraction_or_top_k"},
            {"name": "r1", "resource_fraction": 0.3, "promotion": "top_fraction_or_top_k"},
            {"name": "r2", "resource_fraction": 1.0, "promotion": "top_k"},
        ],
        "search_space_audit": {
            "max_search_dimensions": MAX_SEARCH_DIMENSIONS,
            "protected_axes": ["random_seed", "dataset", "split", "baseline", "metric"],
            "dimensions": [],
        },
        "dehb_config": {
            "population_size": 8,
            "eta": 3,
            "initial_design": "baseline_default_plus_small_random",
            "mutation_strategy": "differential_evolution_survivors",
            "categorical_strategy": "mutate_among_declared_choices",
            "conditional_dimension_strategy": "inactive_dimensions_are_not_sampled",
        },
        "seed_policy": {
            "seed_is_search_axis": False,
            "scout_random_seed_count": 1,
            "matched_seed_protocol": True,
            "max_total_random_seeds": MAX_CONFIRMATION_SEEDS,
        },
        "promotion_rule": {
            "promote_top_k": 1,
            "max_promote_top_k": 2,
            "full_resource_before_candidate": True,
            "metric_policy_ref": "planner/EXPERIMENT_REVIEW_PACKET.json:metric_policy",
        },
        "execution_policy": {
            "mode": "elastic_async",
            "max_concurrent_scouts": "auto",
            "max_concurrent_full_budget_trials": 1,
            "promotions_require_comparable_rung_metrics": True,
            "scheduler_ref": "experiment/NEXT_EXPERIMENT_QUEUE.json",
        },
        "kill_condition": "Stop a trial on NaN/OOM/parser failure/material regression; stop PARAM branch after the declared DEHB budget without promoted improvement.",
        "claim_boundary": "Low-fidelity HPO scouts are pilot/search evidence only; final claims require full-resource plus ablation or confirmation.",
    }
