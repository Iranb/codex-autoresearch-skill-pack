#!/usr/bin/env python3
"""Lint INNOVATION_PACKET experiment-plan authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from hpo_policy_lint import validate_hpo_search_policy


SKILL_ROOT = Path(__file__).resolve().parents[2]
PAPERNEXUS_SCRIPTS = SKILL_ROOT / "autoreskill-papernexus-innovation/scripts"
WORKFLOW_SCRIPTS = SKILL_ROOT / "autoreskill-workflow/scripts"
if str(PAPERNEXUS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PAPERNEXUS_SCRIPTS))
if str(WORKFLOW_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_SCRIPTS))

from idea_support_lint import lint_idea_support, resolve_artifact_path  # noqa: E402
from parameter_transfer import (  # noqa: E402
    VALID_PARAMETER_ROLES,
    program_contract_binding,
    required_dataset_ids,
    validate_parameter_transfer_contract,
)


REQUIRED = [
    "selected_idea_fragment_id",
    "innovation_search_contract",
    "baseline",
    "baseline_code",
    "evidence_import_gate",
    "pre_idea_evidence_gate_path",
    "innovation_slot_map_path",
    "consumed_innovation_slot_ids",
    "compute_backend",
    "path_mapping",
    "stability_seed_policy",
    "primary_metric",
    "fixed_budget",
]


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
ONE_VARIABLE_KEYS = ["one_variable_change", "oneVariableChange", "method_delta", "methodDelta", "intervention", "variable_change"]
FALSIFIER_KEYS = ["falsifier", "falsifiers", "failure_condition", "failure_conditions", "failureCondition", "stop_condition"]
DATASET_KEYS = ["dataset_or_benchmark", "datasetOrBenchmark", "dataset", "datasets", "benchmark", "benchmarks"]
READY = {"ready", "complete", "completed", "pass", "passed", "approved", "verified"}
BACKENDS = {"local_gpu", "autodl_gpu"}
EXECUTION_ROUTES = {"local", "ssh", "bjtu_hpc", "autodl"}
EVIDENCE_GATE_STATUSES = {"passed", "not_required", "async_wait", "blocked"}
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
CORE_CONTRIBUTION_CLASSES = {"core", "core_scientific_contribution"}
SUPPORTING_CONTRIBUTION_CLASSES = {"supporting", "supporting_scientific_contribution"}
NON_INNOVATION_CONTRIBUTION_CLASSES = {"validation_role", "analysis_role", "engineering_support"}
MAX_STABILITY_RANDOM_SEEDS = 3
EXTERNAL_IDENTITY_FIELDS = ["external_campaign_ref", "external_campaign_sha256", "external_candidate_id"]


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if present(mapping.get(key)):
            return mapping[key]
    return None


def evidence_source_mode(base: Path, packet: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    gate_value = first_present(packet, ["pre_idea_evidence_gate_path", "preIdeaEvidenceGatePath"])
    gate_path = resolve_artifact_path(base, gate_value, "ideation/PRE_IDEA_EVIDENCE_GATE.json")
    gate = read_json(gate_path) if gate_path else None
    if not isinstance(gate, dict):
        gate = {}
    return str(gate.get("evidence_source_mode") or "papernexus").strip().lower(), gate


def placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return "required before launch" in text or text.startswith("replace_with")


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
    prefix = "INNOVATION_PACKET.stability_seed_policy"
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


def normalized_role(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def story_step_count(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if present(item) and not placeholder(item)])
    if not isinstance(value, str):
        return 0
    text = value.replace("\n", " ")
    for sep in ["。", "；", ";", "->", "=>", "|"]:
        text = text.replace(sep, ".")
    return len([part for part in text.split(".") if part.strip()])


def validate_baseline_backend_paths(packet: dict[str, Any], missing: list[str], require_route: bool = False) -> None:
    baseline_code = packet.get("baseline_code")
    require_nested(
        baseline_code,
        "INNOVATION_PACKET.baseline_code",
        ["code_id", "source_type", "source_ref", "resolved_path", "train_entrypoint", "eval_entrypoint", "selection_rationale"],
        missing,
    )
    if isinstance(baseline_code, dict):
        if baseline_code.get("locked") is not True:
            missing.append("INNOVATION_PACKET.baseline_code.locked must be true")
        source_type = str(baseline_code.get("source_type") or "").lower()
        if source_type in {"", "search", "web_search", "unbounded_search", "unspecified"}:
            missing.append("INNOVATION_PACKET.baseline_code.source_type must identify a locked code source")

    backend = packet.get("compute_backend")
    require_nested(
        backend,
        "INNOVATION_PACKET.compute_backend",
        ["backend", "decision_rationale", "gpu_evidence", "paid_resource_policy"],
        missing,
    )
    backend_name = str((backend or {}).get("backend") or "").strip() if isinstance(backend, dict) else ""
    if backend_name not in BACKENDS:
        missing.append("INNOVATION_PACKET.compute_backend.backend must be local_gpu or autodl_gpu")
    if backend_name == "autodl_gpu" and isinstance(backend, dict) and not present(backend.get("autodl_plan_ref")):
        missing.append("INNOVATION_PACKET.compute_backend.autodl_plan_ref")

    route = str(packet.get("execution_route") or "").strip().lower()
    if require_route and not route:
        missing.append("INNOVATION_PACKET.execution_route")
    if route and route not in EXECUTION_ROUTES:
        missing.append("INNOVATION_PACKET.execution_route must be local, ssh, bjtu_hpc, or autodl")
    if backend_name == "local_gpu" and route and route not in {"local", "ssh", "bjtu_hpc"}:
        missing.append("INNOVATION_PACKET local_gpu execution_route must be local, ssh, or bjtu_hpc")
    if backend_name == "autodl_gpu" and route and route != "autodl":
        missing.append("INNOVATION_PACKET autodl_gpu execution_route must be autodl")

    mapping = packet.get("path_mapping")
    require_nested(
        mapping,
        "INNOVATION_PACKET.path_mapping",
        ["selected_backend", "logical_dataset_id", "code_root", "data_root", "output_dir", "checkpoint_dir", "persistent_output_dir"],
        missing,
    )
    if isinstance(mapping, dict):
        selected = str(mapping.get("selected_backend") or "").strip()
        if selected not in BACKENDS:
            missing.append("INNOVATION_PACKET.path_mapping.selected_backend must be local_gpu or autodl_gpu")
        if backend_name in BACKENDS and selected and selected != backend_name:
            missing.append("INNOVATION_PACKET.path_mapping.selected_backend must match compute_backend.backend")
        mapping_route = str(mapping.get("execution_route") or "").strip().lower()
        if require_route and not mapping_route:
            missing.append("INNOVATION_PACKET.path_mapping.execution_route")
        if mapping_route and mapping_route not in EXECUTION_ROUTES:
            missing.append("INNOVATION_PACKET.path_mapping.execution_route must be local, ssh, bjtu_hpc, or autodl")
        if route and mapping_route and route != mapping_route:
            missing.append("INNOVATION_PACKET.path_mapping.execution_route must match INNOVATION_PACKET.execution_route")
        require_nested(mapping.get("env"), "INNOVATION_PACKET.path_mapping.env", ["DATA_ROOT", "OUTPUT_DIR", "CKPT_DIR"], missing)


def validate_innovation_contract(packet: dict[str, Any], missing: list[str]) -> None:
    contract = packet.get("innovation_search_contract")
    require_nested(
        contract,
        "INNOVATION_PACKET.innovation_search_contract",
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
        missing.append("INNOVATION_PACKET.innovation_search_contract.mechanism_type must be ALGO, CODE, or PARAM")
    if str(contract.get("promotion_stage") or "").strip().lower() not in PROMOTION_STAGES:
        missing.append("INNOVATION_PACKET.innovation_search_contract.promotion_stage must be candidate, ablation, or confirmation")
    source_role = normalized_role(contract.get("primary_method_source_role") or packet.get("primary_method_source_role"))
    if source_role in TARGET_DOMAIN_ONLY_ROLES:
        if not present(contract.get("current_field_absence_evidence") or packet.get("current_field_absence_evidence")):
            missing.append("INNOVATION_PACKET.innovation_search_contract.current_field_absence_evidence required for target-domain-only main method")
    elif source_role and source_role not in VALID_METHOD_SOURCE_ROLES:
        missing.append("INNOVATION_PACKET.innovation_search_contract.primary_method_source_role must be near/far-neighbor transfer, cross-lane recombination, proposal-graph transfer, external-domain transfer, or target_domain_absence_proven")
    if contract.get("ablation_required") is not True:
        missing.append("INNOVATION_PACKET.innovation_search_contract.ablation_required must be true")
    if contract.get("confirmation_required") is not True:
        missing.append("INNOVATION_PACKET.innovation_search_contract.confirmation_required must be true")


def validate_paper_bundle(
    packet: dict[str, Any],
    missing: list[str],
    details: dict[str, Any],
    *,
    require_storyline: bool = True,
) -> None:
    contract = packet.get("innovation_search_contract") if isinstance(packet.get("innovation_search_contract"), dict) else {}
    core = first_present(packet, ["core_scientific_contribution", "core_contribution"])
    if not present(core):
        core = contract.get("core_scientific_contribution") or contract.get("core_contribution")
    # Keep old bundle keys readable without restoring the retired three-contribution requirement.
    bundle = first_present(packet, ["paper_innovation_bundle", "innovation_bundle", "three_innovation_bundle"])
    if not present(bundle):
        bundle = contract.get("paper_innovation_bundle") or contract.get("innovation_bundle")
    points = as_list(bundle)
    details["paper_innovation_bundle_count"] = len(points)
    legacy_core_index: int | None = None
    if not present(core) and points:
        for index, point in enumerate(points):
            if not isinstance(point, dict):
                continue
            contribution_class = normalized_role(point.get("contribution_class"))
            if contribution_class in CORE_CONTRIBUTION_CLASSES:
                core = point
                legacy_core_index = index
                break
        if not present(core):
            core = points[0]
            legacy_core_index = 0
    if not present(core) or placeholder(core):
        missing.append("INNOVATION_PACKET.core_scientific_contribution")
    details["core_scientific_contribution_present"] = present(core)

    for index, point in enumerate(points):
        prefix = f"INNOVATION_PACKET.paper_innovation_bundle[{index}]"
        if not isinstance(point, dict):
            missing.append(f"{prefix} must be an object")
            continue
        for key in INNOVATION_BUNDLE_REQUIRED_KEYS:
            value = point.get(key)
            if not present(value) or placeholder(value):
                missing.append(f"{prefix}.{key}")
        source_role = normalized_role(point.get("source_role"))
        if source_role in TARGET_DOMAIN_ONLY_ROLES and not present(point.get("current_field_absence_evidence")):
            missing.append(f"{prefix}.current_field_absence_evidence required for target-domain-only innovation point")
        contribution_class = normalized_role(point.get("contribution_class"))
        if contribution_class and contribution_class not in CORE_CONTRIBUTION_CLASSES | SUPPORTING_CONTRIBUTION_CLASSES | NON_INNOVATION_CONTRIBUTION_CLASSES:
            missing.append(f"{prefix}.contribution_class must identify core, supporting, validation, analysis, or engineering support")
        if contribution_class in SUPPORTING_CONTRIBUTION_CLASSES and not present(point.get("counterfactual_necessity")):
            missing.append(f"{prefix}.counterfactual_necessity")

    supporting = packet.get("supporting_contributions")
    if supporting is not None and not isinstance(supporting, list):
        missing.append("INNOVATION_PACKET.supporting_contributions must be a list")
        supporting = []
    for index, point in enumerate(supporting or []):
        prefix = f"INNOVATION_PACKET.supporting_contributions[{index}]"
        if not isinstance(point, dict):
            missing.append(f"{prefix} must be an object")
            continue
        contribution_class = normalized_role(point.get("contribution_class") or "supporting_scientific_contribution")
        if contribution_class not in SUPPORTING_CONTRIBUTION_CLASSES | NON_INNOVATION_CONTRIBUTION_CLASSES:
            missing.append(f"{prefix}.contribution_class")
        for key in ["name", "evidence_refs", "validation_plan"]:
            if not present(point.get(key)) or placeholder(point.get(key)):
                missing.append(f"{prefix}.{key}")
        if contribution_class in SUPPORTING_CONTRIBUTION_CLASSES and not present(point.get("counterfactual_necessity")):
            missing.append(f"{prefix}.counterfactual_necessity")
    details["supporting_contribution_count"] = len(supporting or [])
    details["legacy_bundle_core_index"] = legacy_core_index

    if not require_storyline:
        return

    storyline = first_present(packet, ["paper_storyline", "storyline_contract", "storyline"])
    if not present(storyline):
        storyline = contract.get("paper_storyline") or contract.get("storyline")
    if not isinstance(storyline, dict):
        missing.append("INNOVATION_PACKET.paper_storyline")
        return
    for key in PAPER_STORYLINE_REQUIRED_KEYS:
        value = storyline.get(key)
        if not present(value) or placeholder(value):
            missing.append(f"INNOVATION_PACKET.paper_storyline.{key}")
    if story_step_count(storyline.get("narrative_spine")) < 5:
        missing.append("INNOVATION_PACKET.paper_storyline.narrative_spine must contain 5-7 sequential story steps")


def validate_evidence_import_gate(packet: dict[str, Any], missing: list[str], mode: str = "papernexus") -> None:
    gate = packet.get("evidence_import_gate")
    require_nested(gate, "INNOVATION_PACKET.evidence_import_gate", ["status", "reason", "launch_blocked"], missing)
    if not isinstance(gate, dict):
        return

    status = str(gate.get("status") or "").strip().lower()
    if status not in EVIDENCE_GATE_STATUSES:
        missing.append("INNOVATION_PACKET.evidence_import_gate.status must be passed, not_required, async_wait, or blocked")

    if mode == "external_material":
        if status != "not_required":
            missing.append("INNOVATION_PACKET.evidence_import_gate.status must be not_required for external_material")
        if str(gate.get("source_mode") or "").strip().lower() != "external_material":
            missing.append("INNOVATION_PACKET.evidence_import_gate.source_mode=external_material")
        if not present(gate.get("validation_ref")):
            missing.append("INNOVATION_PACKET.evidence_import_gate.validation_ref")
        if gate.get("mcp_attempted") is True:
            missing.append("INNOVATION_PACKET.evidence_import_gate.mcp_attempted must not be true for external_material")

    if status in {"passed", "not_required"}:
        if gate.get("launch_blocked") is True:
            missing.append("INNOVATION_PACKET.evidence_import_gate.launch_blocked must be false for passed/not_required")
        if not present(gate.get("material_refs")) and not present(gate.get("evidence_ids")):
            missing.append("INNOVATION_PACKET.evidence_import_gate.material_refs or evidence_ids")
        if mode == "papernexus" and status == "passed" and gate.get("mcp_attempted") is not True:
            missing.append("INNOVATION_PACKET.evidence_import_gate.mcp_attempted must be true when status is passed")

    if status in {"async_wait", "blocked"}:
        missing.append("INNOVATION_PACKET.evidence_import_gate must pass before launch")
        if gate.get("launch_blocked") is not True:
            missing.append("INNOVATION_PACKET.evidence_import_gate.launch_blocked must be true for async_wait/blocked")
        if not present(gate.get("claim_limits")):
            missing.append("INNOVATION_PACKET.evidence_import_gate.claim_limits")
        if not present(gate.get("attempts")):
            missing.append("INNOVATION_PACKET.evidence_import_gate.attempts")


def relpath(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def resolve_path(base: Path, value: Any) -> Path | None:
    return resolve_artifact_path(base, value)


def boundary_summary(packet: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    boundaries = packet.get("evidence_boundaries") or packet.get("evidenceBoundaries")
    missing: list[str] = []
    summary: dict[str, int] = {}
    if not isinstance(boundaries, dict):
        return summary, ["INNOVATION_PACKET.evidence_boundaries"]
    for key in ["source_backed", "agent_inferred", "speculative", "unsupported"]:
        value = boundaries.get(key) or boundaries.get(key.replace("_", "-")) or boundaries.get(key.replace("_", " "))
        if not present(value):
            missing.append(f"INNOVATION_PACKET.evidence_boundaries.{key}")
            summary[key] = 0
        elif isinstance(value, list):
            summary[key] = len(value)
        elif isinstance(value, dict):
            summary[key] = len(value)
        else:
            summary[key] = 1
    return summary, missing


def design_review_ready(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or payload.get("verdict") or payload.get("decision") or "").lower()
    return status in READY


def proposal_graph_controller_ready(base: Path, packet: dict[str, Any], details: dict[str, Any]) -> bool:
    manifest_value = first_present(
        packet,
        [
            "proposal_graph_session_manifest_path",
            "proposalSessionManifestPath",
            "proposal_session_manifest_path",
            "proposal_manifest_path",
        ],
    )
    result_value = first_present(
        packet,
        [
            "proposal_graph_session_path",
            "proposalGraphSessionPath",
            "proposal_session_path",
            "proposal_graph_session_result_path",
        ],
    )
    manifest_path = resolve_path(base, manifest_value) if manifest_value else None
    result_path = resolve_path(base, result_value) if result_value else base / "papernexus/proposal_graph_session.json"
    manifest = read_json(manifest_path) if manifest_path else None
    result = read_json(result_path) if result_path else None
    if not isinstance(manifest, dict) and isinstance(result, dict) and isinstance(result.get("manifest"), dict):
        manifest = result["manifest"]
    if not isinstance(manifest, dict):
        return False
    ready = (
        str(manifest.get("final_status") or "").strip().lower() == "committed"
        and present(manifest.get("committed_subgraph_id"))
        and present(manifest.get("controller_trace_paths"))
        and present(manifest.get("validation_report_paths"))
    )
    details["proposal_graph_session_manifest_path"] = relpath(base, manifest_path) if manifest_path else None
    details["proposal_graph_session_path"] = relpath(base, result_path) if result_path else None
    details["proposal_graph_controller_ready"] = ready
    details["proposal_graph_committed_subgraph_id"] = manifest.get("committed_subgraph_id")
    return ready


def validate_pre_idea_refs(base: Path, packet: dict[str, Any], missing: list[str], details: dict[str, Any]) -> None:
    gate_value = first_present(packet, ["pre_idea_evidence_gate_path", "preIdeaEvidenceGatePath"])
    slot_value = first_present(packet, ["innovation_slot_map_path", "innovationSlotMapPath"])
    consumed = first_present(packet, ["consumed_innovation_slot_ids", "consumedInnovationSlotIds", "innovation_slot_refs"])
    if not present(gate_value):
        missing.append("INNOVATION_PACKET.pre_idea_evidence_gate_path")
    else:
        gate_path = resolve_path(base, gate_value)
        gate = read_json(gate_path) if gate_path else None
        details["pre_idea_evidence_gate_path"] = relpath(base, gate_path) if gate_path else None
        if not isinstance(gate, dict):
            missing.append("INNOVATION_PACKET.pre_idea_evidence_gate_path target")
        elif str(gate.get("status") or "").strip().lower() != "passed" and not degraded_gate_approved(gate):
            missing.append("INNOVATION_PACKET.pre_idea_evidence_gate_path status passed")
    if not present(slot_value):
        missing.append("INNOVATION_PACKET.innovation_slot_map_path")
    else:
        slot_path = resolve_path(base, slot_value)
        slot_map = read_json(slot_path) if slot_path else None
        details["innovation_slot_map_path"] = relpath(base, slot_path) if slot_path else None
        if not isinstance(slot_map, dict):
            missing.append("INNOVATION_PACKET.innovation_slot_map_path target")
    if not present(consumed):
        missing.append("INNOVATION_PACKET.consumed_innovation_slot_ids")


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


def find_design_review(base: Path, packet: dict[str, Any]) -> tuple[Path | None, Any, bool]:
    explicit = first_present(packet, ["controller_design_review_path", "controllerDesignReviewPath", "design_review_path", "designReviewPath"])
    candidates: list[Path] = []
    if explicit:
        path = resolve_path(base, explicit)
        if path:
            candidates.append(path)
    candidates.extend(
        [
            base / "papernexus/research_controller/design-review.json",
            base / "ideation/PANEL_DESIGN_REVIEW.json",
        ]
    )
    for path in candidates:
        payload = read_json(path)
        if payload is not None:
            return path, payload, design_review_ready(payload)
    return None, None, False


def validate_external_identity_and_norms(
    base: Path,
    packet: dict[str, Any],
    gate: dict[str, Any],
    missing: list[str],
) -> None:
    for key in EXTERNAL_IDENTITY_FIELDS:
        if not present(packet.get(key)):
            missing.append(f"INNOVATION_PACKET.{key}")
    commitment_sha = str(packet.get("protected_commitment_sha256") or "").strip().lower()
    if len(commitment_sha) != 64 or any(char not in "0123456789abcdef" for char in commitment_sha):
        missing.append("INNOVATION_PACKET.protected_commitment_sha256")
    if present(packet.get("external_campaign_ref")) and str(packet.get("external_campaign_ref")) != str(gate.get("campaign_ref") or ""):
        missing.append("INNOVATION_PACKET.external_campaign_ref must match PRE_IDEA_EVIDENCE_GATE.campaign_ref")
    if present(packet.get("external_campaign_sha256")) and str(packet.get("external_campaign_sha256")) != str(gate.get("campaign_sha256") or ""):
        missing.append("INNOVATION_PACKET.external_campaign_sha256 must match PRE_IDEA_EVIDENCE_GATE.campaign_sha256")
    fragment_id = str(packet.get("selected_idea_fragment_id") or "").strip()
    candidate_id = str(packet.get("external_candidate_id") or "").strip()
    contract = packet.get("innovation_search_contract") if isinstance(packet.get("innovation_search_contract"), dict) else {}
    track_id = str(contract.get("track_id") or packet.get("track_id") or "").strip()
    if candidate_id and fragment_id and candidate_id == fragment_id:
        missing.append("INNOVATION_PACKET.external_candidate_id must remain distinct from selected_idea_fragment_id")
    if candidate_id and track_id and candidate_id == track_id:
        missing.append("INNOVATION_PACKET.external_candidate_id must remain distinct from track_id")

    norms = packet.get("external_evidence_norms") or packet.get("evidence_norms")
    if not isinstance(norms, dict):
        missing.append("INNOVATION_PACKET.external_evidence_norms or evidence_norms")
    else:
        for label, keys in [
            ("campaign_ref", ["campaign_ref", "external_campaign_ref"]),
            ("campaign_sha256", ["campaign_sha256", "external_campaign_sha256"]),
            ("source_integrity", ["source_integrity", "source_integrity_status"]),
            ("source_verification_limits", ["source_verification_limits", "verification_limits"]),
            ("claim_limits", ["claim_limits", "claim_boundary"]),
        ]:
            if not present(first_present(norms, keys)):
                missing.append(f"INNOVATION_PACKET.external_evidence_norms.{label}")
        norm_ref = first_present(norms, ["campaign_ref", "external_campaign_ref"])
        norm_hash = first_present(norms, ["campaign_sha256", "external_campaign_sha256"])
        if present(norm_ref) and str(norm_ref) != str(gate.get("campaign_ref") or ""):
            missing.append("INNOVATION_PACKET.external_evidence_norms.campaign_ref must match gate")
        if present(norm_hash) and str(norm_hash) != str(gate.get("campaign_sha256") or ""):
            missing.append("INNOVATION_PACKET.external_evidence_norms.campaign_sha256 must match gate")


def validate_external_panel_review(
    base: Path,
    packet: dict[str, Any],
    missing: list[str],
    details: dict[str, Any],
) -> None:
    path = base / "ideation/PANEL_DESIGN_REVIEW.json"
    payload = read_json(path)
    details["design_review_path"] = relpath(base, path)
    if not isinstance(payload, dict):
        missing.append("ideation/PANEL_DESIGN_REVIEW.json")
        return
    if not design_review_ready(payload):
        missing.append("PANEL_DESIGN_REVIEW.status/verdict passed or approved")
    reviewer = first_present(payload, ["reviewer_id", "reviewer", "reviewer_context_id"])
    author = first_present(payload, ["generation_author_id", "generation_author", "generator_id"])
    generation_context = first_present(payload, ["generation_context_ref", "generation_context_id", "author_context_ref"])
    review_context = first_present(payload, ["review_context_ref", "review_context_id", "reviewer_context_ref"])
    separated = payload.get("context_separated") is True or (
        present(generation_context)
        and present(review_context)
        and str(generation_context) != str(review_context)
    )
    if not present(reviewer):
        missing.append("PANEL_DESIGN_REVIEW.reviewer_id or reviewer")
    if not present(author) and not present(generation_context):
        missing.append("PANEL_DESIGN_REVIEW generation author/context identity")
    if present(reviewer) and present(author) and str(reviewer) == str(author):
        missing.append("PANEL_DESIGN_REVIEW reviewer must differ from generation author")
    if not separated:
        missing.append("PANEL_DESIGN_REVIEW.context_separated=true or distinct generation/review contexts")
    candidate_id = str(packet.get("external_candidate_id") or "").strip()
    refs = set()
    for key in ["external_candidate_id", "candidate_id", "candidate_refs", "reviewed_candidate_ids"]:
        value = payload.get(key)
        if isinstance(value, list):
            refs.update(str(item) for item in value if present(item))
        elif present(value):
            refs.add(str(value))
    if candidate_id and candidate_id not in refs:
        missing.append("PANEL_DESIGN_REVIEW must reference INNOVATION_PACKET.external_candidate_id")
    details["external_panel_review"] = {
        "status": payload.get("status"),
        "verdict": payload.get("verdict") or payload.get("decision"),
        "candidate_refs": sorted(refs),
        "context_separated": separated,
    }


def validate_passport_binding(
    base: Path, packet: dict[str, Any], missing: list[str], warnings: list[str]
) -> None:
    ref = str(packet.get("project_execution_passport_ref") or "").strip()
    passport_path = base / (ref or "resources/PROJECT_EXECUTION_PASSPORT.json")
    if not ref:
        if passport_path.exists():
            warnings.append("project execution passport exists but this legacy packet has no execution-profile binding")
        return
    passport = read_json(passport_path)
    if not isinstance(passport, dict) or not passport:
        missing.append("INNOVATION_PACKET.project_execution_passport_ref must resolve")
        return
    if str(packet.get("project_execution_passport_index_sha256") or "") != str(passport.get("index_semantic_sha256") or ""):
        missing.append("INNOVATION_PACKET.project_execution_passport_index_sha256 must match passport index")
    profile_id = str(packet.get("execution_profile_id") or "")
    profile = next(
        (
            item
            for item in passport.get("execution_profiles", [])
            if isinstance(item, dict) and str(item.get("profile_id") or "") == profile_id
        ),
        None,
    )
    if profile is None:
        missing.append("INNOVATION_PACKET.execution_profile_id must resolve one passport profile")
    elif str(packet.get("execution_profile_sha256") or "") != str(profile.get("execution_profile_sha256") or ""):
        missing.append("INNOVATION_PACKET.execution_profile_sha256 must match the selected profile")
    delta = packet.get("innovation_delta")
    if not isinstance(delta, dict) or not delta:
        missing.append("INNOVATION_PACKET.innovation_delta")
    elif str(packet.get("innovation_delta_sha256") or "") != canonical_sha256(delta):
        missing.append("INNOVATION_PACKET.innovation_delta_sha256 must match innovation_delta")
    projection = packet.get("resolved_execution_contract_projection")
    if isinstance(projection, dict) and str(packet.get("resolved_execution_contract_projection_sha256") or "") != canonical_sha256(projection):
        missing.append("INNOVATION_PACKET.resolved_execution_contract_projection_sha256 must match projection")


def validate_program_parameter_binding(
    base: Path,
    packet: dict[str, Any],
    missing: list[str],
    details: dict[str, Any],
) -> None:
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json") or {}
    mode = str(program.get("enforcement_mode") or "legacy")
    scope = str(program.get("claim_scope") or "dataset_specific")
    details["program_claim_contract_enforcement_mode"] = mode
    if mode != "enforced":
        return
    for field, expected in program_contract_binding(program).items():
        if packet.get(field) != expected:
            missing.append(f"INNOVATION_PACKET.{field} must match PROGRAM_CLAIM_CONTRACT.json")
    claim_role = str(packet.get("claim_role") or "")
    if scope == "cross_dataset_method" and claim_role == "method_candidate":
        contract = packet.get("parameter_transfer_contract")
        datasets = required_dataset_ids(program, packet)
        validation = validate_parameter_transfer_contract(contract, datasets)
        missing.extend(
            f"INNOVATION_PACKET.parameter_transfer_contract: {error}"
            for error in validation.get("errors") or []
        )
        if not present(packet.get("method_formula_sha256")):
            missing.append("INNOVATION_PACKET.method_formula_sha256")
        inventory = packet.get("parameter_role_inventory")
        if not isinstance(inventory, list) or not inventory:
            missing.append("INNOVATION_PACKET.parameter_role_inventory")
        else:
            load_bearing = []
            for index, row in enumerate(inventory):
                if not isinstance(row, dict):
                    missing.append(f"INNOVATION_PACKET.parameter_role_inventory[{index}] must be an object")
                    continue
                role = str(row.get("parameter_role") or "")
                if role not in VALID_PARAMETER_ROLES:
                    missing.append(f"INNOVATION_PACKET.parameter_role_inventory[{index}].parameter_role")
                if not present(row.get("parameter_name")):
                    missing.append(f"INNOVATION_PACKET.parameter_role_inventory[{index}].parameter_name")
                if role == "innovation_load_bearing":
                    load_bearing.append(row)
            if len(load_bearing) != 1:
                missing.append("INNOVATION_PACKET.parameter_role_inventory must contain exactly one innovation_load_bearing row")
            elif isinstance(contract, dict):
                if load_bearing[0].get("parameter_name") != contract.get("parameter_name"):
                    missing.append("INNOVATION_PACKET load-bearing inventory name must match parameter_transfer_contract")
                if load_bearing[0].get("parameter_transfer_contract_sha256") != contract.get(
                    "parameter_transfer_contract_sha256"
                ):
                    missing.append("INNOVATION_PACKET load-bearing inventory hash must match parameter_transfer_contract")


def lint_packet(project: str, packet_path: Path | None = None) -> dict[str, Any]:
    base = ar(project)
    path = packet_path or base / "orchestrator/INNOVATION_PACKET.json"
    packet = read_json(path)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    if not isinstance(packet, dict):
        missing.append(relpath(base, path))
        return {"complete": False, "status": "incomplete", "missing": missing, "warnings": warnings, "path": str(path)}

    mode, source_gate = evidence_source_mode(base, packet)
    details["evidence_source_mode"] = mode
    if mode not in {"papernexus", "external_material"}:
        missing.append("PRE_IDEA_EVIDENCE_GATE.evidence_source_mode must be papernexus or external_material")

    for key in REQUIRED:
        if not present(packet.get(key)):
            missing.append(f"INNOVATION_PACKET.{key}")
    if not present(packet.get("supporting_idea_fragment_ids")) and not present(packet.get("supportingIdeaFragmentIds")):
        missing.append("INNOVATION_PACKET.supporting_idea_fragment_ids")
    if not present(first_present(packet, ONE_VARIABLE_KEYS)):
        missing.append("INNOVATION_PACKET.one_variable_change")
    if not present(first_present(packet, FALSIFIER_KEYS)):
        missing.append("INNOVATION_PACKET.falsifier or failure_condition")
    if not present(first_present(packet, DATASET_KEYS)):
        missing.append("INNOVATION_PACKET.dataset_or_benchmark")

    validate_baseline_backend_paths(packet, missing, require_route=mode == "external_material")
    validate_innovation_contract(packet, missing)
    validate_paper_bundle(
        packet,
        missing,
        details,
        require_storyline=str(packet.get("track_role") or "primary").strip().lower() == "primary",
    )
    validate_evidence_import_gate(packet, missing, mode)
    validate_pre_idea_refs(base, packet, missing, details)
    validate_stability_seed_policy(packet, missing, warnings)
    validate_hpo_search_policy(packet, "INNOVATION_PACKET", missing, warnings)
    validate_passport_binding(base, packet, missing, warnings)
    validate_program_parameter_binding(base, packet, missing, details)
    if mode == "external_material":
        validate_external_identity_and_norms(base, packet, source_gate, missing)

    summary, boundary_missing = boundary_summary(packet)
    missing.extend(boundary_missing)
    details["evidence_boundary_summary"] = summary

    idea_support = lint_idea_support(project, path)
    details["idea_support"] = idea_support
    missing.extend(f"idea_support: {item}" for item in idea_support.get("missing", []))
    warnings.extend(f"idea_support: {item}" for item in idea_support.get("warnings", []))

    if mode == "external_material":
        validate_external_panel_review(base, packet, missing, details)
    else:
        caps = read_json(base / "capabilities.json") or {}
        controller_available = caps.get("research_controller_available") is True
        brief_value = first_present(packet, ["controller_innovation_brief_path", "controllerInnovationBriefPath", "innovation_brief_path"])
        brief_path = resolve_path(base, brief_value) if brief_value else None
        if controller_available and not brief_path:
            missing.append("INNOVATION_PACKET.controller_innovation_brief_path")
        if brief_path:
            brief = read_json(brief_path)
            if brief is None:
                missing.append(f"controller_innovation_brief_path target missing: {relpath(base, brief_path)}")
            elif str(brief.get("status", "")).lower() not in READY:
                missing.append("controller innovation brief status ready")
            details["controller_innovation_brief_path"] = relpath(base, brief_path)
        elif not controller_available:
            warnings.append("research_controller unavailable or unrecorded; controller innovation brief not required")

        proposal_controller_ready = proposal_graph_controller_ready(base, packet, details)
        design_path, design_payload, design_ready = find_design_review(base, packet)
        if design_payload is None and not proposal_controller_ready:
            missing.append("controller design review or fallback panel review")
        elif design_payload is not None and not design_ready and not proposal_controller_ready:
            missing.append("controller design review status/verdict ready")
        details["design_review_path"] = relpath(base, design_path) if design_path else None
        if proposal_controller_ready and design_payload is None:
            warnings.append("using committed proposal graph controller trace as design-review authority")

    evidence = first_present(packet, ["evidence_paths", "evidencePaths", "supporting_papers", "supportingPapers"])
    if not present(evidence):
        missing.append("INNOVATION_PACKET.evidence_paths or supporting_papers")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(path),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--packet")
    args = parser.parse_args()
    base = ar(args.project)
    path = resolve_artifact_path(base, args.packet) if args.packet else None
    out = lint_packet(args.project, path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
