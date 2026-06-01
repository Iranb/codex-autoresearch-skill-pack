#!/usr/bin/env python3
"""Lint post-idea novelty and venue-support scorecards."""

from __future__ import annotations

import argparse
import json
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
VALID_METHOD_SOURCE_ROLES = {
    "near_neighbor",
    "far_neighbor",
    "cross_lane_recombination",
    "proposal_graph_transfer",
    "external_domain_transfer",
    "target_domain_absence_proven",
}
TARGET_DOMAIN_ONLY_ROLES = {"target_domain", "current_field", "target_domain_only"}


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
    if not isinstance(gate, dict):
        missing.append(f"pre_idea_evidence_gate_path target missing: {gate_value}")
    else:
        gate_status = str(gate.get("status") or "").strip().lower()
        if gate_status == "passed":
            pre_idea_degraded = False
        elif degraded_gate_approved(gate):
            pre_idea_degraded = True
            warnings.append("pre_idea_evidence_gate_path is approved degraded; scorecard claim limits must remain explicit")
        else:
            missing.append("pre_idea_evidence_gate_path status passed or approved degraded")

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
    if proposal_graph_available and not pre_idea_degraded and not proposal_declared:
        missing.append("proposal_graph_session_path or proposal_graph_session_manifest_path")

    idea_ids = {str(row.get("id") or "").strip() for row in ideas if str(row.get("id") or "").strip()}
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
        for key in [
            "closest_prior_pressure",
            "novelty_separation_needed",
            "graph_path_status",
            "evidence_closure_level",
            "near_neighbor_pressure",
            "far_neighbor_transfer_rationale",
            "primary_method_source_role",
            "target_domain_anchor",
            "neighbor_transfer_mechanism",
            "target_domain_method_overlap_risk",
            "top_tier_support_judgment",
            "venue_support_verdict",
            "evidence_debt",
            "next_evidence_closure",
        ]:
            if not present(row.get(key)):
                missing.append(f"{prefix}.{key}")
        if str(row.get("evidence_closure_level") or "").strip().lower() not in EVIDENCE_CLOSURE_LEVELS:
            missing.append(f"{prefix}.evidence_closure_level must be one of {sorted(EVIDENCE_CLOSURE_LEVELS)}")
        if not positive_int(row.get("scientistone_fast_rank")):
            missing.append(f"{prefix}.scientistone_fast_rank positive integer")
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
        if len(top_track_ids) < 3:
            warnings.append("top_track_recommendations should usually include 3-4 candidate tracks")
    selected_primary = scorecard.get("selected_primary_idea_id")
    if present(selected_primary) and str(selected_primary) not in idea_ids:
        missing.append(f"selected_primary_idea_id {selected_primary!r} is not in idea pool")

    if proposal_graph_available and not any(present(row.get("proposal_graph_basis")) for row in rows):
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
