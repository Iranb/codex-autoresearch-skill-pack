#!/usr/bin/env python3
"""Focused offline fixtures for cross-dataset parameter and claim boundaries."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT.parent
SCRIPTS = ROOT / "scripts"
PLAN_SCRIPTS = SKILLS / "autoreskill-experiment-plan/scripts"
for script_dir in [SCRIPTS, PLAN_SCRIPTS]:
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROGRAM = load("cross_program", SCRIPTS / "program_claim_contract.py")
PARAMETER = load("cross_parameter", SCRIPTS / "parameter_transfer.py")
DECISION = load("cross_decision", SCRIPTS / "research_decision.py")
BATCH = load("cross_batch", SCRIPTS / "portfolio_batch.py")
QUEUE = load("cross_queue", SCRIPTS / "experiment_next_actions.py")
MATERIALIZE = SKILLS / "autoreskill-experiment-plan/scripts/experiment_materialize.py"
HPO = load("cross_hpo", SKILLS / "autoreskill-experiment-plan/scripts/hpo_policy_lint.py")
STAGES = load("cross_stages", SCRIPTS / "stage_transition_materialize.py")
GROUP_HPO = load("cross_group_hpo", SKILLS / "autoreskill-run-experiment/scripts/dataset_group_hpo.py")
PRELAUNCH = load("cross_prelaunch", SKILLS / "autoreskill-experiment-plan/scripts/prelaunch_lint.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def program(project: Path) -> dict[str, Any]:
    payload = PROGRAM.default_contract(project)
    payload.update(
        {
            "contract_status": "active",
            "enforcement_mode": "enforced",
            "claim_target": "one method improves both required datasets",
            "target_datasets": [
                {
                    "dataset_id": "dataset-a",
                    "role": "primary",
                    "required": True,
                    "canonical_metric": "score-a",
                    "metric_direction": "higher",
                    "normalization_scale_ref": "scale:a",
                    "matched_baseline_ref": "baseline:a",
                    "paper_report_ref": None,
                    "paper_report_alignment": "unavailable",
                },
                {
                    "dataset_id": "dataset-b",
                    "role": "contrast",
                    "required": True,
                    "canonical_metric": "score-b",
                    "metric_direction": "higher",
                    "normalization_scale_ref": "scale:b",
                    "matched_baseline_ref": "baseline:b",
                    "paper_report_ref": None,
                    "paper_report_alignment": "unavailable",
                },
            ],
        }
    )
    payload["promotion_rule"]["worst_dataset_floor_by_dataset"] = {
        "dataset-a": 0.0,
        "dataset-b": 0.0,
    }
    return PROGRAM.bind_hash(payload)


def transfer(mode: str = "shared_normalized") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "parameter_role": "innovation_load_bearing",
        "load_bearing": True,
        "parameter_name": "association_margin_threshold",
        "parameter_calibration_group_id": "parameter-track-a-r1",
        "parameter_probe_kind": "bounded_calibration",
        "scale_type": "dimensionless_quantile" if mode == "shared_normalized" else "absolute",
        "transfer_mode": mode,
        "shared_formula": "dataset quantile times common q" if mode == "shared_normalized" else "raw scalar",
        "normalization_or_calibration_statistic": "train-only quantile" if mode == "shared_normalized" else "none",
        "calibration_data_scope": "train_only",
        "selection_metric": "mechanism_readout",
        "selection_rule": "maximize worst-dataset mechanism readout",
        "selection_rule_spec": {"direction": "max", "tie_break": "smaller_setting"},
        "stop_rule": "freeze after complete preregistered group",
        "claim_ceiling": "transferable_method" if mode != "dataset_calibrated" else "dataset_calibrated_method",
        "innovation_parameter_coverage_required": True,
        "minimum_distinct_values_per_dataset": 2,
        "max_values_per_dataset": 3,
        "seed_cardinality_per_dataset_during_parameter_coverage": 1,
        "single_value_exception": "none",
        "test_outcome_forbidden": True,
        "required_dataset_ids": ["dataset-a", "dataset-b"],
        "selection_seed_by_dataset": {"dataset-a": 0, "dataset-b": 0},
        "candidate_values_by_dataset": {
            "dataset-a": [0.05, 0.10],
            "dataset-b": [0.05, 0.10],
        },
        "value_basis_by_dataset": {
            "dataset-a": "predeclared train-only scale audit",
            "dataset-b": "predeclared train-only scale audit",
        },
    }
    if mode == "shared_absolute":
        payload["scale_comparability_rationale"] = "same units and matched empirical scale"
    payload["parameter_transfer_contract_sha256"] = PARAMETER.stable_hash(payload)
    return payload


def case_program_contract_cas() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-program-contract-") as temp:
        project = Path(temp)
        candidate = program(project)
        missing_floor = json.loads(json.dumps(candidate))
        del missing_floor["promotion_rule"]["worst_dataset_floor_by_dataset"]["dataset-b"]
        missing_floor = PROGRAM.bind_hash(missing_floor)
        floor_check = PROGRAM.validate_contract(missing_floor, require_activatable=True)
        require(
            any("worst_dataset_floor_by_dataset.dataset-b" in item for item in floor_check["errors"]),
            "active cross-dataset contract accepted a missing promotion floor",
        )
        unbounded = json.loads(json.dumps(candidate))
        unbounded["search_budget"]["max_parameter_probe_gpu_hours_per_track"] = None
        unbounded["search_budget"]["gpu_hour_budget"] = None
        unbounded = PROGRAM.bind_hash(unbounded)
        unbounded_check = PROGRAM.validate_contract(unbounded, require_activatable=True)
        require(
            any("max_parameter_probe_gpu_hours_per_track" in item for item in unbounded_check["errors"])
            and any("gpu_hour_budget" in item for item in unbounded_check["errors"]),
            "active cross-dataset contract accepted unbounded GPU budgets",
        )
        candidate.pop("semantic_sha256", None)
        first = PROGRAM._cas_mutate(
            project,
            candidate,
            action="fixture_commit",
            expected_sha256="",
            expected_revision=-1,
        )
        require(first["changed"] is True, "initial contract commit did not write")
        current = first["contract"]
        idempotent = PROGRAM._cas_mutate(
            project,
            current,
            action="fixture_commit",
            expected_sha256=current["semantic_sha256"],
            expected_revision=current["contract_revision"],
        )
        require(idempotent["changed"] is False, "identical contract commit was not idempotent")
        try:
            PROGRAM._cas_mutate(
                project,
                candidate,
                action="fixture_stale",
                expected_sha256="0" * 64,
                expected_revision=current["contract_revision"],
            )
        except ValueError as exc:
            require("stale expected SHA-256" in str(exc), "stale contract failure was not explicit")
        else:
            raise AssertionError("stale contract CAS was accepted")
        events = (project / PROGRAM.EVENTS_REL).read_text(encoding="utf-8").splitlines()
        require(len(events) == 1, "idempotent or stale contract operation appended an event")
        return {
            "case": "program_contract_cas",
            "revision": current["contract_revision"],
            "semantic_sha256": current["semantic_sha256"],
            "missing_dataset_floor_rejected": True,
        }


def case_rollout_modes() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-program-modes-") as temp:
        project = Path(temp)
        matrix = {
            "schema_version": 2,
            "selection_fingerprint": "selection-a",
            "tracks": [
                {
                    "track_id": "track-a",
                    "idea_id": "idea-a",
                    "track_role": "primary",
                    "claim_role": "method_candidate",
                    "idea_lifecycle_status": "selected_primary",
                    "selected_for_review": True,
                    "hypothesis_contract": {"belief_state": "untested"},
                }
            ],
        }
        write_json(
            project / ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json",
            matrix,
        )
        observed: list[str] = []
        for mode in ["legacy", "shadow", "enforced"]:
            payload = program(project)
            payload["enforcement_mode"] = mode
            payload = PROGRAM.bind_hash(payload)
            checked = PROGRAM.validate_contract(payload, require_activatable=True)
            require(checked["complete"], f"valid {mode} contract was rejected: {checked['errors']}")
            write_json(project / PROGRAM.CONTRACT_REL, payload)
            before = {
                str(path.relative_to(project)): file_sha256(path)
                for path in project.rglob("*") if path.is_file()
            }
            frontier = QUEUE.frontier_status(
                {
                    "schema_version": 2,
                    "queue_revision": 0,
                    "policy": {"portfolio_capacity_target": 4, "method_portfolio_target": 2},
                    "rows": [],
                },
                matrix=matrix,
                project=project,
            )
            require(
                frontier["program_contract_enforcement_mode"] == mode,
                f"frontier did not preserve {mode} rollout mode",
            )
            after = {
                str(path.relative_to(project)): file_sha256(path)
                for path in project.rglob("*") if path.is_file()
            }
            require(before == after, f"{mode} frontier mutated project artifacts")
            if mode == "legacy":
                require(not frontier.get("cross_dataset_blockers"), "legacy mode activated enforced blockers")
                require("shadow_cross_dataset_status" not in frontier, "legacy mode emitted shadow projection")
            elif mode == "shadow":
                require(frontier.get("shadow_enforcement_would_block") is True, "shadow mode missed enforced blockers")
                require(not frontier.get("cross_dataset_blockers"), "shadow blockers changed active frontier")
                require(frontier.get("shadow_cross_dataset_status", {}).get("cross_dataset_blockers"), "shadow blocker details missing")
            else:
                require(frontier.get("cross_dataset_blockers"), "enforced mode did not activate blockers")
            observed.append(mode)
        return {"case": "rollout_modes", "observed": observed}


def case_transfer_freeze_semantics() -> dict[str, Any]:
    datasets = ["dataset-a", "dataset-b"]
    normalized = transfer("shared_normalized")
    require(PARAMETER.validate_parameter_transfer_contract(normalized, datasets)["complete"], "valid shared normalized contract rejected")
    validation_scope = json.loads(json.dumps(normalized))
    validation_scope["calibration_data_scope"] = "validation"
    validation_scope["parameter_transfer_contract_sha256"] = PARAMETER.stable_hash(
        {key: value for key, value in validation_scope.items() if key != "parameter_transfer_contract_sha256"}
    )
    require(
        any("calibration_data_scope" in item for item in PARAMETER.validate_parameter_transfer_contract(validation_scope, datasets)["errors"]),
        "validation-label calibration scope was accepted",
    )
    hardcoded = json.loads(json.dumps(normalized))
    hardcoded["shared_formula"] = "use q=0.10 for dataset-a else q=0.05"
    hardcoded["parameter_transfer_contract_sha256"] = PARAMETER.stable_hash(
        {key: value for key, value in hardcoded.items() if key != "parameter_transfer_contract_sha256"}
    )
    hardcoded_errors = PARAMETER.validate_parameter_transfer_contract(hardcoded, datasets)["errors"]
    require(
        any(item.startswith("shared_formula_contains_dataset_identity_lookup:") for item in hardcoded_errors),
        "shared formula with a hard-coded dataset lookup was accepted",
    )
    seed_substitution = json.loads(json.dumps(normalized))
    seed_substitution["candidate_values_by_dataset"] = {"dataset-a": [0.10], "dataset-b": [0.10]}
    seed_substitution["selection_seed_by_dataset"] = {"dataset-a": [0, 1, 2], "dataset-b": [0, 1, 2]}
    seed_substitution["parameter_transfer_contract_sha256"] = PARAMETER.stable_hash(
        {key: value for key, value in seed_substitution.items() if key != "parameter_transfer_contract_sha256"}
    )
    seed_errors = PARAMETER.validate_parameter_transfer_contract(seed_substitution, datasets)["errors"]
    require(
        all(f"innovation_parameter_coverage_incomplete:{dataset_id}" in seed_errors for dataset_id in datasets),
        "three seeds at one value were accepted as parameter coverage",
    )
    absolute_without_scale = transfer("shared_absolute")
    absolute_without_scale.pop("scale_comparability_rationale")
    absolute_without_scale["parameter_transfer_contract_sha256"] = PARAMETER.stable_hash(
        {key: value for key, value in absolute_without_scale.items() if key != "parameter_transfer_contract_sha256"}
    )
    require(
        "shared_absolute_scale_unjustified"
        in PARAMETER.validate_parameter_transfer_contract(absolute_without_scale, datasets)["errors"],
        "shared absolute contract without a scale rationale was accepted",
    )
    profile = {
        "parameter_profile_status": "frozen",
        "calibration_decision_ref": "ledger:decision",
        "calibration_decision_sha256": "d" * 64,
        "parameter_transfer_contract_sha256": normalized["parameter_transfer_contract_sha256"],
        "selected_setting_by_dataset": {"dataset-a": 0.10, "dataset-b": 0.10},
        "realized_value_by_dataset": {"dataset-a": 0.02, "dataset-b": 0.08},
    }
    profile["frozen_parameter_profile_sha256"] = PARAMETER.stable_hash(profile)
    require(PARAMETER.validate_frozen_profile(profile, normalized, datasets)["complete"], "normalized profile must allow formula-derived raw values")
    profile["selected_setting_by_dataset"]["dataset-b"] = 0.05
    profile["frozen_parameter_profile_sha256"] = PARAMETER.stable_hash(
        {key: value for key, value in profile.items() if key != "frozen_parameter_profile_sha256"}
    )
    errors = PARAMETER.validate_frozen_profile(profile, normalized, datasets)["errors"]
    require("shared_mode_profile_must_freeze_one_common_setting" in errors, "different shared settings were accepted")
    calibrated = transfer("dataset_calibrated")
    calibrated["candidate_values_by_dataset"]["dataset-b"] = [0.1, 0.2]
    calibrated["parameter_transfer_contract_sha256"] = PARAMETER.stable_hash(
        {key: value for key, value in calibrated.items() if key != "parameter_transfer_contract_sha256"}
    )
    require(PARAMETER.validate_parameter_transfer_contract(calibrated, datasets)["complete"], "dataset-calibrated ranges should be independent")
    return {
        "case": "transfer_freeze_semantics",
        "shared_setting_mismatch_rejected": True,
        "dataset_identity_lookup_rejected": True,
        "seed_only_parameter_substitution_rejected": True,
    }


def case_ledger_owned_calibration_and_projection() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-calibration-") as temp:
        project = Path(temp)
        base = project / ".autoreskill"
        program_payload = program(project)
        contract = transfer()
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", program_payload)
        write_json(
            base / "planner/tracks/track-a/EXPERIMENT_REVIEW_PACKET.json",
            {
                "track_id": "track-a",
                "claim_scope": "cross_dataset_method",
                "parameter_transfer_contract": contract,
                "parameter_profile_status": "audit_pending",
                "dataset_group_plan": {"required_dataset_ids": ["dataset-a", "dataset-b"]},
            },
        )
        write_json(base / "ideation/IDEA_DECISION_LEDGER.json", {"schema_version": 2, "decisions": []})
        observations = []
        readouts = {
            ("dataset-a", 0.05): 0.2,
            ("dataset-a", 0.10): 0.8,
            ("dataset-b", 0.05): 0.4,
            ("dataset-b", 0.10): 0.7,
        }
        for (dataset_id, setting), readout in readouts.items():
            result_ref = f"analysis/calibration/{dataset_id}-{setting}.json"
            result_path = base / result_ref
            write_json(
                result_path,
                {
                    "dataset_id": dataset_id,
                    "parameter_setting": setting,
                    "mechanism_readout": readout,
                    "metric_provenance": {
                        "selection_metric": "mechanism_readout",
                        "selection_metric_scope": "train_only",
                        "target_labels_used": False,
                        "test_outcome_used": False,
                    },
                },
            )
            observations.append(
                {
                    "dataset_id": dataset_id,
                    "parameter_setting": setting,
                    "realized_parameter_value": setting / (5 if dataset_id == "dataset-a" else 1.25),
                    "seed": 0,
                    "terminal_valid": True,
                    "mechanism_readout": readout,
                    "result_ref": result_ref,
                    "result_sha256": file_sha256(result_path),
                }
            )
        evidence = {
            "track_id": "track-a",
            "parameter_calibration_group_id": "parameter-track-a-r1",
            "parameter_transfer_contract_sha256": contract["parameter_transfer_contract_sha256"],
            "selection_metric_scope": "train_only",
            "observations": observations,
        }
        evidence_path = base / "analysis/CALIBRATION.json"
        write_json(evidence_path, evidence)
        result, code = DECISION.run_calibration(base, evidence_path, True)
        require(code == 0 and result["decision"]["selected_setting_by_dataset"] == {"dataset-a": 0.1, "dataset-b": 0.1}, "ledger calibration did not use robust shared selection")
        process = subprocess.run(
            [
                sys.executable,
                str(MATERIALIZE),
                "--project",
                str(project),
                "--track-id",
                "track-a",
                "--freeze-parameter-profile",
                "--parameter-calibration-group-id",
                "parameter-track-a-r1",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(process.returncode == 0, f"profile projection failed: {process.stderr}")
        profile = json.loads((base / "planner/tracks/track-a/FROZEN_PARAMETER_PROFILE.json").read_text(encoding="utf-8"))
        require(profile["calibration_decision_sha256"] == result["decision"]["decision_sha256"], "profile is not bound to ledger decision")
        first_artifact = base / observations[0]["result_ref"]
        tampered = read_json(first_artifact)
        tampered["mechanism_readout"] = 999.0
        write_json(first_artifact, tampered)
        rejected = DECISION.proposed_calibration_decision(base, evidence)
        require(
            any(item.get("code") == "calibration_result_hash_mismatch" for item in rejected.get("errors", [])),
            "tampered calibration evidence was accepted after its hash changed",
        )
        return {"case": "ledger_owned_calibration_projection", "profile_sha256": profile["frozen_parameter_profile_sha256"]}


def case_batch_materializes_full_probe_group() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-batch-") as temp:
        project = Path(temp)
        base = project / ".autoreskill"
        contract = transfer()
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", program(project))
        review_ref = "planner/tracks/track-a/EXPERIMENT_REVIEW_PACKET.json"
        write_json(
            base / review_ref,
            {
                "track_id": "track-a",
                "claim_role": "method_candidate",
                "claim_scope": "cross_dataset_method",
                "claim_ids": ["claim-a"],
                "dataset": "dataset-a",
                "dataset_group_plan": {
                    "required_dataset_ids": ["dataset-a", "dataset-b"],
                    "baseline_ref_by_dataset": {"dataset-a": "baseline:a", "dataset-b": "baseline:b"},
                },
                "parameter_transfer_contract": contract,
                "parameter_profile_status": "audit_pending",
                "compute_budget": {"gpu_hours": 4.0},
                "execution_route": "local",
                "primary_metric": "score",
                "falsifiers": ["no effect"],
            },
        )
        matrix_row = {
            "track_id": "track-a",
            "idea_id": "idea-a",
            "branch_id": "branch-a",
            "selection_fingerprint": "selection-a",
            "review_packet_ref": review_ref,
            "innovation_packet_ref": "orchestrator/tracks/track-a/INNOVATION_PACKET.json",
            "hypothesis_contract": {"causal_signature": "intervene | mechanism | outcome"},
            "claim_role": "method_candidate",
            "claim_scope": "cross_dataset_method",
            "launch_status": "ready",
            "evidence_tier_ceiling": "pilot_only",
        }
        rows = BATCH.minimum_queue_rows(QUEUE, base, matrix_row, {"idea-a": 4.0})
        require(len(rows) == 4, f"expected two values x two datasets, got {len(rows)}")
        require({row["dataset"] for row in rows} == {"dataset-a", "dataset-b"}, "probe group missed a dataset")
        require(all(row["role"] == "parameter_probe" and row["seed"] == 0 for row in rows), "probe rows changed role or scout seed")
        return {"case": "batch_materializes_full_probe_group", "row_count": len(rows)}


def case_cross_dataset_adjudication() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-decision-") as temp:
        project = Path(temp)
        base = project / ".autoreskill"
        program_payload = program(project)
        contract = transfer()
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", program_payload)
        write_json(
            base / "planner/tracks/track-a/EXPERIMENT_REVIEW_PACKET.json",
            {
                "track_id": "track-a",
                "parameter_transfer_contract": contract,
                "parameter_profile_status": "frozen",
                "frozen_parameter_profile_sha256": "f" * 64,
                "dataset_group_plan": {"required_dataset_ids": ["dataset-a", "dataset-b"]},
            },
        )
        observations = [
            {
                "dataset_id": dataset_id,
                "terminal_valid": True,
                "baseline_valid": True,
                "protocol_valid": True,
                "mechanism_pass": True,
                "support_pass": True,
                "effective_strength_comparable": True,
                "canonical_signed_delta": 0.5,
                "comparison_source": "vs matched reproduced baseline",
                "result_ref": f"result:{dataset_id}",
            }
            for dataset_id in ["dataset-a", "dataset-b"]
        ]
        evidence = {
            "track_id": "track-a",
            "paired_dataset_group_id": "pair-a",
            "program_claim_contract_sha256": program_payload["semantic_sha256"],
            "innovation_parameter_coverage_status": "complete",
            "parameter_profile_status": "frozen",
            "frozen_parameter_profile_sha256": "f" * 64,
            "observations": observations,
        }
        decision = DECISION.proposed_cross_dataset_decision(base, evidence)
        require(decision.get("verdict") == "cross_dataset_supported", f"positive pair was not supported: {decision}")
        observations[1]["support_pass"] = False
        evidence["innovation_parameter_coverage_status"] = "incomplete"
        decision = DECISION.proposed_cross_dataset_decision(base, evidence)
        require(decision.get("verdict") == "innovation_parameter_coverage_incomplete", "missing value coverage was treated as mechanism failure")
        return {"case": "cross_dataset_adjudication", "incomplete_coverage_blocks_refutation": True}


def case_robust_group_hpo_contract() -> dict[str, Any]:
    policy = HPO.default_hpo_search_policy("PARAM")
    policy.update(
        {
            "activation_status": "eligible",
            "sensitivity_question": "Does one shared coupled parameter improve the worst dataset?",
            "eligible_belief_states": ["cross_dataset_supported"],
            "current_belief_state": "cross_dataset_supported",
            "baseline_freeze_or_calibration_ref": "baseline:freeze",
            "remaining_gpu_hours": 8.0,
            "parameter_profile_status": "frozen",
            "dataset_group_hpo": {
                "required_dataset_ids": ["dataset-a", "dataset-b"],
                "stage2_support_ref_by_dataset": {
                    "dataset-a": "stage2:a",
                    "dataset-b": "stage2:b",
                },
                "full_budget_support_ref_by_dataset": {
                    "dataset-a": "stage4:a",
                    "dataset-b": "stage4:b",
                },
                "frozen_parameter_profile_sha256": "f" * 64,
                "parameter_transfer_contract_sha256": "e" * 64,
                "fixed_scout_seed": 0,
                "robust_objective": "maximin_signed_delta",
                "no_regression_constraints_by_dataset": {
                    "dataset-a": 0.0,
                    "dataset-b": 0.0,
                },
                "incomplete_trial_is_infeasible": True,
            },
        }
    )
    policy["trial_budget"]["max_total_gpu_hours"] = 8.0
    policy["search_space_audit"]["dimensions"] = [
        {
            "name": name,
            "type": "log_float",
            "bounds_or_choices": [0.001, 0.1],
            "default_or_prior": 0.01,
            "rationale": "shared mechanism sensitivity",
        }
        for name in ["shared_weight", "shared_temperature", "shared_margin"]
    ]
    packet = {"innovation_search_contract": {"mechanism_type": "PARAM"}, "hpo_search_policy": policy}
    missing: list[str] = []
    warnings: list[str] = []
    HPO.validate_hpo_search_policy(packet, "packet", missing, warnings)
    require(not missing, f"valid robust group HPO was rejected: {missing}")
    policy["trial_budget"]["max_total_gpu_hours"] = 0
    missing = []
    HPO.validate_hpo_search_policy(packet, "packet", missing, [])
    require(any("max_total_gpu_hours" in item for item in missing), "eligible HPO accepted an unbounded GPU-hour budget")
    policy["trial_budget"]["max_total_gpu_hours"] = 8.0
    policy["search_space_audit"]["dimensions"][0]["name"] = "weight_dataset_a"
    missing = []
    HPO.validate_hpo_search_policy(packet, "packet", missing, [])
    require(any("dataset-specific scalar" in item for item in missing), "dataset-specific HPO dimension was accepted")
    return {"case": "robust_group_hpo_contract", "dataset_specific_dimension_rejected": True}


def stage_fixture(project: Path, hpo_eligible: bool) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    base = project / ".autoreskill"
    program_payload = program(project)
    binding = PARAMETER.program_contract_binding(program_payload)
    contract = transfer()
    profile_ref = "planner/tracks/track-a/FROZEN_PARAMETER_PROFILE.json"
    profile = {
        "schema_version": 1,
        "track_id": "track-a",
        "parameter_profile_status": "frozen",
        "parameter_name": contract["parameter_name"],
        "parameter_calibration_group_id": contract["parameter_calibration_group_id"],
        "parameter_transfer_contract_sha256": contract["parameter_transfer_contract_sha256"],
        "calibration_decision_ref": "ledger:calibration-a",
        "calibration_decision_sha256": "c" * 64,
        "selected_setting_by_dataset": {"dataset-a": 0.1, "dataset-b": 0.1},
        "realized_value_by_dataset": {"dataset-a": 0.02, "dataset-b": 0.08},
    }
    profile["frozen_parameter_profile_sha256"] = PARAMETER.stable_hash(profile)
    policy = HPO.default_hpo_search_policy("PARAM")
    if hpo_eligible:
        policy.update(
            {
                "activation_status": "eligible",
                "sensitivity_question": "Which shared mechanism setting maximizes the worst-dataset signed delta?",
                "eligible_belief_states": ["cross_dataset_supported"],
                "current_belief_state": "cross_dataset_supported",
                "baseline_freeze_or_calibration_ref": "baseline:matched",
                "remaining_gpu_hours": 16.0,
                "parameter_profile_status": "frozen",
                "dataset_group_hpo": {
                    "required_dataset_ids": ["dataset-a", "dataset-b"],
                    "stage2_support_ref_by_dataset": {"dataset-a": "stage2:a", "dataset-b": "stage2:b"},
                    "full_budget_support_ref_by_dataset": {"dataset-a": "stage4:a", "dataset-b": "stage4:b"},
                    "frozen_parameter_profile_sha256": profile["frozen_parameter_profile_sha256"],
                    "parameter_transfer_contract_sha256": contract["parameter_transfer_contract_sha256"],
                    "fixed_scout_seed": 0,
                    "robust_objective": "maximin_signed_delta",
                    "no_regression_constraints_by_dataset": {"dataset-a": 0.0, "dataset-b": 0.0},
                    "incomplete_trial_is_infeasible": True,
                },
            }
        )
        policy["trial_budget"]["max_total_gpu_hours"] = 16.0
        policy["trial_budget"]["max_full_budget_trials"] = 2
        policy["search_space_audit"]["dimensions"] = [
            {
                "name": name,
                "type": "log_float",
                "bounds_or_choices": [0.001, 0.1],
                "default_or_prior": 0.01,
                "rationale": "shared mechanism sensitivity",
            }
            for name in ["shared_weight", "shared_temperature", "shared_margin"]
        ]
    review_ref = "planner/tracks/track-a/EXPERIMENT_REVIEW_PACKET.json"
    review = {
        "track_id": "track-a",
        "claim_role": "method_candidate",
        "claim_scope": "cross_dataset_method",
        "claim_ids": ["claim-a"],
        "dataset": "dataset-a",
        "dataset_group_plan": {
            "required_dataset_ids": ["dataset-a", "dataset-b"],
            "baseline_ref_by_dataset": {"dataset-a": "baseline:a", "dataset-b": "baseline:b"},
        },
        "parameter_transfer_contract": contract,
        "parameter_role_inventory": [
            {
                "parameter_name": contract["parameter_name"],
                "parameter_role": "innovation_load_bearing",
                "parameter_transfer_contract_sha256": contract["parameter_transfer_contract_sha256"],
            }
        ],
        "parameter_profile_status": "frozen",
        "frozen_parameter_profile_ref": profile_ref,
        "frozen_parameter_profile_sha256": profile["frozen_parameter_profile_sha256"],
        "method_formula_sha256": "m" * 64,
        "compute_budget": {
            "gpu_hours": 8.0,
            "full_budget_gpu_hours_by_dataset": {"dataset-a": 4.0, "dataset-b": 4.0},
        },
        "execution_route": "local",
        "primary_metric": "canonical_signed_delta",
        "baseline_training_protocol": "matched training",
        "baseline_eval_protocol": "matched evaluation",
        "data_split": "frozen split",
        "falsifiers": ["worst-dataset signed delta is nonpositive"],
        "stability_seed_policy": {"planned_random_seeds": [0, 1]},
        "hpo_search_policy": policy,
        **binding,
    }
    matrix_row = {
        "track_id": "track-a",
        "idea_id": "idea-a",
        "branch_id": "branch-a",
        "track_role": "primary",
        "selected_for_review": True,
        "planning_admitted": True,
        "idea_lifecycle_status": "selected_primary",
        "selection_fingerprint": "selection-a",
        "review_packet_ref": review_ref,
        "innovation_packet_ref": "orchestrator/tracks/track-a/INNOVATION_PACKET.json",
        "hypothesis_contract": {
            "causal_signature": "intervene | mechanism | cross-dataset outcome",
            "predicted_pattern": "both required datasets improve",
            "falsifier": "one required dataset regresses",
            "belief_state": "cross_dataset_supported",
            "outcome_routes": {
                "positive": "advance",
                "negative": "retire",
                "inconclusive": "repair",
                "invalid": "repair",
            },
        },
        "claim_role": "method_candidate",
        "claim_scope": "cross_dataset_method",
        "launch_status": "ready",
        "evidence_tier_ceiling": "claim_eligible",
        **binding,
    }
    write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", program_payload)
    write_json(base / profile_ref, profile)
    write_json(base / review_ref, review)
    write_json(
        base / "orchestrator/TRACK_PLAN_MATRIX.json",
        {"schema_version": 2, "selection_fingerprint": "selection-a", "tracks": [matrix_row]},
    )
    stage2_rows = BATCH.minimum_queue_rows(QUEUE, base, matrix_row, {"idea-a": 8.0})
    for row in stage2_rows:
        row["status"] = "terminal_positive"
        row.setdefault("evidence_paths", []).append(f"analysis/stage2/{row['dataset_id']}.json")
    group_id = str(stage2_rows[0]["paired_dataset_group_id"])
    queue = {
        "schema_version": 2,
        "queue_revision": 0,
        **binding,
        "policy": {
            "portfolio_capacity_target": 4,
            "method_portfolio_target": 2,
            "max_random_seed_count": 3,
            "portfolio_gpu_hour_budget": 96.0,
        },
        "rows": stage2_rows,
        "decision_log": [],
    }
    ledger = {
        "schema_version": 2,
        "decisions": [],
        "experiment_decisions": [],
        "cross_dataset_decisions": [
            {
                "decision_id": "cross-decision-a",
                "track_id": "track-a",
                "paired_dataset_group_id": group_id,
                "verdict": "cross_dataset_supported",
                "aggregate_ref": "analysis/cross-dataset-a.json",
            }
        ],
    }
    write_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", queue)
    write_json(base / "ideation/IDEA_DECISION_LEDGER.json", ledger)
    return base, queue, ledger


def apply_stage_materializer(project: Path, revision: int) -> dict[str, Any]:
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "stage_transition_materialize.py"),
            "--project",
            str(project),
            "--expected-queue-revision",
            str(revision),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(process.returncode == 0, f"stage materialization failed: {process.stdout} {process.stderr}")
    return json.loads(process.stdout)


def mark_full_budget_supported(base: Path, queue: dict[str, Any], ledger: dict[str, Any]) -> None:
    decisions = ledger.setdefault("experiment_decisions", [])
    for row in queue["rows"]:
        if row.get("validation_stage") not in {3, 4}:
            continue
        row["status"] = "terminal_positive"
        decisions.append(
            {
                "decision_id": f"decision-{row['id']}",
                "queue_row_id": row["id"],
                "track_id": "track-a",
                "outcome_class": "valid_positive_candidate",
            }
        )
    queue["queue_revision"] = int(queue.get("queue_revision") or 0) + 1
    write_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", queue)
    write_json(base / "ideation/IDEA_DECISION_LEDGER.json", ledger)


def case_stage_transition_and_confirmation() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-stages-") as temp:
        project = Path(temp)
        base, _, _ = stage_fixture(project, hpo_eligible=False)
        first = apply_stage_materializer(project, 0)
        require(len(first.get("proposed_row_ids") or []) == 2, "Stage 3/4 were not materialized together")
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")
        ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
        require(
            {row.get("validation_stage") for row in queue["rows"] if row.get("validation_stage") in {3, 4}} == {3, 4},
            "full-budget primary and contrast stages are incomplete",
        )
        mark_full_budget_supported(base, queue, ledger)
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")
        second = apply_stage_materializer(project, int(queue["queue_revision"]))
        require(len(second.get("proposed_row_ids") or []) == 4, "Stage 6 did not materialize the full dataset-by-arm matrix")
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")
        confirmation = [row for row in queue["rows"] if row.get("validation_stage") == 6]
        require(
            {(row["dataset_id"], row["confirmation_arm"]) for row in confirmation}
            == {("dataset-a", "baseline"), ("dataset-a", "method"), ("dataset-b", "baseline"), ("dataset-b", "method")},
            "crossed confirmation cells are incomplete",
        )
        checked = QUEUE.validate_queue(queue, project)
        require(checked["ok"], f"materialized Stage 3-6 queue is invalid: {checked['errors']}")
        return {"case": "stage_transition_and_confirmation", "stage34_rows": 2, "stage6_rows": 4}


def case_group_hpo_runner() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-hpo-runner-") as temp:
        project = Path(temp)
        base, _, _ = stage_fixture(project, hpo_eligible=True)
        apply_stage_materializer(project, 0)
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")
        ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
        mark_full_budget_supported(base, queue, ledger)
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")
        config = {"shared_weight": 0.01, "shared_temperature": 0.01, "shared_margin": 0.01}
        review_path = base / "planner/tracks/track-a/EXPERIMENT_REVIEW_PACKET.json"
        review = read_json(review_path)
        review["hpo_search_policy"]["trial_budget"]["max_total_gpu_hours"] = 7.0
        review["hpo_search_policy"]["remaining_gpu_hours"] = 7.0
        write_json(review_path, review)
        over_budget_rows, over_budget_detail = GROUP_HPO.build_trial_rows(base, queue, "track-a", config, "r2")
        require(
            not over_budget_rows and over_budget_detail.get("reason") == "hpo_gpu_hour_budget_exhausted",
            "grouped HPO ignored the cost of all required dataset legs",
        )
        review["hpo_search_policy"]["trial_budget"]["max_total_gpu_hours"] = 16.0
        review["hpo_search_policy"]["remaining_gpu_hours"] = 16.0
        write_json(review_path, review)
        try:
            GROUP_HPO.build_trial_rows(base, queue, "track-a", {"shared_weight": 0.01}, "r2")
        except RuntimeError as exc:
            require("exactly match declared dimensions" in str(exc), "invalid grouped HPO configuration failed unclearly")
        else:
            raise AssertionError("incomplete grouped HPO configuration was accepted")
        rows, _ = GROUP_HPO.build_trial_rows(base, queue, "track-a", config, "r2")
        require(len(rows) == 2, "grouped HPO did not create one row per required dataset")
        for row in rows:
            row["status"] = "terminal_positive"
        queue["rows"].extend(rows)
        queue["queue_revision"] += 1
        first = rows[0]
        first_result_ref = f"analysis/results/{first['id']}.json"
        write_json(
            base / first_result_ref,
            {
                "dataset_id": first["dataset_id"],
                "dataset_group_trial_id": first["dataset_group_trial_id"],
                "dataset_group_trial_config_sha256": first["dataset_group_trial_config_sha256"],
                "terminal_valid": True,
                "protocol_valid": True,
                "canonical_signed_delta": 0.3,
                "comparison_source": "vs matched reproduced baseline",
            },
        )
        first.setdefault("evidence_paths", []).append(first_result_ref)
        incomplete = GROUP_HPO.aggregate_group(base, rows)
        require(
            incomplete["eligible_for_optimizer"] is False and incomplete["robust_objective_value"] is None,
            "incomplete dataset group emitted an optimizer objective",
        )
        blocked_rows, blocked_detail = GROUP_HPO.build_trial_rows(base, queue, "track-a")
        require(
            not blocked_rows and blocked_detail.get("reason") == "incomplete_group_requires_repair_or_adjudication",
            "terminal incomplete HPO group did not block new search work",
        )
        second = rows[1]
        second_result_ref = f"analysis/results/{second['id']}.json"
        write_json(
            base / second_result_ref,
            {
                "dataset_id": second["dataset_id"],
                "dataset_group_trial_id": second["dataset_group_trial_id"],
                "dataset_group_trial_config_sha256": second["dataset_group_trial_config_sha256"],
                "terminal_valid": True,
                "protocol_valid": True,
                "canonical_signed_delta": 0.1,
                "comparison_source": "vs matched reproduced baseline",
            },
        )
        second.setdefault("evidence_paths", []).append(second_result_ref)
        write_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", queue)
        complete = GROUP_HPO.aggregate_group(base, rows)
        require(
            complete["eligible_for_optimizer"] is True and complete["robust_objective_value"] == 0.1,
            "grouped HPO did not use the maximin signed-delta objective",
        )
        try:
            GROUP_HPO.reconcile(base, queue, "track-a", False, True)
        except RuntimeError as exc:
            require("provide --stop-reason" in str(exc), "premature HPO finalization failed unclearly")
        else:
            raise AssertionError("HPO finalized before budget exhaustion or an explicit stop")
        reconciled = GROUP_HPO.reconcile(base, queue, "track-a", True, True, "fixture bounded stop")
        require(len(reconciled["decisions"]) == 1, "complete full-resource grouped trial was not selected")
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")
        applied = apply_stage_materializer(project, int(queue["queue_revision"]))
        require(len(applied.get("proposed_row_ids") or []) == 4, "HPO decision did not unlock Stage 6")
        return {
            "case": "group_hpo_runner",
            "incomplete_group_excluded": True,
            "robust_objective_value": complete["robust_objective_value"],
        }


def case_group_hpo_promotion_cap() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-hpo-promotion-") as temp:
        project = Path(temp)
        base, _, _ = stage_fixture(project, hpo_eligible=True)
        apply_stage_materializer(project, 0)
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")
        ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
        mark_full_budget_supported(base, queue, ledger)
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json")

        def complete(rows: list[dict[str, Any]], delta: float) -> None:
            for row in rows:
                row["status"] = "terminal_positive"
                result_ref = f"analysis/results/{row['id']}.json"
                write_json(
                    base / result_ref,
                    {
                        "dataset_id": row["dataset_id"],
                        "dataset_group_trial_id": row["dataset_group_trial_id"],
                        "dataset_group_trial_config_sha256": row["dataset_group_trial_config_sha256"],
                        "terminal_valid": True,
                        "protocol_valid": True,
                        "canonical_signed_delta": delta,
                        "comparison_source": "vs matched reproduced baseline",
                    },
                )
                row.setdefault("evidence_paths", []).append(result_ref)
            queue["rows"].extend(rows)

        configs = [
            {"shared_weight": value, "shared_temperature": value, "shared_margin": value}
            for value in [0.01, 0.02, 0.03]
        ]
        for index, config in enumerate(configs):
            rows, _ = GROUP_HPO.build_trial_rows(base, queue, "track-a", config, "r0")
            require(len(rows) == 2, "failed to materialize a complete scout group")
            complete(rows, 0.3 - index * 0.1)
        policy = read_json(base / "planner/tracks/track-a/EXPERIMENT_REVIEW_PACKET.json")["hpo_search_policy"]
        first_promotion = GROUP_HPO.next_trial_spec(base, queue, "track-a", policy)
        require(
            first_promotion is not None
            and first_promotion["rung"]["name"] == "r1"
            and first_promotion["configuration"] == configs[0],
            "Hyperband did not promote the best eligible scout",
        )
        promoted_rows, _ = GROUP_HPO.build_trial_rows(base, queue, "track-a", configs[0], "r1")
        complete(promoted_rows, 0.3)
        after_top_k = GROUP_HPO.next_trial_spec(base, queue, "track-a", policy)
        require(
            after_top_k is not None and after_top_k["rung"]["name"] == "r0",
            "grouped HPO promoted more than the registered top-k from one scout cohort",
        )
        return {"case": "group_hpo_promotion_cap", "promoted_from_three": 1}


def case_prelaunch_parameter_inventory_binding() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-prelaunch-") as temp:
        project = Path(temp)
        payload = program(project)
        write_json(project / ".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json", payload)
        contract = transfer()
        packet = {
            "claim_role": "method_candidate",
            "claim_scope": "cross_dataset_method",
            "method_formula_sha256": "m" * 64,
            "parameter_transfer_contract": contract,
            "parameter_role_inventory": [
                {
                    "parameter_name": contract["parameter_name"],
                    "parameter_role": "innovation_load_bearing",
                    "parameter_transfer_contract_sha256": "0" * 64,
                }
            ],
            **PARAMETER.program_contract_binding(payload),
        }
        missing: list[str] = []
        PRELAUNCH.validate_cross_dataset_parameter_contract(packet, str(project), missing, [])
        require(
            any("load-bearing inventory hash" in item for item in missing),
            "prelaunch accepted a load-bearing inventory that was not bound to the transfer contract",
        )
        return {"case": "prelaunch_parameter_inventory_binding", "mismatched_hash_rejected": True}


def case_crossed_confirmation_matrix() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-cross-confirmation-") as temp:
        project = Path(temp)
        base = project / ".autoreskill"
        program_payload = program(project)
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", program_payload)
        binding = PARAMETER.program_contract_binding(program_payload)

        def row(dataset_id: str, arm: str) -> dict[str, Any]:
            return {
                "id": f"confirm-{dataset_id}-{arm}",
                "priority": 50,
                "status": "ready",
                "role": "stability",
                "dataset": dataset_id,
                "dataset_id": dataset_id,
                "next_action": "paired confirmation",
                "updated_at": "2026-07-13T00:00:00+00:00",
                "validation_stage": 6,
                "validation_prerequisites": ["cross_dataset_support"],
                "baseline_freeze_ref": "baseline:freeze",
                "comparison_source": "vs matched reproduced baseline",
                "experiment_family_id": "family-a",
                "replication_group_id": "replication-a",
                "crossed_confirmation_group_id": "confirmation-a",
                "registered_seed_set": [0, 1],
                "seeds": [0, 1],
                "seed_count": 2,
                "confirmation_arm": arm,
                "claim_scope": "cross_dataset_method",
                "claim_role": "method_candidate",
                "parameter_profile_status": "frozen",
                "parameter_transfer_contract_sha256": "e" * 64,
                "frozen_parameter_profile_ref": "planner/tracks/track-a/FROZEN_PARAMETER_PROFILE.json",
                "frozen_parameter_profile_sha256": "f" * 64,
                **binding,
            }

        rows = [
            row("dataset-a", "baseline"),
            row("dataset-a", "method"),
            row("dataset-b", "baseline"),
        ]
        queue = {
            "schema_version": 2,
            "queue_revision": 0,
            **binding,
            "policy": {
                "portfolio_capacity_target": 4,
                "method_portfolio_target": 2,
                "max_random_seed_count": 3,
                "portfolio_gpu_hour_budget": 96.0,
            },
            "rows": rows,
        }
        checked = QUEUE.validate_queue(queue, project)
        require(
            any("incomplete dataset-by-seed-by-arm matrix" in item for item in checked["errors"]),
            "incomplete crossed confirmation matrix was accepted",
        )
        queue["rows"].append(row("dataset-b", "method"))
        checked = QUEUE.validate_queue(queue, project)
        require(
            not any("crossed confirmation confirmation-a" in item for item in checked["errors"]),
            f"complete crossed confirmation matrix was rejected: {checked['errors']}",
        )
        return {"case": "crossed_confirmation_matrix", "complete_cells_required": True}


def main() -> None:
    results = [
        case_program_contract_cas(),
        case_rollout_modes(),
        case_transfer_freeze_semantics(),
        case_ledger_owned_calibration_and_projection(),
        case_batch_materializes_full_probe_group(),
        case_cross_dataset_adjudication(),
        case_robust_group_hpo_contract(),
        case_prelaunch_parameter_inventory_binding(),
        case_stage_transition_and_confirmation(),
        case_group_hpo_runner(),
        case_group_hpo_promotion_cap(),
        case_crossed_confirmation_matrix(),
    ]
    print(json.dumps({"ok": True, "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
