#!/usr/bin/env python3
"""Lint post-idea novelty and venue-support scorecards."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DIMENSIONS = [
    "significance",
    "novelty_separation",
    "experiment_defensibility",
    "feasibility",
    "evidence_maturity",
    "risk_control",
]
PROMOTION_DECISIONS = {"advance", "advance_with_constraints", "park", "kill"}
RECOMMENDED_TRACK_ACTIONS = {"primary", "alternate", "risk_repair", "mechanism_variant", "park", "kill"}
EVIDENCE_CLOSURE_LEVELS = {"graph_closed", "source_backed", "split_read", "metadata_only", "degraded", "blocked", "needs_closure"}
PAPER_COMPARISON_KEYS = [
    "closest_prior_papers",
    "innovation_comparison",
    "overlap_risk",
    "differentiation_claim",
]
SHORTLIST_ASSESSMENT_KEYS = [
    "core_contribution_verdict",
    "storyline_readiness",
    "weakest_causal_link",
    "required_story_repair",
]
PAIRWISE_COMPARISON_KEYS = [
    "closest_competing_idea_id",
    "mechanism_difference",
    "predicted_pattern_difference",
    "cheapest_discriminator",
    "verdict",
]
PAIRWISE_VERDICTS = {"distinct", "redundant", "ablation", "uncertain"}
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
STORYLINE_KEYS = [
    "opening_tension",
    "hidden_cause",
    "method_as_resolution",
    "proof_ladder",
    "reviewer_risk_and_defense",
    "narrative_spine",
]
VALID_METHOD_SOURCE_ROLES = {
    "near_neighbor",
    "far_neighbor",
    "cross_lane_recombination",
    "proposal_graph_transfer",
    "external_domain_transfer",
    "target_domain_absence_proven",
}
TARGET_DOMAIN_ONLY_ROLES = {"target_domain", "current_field", "target_domain_only"}
EVIDENCE_SOURCE_MODES = {"papernexus", "external_material"}


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def positive_finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def deterministic_rank_tuple(row: dict[str, Any], idea: dict[str, Any]) -> list[Any] | None:
    targets = string_list(row.get("unique_decision_targets") or row.get("decision_target_refs"))
    if not targets:
        target = row.get("decision_target") or idea.get("claim_target")
        targets = [str(target)] if present(target) else []
    cost = positive_finite(
        row.get("estimated_falsifier_gpu_hours")
        or row.get("estimated_gpu_hours")
        or idea.get("estimated_falsifier_gpu_hours")
        or idea.get("estimated_gpu_hours")
    )
    if not targets or cost is None:
        return None
    resolved = row.get("competing_hypotheses_resolved_count")
    try:
        resolved_count = max(0, int(resolved))
    except (TypeError, ValueError):
        resolved_count = len(string_list(row.get("competing_hypotheses_resolved"))) or len(set(targets))
    reuse_count = len(set(string_list(row.get("reusable_invariant_refs") or idea.get("reusable_invariant_refs"))))
    risk_count = len(
        set(
            string_list(
                row.get("reviewer_risks")
                or row.get("reviewer_attack_surface")
                or idea.get("reviewer_risks")
                or idea.get("red_line_risks")
            )
        )
    )
    density = len(set(targets)) / cost
    return [
        0 if row.get("changes_core_claim") is True or idea.get("changes_core_claim") is True else 1,
        -resolved_count,
        -density,
        cost,
        -reuse_count,
        risk_count,
        str(idea.get("id") or row.get("idea_id") or row.get("id") or ""),
    ]


def project_root(project: str) -> Path:
    return Path(project).expanduser().resolve()


def ar(project: str) -> Path:
    return project_root(project) / ".autoreskill"


def resolve(base: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return base.parent / raw
    return base / path


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def source_mode(gate: Any) -> str:
    if not isinstance(gate, dict):
        return "papernexus"
    return str(gate.get("evidence_source_mode") or "papernexus").strip().lower()


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        out = {"stdout": proc.stdout}
    if not isinstance(out, dict):
        out = {"result": out}
    out.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        out["stderr"] = proc.stderr.strip()
    return out


def external_alignment(project: str, stage: str) -> dict[str, Any]:
    script = Path(__file__).resolve().parents[2] / "autoreskill-gpu-idea-validation/scripts/external_alignment_lint.py"
    if not script.is_file():
        return {
            "complete": False,
            "missing": ["autoreskill-gpu-idea-validation/scripts/external_alignment_lint.py"],
            "warnings": [],
            "returncode": 1,
        }
    return run_json(
        [
            sys.executable,
            str(script),
            "--project",
            str(project_root(project)),
            "--stage",
            stage,
        ]
    )


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def score_ok(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 1 <= float(value) <= 5
    return False


def positive_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    return False


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


def recommendation_ids(value: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(value, list):
        return out
    for item in value:
        raw = item.get("idea_id") or item.get("id") if isinstance(item, dict) else item
        if present(raw):
            out.add(str(raw))
    return out


def validate_shortlist_idea(idea: dict[str, Any], prefix: str, selected: bool, missing: list[str]) -> None:
    paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
    if not paper:
        missing.append(f"{prefix}.paper_contribution required for shortlisted ideas")
        return
    for key in SHORTLIST_PAPER_KEYS:
        if not present(paper.get(key)):
            missing.append(f"{prefix}.paper_contribution.{key}")
    if not present(idea.get("closest_prior_comparison") or paper.get("closest_prior_comparison")):
        missing.append(f"{prefix}.closest_prior_comparison")
    if not present(idea.get("claim_boundary") or paper.get("claim_boundary")):
        missing.append(f"{prefix}.claim_boundary")
    routes = idea.get("outcome_routes")
    if not isinstance(routes, dict):
        missing.append(f"{prefix}.outcome_routes")
    else:
        for key in ["positive", "negative", "inconclusive", "invalid"]:
            if not present(routes.get(key)):
                missing.append(f"{prefix}.outcome_routes.{key}")
    if selected:
        storyline = idea.get("paper_storyline") or paper.get("storyline") or paper.get("paper_storyline")
        if not isinstance(storyline, dict):
            missing.append(f"{prefix}.paper_contribution.storyline required for selected primary")
        else:
            for key in STORYLINE_KEYS:
                if not present(storyline.get(key)):
                    missing.append(f"{prefix}.paper_contribution.storyline.{key}")


def degraded_gate_approved(gate: dict[str, Any]) -> bool:
    if str(gate.get("status") or "").strip().lower() != "degraded_requires_user_approval":
        return False
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return False
    if not present(approval.get("approved_by")) or not present(approval.get("approved_at")) or not present(approval.get("reason")):
        return False
    return present(gate.get("claim_limits") or approval.get("claim_limits"))


def ideas_from_pool(pool: Any) -> list[dict[str, Any]]:
    if isinstance(pool, dict) and isinstance(pool.get("ideas"), list):
        return [row for row in pool["ideas"] if isinstance(row, dict)]
    return []


def rows_from_scorecard(scorecard: Any) -> list[dict[str, Any]]:
    if isinstance(scorecard, dict):
        for key in ["ideas", "scores", "scorecard", "rows"]:
            if isinstance(scorecard.get(key), list):
                return [row for row in scorecard[key] if isinstance(row, dict)]
    return []


def lint(project: str, scorecard_rel: str, pool_rel: str) -> dict[str, Any]:
    base = ar(project)
    program_contract = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json") or {}
    program_mode = str(program_contract.get("enforcement_mode") or "legacy").strip().lower() if isinstance(program_contract, dict) else "legacy"
    program_scope = str(program_contract.get("claim_scope") or "dataset_specific").strip().lower() if isinstance(program_contract, dict) else "dataset_specific"
    required_program_datasets = [
        str(item.get("dataset_id"))
        for item in (program_contract.get("target_datasets") or [])
        if isinstance(item, dict) and item.get("required") is True and present(item.get("dataset_id"))
    ] if isinstance(program_contract, dict) else []
    scorecard_path = resolve(base, scorecard_rel)
    pool_path = resolve(base, pool_rel)
    scorecard = read_json(scorecard_path)
    pool = read_json(pool_path)
    ideas = ideas_from_pool(pool)
    rows = rows_from_scorecard(scorecard)
    missing: list[str] = []
    warnings: list[str] = []

    if not isinstance(scorecard, dict):
        return {
            "complete": False,
            "status": "incomplete",
            "missing": [scorecard_rel],
            "warnings": [],
            "path": str(scorecard_path),
        }

    schema_version = scorecard.get("schema_version", 1)
    deterministic_schema = isinstance(schema_version, int) and schema_version >= 2
    if deterministic_schema and not present(scorecard.get("selection_revision")):
        missing.append("selection_revision")
    elif not present(scorecard.get("selection_revision")):
        warnings.append("legacy scorecard has no selection_revision; regenerate before heartbeat batch refill")

    if not ideas:
        missing.append(pool_rel)

    stage = str(scorecard.get("stage") or "").strip()
    if stage != "post_idea_generation_pre_idea_gate":
        missing.append("stage=post_idea_generation_pre_idea_gate")

    if not present(scorecard.get("evidence_boundary")):
        missing.append("evidence_boundary")
    if not present(scorecard.get("scoring_rubric")):
        missing.append("scoring_rubric")
    if not present(scorecard.get("weights")):
        missing.append("weights")
    if not present(scorecard.get("top_recommendations")):
        missing.append("top_recommendations")
    if not present(scorecard.get("top_track_recommendations")):
        missing.append("top_track_recommendations")
    if not present(scorecard.get("pre_idea_evidence_gate_path")):
        missing.append("pre_idea_evidence_gate_path")
    caps = read_json(base / "capabilities.json") or {}
    operations = set(caps.get("agent_materials_operations") or [])
    proposal_graph_available = caps.get("proposal_graph_session_available") is True or "proposal_graph_session" in operations
    proposal_declared = present(scorecard.get("proposal_graph_session_path") or scorecard.get("proposal_graph_session_manifest_path"))
    slot_declared = present(scorecard.get("innovation_slot_map_path"))
    if not present(scorecard.get("source_evidence_roles")):
        warnings.append("source_evidence_roles recommended; scorecard should state target/near/far role coverage")

    gate_value = scorecard.get("pre_idea_evidence_gate_path") or "ideation/PRE_IDEA_EVIDENCE_GATE.json"
    gate_path = resolve(base, str(gate_value))
    gate = read_json(gate_path)
    pre_idea_degraded = False
    evidence_mode = source_mode(gate)
    alignment: dict[str, Any] | None = None
    if not isinstance(gate, dict):
        missing.append(f"pre_idea_evidence_gate_path target missing: {gate_value}")
    elif evidence_mode not in EVIDENCE_SOURCE_MODES:
        missing.append("pre_idea_evidence_gate_path evidence_source_mode must be papernexus or external_material")
    else:
        gate_status = str(gate.get("status") or "").strip().lower()
        if gate_status == "passed":
            pre_idea_degraded = False
        elif degraded_gate_approved(gate):
            pre_idea_degraded = True
            warnings.append("pre_idea_evidence_gate_path is approved degraded; scorecard claim limits must remain explicit")
        else:
            missing.append("pre_idea_evidence_gate_path status passed or approved degraded")
    if evidence_mode == "external_material":
        if pre_idea_degraded:
            missing.append("external_material evidence cannot use an approved degraded gate")
        for packet_key, gate_key in [
            ("external_campaign_ref", "campaign_ref"),
            ("external_campaign_sha256", "campaign_sha256"),
        ]:
            if not present(scorecard.get(packet_key)):
                missing.append(packet_key)
            elif isinstance(gate, dict) and str(scorecard.get(packet_key)) != str(gate.get(gate_key)):
                missing.append(f"{packet_key} must match PRE_IDEA_EVIDENCE_GATE.{gate_key}")
        expected_slot_map = str(gate.get("innovation_slot_map_path") or "").strip() if isinstance(gate, dict) else ""
        if not expected_slot_map or str(scorecard.get("innovation_slot_map_path") or "").strip() != expected_slot_map:
            missing.append("innovation_slot_map_path must match PRE_IDEA_EVIDENCE_GATE.innovation_slot_map_path")
        alignment = external_alignment(project, "ideation")
        if not alignment.get("complete"):
            items = alignment.get("missing") if isinstance(alignment.get("missing"), list) else []
            if items:
                missing.extend(f"external_alignment_lint: {item}" for item in items)
            else:
                missing.append("external_alignment_lint failed without structured missing output")
        items = alignment.get("warnings") if isinstance(alignment.get("warnings"), list) else []
        warnings.extend(f"external_alignment_lint: {item}" for item in items)

    slot_value = scorecard.get("innovation_slot_map_path") or "ideation/INNOVATION_SLOT_MAP.json"
    slot_path = resolve(base, str(slot_value))
    slot_map = read_json(slot_path)
    if not slot_declared and pre_idea_degraded:
        warnings.append("innovation_slot_map_path missing under approved degraded gate; experiment_plan must close selected evidence before launch")
    elif not slot_declared:
        missing.append("innovation_slot_map_path")
    if not isinstance(slot_map, dict) and pre_idea_degraded:
        warnings.append(f"innovation_slot_map_path target missing under approved degraded gate: {slot_value}")
    elif not isinstance(slot_map, dict):
        missing.append(f"innovation_slot_map_path target missing: {slot_value}")
    if pre_idea_degraded and not present(scorecard.get("claim_limits")):
        missing.append("claim_limits required for approved degraded pre-idea gate")
    if evidence_mode == "papernexus" and proposal_graph_available and not pre_idea_degraded and not proposal_declared:
        missing.append("proposal_graph_session_path or proposal_graph_session_manifest_path")

    idea_by_id = {str(row.get("id") or "").strip(): row for row in ideas if str(row.get("id") or "").strip()}
    idea_ids = set(idea_by_id)
    shortlist = recommendation_ids(scorecard.get("shortlisted_idea_ids"))
    if not shortlist:
        shortlist = recommendation_ids(scorecard.get("top_track_recommendations"))
    if not 3 <= len(shortlist) <= 5:
        missing.append(f"shortlist must contain 3-5 ideas, got {len(shortlist)}")
    unknown_shortlist = sorted(shortlist - idea_ids)
    if unknown_shortlist:
        missing.append("shortlist contains unknown idea ids: " + ", ".join(unknown_shortlist))
    selected_primary = str(scorecard.get("selected_primary_idea_id") or "").strip()
    if selected_primary and selected_primary not in idea_ids:
        missing.append(f"selected_primary_idea_id {selected_primary!r} is not in idea pool")
    if selected_primary and selected_primary not in shortlist:
        missing.append("selected_primary_idea_id must be in the 3-5 idea shortlist")
    row_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        idea_id = str(row.get("id") or row.get("idea_id") or "").strip()
        if idea_id:
            row_by_id[idea_id] = row

    missing_ids = sorted(idea_ids - set(row_by_id))
    extra_ids = sorted(set(row_by_id) - idea_ids)
    if missing_ids:
        missing.append("score rows missing idea ids: " + ", ".join(missing_ids))
    if extra_ids:
        warnings.append("score rows include ids not in idea pool: " + ", ".join(extra_ids))

    for idea_id in sorted(idea_ids & set(row_by_id)):
        row = row_by_id[idea_id]
        prefix = f"scorecard[{idea_id}]"
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else row
        if not positive_int(row.get("rank")):
            missing.append(f"{prefix}.rank positive integer")
        for dim in DIMENSIONS:
            if not score_ok(scores.get(dim)):
                missing.append(f"{prefix}.scores.{dim} 1-5")
        if not score_ok(row.get("weighted_total")):
            missing.append(f"{prefix}.weighted_total 1-5")
        comparison = row.get("paper_comparison") if isinstance(row.get("paper_comparison"), dict) else {}
        for key in PAPER_COMPARISON_KEYS:
            if not present(comparison.get(key)):
                missing.append(f"{prefix}.paper_comparison.{key}")
        signature = causal_signature(idea_by_id[idea_id])
        if not signature:
            missing.append(f"idea_pool[{idea_id}].causal_signature")
        if normalized_text(row.get("causal_signature")) != signature:
            missing.append(f"{prefix}.causal_signature must match the idea pool causal identity")
        pairwise = row.get("pairwise_comparison") if isinstance(row.get("pairwise_comparison"), dict) else {}
        for key in PAIRWISE_COMPARISON_KEYS:
            if not present(pairwise.get(key)):
                missing.append(f"{prefix}.pairwise_comparison.{key}")
        competing_id = str(pairwise.get("closest_competing_idea_id") or "").strip()
        if competing_id and (competing_id not in idea_ids or competing_id == idea_id):
            missing.append(f"{prefix}.pairwise_comparison.closest_competing_idea_id must name another pool idea")
        pairwise_verdict = normalized_role(pairwise.get("verdict"))
        if pairwise_verdict and pairwise_verdict not in PAIRWISE_VERDICTS:
            missing.append(f"{prefix}.pairwise_comparison.verdict must be one of {sorted(PAIRWISE_VERDICTS)}")
        for key in ["evidence_closure_level", "evidence_debt", "next_evidence_closure"]:
            if key not in row or (key != "evidence_debt" and not present(row.get(key))):
                missing.append(f"{prefix}.{key}")
        if str(row.get("evidence_closure_level") or "").strip().lower() not in EVIDENCE_CLOSURE_LEVELS:
            missing.append(f"{prefix}.evidence_closure_level must be one of {sorted(EVIDENCE_CLOSURE_LEVELS)}")
        if not positive_int(row.get("paper_potential_rank")):
            missing.append(f"{prefix}.paper_potential_rank positive integer")
        action = str(row.get("recommended_track_action") or "").strip().lower()
        if action not in RECOMMENDED_TRACK_ACTIONS:
            missing.append(f"{prefix}.recommended_track_action must be one of {sorted(RECOMMENDED_TRACK_ACTIONS)}")
        source_role = normalized_role(row.get("primary_method_source_role") or row.get("method_source_role"))
        if source_role in TARGET_DOMAIN_ONLY_ROLES:
            if not present(row.get("current_field_absence_evidence")):
                missing.append(f"{prefix}.current_field_absence_evidence required for target-domain-only main method")
        elif source_role and source_role not in VALID_METHOD_SOURCE_ROLES:
            missing.append(f"{prefix}.primary_method_source_role must be near/far-neighbor transfer, cross-lane recombination, proposal-graph transfer, external-domain transfer, or target_domain_absence_proven")
        slot_refs = row.get("innovation_slot_refs") or row.get("slot_refs") or row.get("supporting_slot_ids")
        if not present(slot_refs) and pre_idea_degraded:
            warnings.append(f"{prefix}.innovation_slot_refs missing under approved degraded gate")
        elif not present(slot_refs):
            missing.append(f"{prefix}.innovation_slot_refs")
        decision = str(row.get("promotion_recommendation") or "").strip().lower()
        if decision not in PROMOTION_DECISIONS:
            missing.append(f"{prefix}.promotion_recommendation advance/advance_with_constraints/park/kill")
        if pairwise_verdict == "redundant" and decision in {"advance", "advance_with_constraints"}:
            missing.append(f"{prefix} cannot advance while pairwise_comparison.verdict=redundant")
        if idea_id in shortlist:
            expected_tuple = deterministic_rank_tuple(row, idea_by_id[idea_id])
            deterministic_fields_missing: list[str] = []
            if not isinstance(row.get("changes_core_claim"), bool):
                deterministic_fields_missing.append("changes_core_claim boolean")
            if not string_list(row.get("unique_decision_targets") or row.get("decision_target_refs")):
                deterministic_fields_missing.append("unique_decision_targets")
            if positive_finite(
                row.get("estimated_falsifier_gpu_hours")
                or row.get("estimated_gpu_hours")
                or idea_by_id[idea_id].get("estimated_falsifier_gpu_hours")
                or idea_by_id[idea_id].get("estimated_gpu_hours")
            ) is None:
                deterministic_fields_missing.append("estimated_falsifier_gpu_hours positive finite")
            recorded_tuple = row.get("deterministic_ranking_tuple")
            if expected_tuple is None:
                deterministic_fields_missing.append("deterministic ranking inputs")
            elif not isinstance(recorded_tuple, list):
                deterministic_fields_missing.append("deterministic_ranking_tuple")
            elif recorded_tuple != expected_tuple:
                missing.append(f"{prefix}.deterministic_ranking_tuple must match the auditable lexicographic inputs")
            if deterministic_fields_missing:
                target = missing if deterministic_schema else warnings
                target.append(f"{prefix}: " + ", ".join(deterministic_fields_missing))
            validate_shortlist_idea(idea_by_id[idea_id], f"idea_pool[{idea_id}]", idea_id == selected_primary, missing)
            if program_contract and program_scope == "cross_dataset_method":
                idea = idea_by_id[idea_id]
                method_errors: list[str] = []
                claim_role = normalized_role(row.get("claim_role") or idea.get("claim_role"))
                if claim_role != "method_candidate":
                    method_errors.append("claim_role must be method_candidate")
                search_contract = (
                    idea.get("innovation_search_contract")
                    if isinstance(idea.get("innovation_search_contract"), dict)
                    else {}
                )
                mechanism_type = str(
                    row.get("mechanism_type")
                    or idea.get("mechanism_type")
                    or search_contract.get("mechanism_type")
                    or ""
                ).strip().upper()
                if mechanism_type not in {"ALGO", "CODE", "PARAM"}:
                    method_errors.append("mechanism_type must be ALGO, CODE, or PARAM")
                for field in [
                    "transfer_assumption",
                    "parameter_transfer_mode",
                    "paired_low_fidelity_falsifier",
                    "shared_method_formula",
                ]:
                    if not present(row.get(field) or idea.get(field)):
                        method_errors.append(f"{field} is required")
                predictions = row.get("cross_dataset_prediction") or idea.get("cross_dataset_prediction")
                prediction_datasets: set[str] = set()
                if isinstance(predictions, dict):
                    prediction_datasets = {str(key) for key in predictions}
                elif isinstance(predictions, list):
                    prediction_datasets = {
                        str(item.get("dataset_id"))
                        for item in predictions
                        if isinstance(item, dict) and present(item.get("dataset_id"))
                    }
                if set(required_program_datasets) - prediction_datasets:
                    method_errors.append("cross_dataset_prediction must cover every required dataset")
                target = missing if program_mode == "enforced" else warnings
                target.extend(f"{prefix}.cross_dataset_method: {item}" for item in method_errors)
            story_assessment = row.get("paper_story_assessment") if isinstance(row.get("paper_story_assessment"), dict) else {}
            for key in SHORTLIST_ASSESSMENT_KEYS:
                if not present(story_assessment.get(key)):
                    missing.append(f"{prefix}.paper_story_assessment.{key}")
            for key in [
                "closest_prior_pressure",
                "novelty_separation_needed",
                "graph_path_status",
                "near_neighbor_pressure",
                "far_neighbor_transfer_rationale",
                "primary_method_source_role",
                "target_domain_anchor",
                "neighbor_transfer_mechanism",
                "target_domain_method_overlap_risk",
                "top_tier_support_judgment",
                "venue_support_verdict",
            ]:
                if not present(row.get(key)):
                    missing.append(f"{prefix}.{key}")

    if isinstance(scorecard.get("top_track_recommendations"), list):
        top_track_ids = set()
        for item in scorecard["top_track_recommendations"]:
            if isinstance(item, dict):
                raw_id = item.get("idea_id") or item.get("id")
            else:
                raw_id = item
            if present(raw_id):
                top_track_ids.add(str(raw_id))
        unknown = sorted(top_track_ids - idea_ids)
        if unknown:
            missing.append("top_track_recommendations unknown idea ids: " + ", ".join(unknown))
        if not 3 <= len(top_track_ids) <= 5:
            missing.append("top_track_recommendations must include 3-5 shortlisted ideas")

    if evidence_mode == "papernexus" and proposal_graph_available and not any(present(row.get("proposal_graph_basis")) for row in rows):
        warnings.append("proposal_graph_session is available but no score rows include proposal_graph_basis")

    md_path = scorecard_path.with_suffix(".md")
    if not md_path.exists() or not md_path.read_text(encoding="utf-8", errors="ignore").strip():
        warnings.append(str(md_path.relative_to(base)) + " missing; recommended for human idea selection")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "idea_count": len(ideas),
        "score_row_count": len(row_by_id),
        "shortlist_count": len(shortlist),
        "evidence_source_mode": evidence_mode,
        "external_alignment_lint": alignment,
        "dimensions": DIMENSIONS,
        "path": str(scorecard_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--scorecard", default="ideation/IDEA_NOVELTY_VENUE_SCORECARD.json")
    parser.add_argument("--pool", default="ideation/EXPERIMENT_IDEA_POOL.json")
    args = parser.parse_args()
    out = lint(args.project, args.scorecard, args.pool)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
