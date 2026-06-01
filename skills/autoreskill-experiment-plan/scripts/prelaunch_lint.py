#!/usr/bin/env python3
"""Lint EXPERIMENT_REVIEW_PACKET before experiment launch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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
    "path_mapping",
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
TRACK_EVIDENCE_READY = {"passed", "complete", "completed", "graph_closed", "source_backed"}
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


def require_nested(mapping: Any, prefix: str, keys: list[str], missing: list[str]) -> None:
    if not isinstance(mapping, dict):
        missing.append(prefix)
        return
    for key in keys:
        value = mapping.get(key)
        if not present(value) or placeholder(value):
            missing.append(f"{prefix}.{key}")


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
            if not isinstance(gate, dict) or str(gate.get("status") or "").strip().lower() != "passed":
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
    validate_evidence_import_gate(packet, missing)
    validate_pre_idea_refs(packet, project, missing)
    validate_compute_backend(packet, missing)
    validate_path_mapping(packet, missing)
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
