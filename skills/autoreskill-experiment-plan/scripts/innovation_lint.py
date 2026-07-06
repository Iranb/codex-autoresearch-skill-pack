#!/usr/bin/env python3
"""Lint INNOVATION_PACKET experiment-plan authority."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from hpo_policy_lint import validate_hpo_search_policy


SKILL_ROOT = Path(__file__).resolve().parents[2]
PAPERNEXUS_SCRIPTS = SKILL_ROOT / "autoreskill-papernexus-innovation/scripts"
if str(PAPERNEXUS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PAPERNEXUS_SCRIPTS))

from idea_support_lint import lint_idea_support, resolve_artifact_path  # noqa: E402


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
ONE_VARIABLE_KEYS = ["one_variable_change", "oneVariableChange", "method_delta", "methodDelta", "intervention", "variable_change"]
FALSIFIER_KEYS = ["falsifier", "falsifiers", "failure_condition", "failure_conditions", "failureCondition", "stop_condition"]
DATASET_KEYS = ["dataset_or_benchmark", "datasetOrBenchmark", "dataset", "datasets", "benchmark", "benchmarks"]
READY = {"ready", "complete", "completed", "pass", "passed", "approved", "verified"}
BACKENDS = {"local_gpu", "autodl_gpu"}
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
PROBLEM_PROTOCOL_ROLES = {"problem_definition", "protocol", "benchmark", "evaluation", "metric"}
METHOD_ROLES = {"method_mechanism", "algorithm", "model", "architecture", "training_mechanism"}
PROOF_INTEGRATION_ROLES = {"training_integration", "system_integration", "theory_analysis", "ablation", "validation", "analysis"}
MAX_STABILITY_RANDOM_SEEDS = 3


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


def validate_baseline_backend_paths(packet: dict[str, Any], missing: list[str]) -> None:
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


def validate_paper_bundle(packet: dict[str, Any], missing: list[str], details: dict[str, Any]) -> None:
    contract = packet.get("innovation_search_contract") if isinstance(packet.get("innovation_search_contract"), dict) else {}
    bundle = first_present(packet, ["paper_innovation_bundle", "innovation_bundle", "three_innovation_bundle"])
    if not present(bundle):
        bundle = contract.get("paper_innovation_bundle") or contract.get("innovation_bundle")
    points = as_list(bundle)
    details["paper_innovation_bundle_count"] = len(points)
    if len(points) < 3:
        missing.append("INNOVATION_PACKET.paper_innovation_bundle must contain at least 3 paper-level innovation points")
        return
    roles: set[str] = set()
    transfer_source_count = 0
    for index, point in enumerate(points):
        prefix = f"INNOVATION_PACKET.paper_innovation_bundle[{index}]"
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
    details["paper_innovation_bundle_roles"] = sorted(roles)
    details["paper_innovation_bundle_transfer_source_count"] = transfer_source_count
    if not roles & PROBLEM_PROTOCOL_ROLES:
        missing.append("INNOVATION_PACKET.paper_innovation_bundle needs a problem/protocol/evaluation innovation point")
    if not roles & METHOD_ROLES:
        missing.append("INNOVATION_PACKET.paper_innovation_bundle needs a method/mechanism innovation point")
    if not roles & PROOF_INTEGRATION_ROLES:
        missing.append("INNOVATION_PACKET.paper_innovation_bundle needs a training/integration/analysis/validation innovation point")
    if transfer_source_count < 1:
        missing.append("INNOVATION_PACKET.paper_innovation_bundle needs at least one near/far/cross-lane or external transfer-backed point")

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


def validate_evidence_import_gate(packet: dict[str, Any], missing: list[str]) -> None:
    gate = packet.get("evidence_import_gate")
    require_nested(gate, "INNOVATION_PACKET.evidence_import_gate", ["status", "reason", "launch_blocked"], missing)
    if not isinstance(gate, dict):
        return

    status = str(gate.get("status") or "").strip().lower()
    if status not in EVIDENCE_GATE_STATUSES:
        missing.append("INNOVATION_PACKET.evidence_import_gate.status must be passed, not_required, async_wait, or blocked")

    if status in {"passed", "not_required"}:
        if gate.get("launch_blocked") is True:
            missing.append("INNOVATION_PACKET.evidence_import_gate.launch_blocked must be false for passed/not_required")
        if not present(gate.get("material_refs")) and not present(gate.get("evidence_ids")):
            missing.append("INNOVATION_PACKET.evidence_import_gate.material_refs or evidence_ids")
        if status == "passed" and gate.get("mcp_attempted") is not True:
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

    validate_baseline_backend_paths(packet, missing)
    validate_innovation_contract(packet, missing)
    validate_paper_bundle(packet, missing, details)
    validate_evidence_import_gate(packet, missing)
    validate_pre_idea_refs(base, packet, missing, details)
    validate_stability_seed_policy(packet, missing, warnings)
    validate_hpo_search_policy(packet, "INNOVATION_PACKET", missing, warnings)

    summary, boundary_missing = boundary_summary(packet)
    missing.extend(boundary_missing)
    details["evidence_boundary_summary"] = summary

    idea_support = lint_idea_support(project, path)
    details["idea_support"] = idea_support
    missing.extend(f"idea_support: {item}" for item in idea_support.get("missing", []))
    warnings.extend(f"idea_support: {item}" for item in idea_support.get("warnings", []))

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
