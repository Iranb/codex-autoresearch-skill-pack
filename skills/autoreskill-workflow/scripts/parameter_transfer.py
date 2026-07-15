#!/usr/bin/env python3
"""Canonical validation for cross-dataset innovation-parameter transfer."""

from __future__ import annotations

import hashlib
import json
from typing import Any


VALID_PARAMETER_ROLES = {
    "baseline_protocol",
    "innovation_load_bearing",
    "innovation_nuisance",
    "diagnostic_only",
}
VALID_TRANSFER_MODES = {"shared_absolute", "shared_normalized", "dataset_calibrated"}
VALID_DATA_SCOPES = {"train_only", "unlabeled_target"}
VALID_PROFILE_STATUSES = {"not_required", "audit_pending", "calibrating", "frozen", "invalidated"}
VALID_PROBE_KINDS = {"scale_audit", "bounded_calibration", "portability_probe"}
VALID_STAGE2_ROLES = {"stage2_parameter_probe", "stage2_method_screen"}
HASH_IGNORED = {"semantic_sha256", "created_at", "generated_at", "updated_at"}


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def stable_hash(payload: Any) -> str:
    if isinstance(payload, dict):
        payload = {key: value for key, value in payload.items() if key not in HASH_IGNORED}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def distinct_values(values: Any) -> list[Any]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = canonical_value(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def program_contract_binding(program_contract: dict[str, Any]) -> dict[str, Any]:
    if not program_contract:
        return {}
    return {
        "program_claim_contract_ref": "orchestrator/PROGRAM_CLAIM_CONTRACT.json",
        "program_claim_contract_sha256": str(program_contract.get("semantic_sha256") or stable_hash(program_contract)),
        "program_claim_contract_revision": int(program_contract.get("contract_revision") or 0),
        "claim_scope": str(program_contract.get("claim_scope") or "dataset_specific"),
    }


def required_dataset_ids(program_contract: dict[str, Any], packet: dict[str, Any] | None = None) -> list[str]:
    rows = program_contract.get("target_datasets") if isinstance(program_contract, dict) else None
    result: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or row.get("required") is not True:
                continue
            dataset_id = str(row.get("dataset_id") or "").strip()
            if dataset_id and dataset_id not in result:
                result.append(dataset_id)
    if result or not isinstance(packet, dict):
        return result
    plan = packet.get("dataset_group_plan")
    if isinstance(plan, dict):
        values = plan.get("required_dataset_ids") or plan.get("dataset_ids")
        if isinstance(values, list):
            return [str(value).strip() for value in values if str(value).strip()]
    dataset = str(packet.get("dataset") or "").strip()
    return [dataset] if dataset else []


def validate_parameter_transfer_contract(
    contract: Any,
    datasets: list[str],
    *,
    require_coverage: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(contract, dict):
        return {
            "complete": False,
            "errors": ["parameter_transfer_contract must be an object"],
            "warnings": [],
        }

    role = str(contract.get("parameter_role") or "").strip()
    if role not in VALID_PARAMETER_ROLES:
        errors.append("parameter_role_unclassified")
    load_bearing = contract.get("load_bearing") is True or role == "innovation_load_bearing"
    if not load_bearing:
        errors.append("parameter_transfer_contract must describe one innovation_load_bearing parameter")
    for field in [
        "parameter_name",
        "parameter_calibration_group_id",
        "parameter_probe_kind",
        "scale_type",
        "transfer_mode",
        "shared_formula",
        "normalization_or_calibration_statistic",
        "calibration_data_scope",
        "selection_metric",
        "selection_rule",
        "stop_rule",
        "claim_ceiling",
    ]:
        if not present(contract.get(field)):
            errors.append(f"parameter_transfer_contract.{field} is required")
    if str(contract.get("parameter_probe_kind") or "") not in VALID_PROBE_KINDS:
        errors.append("parameter_transfer_contract.parameter_probe_kind is invalid")

    mode = str(contract.get("transfer_mode") or "").strip()
    if mode not in VALID_TRANSFER_MODES:
        errors.append("parameter_transfer_contract.transfer_mode is invalid")
    if str(contract.get("calibration_data_scope") or "") not in VALID_DATA_SCOPES:
        errors.append("calibration_data_scope_invalid")
    if contract.get("test_outcome_forbidden") is not True:
        errors.append("test_derived_calibration_forbidden")
    if int(contract.get("seed_cardinality_per_dataset_during_parameter_coverage") or 0) != 1:
        errors.append("seed_cardinality_per_dataset_during_parameter_coverage must be 1")
    minimum = int(contract.get("minimum_distinct_values_per_dataset") or 0)
    maximum = int(contract.get("max_values_per_dataset") or 0)
    if minimum != 2 or maximum < minimum or maximum > 3:
        errors.append("parameter value cardinality must be 2-3")

    exception = str(contract.get("single_value_exception") or "none").strip()
    if exception not in {"none", "zero_shot_only"}:
        errors.append("single_value_exception may be none or zero_shot_only")
    candidates = contract.get("candidate_values_by_dataset")
    seeds = contract.get("selection_seed_by_dataset")
    bases = contract.get("value_basis_by_dataset")
    if not isinstance(candidates, dict):
        candidates = {}
        errors.append("candidate_values_by_dataset must be an object")
    if not isinstance(seeds, dict):
        seeds = {}
        errors.append("selection_seed_by_dataset must be an object")
    if not isinstance(bases, dict):
        bases = {}
        errors.append("value_basis_by_dataset must be an object")

    value_sets: dict[str, list[Any]] = {}
    coverage_deficit: dict[str, int] = {}
    for dataset_id in datasets:
        values = distinct_values(candidates.get(dataset_id))
        value_sets[dataset_id] = values
        required_count = 1 if exception == "zero_shot_only" else minimum
        if require_coverage and not (required_count <= len(values) <= maximum):
            coverage_deficit[dataset_id] = max(0, required_count - len(values))
            errors.append(f"innovation_parameter_coverage_incomplete:{dataset_id}")
        if dataset_id not in seeds or isinstance(seeds.get(dataset_id), (list, dict)):
            errors.append(f"selection_seed_missing_or_non_scalar:{dataset_id}")
        if not present(bases.get(dataset_id)):
            errors.append(f"value_basis_by_dataset missing:{dataset_id}")

    if mode in {"shared_absolute", "shared_normalized"} and value_sets:
        canonical_sets = {
            tuple(sorted(canonical_value(value) for value in values)) for values in value_sets.values()
        }
        if len(canonical_sets) > 1:
            errors.append("shared_mode_candidate_sets_must_match")
    if mode in {"shared_absolute", "shared_normalized"}:
        formula = str(contract.get("shared_formula") or "").casefold()
        for dataset_id in datasets:
            if str(dataset_id).strip().casefold() in formula:
                errors.append(f"shared_formula_contains_dataset_identity_lookup:{dataset_id}")
        for field in ["dataset_formula_by_dataset", "formula_override_by_dataset"]:
            if present(contract.get(field)):
                errors.append(f"{field}_forbidden_for_shared_mode")
    if mode == "shared_absolute" and not present(contract.get("scale_comparability_rationale")):
        errors.append("shared_absolute_scale_unjustified")
    if mode == "shared_normalized" and str(contract.get("normalization_or_calibration_statistic")) == "none":
        errors.append("shared_normalized requires a label-free normalization statistic")
    if exception == "zero_shot_only" and str(contract.get("claim_ceiling") or "") not in {
        "zero_shot_transfer",
        "exploratory_only",
        "dataset_scoped",
    }:
        errors.append("zero_shot_only has an invalid claim ceiling")

    recorded = str(contract.get("parameter_transfer_contract_sha256") or "").strip().lower()
    computed = stable_hash({key: value for key, value in contract.items() if key != "parameter_transfer_contract_sha256"})
    if recorded and recorded != computed:
        errors.append("parameter_transfer_contract_sha256 mismatch")
    elif not recorded:
        warnings.append("parameter_transfer_contract_sha256 is absent")
    return {
        "complete": not errors,
        "errors": errors,
        "warnings": warnings,
        "transfer_mode": mode,
        "required_dataset_ids": datasets,
        "coverage_deficit_by_dataset": coverage_deficit,
        "computed_sha256": computed,
    }


def validate_frozen_profile(
    profile: Any,
    contract: dict[str, Any],
    datasets: list[str],
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(profile, dict):
        return {"complete": False, "errors": ["parameter_profile_not_frozen"]}
    if profile.get("parameter_profile_status") != "frozen":
        errors.append("parameter_profile_not_frozen")
    if not present(profile.get("calibration_decision_ref")) or not present(profile.get("calibration_decision_sha256")):
        errors.append("frozen profile must bind the ledger calibration decision")
    expected_contract_hash = str(
        contract.get("parameter_transfer_contract_sha256")
        or stable_hash({key: value for key, value in contract.items() if key != "parameter_transfer_contract_sha256"})
    ).strip()
    if str(profile.get("parameter_transfer_contract_sha256") or "").strip() != expected_contract_hash:
        errors.append("parameter_profile_stale")
    selected = profile.get("selected_setting_by_dataset")
    realized = profile.get("realized_value_by_dataset")
    if not isinstance(selected, dict):
        selected = {}
        errors.append("selected_setting_by_dataset must be an object")
    if not isinstance(realized, dict):
        realized = {}
        errors.append("realized_value_by_dataset must be an object")
    for dataset_id in datasets:
        if dataset_id not in selected:
            errors.append(f"selected_setting_missing:{dataset_id}")
        if dataset_id not in realized:
            errors.append(f"realized_value_missing:{dataset_id}")

    mode = str(contract.get("transfer_mode") or "")
    if mode in {"shared_absolute", "shared_normalized"}:
        values = {canonical_value(selected.get(dataset_id)) for dataset_id in datasets if dataset_id in selected}
        if len(values) > 1:
            errors.append("shared_mode_profile_must_freeze_one_common_setting")
    if mode == "shared_absolute":
        selected_values = {canonical_value(selected.get(dataset_id)) for dataset_id in datasets if dataset_id in selected}
        realized_values = {canonical_value(realized.get(dataset_id)) for dataset_id in datasets if dataset_id in realized}
        if selected_values != realized_values:
            errors.append("shared_absolute realized values must equal the common selected raw value")

    recorded = str(profile.get("frozen_parameter_profile_sha256") or "").strip().lower()
    computed = stable_hash({key: value for key, value in profile.items() if key != "frozen_parameter_profile_sha256"})
    if recorded and recorded != computed:
        errors.append("frozen_parameter_profile_sha256 mismatch")
    elif not recorded:
        errors.append("frozen_parameter_profile_sha256 is required")
    return {"complete": not errors, "errors": errors, "computed_sha256": computed, "transfer_mode": mode}


def validate_parameter_probe_rows(
    rows: list[dict[str, Any]],
    contract: dict[str, Any],
    datasets: list[str],
) -> dict[str, Any]:
    errors: list[str] = []
    group_id = str(contract.get("parameter_calibration_group_id") or "").strip()
    candidates = contract.get("candidate_values_by_dataset") or {}
    seeds = contract.get("selection_seed_by_dataset") or {}
    observed: dict[str, set[tuple[str, str]]] = {dataset_id: set() for dataset_id in datasets}
    for row in rows:
        if str(row.get("parameter_calibration_group_id") or "") != group_id:
            continue
        if str(row.get("stage2_role") or "") != "stage2_parameter_probe":
            continue
        dataset_id = str(row.get("dataset_id") or row.get("dataset") or "")
        if dataset_id not in observed:
            continue
        observed[dataset_id].add((canonical_value(row.get("parameter_value")), canonical_value(row.get("seed"))))
    for dataset_id in datasets:
        expected_values = {canonical_value(value) for value in distinct_values(candidates.get(dataset_id))}
        expected_seed = canonical_value(seeds.get(dataset_id))
        observed_values = {value for value, _ in observed[dataset_id]}
        observed_seeds = {seed for _, seed in observed[dataset_id]}
        if observed_values != expected_values:
            errors.append(f"parameter_probe_rows_incomplete:{dataset_id}")
        if observed_seeds and observed_seeds != {expected_seed}:
            errors.append(f"selection_seed_drift:{dataset_id}")
    return {"complete": not errors, "errors": errors}
