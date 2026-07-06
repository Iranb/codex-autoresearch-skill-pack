"""Validation helpers for resource-constrained DEHB HPO policy."""

from __future__ import annotations

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
    try:
        return int(value)
    except (TypeError, ValueError):
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
        ["seed_is_search_axis", "scout_random_seed_count", "matched_seed_protocol", "max_confirmation_random_seeds"],
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
    max_confirm = int_value(seed_policy.get("max_confirmation_random_seeds"))
    if max_confirm is None or max_confirm < 1 or max_confirm > MAX_CONFIRMATION_SEEDS:
        missing.append(f"{prefix}.seed_policy.max_confirmation_random_seeds must be between 1 and {MAX_CONFIRMATION_SEEDS}")


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
            "budget_tier",
            "resource_axis",
            "trial_budget",
            "rungs",
            "search_space_audit",
            "seed_policy",
            "promotion_rule",
            "kill_condition",
            "claim_boundary",
        ],
        missing,
    )
    role = normalized(policy.get("search_role"))
    if mtype == "PARAM" and role != "param":
        missing.append(f"{prefix}.search_role must be PARAM for PARAM mechanisms")
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
            "max_confirmation_random_seeds": MAX_CONFIRMATION_SEEDS,
        },
        "promotion_rule": {
            "promote_top_k": 1,
            "max_promote_top_k": 2,
            "full_resource_before_candidate": True,
            "metric_policy_ref": "planner/EXPERIMENT_REVIEW_PACKET.json:metric_policy",
        },
        "kill_condition": "Stop a trial on NaN/OOM/parser failure/material regression; stop PARAM branch after the declared DEHB budget without promoted improvement.",
        "claim_boundary": "Low-fidelity HPO scouts are pilot/search evidence only; final claims require full-resource plus ablation or confirmation.",
    }
