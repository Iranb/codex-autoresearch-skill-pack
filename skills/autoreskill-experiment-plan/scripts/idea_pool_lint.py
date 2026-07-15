#!/usr/bin/env python3
"""Lint the tiered ideation-stage experiment idea pool."""

from __future__ import annotations

import argparse
import json
import re
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
LIGHTWEIGHT_REQUIRED_KEYS = [
    "research_question",
    "core_scientific_contribution",
    "target_domain_anchor",
    "closest_prior_delta",
    "intervention",
    "mechanism",
    "predicted_pattern",
    "falsifier",
    "alternative_explanation",
    "cheapest_discriminating_experiment",
]
SHORTLIST_PAPER_KEYS = [
    "paper_thesis",
    "contribution_type",
    "target_venue_fit",
    "novelty_claim",
    "baseline_pressure",
    "minimum_experiment_table",
    "ablation_plan",
    "falsifier",
]
STORYLINE_REQUIRED_KEYS = [
    "opening_tension",
    "hidden_cause",
    "method_as_resolution",
    "proof_ladder",
    "reviewer_risk_and_defense",
    "narrative_spine",
]
OUTCOME_ROUTE_KEYS = ["positive", "negative", "inconclusive", "invalid"]
VALID_CONTRIBUTION_TYPES = {
    "method",
    "benchmark",
    "dataset",
    "evaluation",
    "analysis",
    "theory",
    "system",
    "engineering_method",
}
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
POOL_EXCEPTION_KINDS = {"niche_topic", "breadth_extension"}
SHARED_SIGNATURE_RELATIONS = {"duplicate", "merged", "ablation"}
SUPPORTING_CONTRIBUTION_CLASSES = {"supporting", "supporting_scientific_contribution"}
NON_INNOVATION_CONTRIBUTION_CLASSES = {"validation_role", "analysis_role", "engineering_support"}
GOE_REQUIRED_FIELDS = [
    "goe_path_refs",
    "closest_prior_delta",
    "mechanism_source_path",
    "negative_evidence_refs",
    "reviewer_attack_surface",
    "falsifier_probe",
    "track_seed_spec",
]


def project_root(project: str) -> Path:
    return Path(project).expanduser().resolve()


def resolve_artifact(project: str, raw: str) -> Path:
    root = project_root(project)
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return root / raw
    return root / ".autoreskill" / path


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
    return value is True or (isinstance(value, str) and value.strip().lower() in BAD_AUDIT_STRINGS)


def ideas_from_pool(pool: dict[str, Any], warnings: list[str]) -> list[Any]:
    ideas = pool.get("ideas")
    if isinstance(ideas, list):
        return ideas
    legacy = pool.get("candidates")
    if isinstance(legacy, list):
        warnings.append("legacy field `candidates` found; migrate to `ideas`")
        return legacy
    return []


def idea_source_backed(idea: dict[str, Any]) -> bool:
    return any(
        present(idea.get(key))
        for key in [
            "source_evidence_refs",
            "source_paper_or_technique",
            "paperNexus_evidence_ids",
            "derived_from_idea_fragment_ids",
            "proposal_session_ref",
            "proposal_graph_refs",
            "proposal_manifest_path",
        ]
    )


def trueish(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "y"})


def degraded_gate_approved(gate: dict[str, Any]) -> bool:
    if str(gate.get("status") or "").strip().lower() != "degraded_requires_user_approval":
        return False
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    return (
        isinstance(approval, dict)
        and approval.get("approved") is True
        and present(approval.get("approved_by"))
        and present(approval.get("approved_at"))
        and present(approval.get("reason"))
        and present(gate.get("claim_limits") or approval.get("claim_limits"))
    )


