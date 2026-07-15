#!/usr/bin/env python3
"""Create, validate, and CAS-update the project-level scientific claim contract."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTRACT_REL = Path(".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json")
EVENTS_REL = Path(".autoreskill/orchestrator/program_claim_contract_events.jsonl")
INTERVENTION_REL = Path(".autoreskill/control/REPLENISHMENT_INTERVENTION_REQUEST.json")
VALID_STATUSES = {"draft", "active", "superseded"}
VALID_MODES = {"legacy", "shadow", "enforced"}
VALID_SCOPES = {"dataset_specific", "cross_dataset_method"}
VALID_DATASET_ROLES = {"primary", "contrast", "confirmation"}
VALID_DIRECTIONS = {"higher", "lower"}
VALID_ALIGNMENTS = {"aligned", "unavailable", "mismatched", "reproduction_below_report"}
VALID_TRANSFER_MODES = {"shared_absolute", "shared_normalized", "dataset_calibrated"}
HASH_EXCLUDED_FIELDS = {"semantic_sha256", "created_at", "updated_at", "contract_revision"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def project_root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def contract_path(project: Path) -> Path:
    return project / CONTRACT_REL


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object in {path}")
    return payload


def canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in HASH_EXCLUDED_FIELDS}


def semantic_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        canonical_payload(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bind_hash(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["semantic_sha256"] = semantic_sha256(result)
    return result


def _artifact_path(project: Path, ref: Any) -> Path | None:
    text = str(ref or "").strip()
    if not text or "://" in text:
        return None
    path = Path(text).expanduser()
    if path.is_absolute():
        return path.resolve()
    if path.parts and path.parts[0] == ".autoreskill":
        return (project / path).resolve()
    return (project / ".autoreskill" / path).resolve()


def validate_replacement_authority(project: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate direct authority for an active replacement program contract.

    Drafts can be structurally checked before their review artifact exists. This
    gate is therefore called by CAS commit, after the candidate semantic hash is
    stable, rather than by the generic schema validator.
    """

    basis_id = str(payload.get("replacement_basis_decision_id") or "").strip()
    if not basis_id:
        return {"complete": True, "errors": [], "warnings": [], "required": False}
    errors: list[str] = []
    warnings: list[str] = []
    source_refs = payload.get("source_refs") if isinstance(payload.get("source_refs"), list) else []
    source_paths = [path for ref in source_refs if (path := _artifact_path(project, ref)) is not None]

    intervention_path = project / INTERVENTION_REL
    intervention = read_json(intervention_path) if intervention_path.exists() else {}
    status = str(intervention.get("status") or "").strip().lower()
    revoked_status = not status or any(
        token in status for token in {"revoked", "cancelled", "rejected", "blocked"}
    )
    if revoked_status:
        errors.append("replacement contract requires a non-revoked budget-authorized intervention")
    if str(intervention.get("basis_decision_id") or "").strip() != basis_id:
        errors.append("replacement_basis_decision_id does not match the intervention basis_decision_id")
    authorization = intervention.get("authorization") if isinstance(intervention.get("authorization"), dict) else {}
    if str(authorization.get("source") or "").strip() != "direct_user_instruction":
        errors.append("replacement replenishment budget requires authorization.source=direct_user_instruction")
    authorized_max = _nonnegative_int(
        authorization.get("max_targeted_replenishments")
        if authorization
        else intervention.get("requested_max_targeted_replenishments")
    )
    budget = payload.get("search_budget") if isinstance(payload.get("search_budget"), dict) else {}
    requested_max = _nonnegative_int(budget.get("max_targeted_replenishments"))
    if authorized_max is None:
        errors.append("authorized max_targeted_replenishments is missing or invalid")
    elif requested_max is not None and requested_max > authorized_max:
        errors.append(
            "replacement contract max_targeted_replenishments exceeds direct user authorization"
        )
    if intervention_path.resolve() not in source_paths:
        errors.append("replacement contract source_refs must include REPLENISHMENT_INTERVENTION_REQUEST.json")

    unresolved_id = str(payload.get("unresolved_paper_decision_id") or "").strip()
    unresolved_candidates: list[dict[str, Any]] = []
    review_candidates: list[dict[str, Any]] = []
    for path in source_paths:
        if not path.exists() or not path.is_file():
            continue
        artifact = read_json(path)
        if not artifact:
            continue
        if str(artifact.get("status") or "").strip().lower() == "unresolved":
            unresolved_candidates.append(artifact)
        cross_review = artifact.get("cross_review") if isinstance(artifact.get("cross_review"), dict) else {}
        if artifact.get("reviewed_semantic_sha256") or cross_review:
            review_candidates.append(artifact)
    if not any(str(row.get("decision_id") or "").strip() == unresolved_id for row in unresolved_candidates):
        errors.append("replacement contract source_refs must include the named unresolved paper decision")

    candidate_sha = str(payload.get("semantic_sha256") or semantic_sha256(payload)).strip().lower()
    approved_review = False
    for review in review_candidates:
        reviewed_sha = str(review.get("reviewed_semantic_sha256") or "").strip().lower()
        cross_review = review.get("cross_review") if isinstance(review.get("cross_review"), dict) else {}
        verdict = str(cross_review.get("verdict") or review.get("verdict") or "").strip().upper()
        if reviewed_sha == candidate_sha and verdict.startswith("APPROVE"):
            approved_review = True
            break
    if not approved_review:
        errors.append("replacement contract requires an approving review bound to its semantic_sha256")
    return {
        "complete": not errors,
        "errors": errors,
        "warnings": warnings,
        "required": True,
        "basis_decision_id": basis_id,
        "authorized_max_targeted_replenishments": authorized_max,
        "requested_max_targeted_replenishments": requested_max,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def contract_lock(path: Path) -> Any:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def default_contract(project: Path) -> dict[str, Any]:
    slug = project.name or "project"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": f"program-claim-{slug}",
        "contract_revision": 0,
        "contract_status": "draft",
        "enforcement_mode": "legacy",
        "claim_scope": "cross_dataset_method",
        "claim_target": "",
        "target_datasets": [],
        "method_eligibility": {
            "allowed_mechanism_types": ["ALGO", "CODE"],
            "forbid_evaluator_only": True,
            "same_method_formula_across_datasets": True,
            "target_labels_forbidden": True,
        },
        "parameter_transfer_policy": {
            "allowed_modes": ["shared_absolute", "shared_normalized", "dataset_calibrated"],
            "preferred_mode": "shared_normalized",
            "innovation_parameter_coverage_required": True,
            "max_load_bearing_parameters_per_calibration_group": 1,
            "min_distinct_values_per_dataset": 2,
            "max_values_per_dataset": 3,
            "seed_cardinality_per_dataset_during_parameter_coverage": 1,
            "single_value_exception_modes": ["zero_shot_only"],
            "max_refinements_per_parameter_profile": 1,
            "selection_seed_is_not_hpo": True,
            "test_outcome_forbidden": True,
            "freeze_before_claim_validation": True,
        },
        "screening_rule": {
            "minimum_required_dataset_count": 2,
            "one_fixed_seed_per_dataset": True,
            "same_seed_across_datasets": "preferred_unless_matched_baseline_passport_requires_mapping",
            "same_method_formula": True,
            "same_parameter_transfer_contract": True,
            "same_raw_parameter_value_required": False,
            "per_dataset_support_thresholds": {},
            "mechanism_readout_required": True,
        },
        "promotion_rule": {
            "max_random_seeds": 3,
            "same_seed_set_across_datasets": True,
            "matched_baseline_and_method": True,
            "dataset_aggregation": "predeclared",
            "robust_objective": "maximin_signed_delta",
            "worst_dataset_floor_by_dataset": {},
            "required_ablation_refs": [],
            "comparison_claim_ceiling": "explicit",
        },
        "search_budget": {
            "portfolio_capacity_target": 4,
            "method_portfolio_target": 2,
            "max_targeted_replenishments": 1,
            "max_moderator_children_per_contradiction": 1,
            "max_scientific_revisions_per_track": 2,
            "max_parameter_calibration_groups_before_support": 1,
            "max_parameter_probe_gpu_hours_per_track": 12.0,
            "gpu_hour_budget": 96.0,
        },
        "source_refs": [],
    }
    return bind_hash(payload)


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _positive_finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def validate_contract(payload: dict[str, Any], *, require_activatable: bool | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    for field in ["contract_id", "contract_status", "enforcement_mode", "claim_scope", "claim_target"]:
        if not str(payload.get(field) or "").strip():
            errors.append(f"{field} is required")
    status = str(payload.get("contract_status") or "").lower()
    mode = str(payload.get("enforcement_mode") or "").lower()
    scope = str(payload.get("claim_scope") or "").lower()
    if status not in VALID_STATUSES:
        errors.append("contract_status must be draft, active, or superseded")
    if mode not in VALID_MODES:
        errors.append("enforcement_mode must be legacy, shadow, or enforced")
    if scope not in VALID_SCOPES:
        errors.append("claim_scope must be dataset_specific or cross_dataset_method")

    datasets = payload.get("target_datasets")
    if not isinstance(datasets, list):
        errors.append("target_datasets must be a list")
        datasets = []
    required_rows: list[dict[str, Any]] = []
    dataset_ids: set[str] = set()
    for index, row in enumerate(datasets):
        prefix = f"target_datasets[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        dataset_id = str(row.get("dataset_id") or "").strip()
        if not dataset_id:
            errors.append(f"{prefix}.dataset_id is required")
        elif dataset_id in dataset_ids:
            errors.append(f"duplicate dataset_id: {dataset_id}")
        dataset_ids.add(dataset_id)
        role = str(row.get("role") or "").lower()
        if role not in VALID_DATASET_ROLES:
            errors.append(f"{prefix}.role must be primary, contrast, or confirmation")
        if str(row.get("metric_direction") or "").lower() not in VALID_DIRECTIONS:
            errors.append(f"{prefix}.metric_direction must be higher or lower")
        if str(row.get("paper_report_alignment") or "").lower() not in VALID_ALIGNMENTS:
            errors.append(f"{prefix}.paper_report_alignment is invalid")
        if row.get("required") is True:
            required_rows.append(row)
        if not str(row.get("canonical_metric") or "").strip():
            errors.append(f"{prefix}.canonical_metric is required")
        if not str(row.get("matched_baseline_ref") or "").strip():
            errors.append(f"{prefix}.matched_baseline_ref is required")

    if scope == "cross_dataset_method":
        if len(required_rows) < 2:
            errors.append("cross_dataset_method requires at least two required datasets")
        roles = {str(row.get("role") or "").lower() for row in required_rows}
        if "primary" not in roles or "contrast" not in roles:
            errors.append("cross_dataset_method requires primary and contrast dataset roles")

    transfer = payload.get("parameter_transfer_policy")
    if not isinstance(transfer, dict):
        errors.append("parameter_transfer_policy must be an object")
        transfer = {}
    allowed_modes = transfer.get("allowed_modes")
    if not isinstance(allowed_modes, list) or not allowed_modes:
        errors.append("parameter_transfer_policy.allowed_modes must be non-empty")
    elif set(str(value) for value in allowed_modes) - VALID_TRANSFER_MODES:
        errors.append("parameter_transfer_policy.allowed_modes contains an invalid mode")
    if transfer.get("preferred_mode") not in VALID_TRANSFER_MODES:
        errors.append("parameter_transfer_policy.preferred_mode is invalid")
    if _positive_int(transfer.get("max_load_bearing_parameters_per_calibration_group")) != 1:
        errors.append("max_load_bearing_parameters_per_calibration_group must be 1")
    if _positive_int(transfer.get("min_distinct_values_per_dataset")) != 2:
        errors.append("min_distinct_values_per_dataset must be 2")
    max_values = _positive_int(transfer.get("max_values_per_dataset"))
    if max_values is None or max_values > 3:
        errors.append("max_values_per_dataset must be between 1 and 3")
    if _positive_int(transfer.get("seed_cardinality_per_dataset_during_parameter_coverage")) != 1:
        errors.append("seed_cardinality_per_dataset_during_parameter_coverage must be 1")
    exceptions = transfer.get("single_value_exception_modes")
    if not isinstance(exceptions, list) or set(str(value) for value in exceptions) - {"zero_shot_only"}:
        errors.append("single_value_exception_modes may contain only zero_shot_only")

    promotion = payload.get("promotion_rule")
    if not isinstance(promotion, dict):
        errors.append("promotion_rule must be an object")
        promotion = {}
    max_seeds = _positive_int(promotion.get("max_random_seeds"))
    if max_seeds is None or max_seeds > 3:
        errors.append("promotion_rule.max_random_seeds must be between 1 and 3")
    if promotion.get("robust_objective") != "maximin_signed_delta":
        errors.append("promotion_rule.robust_objective must be maximin_signed_delta")
    if promotion.get("dataset_aggregation") != "predeclared":
        errors.append("promotion_rule.dataset_aggregation must be predeclared")
    floors = promotion.get("worst_dataset_floor_by_dataset")
    if not isinstance(floors, dict):
        errors.append("promotion_rule.worst_dataset_floor_by_dataset must be an object")
        floors = {}
    if status in {"active", "superseded"} or mode == "enforced" or require_activatable is True:
        for row in required_rows:
            dataset_id = str(row.get("dataset_id") or "")
            floor = floors.get(dataset_id)
            if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not math.isfinite(float(floor)):
                errors.append(
                    f"promotion_rule.worst_dataset_floor_by_dataset.{dataset_id} must be a finite number"
                )

    budget = payload.get("search_budget")
    if not isinstance(budget, dict):
        errors.append("search_budget must be an object")
        budget = {}
    capacity = _positive_int(budget.get("portfolio_capacity_target"))
    method_target = _positive_int(budget.get("method_portfolio_target"))
    if capacity is None or capacity > 4:
        errors.append("portfolio_capacity_target must be between 1 and 4")
    if method_target is None or capacity is None or method_target > capacity:
        errors.append("method_portfolio_target must be between 1 and portfolio_capacity_target")
    if _positive_int(budget.get("max_parameter_calibration_groups_before_support")) != 1:
        errors.append("max_parameter_calibration_groups_before_support must be 1")
    bounded_integer_fields = {
        "max_targeted_replenishments": 8,
        "max_moderator_children_per_contradiction": 1,
        "max_scientific_revisions_per_track": 2,
    }
    for field, maximum in bounded_integer_fields.items():
        value = _nonnegative_int(budget.get(field))
        if value is None or value > maximum:
            errors.append(f"{field} must be an integer between 0 and {maximum}")

    activatable_budget = status in {"active", "superseded"} or mode == "enforced" or require_activatable is True
    probe_budget = _positive_finite(budget.get("max_parameter_probe_gpu_hours_per_track"))
    total_budget = _positive_finite(budget.get("gpu_hour_budget"))
    if activatable_budget:
        if probe_budget is None:
            errors.append("max_parameter_probe_gpu_hours_per_track must be a positive finite number")
        if total_budget is None:
            errors.append("gpu_hour_budget must be a positive finite number")
        if probe_budget is not None and total_budget is not None and probe_budget > total_budget:
            errors.append("max_parameter_probe_gpu_hours_per_track cannot exceed gpu_hour_budget")
    elif probe_budget is None or total_budget is None:
        warnings.append("draft search budget is not activatable until finite GPU-hour caps are recorded")

    recorded_hash = str(payload.get("semantic_sha256") or "").lower()
    computed_hash = semantic_sha256(payload)
    if recorded_hash and recorded_hash != computed_hash:
        errors.append("semantic_sha256 does not match canonical content")
    elif not recorded_hash:
        warnings.append("semantic_sha256 is absent")

    activatable = status in {"active", "superseded"} or mode == "enforced"
    if require_activatable is True:
        activatable = True
    if require_activatable is False:
        activatable = False
    if activatable and scope == "cross_dataset_method" and len(required_rows) < 2:
        errors.append("active/enforced cross_dataset_method contract is not launchable")
    if status == "superseded" and mode == "enforced":
        errors.append("superseded contract cannot remain enforced")

    replacement_basis = str(payload.get("replacement_basis_decision_id") or "").strip()
    if replacement_basis:
        if not str(payload.get("unresolved_paper_decision_id") or "").strip():
            errors.append("replacement contract requires unresolved_paper_decision_id")
        source_refs = payload.get("source_refs")
        if not isinstance(source_refs, list) or not source_refs:
            errors.append("replacement contract requires source_refs for authority and review evidence")

    return {
        "complete": not errors,
        "errors": errors,
        "warnings": warnings,
        "computed_semantic_sha256": computed_hash,
        "contract_status": status,
        "enforcement_mode": mode,
        "claim_scope": scope,
        "required_dataset_count": len(required_rows),
    }


def _load_input(path: str) -> dict[str, Any]:
    return read_json(Path(path).expanduser().resolve())


def _cas_mutate(
    project: Path,
    candidate: dict[str, Any],
    *,
    action: str,
    expected_sha256: str | None,
    expected_revision: int | None,
) -> dict[str, Any]:
    path = contract_path(project)
    with contract_lock(path):
        current = read_json(path) if path.exists() else {}
        current_sha = semantic_sha256(current) if current else ""
        current_revision = int(current.get("contract_revision") or 0) if current else -1
        if expected_sha256 is not None and expected_sha256 != current_sha:
            raise ValueError(f"stale expected SHA-256: expected {expected_sha256}, observed {current_sha}")
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError(f"stale expected revision: expected {expected_revision}, observed {current_revision}")

        next_payload = dict(candidate)
        next_payload["contract_revision"] = current_revision + 1
        next_payload["updated_at"] = now()
        if not current:
            next_payload.setdefault("created_at", next_payload["updated_at"])
        else:
            next_payload.setdefault("created_at", current.get("created_at") or next_payload["updated_at"])
        next_payload = bind_hash(next_payload)
        validation = validate_contract(next_payload)
        if not validation["complete"]:
            raise ValueError("; ".join(validation["errors"]))
        replacement_authority = validate_replacement_authority(project, next_payload)
        if not replacement_authority["complete"]:
            raise ValueError("; ".join(replacement_authority["errors"]))
        if current and semantic_sha256(candidate) == current_sha:
            return {"changed": False, "contract": current, "validation": validate_contract(current)}
        atomic_write_json(path, next_payload)
        append_event(
            project / EVENTS_REL,
            {
                "ts": now(),
                "action": action,
                "prior_semantic_sha256": current_sha or None,
                "semantic_sha256": next_payload["semantic_sha256"],
                "contract_revision": next_payload["contract_revision"],
                "contract_status": next_payload.get("contract_status"),
                "enforcement_mode": next_payload.get("enforcement_mode"),
            },
        )
        return {
            "changed": True,
            "contract": next_payload,
            "validation": validation,
            "replacement_authority": replacement_authority,
        }


def cmd_template(args: argparse.Namespace) -> int:
    payload = default_contract(project_root(args.project))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    payload = _load_input(args.input) if args.input else read_json(contract_path(project))
    result = validate_contract(payload, require_activatable=args.require_activatable)
    replacement_authority = validate_replacement_authority(project, payload)
    result["replacement_authority"] = replacement_authority
    if args.require_replacement_authority and not replacement_authority["complete"]:
        result["errors"] = list(result.get("errors") or []) + list(replacement_authority["errors"])
        result["complete"] = False
    result["path"] = str(Path(args.input).expanduser().resolve() if args.input else contract_path(project))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["complete"] else 1


def cmd_show(args: argparse.Namespace) -> int:
    payload = read_json(contract_path(project_root(args.project)))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload else 1


def cmd_commit(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    candidate = _load_input(args.input)
    candidate.pop("semantic_sha256", None)
    try:
        result = _cas_mutate(
            project,
            candidate,
            action="commit",
            expected_sha256=args.expected_current_sha256,
            expected_revision=args.expected_revision,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2, ensure_ascii=False))
    return 0


def cmd_set_mode(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    current = read_json(contract_path(project))
    if not current:
        print(json.dumps({"ok": False, "error": "contract does not exist"}, indent=2))
        return 1
    candidate = dict(current)
    candidate.pop("semantic_sha256", None)
    candidate["enforcement_mode"] = args.mode
    try:
        result = _cas_mutate(
            project,
            candidate,
            action="set_mode",
            expected_sha256=args.expected_current_sha256,
            expected_revision=args.expected_revision,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2, ensure_ascii=False))
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    current = read_json(contract_path(project))
    if not current:
        print(json.dumps({"ok": False, "error": "contract does not exist"}, indent=2))
        return 1
    candidate = dict(current)
    candidate.pop("semantic_sha256", None)
    candidate["contract_status"] = "superseded"
    candidate["enforcement_mode"] = "legacy"
    candidate["superseded_reason"] = args.reason
    try:
        result = _cas_mutate(
            project,
            candidate,
            action="supersede",
            expected_sha256=args.expected_current_sha256,
            expected_revision=args.expected_revision,
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2, ensure_ascii=False))
    return 0


def _cas_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-current-sha256")
    parser.add_argument("--expected-revision", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template")
    template.add_argument("--project", required=True)
    template.set_defaults(func=cmd_template)
    check = sub.add_parser("check")
    check.add_argument("--project", required=True)
    check.add_argument("--input")
    check.add_argument("--require-activatable", action="store_true", default=None)
    check.add_argument("--require-replacement-authority", action="store_true")
    check.set_defaults(func=cmd_check)
    show = sub.add_parser("show")
    show.add_argument("--project", required=True)
    show.set_defaults(func=cmd_show)
    commit = sub.add_parser("commit")
    commit.add_argument("--project", required=True)
    commit.add_argument("--input", required=True)
    _cas_args(commit)
    commit.set_defaults(func=cmd_commit)
    set_mode = sub.add_parser("set-mode")
    set_mode.add_argument("--project", required=True)
    set_mode.add_argument("--mode", choices=sorted(VALID_MODES), required=True)
    _cas_args(set_mode)
    set_mode.set_defaults(func=cmd_set_mode)
    supersede = sub.add_parser("supersede")
    supersede.add_argument("--project", required=True)
    supersede.add_argument("--reason", required=True)
    _cas_args(supersede)
    supersede.set_defaults(func=cmd_supersede)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
