#!/usr/bin/env python3
"""Lint .autoreskill stage contracts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


READY = {"ready", "complete", "completed", "pass", "passed", "verified"}
IDEA_LIFECYCLE_STATUSES = {
    "selected_primary",
    "alternate_track",
    "risk_repair_track",
    "advance_with_constraints",
    "repair_needed",
    "parked",
    "killed",
    "degraded_speculative",
}
IDEA_FAILURE_CLASSES = {
    "none",
    "novelty_collision",
    "closest_prior_overlap",
    "story_collapse",
    "three_innovation_bundle_incomplete",
    "evidence_gap",
    "proposal_graph_uncommitted",
    "target_domain_only_method",
    "baseline_unavailable",
    "protocol_unsafe",
    "metric_or_dataset_drift_risk",
    "feasibility_fail",
    "risk_uncontrolled",
    "low_expected_value",
}
BIE_REQUIRED_FIELDS = [
    "branch_budget_B",
    "search_iterations_I",
    "versions_per_branch_E",
    "retain_top_K",
    "stop_on_spec_violation",
    "promotion_required",
]
GOAL_TYPES = {
    "paper_producing_top_tier",
    "paper_producing_light",
    "standalone_survey",
    "writing_style_corpus",
    "diagnostic_or_resource",
}
CLAIM_MODES = {
    "strong_paper_claims",
    "pilot_evidence",
    "survey_only",
    "writing_guidance_only",
    "diagnostic_only",
}
MINIMAL_TRACK_PLAN_FIELDS = [
    "certification_policy",
    "intervention_axis",
    "critical_evidence_requirements",
    "negative_knowledge_consultation",
]
SCORE_VERIFICATION_FIELDS = [
    "disaggregated_effects",
    "mechanism_support",
    "validation_to_test_transfer",
    "numeric_measurement_registry",
]
PAPER_CLAIM_VERIFICATION_FIELDS = [
    "claim_drift_status",
    "scientific_alignment_status",
    "numeric_grounding_status",
    "non_defensive_writing_status",
]
SCOPE_CLAIM_LIMIT_FIELDS = [
    "claim_limits",
    "out_of_scope_claim_limits",
    "evidence_boundaries",
    "scope_boundaries",
    "reduced_evidence_target",
]
SELECTION_REF_FIELDS = ["selection_fingerprint", "selected_primary_ref"]


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def has_any(base: Path, rels: list[str]) -> bool:
    return any(nonempty(base / rel) or (base / rel).exists() for rel in rels)


def has_glob(base: Path, pattern: str) -> bool:
    return any(path.is_file() and nonempty(path) for path in base.glob(pattern))


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def workflow_scope(base: Path) -> dict[str, str]:
    state = read_json(base / "goal_state.json") or {}
    policy = read_json(base / "autopilot_policy.json") or {}
    goal_type = str(state.get("goal_type") or policy.get("goal_type") or "paper_producing_top_tier").strip()
    claim_mode = str(state.get("claim_mode") or policy.get("claim_mode") or "strong_paper_claims").strip()
    if goal_type not in GOAL_TYPES:
        goal_type = "paper_producing_top_tier"
    if claim_mode not in CLAIM_MODES:
        claim_mode = "strong_paper_claims"
    return {"goal_type": goal_type, "claim_mode": claim_mode}


def requires_strong_paper_contract(base: Path) -> bool:
    scope = workflow_scope(base)
    return scope["goal_type"] == "paper_producing_top_tier" and scope["claim_mode"] == "strong_paper_claims"


def add_scope_warnings(base: Path, warnings: list[str]) -> None:
    state = read_json(base / "goal_state.json") or {}
    policy = read_json(base / "autopilot_policy.json") or {}
    if "goal_type" not in state and "goal_type" not in policy:
        warnings.append("goal_type missing; defaulting to paper_producing_top_tier")
    if "claim_mode" not in state and "claim_mode" not in policy:
        warnings.append("claim_mode missing; defaulting to strong_paper_claims")


def field_present_any(payload: dict[str, Any], names: list[str]) -> bool:
    return any(present(payload.get(name)) for name in names)


def first_present(payload: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        value = payload.get(name)
        if present(value):
            return value
    return None


def scope_claim_limit_ref(base: Path) -> tuple[bool, str]:
    for rel in ["goal_state.json", "autopilot_policy.json"]:
        payload = read_json(base / rel) or {}
        for field in SCOPE_CLAIM_LIMIT_FIELDS:
            if present(payload.get(field)):
                return True, f"{rel}.{field}"
    return False, ""


def out_of_scope_gate(base: Path, gate: str, skipped_items: list[str]) -> dict[str, Any]:
    has_limits, limit_ref = scope_claim_limit_ref(base)
    return {
        "gate": gate,
        "scope": workflow_scope(base),
        "claim_limits_present": has_limits,
        "claim_limits_ref": limit_ref,
        "skipped_items": skipped_items,
    }


def record_scoped_hardening(
    base: Path,
    gate: str,
    missing_items: list[str],
    warnings: list[str],
    details: dict[str, Any],
) -> None:
    if not missing_items:
        return
    entry = out_of_scope_gate(base, gate, missing_items)
    details.setdefault("out_of_scope_with_claim_limits", []).append(entry)
    if not entry["claim_limits_present"]:
        warnings.append(f"{gate}: out of strong-paper scope but no claim_limits/scope_boundaries recorded")


def record_scoped_gate(
    base: Path,
    gate: str,
    skipped_items: list[str],
    warnings: list[str],
    details: dict[str, Any],
) -> None:
    items = [str(item) for item in skipped_items if str(item).strip()]
    if not items:
        items = [f"{gate}: strong-paper blocking gate skipped by project scope"]
    entry = out_of_scope_gate(base, gate, items)
    details.setdefault("out_of_scope_with_claim_limits", []).append(entry)
    if not entry["claim_limits_present"]:
        warnings.append(f"{gate}: out of strong-paper scope but no claim_limits/scope_boundaries recorded")


def selection_ref(payload: dict[str, Any]) -> str:
    value = first_present(payload, SELECTION_REF_FIELDS)
    return str(value).strip() if present(value) else ""


def derived_selection_ref(idea_id: str, track_id: str) -> str:
    return f"idea:{idea_id}|track:{track_id or 'none'}"


def status_passed(value: Any) -> bool:
    if isinstance(value, dict):
        status = normalized(value.get("status") or value.get("state") or value.get("verdict"))
        return status in READY
    return normalized(value) in READY


def degraded_gate_approved(gate: Any) -> bool:
    if not isinstance(gate, dict):
        return False
    if str(gate.get("status") or "").strip().lower() != "degraded_requires_user_approval":
        return False
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return False
    if not present(approval.get("approved_by")) or not present(approval.get("approved_at")) or not present(approval.get("reason")):
        return False
    return present(gate.get("claim_limits") or approval.get("claim_limits"))


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["tracks", "rows", "track_plans", "ideas", "decisions", "outcomes", "idea_outcomes"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def idea_ids_from_pool(pool: Any) -> set[str]:
    ids: set[str] = set()
    if not isinstance(pool, dict):
        return ids
    for key in ["ideas", "candidates"]:
        rows = pool.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    idea_id = row.get("id") or row.get("idea_id")
                    if present(idea_id):
                        ids.add(str(idea_id))
    return ids


def track_seed_idea_ids(seeds: Any) -> set[str]:
    ids: set[str] = set()
    for row in rows_from_payload(seeds):
        idea_id = row.get("idea_id")
        if present(idea_id):
            ids.add(str(idea_id))
    return ids


def selected_idea_gate_authority(base: Path) -> dict[str, Any]:
    """Return the current selected idea/track from idea-gate authorities."""

    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json") or {}
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json") or {}
    seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json") or {}
    selected_idea = (
        ledger.get("selected_primary_idea_id")
        or ledger.get("selected_idea_id")
        or pool.get("selected_idea_id")
        or pool.get("selected_primary_idea_id")
    )
    selected_track = pool.get("selected_track_id") or ledger.get("selected_track_id")
    primary_seed_tracks: set[str] = set()
    seed_idea_ids: set[str] = set()
    seed_selection_ref = ""
    for row in rows_from_payload(seeds):
        if not isinstance(row, dict):
            continue
        if present(row.get("idea_id")):
            seed_idea_ids.add(str(row["idea_id"]))
        is_primary = normalized(row.get("track_role")) == "primary"
        if selected_idea and row.get("idea_id") and str(row.get("idea_id")) != str(selected_idea):
            is_primary = False
        if is_primary:
            if present(row.get("track_id")):
                primary_seed_tracks.add(str(row["track_id"]))
            if not selected_track and present(row.get("track_id")):
                selected_track = row.get("track_id")
            if not seed_selection_ref:
                seed_selection_ref = selection_ref(row)
    lifecycle_by_id: dict[str, str] = {}
    selected_decision_ref = ""
    for row in rows_from_payload(ledger):
        idea_id = row.get("idea_id")
        if present(idea_id):
            lifecycle_by_id[str(idea_id)] = normalized(row.get("lifecycle_status"))
        if normalized(row.get("lifecycle_status")) == "selected_primary" or (
            selected_idea and present(idea_id) and str(idea_id) == str(selected_idea)
        ):
            if not selected_decision_ref:
                selected_decision_ref = selection_ref(row)
    explicit_ref = selection_ref(ledger) or selected_decision_ref or seed_selection_ref
    selected_idea_str = str(selected_idea) if present(selected_idea) else ""
    selected_track_str = str(selected_track) if present(selected_track) else ""
    fingerprint = explicit_ref or (derived_selection_ref(selected_idea_str, selected_track_str) if selected_idea_str else "")
    return {
        "selected_idea_id": selected_idea_str,
        "selected_track_id": selected_track_str,
        "selection_fingerprint": fingerprint,
        "selection_fingerprint_explicit": bool(explicit_ref),
        "primary_seed_track_ids": sorted(primary_seed_tracks),
        "seed_idea_ids": sorted(seed_idea_ids),
        "lifecycle_by_id": lifecycle_by_id,
    }


def plan_selected_rows(matrix: Any) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows_from_payload(matrix):
        if not isinstance(row, dict):
            continue
        launch_status = normalized(row.get("launch_status"))
        if (
            row.get("selected_for_review") is True
            or launch_status == "ready"
            or normalized(row.get("track_role")) == "primary"
        ):
            selected.append(row)
    return selected


def selected_decision_row(base: Path, selected_idea: str) -> dict[str, Any]:
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json") or {}
    for row in rows_from_payload(ledger):
        if isinstance(row, dict) and str(row.get("idea_id") or "") == selected_idea:
            return row
    return {}


def selected_reentry_mentions_negative(decision: dict[str, Any], selected_idea: str, selected_track: str, evidence: dict[str, Any]) -> bool:
    """Return whether the selected idea explicitly re-enters after its own negative run."""

    run_id = str(evidence.get("run_id") or "").strip().lower()
    source = str(evidence.get("source") or "").strip().lower()
    text = json.dumps(decision, ensure_ascii=False).lower()
    if not text:
        return False
    own_negative = (
        selected_idea.lower() in text
        or (selected_track and selected_track.lower() in text)
        or (run_id and run_id in text)
        or (source and source in text)
    )
    reentry_marker = any(
        marker in text
        for marker in [
            "non-equivalent",
            "non_equivalent",
            "structural",
            "materially different",
            "new mechanism",
            "new route",
            "positive-only reentry",
            "positive_only_reentry",
        ]
    )
    return own_negative and reentry_marker and decision.get("launch_approval") is False


def negative_experiment_artifacts_for_selection(base: Path, selected_idea: str, selected_track: str) -> list[dict[str, Any]]:
    """Find terminal not-promoted evidence for the selected idea/track.

    Experiment ledgers can lag behind per-track REMOTE_RUN/CANDIDATE_VERDICT files.
    This scan intentionally checks both lightweight run artifacts and the aggregate
    ledger so stale selected plans cannot re-launch a track already proven negative.
    """

    negatives: list[dict[str, Any]] = []
    candidate_paths = list(base.glob("coder/experiments/**/CANDIDATE_VERDICT.json"))
    candidate_paths += list(base.glob("coder/experiments/**/REMOTE_RUN.json"))
    candidate_paths += list(base.glob("coder/experiments/**/*VERDICT*.json"))
    candidate_paths += list(base.glob("coder/experiments/**/*NEGATIVE_BLOCKER*.json"))
    for path in candidate_paths:
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        rel = str(path.relative_to(base))
        idea_id = str(payload.get("selected_idea_id") or payload.get("idea_id") or "").strip()
        track_id = str(payload.get("track_id") or payload.get("track") or "").strip()
        path_matches_idea = f"experiments/{selected_idea}/" in rel
        if selected_idea and idea_id and idea_id != selected_idea:
            continue
        if selected_track and track_id and track_id != selected_track:
            continue
        if not (path_matches_idea or idea_id == selected_idea or (selected_track and track_id == selected_track)):
            continue
        status = normalized(payload.get("status") or payload.get("run_status"))
        decision = normalized(payload.get("promotion_decision") or payload.get("promotion_status") or payload.get("verdict"))
        negative = (
            status in {"terminal_not_promoted", "not_promoted", "failed", "regressed", "completed_terminal_not_promoted"}
            or status.startswith("terminal_not_promoted")
            or status.startswith("not_promoted")
            or decision.startswith("not_promoted")
            or decision in {"terminal_not_promoted", "failed", "regressed"}
            or payload.get("candidate_supported") is False and bool(decision)
        )
        if not negative:
            continue
        negatives.append(
            {
                "source": rel,
                "run_id": payload.get("run_id"),
                "idea_id": idea_id or selected_idea if path_matches_idea else idea_id,
                "track_id": track_id,
                "status": payload.get("status") or payload.get("run_status"),
                "promotion_decision": payload.get("promotion_decision") or payload.get("promotion_status") or payload.get("verdict"),
                "candidate_supported": payload.get("candidate_supported"),
                "negative_result_manuscript_allowed": payload.get("negative_result_manuscript_allowed"),
                "mtime": path.stat().st_mtime,
            }
        )

    ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json") or {}
    for index, row in enumerate(rows_from_payload(ledger)):
        if not isinstance(row, dict):
            continue
        idea_id = str(row.get("selected_idea_id") or row.get("idea_id") or "").strip()
        track_id = str(row.get("track_id") or row.get("track") or "").strip()
        if selected_idea and idea_id and idea_id != selected_idea:
            continue
        if selected_track and track_id and track_id != selected_track:
            continue
        if not (idea_id == selected_idea or (selected_track and track_id == selected_track)):
            continue
        status = normalized(row.get("status") or row.get("run_status"))
        decision = normalized(row.get("promotion_decision") or row.get("promotion_status") or row.get("verdict"))
        negative = (
            status.startswith("terminal_not_promoted")
            or status.startswith("not_promoted")
            or decision.startswith("not_promoted")
            or row.get("candidate_supported") is False and bool(decision)
        )
        if negative:
            negatives.append(
                {
                    "source": f"coder/EXPERIMENT_LEDGER.json entries[{index}]",
                    "run_id": row.get("run_id"),
                    "idea_id": idea_id,
                    "track_id": track_id,
                    "status": row.get("status") or row.get("run_status"),
                    "promotion_decision": row.get("promotion_decision") or row.get("promotion_status") or row.get("verdict"),
                    "candidate_supported": row.get("candidate_supported"),
                    "negative_result_manuscript_allowed": row.get("negative_result_manuscript_allowed"),
                    "mtime": 0,
                }
            )
    return sorted(negatives, key=lambda item: float(item.get("mtime") or 0), reverse=True)


def validate_selected_negative_evidence_alignment(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    """Block stale current selections whose own latest experiment evidence is terminal negative."""

    missing: list[str] = []
    warnings: list[str] = []
    gate = selected_idea_gate_authority(base)
    selected_idea = gate.get("selected_idea_id") or ""
    selected_track = gate.get("selected_track_id") or ""
    if not selected_idea:
        return missing, warnings, {"status": "skipped_no_idea_gate_selection", "idea_gate": gate}
    negatives = negative_experiment_artifacts_for_selection(base, selected_idea, selected_track)
    if not negatives:
        return missing, warnings, {"status": "no_selected_negative_evidence", "idea_gate": gate}
    latest = negatives[0]
    decision = selected_decision_row(base, selected_idea)
    if selected_reentry_mentions_negative(decision, selected_idea, selected_track, latest):
        warnings.append(
            f"{selected_idea}/{selected_track or '<no-track>'} has terminal negative evidence but explicit launch-blocked non-equivalent reentry is recorded"
        )
    else:
        missing.append(
            f"idea_gate selected {selected_idea}/{selected_track or '<no-track>'} has terminal not-promoted evidence "
            f"at {latest.get('source')} ({latest.get('promotion_decision') or latest.get('status')}); "
            "select a non-equivalent idea/track or record explicit launch-blocked reentry before experiment_plan/code can advance"
        )
    return missing, warnings, {
        "idea_gate": gate,
        "latest_negative_evidence": latest,
        "negative_evidence_count": len(negatives),
        "selected_decision_lifecycle": decision.get("lifecycle_status"),
        "selected_decision_next_action": decision.get("next_action"),
        "explicit_reentry_after_negative": selected_reentry_mentions_negative(decision, selected_idea, selected_track, latest),
    }


def validate_selected_projection_alignment(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    """Ensure downstream plan/code authorities project the current idea-gate selection.

    This catches stale projection drift after a failed track is parked and a new idea is selected:
    INNOVATION_PACKET, EXPERIMENT_REVIEW_PACKET, TRACK_PLAN_MATRIX active rows, and code-stage
    readiness must not keep pointing at the old failed idea/track.
    """

    missing: list[str] = []
    warnings: list[str] = []
    gate = selected_idea_gate_authority(base)
    selected_idea = gate.get("selected_idea_id") or ""
    selected_track = gate.get("selected_track_id") or ""
    expected_selection_ref = str(gate.get("selection_fingerprint") or "").strip()
    strong_contract = requires_strong_paper_contract(base)
    if not selected_idea:
        return missing, warnings, {"status": "skipped_no_idea_gate_selection", "idea_gate": gate}
    if strong_contract and not gate.get("selection_fingerprint_explicit"):
        missing.append("ideation/IDEA_DECISION_LEDGER.json selection_fingerprint or selected_primary_ref")

    packets: dict[str, dict[str, Any]] = {}
    for rel in ["orchestrator/INNOVATION_PACKET.json", "planner/EXPERIMENT_REVIEW_PACKET.json"]:
        payload = read_json(base / rel) or {}
        packets[rel] = payload
        if not payload:
            missing.append(rel)
            continue
        for key in ["selected_idea_id", "selected_idea_fragment_id"]:
            value = payload.get(key)
            if present(value) and str(value) != selected_idea:
                missing.append(f"{rel} {key}={value} does not match idea_gate selected_primary_idea_id={selected_idea}")
        if present(payload.get("track_id")) and selected_track and str(payload.get("track_id")) != selected_track:
            missing.append(f"{rel} track_id={payload.get('track_id')} does not match idea_gate selected_track_id={selected_track}")
        payload_ref = selection_ref(payload)
        if strong_contract and not payload_ref:
            missing.append(f"{rel} selection_fingerprint or selected_primary_ref")
        elif payload_ref and expected_selection_ref and payload_ref != expected_selection_ref:
            missing.append(f"{rel} selection_fingerprint={payload_ref} does not match idea_gate selection_fingerprint={expected_selection_ref}")

    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json") or {}
    matrix_rows = rows_from_payload(matrix)
    if not matrix:
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json")
    else:
        top_selected = matrix.get("selected_idea_id")
        if present(top_selected) and str(top_selected) != selected_idea:
            missing.append(
                f"orchestrator/TRACK_PLAN_MATRIX.json selected_idea_id={top_selected} "
                f"does not match idea_gate selected_primary_idea_id={selected_idea}"
            )
        matrix_ref = selection_ref(matrix)
        if strong_contract and not matrix_ref:
            missing.append("orchestrator/TRACK_PLAN_MATRIX.json selection_fingerprint or selected_primary_ref")
        elif matrix_ref and expected_selection_ref and matrix_ref != expected_selection_ref:
            missing.append(
                f"orchestrator/TRACK_PLAN_MATRIX.json selection_fingerprint={matrix_ref} "
                f"does not match idea_gate selection_fingerprint={expected_selection_ref}"
            )
        active_rows = plan_selected_rows(matrix)
        selected_active_rows = [
            row
            for row in active_rows
            if str(row.get("idea_id") or "") == selected_idea
            and (not selected_track or str(row.get("track_id") or "") == selected_track)
        ]
        if not selected_active_rows:
            missing.append(
                "orchestrator/TRACK_PLAN_MATRIX.json has no active row for "
                f"idea_gate selection {selected_idea}/{selected_track or '<no-track>'}"
            )
        lifecycle_by_id = gate.get("lifecycle_by_id") if isinstance(gate.get("lifecycle_by_id"), dict) else {}
        for index, row in enumerate(active_rows):
            idea_id = str(row.get("idea_id") or "")
            track_id = str(row.get("track_id") or "")
            lifecycle = normalized(lifecycle_by_id.get(idea_id))
            row_ref = selection_ref(row)
            if strong_contract and not row_ref:
                missing.append(f"orchestrator/TRACK_PLAN_MATRIX.json active tracks[{index}].selection_fingerprint or selected_primary_ref")
            elif row_ref and expected_selection_ref and row_ref != expected_selection_ref:
                missing.append(
                    f"orchestrator/TRACK_PLAN_MATRIX.json active tracks[{index}] "
                    f"selection_fingerprint={row_ref} does not match idea_gate selection_fingerprint={expected_selection_ref}"
                )
            if idea_id and idea_id != selected_idea:
                missing.append(
                    f"orchestrator/TRACK_PLAN_MATRIX.json active tracks[{index}] "
                    f"{idea_id}/{track_id} is stale; expected {selected_idea}/{selected_track or '<no-track>'}"
                )
            if lifecycle in {"parked", "killed"}:
                missing.append(
                    f"orchestrator/TRACK_PLAN_MATRIX.json active tracks[{index}] "
                    f"{idea_id}/{track_id} has lifecycle_status={lifecycle}"
                )
    details = {
        "idea_gate": gate,
        "innovation_packet_selection": {
            "selected_idea_id": packets.get("orchestrator/INNOVATION_PACKET.json", {}).get("selected_idea_id"),
            "selected_idea_fragment_id": packets.get("orchestrator/INNOVATION_PACKET.json", {}).get("selected_idea_fragment_id"),
            "track_id": packets.get("orchestrator/INNOVATION_PACKET.json", {}).get("track_id"),
            "selection_fingerprint": selection_ref(packets.get("orchestrator/INNOVATION_PACKET.json", {})),
        },
        "review_packet_selection": {
            "selected_idea_id": packets.get("planner/EXPERIMENT_REVIEW_PACKET.json", {}).get("selected_idea_id"),
            "selected_idea_fragment_id": packets.get("planner/EXPERIMENT_REVIEW_PACKET.json", {}).get("selected_idea_fragment_id"),
            "track_id": packets.get("planner/EXPERIMENT_REVIEW_PACKET.json", {}).get("track_id"),
            "selection_fingerprint": selection_ref(packets.get("planner/EXPERIMENT_REVIEW_PACKET.json", {})),
        },
        "track_plan_active_rows": [
            {
                "idea_id": row.get("idea_id"),
                "track_id": row.get("track_id"),
                "track_role": row.get("track_role"),
                "launch_status": row.get("launch_status"),
                "selected_for_review": row.get("selected_for_review"),
                "selection_fingerprint": selection_ref(row),
            }
            for row in plan_selected_rows(matrix)
        ],
        "track_plan_row_count": len(matrix_rows),
    }
    return missing, warnings, details


def graph_plan_action_counts(graph_plan: Any) -> dict[str, int]:
    counts = {"import_required": 0, "material_required": 0, "selected": 0}
    if not isinstance(graph_plan, dict):
        return counts
    for row in graph_plan.get("selected_papers") or []:
        if not isinstance(row, dict):
            continue
        counts["selected"] += 1
        action = str(row.get("import_action") or "").strip()
        if action in {"import", "supplement"}:
            counts["import_required"] += 1
        elif action == "material_view":
            counts["material_required"] += 1
    return counts


def source_limited_import_lint(import_workflow_lint: Any) -> bool:
    if not isinstance(import_workflow_lint, dict):
        return False
    details = import_workflow_lint.get("details")
    if not isinstance(details, dict):
        return False
    count = details.get("source_limited_exception_count")
    return isinstance(count, int) and count > 0 and import_workflow_lint.get("complete") is True


def source_limited_graph_decision_allows_advance(decision: Any) -> bool:
    if not isinstance(decision, dict):
        return False
    decision_value = str(decision.get("decision") or "").strip().lower()
    if decision_value not in {"complete", "advance_with_source_limited_exceptions", "complete_with_source_limited_exceptions"}:
        return False
    scope = str(
        decision.get("source_backed_graph_claim_scope")
        or decision.get("graph_claim_scope")
        or decision.get("claim_scope")
        or ""
    ).strip().lower()
    has_scope = scope in {
        "imported_only",
        "graph_visible_imported_only",
        "source_limited_imported_only",
        "claim_limited",
        "metadata_screened_only_for_exceptions",
    }
    return has_scope and present(decision.get("claim_limits") or decision.get("source_limited_exceptions"))


def validate_idea_decision_ledger(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    ledger_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    ledger = read_json(ledger_path)
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json")
    seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json")
    if not ledger:
        return ["ideation/IDEA_DECISION_LEDGER.json"], warnings, {}
    top_selection_ref = selection_ref(ledger)
    decisions = ledger.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        missing.append("ideation/IDEA_DECISION_LEDGER.json decisions[]")
        decisions = []
    decision_ids: set[str] = set()
    lifecycle_by_id: dict[str, str] = {}
    selected_refs: list[str] = []
    for index, decision in enumerate(row for row in decisions if isinstance(row, dict)):
        prefix = f"ideation/IDEA_DECISION_LEDGER.json decisions[{index}]"
        for field in ["idea_id", "scorecard_rank", "lifecycle_status", "decision_reason", "failure_class", "evidence_refs", "claim_scope", "next_action"]:
            if not present(decision.get(field)):
                missing.append(f"{prefix}.{field}")
        idea_id = decision.get("idea_id")
        if present(idea_id):
            decision_ids.add(str(idea_id))
        status = str(decision.get("lifecycle_status") or "").strip()
        failure_class = str(decision.get("failure_class") or "").strip()
        if status and status not in IDEA_LIFECYCLE_STATUSES:
            missing.append(f"{prefix}.lifecycle_status must be one of {sorted(IDEA_LIFECYCLE_STATUSES)}")
        if failure_class and failure_class not in IDEA_FAILURE_CLASSES:
            missing.append(f"{prefix}.failure_class must be one of {sorted(IDEA_FAILURE_CLASSES)}")
        if status in {"parked", "killed", "repair_needed", "advance_with_constraints", "degraded_speculative"}:
            if "can_reenter" not in decision:
                missing.append(f"{prefix}.can_reenter")
            if not present(decision.get("reentry_conditions")) and decision.get("can_reenter") is True:
                missing.append(f"{prefix}.reentry_conditions")
        if status == "selected_primary":
            row_ref = selection_ref(decision)
            if row_ref:
                selected_refs.append(row_ref)
            elif not top_selection_ref:
                missing.append(f"{prefix}.selection_fingerprint or selected_primary_ref")
        if present(idea_id):
            lifecycle_by_id[str(idea_id)] = status
    if not selected_refs and not top_selection_ref:
        missing.append("ideation/IDEA_DECISION_LEDGER.json selection_fingerprint or selected_primary_ref for selected primary")
    pool_ids = idea_ids_from_pool(pool)
    if pool_ids:
        missing_ids = sorted(pool_ids - decision_ids)
        if missing_ids:
            missing.append("IDEA_DECISION_LEDGER missing pool ideas: " + ", ".join(missing_ids))
        extra_ids = sorted(decision_ids - pool_ids)
        if extra_ids:
            warnings.append("IDEA_DECISION_LEDGER has decisions for ids not found in pool: " + ", ".join(extra_ids))
    seed_ids = track_seed_idea_ids(seeds)
    for seed_id in sorted(seed_ids):
        status = lifecycle_by_id.get(seed_id)
        if not status:
            missing.append(f"IDEA_TRACK_SEEDS idea {seed_id} lacks IDEA_DECISION_LEDGER row")
        elif status == "killed":
            missing.append(f"IDEA_TRACK_SEEDS idea {seed_id} is killed in IDEA_DECISION_LEDGER")
        elif status == "parked":
            missing.append(f"IDEA_TRACK_SEEDS idea {seed_id} is parked in IDEA_DECISION_LEDGER")
        elif status not in {"selected_primary", "alternate_track", "risk_repair_track", "advance_with_constraints"}:
            warnings.append(f"IDEA_TRACK_SEEDS idea {seed_id} has lifecycle_status={status}; verify this is intentional")
    return missing, warnings, {
        "decision_count": len(decisions),
        "pool_idea_count": len(pool_ids),
        "track_seed_count": len(seed_ids),
        "selection_fingerprint": top_selection_ref or (selected_refs[0] if selected_refs else ""),
    }


def validate_track_plan_lifecycle(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json")
    if not matrix:
        return ["orchestrator/TRACK_PLAN_MATRIX.json"], warnings, {}
    bie_config = matrix.get("bie_config") if isinstance(matrix.get("bie_config"), dict) else {}
    if not bie_config:
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json bie_config")
    else:
        for field in BIE_REQUIRED_FIELDS:
            if not present(bie_config.get(field)):
                missing.append(f"orchestrator/TRACK_PLAN_MATRIX.json bie_config.{field}")
    if not present(matrix.get("source_idea_decision_ledger_path")) and not present(matrix.get("idea_decision_ledger_path")):
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json source_idea_decision_ledger_path")
    rows = rows_from_payload(matrix)
    for index, row in enumerate(rows):
        prefix = f"orchestrator/TRACK_PLAN_MATRIX.json tracks[{index}]"
        if not present(row.get("idea_decision_ref")):
            missing.append(f"{prefix}.idea_decision_ref")
        if not present(row.get("branch_id")):
            warnings.append(f"{prefix}.branch_id recommended for B/I/E search tracing")
    return missing, warnings, {"bie_config_present": bool(bie_config), "track_count": len(rows)}


def track_plan_row_supports_claim(row: dict[str, Any]) -> bool:
    status = normalized(row.get("status") or row.get("state") or row.get("decision") or row.get("promotion_decision"))
    objective = normalized(row.get("objective_class"))
    if row.get("paper_claim_allowed") is False or row.get("claim_support_allowed") is False:
        return False
    if objective in {"diagnostic", "resource_fill"}:
        return False
    if status in {"parked", "blocked", "diagnostic", "resource_fill", "killed", "failed"}:
        return False
    return status in {
        "ready",
        "launch_ready",
        "queued",
        "active",
        "selected_for_review",
        "primary",
        "promoted",
        "candidate",
        "complete",
        "completed",
    } or bool(row.get("launch_ready") or row.get("selected_for_review") or row.get("primary"))


def validate_minimal_track_plan_fields(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json")
    if not isinstance(matrix, dict):
        return ["orchestrator/TRACK_PLAN_MATRIX.json"], warnings, {}
    rows = rows_from_payload(matrix)
    checked = 0
    for index, row in enumerate(rows):
        if not track_plan_row_supports_claim(row):
            continue
        checked += 1
        prefix = f"orchestrator/TRACK_PLAN_MATRIX.json tracks[{index}]"
        for field in MINIMAL_TRACK_PLAN_FIELDS:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
    return missing, warnings, {"checked_claim_supporting_rows": checked}


def validate_backend_remap_closure(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    """Ensure an open code-stage backend remap request is reflected in plan authority."""

    missing: list[str] = []
    warnings: list[str] = []
    requests = sorted((base / "coder").glob("BACKEND_REMAP_REQUEST_*.json"))
    active_request: dict[str, Any] | None = None
    active_path = ""
    for path in reversed(requests):
        request = read_json(path)
        if not isinstance(request, dict):
            continue
        status = str(request.get("status") or "").strip().lower()
        request_type = str(request.get("request_type") or "").strip().lower()
        if request_type == "experiment_plan_backend_remap" and status in {
            "requires_experiment_plan_authority",
            "pending",
            "open",
        }:
            active_request = request
            active_path = str(path.relative_to(base))
            break
    if not active_request:
        return missing, warnings, {"active_request": None}

    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json") or {}
    innovation = read_json(base / "orchestrator/INNOVATION_PACKET.json") or {}
    candidate = active_request.get("candidate_backend") if isinstance(active_request.get("candidate_backend"), dict) else {}
    host = str(candidate.get("host_alias") or candidate.get("host") or "").strip()
    data_root = str(candidate.get("dataset_root") or "").strip()
    project_root = str(candidate.get("project_root") or "").strip()
    expected_backend = "3090-trainble" if host == "3090-trainble" else host

    for name, packet in [("planner/EXPERIMENT_REVIEW_PACKET.json", review), ("orchestrator/INNOVATION_PACKET.json", innovation)]:
        compute = packet.get("compute_backend") if isinstance(packet.get("compute_backend"), dict) else {}
        gpu = compute.get("gpu_evidence") if isinstance(compute.get("gpu_evidence"), dict) else {}
        mapping = packet.get("path_mapping") if isinstance(packet.get("path_mapping"), dict) else {}
        env = mapping.get("env") if isinstance(mapping.get("env"), dict) else {}
        observed_host = str(gpu.get("ssh_host") or gpu.get("host_alias") or compute.get("host_alias") or "").strip()
        if expected_backend and observed_host != expected_backend:
            missing.append(f"{name} compute_backend.gpu_evidence.ssh_host must be {expected_backend} for {active_path}")
        if project_root and str(mapping.get("project_root") or "") != project_root:
            missing.append(f"{name} path_mapping.project_root must be {project_root} for {active_path}")
        if data_root and str(mapping.get("data_root") or "") != data_root:
            missing.append(f"{name} path_mapping.data_root must be {data_root} for {active_path}")
        if data_root and str(env.get("DATA_ROOT") or "") != data_root:
            missing.append(f"{name} path_mapping.env.DATA_ROOT must be {data_root} for {active_path}")
        if str(compute.get("backend") or "") != "local_gpu":
            warnings.append(f"{name} compute_backend.backend is not local_gpu while remapping to SSH backend")

    return missing, warnings, {"active_request": active_path, "candidate_backend": candidate}


def validate_experiment_failure_lineage(
    base: Path,
    ledger: dict[str, Any] | None,
    require_failure_diagnosis: bool = False,
) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    entries = rows_from_payload((ledger or {}).get("entries") if isinstance(ledger, dict) else None)
    failure_like = {
        "failed",
        "failure",
        "budget_stopped",
        "not_promoted",
        "rollback_to_best",
        "repair",
        "regressed",
        "spec_violation",
    }
    for index, entry in enumerate(entries):
        prefix = f"coder/EXPERIMENT_LEDGER.json entries[{index}]"
        decision = str(entry.get("promotion_decision") or entry.get("promotion_status") or entry.get("verdict") or "").strip().lower()
        status = str(entry.get("status") or "").strip().lower()
        spec = str(entry.get("spec_violation_status") or "").strip().lower()
        is_failure = decision in failure_like or status in {"failed", "failure", "budget_stopped", "regressed"} or spec in {"flagged", "violation", "failed"}
        if is_failure:
            if not present(entry.get("failure_class")):
                missing.append(f"{prefix}.failure_class")
            if require_failure_diagnosis:
                diagnosis = entry.get("failure_diagnosis")
                if not present(diagnosis):
                    missing.append(f"{prefix}.failure_diagnosis")
                elif isinstance(diagnosis, dict):
                    for field in ["primary_cause", "evidence_sufficiency", "intervention_level", "repair_route"]:
                        if not present(diagnosis.get(field)):
                            missing.append(f"{prefix}.failure_diagnosis.{field}")
                    if diagnosis.get("repair_route") == "same_idea_retry" and not present(diagnosis.get("repeated_failure_key")):
                        missing.append(f"{prefix}.failure_diagnosis.repeated_failure_key for same_idea_retry")
                else:
                    missing.append(f"{prefix}.failure_diagnosis must be an object with primary_cause/evidence_sufficiency/intervention_level/repair_route")
            if not present(entry.get("next_action")):
                missing.append(f"{prefix}.next_action")
            if not present(entry.get("selected_idea_id")):
                missing.append(f"{prefix}.selected_idea_id")
            if not present(entry.get("track_id")):
                missing.append(f"{prefix}.track_id")
        if decision == "candidate_supported":
            warnings.append(f"{prefix} candidate_supported is pilot evidence and cannot support stable improvement claims")
    return missing, warnings, {"entry_count": len(entries)}


def resolve_result_path(project_root: Path, base: Path, value: Any) -> Path | None:
    if not present(value):
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    project_candidate = project_root / path
    if project_candidate.exists():
        return project_candidate
    return base / path


def result_bearing_entry(entry: dict[str, Any]) -> bool:
    status = normalized(entry.get("status") or entry.get("run_status"))
    decision = normalized(entry.get("promotion_decision") or entry.get("promotion_status") or entry.get("verdict"))
    if any(
        present(entry.get(key))
        for key in [
            "latest_metric",
            "final_metric",
            "metrics",
            "result",
            "result_summary_path",
            "metric_trajectory_path",
            "candidate_supported",
        ]
    ):
        return True
    return (
        status in {"complete", "completed", "terminal", "terminal_complete", "terminal_not_promoted", "failed", "regressed", "budget_stopped"}
        or status.startswith("terminal")
        or decision in {"candidate_supported", "promoted", "not_promoted", "terminal_not_promoted", "failed", "regressed"}
        or decision.startswith("not_promoted")
    )


def summary_has_final_and_best(summary: dict[str, Any]) -> tuple[bool, bool, bool]:
    """Return whether summary has final metric, best-so-far, and trajectory path."""

    has_final = present(summary.get("final_metric") or summary.get("latest_metric"))
    has_best = present(summary.get("best_so_far") or summary.get("best_metric") or summary.get("best_metrics"))
    runs = summary.get("runs")
    if isinstance(runs, dict) and runs:
        run_values = [row for row in runs.values() if isinstance(row, dict)]
        has_final = has_final or all(present(row.get("final_metric") or row.get("latest_metric")) for row in run_values)
        has_best = has_best or all(present(row.get("best_so_far") or row.get("best_metric") or row.get("best_metrics")) for row in run_values)
    trajectory_ref = summary.get("trajectory_csv_path") or summary.get("metric_trajectory_path") or summary.get("trajectory_path")
    has_trajectory = present(trajectory_ref)
    return has_final, has_best, has_trajectory


def validate_experiment_result_summaries(project: str, base: Path, ledger: dict[str, Any] | None) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"checked_entries": 0, "summary_paths": []}
    project_root = Path(project).expanduser().resolve()
    entries = rows_from_payload((ledger or {}).get("entries") if isinstance(ledger, dict) else None)
    if not entries and isinstance(ledger, dict):
        entries = rows_from_payload(ledger)
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not result_bearing_entry(entry):
            continue
        details["checked_entries"] += 1
        prefix = f"coder/EXPERIMENT_LEDGER.json entries[{index}]"
        summary_ref = (
            entry.get("result_summary_path")
            or entry.get("result_summary_json")
            or entry.get("result_summary")
            or entry.get("summary_path")
        )
        if isinstance(summary_ref, dict):
            has_final, has_best, has_trajectory = summary_has_final_and_best(summary_ref)
            if not has_final:
                missing.append(f"{prefix}.result_summary.final_metric")
            if not has_best:
                missing.append(f"{prefix}.result_summary.best_so_far")
            if not has_trajectory and not present(entry.get("metric_trajectory_path")):
                missing.append(f"{prefix}.result_summary.trajectory_csv_path")
            continue
        summary_path = resolve_result_path(project_root, base, summary_ref)
        if summary_path is None:
            missing.append(f"{prefix}.result_summary_path")
            continue
        details["summary_paths"].append(str(summary_path))
        summary = read_json(summary_path)
        if not isinstance(summary, dict):
            missing.append(f"{prefix}.result_summary_path points to readable JSON")
            continue
        has_final, has_best, has_trajectory = summary_has_final_and_best(summary)
        if not has_final:
            missing.append(f"{prefix}.result_summary final_metric/latest_metric")
        if not has_best:
            missing.append(f"{prefix}.result_summary best_so_far")
        trajectory_ref = (
            entry.get("metric_trajectory_path")
            or summary.get("trajectory_csv_path")
            or summary.get("metric_trajectory_path")
            or summary.get("trajectory_path")
        )
        trajectory_path = resolve_result_path(project_root, base, trajectory_ref)
        if not has_trajectory and trajectory_path is None:
            missing.append(f"{prefix}.metric_trajectory_path")
        elif trajectory_path is not None and not trajectory_path.exists():
            warnings.append(f"{prefix}.metric_trajectory_path does not exist yet: {trajectory_path}")
    return missing, warnings, details


def validate_post_analysis_self_audit(summary: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    missing: list[str] = []
    audit = first_present(
        summary,
        [
            "post_analysis_self_audit",
            "analysis_self_audit",
            "post_analysis_review",
            "analysis_uncertainty_review",
        ],
    )
    if not isinstance(audit, dict):
        return ["analyzer/IDEA_OUTCOME_SUMMARY.json post_analysis_self_audit"], {"post_analysis_self_audit_present": False}

    least_confident = first_present(
        audit,
        [
            "least_confident_point",
            "least_confident_conclusion",
            "lowest_confidence_point",
            "weakest_conclusion",
        ],
    )
    largest_misunderstanding = first_present(
        audit,
        [
            "largest_possible_misunderstanding",
            "biggest_misunderstanding",
            "largest_blind_spot",
            "unnoticed_context",
        ],
    )
    if not present(least_confident):
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json post_analysis_self_audit.least_confident_point")
    if not present(largest_misunderstanding):
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json post_analysis_self_audit.largest_possible_misunderstanding")
    return missing, {
        "post_analysis_self_audit_present": True,
        "least_confident_point_present": present(least_confident),
        "largest_possible_misunderstanding_present": present(largest_misunderstanding),
    }


def validate_idea_outcome_summary(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    summary = read_json(base / "analyzer/IDEA_OUTCOME_SUMMARY.json")
    if not summary:
        return ["analyzer/IDEA_OUTCOME_SUMMARY.json"], warnings, {}
    outcomes = summary.get("idea_outcomes") or summary.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json idea_outcomes[]")
        outcomes = []
    if not present(summary.get("source_idea_decision_ledger_path")):
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json source_idea_decision_ledger_path")
    if not present(summary.get("source_experiment_ledger_path")):
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json source_experiment_ledger_path")
    for index, outcome in enumerate(row for row in outcomes if isinstance(row, dict)):
        prefix = f"analyzer/IDEA_OUTCOME_SUMMARY.json idea_outcomes[{index}]"
        for field in ["idea_id", "lifecycle_status", "claim_scope", "outcome_status", "next_action"]:
            if not present(outcome.get(field)):
                missing.append(f"{prefix}.{field}")
        claim_scope = str(outcome.get("claim_scope") or "").strip().lower()
        if claim_scope in {"strong_improvement", "stable_improvement", "promoted"} and not present(outcome.get("promoted_run_ref")):
            missing.append(f"{prefix}.promoted_run_ref for strong/promoted claim scope")
        if str(outcome.get("outcome_status") or "").strip().lower() in {"failed", "regressed", "killed", "parked"}:
            if claim_scope not in {"negative_evidence", "limitation", "future_work", "pilot_only", "no_claim", "downgraded"}:
                missing.append(f"{prefix}.claim_scope must not be strong for failed/regressed/parked/killed ideas")
    effective_missing, effective_warnings, effective_details = validate_effective_innovation_points(base)
    missing.extend(effective_missing)
    warnings.extend(effective_warnings)
    self_audit_missing, self_audit_details = validate_post_analysis_self_audit(summary)
    missing.extend(self_audit_missing)
    return missing, warnings, {"outcome_count": len(outcomes), **effective_details, **self_audit_details}


def iter_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        rows: list[dict[str, Any]] = []
        for key in ["rows", "slices", "components", "effects", "metrics", "checks"]:
            child = value.get(key)
            if isinstance(child, list):
                rows.extend(row for row in child if isinstance(row, dict))
            elif isinstance(child, dict):
                rows.extend(row for row in child.values() if isinstance(row, dict))
        if rows:
            return rows
        return [value]
    return []


def check_disaggregated_effects(value: Any) -> list[str]:
    missing: list[str] = []
    rows = iter_rows(value)
    if not rows:
        return ["analyzer/SCORE_VERIFICATION.json disaggregated_effects rows/slices"]
    critical_checked = False
    regressed_critical = False
    for index, row in enumerate(rows):
        prefix = f"analyzer/SCORE_VERIFICATION.json disaggregated_effects[{index}]"
        is_critical = row.get("critical") is True or normalized(row.get("claim_relevance")) in {"critical", "primary", "required"}
        if is_critical:
            critical_checked = True
        direction = normalized(row.get("direction") or row.get("effect_direction") or row.get("delta_direction") or row.get("status"))
        regressed = direction in {"regressed", "negative", "loss", "worse", "degraded"} or row.get("regressed") is True
        if is_critical and regressed:
            regressed_critical = True
            disposition = normalized(row.get("claim_disposition") or row.get("promotion_decision") or row.get("claim_status"))
            if disposition not in {"downgraded", "blocked", "no_strong_claim", "claim_limited", "requires_repair"}:
                missing.append(f"{prefix}.claim_disposition must downgrade/block a regressed critical slice")
        if is_critical and not present(row.get("evidence_ref") or row.get("metric_ref") or row.get("result_ref")):
            missing.append(f"{prefix}.evidence_ref")
    if not critical_checked:
        missing.append("analyzer/SCORE_VERIFICATION.json disaggregated_effects must mark at least one critical claim slice")
    if regressed_critical:
        top_status = normalized(value.get("claim_status") if isinstance(value, dict) else "")
        if top_status in {"passed", "strong", "strong_claim_allowed", "promoted"}:
            missing.append("analyzer/SCORE_VERIFICATION.json disaggregated_effects top-level claim_status cannot pass with regressed critical slice")
    return missing


def check_mechanism_support(value: Any) -> list[str]:
    missing: list[str] = []
    if not isinstance(value, dict):
        return ["analyzer/SCORE_VERIFICATION.json mechanism_support object"]
    if not present(value.get("mechanism_claim")):
        missing.append("analyzer/SCORE_VERIFICATION.json mechanism_support.mechanism_claim")
    if not field_present_any(value, ["observed_evidence", "evidence_ref", "ablation_ref", "analysis_ref"]):
        missing.append("analyzer/SCORE_VERIFICATION.json mechanism_support.evidence_ref or observed_evidence")
    support_status = normalized(value.get("status") or value.get("support_status") or value.get("mechanism_status"))
    allowed_wording = normalized(value.get("allowed_wording") or value.get("claim_permission"))
    if support_status in {"unsupported", "outcome_only", "weak", "conflicted"} and any(
        token in allowed_wording for token in ["show", "demonstrate", "prove", "mechanism_confirmed", "strong"]
    ):
        missing.append("analyzer/SCORE_VERIFICATION.json mechanism_support cannot allow strong mechanism wording with weak/outcome-only support")
    return missing


def check_validation_to_test_transfer(value: Any) -> list[str]:
    missing: list[str] = []
    if not isinstance(value, dict):
        return ["analyzer/SCORE_VERIFICATION.json validation_to_test_transfer object"]
    for field in ["validation_selection_ref", "target_or_test_ref", "transfer_status", "claim_status"]:
        if not present(value.get(field)):
            missing.append(f"analyzer/SCORE_VERIFICATION.json validation_to_test_transfer.{field}")
    transfer_status = normalized(value.get("transfer_status"))
    claim_status = normalized(value.get("claim_status"))
    if transfer_status in {"unknown", "not_tested", "failed", "regressed"} and claim_status in {"strong", "strong_claim_allowed", "passed", "promoted"}:
        missing.append("analyzer/SCORE_VERIFICATION.json validation_to_test_transfer cannot allow strong claim without successful transfer")
    return missing


def validate_score_verification_hardening(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    score = read_json(base / "analyzer/SCORE_VERIFICATION.json")
    if not isinstance(score, dict):
        return ["analyzer/SCORE_VERIFICATION.json"], warnings, {}
    for field in SCORE_VERIFICATION_FIELDS:
        if not present(score.get(field)):
            missing.append(f"analyzer/SCORE_VERIFICATION.json {field}")
    if present(score.get("disaggregated_effects")):
        missing.extend(check_disaggregated_effects(score["disaggregated_effects"]))
    if present(score.get("mechanism_support")):
        missing.extend(check_mechanism_support(score["mechanism_support"]))
    if present(score.get("validation_to_test_transfer")):
        missing.extend(check_validation_to_test_transfer(score["validation_to_test_transfer"]))
    registry = score.get("numeric_measurement_registry")
    if isinstance(registry, dict):
        for field in ["metric_units", "parser_source", "baseline_source", "measurement_refs"]:
            if not present(registry.get(field)):
                missing.append(f"analyzer/SCORE_VERIFICATION.json numeric_measurement_registry.{field}")
    return missing, warnings, {"score_verification_fields": SCORE_VERIFICATION_FIELDS}


def validate_idea_outcome_hardening(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    summary = read_json(base / "analyzer/IDEA_OUTCOME_SUMMARY.json")
    if not isinstance(summary, dict):
        return ["analyzer/IDEA_OUTCOME_SUMMARY.json"], warnings, {}
    if not present(summary.get("negative_knowledge_summary")):
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json negative_knowledge_summary")
    points = summary.get("effective_innovation_points") or summary.get("accepted_innovation_points")
    checked = 0
    if isinstance(points, list):
        for index, point in enumerate(row for row in points if isinstance(row, dict)):
            checked += 1
            prefix = f"analyzer/IDEA_OUTCOME_SUMMARY.json effective_innovation_points[{index}]"
            if not field_present_any(point, ["evidence_ref", "evidence_refs", "promoted_run_ref", "review_acceptance_ref"]):
                missing.append(f"{prefix}.evidence_ref")
            if not present(point.get("mechanism_status")):
                missing.append(f"{prefix}.mechanism_status")
            if not field_present_any(point, ["claim_permission", "claim_scope"]):
                missing.append(f"{prefix}.claim_permission")
    return missing, warnings, {"checked_effective_points": checked}


def innovation_role_bucket(value: Any) -> str | None:
    text = normalized(value)
    if not text:
        return None
    if any(token in text for token in ["problem", "protocol", "evaluation", "framing", "benchmark"]):
        return "problem_protocol_evaluation"
    if any(token in text for token in ["method", "mechanism", "module", "algorithm", "assignment"]):
        return "method_mechanism"
    if any(token in text for token in ["training", "integration", "analysis", "validation", "evidence", "diagnostic"]):
        return "training_integration_analysis_validation"
    return None


def validate_effective_innovation_points(base: Path, min_count: int = 3) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    summary = read_json(base / "analyzer/IDEA_OUTCOME_SUMMARY.json")
    if not isinstance(summary, dict):
        return ["analyzer/IDEA_OUTCOME_SUMMARY.json"], warnings, {"effective_innovation_point_count": 0}
    points = summary.get("effective_innovation_points") or summary.get("accepted_innovation_points")
    if not isinstance(points, list) or not points:
        return ["analyzer/IDEA_OUTCOME_SUMMARY.json effective_innovation_points[]"], warnings, {"effective_innovation_point_count": 0}

    accepted_statuses = {
        "effective",
        "accepted",
        "confirmed",
        "validated",
        "promoted",
        "supported",
        "review_accepted",
        "evidence_backed",
    }
    rejected_statuses = {
        "failed",
        "regressed",
        "killed",
        "parked",
        "not_promoted",
        "terminal_not_promoted",
        "negative",
        "future_work",
        "unsupported",
        "pilot_only",
    }
    low_priority_objectives = {"parameter_tuning", "diagnostic", "resource_fill"}
    accepted_count = 0
    role_buckets: set[str] = set()

    for index, point in enumerate(row for row in points if isinstance(row, dict)):
        prefix = f"analyzer/IDEA_OUTCOME_SUMMARY.json effective_innovation_points[{index}]"
        identifier = point.get("innovation_point_id") or point.get("id") or point.get("idea_id") or point.get("name")
        if not present(identifier):
            missing.append(f"{prefix}.innovation_point_id")
        role = point.get("story_role") or point.get("role") or point.get("contribution_role")
        if not present(role):
            missing.append(f"{prefix}.story_role")
        bucket = innovation_role_bucket(role)
        if not bucket:
            missing.append(f"{prefix}.story_role must map to problem/protocol/evaluation, method/mechanism, or training/integration/analysis/validation")
        evidence_status = normalized(point.get("evidence_status") or point.get("status") or point.get("outcome_status"))
        if evidence_status not in accepted_statuses:
            missing.append(f"{prefix}.evidence_status effective/accepted/confirmed/validated/promoted")
        lifecycle_status = normalized(point.get("lifecycle_status") or point.get("promotion_decision") or point.get("promotion_status"))
        if lifecycle_status in rejected_statuses:
            missing.append(f"{prefix}.lifecycle_status must not be {lifecycle_status}")
        objective_class = normalized(point.get("objective_class"))
        if objective_class in low_priority_objectives and point.get("reclassified_by_idea_gate") is not True:
            missing.append(f"{prefix}.objective_class {objective_class} cannot count as an effective innovation point without reclassified_by_idea_gate=true")
        if not present(point.get("claim_scope")):
            missing.append(f"{prefix}.claim_scope")
        evidence_ref = point.get("promoted_run_ref") or point.get("evidence_ref") or point.get("review_acceptance_ref") or point.get("analysis_ref")
        if not present(evidence_ref):
            missing.append(f"{prefix}.evidence_ref or promoted_run_ref or review_acceptance_ref")
        low_priority_reclassified = objective_class in low_priority_objectives and point.get("reclassified_by_idea_gate") is True
        if evidence_status in accepted_statuses and lifecycle_status not in rejected_statuses and (objective_class not in low_priority_objectives or low_priority_reclassified):
            accepted_count += 1
            if bucket:
                role_buckets.add(bucket)

    required_buckets = {
        "problem_protocol_evaluation",
        "method_mechanism",
        "training_integration_analysis_validation",
    }
    if accepted_count < min_count:
        missing.append(f"analyzer/IDEA_OUTCOME_SUMMARY.json effective_innovation_points needs at least {min_count} accepted points; found {accepted_count}")
    missing_buckets = sorted(required_buckets - role_buckets)
    if missing_buckets:
        missing.append(f"analyzer/IDEA_OUTCOME_SUMMARY.json effective_innovation_points missing story roles {missing_buckets}")
    return missing, warnings, {"effective_innovation_point_count": accepted_count, "effective_innovation_role_buckets": sorted(role_buckets)}


def read_first_json(base: Path, rels: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    for rel in rels:
        payload = read_json(base / rel)
        if isinstance(payload, dict):
            return payload, rel
    return None, None


def review_axis_bucket(value: Any) -> str | None:
    text = normalized(value)
    if not text:
        return None
    if "claim_drift" in text or ("claim" in text and "drift" in text):
        return "claim_drift"
    if "scientific_alignment" in text or ("scientific" in text and "align" in text):
        return "scientific_alignment"
    if "defensive_underclaim" in text or ("defensive" in text and "underclaim" in text):
        return "defensive_underclaim"
    if "novel" in text or "prior" in text:
        return "novelty"
    if any(token in text for token in ["sound", "method", "mechanism", "validity"]):
        return "soundness_method"
    if any(token in text for token in ["experiment", "stat", "metric", "ablation", "baseline"]):
        return "experiments_statistics"
    if any(token in text for token in ["clarity", "writing", "organization", "story"]):
        return "clarity_writing"
    if any(token in text for token in ["repro", "ethic", "limitation", "claim", "artifact"]):
        return "reproducibility_limitations"
    return None


def validate_multi_round_review_gate(
    base: Path,
    min_rounds: int = 2,
    require_hardening_axes: bool = False,
) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    gate, gate_rel = read_first_json(
        base,
        [
            "reviewer/MULTI_ROUND_REVIEW_GATE.json",
            "review/MULTI_ROUND_REVIEW_GATE.json",
        ],
    )
    ledger, ledger_rel = read_first_json(
        base,
        [
            "reviewer/REVIEW_REPAIR_LEDGER.json",
            "review/REVIEW_REPAIR_LEDGER.json",
        ],
    )
    if not gate:
        missing.append("reviewer/MULTI_ROUND_REVIEW_GATE.json")
        return missing, warnings, {"completed_review_rounds": 0}
    status = normalized(gate.get("status") or gate.get("gate_status"))
    if status not in READY:
        missing.append(f"{gate_rel} status passed/ready")
    rounds = gate.get("review_rounds") or gate.get("rounds")
    if isinstance(rounds, list):
        completed_rounds = len([row for row in rounds if isinstance(row, dict) and normalized(row.get("status") or row.get("state")) in READY])
    else:
        completed_rounds = int(gate.get("completed_rounds") or gate.get("round_count") or 0)
    if completed_rounds < min_rounds:
        missing.append(f"{gate_rel} completed_rounds >= {min_rounds}")
    blocking_count = int(gate.get("open_blocking_count") or gate.get("unresolved_blocker_count") or 0)
    if gate.get("unresolved_blockers") is True or blocking_count > 0:
        missing.append(f"{gate_rel} no unresolved blockers")
    axes_payload = gate.get("review_axes") or gate.get("covered_axes") or gate.get("axes")
    axis_buckets: set[str] = set()
    if isinstance(axes_payload, list):
        for item in axes_payload:
            bucket = review_axis_bucket(item)
            if bucket:
                axis_buckets.add(bucket)
    required_axes = {
        "novelty",
        "soundness_method",
        "experiments_statistics",
        "clarity_writing",
        "reproducibility_limitations",
    }
    if require_hardening_axes:
        required_axes.update({"claim_drift", "scientific_alignment", "defensive_underclaim"})
    missing_axes = sorted(required_axes - axis_buckets)
    if missing_axes:
        missing.append(f"{gate_rel} review_axes missing {missing_axes}")
    if not ledger:
        missing.append("reviewer/REVIEW_REPAIR_LEDGER.json")
    else:
        repairs = ledger.get("repairs") or ledger.get("round_repairs") or ledger.get("entries")
        if not isinstance(repairs, list) or len(repairs) < min_rounds:
            missing.append(f"{ledger_rel} repairs for at least {min_rounds} review rounds")
    return missing, warnings, {"completed_review_rounds": completed_rounds, "review_axes": sorted(axis_buckets)}


def validate_review_findings_hardening(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    findings = read_json(base / "reviewer/REVIEW_FINDINGS.json")
    if not isinstance(findings, dict):
        return ["reviewer/REVIEW_FINDINGS.json"], warnings, {}
    axis_buckets: set[str] = set()
    axes_payload = findings.get("review_axes") or findings.get("covered_axes") or findings.get("axes")
    if isinstance(axes_payload, list):
        for item in axes_payload:
            bucket = review_axis_bucket(item)
            if bucket:
                axis_buckets.add(bucket)
    for key in ["issues", "findings", "review_findings", "items"]:
        rows = findings.get(key)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                bucket = review_axis_bucket(row.get("axis") or row.get("category") or row.get("type"))
                if bucket:
                    axis_buckets.add(bucket)
    required = {"claim_drift", "scientific_alignment", "defensive_underclaim"}
    missing_axes = sorted(required - axis_buckets)
    if missing_axes:
        missing.append(f"reviewer/REVIEW_FINDINGS.json axes missing {missing_axes}")
    return missing, warnings, {"review_finding_axes": sorted(axis_buckets)}


def truthy_value(value: Any) -> bool:
    if value is True:
        return True
    return normalized(value) in {"true", "yes", "pass", "passed", "ready", "verified", "preserved", "blocked", "complete"}


def falsy_value(value: Any) -> bool:
    if value is False:
        return True
    return normalized(value) in {"false", "no", "none", "absent", "zero", "not_detected", "clear"}


def dict_status_ready(value: Any, label: str) -> list[str]:
    if not present(value):
        return [label]
    if isinstance(value, dict):
        status = normalized(value.get("status") or value.get("state") or value.get("verdict"))
        if status and status not in READY:
            return [f"{label}.status passed/ready"]
        if value.get("blocking_failures") is True or value.get("open_blockers") is True:
            return [f"{label} no blocking failures"]
        blocker_count = value.get("blocking_count") or value.get("open_blocker_count") or value.get("unresolved_blocker_count")
        if isinstance(blocker_count, int) and blocker_count > 0:
            return [f"{label} no open blockers"]
        return []
    if normalized(value) not in READY:
        return [f"{label} passed/ready"]
    return []


def list_mentions(value: Any, needles: set[str]) -> bool:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value).lower()
    else:
        text = str(value or "").lower()
    return any(needle in text for needle in needles)


def validate_non_defensive_claim_posture(value: Any) -> list[str]:
    missing: list[str] = []
    label = "paper/PAPER_CLAIM_VERIFICATION.json non_defensive_writing_status"
    if not present(value):
        return [label]
    if not isinstance(value, dict):
        return dict_status_ready(value, label)

    missing.extend(dict_status_ready(value, label))
    if not any(
        truthy_value(value.get(field))
        for field in ["necessary_limitations_preserved", "true_limitations_preserved", "real_limitations_preserved"]
    ):
        missing.append(f"{label}.necessary_limitations_preserved")
    if not any(
        truthy_value(value.get(field))
        for field in ["evidence_boundary_preserved", "claim_boundaries_preserved", "scope_boundaries_preserved"]
    ):
        missing.append(f"{label}.evidence_boundary_preserved")
    claim_upgrades_blocked = any(
        truthy_value(value.get(field))
        for field in ["claim_upgrades_blocked", "unsupported_claim_upgrades_blocked", "overclaim_blocked"]
    ) or any(
        falsy_value(value.get(field))
        for field in ["unsupported_claim_upgrades", "claim_upgrades_detected", "overclaiming_introduced"]
    )
    if not claim_upgrades_blocked:
        missing.append(f"{label}.claim_upgrades_blocked or unsupported_claim_upgrades=false")
    if value.get("defensive_underclaim_remaining") is True:
        missing.append(f"{label}.defensive_underclaim_remaining must be false")
    if value.get("overclaiming_introduced") is True or value.get("unsupported_claim_upgrades") is True:
        missing.append(f"{label} must not introduce unsupported claim upgrades")
    if not field_present_any(
        value,
        ["top_tier_claim_posture", "reviewer_risk_positions_checked", "front_matter_claim_posture"],
    ):
        missing.append(f"{label}.top_tier_claim_posture or reviewer_risk_positions_checked")
    locations = (
        value.get("locations_checked")
        or value.get("high_impact_positions_checked")
        or value.get("front_matter_positions_checked")
        or value.get("checked_locations")
    )
    if not present(locations):
        missing.append(f"{label}.high_impact_positions_checked")
    elif not list_mentions(locations, {"title", "abstract", "introduction", "contribution"}):
        missing.append(f"{label}.high_impact_positions_checked must include front matter or contribution positions")
    return missing


def validate_writing_hardening(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    verification = read_json(base / "paper/PAPER_CLAIM_VERIFICATION.json")
    if not isinstance(verification, dict):
        missing.append("paper/PAPER_CLAIM_VERIFICATION.json")
    else:
        for field in PAPER_CLAIM_VERIFICATION_FIELDS:
            if not present(verification.get(field)):
                missing.append(f"paper/PAPER_CLAIM_VERIFICATION.json {field}")
        for field in ["claim_drift_status", "scientific_alignment_status", "numeric_grounding_status"]:
            missing.extend(dict_status_ready(verification.get(field), f"paper/PAPER_CLAIM_VERIFICATION.json {field}"))
        missing.extend(validate_non_defensive_claim_posture(verification.get("non_defensive_writing_status")))
    audit = base / "paper/CCFA_WRITING_AUDIT.md"
    if audit.exists():
        text = audit.read_text(encoding="utf-8", errors="ignore").lower()
        if "non-defensive writing pass" not in text and "non defensive writing pass" not in text:
            missing.append("paper/CCFA_WRITING_AUDIT.md Non-Defensive Writing Pass")
        if "necessary limitations preserved" not in text and "necessary limitation preserved" not in text:
            missing.append("paper/CCFA_WRITING_AUDIT.md Necessary Limitations Preserved")
        if "claim upgrades blocked" not in text and "unsupported claim upgrades" not in text:
            missing.append("paper/CCFA_WRITING_AUDIT.md Claim Upgrades Blocked")
        if "top-tier reviewer" not in text and "reviewer risk" not in text and "front matter claim posture" not in text:
            missing.append("paper/CCFA_WRITING_AUDIT.md Top-Tier Reviewer Risk or Front Matter Claim Posture")
    else:
        warnings.append("paper/CCFA_WRITING_AUDIT.md missing; required for top-tier/CCF-A manuscript polish")
    return missing, warnings, {"paper_claim_verification_fields": PAPER_CLAIM_VERIFICATION_FIELDS}


def result(
    stage: str,
    complete: bool,
    missing: list[str],
    source: str,
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "missing": missing,
        "warnings": warnings or [],
        "contract_source": source,
        "details": details or {},
    }


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"stdout": proc.stdout}
    parsed.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    return parsed


def run_innovation_story_lint(skill_root: Path, project: str, stage: str) -> dict[str, Any]:
    return run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-workflow/scripts/innovation_story_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
            "--stage",
            stage,
        ]
    )


def run_paper_code_transfer_lint(skill_root: Path, project: str) -> dict[str, Any]:
    return run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-workflow/scripts/paper_code_transfer_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
        ]
    )


def run_baseline_report_alignment_lint(skill_root: Path, project: str, stage: str) -> dict[str, Any]:
    return run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-workflow/scripts/baseline_report_alignment_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
            "--stage",
            stage,
        ]
    )


def run_paper_forensics_lint(skill_root: Path, project: str, stage: str) -> dict[str, Any]:
    return run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-workflow/scripts/paper_forensics_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
            "--stage",
            stage,
        ]
    )


def lint(project: str, stage: str) -> dict[str, Any]:
    base = ar(project)
    scope = workflow_scope(base)
    strong_contract = requires_strong_paper_contract(base)
    if stage == "init":
        missing = [
            rel
            for rel in [
                "goal_state.json",
                "autopilot_policy.json",
                "capabilities.json",
                "memory.md",
                "decision_log.jsonl",
                "blocker_ledger.jsonl",
                "repair_queue.jsonl",
                "async_jobs.jsonl",
            ]
            if not (base / rel).exists()
        ]
        warnings: list[str] = []
        add_scope_warnings(base, warnings)
        return result(stage, not missing, missing, "init_contract", warnings, {"scope": scope})

    if stage == "topic_search":
        missing = []
        if not has_any(base, ["literature/LITERATURE_DISCOVERY_PACKET.json", "literature/LITERATURE_DISCOVERY_RUN.json"]):
            missing.append("literature discovery evidence")
        for rel in [
            "papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
            "papernexus/PAPER_SELECTION_SCORECARD.json",
            "papernexus/GRAPH_IMPORT_PLAN.json",
        ]:
            if not nonempty(base / rel):
                missing.append(rel)
        return result(stage, not missing, missing, "topic_search_contract")

    if stage == "graph_build":
        skill_root = Path(__file__).resolve().parents[2]
        decision = read_json(base / "graph/GRAPH_BUILD_DECISION.json")
        graph_plan = read_json(base / "papernexus/GRAPH_IMPORT_PLAN.json")
        graph_plan_counts = graph_plan_action_counts(graph_plan)
        import_workflow_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/import_workflow_status_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        missing = []
        warnings = []
        source_limited = source_limited_import_lint(import_workflow_lint)
        if source_limited:
            if not source_limited_graph_decision_allows_advance(decision):
                missing.append(
                    "graph/GRAPH_BUILD_DECISION.json decision=advance_with_source_limited_exceptions with "
                    "source_backed_graph_claim_scope=imported_only and explicit claim_limits/source_limited_exceptions"
                )
            else:
                warnings.append(
                    "graph_build is complete with source-limited exceptions; exception papers must not be used as graph-grounded evidence"
                )
        elif not bool(decision and decision.get("decision") == "complete" and decision.get("source_backed_graph_claim") is True):
            missing.append("graph/GRAPH_BUILD_DECISION.json decision=complete source_backed_graph_claim=true")
        if not isinstance(graph_plan, dict):
            missing.append("papernexus/GRAPH_IMPORT_PLAN.json")
        elif graph_plan_counts["import_required"]:
            if not import_workflow_lint.get("complete"):
                items = import_workflow_lint.get("missing") if isinstance(import_workflow_lint.get("missing"), list) else []
                if items:
                    missing.extend(f"import_workflow_status_lint: {item}" for item in items)
                else:
                    missing.append("papernexus/IMPORT_WORKFLOW_STATUS.json with all graph_import import/supplement tasks completed and authoritative-synced")
            if graph_plan_counts["material_required"] and not nonempty(base / "papernexus/SPLIT_READING_EVIDENCE_PACK.json"):
                warnings.append("material_view selected papers still need papernexus/SPLIT_READING_EVIDENCE_PACK.json before downstream evidence use")
        elif graph_plan_counts["selected"] and not nonempty(base / "papernexus/SPLIT_READING_EVIDENCE_PACK.json"):
            missing.append("papernexus/SPLIT_READING_EVIDENCE_PACK.json for selected material_view papers")
        items = import_workflow_lint.get("warnings") if isinstance(import_workflow_lint.get("warnings"), list) else []
        warnings.extend(f"import_workflow_status_lint: {item}" for item in items)
        return result(stage, not missing, missing, "graph_build_contract", warnings, {"import_workflow_status_lint": import_workflow_lint, "graph_plan_counts": graph_plan_counts})

    if stage == "frontier_mapping":
        ok = has_any(base, ["papernexus/research_material_pack.json", "papernexus/source_discovery_plan.json", "ideation/CHALLENGE_INSIGHT_TREE.md"])
        return result(stage, ok, [] if ok else ["frontier mapping material pack or challenge insight tree"], "frontier_mapping_contract")

    if stage == "literature_review":
        skill_root = Path(__file__).resolve().parents[2]
        transfer_lint = run_paper_code_transfer_lint(skill_root, project)
        missing = [
            rel
            for rel in ["literature/SOTA_MATRIX.md", "literature/GAP_SYNTHESIS.md", "literature/CITATION_QUEUE.json"]
            if not nonempty(base / rel)
        ]
        warnings: list[str] = []
        add_scope_warnings(base, warnings)
        if not transfer_lint.get("complete"):
            items = transfer_lint.get("missing") if isinstance(transfer_lint.get("missing"), list) else []
            missing.extend(f"paper_code_transfer_lint: {item}" for item in items)
            if transfer_lint.get("returncode", 1) != 0 and not items:
                missing.append("paper_code_transfer_lint failed without structured missing output")
        items = transfer_lint.get("warnings") if isinstance(transfer_lint.get("warnings"), list) else []
        warnings.extend(f"paper_code_transfer_lint: {item}" for item in items)
        return result(stage, not missing, missing, "literature_review_contract", warnings, {"paper_code_transfer_lint": transfer_lint})

    if stage == "ideation":
        skill_root = Path(__file__).resolve().parents[2]
        contract = read_json(base / "ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json")
        discovery_packet = read_json(base / "literature/LITERATURE_DISCOVERY_PACKET.json")
        discovery_triage = read_json(base / "papernexus/LITERATURE_DISCOVERY_TRIAGE.json")
        gate_payload = read_json(base / "ideation/PRE_IDEA_EVIDENCE_GATE.json")
        caps = read_json(base / "capabilities.json") or {}
        agent_ops = set(caps.get("agent_materials_operations") or [])
        proposal_graph_available = caps.get("proposal_graph_session_available") is True or "proposal_graph_session" in agent_ops
        approved_degraded = degraded_gate_approved(gate_payload)
        pool_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--pool",
                "ideation/EXPERIMENT_IDEA_POOL.json",
            ]
        )
        scorecard_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_scorecard_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        idea_graph_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_graph_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        pre_idea_gate_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/pre_idea_evidence_gate_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--allow-degraded",
            ]
        )
        proposal_graph_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/proposal_graph_session_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        discovery_config_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/pre_idea_discovery_config_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        abstract_screening_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/abstract_screening_audit_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        paper_selection_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/paper_selection_scorecard_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        breadth_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/pre_idea_breadth_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        graph_import_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/graph_import_plan_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        import_workflow_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/import_workflow_status_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        split_reading_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/split_reading_evidence_pack_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        paper_code_transfer_lint = run_paper_code_transfer_lint(skill_root, project)
        idea_decision_missing, idea_decision_warnings, idea_decision_details = validate_idea_decision_ledger(base)
        missing = []
        warnings = []
        if approved_degraded:
            warnings.append("pre-idea gate is approved degraded; discovery/triage gaps are tracked as claim limits")
        elif not discovery_packet:
            missing.append("literature/LITERATURE_DISCOVERY_PACKET.json from pre-idea literature discovery")
        if approved_degraded:
            pass
        elif not discovery_triage:
            missing.append("papernexus/LITERATURE_DISCOVERY_TRIAGE.json from pre-idea candidate screening")
        elif discovery_triage.get("discovery_attempted") is not True:
            missing.append("papernexus/LITERATURE_DISCOVERY_TRIAGE.json discovery_attempted=true")
        elif discovery_triage.get("policy", {}).get("import_resolved") is not False or discovery_triage.get("policy", {}).get("process_imports") is not False:
            missing.append("first-pass ideation literature discovery must be metadata-only and non-importing")
        if not approved_degraded:
            for name, out in {
                "pre_idea_discovery_config_lint": discovery_config_lint,
                "abstract_screening_audit_lint": abstract_screening_lint,
                "paper_selection_scorecard_lint": paper_selection_lint,
                "pre_idea_breadth_lint": breadth_lint,
                "graph_import_plan_lint": graph_import_lint,
                "import_workflow_status_lint": import_workflow_lint,
                "split_reading_evidence_pack_lint": split_reading_lint,
            }.items():
                if not out.get("complete"):
                    items = out.get("missing") if isinstance(out.get("missing"), list) else []
                    missing.extend(f"{name}: {item}" for item in items)
                    if out.get("returncode", 1) != 0 and not items:
                        missing.append(f"{name} failed without structured missing output")
                items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
                warnings.extend(f"{name}: {item}" for item in items)
        if not pre_idea_gate_lint.get("complete"):
            items = pre_idea_gate_lint.get("missing") if isinstance(pre_idea_gate_lint.get("missing"), list) else []
            missing.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
            if pre_idea_gate_lint.get("returncode", 1) != 0 and not items:
                missing.append("pre_idea_evidence_gate_lint failed without structured missing output")
        items = pre_idea_gate_lint.get("warnings") if isinstance(pre_idea_gate_lint.get("warnings"), list) else []
        warnings.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
        if not contract:
            warnings.append("ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json missing; allowed when pre-idea evidence gate and slot map pass")
        elif contract.get("status") not in {"ready", "brainstorm_ready"}:
            warnings.append("ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json not ready; treating as PaperNexus evidence debt")
        if proposal_graph_available and not approved_degraded:
            if not proposal_graph_lint.get("complete"):
                items = proposal_graph_lint.get("missing") if isinstance(proposal_graph_lint.get("missing"), list) else []
                missing.extend(f"proposal_graph_session_lint: {item}" for item in items)
                if proposal_graph_lint.get("returncode", 1) != 0 and not items:
                    missing.append("proposal_graph_session_lint failed without structured missing output")
        elif not proposal_graph_available:
            warnings.append("proposal_graph_session unavailable or unrecorded; falling back to split-reading slots plus idea_catalyst/research_controller")
        if not pool_lint.get("complete"):
            items = pool_lint.get("missing") if isinstance(pool_lint.get("missing"), list) else []
            missing.extend(f"idea_pool_lint: {item}" for item in items)
            if pool_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_pool_lint failed without structured missing output")
        items = pool_lint.get("warnings") if isinstance(pool_lint.get("warnings"), list) else []
        warnings.extend(f"idea_pool_lint: {item}" for item in items)
        if not scorecard_lint.get("complete"):
            items = scorecard_lint.get("missing") if isinstance(scorecard_lint.get("missing"), list) else []
            missing.extend(f"idea_scorecard_lint: {item}" for item in items)
            if scorecard_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_scorecard_lint failed without structured missing output")
        items = scorecard_lint.get("warnings") if isinstance(scorecard_lint.get("warnings"), list) else []
        warnings.extend(f"idea_scorecard_lint: {item}" for item in items)
        if not idea_graph_lint.get("complete"):
            items = idea_graph_lint.get("missing") if isinstance(idea_graph_lint.get("missing"), list) else []
            missing.extend(f"idea_graph_lint: {item}" for item in items)
            if idea_graph_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_graph_lint failed without structured missing output")
        items = idea_graph_lint.get("warnings") if isinstance(idea_graph_lint.get("warnings"), list) else []
        warnings.extend(f"idea_graph_lint: {item}" for item in items)
        if not approved_degraded:
            for rel in ["ideation/IDEA_BUILD_BRIEF.json", "ideation/IDEA_BUILD_BRIEF.md", "ideation/GOE_IDEA_AUDIT.json"]:
                if not nonempty(base / rel):
                    missing.append(rel)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        if not paper_code_transfer_lint.get("complete"):
            items = paper_code_transfer_lint.get("missing") if isinstance(paper_code_transfer_lint.get("missing"), list) else []
            missing.extend(f"paper_code_transfer_lint: {item}" for item in items)
            if paper_code_transfer_lint.get("returncode", 1) != 0 and not items:
                missing.append("paper_code_transfer_lint failed without structured missing output")
        items = paper_code_transfer_lint.get("warnings") if isinstance(paper_code_transfer_lint.get("warnings"), list) else []
        warnings.extend(f"paper_code_transfer_lint: {item}" for item in items)
        positive_routes = sorted(base.glob("orchestrator/POSITIVE_ONLY_STRUCTURAL_LEAP_ROUTE*.json"))
        latest_positive_route = None
        latest_positive_route_rel = ""
        for path in reversed(positive_routes):
            payload = read_json(path)
            if isinstance(payload, dict) and payload.get("target_stage_after_decision") == "ideation":
                latest_positive_route = payload
                latest_positive_route_rel = str(path.relative_to(base))
                break
        if latest_positive_route:
            regen_status = read_json(base / "ideation/POSITIVE_ONLY_REGENERATION_STATUS.json")
            if not isinstance(regen_status, dict) or regen_status.get("status") != "complete" or regen_status.get("source_route") != latest_positive_route_rel:
                missing.append(
                    "ideation/POSITIVE_ONLY_REGENERATION_STATUS.json status=complete for latest positive-only structural-leap route"
                )
        return result(
            stage,
            not missing,
            missing,
            "ideation_contract",
            warnings,
            {
                "pre_idea_evidence_gate_lint": pre_idea_gate_lint,
                "pre_idea_discovery_config_lint": discovery_config_lint,
                "abstract_screening_audit_lint": abstract_screening_lint,
                "paper_selection_scorecard_lint": paper_selection_lint,
                "pre_idea_breadth_lint": breadth_lint,
                "graph_import_plan_lint": graph_import_lint,
                "import_workflow_status_lint": import_workflow_lint,
                "split_reading_evidence_pack_lint": split_reading_lint,
                "innovation_story_lint": innovation_story_lint,
                "paper_code_transfer_lint": paper_code_transfer_lint,
                "proposal_graph_session_lint": proposal_graph_lint,
                "idea_pool_lint": pool_lint,
                "idea_scorecard_lint": scorecard_lint,
                "idea_graph_lint": idea_graph_lint,
                "discovery_triage": discovery_triage or {},
                "proposal_graph_session_available": proposal_graph_available,
            },
        )

    if stage == "idea_gate":
        skill_root = Path(__file__).resolve().parents[2]
        pool_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--pool",
                "ideation/EXPERIMENT_IDEA_POOL.json",
                "--require-selected",
            ]
        )
        scorecard_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_scorecard_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        track_seed_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_track_seeds.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--check",
            ]
        )
        pre_idea_gate_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/pre_idea_evidence_gate_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--allow-degraded",
            ]
        )
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        paper_code_transfer_lint = run_paper_code_transfer_lint(skill_root, project)
        idea_decision_missing, idea_decision_warnings, idea_decision_details = validate_idea_decision_ledger(base)
        missing = []
        warnings = []
        if not has_any(base, ["ideation/TOURNAMENT_SCOREBOARD.json", "ideation/TOP3_DIRECTION_SUMMARY.md", "reviewer/IDEA_GATE_REVIEW.json"]):
            missing.append("idea gate review or tournament scoreboard")
        if not pool_lint.get("complete"):
            items = pool_lint.get("missing") if isinstance(pool_lint.get("missing"), list) else []
            missing.extend(f"idea_pool_lint: {item}" for item in items)
            if pool_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_pool_lint failed without structured missing output")
        items = pool_lint.get("warnings") if isinstance(pool_lint.get("warnings"), list) else []
        warnings.extend(f"idea_pool_lint: {item}" for item in items)
        if not pre_idea_gate_lint.get("complete"):
            items = pre_idea_gate_lint.get("missing") if isinstance(pre_idea_gate_lint.get("missing"), list) else []
            missing.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
            if pre_idea_gate_lint.get("returncode", 1) != 0 and not items:
                missing.append("pre_idea_evidence_gate_lint failed without structured missing output")
        items = pre_idea_gate_lint.get("warnings") if isinstance(pre_idea_gate_lint.get("warnings"), list) else []
        warnings.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
        if not scorecard_lint.get("complete"):
            items = scorecard_lint.get("missing") if isinstance(scorecard_lint.get("missing"), list) else []
            missing.extend(f"idea_scorecard_lint: {item}" for item in items)
            if scorecard_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_scorecard_lint failed without structured missing output")
        items = scorecard_lint.get("warnings") if isinstance(scorecard_lint.get("warnings"), list) else []
        warnings.extend(f"idea_scorecard_lint: {item}" for item in items)
        if not track_seed_lint.get("complete"):
            items = track_seed_lint.get("missing") if isinstance(track_seed_lint.get("missing"), list) else []
            missing.extend(f"idea_track_seeds: {item}" for item in items)
            if track_seed_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_track_seeds failed without structured missing output")
        items = track_seed_lint.get("warnings") if isinstance(track_seed_lint.get("warnings"), list) else []
        warnings.extend(f"idea_track_seeds: {item}" for item in items)
        missing.extend(f"idea_decision_ledger: {item}" for item in idea_decision_missing)
        warnings.extend(f"idea_decision_ledger: {item}" for item in idea_decision_warnings)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        if not paper_code_transfer_lint.get("complete"):
            items = paper_code_transfer_lint.get("missing") if isinstance(paper_code_transfer_lint.get("missing"), list) else []
            missing.extend(f"paper_code_transfer_lint: {item}" for item in items)
            if paper_code_transfer_lint.get("returncode", 1) != 0 and not items:
                missing.append("paper_code_transfer_lint failed without structured missing output")
        items = paper_code_transfer_lint.get("warnings") if isinstance(paper_code_transfer_lint.get("warnings"), list) else []
        warnings.extend(f"paper_code_transfer_lint: {item}" for item in items)
        negative_missing, negative_warnings, negative_details = validate_selected_negative_evidence_alignment(base)
        if negative_missing:
            missing.extend(f"selected_negative_evidence: {item}" for item in negative_missing)
        warnings.extend(f"selected_negative_evidence: {item}" for item in negative_warnings)
        return result(
            stage,
            not missing,
            missing,
            "idea_gate_contract",
            warnings,
            {
                "pre_idea_evidence_gate_lint": pre_idea_gate_lint,
                "idea_pool_lint": pool_lint,
                "idea_scorecard_lint": scorecard_lint,
                "idea_track_seeds": track_seed_lint,
                "idea_decision_ledger": idea_decision_details,
                "innovation_story_lint": innovation_story_lint,
                "paper_code_transfer_lint": paper_code_transfer_lint,
                "selected_negative_evidence": negative_details,
            },
        )

    if stage == "experiment_plan":
        skill_root = Path(__file__).resolve().parents[2]
        scripts = {
            "track_plan_matrix": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/track_plan_matrix.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--check",
            ],
            "prelaunch_lint": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/prelaunch_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ],
            "innovation_lint": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/innovation_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ],
            "innovation_story_lint": [
                sys.executable,
                str(skill_root / "autoreskill-workflow/scripts/innovation_story_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--stage",
                stage,
            ],
        }
        details = {name: run_json(cmd) for name, cmd in scripts.items()}
        details["paper_code_transfer_lint"] = run_paper_code_transfer_lint(skill_root, project)
        details["baseline_report_alignment_lint"] = run_baseline_report_alignment_lint(skill_root, project, stage)
        missing: list[str] = []
        warnings: list[str] = []
        complete = True
        for name, out in details.items():
            if not out.get("complete"):
                complete = False
                items = out.get("missing") if isinstance(out.get("missing"), list) else []
                missing.extend(f"{name}: {item}" for item in items)
                if out.get("returncode", 1) != 0 and not items:
                    missing.append(f"{name} failed without structured missing output")
            items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
            warnings.extend(f"{name}: {item}" for item in items)
        track_lifecycle_missing, track_lifecycle_warnings, track_lifecycle_details = validate_track_plan_lifecycle(base)
        if track_lifecycle_missing:
            complete = False
            missing.extend(f"track_plan_lifecycle: {item}" for item in track_lifecycle_missing)
        warnings.extend(f"track_plan_lifecycle: {item}" for item in track_lifecycle_warnings)
        details["track_plan_lifecycle"] = track_lifecycle_details
        hardening_missing, hardening_warnings, hardening_details = validate_minimal_track_plan_fields(base)
        if strong_contract and hardening_missing:
            complete = False
            missing.extend(f"minimal_hardening: {item}" for item in hardening_missing)
        elif hardening_missing:
            record_scoped_hardening(base, "minimal_hardening", hardening_missing, warnings, details)
            if scope["goal_type"] == "paper_producing_light":
                warnings.extend(f"minimal_hardening: {item}" for item in hardening_missing)
        warnings.extend(f"minimal_hardening: {item}" for item in hardening_warnings)
        details["minimal_hardening"] = hardening_details
        remap_missing, remap_warnings, remap_details = validate_backend_remap_closure(base)
        if remap_missing:
            complete = False
            missing.extend(f"backend_remap_closure: {item}" for item in remap_missing)
        warnings.extend(f"backend_remap_closure: {item}" for item in remap_warnings)
        details["backend_remap_closure"] = remap_details
        projection_missing, projection_warnings, projection_details = validate_selected_projection_alignment(base)
        if projection_missing:
            complete = False
            missing.extend(f"selected_projection_alignment: {item}" for item in projection_missing)
        warnings.extend(f"selected_projection_alignment: {item}" for item in projection_warnings)
        details["selected_projection_alignment"] = projection_details
        negative_missing, negative_warnings, negative_details = validate_selected_negative_evidence_alignment(base)
        if negative_missing:
            complete = False
            missing.extend(f"selected_negative_evidence: {item}" for item in negative_missing)
        warnings.extend(f"selected_negative_evidence: {item}" for item in negative_warnings)
        details["selected_negative_evidence"] = negative_details
        return result(stage, complete, missing, "experiment_plan_contract", warnings, details)

    if stage == "code":
        skill_root = Path(__file__).resolve().parents[2]
        missing = []
        if not nonempty(base / "coder/EXPERIMENT_INDEX.md"):
            missing.append("coder/EXPERIMENT_INDEX.md")
        if not has_glob(base, "coder/experiments/**/EXPERIMENT_MANIFEST.json"):
            missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
        if not (has_glob(base, "coder/experiments/**/logs/dry_run*") or has_glob(base, "coder/experiments/**/logs/real_*")):
            missing.append("coder/experiments/**/logs/dry_run* or coder/experiments/**/logs/real_*")
        details: dict[str, Any] = {}
        warnings: list[str] = []
        if has_glob(base, "coder/experiments/**/EXPERIMENT_MANIFEST.json"):
            scripts = {
                "baseline_clone_lint": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/baseline_clone_lint.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                ],
                "experiment_drift_lint": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/experiment_drift_lint.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                ],
                "track_implementation_index": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/track_implementation_index.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                    "--check",
                ],
                "experiment_real_readiness_lint": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/experiment_real_readiness_lint.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                ],
            }
            details = {name: run_json(cmd) for name, cmd in scripts.items()}
            details["baseline_report_alignment_lint"] = run_baseline_report_alignment_lint(skill_root, project, stage)
            for name, out in details.items():
                if not out.get("complete"):
                    items = out.get("missing") if isinstance(out.get("missing"), list) else []
                    missing.extend(f"{name}: {item}" for item in items)
                    if out.get("returncode", 1) != 0 and not items:
                        missing.append(f"{name} failed without structured missing output")
                items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
                warnings.extend(f"{name}: {item}" for item in items)
        projection_missing, projection_warnings, projection_details = validate_selected_projection_alignment(base)
        if projection_missing:
            missing.extend(f"selected_projection_alignment: {item}" for item in projection_missing)
        warnings.extend(f"selected_projection_alignment: {item}" for item in projection_warnings)
        details["selected_projection_alignment"] = projection_details
        negative_missing, negative_warnings, negative_details = validate_selected_negative_evidence_alignment(base)
        if negative_missing:
            missing.extend(f"selected_negative_evidence: {item}" for item in negative_missing)
        warnings.extend(f"selected_negative_evidence: {item}" for item in negative_warnings)
        details["selected_negative_evidence"] = negative_details
        return result(stage, not missing, missing, "code_contract", warnings, details)

    if stage == "experiment":
        missing = []
        warnings = []
        details: dict[str, Any] = {}
        ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json")
        if not nonempty(base / "coder/EXPERIMENT_LEDGER.json"):
            missing.append("coder/EXPERIMENT_LEDGER.json")
        if not (has_glob(base, "coder/experiments/**/REMOTE_RUN.json") or has_glob(base, "coder/experiments/**/results/*")):
            missing.append("REMOTE_RUN.json or experiment results")
        skill_root = Path(__file__).resolve().parents[2]
        protocol_out = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-run-experiment/scripts/baseline_protocol_launch_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        details["baseline_protocol_launch_lint"] = protocol_out
        clone_out = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-implement-experiment/scripts/baseline_clone_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        details["baseline_clone_lint"] = clone_out
        baseline_report_out = run_baseline_report_alignment_lint(skill_root, project, stage)
        details["baseline_report_alignment_lint"] = baseline_report_out
        if not clone_out.get("complete"):
            items = clone_out.get("missing") if isinstance(clone_out.get("missing"), list) else []
            missing.extend(f"baseline_clone_lint: {item}" for item in items)
            if clone_out.get("returncode", 1) != 0 and not items:
                missing.append("baseline_clone_lint failed without structured missing output")
        items = clone_out.get("warnings") if isinstance(clone_out.get("warnings"), list) else []
        warnings.extend(f"baseline_clone_lint: {item}" for item in items)
        if not protocol_out.get("complete"):
            items = protocol_out.get("missing") if isinstance(protocol_out.get("missing"), list) else []
            missing.extend(f"baseline_protocol_launch_lint: {item}" for item in items)
            if protocol_out.get("returncode", 1) != 0 and not items:
                missing.append("baseline_protocol_launch_lint failed without structured missing output")
        items = protocol_out.get("warnings") if isinstance(protocol_out.get("warnings"), list) else []
        warnings.extend(f"baseline_protocol_launch_lint: {item}" for item in items)
        if not baseline_report_out.get("complete"):
            items = baseline_report_out.get("missing") if isinstance(baseline_report_out.get("missing"), list) else []
            missing.extend(f"baseline_report_alignment_lint: {item}" for item in items)
            if baseline_report_out.get("returncode", 1) != 0 and not items:
                missing.append("baseline_report_alignment_lint failed without structured missing output")
        items = baseline_report_out.get("warnings") if isinstance(baseline_report_out.get("warnings"), list) else []
        warnings.extend(f"baseline_report_alignment_lint: {item}" for item in items)
        if ledger:
            if ledger.get("ready_for_analysis") is not True:
                missing.append("coder/EXPERIMENT_LEDGER.json ready_for_analysis=true from promoted evidence")
            if not ledger.get("best_run") and not ledger.get("track_best_runs"):
                missing.append("promoted best_run or track_best_runs")
            if ledger.get("candidate_runs"):
                warnings.append("candidate_supported runs are pilot evidence; run linked ablation/confirmation before analysis")
            failure_missing, failure_warnings, failure_details = validate_experiment_failure_lineage(
                base,
                ledger,
                require_failure_diagnosis=strong_contract,
            )
            missing.extend(f"experiment_failure_lineage: {item}" for item in failure_missing)
            warnings.extend(f"experiment_failure_lineage: {item}" for item in failure_warnings)
            details["experiment_failure_lineage"] = failure_details
            summary_missing, summary_warnings, summary_details = validate_experiment_result_summaries(project, base, ledger)
            missing.extend(f"experiment_result_summaries: {item}" for item in summary_missing)
            warnings.extend(f"experiment_result_summaries: {item}" for item in summary_warnings)
            details["experiment_result_summaries"] = summary_details
        return result(stage, not missing, missing, "experiment_contract", warnings, details)

    if stage == "analysis":
        skill_root = Path(__file__).resolve().parents[2]
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        baseline_report_lint = run_baseline_report_alignment_lint(skill_root, project, stage)
        analysis_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-analyze-results/scripts/analysis_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        missing = []
        warnings = []
        if not baseline_report_lint.get("complete"):
            items = baseline_report_lint.get("missing") if isinstance(baseline_report_lint.get("missing"), list) else []
            missing.extend(f"baseline_report_alignment_lint: {item}" for item in items)
            if baseline_report_lint.get("returncode", 1) != 0 and not items:
                missing.append("baseline_report_alignment_lint failed without structured missing output")
        items = baseline_report_lint.get("warnings") if isinstance(baseline_report_lint.get("warnings"), list) else []
        warnings.extend(f"baseline_report_alignment_lint: {item}" for item in items)
        if not analysis_lint.get("complete"):
            items = analysis_lint.get("missing") if isinstance(analysis_lint.get("missing"), list) else []
            missing.extend(f"analysis_lint: {item}" for item in items)
            if analysis_lint.get("returncode", 1) != 0 and not items:
                missing.append("analysis_lint failed without structured missing output")
        items = analysis_lint.get("warnings") if isinstance(analysis_lint.get("warnings"), list) else []
        warnings.extend(f"analysis_lint: {item}" for item in items)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        outcome_missing, outcome_warnings, outcome_details = validate_idea_outcome_summary(base)
        missing.extend(f"idea_outcome_summary: {item}" for item in outcome_missing)
        warnings.extend(f"idea_outcome_summary: {item}" for item in outcome_warnings)
        score_hardening_missing, score_hardening_warnings, score_hardening_details = validate_score_verification_hardening(base)
        outcome_hardening_missing, outcome_hardening_warnings, outcome_hardening_details = validate_idea_outcome_hardening(base)
        analysis_details = {
            "innovation_story_lint": innovation_story_lint,
            "analysis_lint": analysis_lint,
            "baseline_report_alignment_lint": baseline_report_lint,
            "idea_outcome_summary": outcome_details,
            "score_verification_hardening": score_hardening_details,
            "idea_outcome_hardening": outcome_hardening_details,
        }
        if strong_contract:
            missing.extend(f"score_verification_hardening: {item}" for item in score_hardening_missing)
            missing.extend(f"idea_outcome_hardening: {item}" for item in outcome_hardening_missing)
        else:
            if score_hardening_missing:
                record_scoped_hardening(base, "score_verification_hardening", score_hardening_missing, warnings, analysis_details)
            if outcome_hardening_missing:
                record_scoped_hardening(base, "idea_outcome_hardening", outcome_hardening_missing, warnings, analysis_details)
            if scope["goal_type"] == "paper_producing_light":
                warnings.extend(f"score_verification_hardening: {item}" for item in score_hardening_missing)
                warnings.extend(f"idea_outcome_hardening: {item}" for item in outcome_hardening_missing)
        warnings.extend(f"score_verification_hardening: {item}" for item in score_hardening_warnings)
        warnings.extend(f"idea_outcome_hardening: {item}" for item in outcome_hardening_warnings)
        return result(
            stage,
            not missing,
            missing,
            "analysis_contract",
            warnings,
            analysis_details,
        )

    if stage == "review_pressure":
        skill_root = Path(__file__).resolve().parents[2]
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        baseline_report_lint = run_baseline_report_alignment_lint(skill_root, project, stage)
        review_gate_missing, review_gate_warnings, review_gate_details = validate_multi_round_review_gate(
            base,
            require_hardening_axes=strong_contract,
        )
        findings_hardening_missing, findings_hardening_warnings, findings_hardening_details = validate_review_findings_hardening(base)
        findings = read_json(base / "reviewer/REVIEW_FINDINGS.json")
        status = str((findings or {}).get("status", "")).lower()
        issues = []
        if isinstance(findings, dict):
            for key in ["issues", "findings", "review_findings", "items"]:
                if isinstance(findings.get(key), list):
                    issues = findings[key]
                    break
        blocking = [
            issue
            for issue in issues
            if isinstance(issue, dict)
            and str(issue.get("severity") or issue.get("priority") or "").lower() in {"critical", "high"}
            and str(issue.get("status") or issue.get("state") or "open").lower() not in {"closed", "resolved", "waived", "accepted_risk", "fixed"}
        ]
        ok = bool(findings and status in READY and not blocking)
        missing = []
        warnings = []
        if not findings:
            missing.append("reviewer/REVIEW_FINDINGS.json")
        if findings and status not in READY:
            missing.append("reviewer/REVIEW_FINDINGS.json status ready")
        if blocking:
            missing.append("open high/critical review findings")
        if not baseline_report_lint.get("complete"):
            items = baseline_report_lint.get("missing") if isinstance(baseline_report_lint.get("missing"), list) else []
            missing.extend(f"baseline_report_alignment_lint: {item}" for item in items)
            if baseline_report_lint.get("returncode", 1) != 0 and not items:
                missing.append("baseline_report_alignment_lint failed without structured missing output")
        items = baseline_report_lint.get("warnings") if isinstance(baseline_report_lint.get("warnings"), list) else []
        warnings.extend(f"baseline_report_alignment_lint: {item}" for item in items)
        missing.extend(f"multi_round_review_gate: {item}" for item in review_gate_missing)
        warnings.extend(f"multi_round_review_gate: {item}" for item in review_gate_warnings)
        review_details = {
            "innovation_story_lint": innovation_story_lint,
            "baseline_report_alignment_lint": baseline_report_lint,
            "multi_round_review_gate": review_gate_details,
            "review_findings_hardening": findings_hardening_details,
        }
        if strong_contract:
            missing.extend(f"review_findings_hardening: {item}" for item in findings_hardening_missing)
        elif findings_hardening_missing:
            record_scoped_hardening(base, "review_findings_hardening", findings_hardening_missing, warnings, review_details)
            if scope["goal_type"] == "paper_producing_light":
                warnings.extend(f"review_findings_hardening: {item}" for item in findings_hardening_missing)
        warnings.extend(f"review_findings_hardening: {item}" for item in findings_hardening_warnings)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        return result(
            stage,
            ok and not missing,
            missing,
            "review_pressure_contract",
            warnings,
            review_details,
        )

    if stage == "writing":
        skill_root = Path(__file__).resolve().parents[2]
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        baseline_report_lint = run_baseline_report_alignment_lint(skill_root, project, stage)
        write_package_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-paper-write/scripts/write_package_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        paper_forensics_lint = run_paper_forensics_lint(skill_root, project, stage)
        missing = []
        warnings = []
        if not baseline_report_lint.get("complete"):
            items = baseline_report_lint.get("missing") if isinstance(baseline_report_lint.get("missing"), list) else []
            missing.extend(f"baseline_report_alignment_lint: {item}" for item in items)
            if baseline_report_lint.get("returncode", 1) != 0 and not items:
                missing.append("baseline_report_alignment_lint failed without structured missing output")
        items = baseline_report_lint.get("warnings") if isinstance(baseline_report_lint.get("warnings"), list) else []
        warnings.extend(f"baseline_report_alignment_lint: {item}" for item in items)
        if not write_package_lint.get("complete"):
            items = write_package_lint.get("missing") if isinstance(write_package_lint.get("missing"), list) else []
            missing.extend(f"write_package_lint: {item}" for item in items)
            if write_package_lint.get("returncode", 1) != 0 and not items:
                missing.append("write_package_lint failed without structured missing output")
        items = write_package_lint.get("warnings") if isinstance(write_package_lint.get("warnings"), list) else []
        warnings.extend(f"write_package_lint: {item}" for item in items)
        paper_forensics_missing = []
        if not paper_forensics_lint.get("complete"):
            items = paper_forensics_lint.get("missing") if isinstance(paper_forensics_lint.get("missing"), list) else []
            paper_forensics_missing.extend(str(item) for item in items)
            if paper_forensics_lint.get("returncode", 1) != 0 and not items:
                paper_forensics_missing.append("paper_forensics_lint failed without structured missing output")
        items = paper_forensics_lint.get("warnings") if isinstance(paper_forensics_lint.get("warnings"), list) else []
        warnings.extend(f"paper_forensics_lint: {item}" for item in items)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        effective_missing, effective_warnings, effective_details = validate_effective_innovation_points(base)
        missing.extend(f"effective_innovation_points: {item}" for item in effective_missing)
        warnings.extend(f"effective_innovation_points: {item}" for item in effective_warnings)
        writing_hardening_missing, writing_hardening_warnings, writing_hardening_details = validate_writing_hardening(base)
        writing_details = {
            "innovation_story_lint": innovation_story_lint,
            "write_package_lint": write_package_lint,
            "baseline_report_alignment_lint": baseline_report_lint,
            "paper_forensics_lint": paper_forensics_lint,
            "effective_innovation_points": effective_details,
            "writing_hardening": writing_hardening_details,
        }
        if strong_contract:
            missing.extend(f"writing_hardening: {item}" for item in writing_hardening_missing)
            missing.extend(f"paper_forensics_lint: {item}" for item in paper_forensics_missing)
        else:
            if writing_hardening_missing:
                record_scoped_hardening(base, "writing_hardening", writing_hardening_missing, warnings, writing_details)
                if scope["goal_type"] == "paper_producing_light":
                    warnings.extend(f"writing_hardening: {item}" for item in writing_hardening_missing)
            record_scoped_gate(base, "paper_forensics_lint", paper_forensics_missing, warnings, writing_details)
            if paper_forensics_missing and scope["goal_type"] == "paper_producing_light":
                warnings.extend(f"paper_forensics_lint: {item}" for item in paper_forensics_missing)
        warnings.extend(f"writing_hardening: {item}" for item in writing_hardening_warnings)
        return result(
            stage,
            not missing,
            missing,
            "writing_contract",
            warnings,
            writing_details,
        )

    if stage == "submission_ready":
        skill_root = Path(__file__).resolve().parents[2]
        package = read_json(base / "submission_ready.json")
        status = str((package or {}).get("status", "")).lower()
        baseline_report_lint = run_baseline_report_alignment_lint(skill_root, project, stage)
        citation_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-review-gate/scripts/citation_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        write_package_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-paper-write/scripts/write_package_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        submission_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-review-gate/scripts/submission_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        paper_forensics_lint = run_paper_forensics_lint(skill_root, project, stage)
        ok = nonempty(base / "paper/main.tex") and (base / "paper/main.pdf").exists() and status in READY and citation_lint.get("complete") is True
        missing = []
        if not nonempty(base / "paper/main.tex"):
            missing.append("paper/main.tex")
        if not (base / "paper/main.pdf").exists():
            missing.append("paper/main.pdf")
        if status not in READY:
            missing.append("submission_ready.json status ready")
        if not baseline_report_lint.get("complete"):
            items = baseline_report_lint.get("missing") if isinstance(baseline_report_lint.get("missing"), list) else []
            missing.extend(f"baseline_report_alignment_lint: {item}" for item in items)
            if baseline_report_lint.get("returncode", 1) != 0 and not items:
                missing.append("baseline_report_alignment_lint failed without structured missing output")
        if not citation_lint.get("complete"):
            items = citation_lint.get("missing") if isinstance(citation_lint.get("missing"), list) else []
            missing.extend(f"citation_lint: {item}" for item in items)
            if citation_lint.get("returncode", 1) != 0 and not items:
                missing.append("citation_lint failed without structured missing output")
        if not write_package_lint.get("complete"):
            items = write_package_lint.get("missing") if isinstance(write_package_lint.get("missing"), list) else []
            missing.extend(f"write_package_lint: {item}" for item in items)
            if write_package_lint.get("returncode", 1) != 0 and not items:
                missing.append("write_package_lint failed without structured missing output")
        if not submission_lint.get("complete"):
            items = submission_lint.get("missing") if isinstance(submission_lint.get("missing"), list) else []
            missing.extend(f"submission_lint: {item}" for item in items)
            if submission_lint.get("returncode", 1) != 0 and not items:
                missing.append("submission_lint failed without structured missing output")
        paper_forensics_missing = []
        if not paper_forensics_lint.get("complete"):
            items = paper_forensics_lint.get("missing") if isinstance(paper_forensics_lint.get("missing"), list) else []
            paper_forensics_missing.extend(str(item) for item in items)
            if paper_forensics_lint.get("returncode", 1) != 0 and not items:
                paper_forensics_missing.append("paper_forensics_lint failed without structured missing output")
        effective_missing, effective_warnings, effective_details = validate_effective_innovation_points(base)
        missing.extend(f"effective_innovation_points: {item}" for item in effective_missing)
        warnings = []
        items = baseline_report_lint.get("warnings") if isinstance(baseline_report_lint.get("warnings"), list) else []
        warnings.extend(f"baseline_report_alignment_lint: {item}" for item in items)
        warnings.extend(f"effective_innovation_points: {item}" for item in effective_warnings)
        items = submission_lint.get("warnings") if isinstance(submission_lint.get("warnings"), list) else []
        warnings.extend(f"submission_lint: {item}" for item in items)
        items = paper_forensics_lint.get("warnings") if isinstance(paper_forensics_lint.get("warnings"), list) else []
        warnings.extend(f"paper_forensics_lint: {item}" for item in items)
        review_gate_missing, review_gate_warnings, review_gate_details = validate_multi_round_review_gate(
            base,
            require_hardening_axes=strong_contract,
        )
        missing.extend(f"multi_round_review_gate: {item}" for item in review_gate_missing)
        warnings.extend(f"multi_round_review_gate: {item}" for item in review_gate_warnings)
        writing_hardening_missing, writing_hardening_warnings, writing_hardening_details = validate_writing_hardening(base)
        submission_details = {
            "citation_lint": citation_lint,
            "submission_lint": submission_lint,
            "write_package_lint": write_package_lint,
            "baseline_report_alignment_lint": baseline_report_lint,
            "paper_forensics_lint": paper_forensics_lint,
            "effective_innovation_points": effective_details,
            "multi_round_review_gate": review_gate_details,
            "writing_hardening": writing_hardening_details,
        }
        if strong_contract:
            missing.extend(f"writing_hardening: {item}" for item in writing_hardening_missing)
            missing.extend(f"paper_forensics_lint: {item}" for item in paper_forensics_missing)
        else:
            if writing_hardening_missing:
                record_scoped_hardening(base, "writing_hardening", writing_hardening_missing, warnings, submission_details)
                if scope["goal_type"] == "paper_producing_light":
                    warnings.extend(f"writing_hardening: {item}" for item in writing_hardening_missing)
            record_scoped_gate(base, "paper_forensics_lint", paper_forensics_missing, warnings, submission_details)
            if paper_forensics_missing and scope["goal_type"] == "paper_producing_light":
                warnings.extend(f"paper_forensics_lint: {item}" for item in paper_forensics_missing)
        warnings.extend(f"writing_hardening: {item}" for item in writing_hardening_warnings)
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        return result(
            stage,
            ok and not missing,
            missing,
            "submission_ready_contract",
            warnings,
            {
                **submission_details,
                "innovation_story_lint": innovation_story_lint,
            },
        )

    return result(stage, False, [f"unknown stage {stage}"], "unknown_contract")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.stage)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
