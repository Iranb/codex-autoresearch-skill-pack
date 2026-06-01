#!/usr/bin/env python3
"""Lint the ideation-stage experiment idea pool before implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AUDIT_KEYS = [
    "metric_drift",
    "eval_drift",
    "dataset_drift",
    "data_leakage",
    "prediction_cheating",
    "training_budget_drift",
]
VALID_TYPES = {"ALGO", "CODE", "PARAM"}
BAD_AUDIT_STRINGS = {"true", "yes", "fail", "failed", "violation", "drift", "cheat", "leak"}
PAPER_REQUIRED_KEYS = [
    "paper_thesis",
    "contribution_type",
    "target_venue_fit",
    "novelty_claim",
    "baseline_pressure",
    "minimum_experiment_table",
    "ablation_plan",
    "falsifier",
]
VALID_CONTRIBUTION_TYPES = {"method", "benchmark", "dataset", "evaluation", "analysis", "theory", "system", "engineering_method"}
CODE_PAPER_TYPES = {"method", "benchmark", "dataset", "evaluation", "system", "engineering_method"}
ENGINEERING_ONLY_TYPES = {"engineering_support", "infrastructure", "tooling", "dashboard", "script"}
VALID_EVIDENCE_MATURITY = {"blue_sky", "promising", "evidence_backed", "plan_ready"}
VALID_METHOD_SOURCE_ROLES = {
    "near_neighbor",
    "far_neighbor",
    "cross_lane_recombination",
    "proposal_graph_transfer",
    "external_domain_transfer",
    "target_domain_absence_proven",
}
TARGET_DOMAIN_ONLY_ROLES = {"target_domain", "current_field", "target_domain_only"}
METHOD_BEARING_CONTRIBUTIONS = {"method", "engineering_method", "system"}


def project_root(project: str) -> Path:
    return Path(project).expanduser().resolve()


def resolve_artifact(project: str, raw: str) -> Path:
    root = project_root(project)
    base = root / ".autoreskill"
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return root / raw
    return base / path


def read_json(path: Path) -> Any:
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
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def audit_violation(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in BAD_AUDIT_STRINGS:
        return True
    return False


def ideas_from_pool(pool: dict[str, Any], warnings: list[str]) -> list[Any]:
    ideas = pool.get("ideas")
    if isinstance(ideas, list):
        return ideas
    legacy = pool.get("candidates")
    if isinstance(legacy, list):
        warnings.append("legacy field `candidates` found; use `ideas` because the 12-15 items are optimization ideas")
        return legacy
    return []


def idea_source_backed(idea: dict[str, Any]) -> bool:
    return any(
        present(idea.get(key))
        for key in [
            "source_paper_or_technique",
            "paperNexus_evidence_ids",
            "derived_from_idea_fragment_ids",
            "proposal_session_ref",
            "proposal_graph_refs",
            "proposal_manifest_path",
        ]
    )


def trueish(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y"}:
        return True
    return False


def degraded_gate_approved(gate: dict[str, Any]) -> bool:
    if str(gate.get("status") or "").strip().lower() != "degraded_requires_user_approval":
        return False
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return False
    if not present(approval.get("approved_by")) or not present(approval.get("approved_at")) or not present(approval.get("reason")):
        return False
    return present(gate.get("claim_limits") or approval.get("claim_limits"))


def normalized_role(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def lint(pool: Any, require_selected: bool, project: str | None = None) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    pre_idea_degraded = False

    if not isinstance(pool, dict):
        return {
            "complete": False,
            "status": "incomplete",
            "missing": ["ideation/EXPERIMENT_IDEA_POOL.json"],
            "warnings": [],
        }

    pre_idea_gate = pool.get("pre_idea_evidence_gate") or pool.get("pre_idea_evidence_gate_path")
    if not present(pre_idea_gate):
        missing.append("pre_idea_evidence_gate_path")
    elif project:
        gate_path = resolve_artifact(project, str(pre_idea_gate))
        gate = read_json(gate_path)
        if not isinstance(gate, dict):
            missing.append(f"pre_idea_evidence_gate_path target missing: {pre_idea_gate}")
        else:
            gate_status = str(gate.get("status") or "").strip().lower()
            if gate_status == "passed":
                pre_idea_degraded = False
            elif degraded_gate_approved(gate):
                pre_idea_degraded = True
                warnings.append("pre_idea_evidence_gate_path is approved degraded; idea pool must keep claim_limits and evidence_boundary")
            else:
                missing.append("pre_idea_evidence_gate_path status passed or approved degraded")
    if pre_idea_degraded:
        if not present(pool.get("claim_limits")):
            missing.append("claim_limits required for approved degraded pre-idea gate")
        if not present(pool.get("evidence_boundary")) and not present(pool.get("evidence_boundaries")):
            missing.append("evidence_boundary required for approved degraded pre-idea gate")
    slot_map = pool.get("innovation_slot_map_path")
    if not present(slot_map):
        if pre_idea_degraded:
            warnings.append("innovation_slot_map_path missing under approved degraded pre-idea gate; experiment_plan must close selected evidence before launch")
        else:
            missing.append("innovation_slot_map_path")
        slot_ids: set[str] = set()
    elif project:
        slot_path = resolve_artifact(project, str(slot_map))
        slot_payload = read_json(slot_path)
        if not isinstance(slot_payload, dict):
            missing.append(f"innovation_slot_map_path target missing: {slot_map}")
            slot_ids = set()
        else:
            slot_ids = set()
            for key in ["challenge_clusters", "insight_clusters", "transfer_bridges", "anchor_nodes", "relation_patterns"]:
                value = slot_payload.get(key)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            raw_id = item.get("slot_id") or item.get("id")
                            if raw_id:
                                slot_ids.add(str(raw_id))
    else:
        slot_ids = set()

    ideas = ideas_from_pool(pool, warnings)

    count = len(ideas)
    if count < 12 or count > 15:
        missing.append(f"idea count must be 12-15, got {count}")

    ids: set[str] = set()
    duplicate_ids: set[str] = set()
    type_counts = {"ALGO": 0, "CODE": 0, "PARAM": 0}
    selected_ideas: list[str] = []
    source_backed_algo = 0
    paper_ready_count = 0
    maturity_counts: dict[str, int] = {}
    transfer_method_count = 0

    for index, idea in enumerate(ideas):
        prefix = f"ideas[{index}]"
        if not isinstance(idea, dict):
            missing.append(f"{prefix} must be an object")
            continue
        contribution_type = ""

        idea_id = str(idea.get("id") or "").strip()
        if not idea_id:
            missing.append(f"{prefix}.id")
        elif idea_id in ids:
            duplicate_ids.add(idea_id)
        else:
            ids.add(idea_id)

        itype = str(idea.get("type") or "").upper()
        if itype not in VALID_TYPES:
            missing.append(f"{prefix}.type must be one of ALGO/CODE/PARAM")
        else:
            type_counts[itype] += 1

        for key in ["priority", "risk", "description", "hypothesis", "one_variable_change", "expected_metric_impact", "implementation_scope", "status"]:
            if not present(idea.get(key)):
                missing.append(f"{prefix}.{key}")

        if itype == "ALGO" and idea_source_backed(idea):
            source_backed_algo += 1

        maturity = str(idea.get("evidence_maturity") or "").strip().lower()
        if maturity:
            maturity_counts[maturity] = maturity_counts.get(maturity, 0) + 1
            if maturity not in VALID_EVIDENCE_MATURITY:
                warnings.append(f"{prefix}.evidence_maturity should be one of {sorted(VALID_EVIDENCE_MATURITY)}")
        else:
            warnings.append(f"{prefix}.evidence_maturity missing; mark brainstorm maturity as blue_sky/promising/evidence_backed/plan_ready")

        if maturity in {"blue_sky", "promising"}:
            if not present(idea.get("missing_materials")):
                warnings.append(f"{prefix}.missing_materials recommended for {maturity} ideas")
            if not present(idea.get("followup_evidence_plan")):
                warnings.append(f"{prefix}.followup_evidence_plan recommended for {maturity} ideas")

        if str(idea.get("status") or "").lower() == "selected" and idea_id:
            selected_ideas.append(idea_id)

        audit = idea.get("red_line_audit")
        if not isinstance(audit, dict):
            missing.append(f"{prefix}.red_line_audit")
        else:
            for key in AUDIT_KEYS:
                if key not in audit:
                    missing.append(f"{prefix}.red_line_audit.{key}")
                elif audit_violation(audit.get(key)):
                    missing.append(f"{prefix}.red_line_audit.{key} indicates a red-line violation")

        paper = idea.get("paper_contribution")
        paper_ok = True
        if not isinstance(paper, dict):
            missing.append(f"{prefix}.paper_contribution")
            paper_ok = False
        else:
            for key in PAPER_REQUIRED_KEYS:
                if not present(paper.get(key)):
                    missing.append(f"{prefix}.paper_contribution.{key}")
                    paper_ok = False
            contribution_type = str(paper.get("contribution_type") or "").strip().lower()
            if contribution_type in ENGINEERING_ONLY_TYPES:
                missing.append(f"{prefix}.paper_contribution.contribution_type is engineering-only; move this item to SUPPORTING_ARTIFACTS.json")
                paper_ok = False
            elif contribution_type and contribution_type not in VALID_CONTRIBUTION_TYPES:
                missing.append(f"{prefix}.paper_contribution.contribution_type must be one of {sorted(VALID_CONTRIBUTION_TYPES)}")
                paper_ok = False
            if itype == "CODE":
                if contribution_type not in CODE_PAPER_TYPES:
                    missing.append(f"{prefix}.paper_contribution.contribution_type for CODE ideas must be one of {sorted(CODE_PAPER_TYPES)}")
                    paper_ok = False
                if not present(paper.get("performance_claim")):
                    missing.append(f"{prefix}.paper_contribution.performance_claim")
                    paper_ok = False
            if trueish(paper.get("standalone_engineering")):
                missing.append(f"{prefix}.paper_contribution.standalone_engineering must be false")
                paper_ok = False
        if paper_ok:
            paper_ready_count += 1

        method_bearing = itype in {"ALGO", "CODE"} or contribution_type in METHOD_BEARING_CONTRIBUTIONS
        if method_bearing:
            source_role = normalized_role(idea.get("primary_method_source_role") or idea.get("method_source_role"))
            if not source_role:
                missing.append(f"{prefix}.primary_method_source_role")
            elif source_role in TARGET_DOMAIN_ONLY_ROLES:
                if not present(idea.get("current_field_absence_evidence")):
                    missing.append(f"{prefix}.current_field_absence_evidence required for target-domain-only main method")
            elif source_role not in VALID_METHOD_SOURCE_ROLES:
                missing.append(f"{prefix}.primary_method_source_role must be near/far-neighbor transfer, cross-lane recombination, proposal-graph transfer, external-domain transfer, or target_domain_absence_proven")
            else:
                transfer_method_count += 1
            for key in ["target_domain_anchor", "neighbor_transfer_mechanism", "target_domain_method_overlap_risk"]:
                if not present(idea.get(key)):
                    missing.append(f"{prefix}.{key}")
            if source_role in {"near_neighbor", "far_neighbor", "cross_lane_recombination", "proposal_graph_transfer", "external_domain_transfer"} and not present(idea.get("neighbor_transfer_mechanism")):
                missing.append(f"{prefix}.neighbor_transfer_mechanism")

        slot_refs = idea.get("innovation_slot_refs") or idea.get("slot_refs") or idea.get("supporting_slot_ids")
        degraded = str(idea.get("evidence_maturity") or "").strip().lower() in {"blue_sky", "promising"}
        if not present(slot_refs) and not degraded:
            missing.append(f"{prefix}.innovation_slot_refs or explicit low-maturity evidence debt")
        if present(slot_refs) and slot_ids:
            refs = slot_refs if isinstance(slot_refs, list) else [slot_refs]
            unknown = sorted({str(ref) for ref in refs if str(ref) not in slot_ids})
            if unknown:
                missing.append(f"{prefix}.innovation_slot_refs unknown slot ids: {', '.join(unknown)}")

    if duplicate_ids:
        missing.append("duplicate idea ids: " + ", ".join(sorted(duplicate_ids)))

    if paper_ready_count != count:
        missing.append(f"all ideas must be academic-paper-oriented, got {paper_ready_count}/{count} with complete paper_contribution")
    if type_counts["PARAM"] > 2:
        missing.append(f"PARAM ideas must be <= 2, got {type_counts['PARAM']}")
    if type_counts["CODE"] > 4:
        missing.append(f"CODE ideas must be <= 4 and only performance-bearing engineering-method or benchmark/evaluation/dataset/system paper contributions, got {type_counts['CODE']}")
    if type_counts["ALGO"] < 8:
        missing.append(f"need at least 8 ALGO paper ideas, got {type_counts['ALGO']}")
    if transfer_method_count < 8:
        missing.append(f"need at least 8 method ideas with near/far-neighbor or cross-lane primary method source, got {transfer_method_count}")
    if source_backed_algo < 6:
        warnings.append(f"prefer at least 6 ALGO ideas with source paper/technique or PaperNexus evidence when available, got {source_backed_algo}; do not block brainstorm, record evidence debt instead")

    selected_id = str(pool.get("selected_idea_id") or pool.get("selected_candidate_id") or "").strip()
    if require_selected and not selected_id and not selected_ideas:
        missing.append("selected_idea_id or one idea with status=SELECTED")
    if selected_id and selected_id not in ids:
        missing.append(f"selected_idea_id {selected_id!r} is not in ideas")

    protocol = pool.get("locked_protocol")
    if not isinstance(protocol, dict):
        warnings.append("locked_protocol missing; allowed during brainstorming, but experiment_plan must lock dataset/metric/eval/baseline before launch")
    else:
        for key in ["dataset", "primary_metric", "baseline_eval_protocol", "evaluation_command"]:
            if not present(protocol.get(key)):
                warnings.append(f"locked_protocol.{key} missing; allowed during brainstorming, must be closed in experiment_plan")
        if not present(protocol.get("metric_direction")):
            warnings.append("locked_protocol.metric_direction missing; default higher may be assumed")
        if not present(protocol.get("protected_paths")):
            warnings.append("protected_paths missing; hash eval/test/metric files when available")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "idea_count": count,
        "type_counts": type_counts,
        "source_backed_algo_count": source_backed_algo,
        "transfer_method_count": transfer_method_count,
        "paper_ready_count": paper_ready_count,
        "evidence_maturity_counts": maturity_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--pool", default="ideation/EXPERIMENT_IDEA_POOL.json")
    parser.add_argument("--require-selected", action="store_true")
    args = parser.parse_args()

    path = resolve_artifact(args.project, args.pool)
    out = lint(read_json(path), args.require_selected, args.project)
    out["path"] = str(path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
