#!/usr/bin/env python3
"""Focused fixtures for the closed-loop research contracts."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SKILLS = Path(__file__).resolve().parents[2]
EXPERIMENT_SCRIPTS = SKILLS / "autoreskill-experiment-plan/scripts"
WORKFLOW_SCRIPTS = SKILLS / "autoreskill-workflow/scripts"
for scripts_dir in [EXPERIMENT_SCRIPTS, WORKFLOW_SCRIPTS]:
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IDEA_POOL = load_module(
    "closed_loop_idea_pool",
    SKILLS / "autoreskill-experiment-plan/scripts/idea_pool_lint.py",
)
TRACK_SEEDS = load_module(
    "closed_loop_track_seeds",
    SKILLS / "autoreskill-ideation-panel/scripts/idea_track_seeds.py",
)
IDEA_SCORECARD = load_module(
    "closed_loop_idea_scorecard",
    SKILLS / "autoreskill-ideation-panel/scripts/idea_scorecard_lint.py",
)
INNOVATION_LINT = load_module(
    "closed_loop_innovation_lint",
    EXPERIMENT_SCRIPTS / "innovation_lint.py",
)
PRELAUNCH_LINT = load_module(
    "closed_loop_prelaunch_lint",
    EXPERIMENT_SCRIPTS / "prelaunch_lint.py",
)
HPO_POLICY = load_module(
    "closed_loop_hpo_policy",
    EXPERIMENT_SCRIPTS / "hpo_policy_lint.py",
)
TRACK_MATRIX = load_module(
    "closed_loop_track_matrix",
    EXPERIMENT_SCRIPTS / "track_plan_matrix.py",
)
GOAL_TICK = load_module(
    "closed_loop_goal_tick",
    WORKFLOW_SCRIPTS / "goal_tick.py",
)
CONTRACT_LINT = sys.modules["contract_lint"]
NEXT_ACTIONS = load_module(
    "closed_loop_next_actions",
    SKILLS / "autoreskill-workflow/scripts/experiment_next_actions.py",
)
QUEUE_FIXTURES = load_module(
    "closed_loop_queue_fixtures",
    SKILLS / "autoreskill-workflow/tests/run_experiment_next_actions_fixtures.py",
)

RUN_RECONCILE = SKILLS / "autoreskill-run-experiment/scripts/run_reconcile.py"
RESEARCH_DECISION = SKILLS / "autoreskill-workflow/scripts/research_decision.py"
BEST_RUN_SELECTOR = SKILLS / "autoreskill-analyze-results/scripts/best_run_selector.py"
ANALYSIS_LINT = SKILLS / "autoreskill-analyze-results/scripts/analysis_lint.py"
RETRY_SCHEDULER = SKILLS / "autoreskill-autopilot-controller/scripts/retry_scheduler.py"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_json(cmd: list[str], expect: int = 0) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"stdout": proc.stdout}
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr.strip()
    payload["returncode"] = proc.returncode
    if proc.returncode != expect:
        raise AssertionError({"cmd": cmd, "expected": expect, "result": payload})
    return payload


def audit() -> dict[str, bool]:
    return {
        "metric_drift": False,
        "eval_drift": False,
        "dataset_drift": False,
        "data_leakage": False,
        "prediction_cheating": False,
        "training_budget_drift": False,
    }


def storyline() -> dict[str, Any]:
    return {
        "opening_tension": "Current evidence does not explain the failure mode.",
        "hidden_cause": "The representation suppresses a required signal.",
        "method_as_resolution": "Restore that signal with one controlled intervention.",
        "proof_ladder": ["pilot", "ablation", "transfer"],
        "reviewer_risk_and_defense": "Separate mechanism support from parameter gains.",
        "narrative_spine": ["problem", "cause", "method", "pilot", "ablation"],
    }


def idea(index: int, deep: bool = False, selected: bool = False) -> dict[str, Any]:
    idea_id = f"IDEA-{index:03d}"
    payload: dict[str, Any] = {
        "id": idea_id,
        "type": "ALGO" if index < 8 else "PARAM",
        "priority": "HIGH" if index <= 3 else "MEDIUM",
        "risk": "MEDIUM",
        "status": "SELECTED" if selected else "SHORTLISTED" if deep else "PENDING",
        "research_question": f"Does intervention {index} recover signal {index}?",
        "core_scientific_contribution": f"Mechanism {index} explains and repairs failure {index}.",
        "target_domain_anchor": "target benchmark",
        "closest_prior_delta": f"Prior work does not test mechanism {index}.",
        "intervention": f"activate component {index}",
        "mechanism": f"restore latent signal {index}",
        "predicted_pattern": f"metric-{index} improves only when component {index} is active",
        "falsifier": f"matched ablation shows no metric-{index} change",
        "alternative_explanation": f"capacity rather than mechanism {index}",
        "cheapest_discriminating_experiment": f"one-seed matched pilot {index}",
        "causal_signature": f"component-{index}|signal-{index}|pattern-{index}",
        "paper_potential": {
            "target_claim": f"mechanism claim {index}",
            "minimum_experiment_table": "baseline, intervention, matched ablation",
            "reviewer_risk": "causal attribution",
        },
        "source_evidence_refs": [f"EV-{index:03d}"],
        "evidence_maturity": "evidence_backed" if deep else "promising",
        "primary_method_source_role": "near_neighbor",
        "innovation_slot_refs": [f"SLOT-{index:03d}"],
        "red_line_audit": audit(),
    }
    if deep:
        payload.update(
            {
                "closest_prior_comparison": "Different mechanism and predicted pattern.",
                "claim_boundary": "No SOTA or generalization claim before confirmation.",
                "outcome_routes": {
                    "positive": "ablation_or_confirmation",
                    "negative": "weaken_or_retire",
                    "inconclusive": "one_disambiguator",
                    "invalid": "repair_protocol",
                },
                "goe_path_refs": [f"GOE-{index:03d}"],
                "mechanism_source_path": f"evidence/mechanism-{index}.json",
                "negative_evidence_refs": [f"NEG-{index:03d}"],
                "reviewer_attack_surface": ["causal attribution"],
                "falsifier_probe": f"matched pilot {index}",
                "track_seed_spec": {
                    "track_id": f"track-{index:02d}",
                    "one_variable_change": f"activate component {index}",
                    "expected_metric_effect": f"metric-{index} increases",
                    "baseline_pressure": "paper-reported baseline",
                    "locked_or_missing_protocol_fields": ["dataset"],
                    "minimum_pilot": ["baseline", "proposed"],
                    "kill_condition": f"no metric-{index} change",
                },
                "paper_contribution": {
                    "paper_thesis": f"Mechanism {index} repairs the target failure.",
                    "contribution_type": "method",
                    "target_venue_fit": "top-tier ML",
                    "novelty_claim": f"first causal test of mechanism {index}",
                    "baseline_pressure": "paper-reported and matched reproduced baselines",
                    "minimum_experiment_table": "baseline, proposed, ablation",
                    "ablation_plan": f"remove component {index}",
                    "falsifier": f"no matched improvement for mechanism {index}",
                    "standalone_engineering": False,
                },
            }
        )
    if selected:
        payload["paper_contribution"]["storyline"] = storyline()
    return payload


def pool(count: int = 8, exception: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
        "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
        "selected_idea_id": "IDEA-001",
        "shortlisted_idea_ids": ["IDEA-001", "IDEA-002", "IDEA-003"],
        "ideas": [idea(index, deep=index <= 3, selected=index == 1) for index in range(1, count + 1)],
    }
    if exception:
        payload["pool_size_exception"] = exception
    return payload


def scorecard_row(payload: dict[str, Any], index: int) -> dict[str, Any]:
    idea_id = str(payload["id"])
    shortlisted = index <= 3
    row: dict[str, Any] = {
        "idea_id": idea_id,
        "rank": index,
        "scores": {
            "significance": 4,
            "novelty_separation": 4,
            "experiment_defensibility": 4,
            "feasibility": 4,
            "evidence_maturity": 4,
            "risk_control": 4,
        },
        "weighted_total": 4,
        "paper_comparison": {
            "closest_prior_papers": [f"PRIOR-{index:03d}"],
            "innovation_comparison": "different causal mechanism",
            "overlap_risk": "medium",
            "differentiation_claim": "different intervention and predicted pattern",
        },
        "causal_signature": payload["causal_signature"],
        "pairwise_comparison": {
            "closest_competing_idea_id": f"IDEA-{(index % 8) + 1:03d}",
            "mechanism_difference": "different latent signal",
            "predicted_pattern_difference": "different metric component",
            "cheapest_discriminator": "matched one-seed pilot",
            "verdict": "distinct",
        },
        "evidence_closure_level": "source_backed",
        "evidence_debt": [],
        "next_evidence_closure": "none before shortlist",
        "paper_potential_rank": index,
        "recommended_track_action": "primary" if index == 1 else "alternate" if shortlisted else "park",
        "innovation_slot_refs": payload["innovation_slot_refs"],
        "promotion_recommendation": "advance" if shortlisted else "park",
    }
    if shortlisted:
        row.update(
            {
                "paper_story_assessment": {
                    "core_contribution_verdict": "defensible",
                    "storyline_readiness": "ready" if index == 1 else "needs_selected-depth prose",
                    "weakest_causal_link": "alternative explanation",
                    "required_story_repair": "none" if index == 1 else "defer until selected",
                },
                "closest_prior_pressure": "matched prior required",
                "novelty_separation_needed": "mechanism and prediction",
                "graph_path_status": "closed",
                "near_neighbor_pressure": "source-backed",
                "far_neighbor_transfer_rationale": "mechanism transfer",
                "primary_method_source_role": "near_neighbor",
                "target_domain_anchor": "target benchmark",
                "neighbor_transfer_mechanism": "latent signal restoration",
                "target_domain_method_overlap_risk": "medium",
                "top_tier_support_judgment": "conditional on experiment",
                "venue_support_verdict": "advance with causal test",
            }
        )
    return row


def scorecard(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": "post_idea_generation_pre_idea_gate",
        "evidence_boundary": "source-backed synthetic fixture",
        "scoring_rubric": "1-5",
        "weights": {"significance": 1},
        "top_recommendations": ["IDEA-001", "IDEA-002", "IDEA-003"],
        "top_track_recommendations": ["IDEA-001", "IDEA-002", "IDEA-003"],
        "shortlisted_idea_ids": ["IDEA-001", "IDEA-002", "IDEA-003"],
        "selected_primary_idea_id": "IDEA-001",
        "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
        "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
        "source_evidence_roles": ["target_domain", "near_neighbor", "far_neighbor"],
        "rows": [scorecard_row(row, index) for index, row in enumerate(payload["ideas"], start=1)],
    }


def assert_complete(payload: dict[str, Any]) -> None:
    result = IDEA_POOL.lint(payload, require_selected=True)
    if not result["complete"]:
        raise AssertionError(result)


def phase1_cases() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    base = pool()
    assert_complete(base)
    results.append({"case": "eight_lightweight_three_deep", "ok": True})

    niche = pool(
        6,
        {
            "kind": "niche_topic",
            "reason": "Only six causally distinct mechanisms survived evidence screening.",
            "approved_by": "research-lead",
            "approved_at": "2026-07-10T00:00:00Z",
        },
    )
    assert_complete(niche)
    results.append({"case": "six_item_niche_exception", "ok": True})

    too_small = pool(6)
    result = IDEA_POOL.lint(too_small, require_selected=True)
    if result["complete"] or not any("recorded niche/breadth exception" in item for item in result["missing"]):
        raise AssertionError(result)
    results.append({"case": "six_without_exception_blocked", "ok": True})

    duplicate = pool()
    duplicate["ideas"][1]["causal_signature"] = duplicate["ideas"][0]["causal_signature"]
    result = IDEA_POOL.lint(duplicate, require_selected=True)
    if result["complete"] or not any("duplicates IDEA-001" in item for item in result["missing"]):
        raise AssertionError(result)
    results.append({"case": "semantic_duplicate_blocked", "ok": True})

    no_story = pool()
    del no_story["ideas"][0]["paper_contribution"]["storyline"]
    result = IDEA_POOL.lint(no_story, require_selected=True)
    if result["complete"] or not any("storyline required for selected primary" in item for item in result["missing"]):
        raise AssertionError(result)
    results.append({"case": "selected_story_required", "ok": True})

    paper_storyline = {"paper_thesis": "One causal mechanism explains the target failure.", **storyline()}
    single_core = {
        "core_scientific_contribution": "One falsifiable mechanism contribution.",
        "paper_storyline": paper_storyline,
    }
    missing: list[str] = []
    INNOVATION_LINT.validate_paper_bundle(single_core, missing, {})
    PRELAUNCH_LINT.validate_paper_bundle(single_core, missing)
    if missing:
        raise AssertionError(missing)
    results.append({"case": "one_core_contribution_without_invented_bundle", "ok": True})

    unsupported = {
        **single_core,
        "supporting_contributions": [
            {
                "name": "Optional scientific support",
                "contribution_class": "supporting_scientific_contribution",
                "evidence_refs": ["EV-support"],
                "validation_plan": "matched ablation",
            }
        ],
    }
    missing = []
    INNOVATION_LINT.validate_paper_bundle(unsupported, missing, {})
    if not any("counterfactual_necessity" in item for item in missing):
        raise AssertionError(missing)
    results.append({"case": "supporting_contribution_requires_counterfactual_necessity", "ok": True})

    seed_policy = {
        "seed_policy": {
            "seed_is_search_axis": False,
            "scout_random_seed_count": 1,
            "max_total_random_seeds": 3,
            "matched_seed_protocol": True,
        }
    }
    missing = []
    HPO_POLICY._validate_seed_policy(seed_policy, "fixture", missing)
    if missing:
        raise AssertionError(missing)
    seed_policy["seed_policy"]["max_total_random_seeds"] = 4
    missing = []
    HPO_POLICY._validate_seed_policy(seed_policy, "fixture", missing)
    if not any("between 1 and 3" in item for item in missing):
        raise AssertionError(missing)
    results.append({"case": "hpo_scout_and_confirmation_total_seed_cap_three", "ok": True})

    async_policy = HPO_POLICY.default_hpo_search_policy("PARAM")
    async_policy["search_space_audit"]["dimensions"] = [
        {
            "name": "temperature",
            "type": "log_float",
            "bounds_or_choices": [0.01, 1.0],
            "default_or_prior": 0.1,
            "rationale": "Test the mechanism scale under a bounded search.",
        }
    ]
    missing = []
    warnings: list[str] = []
    HPO_POLICY.validate_hpo_search_policy(
        {"mechanism_type": "PARAM", "hpo_search_policy": async_policy},
        "fixture",
        missing,
        warnings,
    )
    if missing or async_policy["execution_policy"]["mode"] != "elastic_async":
        raise AssertionError({"missing": missing, "warnings": warnings, "policy": async_policy})
    results.append({"case": "dehb_default_uses_bounded_elastic_async_execution", "ok": True})

    baseline_policy = json.loads(json.dumps(async_policy))
    baseline_policy["tuning_target"] = "baseline_calibration"
    baseline_policy["baseline_calibration_policy"] = {
        "validation_only_search": True,
        "freeze_before_claim_promotion": True,
        "equal_or_shared_tuning_budget": True,
        "provisional_overlap_evidence_tier": "pilot_only",
    }
    missing = []
    HPO_POLICY.validate_hpo_search_policy(
        {"mechanism_type": "PARAM", "hpo_search_policy": baseline_policy},
        "fixture",
        missing,
        [],
    )
    if missing:
        raise AssertionError(missing)
    baseline_policy["baseline_calibration_policy"]["provisional_overlap_evidence_tier"] = "claim_eligible"
    missing = []
    HPO_POLICY.validate_hpo_search_policy(
        {"mechanism_type": "PARAM", "hpo_search_policy": baseline_policy},
        "fixture",
        missing,
        [],
    )
    if not any("must be pilot_only" in item for item in missing):
        raise AssertionError(missing)
    results.append({"case": "baseline_calibration_overlap_remains_pilot_only", "ok": True})

    invalid_concurrency = json.loads(json.dumps(async_policy))
    invalid_concurrency["execution_policy"]["max_concurrent_scouts"] = 12.5
    missing = []
    HPO_POLICY.validate_hpo_search_policy(
        {"mechanism_type": "PARAM", "hpo_search_policy": invalid_concurrency},
        "fixture",
        missing,
        [],
    )
    if not any("max_concurrent_scouts" in item for item in missing):
        raise AssertionError(missing)
    results.append({"case": "fractional_hpo_concurrency_rejected", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-closed-loop-") as tmp:
        root = Path(tmp)
        payload = pool()
        scorecard_payload = scorecard(payload)
        write_json(root / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json", payload)
        write_json(root / ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", scorecard_payload)
        write_json(root / ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json", {"status": "passed"})
        write_json(root / ".autoreskill/ideation/INNOVATION_SLOT_MAP.json", {"challenge_clusters": []})
        scored = IDEA_SCORECARD.lint(
            str(root),
            "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            "ideation/EXPERIMENT_IDEA_POOL.json",
        )
        if not scored["complete"]:
            raise AssertionError(scored)
        results.append({"case": "pairwise_scorecard_three_item_shortlist", "ok": True})
        seeds = TRACK_SEEDS.build(str(root))
        write_json(root / ".autoreskill/ideation/IDEA_TRACK_SEEDS.json", seeds)
        checked = TRACK_SEEDS.check(str(root))
        if not checked["complete"] or len(seeds["tracks"]) != 3:
            raise AssertionError({"seeds": seeds, "check": checked})
        results.append({"case": "default_three_track_hypothesis_contracts", "ok": True})

        write_json(
            root / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
            {
                "selected_primary_idea_id": "IDEA-001",
                "selected_track_id": seeds["tracks"][0]["track_id"],
                "selection_fingerprint": "IDEA-001/track-selection/v1",
                "decisions": [
                    {
                        "idea_id": row["idea_id"],
                        "lifecycle_status": "selected_primary" if index == 0 else "alternate",
                        "selected_primary_ref": "IDEA-001/track-selection/v1",
                    }
                    for index, row in enumerate(seeds["tracks"])
                ],
            },
        )
        matrix = TRACK_MATRIX.build(str(root))
        if matrix.get("selection_fingerprint") != "IDEA-001/track-selection/v1" or any(
            row.get("selection_fingerprint") != "IDEA-001/track-selection/v1"
            for row in matrix.get("tracks", [])
        ):
            raise AssertionError(matrix)
        results.append({"case": "selection_fingerprint_propagates_to_track_matrix", "ok": True})
    return results


def science_project(root: Path, mechanism_type: str = "ALGO") -> None:
    base = root / ".autoreskill"
    write_json(
        base / "goal_state.json",
        {"stage": "experiment", "goal_type": "paper_producing_light", "claim_mode": "pilot_evidence"},
    )
    write_json(
        base / "ideation/IDEA_DECISION_LEDGER.json",
        {
            "schema_version": 2,
            "selected_primary_idea_id": "IDEA-001",
            "selected_track_id": "track-main",
            "selection_fingerprint": "IDEA-001/track-main/v1",
            "decisions": [
                {
                    "idea_id": "IDEA-001",
                    "scorecard_rank": 1,
                    "lifecycle_status": "selected_primary",
                    "decision_reason": "fixture primary",
                    "failure_class": "none",
                    "evidence_refs": ["EV-001"],
                    "claim_scope": "pilot only",
                    "next_action": "run discriminating experiment",
                    "selected_primary_ref": "IDEA-001/track-main/v1",
                }
            ],
            "terminal_program_context": {
                "remaining_claim_scope": "negative_or_inconclusive_evidence_only",
                "mandatory_downgrade": "No improvement or effectiveness claim is permitted.",
                "budget_or_value_rationale": "All bounded causal tracks are terminal and no remaining test changes a decision.",
                "target_stage": "analysis",
            },
        },
    )
    write_json(
        base / "orchestrator/TRACK_PLAN_MATRIX.json",
        {
            "schema_version": 2,
            "selected_idea_id": "IDEA-001",
            "selected_track_id": "track-main",
            "selection_fingerprint": "IDEA-001/track-main/v1",
            "tracks": [
                {
                    "idea_id": "IDEA-001",
                    "track_id": "track-main",
                    "branch_id": "branch-main",
                    "track_role": "primary",
                    "selected_for_review": True,
                    "selection_fingerprint": "IDEA-001/track-main/v1",
                    "hypothesis_contract": {
                        "track_id": "track-main",
                        "causal_signature": "intervention|mechanism|pattern",
                        "belief_state": "untested",
                        "max_scientific_revisions": 2,
                        "scientific_revision_index": 0,
                    },
                }
            ],
        },
    )
    write_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {"schema_version": 2, "queue_revision": 0, "rows": []})
    write_json(
        base / "planner/EXPERIMENT_REVIEW_PACKET.json",
        {
            "selected_idea_id": "IDEA-001",
            "track_id": "track-main",
            "selection_fingerprint": "IDEA-001/track-main/v1",
            "metric_direction": "higher",
        },
    )
    write_json(
        base / "orchestrator/INNOVATION_PACKET.json",
        {
            "selected_idea_id": "IDEA-001",
            "track_id": "track-main",
            "selection_fingerprint": "IDEA-001/track-main/v1",
            "innovation_mechanism": "fixture causal mechanism",
            "mechanism_type": mechanism_type,
        },
    )


def validity(outcome_class: str) -> dict[str, bool]:
    if outcome_class == "infrastructure_failure":
        return {"protocol_valid": True, "spec_valid": True, "evaluator_valid": False, "canonical_result_valid": False}
    if outcome_class == "implementation_failure":
        return {"protocol_valid": True, "spec_valid": False, "evaluator_valid": False, "canonical_result_valid": False}
    if outcome_class == "protocol_invalid":
        return {"protocol_valid": False, "spec_valid": True, "evaluator_valid": True, "canonical_result_valid": False}
    if outcome_class == "budget_stopped_no_scientific_conclusion":
        return {"protocol_valid": True, "spec_valid": True, "evaluator_valid": True, "canonical_result_valid": False}
    return {"protocol_valid": True, "spec_valid": True, "evaluator_valid": True, "canonical_result_valid": True}


def add_science_run(
    root: Path,
    run_id: str,
    outcome_class: str,
    belief_effect: str,
    transition: str,
    scientific_revision: int,
    operational_attempt: int = 0,
    mechanism_type: str = "ALGO",
    track_id: str = "track-main",
    selected_idea_id: str = "IDEA-001",
    track_role: str = "primary",
    evidence_tier_ceiling: str = "claim_eligible_after_gates",
) -> None:
    exp_dir = root / ".autoreskill/coder/experiments" / track_id / run_id
    launch_hash = f"launch-{run_id}"
    queue_row_id = f"queue-{run_id}"
    write_json(
        exp_dir / "EXPERIMENT_MANIFEST.json",
        {
            "run_id": run_id,
            "experiment_id": run_id,
            "selected_idea_id": selected_idea_id,
            "track_id": track_id,
            "track_role": track_role,
            "evidence_tier_ceiling": evidence_tier_ceiling,
            "evidence_tier": "pilot_only" if evidence_tier_ceiling == "pilot_only" else "claim_eligible",
            "branch_id": "branch-main",
            "queue_row_id": queue_row_id,
            "selection_fingerprint": "IDEA-001/track-main/v1",
            "launch_identity_hash": launch_hash,
            "innovation_mechanism": "fixture causal mechanism",
            "mechanism_type": mechanism_type,
            "promotion_stage": "candidate",
            "primary_metric": "accuracy",
            "metric_direction": "higher",
            "dataset": "fixture-dataset",
            "data_split": "test",
            "evaluate_command": "python evaluate.py",
            "locked_protocol": {"dataset": "fixture-dataset", "split": "test"},
            "source_snapshot": {"fixture": True},
        },
    )
    write_json(
        exp_dir / "results/metrics.json",
        {
            "baseline": 0.5,
            "proposed": 0.6 if outcome_class == "valid_positive_candidate" else 0.45,
            "primary_metric": 0.6 if outcome_class == "valid_positive_candidate" else 0.45,
        },
    )
    write_json(
        exp_dir / "SCIENTIFIC_OUTCOME.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "selected_idea_id": selected_idea_id,
            "track_id": track_id,
            "branch_id": "branch-main",
            "queue_row_id": queue_row_id,
            "selection_fingerprint": "IDEA-001/track-main/v1",
            "launch_identity_hash": launch_hash,
            "canonical_result_ref": f"coder/experiments/{track_id}/{run_id}/results/metrics.json",
            "raw_evidence_refs": [f"coder/experiments/{track_id}/{run_id}/REMOTE_RUN.json"],
            "validity": validity(outcome_class),
            "falsifier_evaluation": {"status": "satisfied" if outcome_class == "valid_negative" else "not_satisfied_or_not_applicable"},
            "outcome_class": outcome_class,
            "belief_effect": belief_effect,
            "recommended_transition": transition,
            "evidence_rationale": f"fixture evidence for {outcome_class}",
            "operational_attempt": operational_attempt,
            "scientific_revision": scientific_revision,
            "claim_effect": "downgrade" if outcome_class != "valid_positive_candidate" else "candidate_only",
            "claim_limits": {"scope": "fixture; no automatic improvement claim"},
            "adjudicator": {"role": "fixture-independent-adjudicator"},
            "adjudicated_at": "2026-07-10T00:00:00Z",
        },
    )


def reconcile(root: Path, status: str) -> dict[str, Any]:
    return run_json(
        [sys.executable, str(RUN_RECONCILE), "--project", str(root), "--backend", "local", "--status", status]
    )


def decide(root: Path, run_id: str, expect: int = 0) -> dict[str, Any]:
    return run_json(
        [sys.executable, str(RESEARCH_DECISION), "--project", str(root), "--run-id", run_id, "--write"],
        expect=expect,
    )


def one_outcome_case(
    outcome_class: str,
    belief_effect: str,
    transition: str,
    *,
    revision: int = 0,
    operational_attempt: int = 0,
    status: str = "completed",
    mechanism_type: str = "ALGO",
) -> tuple[dict[str, Any], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-science-") as tmp:
        root = Path(tmp)
        science_project(root, mechanism_type=mechanism_type)
        add_science_run(
            root,
            "run-1",
            outcome_class,
            belief_effect,
            transition,
            revision,
            operational_attempt,
            mechanism_type,
        )
        reconcile(root, status)
        decision = decide(root, "run-1")
        reconcile(root, status)
        experiment = json.loads((root / ".autoreskill/coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        lifecycle = json.loads((root / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json").read_text(encoding="utf-8"))
        entry = experiment["entries"][0]
        if entry.get("scientific_outcome_status") != "accepted":
            raise AssertionError(entry)
        if decision.get("decision", {}).get("belief_effect") != belief_effect:
            raise AssertionError(decision)
        return entry, lifecycle


def phase2_to_5_cases() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="autoreskill-capacity-replenishment-") as tmp:
        root = Path(tmp)
        base = root / ".autoreskill"
        write_json(
            base / "goal_state.json",
            {
                "autonomy_level": "full_auto_bounded",
                "goal_type": "paper_producing_top_tier",
            },
        )
        write_json(base / "autopilot_policy.json", {"allow_autonomous_candidate_replenishment": True})
        frontier = {
            "portfolio_actionable": False,
            "portfolio_admission_deficit": 2,
            "portfolio_blocker_code": "shortlist_missing_or_exhausted",
            "active_nonterminal_track_count": 2,
            "fresh_fitting_idle_slots": 3,
            "frontier_underfilled": False,
        }
        original_frontier_signal = GOAL_TICK.experiment_frontier_signal
        GOAL_TICK.experiment_frontier_signal = lambda _base: frontier
        try:
            blocker_class, action = GOAL_TICK.classify("experiment", "fixture shortage", base)
        finally:
            GOAL_TICK.experiment_frontier_signal = original_frontier_signal
        if (blocker_class, action) != ("auto_repairable", "replenish_experiment_portfolio"):
            raise AssertionError({"blocker_class": blocker_class, "action": action})
        spec = GOAL_TICK.execution_spec(
            "experiment",
            {
                "goal": "test a bounded paper hypothesis",
                "paperNexus": {"corpus": "fixture"},
                "autonomy_level": "full_auto_bounded",
            },
            {},
            {"action": "replenish_experiment_portfolio"},
            base,
        )
        if spec.get("skill") != "autoreskill-workflow" or "preserve the active selection_fingerprint" not in str(
            spec.get("goal") or ""
        ):
            raise AssertionError(spec)
        if GOAL_TICK.automatic_portfolio_replenishment_allowed(
            base, {**frontier, "active_nonterminal_track_count": 0}
        ):
            raise AssertionError("legacy zero-active behavior changed without an enforced program contract")
        write_json(
            base / "ideation/IDEA_DECISION_LEDGER.json",
            {"track_states": [{"track_id": "terminal-track", "lifecycle_status": "retired"}]},
        )
        if GOAL_TICK.automatic_portfolio_replenishment_allowed(base, frontier):
            raise AssertionError("all-terminal program closure must outrank candidate replenishment")
        results.append({"case": "idle_capacity_routes_bounded_candidate_replenishment", "ok": True})
        results.append({"case": "zero_active_or_all_terminal_does_not_force_positive_search", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-enforced-zero-active-replenishment-") as tmp:
        root = Path(tmp)
        base = root / ".autoreskill"
        write_json(
            base / "goal_state.json",
            {"autonomy_level": "full_auto_bounded", "goal_type": "paper_producing_top_tier"},
        )
        write_json(base / "autopilot_policy.json", {"allow_autonomous_candidate_replenishment": True})
        write_json(
            base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json",
            {
                "contract_status": "active",
                "enforcement_mode": "enforced",
                "claim_scope": "cross_dataset_method",
                "semantic_sha256": "a" * 64,
                "search_budget": {
                    "portfolio_capacity_target": 4,
                    "method_portfolio_target": 2,
                    "max_targeted_replenishments": 1,
                },
                "promotion_rule": {"max_random_seeds": 3},
            },
        )
        write_json(
            base / "ideation/IDEA_DECISION_LEDGER.json",
            {"program_scientific_status": "unresolved", "selection_fingerprint": "selection-zero"},
        )
        write_json(
            base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            {"selection_revision": "selection-zero", "shortlist": []},
        )
        queue = {
            "schema_version": 2,
            "queue_revision": 0,
            "policy": {"portfolio_capacity_target": 4, "method_portfolio_target": 2},
            "resource_snapshot": {
                "fresh": True,
                "stale": False,
                "status": "fresh",
                "pools": [{"pool_id": "fixture", "status": "available", "launch_slots": 3}],
            },
            "rows": [],
        }
        write_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", queue)
        write_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {"tracks": []})
        enforced_frontier = NEXT_ACTIONS.frontier_status(queue, {"tracks": []}, root)
        if not GOAL_TICK.automatic_portfolio_replenishment_allowed(base, enforced_frontier):
            raise AssertionError({"frontier": enforced_frontier, "proposal": GOAL_TICK.replenishment_proposal(base, enforced_frontier)})
        run_json([sys.executable, str(RESEARCH_DECISION), "--project", str(root), "--replenishment", "--write"])
        ledger = json.loads((base / "ideation/IDEA_DECISION_LEDGER.json").read_text(encoding="utf-8"))
        if len(ledger.get("replenishment_events") or []) != 1:
            raise AssertionError("enforced zero-active replenishment did not commit exactly one ledger event")
        if GOAL_TICK.automatic_portfolio_replenishment_allowed(base, enforced_frontier):
            raise AssertionError("unchanged replenishment basis was authorized twice")
        results.append({"case": "enforced_zero_active_changed_basis_replenishes_once", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-queue-contract-") as tmp:
        root = Path(tmp)
        QUEUE_FIXTURES.write_authorities(root)
        row = QUEUE_FIXTURES.valid_row("stale-row", 1)
        row["selection_fingerprint"] = "stale-selection"
        queue = {"schema_version": 2, "queue_revision": 0, "policy": {"max_random_seed_count": 3}, "rows": [row]}
        checked = NEXT_ACTIONS.validate_queue(queue, root)
        if checked["ok"] or not any("stale selection fingerprint" in error for error in checked["errors"]):
            raise AssertionError(checked)
        results.append({"case": "stale_selection_fingerprint_ready_blocked", "ok": True})

        row = QUEUE_FIXTURES.valid_row("missing-routes", 1)
        del row["outcome_routes"]
        checked = NEXT_ACTIONS.validate_queue({**queue, "rows": [row]}, root)
        if checked["ok"] or not any("outcome_routes" in error for error in checked["errors"]):
            raise AssertionError(checked)
        results.append({"case": "missing_outcome_routes_ready_blocked", "ok": True})

        QUEUE_FIXTURES.test_hard_launch_identity_and_atomic_claim(root)
        results.append({"case": "two_local_claimers_one_lease", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-untyped-outcome-") as tmp:
        root = Path(tmp)
        science_project(root)
        write_json(
            root / ".autoreskill/coder/EXPERIMENT_LEDGER.json",
            {
                "entries": [
                    {
                        "run_id": "legacy-run",
                        "selected_idea_id": "IDEA-001",
                        "track_id": "track-main",
                        "status": "completed",
                        "promotion_decision": "not_promoted",
                    }
                ]
            },
        )
        blocker_class, action = GOAL_TICK.classify(
            "experiment", "promoted best_run is required for ready_for_analysis", root / ".autoreskill"
        )
        if (blocker_class, action) != ("auto_repairable", "adjudicate_scientific_outcome"):
            raise AssertionError({"blocker_class": blocker_class, "action": action})
        results.append({"case": "untyped_nonpromotion_requires_adjudication_not_repair", "ok": True})

    entry, lifecycle = one_outcome_case(
        "infrastructure_failure", "none", "WAIT_OR_RECONCILE_BACKEND", operational_attempt=1, status="failed"
    )
    if lifecycle["track_states"][0]["belief_state"] != "untested":
        raise AssertionError(lifecycle)
    results.append({"case": "infrastructure_failure_belief_unchanged", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-infra-not-negative-") as tmp:
        root = Path(tmp)
        science_project(root)
        add_science_run(
            root,
            "run-infra",
            "infrastructure_failure",
            "none",
            "WAIT_OR_RECONCILE_BACKEND",
            0,
            operational_attempt=1,
        )
        reconcile(root, "failed")
        decide(root, "run-infra")
        reconcile(root, "failed")
        negatives = CONTRACT_LINT.negative_experiment_artifacts_for_selection(
            root / ".autoreskill", "IDEA-001", "track-main"
        )
        if negatives:
            raise AssertionError(negatives)
        results.append({"case": "typed_infrastructure_not_misread_as_scientific_negative", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-negative-authority-") as tmp:
        root = Path(tmp)
        science_project(root)
        add_science_run(
            root,
            "run-negative",
            "valid_negative",
            "support_weakened",
            "RETIRE_TRACK",
            0,
        )
        reconcile(root, "completed")
        negatives = CONTRACT_LINT.negative_experiment_artifacts_for_selection(
            root / ".autoreskill", "IDEA-001", "track-main"
        )
        if negatives:
            raise AssertionError({"message": "unaccepted sidecar changed selection state", "negatives": negatives})
        decide(root, "run-negative")
        reconcile(root, "completed")
        negatives = CONTRACT_LINT.negative_experiment_artifacts_for_selection(
            root / ".autoreskill", "IDEA-001", "track-main"
        )
        if not any(row.get("outcome_class") == "valid_negative" for row in negatives):
            raise AssertionError({"message": "accepted negative was not visible", "negatives": negatives})
        results.append({"case": "only_accepted_scientific_negative_changes_selection_state", "ok": True})

    entry, lifecycle = one_outcome_case(
        "implementation_failure", "none", "REFINE_IMPLEMENTATION", operational_attempt=1, status="failed"
    )
    if lifecycle["track_states"][0]["belief_state"] != "untested":
        raise AssertionError(lifecycle)
    results.append({"case": "implementation_failure_refines_without_downgrade", "ok": True})

    entry, lifecycle = one_outcome_case("protocol_invalid", "none", "REFINE_PROTOCOL", operational_attempt=1)
    if entry.get("canonical_eval_status") != "passed" or entry.get("scientific_outcome_status") != "accepted":
        raise AssertionError(entry)
    results.append({"case": "protocol_drift_quarantines_scientific_claim", "ok": True})

    entry, lifecycle = one_outcome_case("valid_negative", "support_weakened", "PIVOT_TO_CHILD_TRACK", revision=1)
    if entry.get("research_transition") == "REFINE_IMPLEMENTATION" or lifecycle["track_states"][0]["belief_state"] != "support_weakened":
        raise AssertionError({"entry": entry, "lifecycle": lifecycle})
    results.append({"case": "valid_negative_weakens_and_pivots", "ok": True})

    entry, lifecycle = one_outcome_case("valid_inconclusive", "still_inconclusive", "RUN_ONE_DISAMBIGUATOR", revision=1)
    if lifecycle["track_states"][0]["disambiguator_count"] != 1:
        raise AssertionError(lifecycle)
    results.append({"case": "inconclusive_allows_one_disambiguator", "ok": True})

    entry, lifecycle = one_outcome_case("valid_inconclusive", "still_inconclusive", "RETIRE_TRACK")
    if lifecycle["track_states"][0]["lifecycle_status"] != "retired":
        raise AssertionError(lifecycle)
    results.append({"case": "inconclusive_without_useful_test_retires", "ok": True})

    entry, lifecycle = one_outcome_case(
        "valid_positive_candidate", "support_increased", "PROCEED_TO_ABLATION_OR_CONFIRMATION"
    )
    if entry.get("promotion_decision") != "candidate_supported" or entry.get("research_transition") != "PROCEED_TO_ABLATION_OR_CONFIRMATION":
        raise AssertionError(entry)
    results.append({"case": "positive_candidate_requires_confirmation", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-positive-alternate-") as tmp:
        root = Path(tmp)
        science_project(root)
        add_science_run(
            root,
            "run-alternate",
            "valid_positive_candidate",
            "support_increased",
            "PROCEED_TO_ABLATION_OR_CONFIRMATION",
            0,
            track_id="track-alternate",
            selected_idea_id="IDEA-ALT",
            track_role="alternate",
            evidence_tier_ceiling="pilot_only",
        )
        reconcile(root, "completed")
        blocked = decide(root, "run-alternate", expect=1)
        if not any(
            "must request primary reselection" in str(error.get("observed") or "")
            for error in blocked.get("errors") or []
        ):
            raise AssertionError(blocked)
        outcome_path = root / ".autoreskill/coder/experiments/track-alternate/run-alternate/SCIENTIFIC_OUTCOME.json"
        outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
        outcome["recommended_transition"] = "REQUEST_PRIMARY_RESELECTION"
        write_json(outcome_path, outcome)
        decision = decide(root, "run-alternate")
        reconcile(root, "completed")
        experiment = json.loads((root / ".autoreskill/coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        lifecycle = json.loads((root / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json").read_text(encoding="utf-8"))
        entry = experiment["entries"][0]
        if entry.get("promotion_decision") != "record_only":
            raise AssertionError(entry)
        if decision.get("decision", {}).get("reselection_required") is not True:
            raise AssertionError(decision)
        alternate_state = next(row for row in lifecycle["track_states"] if row.get("track_id") == "track-alternate")
        if alternate_state.get("lifecycle_status") != "reselection_candidate":
            raise AssertionError(lifecycle)
        if lifecycle.get("selected_primary_idea_id") != "IDEA-001":
            raise AssertionError("positive alternate must not auto-replace the paper primary")
        results.append({"case": "positive_alternate_requires_reselection_and_matched_rerun", "ok": True})

    entry, lifecycle = one_outcome_case("cross_dataset_contradiction", "scope_narrowed", "SCOPE_CLAIM")
    if lifecycle["track_states"][0]["belief_state"] != "scope_narrowed":
        raise AssertionError(lifecycle)
    results.append({"case": "cross_dataset_contradiction_scopes_claim", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-running-") as tmp:
        root = Path(tmp)
        science_project(root)
        add_science_run(root, "run-live", "valid_inconclusive", "still_inconclusive", "RETIRE_TRACK", 0)
        (root / ".autoreskill/coder/experiments/track-main/run-live/SCIENTIFIC_OUTCOME.json").unlink()
        (root / ".autoreskill/coder/experiments/track-main/run-live/results/metrics.json").unlink()
        reconcile(root, "running")
        ledger = json.loads((root / ".autoreskill/coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        if ledger["entries"][0]["status"] != "running" or ledger["entries"][0]["scientific_outcome_status"] != "pending_runtime":
            raise AssertionError(ledger)
        results.append({"case": "empty_log_backend_running_stays_active", "ok": True})

    entry, lifecycle = one_outcome_case(
        "valid_positive_candidate",
        "support_increased",
        "PROCEED_TO_ABLATION_OR_CONFIRMATION",
        mechanism_type="PARAM",
    )
    if entry.get("scientific_claim_class") != "parameter_evidence" or entry.get("promotion_decision") == "promoted":
        raise AssertionError(entry)
    results.append({"case": "param_gain_remains_parameter_evidence", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-repair-budgets-") as tmp:
        root = Path(tmp)
        add_cmd = [
            sys.executable,
            str(RETRY_SCHEDULER),
            "add",
            "--project",
            str(root),
            "--kind",
            "repair",
            "--stage",
            "experiment",
            "--action",
            "refine_implementation",
            "--reason",
            "same deterministic parser defect",
            "--failure-class",
            "implementation_failure",
            "--failure-signature",
            "failure-parser-fixture",
        ]
        job = run_json(add_cmd)
        job_id = job["job_id"]
        for status in ["running", "running", "completed"]:
            run_json(
                [
                    sys.executable,
                    str(RETRY_SCHEDULER),
                    "update",
                    "--project",
                    str(root),
                    "--kind",
                    "repair",
                    "--job-id",
                    job_id,
                    "--status",
                    status,
                ]
            )
        exhausted = run_json(add_cmd, expect=1)
        if "operational repair budget exhausted" not in exhausted.get("stderr", ""):
            raise AssertionError(exhausted)
        run_json(
            [
                sys.executable,
                str(RETRY_SCHEDULER),
                "add",
                "--project",
                str(root),
                "--kind",
                "repair",
                "--stage",
                "experiment",
                "--action",
                "run_one_disambiguator",
                "--reason",
                "scientific discriminator remains useful",
                "--failure-class",
                "valid_inconclusive",
                "--repair-kind",
                "scientific_revision",
                "--scientific-revision",
                "2",
            ]
        )
        revision_blocked = run_json(
            [
                sys.executable,
                str(RETRY_SCHEDULER),
                "add",
                "--project",
                str(root),
                "--kind",
                "repair",
                "--stage",
                "experiment",
                "--action",
                "run_one_disambiguator",
                "--reason",
                "third scientific revision",
                "--failure-class",
                "valid_inconclusive",
                "--repair-kind",
                "scientific_revision",
                "--scientific-revision",
                "3",
            ],
            expect=1,
        )
        if "scientific revision budget exhausted" not in revision_blocked.get("stderr", ""):
            raise AssertionError(revision_blocked)
        results.append({"case": "operational_and_scientific_budgets_are_separate_and_bounded", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-negative-program-") as tmp:
        root = Path(tmp)
        science_project(root)
        add_science_run(root, "run-neg-1", "valid_negative", "support_weakened", "PIVOT_TO_CHILD_TRACK", 1)
        add_science_run(root, "run-neg-2", "valid_negative", "refuted", "RETIRE_TRACK", 2)
        reconcile(root, "completed")
        decide(root, "run-neg-1")
        decide(root, "run-neg-2")
        reconcile(root, "completed")
        program = run_json(
            [sys.executable, str(RESEARCH_DECISION), "--project", str(root), "--all-terminal", "--write"]
        )
        if program["program_decision"]["status"] != "core_hypotheses_refuted":
            raise AssertionError(program)
        reconcile(root, "completed")
        ledger = json.loads((root / ".autoreskill/coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        if ledger.get("ready_for_analysis") is not True or ledger.get("improvement_claim_allowed") is not False:
            raise AssertionError(ledger)
        selector = run_json([sys.executable, str(BEST_RUN_SELECTOR), "--project", str(root)])
        if not selector.get("complete"):
            raise AssertionError(selector)
        selection = json.loads(
            (root / ".autoreskill/analyzer/BEST_RUN_SELECTION.json").read_text(encoding="utf-8")
        )
        if selection.get("final_promotion_status") != "terminal_program_no_promoted_run" or selection.get("selected_run_id"):
            raise AssertionError(selection)
        for rel in [
            "analyzer/CLAIM_EVIDENCE_MATRIX.md",
            "analyzer/TRACK_VERDICTS.md",
            "analyzer/UNSUPPORTED_CLAIMS.md",
            "analyzer/NARRATIVE_REPORT.md",
        ]:
            path = root / ".autoreskill" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Terminal negative fixture\n\nNo positive improvement claim.\n", encoding="utf-8")
        analysis = run_json([sys.executable, str(ANALYSIS_LINT), "--project", str(root), "--strict"])
        if not analysis.get("complete"):
            raise AssertionError(analysis)
        results.append({"case": "two_negatives_retire_no_third_repair", "ok": True})
        results.append({"case": "all_terminal_negative_reaches_analysis", "ok": True})
        results.append({"case": "terminal_negative_analyzer_selects_no_invented_best", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-budget-program-") as tmp:
        root = Path(tmp)
        science_project(root)
        add_science_run(
            root,
            "run-budget",
            "budget_stopped_no_scientific_conclusion",
            "none",
            "CONCLUDE_PROGRAM",
            0,
        )
        reconcile(root, "budget_stopped")
        decide(root, "run-budget")
        reconcile(root, "budget_stopped")
        program = run_json(
            [sys.executable, str(RESEARCH_DECISION), "--project", str(root), "--all-terminal", "--write"]
        )
        if program["program_decision"]["status"] != "inconclusive_budget_exhausted":
            raise AssertionError(program)
        reconcile(root, "budget_stopped")
        ledger = json.loads((root / ".autoreskill/coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        if ledger.get("ready_for_analysis") is not True or ledger.get("improvement_claim_allowed") is not False:
            raise AssertionError(ledger)
        results.append({"case": "budget_exhausted_program_reaches_analysis_without_claim", "ok": True})

    return results


def main() -> None:
    results = phase1_cases() + phase2_to_5_cases()
    print(json.dumps({"ok": True, "results": results}, indent=2))


if __name__ == "__main__":
    main()
