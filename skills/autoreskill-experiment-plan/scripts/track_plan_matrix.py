#!/usr/bin/env python3
"""Materialize and lint TRACK_PLAN_MATRIX from IDEA_TRACK_SEEDS."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prelaunch_lint import lint as lint_prelaunch_packet


REQUIRED_ROW_FIELDS = [
    "track_id",
    "idea_id",
    "track_role",
    "baseline_code",
    "dataset",
    "dataset_runtime_plan_ref",
    "split",
    "primary_metric",
    "metric_direction",
    "eval_command",
    "compute_budget",
    "evidence_closure_status",
    "launch_status",
    "promotion_gate",
    "one_variable_change",
    "expected_metric_effect",
    "ablation_required",
    "confirmation_required",
    "hypothesis_contract",
]
HYPOTHESIS_REQUIRED_FIELDS = [
    "track_id",
    "causal_signature",
    "causal_question",
    "intervention",
    "one_variable_delta",
    "mechanism",
    "predicted_pattern",
    "falsifier",
    "alternative_explanation",
    "minimum_discriminating_experiment",
    "dataset_transfer_assumption",
    "outcome_routes",
    "max_scientific_revisions",
    "scientific_revision_index",
    "belief_state",
]

READY_EVIDENCE = {"passed", "complete", "completed", "graph_closed", "source_backed", "not_required"}
LAUNCH_STATUSES = {"ready", "blocked", "diagnostic_only", "parked"}
READY_PACKET_STATUSES = {"reviewed", "ready", "approved", "pass", "passed"}
TERMINAL_TRACK_STATES = {"refuted", "retired", "killed", "terminal", "parked"}
ADMITTED_LIFECYCLES = {
    "selected_primary",
    "alternate_track",
    "risk_repair_track",
    "advance_with_constraints",
    "alternate",  # schema-v2 compatibility
}
TRACK_ROLES = {"primary", "alternate", "risk_repair"}
DEFAULT_BIE_CONFIG = {
    "branch_budget_B": 4,
    "search_iterations_I": 2,
    "versions_per_branch_E": 2,
    "retain_top_K": 1,
    "stop_on_spec_violation": True,
    "promotion_required": True,
    "param_search_method": "dehb_resource_constrained",
    "param_search_budget_note": "Use low-fidelity DEHB scouts and promote at most 1-2 full-resource survivors before ablation/confirmation.",
    "seed_is_search_axis": False,
    "max_random_seeds_for_stability": 3,
    "promotion_requirements": [
        "candidate support on the locked baseline protocol",
        "linked ablation or confirmation before promoted best_run",
        "no metric, dataset, evaluator, or budget drift",
        "failed tracks remain negative evidence and cannot satisfy best_run",
    ],
}
EXTERNAL_CAMPAIGN_REF = "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
EXTERNAL_IDENTITY_FIELDS = [
    "external_campaign_ref",
    "external_campaign_sha256",
    "external_candidate_id",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seed_semantic_sha256(payload: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at", "semantic_sha256"}
    }
    return canonical_sha256(stable)


def packet_semantic_sha256(payload: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"created_at", "generated_at", "semantic_sha256"}
    }
    return canonical_sha256(stable)


def semantic_matrix_sha256(payload: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at", "semantic_sha256"}
    }
    return canonical_sha256(stable)


def evidence_source_mode(base: Path) -> str:
    gate = read_json(base / "ideation/PRE_IDEA_EVIDENCE_GATE.json", {})
    if not isinstance(gate, dict):
        return "papernexus"
    return str(gate.get("evidence_source_mode") or "papernexus").strip().lower()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["tracks", "rows", "track_plans"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def decision_rows_by_idea(payload: Any) -> dict[str, dict[str, Any]]:
    return {str(row.get("idea_id")): row for row in rows_from_payload(payload) if present(row.get("idea_id"))}


def track_states_by_track(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("track_states"), list):
        return {}
    return {
        str(row.get("track_id")): row
        for row in payload["track_states"]
        if isinstance(row, dict) and present(row.get("track_id"))
    }


def selection_ref(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for field in ["selection_fingerprint", "selected_primary_ref"]:
        if present(payload.get(field)):
            return str(payload[field]).strip()
    for row in rows_from_payload(payload):
        if normalized(row.get("lifecycle_status")) == "selected_primary":
            for field in ["selection_fingerprint", "selected_primary_ref"]:
                if present(row.get(field)):
                    return str(row[field]).strip()
    return ""


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def review_prelaunch_status(base: Path, review: dict[str, Any], review_ref: str) -> dict[str, Any]:
    if not review:
        return {
            "complete": False,
            "status": "incomplete",
            "missing": ["per-track EXPERIMENT_REVIEW_PACKET.json"],
            "warnings": [],
        }
    return lint_prelaunch_packet(
        review,
        str(base.parent),
        base / review_ref,
        check_matrix=False,
    )


def hypothesis_contract(seed: dict[str, Any], decision: dict[str, Any], track_state: dict[str, Any]) -> dict[str, Any]:
    contract = dict(seed.get("hypothesis_contract")) if isinstance(seed.get("hypothesis_contract"), dict) else {}
    contract["track_id"] = seed.get("track_id")
    belief = track_state.get("belief_state") if present(track_state.get("belief_state")) else decision.get("belief_state")
    revision = (
        track_state.get("scientific_revision_index")
        if isinstance(track_state.get("scientific_revision_index"), int)
        else decision.get("scientific_revision_index")
    )
    if present(belief):
        contract["belief_state"] = belief
    if isinstance(revision, int):
        contract["scientific_revision_index"] = revision
    return contract


def hypothesis_ready(contract: dict[str, Any]) -> bool:
    for field in HYPOTHESIS_REQUIRED_FIELDS:
        if field == "scientific_revision_index":
            if not isinstance(contract.get(field), int) or isinstance(contract.get(field), bool):
                return False
        elif not present(contract.get(field)):
            return False
    routes = contract.get("outcome_routes") if isinstance(contract.get("outcome_routes"), dict) else {}
    if not all(present(routes.get(key)) for key in ["positive", "negative", "inconclusive", "invalid"]):
        return False
    max_revisions = contract.get("max_scientific_revisions")
    revision = contract.get("scientific_revision_index")
    return isinstance(max_revisions, int) and isinstance(revision, int) and revision <= max_revisions


def evidence_status(seed: dict[str, Any], review: dict[str, Any], selected: bool) -> str:
    if selected:
        gate = review.get("evidence_import_gate") if isinstance(review.get("evidence_import_gate"), dict) else {}
        status = str(gate.get("status") or "").strip()
        if status:
            return status
    if present(seed.get("evidence_debt")):
        return "blocked"
    return "source_backed"


def default_promotion_gate(seed: dict[str, Any], review: dict[str, Any], selected: bool) -> dict[str, Any]:
    if isinstance(review.get("promotion_gate"), dict):
        return review["promotion_gate"]
    return {
        "stage": "candidate",
        "promotion_requires": ["linked_ablation", "confirmation_or_second_seed"],
        "claim_policy": (
            "seed rows are not launch approval; promoted evidence is required for manuscript claims"
            if selected
            else "pilot_only evidence cannot promote or close a manuscript claim; explicit primary reselection and a frozen matched-baseline rerun are required"
        ),
        "stability_seed_policy": {
            "max_random_seeds": 3,
            "claim_rule": "Random-seed stability validation is capped at three seeds; IDEA_TRACK_SEEDS are track candidates, not random seeds.",
        },
        "ablation_required": seed.get("ablation_required") is True,
        "confirmation_required": seed.get("confirmation_required") is True,
    }


def decision_ref(seed: dict[str, Any], decision: dict[str, Any]) -> str:
    explicit = decision.get("decision_id") or decision.get("id") or decision.get("ref")
    if present(explicit):
        return str(explicit)
    idea_id = str(seed.get("idea_id") or "unknown").strip().lower()
    status = str(decision.get("lifecycle_status") or seed.get("track_role") or "seed").strip().lower()
    return f"idea-decision-{idea_id}-{status}".replace("_", "-")


def branch_id(seed: dict[str, Any], selected: bool, decision: dict[str, Any]) -> str:
    explicit = decision.get("branch_id") or seed.get("branch_id")
    if present(explicit):
        return str(explicit)
    track_id = str(seed.get("track_id") or "track-unknown").strip()
    role = "primary" if selected else str(seed.get("track_role") or "alternate").strip().lower()
    return f"branch-{track_id}-{role}".replace("_", "-")


def inferred_lifecycle(seed: dict[str, Any]) -> str:
    return {
        "primary": "selected_primary",
        "alternate": "alternate_track",
        "risk_repair": "risk_repair_track",
    }.get(normalized(seed.get("track_role")), "")


def track_packet(
    base: Path,
    seed: dict[str, Any],
    kind: str,
) -> tuple[dict[str, Any], str]:
    track_id = str(seed.get("track_id") or "").strip()
    role = normalized(seed.get("track_role"))
    if kind == "review":
        per_track = f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json"
        legacy = "planner/EXPERIMENT_REVIEW_PACKET.json"
    else:
        per_track = f"orchestrator/tracks/{track_id}/INNOVATION_PACKET.json"
        legacy = "orchestrator/INNOVATION_PACKET.json"
    packet = read_json(base / per_track, {}) or {}
    if isinstance(packet, dict) and packet:
        return packet, per_track
    if role == "primary":
        packet = read_json(base / legacy, {}) or {}
        if isinstance(packet, dict) and packet:
            return packet, legacy
    return {}, per_track


def packet_identity_matches(
    packet: dict[str, Any],
    seed: dict[str, Any],
    current_selection_ref: str,
    source_seed_sha256: str,
    *,
    legacy_primary: bool,
) -> bool:
    if not packet:
        return False
    idea_id = str(seed.get("idea_id") or "")
    track_id = str(seed.get("track_id") or "")
    if str(packet.get("selected_idea_id") or "") != idea_id:
        return False
    packet_track = str(packet.get("track_id") or "")
    if packet_track and packet_track != track_id:
        return False
    packet_selection = selection_ref(packet)
    if packet_selection and current_selection_ref and packet_selection != current_selection_ref:
        return False
    track_seed_sha = str(seed.get("track_seed_sha256") or "").strip().lower()
    packet_item_sha = str(packet.get("source_track_seed_item_sha256") or "").strip().lower()
    if track_seed_sha and packet_item_sha:
        return packet_item_sha == track_seed_sha
    packet_seed_sha = str(packet.get("source_track_seed_sha256") or "").strip().lower()
    if not legacy_primary and packet_seed_sha != source_seed_sha256:
        return False
    return not packet_seed_sha or packet_seed_sha == source_seed_sha256


def row_from_seed(
    base: Path,
    seed: dict[str, Any],
    review: dict[str, Any],
    review_ref: str,
    innovation: dict[str, Any],
    innovation_ref: str,
    decision: dict[str, Any],
    track_state: dict[str, Any],
    current_selection_ref: str,
    source_seed_sha256: str,
    selected_primary: bool,
) -> dict[str, Any]:
    contract = hypothesis_contract(seed, decision, track_state)
    role = normalized(seed.get("track_role"))
    lifecycle = normalized(
        decision.get("lifecycle_status")
        or track_state.get("lifecycle_status")
        or inferred_lifecycle(seed)
    )
    terminal = (
        normalized(contract.get("belief_state")) in TERMINAL_TRACK_STATES
        or normalized(track_state.get("lifecycle_status")) in TERMINAL_TRACK_STATES
        or lifecycle in TERMINAL_TRACK_STATES
    )
    legacy_primary = selected_primary and review_ref == "planner/EXPERIMENT_REVIEW_PACKET.json"
    packet_identity_ok = packet_identity_matches(
        review,
        seed,
        current_selection_ref,
        source_seed_sha256,
        legacy_primary=legacy_primary,
    ) and packet_identity_matches(
        innovation,
        seed,
        current_selection_ref,
        source_seed_sha256,
        legacy_primary=selected_primary and innovation_ref == "orchestrator/INNOVATION_PACKET.json",
    )
    planning_admitted = lifecycle in ADMITTED_LIFECYCLES and role in TRACK_ROLES and packet_identity_ok and not terminal
    ceiling = str(
        review.get("evidence_tier_ceiling")
        or innovation.get("evidence_tier_ceiling")
        or ("claim_eligible_after_gates" if role == "primary" else "pilot_only")
    ).strip()
    promotion_gate = default_promotion_gate(seed, review, selected_primary)
    claim_policy = normalized(promotion_gate.get("claim_policy")) if isinstance(promotion_gate, dict) else ""
    ceiling_ok = role == "primary" or (ceiling == "pilot_only" and "pilot_only" in claim_policy)
    gate = review.get("evidence_import_gate") if isinstance(review.get("evidence_import_gate"), dict) else {}
    closure = str(gate.get("status") or "source_backed" if packet_identity_ok else "blocked").strip()
    prelaunch = review_prelaunch_status(base, review, review_ref)
    review_is_ready = prelaunch.get("complete") is True
    ready = (
        planning_admitted
        and review_is_ready
        and hypothesis_ready(contract)
        and normalized(closure) in READY_EVIDENCE
        and ceiling_ok
    )
    status = "ready" if ready else "parked" if lifecycle in TERMINAL_TRACK_STATES else "blocked"
    baseline_code = review.get("baseline_code") if present(review.get("baseline_code")) else {"status": "unresolved", "reason": "baseline lock required before launch"}
    compute_budget = review.get("compute_budget") if present(review.get("compute_budget")) else {"status": "bounded_seed", "gpu_hours": 0, "walltime_hours": 0}
    hpo_policy = review.get("hpo_search_policy") or innovation.get("hpo_search_policy")
    reasons: list[str] = []
    if terminal:
        reasons.append("track lifecycle or belief state is terminal")
    if lifecycle not in ADMITTED_LIFECYCLES:
        reasons.append(f"track lifecycle {lifecycle or '<missing>'} is not admitted")
    if not review or not innovation:
        reasons.append("per-track innovation/review packet is missing")
    elif not packet_identity_ok:
        reasons.append("per-track packet identity, selection revision, or seed hash is stale")
    if packet_identity_ok and not review_is_ready:
        reasons.append("per-track prelaunch lint is incomplete")
    if not hypothesis_ready(contract):
        reasons.append("hypothesis contract is incomplete or revision budget is exhausted")
    if not ceiling_ok:
        reasons.append("non-primary track does not enforce the pilot_only claim ceiling")
    row = {
        "track_id": seed.get("track_id"),
        "branch_id": branch_id(seed, selected_primary, decision),
        "idea_id": seed.get("idea_id"),
        "idea_decision_ref": decision_ref(seed, decision),
        "selection_fingerprint": current_selection_ref,
        "source_track_seed_sha256": source_seed_sha256,
        "source_track_seed_item_sha256": seed.get("track_seed_sha256"),
        "idea_lifecycle_status": lifecycle,
        "idea_failure_class": decision.get("failure_class"),
        "last_scientific_decision_id": track_state.get("last_decision_id") or decision.get("last_scientific_decision_id"),
        "hypothesis_contract": contract,
        "track_role": seed.get("track_role"),
        "claim_role": review.get("claim_role") or innovation.get("claim_role") or seed.get("claim_role"),
        "selected_for_review": selected_primary,
        "planning_admitted": planning_admitted,
        "source_seed_path": "ideation/IDEA_TRACK_SEEDS.json",
        "idea_pool_path": review.get("idea_pool_path") or innovation.get("idea_pool_path") or "ideation/EXPERIMENT_IDEA_POOL.json",
        "innovation_packet_ref": innovation_ref,
        "innovation_packet_sha256": packet_semantic_sha256(innovation) if innovation else "",
        "review_packet_ref": review_ref,
        "review_packet_sha256": packet_semantic_sha256(review) if review else "",
        "project_execution_passport_ref": review.get("project_execution_passport_ref"),
        "project_execution_passport_index_sha256": review.get(
            "project_execution_passport_index_sha256"
        ),
        "execution_profile_id": review.get("execution_profile_id"),
        "execution_profile_sha256": review.get("execution_profile_sha256"),
        "innovation_delta_sha256": review.get("innovation_delta_sha256")
        or innovation.get("innovation_delta_sha256"),
        "program_claim_contract_ref": review.get("program_claim_contract_ref"),
        "program_claim_contract_sha256": review.get("program_claim_contract_sha256"),
        "program_claim_contract_revision": review.get("program_claim_contract_revision"),
        "dataset_group_plan": review.get("dataset_group_plan"),
        "parameter_transfer_contract_sha256": (
            review.get("parameter_transfer_contract") or {}
        ).get("parameter_transfer_contract_sha256") if isinstance(review.get("parameter_transfer_contract"), dict) else None,
        "method_formula_sha256": review.get("method_formula_sha256") or innovation.get("method_formula_sha256"),
        "parameter_profile_status": review.get("parameter_profile_status"),
        "stage2_role": review.get("stage2_role"),
        "frozen_parameter_profile_ref": review.get("frozen_parameter_profile_ref"),
        "frozen_parameter_profile_sha256": review.get("frozen_parameter_profile_sha256"),
        "prelaunch_lint_status": prelaunch.get("status") or "incomplete",
        "prelaunch_lint_missing": prelaunch.get("missing") or [],
        "evidence_tier_ceiling": ceiling,
        "baseline_code": baseline_code,
        "dataset": review.get("dataset") if present(review.get("dataset")) else "unresolved_dataset_for_track",
        "dataset_runtime_plan_ref": f"{review_ref}:dataset_runtime_plan" if present(review.get("dataset_runtime_plan")) else "unresolved_dataset_runtime_plan_for_track",
        "split": review.get("data_split") if present(review.get("data_split")) else "unresolved_split_for_track",
        "primary_metric": review.get("primary_metric") if present(review.get("primary_metric")) else "unresolved_primary_metric",
        "metric_direction": review.get("metric_direction") or "higher",
        "eval_command": review.get("evaluation_command") if present(review.get("evaluation_command")) else "unresolved_eval_command",
        "compute_budget": compute_budget,
        "evidence_closure_status": closure,
        "launch_status": status,
        "blocked_reason": "" if ready else "; ".join(reasons) or "track is not planning-ready",
        "promotion_gate": promotion_gate,
        "hpo_search_policy_ref": f"{review_ref}:hpo_search_policy" if present(hpo_policy) else "not_applicable_until_track_planned",
        "hpo_search_method": hpo_policy.get("search_method") if isinstance(hpo_policy, dict) else "not_applicable",
        "one_variable_change": seed.get("one_variable_change"),
        "expected_metric_effect": seed.get("expected_metric_effect"),
        "minimum_pilot": seed.get("minimum_pilot"),
        "kill_condition": seed.get("kill_condition"),
        "red_line_risks": seed.get("red_line_risks") or [],
        "evidence_debt": seed.get("evidence_debt") or [],
        "ablation_required": seed.get("ablation_required") is True,
        "confirmation_required": seed.get("confirmation_required") is True,
    }
    # Preserve the source campaign identity byte-for-byte.  Do not synthesize an
    # external candidate id from track_id or idea_id; those are separate domains.
    if any(present(seed.get(field)) for field in EXTERNAL_IDENTITY_FIELDS):
        for field in EXTERNAL_IDENTITY_FIELDS:
            row[field] = seed.get(field)
    return row


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    program_contract = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json", {}) or {}
    decisions = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    rows = rows_from_payload(seeds)
    decisions_by_idea = decision_rows_by_idea(decisions)
    states_by_track = track_states_by_track(decisions)
    current_selection_ref = selection_ref(decisions) or selection_ref(seeds)
    selected_idea_id = decisions.get("selected_primary_idea_id") or seeds.get("selected_primary_idea_id")
    selected_track_id = decisions.get("selected_track_id")
    if not present(selected_track_id):
        for seed in rows:
            if normalized(seed.get("track_role")) == "primary" or (
                present(selected_idea_id) and str(seed.get("idea_id") or "") == str(selected_idea_id)
            ):
                selected_track_id = seed.get("track_id")
                break
    source_seed_sha256 = seed_semantic_sha256(seeds) if isinstance(seeds, dict) else ""
    recorded_seed_sha256 = str(seeds.get("semantic_sha256") or "").strip().lower() if isinstance(seeds, dict) else ""
    if recorded_seed_sha256 and recorded_seed_sha256 != source_seed_sha256:
        raise SystemExit("IDEA_TRACK_SEEDS semantic_sha256 does not match current canonical content")
    matrix_rows: list[dict[str, Any]] = []
    for seed in rows:
        review, review_ref = track_packet(base, seed, "review")
        innovation, innovation_ref = track_packet(base, seed, "innovation")
        selected_primary = (
            str(seed.get("idea_id") or "") == str(selected_idea_id or "")
            and (
                not present(selected_track_id)
                or str(seed.get("track_id") or "") == str(selected_track_id)
            )
        )
        matrix_rows.append(
            row_from_seed(
                base,
                seed,
                review,
                review_ref,
                innovation,
                innovation_ref,
                decisions_by_idea.get(str(seed.get("idea_id")), {}),
                states_by_track.get(str(seed.get("track_id")), {}),
                current_selection_ref,
                source_seed_sha256,
                selected_primary,
            )
        )
    matrix = {
        "schema_version": 3,
        "generated_at": now(),
        "artifact": "TRACK_PLAN_MATRIX",
        "source_track_seed_path": "ideation/IDEA_TRACK_SEEDS.json",
        "source_track_seed_sha256": source_seed_sha256,
        "primary_review_packet_path": "planner/EXPERIMENT_REVIEW_PACKET.json",
        "source_idea_decision_ledger_path": "ideation/IDEA_DECISION_LEDGER.json",
        "selected_idea_id": selected_idea_id,
        "selected_track_id": selected_track_id,
        "selection_fingerprint": current_selection_ref,
        "program_claim_contract_ref": "orchestrator/PROGRAM_CLAIM_CONTRACT.json" if program_contract else None,
        "program_claim_contract_sha256": program_contract.get("semantic_sha256") if isinstance(program_contract, dict) else None,
        "program_claim_contract_revision": program_contract.get("contract_revision") if isinstance(program_contract, dict) else None,
        "bie_config": DEFAULT_BIE_CONFIG,
        "policy": "bounded_explore_exploit_matrix_seed_rows_are_not_launch_approval",
        "tracks": matrix_rows,
    }
    matrix["semantic_sha256"] = semantic_matrix_sha256(matrix)
    return matrix


def lint(project: str) -> dict[str, Any]:
    base = ar(project)
    program_contract = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    program_mode = str(program_contract.get("enforcement_mode") or "legacy").strip().lower() if isinstance(program_contract, dict) else "legacy"
    seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json", {}) or {}
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
    missing: list[str] = []
    warnings: list[str] = []
    seed_rows = rows_from_payload(seeds)
    rows = rows_from_payload(matrix)
    if not isinstance(seeds, dict) or not seed_rows:
        missing.append("ideation/IDEA_TRACK_SEEDS.json tracks")
    if not isinstance(matrix, dict) or not rows:
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json tracks")
        rows = []
    schema_version = matrix.get("schema_version") if isinstance(matrix, dict) else None
    if schema_version not in {2, 3}:
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json schema_version must be 2 or 3")
    if schema_version == 2:
        warnings.append("schema_version=2 is readable primary-only legacy state; explicit per-track materialization is required before alternate activation")
    current_seed_sha256 = seed_semantic_sha256(seeds) if isinstance(seeds, dict) else ""
    if schema_version == 3:
        if str(matrix.get("source_track_seed_sha256") or "") != current_seed_sha256:
            missing.append("orchestrator/TRACK_PLAN_MATRIX.json source_track_seed_sha256 must match IDEA_TRACK_SEEDS")
        recorded_matrix_sha = str(matrix.get("semantic_sha256") or "").strip().lower()
        if recorded_matrix_sha and recorded_matrix_sha != semantic_matrix_sha256(matrix):
            missing.append("orchestrator/TRACK_PLAN_MATRIX.json semantic_sha256 must match canonical matrix content")
        if program_contract and program_mode == "enforced":
            if matrix.get("program_claim_contract_ref") != "orchestrator/PROGRAM_CLAIM_CONTRACT.json":
                missing.append("TRACK_PLAN_MATRIX program_claim_contract_ref must bind the live contract")
            if matrix.get("program_claim_contract_sha256") != program_contract.get("semantic_sha256"):
                missing.append("TRACK_PLAN_MATRIX program_claim_contract_sha256 must match the live contract")
    matrix_selection_ref = selection_ref(matrix)
    if not matrix_selection_ref:
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json selection_fingerprint or selected_primary_ref")
    rows_by_track = {str(row.get("track_id")): row for row in rows if present(row.get("track_id"))}
    seeds_by_track = {str(seed.get("track_id")): seed for seed in seed_rows if present(seed.get("track_id"))}
    causal_signatures: dict[str, str] = {}
    for seed in seed_rows:
        track_id = str(seed.get("track_id") or "")
        if track_id and track_id not in rows_by_track:
            missing.append(f"TRACK_PLAN_MATRIX missing seed track {track_id}")
    for index, row in enumerate(rows):
        prefix = f"tracks[{index}]"
        launch_status = normalized(row.get("launch_status"))
        for field in REQUIRED_ROW_FIELDS:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if schema_version == 3:
            for field in [
                "planning_admitted",
                "innovation_packet_ref",
                "review_packet_ref",
                "evidence_tier_ceiling",
                "source_track_seed_sha256",
                "source_track_seed_item_sha256",
            ]:
                if field == "planning_admitted":
                    if not isinstance(row.get(field), bool):
                        missing.append(f"{prefix}.{field} boolean")
                elif not present(row.get(field)):
                    missing.append(f"{prefix}.{field}")
            if row.get("planning_admitted") is True or launch_status == "ready":
                for field in ["innovation_packet_sha256", "review_packet_sha256"]:
                    if not present(row.get(field)):
                        missing.append(f"{prefix}.{field}")
            if str(row.get("source_track_seed_sha256") or "") != current_seed_sha256:
                missing.append(f"{prefix}.source_track_seed_sha256 must match IDEA_TRACK_SEEDS")
            seed = seeds_by_track.get(str(row.get("track_id") or ""), {})
            if str(row.get("source_track_seed_item_sha256") or "") != str(seed.get("track_seed_sha256") or ""):
                missing.append(f"{prefix}.source_track_seed_item_sha256 must match the source track row")
            if str(seed.get("idea_id") or "") != str(row.get("idea_id") or ""):
                missing.append(f"{prefix}.idea_id must match source IDEA_TRACK_SEEDS row")
            if str(seed.get("track_role") or "") != str(row.get("track_role") or ""):
                missing.append(f"{prefix}.track_role must match source IDEA_TRACK_SEEDS row")
            for ref_field, hash_field in [
                ("innovation_packet_ref", "innovation_packet_sha256"),
                ("review_packet_ref", "review_packet_sha256"),
            ]:
                ref = str(row.get(ref_field) or "").strip()
                packet_path = base / ref
                packet = read_json(packet_path, {}) if ref else {}
                if not ref or not packet_path.exists() or not isinstance(packet, dict) or not packet:
                    if row.get("planning_admitted") is True or launch_status == "ready":
                        missing.append(f"{prefix}.{ref_field} must resolve to a current packet")
                elif str(row.get(hash_field) or "") != packet_semantic_sha256(packet):
                    missing.append(f"{prefix}.{hash_field} must match current packet semantic hash")
            if present(row.get("project_execution_passport_ref")):
                review_ref = str(row.get("review_packet_ref") or "")
                review_packet = read_json(base / review_ref, {}) if review_ref else {}
                for field in [
                    "project_execution_passport_index_sha256",
                    "execution_profile_id",
                    "execution_profile_sha256",
                    "innovation_delta_sha256",
                ]:
                    if not present(row.get(field)):
                        missing.append(f"{prefix}.{field}")
                    elif isinstance(review_packet, dict) and str(row.get(field) or "") != str(review_packet.get(field) or ""):
                        missing.append(f"{prefix}.{field} must match the current review packet")
            if program_contract and program_mode == "enforced":
                review_ref = str(row.get("review_packet_ref") or "")
                review_packet = read_json(base / review_ref, {}) if review_ref else {}
                for field in [
                    "program_claim_contract_ref",
                    "program_claim_contract_sha256",
                    "program_claim_contract_revision",
                    "claim_role",
                    "dataset_group_plan",
                    "method_formula_sha256",
                    "parameter_profile_status",
                    "stage2_role",
                ]:
                    if row.get(field) != review_packet.get(field):
                        missing.append(f"{prefix}.{field} must match the current review packet")
            role = normalized(row.get("track_role"))
            lifecycle = normalized(row.get("idea_lifecycle_status"))
            if role not in TRACK_ROLES:
                missing.append(f"{prefix}.track_role must be primary/alternate/risk_repair")
            if row.get("planning_admitted") is True and lifecycle not in ADMITTED_LIFECYCLES:
                missing.append(f"{prefix}.idea_lifecycle_status is not admitted")
            if role != "primary":
                if row.get("evidence_tier_ceiling") != "pilot_only":
                    missing.append(f"{prefix}.evidence_tier_ceiling must be pilot_only for non-primary tracks")
                gate = row.get("promotion_gate") if isinstance(row.get("promotion_gate"), dict) else {}
                if "pilot_only" not in normalized(gate.get("claim_policy")):
                    missing.append(f"{prefix}.promotion_gate.claim_policy must prohibit pilot_only claim promotion")
        if launch_status and launch_status not in LAUNCH_STATUSES:
            missing.append(f"{prefix}.launch_status must be ready/blocked/diagnostic_only/parked")
        if row.get("ablation_required") is not True:
            missing.append(f"{prefix}.ablation_required=true")
        if row.get("confirmation_required") is not True:
            missing.append(f"{prefix}.confirmation_required=true")
        contract = row.get("hypothesis_contract") if isinstance(row.get("hypothesis_contract"), dict) else {}
        for field in HYPOTHESIS_REQUIRED_FIELDS:
            if field == "scientific_revision_index":
                if not isinstance(contract.get(field), int) or isinstance(contract.get(field), bool):
                    missing.append(f"{prefix}.hypothesis_contract.{field} integer")
            elif not present(contract.get(field)):
                missing.append(f"{prefix}.hypothesis_contract.{field}")
        routes = contract.get("outcome_routes") if isinstance(contract.get("outcome_routes"), dict) else {}
        for route in ["positive", "negative", "inconclusive", "invalid"]:
            if not present(routes.get(route)):
                missing.append(f"{prefix}.hypothesis_contract.outcome_routes.{route}")
        if str(contract.get("track_id") or "") != str(row.get("track_id") or ""):
            missing.append(f"{prefix}.hypothesis_contract.track_id must match track_id")
        signature = str(contract.get("causal_signature") or "").strip()
        if signature in causal_signatures:
            missing.append(f"{prefix}.hypothesis_contract.causal_signature duplicates track {causal_signatures[signature]}")
        elif signature:
            causal_signatures[signature] = str(row.get("track_id") or prefix)
        parent = contract.get("parent_track_id")
        if present(parent):
            for field in ["derived_from_run_id", "hypothesis_delta"]:
                if not present(contract.get(field)):
                    missing.append(f"{prefix}.hypothesis_contract.{field} required for child track")
        revision = contract.get("scientific_revision_index")
        max_revisions = contract.get("max_scientific_revisions")
        if isinstance(revision, int) and isinstance(max_revisions, int) and revision > max_revisions and launch_status == "ready":
            missing.append(f"{prefix} exhausted scientific revision budget and cannot be ready")
        if launch_status == "ready":
            if schema_version == 3 and row.get("planning_admitted") is not True:
                missing.append(f"{prefix}.planning_admitted=true required for ready tracks")
            if not selection_ref(row):
                missing.append(f"{prefix}.selection_fingerprint or selected_primary_ref")
            elif matrix_selection_ref and selection_ref(row) != matrix_selection_ref:
                missing.append(f"{prefix}.selection_fingerprint must match matrix selection_fingerprint")
            if not hypothesis_ready(contract):
                missing.append(f"{prefix}.hypothesis_contract incomplete or revision budget exhausted")
            if normalized(row.get("evidence_closure_status")) not in READY_EVIDENCE:
                missing.append(f"{prefix}.evidence_closure_status must be ready for launch")
            if present(row.get("blocked_reason")):
                missing.append(f"{prefix}.blocked_reason must be empty for ready tracks")
            gate = row.get("promotion_gate") if isinstance(row.get("promotion_gate"), dict) else {}
            if gate.get("ablation_required") is False or gate.get("confirmation_required") is False:
                missing.append(f"{prefix}.promotion_gate must preserve ablation/confirmation requirements")
        elif not present(row.get("blocked_reason")):
            warnings.append(f"{prefix}.blocked_reason recommended for non-ready tracks")
    mode = evidence_source_mode(base)
    if mode == "external_material":
        campaign_path = base / EXTERNAL_CAMPAIGN_REF
        campaign = read_json(campaign_path, {})
        if not campaign_path.exists() or not isinstance(campaign, dict) or not campaign:
            missing.append(EXTERNAL_CAMPAIGN_REF)
        else:
            campaign_sha = sha256_file(campaign_path)
            admitted = {
                str(item).strip()
                for item in campaign.get("admitted_candidate_ids", [])
                if str(item).strip()
            } if isinstance(campaign.get("admitted_candidate_ids"), list) else set()
            seeds_by_track = {
                str(seed.get("track_id")): seed
                for seed in seed_rows
                if present(seed.get("track_id"))
            }
            seen: list[str] = []
            for index, row in enumerate(rows):
                prefix = f"tracks[{index}]"
                for field in EXTERNAL_IDENTITY_FIELDS:
                    if not present(row.get(field)):
                        missing.append(f"{prefix}.{field}")
                if row.get("external_campaign_ref") != EXTERNAL_CAMPAIGN_REF:
                    missing.append(f"{prefix}.external_campaign_ref must be {EXTERNAL_CAMPAIGN_REF}")
                if row.get("external_campaign_sha256") != campaign_sha:
                    missing.append(f"{prefix}.external_campaign_sha256 must match current campaign")
                candidate_id = str(row.get("external_candidate_id") or "").strip()
                if candidate_id:
                    seen.append(candidate_id)
                    if candidate_id not in admitted:
                        missing.append(f"{prefix}.external_candidate_id must be admitted by current campaign")
                    if candidate_id in {str(row.get("track_id") or ""), str(row.get("idea_id") or "")}:
                        missing.append(f"{prefix} track_id/idea_id must remain distinct from external_candidate_id")
                seed = seeds_by_track.get(str(row.get("track_id") or ""), {})
                for field in EXTERNAL_IDENTITY_FIELDS:
                    if row.get(field) != seed.get(field):
                        missing.append(f"{prefix}.{field} must match source IDEA_TRACK_SEEDS row")
            if len(seen) != len(set(seen)):
                missing.append("external_candidate_id must be unique across TRACK_PLAN_MATRIX rows")
            if set(seen) != admitted:
                missing.append("TRACK_PLAN_MATRIX external candidate ids must exactly match admitted campaign ids")
    elif mode != "papernexus":
        missing.append(f"unsupported evidence_source_mode: {mode}")
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "track_count": len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        out = lint(args.project)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        raise SystemExit(0 if out["complete"] else 1)
    payload = build(args.project)
    path = ar(args.project) / "orchestrator/TRACK_PLAN_MATRIX.json"
    current = read_json(path, {}) or {}
    changed = not isinstance(current, dict) or current.get("semantic_sha256") != payload.get("semantic_sha256")
    if changed:
        write_json(path, payload)
        append_jsonl(
            ar(args.project) / "decision_log.jsonl",
            {
                "ts": now(),
                "stage": "experiment_plan",
                "action": "track_plan_matrix",
                "details": {
                    "track_count": len(payload["tracks"]),
                    "planning_admitted_count": sum(row.get("planning_admitted") is True for row in payload["tracks"]),
                },
            },
        )
    print(
        json.dumps(
            {
                "ok": True,
                "changed": changed,
                "path": "orchestrator/TRACK_PLAN_MATRIX.json",
                "track_count": len(payload["tracks"]),
                "planning_admitted_count": sum(row.get("planning_admitted") is True for row in payload["tracks"]),
                "semantic_sha256": payload.get("semantic_sha256"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
