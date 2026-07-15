#!/usr/bin/env python3
"""Materialize and reconcile complete cross-dataset DEHB-lite trial groups.

The experiment queue remains the launch authority. This helper creates one
queue row per required dataset for a shared configuration and reports an HPO
objective only after every leg has terminal, hash-bound result evidence.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import random
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILLS_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_SCRIPT = SKILLS_ROOT / "autoreskill-workflow/scripts/experiment_next_actions.py"
QUEUE_REL = Path(".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json")
LEDGER_REL = Path(".autoreskill/ideation/IDEA_DECISION_LEDGER.json")
TERMINAL = {"terminal_positive", "terminal_negative"}
COMPARISONS = {
    "vs paper-reported baseline",
    "vs reproduced baseline",
    "vs matched reproduced baseline",
    "paper-report comparison not established",
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def load_workflow() -> Any:
    spec = importlib.util.spec_from_file_location("dataset_group_hpo_queue", WORKFLOW_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {WORKFLOW_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def ledger_lock(base: Path) -> Any:
    path = base / "ideation/IDEA_DECISION_LEDGER.json.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def row_gpu_hours(row: dict[str, Any]) -> float | None:
    direct = numeric(row.get("estimated_gpu_hours"))
    if direct is not None:
        return direct
    request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    return numeric(request.get("estimated_gpu_hours"))


def review_packet(base: Path, track_id: str) -> dict[str, Any]:
    value = read_json(base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json", {})
    return value if isinstance(value, dict) else {}


def eligible_policy(review: dict[str, Any]) -> dict[str, Any]:
    policy = review.get("hpo_search_policy") if isinstance(review.get("hpo_search_policy"), dict) else {}
    if str(policy.get("activation_status") or "").strip().lower() != "eligible":
        raise RuntimeError("Stage-5 HPO is not activation_status=eligible")
    if str(policy.get("tuning_target") or "").strip().lower() != "mechanism_parameterization":
        raise RuntimeError("dataset-group HPO only supports mechanism_parameterization")
    if not str(policy.get("sensitivity_question") or "").strip():
        raise RuntimeError("eligible HPO requires an explicit sensitivity_question")
    dimensions = (policy.get("search_space_audit") or {}).get("dimensions")
    if not isinstance(dimensions, list) or not 3 <= len(dimensions) <= 6:
        raise RuntimeError("eligible HPO requires 3-6 declared dimensions")
    return copy.deepcopy(policy)


def required_datasets(review: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    group = policy.get("dataset_group_hpo") if isinstance(policy.get("dataset_group_hpo"), dict) else {}
    values = group.get("required_dataset_ids") or (review.get("dataset_group_plan") or {}).get("required_dataset_ids")
    datasets = [str(value) for value in as_list(values) if str(value)]
    if len(set(datasets)) < 2:
        raise RuntimeError("dataset-group HPO requires at least two required datasets")
    return list(dict.fromkeys(datasets))


def full_budget_support_rows(queue: dict[str, Any], track_id: str, datasets: list[str], ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    positive_decisions = {
        str(row.get("queue_row_id") or "")
        for row in ledger.get("experiment_decisions", [])
        if isinstance(row, dict) and str(row.get("outcome_class") or "") == "valid_positive_candidate"
    }
    result: dict[str, dict[str, Any]] = {}
    for row in queue.get("rows", []):
        if not isinstance(row, dict) or str(row.get("track_id") or "") != track_id:
            continue
        if row.get("validation_stage") not in {3, 4} or str(row.get("status") or "") != "terminal_positive":
            continue
        row_id = str(row.get("id") or "")
        dataset_id = str(row.get("dataset_id") or row.get("dataset") or "")
        if dataset_id in datasets and row_id in positive_decisions:
            result[dataset_id] = row
    missing = sorted(set(datasets) - set(result))
    if missing:
        raise RuntimeError("Stage-5 HPO lacks ledger-backed full-budget support for: " + ", ".join(missing))
    return result


def dimension_config(policy: dict[str, Any], index: int, completed: list[dict[str, Any]]) -> dict[str, Any]:
    dimensions = policy["search_space_audit"]["dimensions"]
    if index == 0:
        return {str(row["name"]): row.get("default_or_prior") for row in dimensions}
    rng = random.Random(int(stable_hash({"policy": policy, "index": index})[:16], 16))
    population = [row.get("configuration") for row in completed if isinstance(row.get("configuration"), dict)]
    parents = population[:3] if len(population) >= 3 else []
    config: dict[str, Any] = {}
    for dimension in dimensions:
        name = str(dimension.get("name") or "")
        kind = str(dimension.get("type") or "").strip().lower()
        bounds = dimension.get("bounds_or_choices")
        if not name or not isinstance(bounds, list) or not bounds:
            raise RuntimeError(f"invalid HPO dimension {name or '<unnamed>'}")
        if kind in {"categorical", "ordinal", "boolean"}:
            config[name] = bounds[index % len(bounds)] if index < len(bounds) else rng.choice(bounds)
            continue
        if len(bounds) != 2 or numeric(bounds[0]) is None or numeric(bounds[1]) is None:
            raise RuntimeError(f"numeric HPO dimension {name} requires two finite bounds")
        low, high = float(bounds[0]), float(bounds[1])
        if low > high:
            low, high = high, low
        if parents and all(numeric(parent.get(name)) is not None for parent in parents):
            value = float(parents[0][name]) + 0.5 * (float(parents[1][name]) - float(parents[2][name]))
            if rng.random() > 0.7:
                value = float(parents[rng.randrange(len(parents))][name])
        elif kind == "log_float" and low > 0:
            value = math.exp(math.log(low) + rng.random() * (math.log(high) - math.log(low)))
        else:
            value = low + rng.random() * (high - low)
        value = min(high, max(low, value))
        config[name] = int(round(value)) if kind == "integer" else value
    return config


def validate_configuration(policy: dict[str, Any], configuration: dict[str, Any]) -> None:
    dimensions = [row for row in (policy.get("search_space_audit") or {}).get("dimensions", []) if isinstance(row, dict)]
    expected = {str(row.get("name") or "") for row in dimensions if str(row.get("name") or "")}
    if set(configuration) != expected:
        raise RuntimeError(
            "HPO configuration keys must exactly match declared dimensions; "
            f"missing={sorted(expected - set(configuration))}, extra={sorted(set(configuration) - expected)}"
        )
    for dimension in dimensions:
        name = str(dimension["name"])
        kind = str(dimension.get("type") or "").strip().lower()
        bounds = dimension.get("bounds_or_choices")
        value = configuration[name]
        if not isinstance(bounds, list) or not bounds:
            raise RuntimeError(f"invalid HPO dimension {name}")
        if kind in {"categorical", "ordinal", "boolean"}:
            if value not in bounds:
                raise RuntimeError(f"HPO configuration value for {name} is outside declared choices")
            continue
        parsed = numeric(value)
        if parsed is None or len(bounds) != 2 or numeric(bounds[0]) is None or numeric(bounds[1]) is None:
            raise RuntimeError(f"HPO configuration value for {name} must be finite and within declared bounds")
        low, high = sorted([float(bounds[0]), float(bounds[1])])
        if not low <= parsed <= high:
            raise RuntimeError(f"HPO configuration value for {name} is outside declared bounds")
        if kind == "integer" and not float(parsed).is_integer():
            raise RuntimeError(f"HPO configuration value for {name} must be an integer")


def trial_groups(queue: dict[str, Any], track_id: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in queue.get("rows", []):
        if not isinstance(row, dict) or str(row.get("track_id") or "") != track_id:
            continue
        trial_id = str(row.get("dataset_group_trial_id") or "")
        if trial_id:
            groups.setdefault(trial_id, []).append(row)
    return groups


def result_artifact(base: Path, row: dict[str, Any]) -> tuple[dict[str, Any], str | None, str | None]:
    refs = []
    if row.get("canonical_result_ref"):
        refs.append(str(row["canonical_result_ref"]))
    refs.extend(str(value) for value in reversed(as_list(row.get("evidence_paths"))) if value)
    for ref in refs:
        path = Path(ref).expanduser()
        path = path if path.is_absolute() else base / path
        payload = read_json(path, None)
        if isinstance(payload, dict) and "canonical_signed_delta" in payload:
            return payload, ref, file_sha256(path)
    return {}, None, None


def aggregate_group(base: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    exemplar = rows[0]
    policy = exemplar.get("hpo_search_policy") if isinstance(exemplar.get("hpo_search_policy"), dict) else {}
    group = policy.get("dataset_group_hpo") if isinstance(policy.get("dataset_group_hpo"), dict) else {}
    required = [str(value) for value in as_list(group.get("required_dataset_ids")) if str(value)]
    errors: list[str] = []
    by_dataset: dict[str, dict[str, Any]] = {}
    for row in rows:
        dataset_id = str(row.get("dataset_id") or row.get("dataset") or "")
        if dataset_id in by_dataset:
            errors.append(f"duplicate_dataset_leg:{dataset_id}")
        else:
            by_dataset[dataset_id] = row
    observations: list[dict[str, Any]] = []
    for dataset_id in required:
        row = by_dataset.get(dataset_id)
        if row is None:
            errors.append(f"missing_dataset_leg:{dataset_id}")
            continue
        if str(row.get("dataset_group_trial_config_sha256") or "") != str(
            exemplar.get("dataset_group_trial_config_sha256") or ""
        ):
            errors.append(f"queue_configuration_identity_mismatch:{dataset_id}")
        if str(row.get("hpo_rung_name") or "") != str(exemplar.get("hpo_rung_name") or ""):
            errors.append(f"queue_rung_identity_mismatch:{dataset_id}")
        if numeric(row.get("hpo_resource_fraction")) != numeric(exemplar.get("hpo_resource_fraction")):
            errors.append(f"queue_resource_identity_mismatch:{dataset_id}")
        if row.get("seed") != exemplar.get("seed"):
            errors.append(f"queue_seed_identity_mismatch:{dataset_id}")
        if str(row.get("status") or "") not in TERMINAL:
            errors.append(f"nonterminal_dataset_leg:{dataset_id}")
            continue
        artifact, ref, digest = result_artifact(base, row)
        delta = numeric(artifact.get("canonical_signed_delta")) if artifact else None
        if not artifact or not ref or not digest:
            errors.append(f"result_artifact_missing:{dataset_id}")
            continue
        if str(artifact.get("dataset_id") or "") != dataset_id:
            errors.append(f"result_identity_mismatch:{dataset_id}")
        if str(artifact.get("dataset_group_trial_id") or "") != str(exemplar.get("dataset_group_trial_id") or ""):
            errors.append(f"trial_identity_mismatch:{dataset_id}")
        if str(artifact.get("dataset_group_trial_config_sha256") or "") != str(
            exemplar.get("dataset_group_trial_config_sha256") or ""
        ):
            errors.append(f"configuration_identity_mismatch:{dataset_id}")
        if artifact.get("terminal_valid") is not True or artifact.get("protocol_valid") is not True:
            errors.append(f"invalid_result:{dataset_id}")
        if delta is None:
            errors.append(f"canonical_signed_delta_missing:{dataset_id}")
        comparison = str(artifact.get("comparison_source") or "")
        if comparison not in COMPARISONS:
            errors.append(f"comparison_source_invalid:{dataset_id}")
        observations.append(
            {
                "dataset_id": dataset_id,
                "canonical_signed_delta": delta,
                "comparison_source": comparison,
                "result_ref": ref,
                "result_sha256": digest,
            }
        )
    floors = group.get("no_regression_constraints_by_dataset") if isinstance(
        group.get("no_regression_constraints_by_dataset"), dict
    ) else {}
    complete = not errors and len(observations) == len(required)
    objective = min(float(row["canonical_signed_delta"]) for row in observations) if complete else None
    floor_pass = complete and all(
        float(row["canonical_signed_delta"]) >= float(floors[row["dataset_id"]])
        for row in observations
        if numeric(floors.get(row["dataset_id"])) is not None
    ) and set(floors) == set(required)
    payload = {
        "schema_version": 1,
        "track_id": exemplar.get("track_id"),
        "dataset_group_trial_id": exemplar.get("dataset_group_trial_id"),
        "dataset_group_trial_config_sha256": exemplar.get("dataset_group_trial_config_sha256"),
        "configuration": exemplar.get("dataset_group_trial_config"),
        "hpo_rung_name": exemplar.get("hpo_rung_name"),
        "hpo_resource_fraction": exemplar.get("hpo_resource_fraction"),
        "required_dataset_ids": required,
        "observations": observations,
        "complete_required_dataset_trial": complete,
        "eligible_for_optimizer": complete,
        "robust_objective": "maximin_signed_delta",
        "robust_objective_value": objective,
        "no_regression_constraints_passed": floor_pass,
        "feasible": bool(complete and floor_pass),
        "errors": errors,
    }
    payload["aggregate_sha256"] = stable_hash(payload)
    return payload


def completed_summaries(base: Path, queue: dict[str, Any], track_id: str) -> list[dict[str, Any]]:
    summaries = [aggregate_group(base, rows) for rows in trial_groups(queue, track_id).values()]
    return sorted(
        [row for row in summaries if row.get("complete_required_dataset_trial") is True],
        key=lambda row: (-float(row.get("robust_objective_value") or -math.inf), str(row.get("dataset_group_trial_id") or "")),
    )


def next_trial_spec(base: Path, queue: dict[str, Any], track_id: str, policy: dict[str, Any]) -> dict[str, Any] | None:
    groups = trial_groups(queue, track_id)
    if any(any(str(row.get("status") or "") not in TERMINAL for row in rows) for rows in groups.values()):
        return None
    summaries = [aggregate_group(base, rows) for rows in groups.values()]
    if any(row.get("complete_required_dataset_trial") is not True for row in summaries):
        return None
    completed = completed_summaries(base, queue, track_id)
    rungs = [row for row in policy.get("rungs", []) if isinstance(row, dict)]
    if len(rungs) < 2:
        raise RuntimeError("HPO policy requires at least two rungs")
    eta = int((policy.get("dehb_config") or {}).get("eta") or 3)
    full_rung_names = {
        str(row.get("name") or "") for row in rungs
        if numeric(row.get("resource_fraction") or row.get("fraction")) == 1.0
    }
    max_full = int((policy.get("trial_budget") or {}).get("max_full_budget_trials") or 0)
    completed_full = sum(1 for row in completed if str(row.get("hpo_rung_name") or "") in full_rung_names)
    if completed_full >= max_full:
        return None
    promote_top_k = max(1, int((policy.get("promotion_rule") or {}).get("promote_top_k") or 1))
    for index, rung in enumerate(rungs[:-1]):
        source = [
            row for row in completed
            if str(row.get("hpo_rung_name") or "") == str(rung.get("name") or "") and row.get("feasible") is True
        ]
        if len(source) < eta:
            continue
        next_name = str(rungs[index + 1].get("name") or "")
        if next_name in full_rung_names and completed_full >= max_full:
            continue
        represented = {
            str(row.get("dataset_group_trial_config_sha256") or "")
            for row in completed if str(row.get("hpo_rung_name") or "") == next_name
        }
        promotion_slots = min(promote_top_k, max(1, len(source) // eta))
        if next_name in full_rung_names:
            promotion_slots = min(promotion_slots, max_full - completed_full)
        if len(represented) >= promotion_slots:
            continue
        candidate = next((row for row in source if row.get("dataset_group_trial_config_sha256") not in represented), None)
        if candidate is not None:
            return {"configuration": candidate["configuration"], "rung": rungs[index + 1], "source": "hyperband_promotion"}
    first_name = str(rungs[0].get("name") or "")
    scouts = [
        rows[0] for rows in groups.values()
        if rows and str(rows[0].get("hpo_rung_name") or "") == first_name
    ]
    max_scouts = int((policy.get("trial_budget") or {}).get("max_scout_trials") or 0)
    if len(scouts) >= max_scouts:
        return None
    config = dimension_config(policy, len(scouts), completed)
    return {"configuration": config, "rung": rungs[0], "source": "default_or_de_mutation"}


def build_trial_rows(
    base: Path,
    queue: dict[str, Any],
    track_id: str,
    configuration: dict[str, Any] | None = None,
    rung_name: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    review = review_packet(base, track_id)
    if not review:
        raise RuntimeError(f"missing review packet for {track_id}")
    policy = eligible_policy(review)
    datasets = required_datasets(review, policy)
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    support = full_budget_support_rows(queue, track_id, datasets, ledger)
    rungs = [row for row in policy.get("rungs", []) if isinstance(row, dict)]
    if configuration is None:
        suggestion = next_trial_spec(base, queue, track_id, policy)
        if suggestion is None:
            groups = trial_groups(queue, track_id)
            if any(any(str(row.get("status") or "") not in TERMINAL for row in rows) for rows in groups.values()):
                reason = "open_dataset_group_trial"
            elif any(
                aggregate_group(base, rows).get("complete_required_dataset_trial") is not True
                for rows in groups.values()
            ):
                reason = "incomplete_group_requires_repair_or_adjudication"
            else:
                reason = "registered_hpo_budget_exhausted"
            return [], {"reason": reason}
        configuration = suggestion["configuration"]
        rung = suggestion["rung"]
        source = suggestion["source"]
    else:
        rung = next((row for row in rungs if str(row.get("name") or "") == str(rung_name or "")), None)
        if rung is None:
            raise RuntimeError("explicit configuration requires a valid --rung-name")
        source = "explicit_dehb_configuration"
    validate_configuration(policy, configuration)
    config_sha = stable_hash(configuration)
    fraction = float(rung.get("resource_fraction") or rung.get("fraction") or 0)
    if not 0 < fraction <= 1:
        raise RuntimeError("HPO rung resource_fraction must be in (0, 1]")
    trial_identity = {
        "track_id": track_id,
        "configuration_sha256": config_sha,
        "rung": rung.get("name"),
        "resource_fraction": fraction,
        "program_claim_contract_sha256": review.get("program_claim_contract_sha256"),
    }
    trial_id = f"hpo-{track_id}-{stable_hash(trial_identity)[:16]}"
    if trial_id in trial_groups(queue, track_id):
        return [], {"reason": "trial_already_materialized", "dataset_group_trial_id": trial_id}
    group = copy.deepcopy(policy.get("dataset_group_hpo") or {})
    group.update(
        {
            "required_dataset_ids": datasets,
            "stage2_support_ref_by_dataset": group.get("stage2_support_ref_by_dataset") or {
                dataset_id: str(review.get("stage2_support_ref_by_dataset", {}).get(dataset_id) or "stage2-cross-dataset-decision")
                for dataset_id in datasets
            },
            "full_budget_support_ref_by_dataset": {
                dataset_id: str(support[dataset_id]["id"]) for dataset_id in datasets
            },
            "frozen_parameter_profile_sha256": review.get("frozen_parameter_profile_sha256"),
            "parameter_transfer_contract_sha256": (review.get("parameter_transfer_contract") or {}).get(
                "parameter_transfer_contract_sha256"
            ),
            "fixed_scout_seed": group.get("fixed_scout_seed", 0),
            "robust_objective": "maximin_signed_delta",
            "no_regression_constraints_by_dataset": group.get("no_regression_constraints_by_dataset") or {},
            "incomplete_trial_is_infeasible": True,
        }
    )
    policy["dataset_group_hpo"] = group
    policy["parameter_profile_status"] = "frozen"
    total_hours = numeric((policy.get("trial_budget") or {}).get("max_total_gpu_hours")) or numeric(
        policy.get("remaining_gpu_hours")
    )
    if total_hours is None or total_hours <= 0:
        raise RuntimeError("eligible HPO requires a positive finite GPU-hour budget")
    remaining_hours = numeric(policy.get("remaining_gpu_hours"))
    if remaining_hours is None or remaining_hours <= 0:
        raise RuntimeError("eligible HPO requires positive remaining_gpu_hours")
    existing_hpo_hours = sum(
        row_gpu_hours(row) or 0.0 for row in queue.get("rows", [])
        if isinstance(row, dict) and str(row.get("track_id") or "") == track_id and row.get("validation_stage") == 5
    )
    support_hours = {dataset_id: row_gpu_hours(support[dataset_id]) for dataset_id in datasets}
    missing_cost = sorted(dataset_id for dataset_id, value in support_hours.items() if value is None or value <= 0)
    if missing_cost:
        raise RuntimeError("full-budget support rows lack positive GPU-hour estimates for: " + ", ".join(missing_cost))
    per_leg_hours_by_dataset = {
        dataset_id: float(support_hours[dataset_id]) * fraction for dataset_id in datasets
    }
    proposed_hpo_hours = sum(per_leg_hours_by_dataset.values())
    if existing_hpo_hours + proposed_hpo_hours > total_hours + 1e-9 or proposed_hpo_hours > remaining_hours + 1e-9:
        return [], {
            "reason": "hpo_gpu_hour_budget_exhausted",
            "planned_gpu_hours": existing_hpo_hours,
            "proposed_gpu_hours": proposed_hpo_hours,
            "max_total_gpu_hours": total_hours,
            "remaining_gpu_hours": remaining_hours,
        }
    if fraction == 1.0:
        full_trials = {
            str(row.get("dataset_group_trial_id") or "") for row in queue.get("rows", [])
            if isinstance(row, dict) and str(row.get("track_id") or "") == track_id
            and row.get("validation_stage") == 5 and numeric(row.get("hpo_resource_fraction")) == 1.0
        }
        max_full = int((policy.get("trial_budget") or {}).get("max_full_budget_trials") or 0)
        if len(full_trials) >= max_full:
            return [], {"reason": "max_full_budget_trials_reached", "max_full_budget_trials": max_full}
    support_ids = [str(support[dataset_id]["id"]) for dataset_id in datasets]
    rows: list[dict[str, Any]] = []
    for dataset_id in datasets:
        template = copy.deepcopy(support[dataset_id])
        for field in [
            "completed_at", "lease_owner", "lease_acquired_at", "lease_expires_at", "resource_allocation",
            "planned_resource_allocation", "backend_submit_intent", "backend_submit_intent_sha256",
            "backend_submit_receipt", "backend_submit_receipt_sha256", "backend_observations", "canonical_result_ref",
        ]:
            template.pop(field, None)
        row_id = f"{trial_id}-{stable_hash(dataset_id)[:8]}"
        template.update(
            {
                "id": row_id,
                "status": "ready",
                "role": "single_innovation",
                "dataset": dataset_id,
                "dataset_id": dataset_id,
                "priority": 40,
                "next_action": "run one shared DEHB configuration leg at the registered fidelity",
                "updated_at": now(),
                "decision_class": "optimize_supported_mechanism",
                "why_now": "cross-dataset mechanism support and an explicit sensitivity question unlock bounded HPO",
                "expected_decision_change": "complete every dataset leg, then rank only the robust grouped objective",
                "comparison_source": "vs matched reproduced baseline",
                "estimated_gpu_hours": per_leg_hours_by_dataset[dataset_id],
                "resource_request": {
                    **(template.get("resource_request") if isinstance(template.get("resource_request"), dict) else {}),
                    "gpu_count": 1,
                    "estimated_gpu_hours": per_leg_hours_by_dataset[dataset_id],
                },
                "mutex_group": f"{trial_id}:{dataset_id}",
                "parallel_safe": True,
                "launch_mode": "repeated_variant",
                "validation_stage": 5,
                "validation_stage_name": "dataset_group_dehb",
                "validation_prerequisites": ["cross_dataset_full_budget_support"],
                "depends_on_rows": support_ids,
                "mechanism_support_refs": support_ids,
                "reused_cross_dataset_evidence_refs": support_ids,
                "evidence_tier": "pilot_only",
                "claim_eligible": False,
                "claim_ceiling": "search_evidence_only",
                "tuning_target": "mechanism_parameterization",
                "sensitivity_question": policy.get("sensitivity_question"),
                "eligible_belief_states": policy.get("eligible_belief_states"),
                "current_belief_state": policy.get("current_belief_state"),
                "baseline_freeze_or_calibration_ref": policy.get("baseline_freeze_or_calibration_ref"),
                "remaining_hpo_gpu_hours": policy.get("remaining_gpu_hours"),
                "hpo_search_policy": policy,
                "dataset_group_trial_id": trial_id,
                "dataset_group_trial_config": configuration,
                "dataset_group_trial_config_sha256": config_sha,
                "hpo_rung_name": rung.get("name"),
                "hpo_resource_fraction": fraction,
                "hpo_suggestion_source": source,
                "seed": group.get("fixed_scout_seed"),
                "seeds": [group.get("fixed_scout_seed")],
                "seed_count": 1,
                "protocol": stable_hash(
                    {
                        "prior_protocol": template.get("protocol"),
                        "configuration_sha256": config_sha,
                        "rung": rung.get("name"),
                        "resource_fraction": fraction,
                        "dataset_id": dataset_id,
                    }
                ),
                "row_revision": 0,
            }
        )
        template["launch_identity_hash"] = stable_hash(
            {
                "track_id": track_id,
                "row_id": row_id,
                "configuration_sha256": config_sha,
                "rung": rung.get("name"),
                "dataset_id": dataset_id,
                "selection_fingerprint": template.get("selection_fingerprint"),
            }
        )
        rows.append(template)
    return rows, {"dataset_group_trial_id": trial_id, "configuration": configuration, "rung": rung, "source": source}


def reconcile(
    base: Path,
    queue: dict[str, Any],
    track_id: str | None,
    write: bool,
    finalize: bool,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    track_ids = sorted(
        {
            str(row.get("track_id") or "")
            for row in queue.get("rows", [])
            if isinstance(row, dict) and row.get("dataset_group_trial_id")
        }
    )
    if track_id:
        track_ids = [value for value in track_ids if value == track_id]
    aggregates: list[dict[str, Any]] = []
    for current in track_ids:
        aggregates.extend(aggregate_group(base, rows) for rows in trial_groups(queue, current).values())
    decisions: list[dict[str, Any]] = []
    if finalize:
        for current in track_ids:
            groups = trial_groups(queue, current)
            if any(any(str(row.get("status") or "") not in TERMINAL for row in rows) for rows in groups.values()):
                raise RuntimeError(f"cannot finalize {current} while a dataset-group trial is nonterminal")
            if stop_reason:
                finalization_reason = f"explicit_stop:{stop_reason.strip()}"
            else:
                pending_rows, detail = build_trial_rows(base, queue, current)
                if pending_rows:
                    raise RuntimeError(
                        f"cannot finalize {current} before the registered HPO search is exhausted; "
                        "provide --stop-reason for an explicit early stop"
                    )
                reason = str(detail.get("reason") or "")
                if reason != "registered_hpo_budget_exhausted":
                    raise RuntimeError(
                        f"cannot finalize {current} while {reason or 'HPO state is unresolved'}; "
                        "repair/adjudicate the group or provide --stop-reason"
                    )
                finalization_reason = reason
            full = [
                row for row in aggregates
                if row.get("track_id") == current
                and float(row.get("hpo_resource_fraction") or 0) == 1.0
                and row.get("eligible_for_optimizer") is True
                and row.get("feasible") is True
            ]
            if not full:
                continue
            best = max(full, key=lambda row: (float(row["robust_objective_value"]), str(row["dataset_group_trial_id"])))
            decision = {
                "schema_version": 1,
                "track_id": current,
                "verdict": "hpo_configuration_selected",
                "dataset_group_trial_id": best["dataset_group_trial_id"],
                "dataset_group_trial_config_sha256": best["dataset_group_trial_config_sha256"],
                "selected_configuration": best["configuration"],
                "robust_objective": "maximin_signed_delta",
                "robust_objective_value": best["robust_objective_value"],
                "aggregate_sha256": best["aggregate_sha256"],
                "complete_required_dataset_trial": True,
                "no_regression_constraints_passed": True,
                "finalization_reason": finalization_reason,
            }
            decision["decision_sha256"] = stable_hash(decision)
            decision["decision_id"] = "hpo-decision-" + decision["decision_sha256"][:16]
            decisions.append(decision)
    if write:
        with ledger_lock(base):
            ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
            existing_trials = {
                str(row.get("aggregate_sha256") or ""): row
                for row in ledger.get("hpo_group_trials", []) if isinstance(row, dict)
            }
            for aggregate in aggregates:
                trial_id = str(aggregate.get("dataset_group_trial_id") or "")
                path = base / f"analysis/hpo/{aggregate.get('track_id')}/{trial_id}.json"
                atomic_write_json(path, aggregate)
                aggregate["aggregate_ref"] = str(path.relative_to(base))
                existing_trials[aggregate["aggregate_sha256"]] = aggregate
            ledger["hpo_group_trials"] = sorted(existing_trials.values(), key=lambda row: str(row.get("dataset_group_trial_id") or ""))
            existing_decisions = {
                str(row.get("decision_id") or ""): row
                for row in ledger.get("hpo_group_decisions", []) if isinstance(row, dict)
            }
            for decision in decisions:
                existing_decisions[decision["decision_id"]] = decision
            ledger["hpo_group_decisions"] = sorted(existing_decisions.values(), key=lambda row: str(row.get("decision_id") or ""))
            ledger["updated_at"] = now()
            atomic_write_json(base / "ideation/IDEA_DECISION_LEDGER.json", ledger)
    return {"ok": True, "write": write, "aggregates": aggregates, "decisions": decisions}


def cmd_materialize(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    base = project / ".autoreskill"
    workflow = load_workflow()
    queue_path = project / QUEUE_REL
    configuration = read_json(Path(args.configuration_json).expanduser().resolve(), None) if args.configuration_json else None
    if configuration is not None and not isinstance(configuration, dict):
        raise RuntimeError("configuration JSON must contain one object")
    with workflow.queue_lock(queue_path):
        queue = workflow.load_queue(project)
        if not queue:
            raise RuntimeError("NEXT_EXPERIMENT_QUEUE.json is missing")
        if args.expected_revision is not None and int(queue.get("queue_revision") or 0) != args.expected_revision:
            raise RuntimeError("queue revision changed before HPO materialization")
        rows, detail = build_trial_rows(base, queue, args.track_id, configuration, args.rung_name)
        result = {"ok": True, "dry_run": args.dry_run, "added_row_ids": [row["id"] for row in rows], **detail}
        if args.dry_run or not rows:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        queue.setdefault("rows", []).extend(rows)
        queue["queue_revision"] = int(queue.get("queue_revision") or 0) + 1
        queue["updated_at"] = now()
        checked = workflow.validate_queue(queue, project=project)
        if not checked.get("ok"):
            raise RuntimeError("HPO trial rows are invalid: " + "; ".join(checked.get("errors") or []))
        workflow.atomic_write_json(queue_path, queue)
        result["queue_revision"] = queue["queue_revision"]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    if args.stop_reason and not args.finalize:
        raise RuntimeError("--stop-reason is valid only with --finalize")
    project = Path(args.project).expanduser().resolve()
    workflow = load_workflow()
    queue_path = project / QUEUE_REL
    with workflow.queue_lock(queue_path):
        queue = workflow.load_queue(project)
        if not queue:
            raise RuntimeError("NEXT_EXPERIMENT_QUEUE.json is missing")
        result = reconcile(
            project / ".autoreskill",
            queue,
            args.track_id,
            args.write,
            args.finalize,
            args.stop_reason,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("--project", required=True)
    materialize.add_argument("--track-id", required=True)
    materialize.add_argument("--configuration-json")
    materialize.add_argument("--rung-name")
    materialize.add_argument("--expected-revision", type=int)
    materialize.add_argument("--dry-run", action="store_true")
    materialize.set_defaults(func=cmd_materialize)
    reconcile_parser = sub.add_parser("reconcile")
    reconcile_parser.add_argument("--project", required=True)
    reconcile_parser.add_argument("--track-id")
    reconcile_parser.add_argument("--write", action="store_true")
    reconcile_parser.add_argument("--finalize", action="store_true")
    reconcile_parser.add_argument("--stop-reason")
    reconcile_parser.set_defaults(func=cmd_reconcile)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.func(args))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