def normalized_role(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def causal_signature(idea: dict[str, Any]) -> str:
    explicit = normalized_text(idea.get("causal_signature"))
    if explicit:
        return explicit
    fields = [normalized_text(idea.get(key)) for key in ["intervention", "mechanism", "predicted_pattern"]]
    return " | ".join(fields) if all(fields) else ""


def pool_size_exception_valid(pool: dict[str, Any], count: int) -> bool:
    exception = pool.get("pool_size_exception")
    if not isinstance(exception, dict):
        return False
    kind = normalized_role(exception.get("kind"))
    if kind not in POOL_EXCEPTION_KINDS:
        return False
    if not all(present(exception.get(key)) for key in ["reason", "approved_by", "approved_at"]):
        return False
    if count < 8 and kind != "niche_topic":
        return False
    if count > 12 and kind != "breadth_extension":
        return False
    return True


def shortlist_ids(pool: dict[str, Any], ideas: list[Any]) -> set[str]:
    out = {str(value) for value in pool.get("shortlisted_idea_ids", []) if present(value)} if isinstance(pool.get("shortlisted_idea_ids"), list) else set()
    for idea in ideas:
        if isinstance(idea, dict) and normalized_role(idea.get("status")) in {"shortlisted", "selected"} and present(idea.get("id")):
            out.add(str(idea["id"]))
    return out


def validate_storyline(idea: dict[str, Any], prefix: str, missing: list[str]) -> bool:
    paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
    storyline = idea.get("paper_storyline") or paper.get("storyline") or paper.get("paper_storyline")
    if not isinstance(storyline, dict):
        missing.append(f"{prefix}.paper_contribution.storyline required for selected primary")
        return False
    ok = True
    for key in STORYLINE_REQUIRED_KEYS:
        if not present(storyline.get(key)):
            missing.append(f"{prefix}.paper_contribution.storyline.{key}")
            ok = False
    spine = storyline.get("narrative_spine")
    steps = [item for item in spine if present(item)] if isinstance(spine, list) else []
    if not 5 <= len(steps) <= 7:
        missing.append(f"{prefix}.paper_contribution.storyline.narrative_spine must contain 5-7 sequential steps")
        ok = False
    return ok


def validate_supporting_contributions(idea: dict[str, Any], prefix: str, missing: list[str]) -> None:
    values = idea.get("supporting_contributions")
    if values is None:
        return
    if not isinstance(values, list):
        missing.append(f"{prefix}.supporting_contributions must be a list")
        return
    for index, contribution in enumerate(values):
        item_prefix = f"{prefix}.supporting_contributions[{index}]"
        if not isinstance(contribution, dict):
            missing.append(f"{item_prefix} must be an object")
            continue
        contribution_class = normalized_role(
            contribution.get("contribution_class") or "supporting_scientific_contribution"
        )
        if contribution_class not in SUPPORTING_CONTRIBUTION_CLASSES | NON_INNOVATION_CONTRIBUTION_CLASSES:
            missing.append(f"{item_prefix}.contribution_class")
        for key in ["name", "evidence_refs", "validation_plan"]:
            if not present(contribution.get(key)):
                missing.append(f"{item_prefix}.{key}")
        if contribution_class in SUPPORTING_CONTRIBUTION_CLASSES and not present(contribution.get("counterfactual_necessity")):
            missing.append(f"{item_prefix}.counterfactual_necessity")


def validate_shortlist_depth(idea: dict[str, Any], prefix: str, selected: bool, missing: list[str]) -> str:
    paper = idea.get("paper_contribution")
    if not isinstance(paper, dict):
        missing.append(f"{prefix}.paper_contribution required for shortlisted ideas")
        return ""
    for key in SHORTLIST_PAPER_KEYS:
        if not present(paper.get(key)):
            missing.append(f"{prefix}.paper_contribution.{key}")
    contribution_type = normalized_role(paper.get("contribution_type"))
    if contribution_type in ENGINEERING_ONLY_TYPES:
        missing.append(f"{prefix}.paper_contribution.contribution_type is engineering-only; move it to SUPPORTING_ARTIFACTS.json")
    elif contribution_type and contribution_type not in VALID_CONTRIBUTION_TYPES:
        missing.append(f"{prefix}.paper_contribution.contribution_type must be one of {sorted(VALID_CONTRIBUTION_TYPES)}")
    for key in ["closest_prior_comparison", "claim_boundary"]:
        if not present(idea.get(key)) and not present(paper.get(key)):
            missing.append(f"{prefix}.{key}")
    routes = idea.get("outcome_routes")
    if not isinstance(routes, dict):
        missing.append(f"{prefix}.outcome_routes")
    else:
        for key in OUTCOME_ROUTE_KEYS:
            if not present(routes.get(key)):
                missing.append(f"{prefix}.outcome_routes.{key}")
    validate_supporting_contributions(idea, prefix, missing)
    if selected:
        validate_storyline(idea, prefix, missing)
    return contribution_type


def lint(pool: Any, require_selected: bool, project: str | None = None) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    pre_idea_degraded = False
    if not isinstance(pool, dict):
        return {"complete": False, "status": "incomplete", "missing": ["ideation/EXPERIMENT_IDEA_POOL.json"], "warnings": []}

    gate: Any = None
    pre_idea_gate = pool.get("pre_idea_evidence_gate") or pool.get("pre_idea_evidence_gate_path")
    if not present(pre_idea_gate):
        missing.append("pre_idea_evidence_gate_path")
    elif project:
        gate = read_json(resolve_artifact(project, str(pre_idea_gate)))
        if not isinstance(gate, dict):
            missing.append(f"pre_idea_evidence_gate_path target missing: {pre_idea_gate}")
        elif str(gate.get("status") or "").strip().lower() == "passed":
            pass
        elif degraded_gate_approved(gate):
            pre_idea_degraded = True
            warnings.append("pre-idea gate is approved degraded; preserve claim limits and evidence boundary")
        else:
            missing.append("pre_idea_evidence_gate_path status passed or approved degraded")
    if pre_idea_degraded:
        if not present(pool.get("claim_limits")):
            missing.append("claim_limits required for approved degraded pre-idea gate")
        if not present(pool.get("evidence_boundary") or pool.get("evidence_boundaries")):
            missing.append("evidence_boundary required for approved degraded pre-idea gate")

    slot_ids: set[str] = set()
    slot_map = pool.get("innovation_slot_map_path")
    if isinstance(gate, dict) and str(gate.get("evidence_source_mode") or "").strip().lower() == "external_material":
        expected_slot_map = str(gate.get("innovation_slot_map_path") or "").strip()
        if not expected_slot_map or str(slot_map or "").strip() != expected_slot_map:
            missing.append("innovation_slot_map_path must match the external PRE_IDEA_EVIDENCE_GATE")
    if not present(slot_map):
        (warnings if pre_idea_degraded else missing).append("innovation_slot_map_path")
    elif project:
        slot_payload = read_json(resolve_artifact(project, str(slot_map)))
        if not isinstance(slot_payload, dict):
            missing.append(f"innovation_slot_map_path target missing: {slot_map}")
        else:
            for key in ["challenge_clusters", "insight_clusters", "transfer_bridges", "anchor_nodes", "relation_patterns"]:
                for item in slot_payload.get(key, []) if isinstance(slot_payload.get(key), list) else []:
                    if isinstance(item, dict) and present(item.get("slot_id") or item.get("id")):
                        slot_ids.add(str(item.get("slot_id") or item.get("id")))

    ideas = ideas_from_pool(pool, warnings)
    count = len(ideas)
    exception_used = False
    if not 8 <= count <= 12:
        if 6 <= count <= 15 and pool_size_exception_valid(pool, count):
            exception_used = True
            warnings.append(f"explicit pool-size exception accepted for {count} ideas")
        else:
            missing.append(f"idea count must be 8-12 by default; 6-15 requires a recorded niche/breadth exception, got {count}")

    selected_id = str(pool.get("selected_idea_id") or pool.get("selected_candidate_id") or "").strip()
    selected_from_status = [
        str(idea.get("id"))
        for idea in ideas
        if isinstance(idea, dict) and normalized_role(idea.get("status")) == "selected" and present(idea.get("id"))
    ]
    if not selected_id and len(selected_from_status) == 1:
        selected_id = selected_from_status[0]
    if len(selected_from_status) > 1:
        missing.append("only one idea may have status=SELECTED")
    shortlist = shortlist_ids(pool, ideas)

    ids: set[str] = set()
    duplicate_ids: set[str] = set()
    signatures: dict[str, str] = {}
    type_counts = {"ALGO": 0, "CODE": 0, "PARAM": 0}
    maturity_counts: dict[str, int] = {}
    source_backed_count = 0
    transfer_method_count = 0
    deep_specified_count = 0

    for index, idea in enumerate(ideas):
        prefix = f"ideas[{index}]"
        if not isinstance(idea, dict):
            missing.append(f"{prefix} must be an object")
            continue
        idea_id = str(idea.get("id") or "").strip()
        if not idea_id:
            missing.append(f"{prefix}.id")
        elif idea_id in ids:
            duplicate_ids.add(idea_id)
        else:
            ids.add(idea_id)

        idea_type = str(idea.get("type") or "").upper()
        if idea_type not in VALID_TYPES:
            missing.append(f"{prefix}.type must be one of ALGO/CODE/PARAM")
        else:
            type_counts[idea_type] += 1
        for key in ["priority", "risk", "status", *LIGHTWEIGHT_REQUIRED_KEYS]:
            if not present(idea.get(key)):
                missing.append(f"{prefix}.{key}")

        signature = causal_signature(idea)
        if not signature:
            missing.append(f"{prefix}.causal_signature or complete intervention/mechanism/predicted_pattern")
        elif signature in signatures:
            relation = idea.get("causal_relation")
            relation_type = normalized_role(relation.get("type")) if isinstance(relation, dict) else ""
            related_id = str(relation.get("related_idea_id") or "") if isinstance(relation, dict) else ""
            if relation_type not in SHARED_SIGNATURE_RELATIONS or related_id != signatures[signature]:
                missing.append(f"{prefix}.causal_signature duplicates {signatures[signature]}; merge it or mark an explicit duplicate/ablation relation")
        else:
            signatures[signature] = idea_id or prefix

        paper_potential = idea.get("paper_potential")
        if not isinstance(paper_potential, dict):
            missing.append(f"{prefix}.paper_potential")
        else:
            for key in ["target_claim", "minimum_experiment_table", "reviewer_risk"]:
                if not present(paper_potential.get(key)):
                    missing.append(f"{prefix}.paper_potential.{key}")

        maturity = normalized_role(idea.get("evidence_maturity"))
        if maturity not in VALID_EVIDENCE_MATURITY:
            missing.append(f"{prefix}.evidence_maturity must be one of {sorted(VALID_EVIDENCE_MATURITY)}")
        else:
            maturity_counts[maturity] = maturity_counts.get(maturity, 0) + 1
        if idea_source_backed(idea):
            source_backed_count += 1
        elif not present(idea.get("evidence_debt") or idea.get("missing_materials")):
            missing.append(f"{prefix}.source_evidence_refs or evidence_debt")

        audit = idea.get("red_line_audit")
        if not isinstance(audit, dict):
            missing.append(f"{prefix}.red_line_audit")
        else:
            for key in AUDIT_KEYS:
                if key not in audit:
                    missing.append(f"{prefix}.red_line_audit.{key}")
                elif audit_violation(audit.get(key)):
                    missing.append(f"{prefix}.red_line_audit.{key} indicates a red-line violation")

        is_selected = idea_id == selected_id
        is_shortlisted = idea_id in shortlist or is_selected
        contribution_type = ""
        if is_shortlisted:
            contribution_type = validate_shortlist_depth(idea, prefix, is_selected, missing)
            deep_specified_count += 1
        else:
            validate_supporting_contributions(idea, prefix, missing)
        if idea_type == "CODE" and is_shortlisted:
            if contribution_type not in CODE_PAPER_TYPES:
                missing.append(f"{prefix}.paper_contribution.contribution_type for CODE ideas must be one of {sorted(CODE_PAPER_TYPES)}")
            paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
            if not present(paper.get("performance_claim")):
                missing.append(f"{prefix}.paper_contribution.performance_claim")
        paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
        if trueish(paper.get("standalone_engineering")):
            missing.append(f"{prefix}.paper_contribution.standalone_engineering must be false")

        method_bearing = idea_type in {"ALGO", "CODE"} or contribution_type in METHOD_BEARING_CONTRIBUTIONS
        if method_bearing:
            target = warnings if pre_idea_degraded and not is_shortlisted else missing
            source_role = normalized_role(idea.get("primary_method_source_role") or idea.get("method_source_role"))
            if source_role in TARGET_DOMAIN_ONLY_ROLES:
                if not present(idea.get("current_field_absence_evidence")):
                    target.append(f"{prefix}.current_field_absence_evidence required for target-domain-only main method")
            elif source_role not in VALID_METHOD_SOURCE_ROLES:
                target.append(f"{prefix}.primary_method_source_role")
            else:
                transfer_method_count += 1

        if is_shortlisted:
            for field in GOE_REQUIRED_FIELDS:
                if not present(idea.get(field)):
                    missing.append(f"{prefix}.{field}")
            seed_spec = idea.get("track_seed_spec") if isinstance(idea.get("track_seed_spec"), dict) else {}
            for key in ["one_variable_change", "expected_metric_effect", "kill_condition"]:
                if not present(seed_spec.get(key)):
                    missing.append(f"{prefix}.track_seed_spec.{key}")

        slot_refs = idea.get("innovation_slot_refs") or idea.get("slot_refs") or idea.get("supporting_slot_ids")
        if not present(slot_refs) and not present(idea.get("evidence_debt") or idea.get("missing_materials")):
            missing.append(f"{prefix}.innovation_slot_refs or evidence_debt")
        if present(slot_refs) and slot_ids:
            refs = slot_refs if isinstance(slot_refs, list) else [slot_refs]
            unknown = sorted({str(ref) for ref in refs if str(ref) not in slot_ids})
            if unknown:
                missing.append(f"{prefix}.innovation_slot_refs unknown slot ids: {', '.join(unknown)}")

    if duplicate_ids:
        missing.append("duplicate idea ids: " + ", ".join(sorted(duplicate_ids)))
    if type_counts["PARAM"] > 2:
        missing.append(f"PARAM ideas must be <= 2, got {type_counts['PARAM']}")
    if type_counts["CODE"] > 4:
        missing.append(f"CODE ideas must be <= 4, got {type_counts['CODE']}")
    if require_selected and not selected_id:
        missing.append("selected_idea_id or exactly one idea with status=SELECTED")
    if selected_id and selected_id not in ids:
        missing.append(f"selected_idea_id {selected_id!r} is not in ideas")
    unknown_shortlist = sorted(shortlist - ids)
    if unknown_shortlist:
        missing.append("shortlisted_idea_ids unknown idea ids: " + ", ".join(unknown_shortlist))

    protocol = pool.get("locked_protocol")
    if not isinstance(protocol, dict):
        warnings.append("locked_protocol may remain incomplete during brainstorming but must close before launch")
    else:
        for key in ["dataset", "primary_metric", "baseline_eval_protocol", "evaluation_command"]:
            if not present(protocol.get(key)):
                warnings.append(f"locked_protocol.{key} missing; close it in experiment_plan")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "idea_count": count,
        "pool_size_exception_used": exception_used,
        "type_counts": type_counts,
        "source_backed_count": source_backed_count,
        "transfer_method_count": transfer_method_count,
        "shortlist_count": len(shortlist),
        "deep_specified_count": deep_specified_count,
        "causal_signature_count": len(signatures),
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
