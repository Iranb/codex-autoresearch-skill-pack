#!/usr/bin/env python3
"""Materialize INNOVATION_PACKET and EXPERIMENT_REVIEW_PACKET from a selected idea."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hpo_policy_lint import default_hpo_search_policy


EXTERNAL_GATE_SCRIPT_DIR = (
    Path(__file__).resolve().parents[2] / "autoreskill-gpu-idea-validation/scripts"
)
if str(EXTERNAL_GATE_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_GATE_SCRIPT_DIR))

WORKFLOW_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "autoreskill-workflow/scripts"
if str(WORKFLOW_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_SCRIPT_DIR))

from external_gate_commit import (  # noqa: E402
    ExternalGateError,
    load_external_gate_commit,
    load_gate_source_mode,
    require_same_external_gate_commit,
)
from parameter_transfer import (  # noqa: E402
    program_contract_binding,
    required_dataset_ids,
    stable_hash,
    validate_frozen_profile,
    validate_parameter_transfer_contract,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_passport_binding(base: Path, idea: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    passport = read_json(base / "resources/PROJECT_EXECUTION_PASSPORT.json", {})
    if not isinstance(passport, dict) or not passport:
        return {}
    requested = str(protocol.get("execution_profile_id") or idea.get("execution_profile_id") or "default").strip()
    profiles = [item for item in passport.get("execution_profiles", []) if isinstance(item, dict)]
    profile = next((item for item in profiles if str(item.get("profile_id") or "") == requested), None)
    if profile is None and len(profiles) == 1:
        profile = profiles[0]
    if profile is None:
        raise SystemExit(f"project execution passport has no profile {requested!r}")
    return {
        "project_execution_passport_ref": "resources/PROJECT_EXECUTION_PASSPORT.json",
        "project_execution_passport_index_sha256": passport.get("index_semantic_sha256"),
        "execution_profile_id": profile.get("profile_id"),
        "execution_profile_sha256": profile.get("execution_profile_sha256"),
    }


def default_validation_ladder(dataset: str, metric: str, gpu_hours: float) -> list[dict[str, Any]]:
    stages = [
        (0, "static_identity_and_path_checks", [], "diagnostic_only", 0.0),
        (1, "smoke_or_tiny_batch_overfit", ["stage_0_pass"], "readiness_only", min(gpu_hours, 0.1) if gpu_hours > 0 else 0.0),
        (2, "smallest_valid_dataset_single_seed", ["stage_1_pass"], "pilot_only", gpu_hours),
        (3, "full_budget_single_seed_matched_control", ["stage_2_support_or_ambiguity"], "initial_mechanism_support", gpu_hours),
        (4, "second_target_dataset", ["stage_3_initial_support"], "dataset_scoped_support", gpu_hours),
        (5, "bounded_dehb_and_required_ablation", ["stage_3_support_or_ambiguity", "stage_4_or_equivalent_cross_dataset_evidence"], "search_evidence_only", gpu_hours),
        (6, "paired_seed_stability", ["frozen_matched_baseline", "promotion_candidate"], "claim_promotion_candidate", gpu_hours * 3 if gpu_hours > 0 else 0.0),
        (7, "bounded_supported_component_combination", ["independently_supported_components"], "bounded_combination_evidence", gpu_hours),
    ]
    return [
        {
            "stage": stage,
            "name": name,
            "prerequisites": prerequisites,
            "decision_targets": [f"{dataset}:{metric}:stage-{stage}"],
            "claim_ceiling": ceiling,
            "estimated_gpu_hours": cost,
            "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
            "stop_condition": "stop on protocol invalidity or the stage-declared scientific falsifier",
        }
        for stage, name, prerequisites, ceiling, cost in stages
    ]


def semantic_packet(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"created_at", "generated_at", "semantic_sha256"}
    }


def bind_semantic_sha256(payload: dict[str, Any]) -> dict[str, Any]:
    payload["semantic_sha256"] = canonical_sha256(semantic_packet(payload))
    return payload


def write_json_if_changed(path: Path, payload: dict[str, Any]) -> bool:
    bind_semantic_sha256(payload)
    current = read_json(path, {})
    if isinstance(current, dict) and current.get("semantic_sha256") == payload["semantic_sha256"]:
        return False
    write_json(path, payload)
    return True


def write_text_if_changed(path: Path, value: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == value:
        return False
    write_text(path, value)
    return True


def json_would_change(path: Path, payload: dict[str, Any]) -> bool:
    current = read_json(path, {})
    return not (
        isinstance(current, dict)
        and current.get("semantic_sha256") == payload.get("semantic_sha256")
    )


def text_would_change(path: Path, value: str) -> bool:
    return not path.exists() or path.read_text(encoding="utf-8") != value


def migration_stale_rows(base: Path, admitted_track_ids: set[str], selection_fingerprint: str) -> list[str]:
    queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {})
    rows = queue.get("rows") if isinstance(queue, dict) else []
    if not isinstance(rows, list):
        return []
    stale: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in {"terminal_positive", "terminal_negative", "dropped", "superseded"}:
            continue
        track_id = str(row.get("track_id") or "").strip()
        row_selection = str(row.get("selection_fingerprint") or row.get("selected_primary_ref") or "").strip()
        if (track_id and track_id not in admitted_track_ids) or (
            row_selection and selection_fingerprint and row_selection != selection_fingerprint
        ):
            row_id = str(row.get("id") or "").strip()
            if row_id:
                stale.append(row_id)
    return sorted(set(stale))


def first_candidate(pool: Any) -> dict[str, Any]:
    rows = []
    if isinstance(pool, dict):
        for key in ["candidates", "tracks", "ideas"]:
            if isinstance(pool.get(key), list):
                rows = pool[key]
                break
    elif isinstance(pool, list):
        rows = pool
    for row in rows:
        if isinstance(row, dict) and str(row.get("status") or row.get("verdict") or "").lower() in {"advance", "advance_with_constraints"}:
            return row
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def idea_rows(pool: Any) -> list[dict[str, Any]]:
    if not isinstance(pool, dict):
        return []
    for key in ["ideas", "candidates", "tracks"]:
        rows = pool.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def selected_idea_from_pool(pool: Any, idea_id: str | None = None) -> dict[str, Any]:
    if not isinstance(pool, dict):
        return {}
    ideas = idea_rows(pool)
    if not ideas:
        return {}
    selected_id = str(idea_id or pool.get("selected_idea_id") or pool.get("selected_candidate_id") or "").strip()
    for row in ideas:
        if isinstance(row, dict) and selected_id and str(row.get("id") or "").strip() == selected_id:
            return row
    for row in ideas:
        if isinstance(row, dict) and str(row.get("status") or "").lower() == "selected":
            return row
    return {}


def payload_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in ["decisions", "tracks", "rows", "ideas"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def selection_ref(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("selection_fingerprint") or payload.get("selected_primary_ref") or "").strip()


def seed_semantic_sha256(seeds: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in seeds.items()
        if key not in {"generated_at", "semantic_sha256"}
    }
    return canonical_sha256(stable)


def decision_for_idea(ledger: dict[str, Any], idea_id: str) -> dict[str, Any]:
    matches = [row for row in payload_rows(ledger) if str(row.get("idea_id") or "").strip() == idea_id]
    if len(matches) > 1:
        raise SystemExit(f"idea decision ledger contains duplicate decisions for {idea_id}")
    return matches[0] if matches else {}


def inferred_lifecycle(seed: dict[str, Any]) -> str:
    return {
        "primary": "selected_primary",
        "alternate": "alternate_track",
        "risk_repair": "risk_repair_track",
    }.get(str(seed.get("track_role") or "").strip().lower(), "")


def admitted_lifecycle(value: Any) -> bool:
    return str(value or "").strip().lower() in {
        "selected_primary",
        "alternate_track",
        "risk_repair_track",
        "advance_with_constraints",
        "alternate",  # schema-v2 compatibility
    }


def locked_protocol(pool: Any) -> dict[str, Any]:
    if isinstance(pool, dict) and isinstance(pool.get("locked_protocol"), dict):
        return pool["locked_protocol"]
    return {}


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def source_mode(base: Path) -> tuple[str, dict[str, Any]]:
    return load_gate_source_mode(base)


def candidate_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    for key in ["candidates", "idea_candidates", "admitted_candidates"]:
        rows = value.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def external_candidate(campaign: Any, candidate_id: str) -> dict[str, Any]:
    for row in candidate_rows(campaign):
        row_id = row.get("external_candidate_id") or row.get("candidate_id") or row.get("id")
        if present(row_id) and str(row_id) == candidate_id:
            return row
    return {}


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def jsonish_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def selected_paper_contributions(idea: dict[str, Any]) -> tuple[Any, list[Any], list[Any], dict[str, Any]]:
    paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
    core = (
        idea.get("core_scientific_contribution")
        or paper.get("core_scientific_contribution")
        or paper.get("paper_thesis")
        or idea.get("paper_thesis")
    )
    supporting = idea.get("supporting_contributions") or paper.get("supporting_contributions") or []
    # Legacy bundle keys are read-only migration inputs; they do not impose a contribution count.
    bundle = (
        idea.get("paper_innovation_bundle")
        or idea.get("innovation_bundle")
        or idea.get("three_innovation_bundle")
        or paper.get("innovation_bundle")
        or paper.get("innovation_points")
    )
    storyline = (
        idea.get("paper_storyline")
        or idea.get("storyline")
        or paper.get("storyline")
        or paper.get("paper_storyline")
    )

    core_out = jsonish_copy(core) if isinstance(core, (dict, list)) else core
    supporting_out = jsonish_copy(supporting) if isinstance(supporting, list) else []
    bundle_out = jsonish_copy(bundle) if isinstance(bundle, list) else []
    storyline_out = jsonish_copy(storyline) if isinstance(storyline, dict) else {}
    thesis = paper.get("paper_thesis") or idea.get("paper_thesis") or idea.get("thesis")
    if present(thesis) and isinstance(storyline_out, dict) and not present(storyline_out.get("paper_thesis")):
        storyline_out["paper_thesis"] = thesis
    return core_out, supporting_out, bundle_out, storyline_out


def choose(cli_value: str, default_value: str, fallback: Any) -> Any:
    if cli_value != default_value:
        return cli_value
    return fallback if fallback not in (None, "", [], {}) else default_value


def default_dataset_runtime_plan(dataset: str, gpu_hours: float, walltime_hours: float) -> dict[str, Any]:
    walltime = walltime_hours if walltime_hours > 0 else 1.0
    gpu = gpu_hours if gpu_hours > 0 else walltime
    return {
        "candidate_datasets": [
            {
                "dataset_id": dataset,
                "scale_class": "small_multiclass",
                "num_classes": "estimate_required",
                "train_samples": "estimate_required",
                "eval_samples": "estimate_required",
                "epochs_or_steps": "estimate_required",
                "estimated_minutes_per_epoch": round(max(walltime * 60.0, 1.0), 3),
                "estimated_walltime_hours": walltime,
                "estimated_gpu_hours": gpu,
                "estimation_basis": "placeholder from materialize; replace with dataset counts, epoch count, batch size, backend GPU probe, and prior logs before launch",
                "purpose": "feasibility_first",
            }
        ],
        "feasibility_first_dataset_id": dataset,
        "first_run_scale_class": "small_multiclass",
        "largest_dataset_id": dataset,
        "largest_dataset_deferred": True,
        "escalation_criteria": [
            "smoke run passes",
            "metric parser and data split are verified",
            "innovation mechanism shows non-degenerate behavior on the feasibility dataset",
        ],
        "runtime_risk": "Replace placeholder estimates before launch; largest dataset remains deferred for confirmation/final-scale evidence.",
    }


def default_dataset_requirement_inventory(dataset: str) -> dict[str, Any]:
    return {
        "required_datasets": [
            {
                "dataset_id": dataset,
                "dataset_name": dataset,
                "claim_role": "method_validation",
                "reason_required": "placeholder from materialize; replace with a full dataset inventory from baseline scripts, evidence, benchmark norms, and selected claim before launch",
                "baseline_supported": "probe_required",
                "availability": "unknown",
                "scale_class": "small_multiclass",
                "num_classes": "estimate_required",
                "train_samples": "estimate_required",
                "eval_samples": "estimate_required",
                "native_protocol_ref": "probe_required",
                "native_epochs_or_steps": "probe_required",
                "native_warmup_or_schedule": "probe_required",
                "data_root_or_probe": "probe_required",
                "selection_status": "selected_first",
            }
        ],
        "selection_rule": "choose_smallest_available_baseline_supported_required_dataset_for_method_validation",
        "method_validation_dataset_id": dataset,
        "smallest_available_required_dataset_id": dataset,
        "deferred_dataset_ids": [],
        "rejected_datasets": [],
    }


def dataset_group_plan_from_contract(program: dict[str, Any]) -> dict[str, Any]:
    rows = program.get("target_datasets") if isinstance(program, dict) else None
    if not isinstance(rows, list):
        return {}
    required_rows = [row for row in rows if isinstance(row, dict) and row.get("required") is True]
    if not required_rows:
        return {}
    return {
        "required_dataset_ids": [str(row.get("dataset_id")) for row in required_rows],
        "dataset_roles": {
            str(row.get("dataset_id")): str(row.get("role")) for row in required_rows
        },
        "baseline_ref_by_dataset": {
            str(row.get("dataset_id")): row.get("matched_baseline_ref") for row in required_rows
        },
        "canonical_metric_by_dataset": {
            str(row.get("dataset_id")): row.get("canonical_metric") for row in required_rows
        },
        "full_budget_parallel_safe": True,
    }


def normalized_parameter_contract(value: Any, datasets: list[str], track_id: str = "") -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}
    contract = jsonish_copy(value)
    contract.setdefault("parameter_role", "innovation_load_bearing")
    contract.setdefault("load_bearing", True)
    contract.setdefault("innovation_parameter_coverage_required", True)
    contract.setdefault("minimum_distinct_values_per_dataset", 2)
    contract.setdefault("max_values_per_dataset", 3)
    contract.setdefault("dataset_specific_ranges_allowed", True)
    contract.setdefault("identical_ranges_require_scale_comparability", True)
    contract.setdefault("single_value_exception", "none")
    contract.setdefault("seed_cardinality_per_dataset_during_parameter_coverage", 1)
    contract.setdefault("test_outcome_forbidden", True)
    contract.setdefault("selection_seed_by_dataset", {})
    contract.setdefault("candidate_values_by_dataset", {})
    contract.setdefault("value_basis_by_dataset", {})
    contract.setdefault("required_dataset_ids", datasets)
    contract.setdefault("parameter_calibration_group_id", f"parameter-{track_id}-r1" if track_id else "")
    contract.setdefault("parameter_probe_kind", "bounded_calibration")
    contract.pop("parameter_transfer_contract_sha256", None)
    contract["parameter_transfer_contract_sha256"] = stable_hash(contract)
    return contract


def freeze_parameter_profile(base: Path, track_id: str, group_id: str) -> dict[str, Any]:
    review_path = base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json"
    review = read_json(review_path, {})
    if not isinstance(review, dict) or not review:
        raise SystemExit(f"missing review packet for {track_id}")
    contract = review.get("parameter_transfer_contract")
    if not isinstance(contract, dict):
        raise SystemExit("review packet has no parameter_transfer_contract")
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {})
    decisions = ledger.get("calibration_decisions") if isinstance(ledger, dict) else None
    matches = [
        row for row in (decisions or [])
        if isinstance(row, dict)
        and str(row.get("track_id") or "") == track_id
        and str(row.get("parameter_calibration_group_id") or "") == group_id
    ]
    if len(matches) != 1:
        raise SystemExit("freeze requires exactly one ledger calibration decision for the track/group")
    decision = matches[0]
    expected_contract_hash = str(contract.get("parameter_transfer_contract_sha256") or "")
    if str(decision.get("parameter_transfer_contract_sha256") or "") != expected_contract_hash:
        raise SystemExit("ledger calibration decision is stale for the review packet")
    profile = {
        "schema_version": 1,
        "parameter_profile_status": "frozen",
        "track_id": track_id,
        "parameter_calibration_group_id": group_id,
        "parameter_name": contract.get("parameter_name"),
        "transfer_mode": contract.get("transfer_mode"),
        "shared_formula": contract.get("shared_formula"),
        "normalization_or_calibration_statistic": contract.get("normalization_or_calibration_statistic"),
        "selected_setting_by_dataset": decision.get("selected_setting_by_dataset"),
        "realized_value_by_dataset": decision.get("realized_value_by_dataset"),
        "parameter_transfer_contract_sha256": expected_contract_hash,
        "calibration_decision_ref": f"ideation/IDEA_DECISION_LEDGER.json#calibration_decisions/{decision.get('decision_id')}",
        "calibration_decision_sha256": decision.get("decision_sha256"),
        "selection_evidence_sha256": decision.get("selection_evidence_sha256"),
        "source_evidence_refs": decision.get("source_evidence_refs") or [],
        "claim_ceiling": decision.get("claim_ceiling"),
        "generated_at": now(),
    }
    profile["frozen_parameter_profile_sha256"] = stable_hash(profile)
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {})
    datasets = required_dataset_ids(program if isinstance(program, dict) else {}, review)
    validation = validate_frozen_profile(profile, contract, datasets)
    if not validation["complete"]:
        raise SystemExit("invalid frozen profile: " + "; ".join(validation.get("errors") or []))
    profile_ref = f"planner/tracks/{track_id}/FROZEN_PARAMETER_PROFILE.json"
    profile_path = base / profile_ref
    existing = read_json(profile_path, {})
    if isinstance(existing, dict) and existing:
        existing_hash = str(existing.get("frozen_parameter_profile_sha256") or "")
        if existing_hash and existing_hash != profile["frozen_parameter_profile_sha256"]:
            raise SystemExit("a different frozen parameter profile already exists; create a reviewed profile revision")
    changed = not isinstance(existing, dict) or existing.get("frozen_parameter_profile_sha256") != profile["frozen_parameter_profile_sha256"]
    if changed:
        write_json(profile_path, profile)

    review["parameter_profile_status"] = "frozen"
    review["stage2_role"] = "stage2_method_screen"
    review["frozen_parameter_profile_ref"] = profile_ref
    review["frozen_parameter_profile_sha256"] = profile["frozen_parameter_profile_sha256"]
    review_changed = write_json_if_changed(review_path, review)
    primary_path = base / "planner/EXPERIMENT_REVIEW_PACKET.json"
    primary = read_json(primary_path, {})
    if isinstance(primary, dict) and str(primary.get("track_id") or "") == track_id:
        primary.update(
            {
                "parameter_profile_status": "frozen",
                "stage2_role": "stage2_method_screen",
                "frozen_parameter_profile_ref": profile_ref,
                "frozen_parameter_profile_sha256": profile["frozen_parameter_profile_sha256"],
            }
        )
        write_json_if_changed(primary_path, primary)
    if changed or review_changed:
        append_jsonl(
            base / "decision_log.jsonl",
            {
                "ts": now(),
                "stage": "experiment_plan",
                "action": "freeze_parameter_profile_projection",
                "details": {
                    "track_id": track_id,
                    "parameter_calibration_group_id": group_id,
                    "calibration_decision_id": decision.get("decision_id"),
                    "frozen_parameter_profile_sha256": profile["frozen_parameter_profile_sha256"],
                },
            },
        )
    return {
        "ok": True,
        "changed": changed or review_changed,
        "track_id": track_id,
        "parameter_calibration_group_id": group_id,
        "profile_ref": profile_ref,
        "frozen_parameter_profile_sha256": profile["frozen_parameter_profile_sha256"],
        "calibration_decision_id": decision.get("decision_id"),
    }


def preserve_frozen_parameter_profile(
    base: Path,
    track_id: str,
    review: dict[str, Any],
    innovation: dict[str, Any],
) -> None:
    """Carry a valid frozen projection forward across idempotent rematerialization."""

    existing_path = base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json"
    existing = read_json(existing_path, {})
    if not isinstance(existing, dict) or existing.get("parameter_profile_status") != "frozen":
        return
    existing_contract = existing.get("parameter_transfer_contract")
    new_contract = review.get("parameter_transfer_contract")
    if not isinstance(existing_contract, dict) or not isinstance(new_contract, dict):
        raise SystemExit("frozen parameter profile cannot be rematerialized without its transfer contract")
    existing_contract_hash = str(existing_contract.get("parameter_transfer_contract_sha256") or "")
    new_contract_hash = str(new_contract.get("parameter_transfer_contract_sha256") or "")
    if not existing_contract_hash or existing_contract_hash != new_contract_hash:
        raise SystemExit(
            "parameter transfer contract changed after profile freeze; create an explicit reviewed profile revision"
        )
    profile_ref = str(existing.get("frozen_parameter_profile_ref") or "").strip()
    profile_hash = str(existing.get("frozen_parameter_profile_sha256") or "").strip()
    profile_path = base / profile_ref if profile_ref else None
    profile = read_json(profile_path, {}) if profile_path is not None else {}
    datasets = required_dataset_ids(
        read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}),
        review,
    )
    validation = validate_frozen_profile(profile, new_contract, datasets)
    if not profile_ref or not profile_hash or profile_hash != profile.get("frozen_parameter_profile_sha256"):
        raise SystemExit("frozen parameter profile reference/hash is missing or stale")
    if not validation["complete"]:
        raise SystemExit("frozen parameter profile is invalid: " + "; ".join(validation.get("errors") or []))
    projection = {
        "parameter_profile_status": "frozen",
        "stage2_role": "stage2_method_screen",
        "frozen_parameter_profile_ref": profile_ref,
        "frozen_parameter_profile_sha256": profile_hash,
    }
    review.update(projection)
    innovation.update(projection)


def selected_mechanism_type(idea: dict[str, Any], pool_candidate: dict[str, Any], protocol: dict[str, Any]) -> str:
    contract = idea.get("innovation_search_contract") if isinstance(idea.get("innovation_search_contract"), dict) else {}
    for value in [
        contract.get("mechanism_type"),
        idea.get("mechanism_type"),
        idea.get("type"),
        pool_candidate.get("mechanism_type"),
        pool_candidate.get("type"),
        protocol.get("mechanism_type"),
    ]:
        text = str(value or "").strip().upper()
        if text in {"ALGO", "CODE", "PARAM"}:
            return text
    return "ALGO"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--track-id")
    selector.add_argument("--all-admitted", action="store_true")
    parser.add_argument("--baseline", default="baseline_protocol")
    parser.add_argument("--metric", default="primary_metric")
    parser.add_argument("--dataset", default="target_dataset")
    parser.add_argument("--gpu-hours", type=float, default=0)
    parser.add_argument("--walltime-hours", type=float, default=1)
    parser.add_argument("--allow-fixture", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--freeze-parameter-profile", action="store_true")
    parser.add_argument("--parameter-calibration-group-id")
    args = parser.parse_args()

    base = ar(args.project)
    program_contract = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {})
    if not isinstance(program_contract, dict):
        program_contract = {}
    program_binding = program_contract_binding(program_contract)
    program_mode = str(program_contract.get("enforcement_mode") or "legacy").strip().lower()
    program_scope = str(program_contract.get("claim_scope") or "dataset_specific").strip().lower()
    if args.freeze_parameter_profile:
        if not args.track_id or not args.parameter_calibration_group_id:
            raise SystemExit("--freeze-parameter-profile requires --track-id and --parameter-calibration-group-id")
        if args.dry_run:
            raise SystemExit("profile projection dry-run uses research_decision.py --check before this write step")
        print(
            json.dumps(
                freeze_parameter_profile(base, args.track_id, args.parameter_calibration_group_id),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    seed_path = base / "ideation/IDEA_TRACK_SEEDS.json"
    seeds = read_json(seed_path, {})
    if args.all_admitted:
        if not isinstance(seeds, dict) or not payload_rows(seeds):
            raise SystemExit("--all-admitted requires ideation/IDEA_TRACK_SEEDS.json")
        ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {})
        admitted: list[dict[str, Any]] = []
        for seed in payload_rows(seeds):
            idea_id = str(seed.get("idea_id") or "").strip()
            decision = decision_for_idea(ledger, idea_id) if isinstance(ledger, dict) else {}
            lifecycle = decision.get("lifecycle_status") or inferred_lifecycle(seed)
            if admitted_lifecycle(lifecycle):
                admitted.append(seed)
        admitted.sort(key=lambda row: str(row.get("track_id") or ""))
        if not admitted:
            raise SystemExit("--all-admitted found no nonterminal admitted track")
        results: list[dict[str, Any]] = []
        for seed in admitted:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--project",
                args.project,
                "--track-id",
                str(seed.get("track_id")),
                "--baseline",
                args.baseline,
                "--metric",
                args.metric,
                "--dataset",
                args.dataset,
                "--gpu-hours",
                str(args.gpu_hours),
                "--walltime-hours",
                str(args.walltime_hours),
            ]
            if args.allow_fixture:
                command.append("--allow-fixture")
            if args.dry_run:
                command.append("--dry-run")
            completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if completed.returncode != 0:
                raise SystemExit(
                    f"failed to materialize track {seed.get('track_id')}: {completed.stderr.strip() or completed.stdout.strip()}"
                )
            results.append(json.loads(completed.stdout))
        admitted_tracks = [
            {
                "track_id": result.get("track_id"),
                "idea_id": result.get("idea_id"),
                "track_role": result.get("track_role"),
                "evidence_tier_ceiling": result.get("evidence_tier_ceiling"),
            }
            for result in results
        ]
        admitted_track_ids = {
            str(item.get("track_id") or "").strip()
            for item in admitted_tracks
            if str(item.get("track_id") or "").strip()
        }
        current_selection = selection_ref(ledger)
        missing_packet_refs = sorted(
            {
                str(ref)
                for result in results
                for ref in result.get("missing_packet_refs", [])
                if str(ref).strip()
            }
        )
        files_that_would_be_written = sorted(
            {
                str(ref)
                for result in results
                for ref in result.get("files_that_would_be_written", [])
                if str(ref).strip()
            }
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": args.dry_run,
                    "track_count": len(results),
                    "tracks": results,
                    "migration_report": {
                        "admitted_tracks": admitted_tracks,
                        "missing_packet_refs": missing_packet_refs,
                        "rows_that_would_become_eligible": sorted(admitted_track_ids),
                        "stale_rows": migration_stale_rows(base, admitted_track_ids, current_selection),
                        "files_that_would_be_written": files_that_would_be_written,
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    try:
        evidence_mode, gate = source_mode(base)
    except ExternalGateError as exc:
        raise SystemExit(f"external_gate_invalid: {exc}") from exc
    if evidence_mode not in {"papernexus", "external_material"}:
        raise SystemExit("PRE_IDEA_EVIDENCE_GATE.evidence_source_mode must be papernexus or external_material")
    external_mode = evidence_mode == "external_material"
    external_commit = None
    if external_mode:
        try:
            external_commit = load_external_gate_commit(base)
        except ExternalGateError as exc:
            raise SystemExit(f"external_gate_invalid: {exc}") from exc
        gate = external_commit["gate"]
        campaign_ref = external_commit["campaign_ref"]
        campaign = external_commit["campaign"]
        lint_ref = external_commit["lint_ref"]
    else:
        campaign_ref = ""
        campaign = {}
        lint_ref = ""
    pool = read_json(base / "ideation/CANDIDATE_POOL.json", {})
    idea_pool_path = "ideation/EXPERIMENT_IDEA_POOL.json"
    legacy_planner_idea_pool_path = "planner/EXPERIMENT_IDEA_POOL.json"
    legacy_candidate_library_path = "planner/EXPERIMENT_CANDIDATE_LIBRARY.json"
    idea_pool = read_json(base / idea_pool_path, {})
    if not idea_pool:
        idea_pool_path = legacy_planner_idea_pool_path
        idea_pool = read_json(base / idea_pool_path, {})
    if not idea_pool:
        idea_pool_path = legacy_candidate_library_path
        idea_pool = read_json(base / idea_pool_path, {})
    pool_candidate = first_candidate(pool)
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {})
    seed_rows = payload_rows(seeds) if isinstance(seeds, dict) else []
    seed: dict[str, Any] = {}
    if args.track_id:
        matches = [row for row in seed_rows if str(row.get("track_id") or "").strip() == args.track_id]
        if len(matches) != 1:
            raise SystemExit(f"--track-id must resolve exactly one IDEA_TRACK_SEEDS row: {args.track_id}")
        seed = matches[0]
    elif seed_rows:
        primary_idea_id = str(
            (ledger.get("selected_primary_idea_id") if isinstance(ledger, dict) else None)
            or seeds.get("selected_primary_idea_id")
            or idea_pool.get("selected_idea_id")
            or ""
        ).strip()
        matches = [
            row
            for row in seed_rows
            if str(row.get("track_role") or "").strip().lower() == "primary"
            and (not primary_idea_id or str(row.get("idea_id") or "").strip() == primary_idea_id)
        ]
        if len(matches) != 1:
            raise SystemExit("current primary must resolve exactly one IDEA_TRACK_SEEDS row")
        seed = matches[0]

    if seed:
        seed_idea_id = str(seed.get("idea_id") or "").strip()
        track_id = str(seed.get("track_id") or "").strip()
        idea = selected_idea_from_pool(idea_pool, seed_idea_id)
        if not idea:
            raise SystemExit(f"track {track_id} references idea {seed_idea_id!r}, absent from {idea_pool_path}")
        selected_idea_id = str(idea.get("id") or idea.get("idea_id") or "").strip()
        if selected_idea_id != seed_idea_id:
            raise SystemExit(f"track {track_id} idea identity mismatch: seed={seed_idea_id}, pool={selected_idea_id}")
        decision = decision_for_idea(ledger, selected_idea_id) if isinstance(ledger, dict) else {}
        lifecycle = str(decision.get("lifecycle_status") or inferred_lifecycle(seed)).strip().lower()
        if not admitted_lifecycle(lifecycle):
            raise SystemExit(f"track {track_id} is not admitted: lifecycle_status={lifecycle or '<missing>'}")
        track_role = str(seed.get("track_role") or "").strip().lower()
        if track_role not in {"primary", "alternate", "risk_repair"}:
            raise SystemExit(f"track {track_id} has unsupported track_role={track_role!r}")
        selected_primary_id = str(
            (ledger.get("selected_primary_idea_id") if isinstance(ledger, dict) else None)
            or (seeds.get("selected_primary_idea_id") if isinstance(seeds, dict) else None)
            or idea_pool.get("selected_idea_id")
            or ""
        ).strip()
        if track_role == "primary" and selected_primary_id and selected_idea_id != selected_primary_id:
            raise SystemExit(
                f"primary track {track_id} must reference selected primary idea {selected_primary_id}, not {selected_idea_id}"
            )
        if track_role != "primary" and selected_primary_id and selected_idea_id == selected_primary_id:
            raise SystemExit(f"non-primary track {track_id} cannot relabel the selected primary idea")
        allowed_lifecycle_by_role = {
            "primary": {"selected_primary"},
            "alternate": {"alternate_track", "alternate", "advance_with_constraints"},
            "risk_repair": {"risk_repair_track", "advance_with_constraints"},
        }
        if lifecycle not in allowed_lifecycle_by_role[track_role]:
            raise SystemExit(
                f"track {track_id} role/lifecycle mismatch: track_role={track_role}, lifecycle_status={lifecycle}"
            )
        decision_track_id = str(decision.get("track_id") or "").strip()
        if decision_track_id and decision_track_id != track_id:
            raise SystemExit(
                f"track {track_id} conflicts with decision-ledger track_id={decision_track_id}"
            )
    else:
        idea = selected_idea_from_pool(idea_pool) or pool_candidate
        track_id = str(args.track_id or idea.get("track_id") or pool_candidate.get("track_id") or "track_001")
        selected_idea_id = str(idea.get("id") or idea.get("idea_id") or idea.get("candidate_id") or track_id)
        decision = decision_for_idea(ledger, selected_idea_id) if isinstance(ledger, dict) else {}
        lifecycle = str(decision.get("lifecycle_status") or "selected_primary").strip().lower()
        track_role = "primary"

    seed_sha = seed_semantic_sha256(seeds) if isinstance(seeds, dict) and seeds else ""
    recorded_seed_sha = str(seeds.get("semantic_sha256") or "").strip().lower() if isinstance(seeds, dict) else ""
    if recorded_seed_sha and recorded_seed_sha != seed_sha:
        raise SystemExit("IDEA_TRACK_SEEDS semantic_sha256 does not match current canonical content")
    primary_idea_id = str(
        (ledger.get("selected_primary_idea_id") if isinstance(ledger, dict) else None)
        or (seeds.get("selected_primary_idea_id") if isinstance(seeds, dict) else None)
        or idea_pool.get("selected_idea_id")
        or selected_idea_id
    ).strip()
    primary_track_id = str(
        (ledger.get("selected_track_id") if isinstance(ledger, dict) else None)
        or next(
            (
                row.get("track_id")
                for row in seed_rows
                if str(row.get("track_role") or "").strip().lower() == "primary"
            ),
            track_id,
        )
    ).strip()
    selection_fingerprint = (
        selection_ref(ledger)
        or selection_ref(decision)
        or f"{primary_idea_id}/{primary_track_id}/unversioned"
    )
    evidence_tier_ceiling = "claim_eligible_after_gates" if track_role == "primary" else "pilot_only"
    idea_decision_ref = str(
        decision.get("decision_id")
        or decision.get("id")
        or decision.get("ref")
        or f"idea-decision-{selected_idea_id}-{lifecycle}"
    )
    protocol = locked_protocol(idea_pool)
    external_candidate_id = str(
        seed.get("external_candidate_id")
        or idea.get("external_candidate_id")
        or pool_candidate.get("external_candidate_id")
        or ""
    ).strip()
    campaign_candidate = external_candidate(campaign, external_candidate_id) if external_mode else {}
    if external_mode and external_candidate_id not in external_commit["admitted_candidate_ids"]:
        raise SystemExit(
            "external_gate_invalid: selected external_candidate_id is not admitted by the committed campaign"
        )
    if external_mode and seed:
        for field in ["external_campaign_ref", "external_campaign_sha256", "external_candidate_id"]:
            expected = seed.get(field)
            observed = idea.get(field) or campaign_candidate.get(field)
            if present(expected) and present(observed) and expected != observed:
                raise SystemExit(f"protected external identity drift for {field}: seed and selected idea/campaign differ")
    protected_commitments = (
        campaign_candidate.get("protected_commitments")
        if isinstance(campaign_candidate.get("protected_commitments"), dict)
        else {}
    )
    protected_commitment_sha256 = str(
        campaign_candidate.get("protected_commitment_sha256")
        or campaign_candidate.get("protected_commitments_sha256")
        or protected_commitments.get("sha256")
        or ""
    ).strip().lower()
    rapid_validation = (
        campaign_candidate.get("rapid_validation")
        if external_mode and isinstance(campaign_candidate.get("rapid_validation"), dict)
        else {}
    )
    resource_request = (
        rapid_validation.get("resource_request")
        if isinstance(rapid_validation.get("resource_request"), dict)
        else {}
    )
    rapid_dataset = rapid_validation.get("dataset") if isinstance(rapid_validation.get("dataset"), dict) else {}
    rapid_metric = rapid_validation.get("metric_policy") if isinstance(rapid_validation.get("metric_policy"), dict) else {}
    if external_mode:
        evidence_ids = (
            idea.get("evidence_ids")
            or idea.get("source_evidence_refs")
            or idea.get("source_refs")
            or campaign_candidate.get("evidence_ids")
            or campaign_candidate.get("source_evidence_refs")
            or campaign_candidate.get("source_refs")
            or campaign_candidate.get("material_refs")
            or []
        )
    else:
        evidence_ids = idea.get("paperNexus_evidence_ids") or idea.get("evidence_ids") or pool_candidate.get("evidence_ids") or []
    if not evidence_ids and not args.allow_fixture:
        raise SystemExit("cannot materialize experiment plan without idea evidence_ids")
    selected_fragment_id = (
        idea.get("selected_idea_fragment_id")
        or idea.get("idea_fragment_id")
        or selected_idea_id
    )
    if external_mode:
        if not external_candidate_id:
            raise SystemExit("external_material plan requires selected idea external_candidate_id")
        if external_candidate_id in {str(selected_fragment_id), str(track_id)}:
            raise SystemExit("external_candidate_id, selected_idea_fragment_id, and track_id must remain distinct")
        if len(protected_commitment_sha256) != 64 or any(char not in "0123456789abcdef" for char in protected_commitment_sha256):
            raise SystemExit("external_material plan requires the candidate protected commitment SHA-256")
    rapid_baseline_code = rapid_validation.get("baseline_code") if isinstance(rapid_validation.get("baseline_code"), dict) else {}
    rapid_baseline_ref = rapid_baseline_code.get("source_ref") or rapid_baseline_code.get("resolved_path")
    baseline = choose(
        args.baseline,
        "baseline_protocol",
        protocol.get("baseline_reference") or protocol.get("baseline_training_protocol") or rapid_baseline_ref,
    )
    rapid_dataset_name = rapid_dataset.get("name") or rapid_dataset.get("dataset_id")
    dataset = choose(args.dataset, "target_dataset", protocol.get("dataset") or rapid_dataset_name)
    data_split = protocol.get("data_split") or rapid_dataset.get("split") or "locked split required before launch"
    primary_metric = choose(args.metric, "primary_metric", protocol.get("primary_metric") or rapid_metric.get("primary_metric"))
    metric_direction = protocol.get("metric_direction") or rapid_metric.get("direction") or "higher"
    mechanism_type = selected_mechanism_type(idea, pool_candidate, protocol)
    claim_role = str(
        seed.get("claim_role")
        or idea.get("claim_role")
        or protocol.get("claim_role")
        or ("method_candidate" if mechanism_type in {"ALGO", "CODE", "PARAM"} else "diagnostic_only")
    ).strip()
    dataset_group_plan = (
        protocol.get("dataset_group_plan")
        or idea.get("dataset_group_plan")
        or dataset_group_plan_from_contract(program_contract)
    )
    program_dataset_ids = required_dataset_ids(program_contract, {"dataset_group_plan": dataset_group_plan, "dataset": dataset})
    parameter_transfer_contract = normalized_parameter_contract(
        protocol.get("parameter_transfer_contract") or idea.get("parameter_transfer_contract"),
        program_dataset_ids,
        track_id,
    )
    if parameter_transfer_contract:
        parameter_validation = validate_parameter_transfer_contract(
            parameter_transfer_contract,
            program_dataset_ids,
        )
        if program_mode == "enforced" and not parameter_validation["complete"]:
            raise SystemExit(
                "parameter_transfer_contract invalid: " + "; ".join(parameter_validation.get("errors") or [])
            )
    elif program_mode == "enforced" and program_scope == "cross_dataset_method" and claim_role == "method_candidate":
        raise SystemExit("enforced cross-dataset method requires parameter_transfer_contract")
    parameter_profile_status = str(
        protocol.get("parameter_profile_status")
        or idea.get("parameter_profile_status")
        or ("audit_pending" if parameter_transfer_contract else "not_required")
    ).strip()
    stage2_role = str(
        protocol.get("stage2_role")
        or idea.get("stage2_role")
        or ("stage2_parameter_probe" if parameter_transfer_contract else "stage2_method_screen")
    ).strip()
    baseline_training_protocol = protocol.get("baseline_training_protocol") or baseline
    baseline_eval_protocol = protocol.get("baseline_eval_protocol") or "same dataset split and primary metric"
    evaluation_command = protocol.get("evaluation_command") or rapid_validation.get("evaluation_command") or "locked evaluation command required before launch"
    protected_paths = protocol.get("protected_paths", [])
    one_variable_change = idea.get("one_variable_change") or "selected idea changes exactly one planned variable"
    falsifier = idea.get("falsifier") or "no improvement over the matched baseline"
    method_formula = protocol.get("method_formula") or idea.get("method_formula") or {
        "mechanism_type": mechanism_type,
        "one_variable_change": one_variable_change,
        "shared_parameter_formula": (
            parameter_transfer_contract.get("shared_formula") if parameter_transfer_contract else "not_applicable"
        ),
    }
    method_formula_sha256 = canonical_sha256(method_formula)
    parameter_role_inventory = protocol.get("parameter_role_inventory") or idea.get("parameter_role_inventory")
    if not isinstance(parameter_role_inventory, list) or not parameter_role_inventory:
        parameter_role_inventory = [
            {
                "parameter_name": "baseline_training_protocol",
                "parameter_role": "baseline_protocol",
                "dataset_specific_allowed": True,
            },
            {
                "parameter_name": "baseline_eval_protocol",
                "parameter_role": "baseline_protocol",
                "dataset_specific_allowed": True,
            },
            {
                "parameter_name": "data_split",
                "parameter_role": "baseline_protocol",
                "dataset_specific_allowed": True,
            },
        ]
        if parameter_transfer_contract:
            parameter_role_inventory.append(
                {
                    "parameter_name": parameter_transfer_contract.get("parameter_name"),
                    "parameter_role": "innovation_load_bearing",
                    "dataset_specific_allowed": (
                        parameter_transfer_contract.get("transfer_mode") == "dataset_calibrated"
                    ),
                    "parameter_transfer_contract_sha256": parameter_transfer_contract.get(
                        "parameter_transfer_contract_sha256"
                    ),
                }
            )
    core_scientific_contribution, supporting_contributions, paper_innovation_bundle, paper_storyline = selected_paper_contributions(idea)
    if track_role != "primary" and not core_scientific_contribution:
        core_scientific_contribution = {
            "name": idea.get("title") or idea.get("name") or selected_idea_id,
            "contribution_class": "core_scientific_contribution",
            "mechanism_delta": one_variable_change,
            "validation_plan": seed.get("minimum_pilot") if seed else ["baseline", "proposed"],
        }
    effective_gpu_hours = args.gpu_hours
    effective_walltime_hours = args.walltime_hours
    if effective_gpu_hours <= 0:
        track_spec = idea.get("track_seed_spec") if isinstance(idea.get("track_seed_spec"), dict) else {}
        for candidate in [
            idea.get("estimated_falsifier_gpu_hours"),
            idea.get("estimated_gpu_hours"),
            seed.get("estimated_falsifier_gpu_hours") if seed else None,
            seed.get("estimated_gpu_hours") if seed else None,
            track_spec.get("estimated_falsifier_gpu_hours"),
            track_spec.get("estimated_gpu_hours"),
            protocol.get("estimated_falsifier_gpu_hours"),
        ]:
            try:
                parsed = float(candidate)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                effective_gpu_hours = parsed
                break
    if external_mode:
        if effective_gpu_hours <= 0 and present(resource_request.get("estimated_gpu_hours")):
            effective_gpu_hours = float(resource_request["estimated_gpu_hours"])
        if args.walltime_hours == 1 and present(resource_request.get("walltime_minutes")):
            effective_walltime_hours = float(resource_request["walltime_minutes"]) / 60.0
    dataset_runtime_plan = (
        protocol.get("dataset_runtime_plan")
        or idea.get("dataset_runtime_plan")
        or default_dataset_runtime_plan(dataset, effective_gpu_hours, effective_walltime_hours)
    )
    dataset_requirement_inventory = (
        protocol.get("dataset_requirement_inventory")
        or idea.get("dataset_requirement_inventory")
        or default_dataset_requirement_inventory(dataset)
    )
    stability_seed_policy = (
        protocol.get("stability_seed_policy")
        or idea.get("stability_seed_policy")
        or (rapid_validation.get("seed_policy") if external_mode else None)
        or {
            "max_random_seeds": 3,
            "planned_seed_count": 1,
            "planned_random_seeds": [],
            "claim_rule": "Use at most three random seeds for stability validation; single-seed evidence remains pilot-only unless supported by ablation/confirmation.",
            "scope_note": "This caps experiment random seeds, not IDEA_TRACK_SEEDS track candidates.",
        }
    )
    hpo_search_policy = (
        protocol.get("hpo_search_policy")
        or idea.get("hpo_search_policy")
        or default_hpo_search_policy(mechanism_type)
    )
    pre_idea_gate_path = "ideation/PRE_IDEA_EVIDENCE_GATE.json"
    innovation_slot_map_path = str(gate.get("innovation_slot_map_path") or "ideation/INNOVATION_SLOT_MAP.json")
    consumed_slot_ids = (
        idea.get("consumed_innovation_slot_ids")
        or idea.get("innovation_slot_refs")
        or campaign_candidate.get("innovation_slot_refs")
        or campaign_candidate.get("gap_closure_refs")
        or []
    )
    compute_backend = (
        protocol.get("compute_backend")
        or idea.get("compute_backend")
        or (resource_request.get("compute_backend") if external_mode else None)
        or {
            "backend": "local_gpu",
            "decision_rationale": "bounded quick validation on an available GPU",
            "gpu_evidence": "resource observation required before launch",
            "paid_resource_policy": "no paid resource without separate authorization",
        }
    )
    if not isinstance(compute_backend, dict):
        compute_backend = {
            "backend": str(compute_backend),
            "decision_rationale": "bounded quick validation route committed by the external campaign",
            "gpu_evidence": "resource observation required before launch",
            "paid_resource_policy": "no paid resource without separate authorization",
        }
    backend_name = str(compute_backend.get("backend") or "local_gpu").strip()
    execution_route = str(
        protocol.get("execution_route")
        or idea.get("execution_route")
        or compute_backend.get("execution_route")
        or (resource_request.get("execution_route") if external_mode else None)
        or ("autodl" if backend_name == "autodl_gpu" else "local")
    ).strip().lower()
    path_mapping = (
        protocol.get("path_mapping")
        or idea.get("path_mapping")
        or {
            "selected_backend": backend_name,
            "logical_dataset_id": dataset,
            "code_root": "path mapping required before launch",
            "data_root": "path mapping required before launch",
            "output_dir": "path mapping required before launch",
            "checkpoint_dir": "path mapping required before launch",
            "persistent_output_dir": "path mapping required before launch",
            "env": {
                "DATA_ROOT": "path mapping required before launch",
                "OUTPUT_DIR": "path mapping required before launch",
                "CKPT_DIR": "path mapping required before launch",
            },
        }
    )
    if isinstance(path_mapping, dict) and external_mode:
        path_mapping = jsonish_copy(path_mapping)
        path_mapping["execution_route"] = execution_route
    baseline_code = protocol.get("baseline_code") or idea.get("baseline_code") or rapid_baseline_code or {}
    innovation_search_contract = (
        idea.get("innovation_search_contract")
        or campaign_candidate.get("innovation_search_contract")
        or {
            "selected_idea_id": selected_idea_id,
            "track_id": track_id,
            "innovation_mechanism": idea.get("mechanism") or campaign_candidate.get("mechanism") or one_variable_change,
            "mechanism_type": mechanism_type,
            "primary_method_source_role": idea.get("primary_method_source_role") or "external_domain_transfer",
            "neighbor_transfer_mechanism": idea.get("neighbor_transfer_mechanism") or campaign_candidate.get("structural_gap") or "external structural-gap transfer",
            "target_domain_anchor": idea.get("target_domain_anchor") or dataset,
            "target_domain_method_overlap_risk": idea.get("target_domain_method_overlap_risk") or "bounded by collision search and panel review",
            "one_variable_change": one_variable_change,
            "expected_effect": idea.get("expected_effect") or campaign_candidate.get("observable_prediction") or "decision-changing pilot signal",
            "falsifier": falsifier,
            "promotion_stage": "candidate",
            "ablation_required": True,
            "confirmation_required": True,
        }
    )
    if not isinstance(innovation_search_contract, dict):
        raise SystemExit("selected idea innovation_search_contract must be an object")
    innovation_search_contract = jsonish_copy(innovation_search_contract)
    for field, expected in [("selected_idea_id", selected_idea_id), ("track_id", track_id)]:
        if present(innovation_search_contract.get(field)) and str(innovation_search_contract.get(field)) != str(expected):
            raise SystemExit(
                f"innovation_search_contract.{field}={innovation_search_contract.get(field)!r} does not match {expected!r}"
            )
        innovation_search_contract[field] = expected
    innovation_search_contract.setdefault("mechanism_type", mechanism_type)
    innovation_search_contract.setdefault("one_variable_change", one_variable_change)
    innovation_search_contract.setdefault("falsifier", falsifier)
    innovation_search_contract.setdefault("promotion_stage", "candidate")
    innovation_search_contract["ablation_required"] = True
    innovation_search_contract["confirmation_required"] = True
    evidence_paths = [".autoreskill/evidence_cart.jsonl"]
    if external_mode:
        evidence_paths.extend([f".autoreskill/{campaign_ref}", f".autoreskill/{lint_ref}"])
        design_path = ".autoreskill/ideation/PANEL_DESIGN_REVIEW.json"
        evidence_import_gate = {
            "status": "not_required",
            "source_mode": "external_material",
            "material_refs": [campaign_ref],
            "validation_ref": lint_ref,
            "reason": "evidence was supplied and validated through the non-PaperNexus external-material gate",
            "launch_blocked": False,
        }
        source_verification_limits = (
            campaign_candidate.get("source_verification_limits")
            or campaign.get("source_verification_limits")
            or gate.get("source_verification_limits")
            or ["excerpt integrity does not by itself prove fidelity to the original source"]
        )
        claim_limits = (
            campaign_candidate.get("claim_limits")
            or campaign.get("claim_limits")
            or ["quick pilots are candidate evidence and cannot directly promote paper claims"]
        )
        external_evidence_norms = {
            "campaign_ref": campaign_ref,
            "campaign_sha256": gate.get("campaign_sha256"),
            "source_integrity": {
                "lint_ref": lint_ref,
                "lint_sha256": gate.get("lint_sha256"),
                "slot_map_sha256": gate.get("slot_map_sha256"),
            },
            "source_verification_limits": source_verification_limits,
            "claim_limits": claim_limits,
        }
    else:
        design_path = ".autoreskill/papernexus/research_controller/design-review.json"
        evidence_import_gate = idea.get("evidence_import_gate") or protocol.get("evidence_import_gate") or {}
        external_evidence_norms = None
    passport_binding = project_passport_binding(base, idea, protocol)
    innovation_delta = {
        "mechanism": (
            (seed.get("hypothesis_contract") or {}).get("mechanism")
            if seed and isinstance(seed.get("hypothesis_contract"), dict)
            else idea.get("mechanism")
        ),
        "one_variable_change": one_variable_change,
        "predicted_pattern": (
            (seed.get("hypothesis_contract") or {}).get("predicted_pattern")
            if seed and isinstance(seed.get("hypothesis_contract"), dict)
            else idea.get("predicted_pattern") or idea.get("expected_effect")
        ),
        "falsifier": falsifier,
        "alternative_explanations": idea.get("alternative_explanations") or idea.get("competing_explanations") or [],
        "stop_rules": ["stop on protocol invalidity", "stop on the declared scientific falsifier"],
        "budget": {"gpu_hours": effective_gpu_hours, "walltime_hours": effective_walltime_hours},
    }
    innovation_delta_sha256 = canonical_sha256(innovation_delta)
    validation_ladder = default_validation_ladder(dataset, primary_metric, effective_gpu_hours)
    innovation = {
        "schema_version": 1,
        "created_at": now(),
        "selected_idea_fragment_id": selected_fragment_id if external_mode else selected_idea_id,
        "supporting_idea_fragment_ids": [selected_fragment_id if external_mode else selected_idea_id],
        "idea_pool_path": idea_pool_path,
        "selected_idea_id": selected_idea_id,
        "track_id": track_id,
        "track_role": track_role,
        "claim_role": claim_role,
        "idea_lifecycle_status": lifecycle,
        "idea_decision_ref": idea_decision_ref,
        "selection_fingerprint": selection_fingerprint,
        "evidence_tier_ceiling": evidence_tier_ceiling,
        "source_track_seed_ref": "ideation/IDEA_TRACK_SEEDS.json" if seed else None,
        "source_track_seed_sha256": seed_sha or None,
        "source_track_seed_item_sha256": seed.get("track_seed_sha256") if seed else None,
        "innovation_delta": innovation_delta,
        "innovation_delta_sha256": innovation_delta_sha256,
        "baseline": baseline,
        "primary_metric": primary_metric,
        "dataset_or_benchmark": dataset,
        "dataset": dataset,
        "core_scientific_contribution": core_scientific_contribution,
        "supporting_contributions": supporting_contributions,
        "paper_innovation_bundle": paper_innovation_bundle,
        "paper_storyline": paper_storyline,
        "one_variable_change": one_variable_change,
        "falsifier": falsifier,
        "falsifiers": [falsifier],
        "fixed_budget": {"gpu_hours": effective_gpu_hours, "walltime_hours": effective_walltime_hours},
        "dataset_requirement_inventory": dataset_requirement_inventory,
        "dataset_runtime_plan": dataset_runtime_plan,
        "dataset_group_plan": dataset_group_plan,
        "parameter_transfer_contract": parameter_transfer_contract or None,
        "method_formula": method_formula,
        "method_formula_sha256": method_formula_sha256,
        "parameter_role_inventory": parameter_role_inventory,
        "parameter_profile_status": parameter_profile_status,
        "stage2_role": stage2_role,
        "stability_seed_policy": stability_seed_policy,
        "hpo_search_policy": hpo_search_policy,
        "innovation_search_contract": innovation_search_contract,
        "baseline_code": baseline_code,
        "compute_backend": compute_backend,
        "execution_route": execution_route,
        "path_mapping": path_mapping,
        "evidence_import_gate": evidence_import_gate,
        "pre_idea_evidence_gate_path": pre_idea_gate_path,
        "innovation_slot_map_path": innovation_slot_map_path,
        "consumed_innovation_slot_ids": as_list(consumed_slot_ids),
        "evidence_paths": evidence_paths,
        "idea_evidence_export_path": ".autoreskill/papernexus/idea_catalyst_evidence_export.json",
        "evidence_boundaries": {
            "source_backed": evidence_ids or evidence_paths,
            "agent_inferred": [one_variable_change],
            "speculative": ["expected metric impact remains unverified until experiment reconciliation"],
            "unsupported": ["do not promote manuscript claims before non-fixture results and analysis"],
        },
        "paperNexus_corpus": read_json(base / "goal_state.json", {}).get("paperNexus", {}).get("corpus"),
        "source_backing_summary": "Evidence ids are required for claim promotion; fixture mode is not graph-grounded.",
        "controller_design_review_path": design_path if (base / design_path.removeprefix(".autoreskill/")).exists() else None,
        "claim_strength": "provisional" if not evidence_ids else "bounded",
        "fixture": bool(args.allow_fixture and not evidence_ids),
    }
    innovation.update(program_binding)
    innovation.update(passport_binding)
    if external_mode:
        innovation.pop("idea_evidence_export_path", None)
        innovation.pop("paperNexus_corpus", None)
        innovation.update(
            {
                "external_campaign_ref": campaign_ref,
                "external_campaign_sha256": gate.get("campaign_sha256"),
                "external_candidate_id": external_candidate_id,
                "protected_commitment_sha256": protected_commitment_sha256,
                "track_id": track_id,
                "evidence_import_gate": evidence_import_gate,
                "pre_idea_evidence_gate_path": pre_idea_gate_path,
                "innovation_slot_map_path": innovation_slot_map_path,
                "consumed_innovation_slot_ids": as_list(consumed_slot_ids),
                "innovation_search_contract": innovation_search_contract,
                "baseline_code": baseline_code,
                "compute_backend": compute_backend,
                "execution_route": execution_route,
                "path_mapping": path_mapping,
                "external_evidence_norms": external_evidence_norms,
                "source_backing_summary": "External evidence is bound to the committed campaign/lint hashes; claim strength remains limited by recorded source-verification limits.",
            }
        )
    review = {
        "schema_version": 1,
        "created_at": now(),
        "status": "reviewed",
        "track_id": track_id,
        "track_role": track_role,
        "claim_role": claim_role,
        "idea_lifecycle_status": lifecycle,
        "idea_decision_ref": idea_decision_ref,
        "selection_fingerprint": selection_fingerprint,
        "evidence_tier_ceiling": evidence_tier_ceiling,
        "source_track_seed_ref": "ideation/IDEA_TRACK_SEEDS.json" if seed else None,
        "source_track_seed_sha256": seed_sha or None,
        "source_track_seed_item_sha256": seed.get("track_seed_sha256") if seed else None,
        "innovation_delta": innovation_delta,
        "innovation_delta_sha256": innovation_delta_sha256,
        "claim_ids": [f"{track_id}_claim"],
        "hypothesis": "The selected one-variable change improves the primary metric under a fixed baseline protocol.",
        "novelty_basis": (
            idea.get("novelty_basis")
            or campaign_candidate.get("novelty_basis")
            or "External-material lineage, structural-gap, and collision evidence with bounded source-verification limits."
            if external_mode
            else "Must be grounded in PaperNexus evidence before strong manuscript claims."
        ),
        "idea_pool_path": idea_pool_path,
        "selected_idea_id": selected_idea_id,
        "idea_generation_scope": "ideation-stage experiment idea pool; no experiment-plan generation",
        "core_scientific_contribution": core_scientific_contribution,
        "supporting_contributions": supporting_contributions,
        "paper_innovation_bundle": paper_innovation_bundle,
        "paper_storyline": paper_storyline,
        "one_variable_change": True,
        "one_variable_change_description": one_variable_change,
        "observable_prediction": (
            (seed.get("hypothesis_contract") or {}).get("predicted_pattern")
            if isinstance(seed.get("hypothesis_contract"), dict)
            else idea.get("predicted_pattern")
        ) or idea.get("expected_effect") or "decision-changing pilot signal",
        "hypothesis_contract": seed.get("hypothesis_contract") if isinstance(seed.get("hypothesis_contract"), dict) else {},
        "minimum_pilot": seed.get("minimum_pilot") if seed else ["baseline", "proposed"],
        "baseline_reference": baseline,
        "baseline_training_protocol": baseline_training_protocol,
        "baseline_eval_protocol": baseline_eval_protocol,
        "evaluation_command": evaluation_command,
        "dataset": dataset,
        "dataset_requirement_inventory": dataset_requirement_inventory,
        "dataset_runtime_plan": dataset_runtime_plan,
        "dataset_group_plan": dataset_group_plan,
        "parameter_transfer_contract": parameter_transfer_contract or None,
        "method_formula": method_formula,
        "method_formula_sha256": method_formula_sha256,
        "parameter_role_inventory": parameter_role_inventory,
        "parameter_profile_status": parameter_profile_status,
        "stage2_role": stage2_role,
        "stability_seed_policy": stability_seed_policy,
        "hpo_search_policy": hpo_search_policy,
        "data_split": data_split,
        "primary_metric": primary_metric,
        "metric_direction": metric_direction,
        "secondary_metrics": ["runtime", "stability"],
        "ablation_plan": ["remove the proposed one-variable change"],
        "falsifiers": [falsifier],
        "stop_rules": ["stop if dry-run fails after bounded repair", "stop if metric/dataset drift is detected"],
        "compute_budget": {"gpu_hours": effective_gpu_hours, "walltime_hours": effective_walltime_hours},
        "validation_ladder_schema_version": 1,
        "validation_ladder": validation_ladder,
        "protected_paths": protected_paths,
        "expected_artifacts": ["EXPERIMENT_MANIFEST.json", "dry_run.log", "REMOTE_RUN.json", "EXPERIMENT_LEDGER.json"],
        "paperNexus_norms": ["See evidence_cart and PaperNexus artifacts."],
        "experiment_cost_norms": {"gpu_hours": effective_gpu_hours, "walltime_hours": effective_walltime_hours},
        "non_promotion_signals": ["single seed only", "fixture mode", "missing graph-grounded novelty evidence", "low-fidelity HPO scout evidence"],
        "promotion_gate": {
            "stage": "candidate",
            "promotion_requires": (
                ["explicit primary reselection", "frozen matched baseline rerun", "ablation", "confirmation"]
                if evidence_tier_ceiling == "pilot_only"
                else ["matched baseline", "ablation", "confirmation"]
            ),
            "claim_policy": (
                "pilot_only evidence cannot directly close or promote a manuscript claim"
                if evidence_tier_ceiling == "pilot_only"
                else "claim eligibility begins only after matched baseline, ablation, and confirmation gates"
            ),
        },
        "innovation_search_contract": innovation_search_contract,
        "baseline_code": baseline_code,
        "compute_backend": compute_backend,
        "execution_route": execution_route,
        "path_mapping": path_mapping,
        "evidence_import_gate": evidence_import_gate,
        "pre_idea_evidence_gate_path": pre_idea_gate_path,
        "innovation_slot_map_path": innovation_slot_map_path,
        "consumed_innovation_slot_ids": as_list(consumed_slot_ids),
    }
    review.update(program_binding)
    review.update(passport_binding)
    if passport_binding:
        resolved_projection = {
            **passport_binding,
            "baseline_reference": baseline,
            "dataset": dataset,
            "data_split": data_split,
            "primary_metric": primary_metric,
            "execution_route": execution_route,
            "innovation_delta_sha256": innovation_delta_sha256,
        }
        projection_sha256 = canonical_sha256(resolved_projection)
        innovation["resolved_execution_contract_projection"] = resolved_projection
        innovation["resolved_execution_contract_projection_sha256"] = projection_sha256
        review["resolved_execution_contract_projection"] = resolved_projection
        review["resolved_execution_contract_projection_sha256"] = projection_sha256
    if external_mode:
        review.pop("paperNexus_norms", None)
        review.update(
            {
                "selected_idea_fragment_id": selected_fragment_id,
                "external_campaign_ref": campaign_ref,
                "external_campaign_sha256": gate.get("campaign_sha256"),
                "external_candidate_id": external_candidate_id,
                "protected_commitment_sha256": protected_commitment_sha256,
                "evidence_import_gate": evidence_import_gate,
                "pre_idea_evidence_gate_path": pre_idea_gate_path,
                "innovation_slot_map_path": innovation_slot_map_path,
                "consumed_innovation_slot_ids": as_list(consumed_slot_ids),
                "innovation_search_contract": innovation_search_contract,
                "baseline_code": baseline_code,
                "compute_backend": compute_backend,
                "execution_route": execution_route,
                "path_mapping": path_mapping,
                "external_evidence_norms": external_evidence_norms,
                "controller_design_review_path": design_path,
            }
        )
    if external_commit is not None:
        try:
            require_same_external_gate_commit(
                external_commit,
                load_external_gate_commit(base),
            )
        except ExternalGateError as exc:
            raise SystemExit(f"external_gate_invalid: {exc}") from exc

    preserve_frozen_parameter_profile(base, track_id, review, innovation)
    bind_semantic_sha256(innovation)
    bind_semantic_sha256(review)
    innovation_ref = f"orchestrator/tracks/{track_id}/INNOVATION_PACKET.json"
    review_ref = f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json"
    plan_ref = f"planner/tracks/{track_id}/EXPERIMENT_PLAN.md"
    plan_text = (
        f"# Experiment Plan: {track_id}\n\n"
        f"Role: `{track_role}`\n\n"
        f"Evidence ceiling: `{evidence_tier_ceiling}`\n\n"
        "Baseline-first, one-variable, dry-run-gated plan. Non-primary positive evidence routes to explicit reselection and a frozen matched-baseline rerun.\n"
    )
    target_paths = [innovation_ref, review_ref, plan_ref]
    if track_role == "primary":
        target_paths.extend(
            [
                "orchestrator/INNOVATION_PACKET.json",
                "planner/EXPERIMENT_REVIEW_PACKET.json",
                "planner/EXPERIMENT_PLAN.md",
            ]
        )

    missing_packet_refs = [
        ref
        for ref in [innovation_ref, review_ref, plan_ref]
        if not (base / ref).exists()
    ]
    files_that_would_be_written = [
        ref
        for ref, would_change in [
            (innovation_ref, json_would_change(base / innovation_ref, innovation)),
            (review_ref, json_would_change(base / review_ref, review)),
            (plan_ref, text_would_change(base / plan_ref, plan_text)),
        ]
        if would_change
    ]
    if track_role == "primary":
        files_that_would_be_written.extend(
            ref
            for ref, would_change in [
                (
                    "orchestrator/INNOVATION_PACKET.json",
                    json_would_change(base / "orchestrator/INNOVATION_PACKET.json", innovation),
                ),
                (
                    "planner/EXPERIMENT_REVIEW_PACKET.json",
                    json_would_change(base / "planner/EXPERIMENT_REVIEW_PACKET.json", review),
                ),
                (
                    "planner/EXPERIMENT_PLAN.md",
                    text_would_change(base / "planner/EXPERIMENT_PLAN.md", plan_text),
                ),
            ]
            if would_change
        )

    changed_paths: list[str] = []
    if not args.dry_run:
        if write_json_if_changed(base / innovation_ref, innovation):
            changed_paths.append(innovation_ref)
        if write_json_if_changed(base / review_ref, review):
            changed_paths.append(review_ref)
        if write_text_if_changed(base / plan_ref, plan_text):
            changed_paths.append(plan_ref)
        if track_role == "primary":
            if write_json_if_changed(base / "orchestrator/INNOVATION_PACKET.json", innovation):
                changed_paths.append("orchestrator/INNOVATION_PACKET.json")
            if write_json_if_changed(base / "planner/EXPERIMENT_REVIEW_PACKET.json", review):
                changed_paths.append("planner/EXPERIMENT_REVIEW_PACKET.json")
            if write_text_if_changed(base / "planner/EXPERIMENT_PLAN.md", plan_text):
                changed_paths.append("planner/EXPERIMENT_PLAN.md")
        if changed_paths:
            append_jsonl(
                base / "decision_log.jsonl",
                {
                    "ts": now(),
                    "stage": "experiment_plan",
                    "action": "materialize_track_experiment_plan",
                    "details": {
                        "track_id": track_id,
                        "track_role": track_role,
                        "evidence_tier_ceiling": evidence_tier_ceiling,
                        "fixture": innovation["fixture"],
                        "changed_paths": changed_paths,
                    },
                },
            )
    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": args.dry_run,
                "changed": bool(changed_paths),
                "track_id": track_id,
                "idea_id": selected_idea_id,
                "track_role": track_role,
                "idea_lifecycle_status": lifecycle,
                "evidence_tier_ceiling": evidence_tier_ceiling,
                "source_track_seed_sha256": seed_sha or None,
                "target_paths": target_paths,
                "missing_packet_refs": missing_packet_refs,
                "files_that_would_be_written": sorted(set(files_that_would_be_written)),
                "changed_paths": changed_paths,
                "innovation_packet": innovation_ref,
                "experiment_review_packet": review_ref,
                "primary_projection_written": track_role == "primary" and not args.dry_run,
                "semantic_sha256": {
                    "innovation": innovation["semantic_sha256"],
                    "review": review["semantic_sha256"],
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
