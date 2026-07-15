#!/usr/bin/env python3
"""Focused fixtures for replacement-program replenishment recovery."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import program_claim_contract as CONTRACT  # noqa: E402
import research_decision as DECISION  # noqa: E402


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GOAL_TICK = load_module("replenishment_recovery_goal_tick", SCRIPTS / "goal_tick.py")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_json(command: list[str], *, expect: int = 0) -> dict[str, Any]:
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != expect:
        raise AssertionError(
            {"command": command, "expected": expect, "actual": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        )
    return json.loads(completed.stdout)


def intervention_payload(basis_id: str, maximum: int = 8) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "budget_authorized_pending_replacement_contract_review",
        "request_id": f"intervention-{basis_id}",
        "basis_decision_id": basis_id,
        "requested_max_targeted_replenishments": maximum,
        "authorization": {
            "source": "direct_user_instruction",
            "authorized_at": "2026-07-15T00:00:00+00:00",
            "max_targeted_replenishments": maximum,
        },
    }


def old_route(basis_id: str, *, terminal_for_project: bool = False) -> dict[str, Any]:
    return {
        "decision_id": basis_id,
        "status": "core_hypotheses_refuted",
        "terminal_for_track": True,
        "terminal_for_project": terminal_for_project,
        "track_id": "old-track",
        "transition": "RETIRE_TRACK",
        "target_stage": "idea_gate",
        "improvement_claim_allowed": False,
        "evidence_ref": "analysis/old-negative.json",
    }


def replacement_contract(root: Path, basis_id: str, maximum: int = 8) -> dict[str, Any]:
    payload = CONTRACT.default_contract(root)
    payload.pop("semantic_sha256", None)
    payload.update(
        {
            "contract_id": "program-claim-fixture-replacement-r1",
            "contract_status": "active",
            "enforcement_mode": "enforced",
            "claim_scope": "cross_dataset_method",
            "claim_target": "A changed-basis learner intervention improves both required datasets.",
            "replacement_basis_decision_id": basis_id,
            "unresolved_paper_decision_id": "paper-decision-fixture-r1",
            "target_datasets": [
                {
                    "dataset_id": "dataset-a",
                    "role": "primary",
                    "required": True,
                    "canonical_metric": "all_accuracy",
                    "metric_direction": "higher",
                    "paper_report_alignment": "aligned",
                    "matched_baseline_ref": "baseline/a.json",
                },
                {
                    "dataset_id": "dataset-b",
                    "role": "contrast",
                    "required": True,
                    "canonical_metric": "all_accuracy",
                    "metric_direction": "higher",
                    "paper_report_alignment": "aligned",
                    "matched_baseline_ref": "baseline/b.json",
                },
            ],
            "source_refs": [
                "control/UNRESOLVED_PAPER_DECISION.fixture.json",
                "control/REPLENISHMENT_INTERVENTION_REQUEST.json",
                "reviewer/PROGRAM_CLAIM_CONTRACT_REPLACEMENT_REVIEW.fixture.json",
                "analysis/old-negative.json",
            ],
        }
    )
    payload["promotion_rule"]["worst_dataset_floor_by_dataset"] = {
        "dataset-a": 0.0,
        "dataset-b": 0.0,
    }
    payload["search_budget"]["max_targeted_replenishments"] = maximum
    return CONTRACT.bind_hash(payload)


def write_replacement_authorities(root: Path, contract: dict[str, Any], basis_id: str, authorization_max: int = 8) -> None:
    base = root / ".autoreskill"
    write_json(base / "control/REPLENISHMENT_INTERVENTION_REQUEST.json", intervention_payload(basis_id, authorization_max))
    write_json(
        base / "control/UNRESOLVED_PAPER_DECISION.fixture.json",
        {"schema_version": 1, "decision_id": "paper-decision-fixture-r1", "status": "unresolved"},
    )
    write_json(
        base / "reviewer/PROGRAM_CLAIM_CONTRACT_REPLACEMENT_REVIEW.fixture.json",
        {
            "schema_version": 1,
            "reviewed_semantic_sha256": contract["semantic_sha256"],
            "cross_review": {"verdict": "APPROVE_CONTRACT_ACTIVATION"},
        },
    )
    write_json(base / "analysis/old-negative.json", {"verdict": "negative"})


def write_common_project(root: Path, basis_id: str, *, terminal_for_project: bool = False) -> None:
    base = root / ".autoreskill"
    write_json(
        base / "goal_state.json",
        {
            "schema_version": 1,
            "project_root": str(root),
            "goal": "Produce a paper from a bounded changed-basis search.",
            "stage": "idea_gate",
            "owner": "WorkflowGuard",
            "next_action": "request_reviewed_replacement_contract",
            "blocking_reason": None,
            "autonomy_level": "full_auto_bounded",
            "iteration": 1,
        },
    )
    write_json(
        base / "autopilot_policy.json",
        {"autonomy_level": "full_auto_bounded", "allow_autonomous_candidate_replenishment": True},
    )
    write_json(
        base / "ideation/IDEA_DECISION_LEDGER.json",
        {
            "schema_version": 2,
            "program_scientific_status": "refuted",
            "program_route_decision": old_route(basis_id, terminal_for_project=terminal_for_project),
            "selected_idea_id": "old-idea",
            "selected_primary_idea_id": "old-idea",
            "selected_track_id": "old-track",
            "selection_fingerprint": "old-selection",
            "active_scientific_portfolio": {
                "primary": "old-idea",
                "alternates": ["old-alt"],
                "shortlist_only": ["stale-shortlist"],
                "diagnostic_only": [],
                "retired": ["older-retired"],
            },
        },
    )
    write_json(
        base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
        {
            "selection_revision": "old-selection",
            "selection_fingerprint": "old-selection",
            "selected_primary_idea_id": "old-idea",
            "shortlisted_idea_ids": ["stale-shortlist"],
        },
    )
    write_json(
        base / "experiment/NEXT_EXPERIMENT_QUEUE.json",
        {
            "schema_version": 2,
            "queue_revision": 1,
            "policy": {"portfolio_capacity_target": 4, "method_portfolio_target": 3},
            "rows": [
                {
                    "id": "audit-row",
                    "status": "running",
                    "launch_mode": "monitor_only",
                    "program_decision_blocking": False,
                }
            ],
        },
    )
    write_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {"tracks": []})


def test_authorized_recovery_and_idempotence() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    basis_id = "program-route-old-negative"
    with tempfile.TemporaryDirectory(prefix="autoreskill-replenishment-recovery-") as tmp:
        root = Path(tmp)
        base = root / ".autoreskill"
        write_common_project(root, basis_id)
        superseded = replacement_contract(root, basis_id)
        superseded["contract_status"] = "superseded"
        superseded["enforcement_mode"] = "legacy"
        superseded = CONTRACT.bind_hash(superseded)
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", superseded)
        write_json(base / "control/REPLENISHMENT_INTERVENTION_REQUEST.json", intervention_payload(basis_id, 8))

        recovery = DECISION.program_recovery_status(base)
        if (recovery.get("class"), recovery.get("action"), recovery.get("phase")) != (
            "auto_repairable",
            "recover_replenishment_route",
            "review_and_commit_replacement_contract",
        ):
            raise AssertionError(recovery)
        tick = run_json([sys.executable, str(SCRIPTS / "goal_tick.py"), "--project", str(root)])
        if tick.get("action") != "queued_repair_handoff" or tick.get("job", {}).get("action") != "recover_replenishment_route":
            raise AssertionError(tick)
        spec = GOAL_TICK.execution_spec(
            "idea_gate", read_json(base / "goal_state.json"), {}, {"action": "recover_replenishment_route"}, base
        )
        if "Do not infer or raise a budget" not in str(spec.get("goal") or "") or spec.get("mcp_calls"):
            raise AssertionError(spec)
        results.append({"case": "authorized_superseded_route_queues_local_recovery", "ok": True})

        active = replacement_contract(root, basis_id)
        write_replacement_authorities(root, active, basis_id)
        candidate_path = base / "control/PROGRAM_CLAIM_CONTRACT_REPLACEMENT_CANDIDATE.json"
        write_json(candidate_path, active)
        committed = run_json(
            [
                sys.executable,
                str(SCRIPTS / "program_claim_contract.py"),
                "commit",
                "--project",
                str(root),
                "--input",
                str(candidate_path),
            ]
        )
        if committed.get("ok") is not True or committed.get("replacement_authority", {}).get("complete") is not True:
            raise AssertionError(committed)
        active = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json")
        authority = CONTRACT.validate_replacement_authority(root, active)
        if not authority.get("complete"):
            raise AssertionError(authority)
        proposal = DECISION.program_revision_activation_proposal(base)
        if not proposal.get("complete") or proposal.get("idempotent"):
            raise AssertionError(proposal)
        first, first_code = DECISION.run_program_revision_activation(base, True)
        second, second_code = DECISION.run_program_revision_activation(base, True)
        if first_code or second_code or second.get("idempotent") is not True:
            raise AssertionError({"first": first, "second": second})
        ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
        if ledger.get("program_scientific_status") != "unresolved" or ledger.get("program_route_decision") is not None:
            raise AssertionError(ledger)
        if len(ledger.get("program_revision_history") or []) != 1:
            raise AssertionError("activation duplicated or failed to archive the old route")
        if ledger.get("active_scientific_portfolio", {}).get("legacy_quarantined") != [
            "old-idea",
            "old-alt",
            "stale-shortlist",
        ]:
            raise AssertionError(ledger.get("active_scientific_portfolio"))
        results.append({"case": "program_revision_activation_archives_once", "ok": True})

        frontier = {
            "method_admission_deficit": 3,
            "portfolio_admission_deficit": 4,
            "method_fillable_candidate_ids": ["stale-shortlist"],
            "selection_revision": "old-selection",
            "fresh_fitting_idle_slots": 0,
        }
        replenishment = DECISION.replenishment_proposal(base, frontier)
        if not replenishment.get("complete"):
            raise AssertionError(replenishment)
        if not any("stale or unbound" in warning for warning in replenishment.get("warnings") or []):
            raise AssertionError(replenishment)
        if DECISION.decision_bearing_live_rows(base):
            raise AssertionError("monitor_only row was treated as decision-bearing")
        first_event, event_code = DECISION.run_replenishment(base, True)
        if event_code or not first_event.get("complete"):
            raise AssertionError(first_event)
        duplicate, duplicate_code = DECISION.run_replenishment(base, False)
        if duplicate_code != 1 or duplicate.get("idempotent") is not True:
            raise AssertionError(duplicate)
        ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
        if len(ledger.get("replenishment_events") or []) != 1:
            raise AssertionError(ledger.get("replenishment_events"))
        results.append({"case": "no_gpu_snapshot_monitor_only_and_stale_supply_do_not_block", "ok": True})

        recovery = DECISION.program_recovery_status(base, frontier)
        if recovery.get("phase") != "materialize_candidate_supply_from_existing_event":
            raise AssertionError(recovery)
        pool = {
            "program_revision_id": ledger["program_revision_id"],
            "program_claim_contract_sha256": active["semantic_sha256"],
            "ideas": [{"id": f"new-candidate-{index}"} for index in range(1, 9)],
        }
        write_json(base / "ideation/EXPERIMENT_IDEA_POOL.json", pool)
        scorecard = read_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json")
        scorecard.update(
            {
                "program_revision_id": ledger["program_revision_id"],
                "program_claim_contract_sha256": active["semantic_sha256"],
                "shortlisted_idea_ids": ["new-candidate-1", "new-candidate-2", "new-candidate-3"],
                "selected_primary_idea_id": None,
            }
        )
        write_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", scorecard)
        current = DECISION.program_recovery_status(base, {**frontier, "method_fillable_candidate_ids": ["new-candidate-1"]})
        if current.get("applicable") is not False or current.get("phase") != "current_candidate_supply_available":
            raise AssertionError(current)
        results.append({"case": "current_revision_supply_closes_recovery", "ok": True})

        ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json")
        ledger["replenishment_events"][-1].update({"cards_generated": 8, "shortlisted_candidates": 4})
        write_json(base / "ideation/IDEA_DECISION_LEDGER.json", ledger)
        scorecard["selected_primary_idea_id"] = "new-candidate-1"
        scorecard["shortlisted_idea_ids"] = ["new-candidate-1", "new-candidate-2"]
        write_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", scorecard)
        post_selection = DECISION.program_recovery_status(
            base, {**frontier, "method_fillable_candidate_ids": ["new-candidate-2"]}
        )
        if post_selection.get("applicable") is not False:
            raise AssertionError(post_selection)
        results.append({"case": "audited_preselection_shape_survives_postselection_narrowing", "ok": True})
    return results


def test_negative_authority_cases() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    basis_id = "program-route-old-negative"
    with tempfile.TemporaryDirectory(prefix="autoreskill-replenishment-no-authority-") as tmp:
        root = Path(tmp)
        base = root / ".autoreskill"
        write_common_project(root, basis_id)
        contract = replacement_contract(root, basis_id)
        contract["contract_status"] = "superseded"
        contract["enforcement_mode"] = "legacy"
        contract = CONTRACT.bind_hash(contract)
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", contract)
        recovery = DECISION.program_recovery_status(base)
        if (recovery.get("class"), recovery.get("action")) != (
            "hard_stop",
            "request_replenishment_budget_authorization",
        ):
            raise AssertionError(recovery)
        results.append({"case": "missing_direct_authority_stays_hard_stop", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-replenishment-project-terminal-") as tmp:
        root = Path(tmp)
        base = root / ".autoreskill"
        write_common_project(root, basis_id, terminal_for_project=True)
        contract = replacement_contract(root, basis_id)
        contract["contract_status"] = "superseded"
        contract["enforcement_mode"] = "legacy"
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", CONTRACT.bind_hash(contract))
        write_json(base / "control/REPLENISHMENT_INTERVENTION_REQUEST.json", intervention_payload(basis_id, 8))
        recovery = DECISION.program_recovery_status(base)
        if (recovery.get("class"), recovery.get("action")) != ("hard_stop", "conclude_program"):
            raise AssertionError(recovery)
        results.append({"case": "project_terminal_route_cannot_reopen", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-replenishment-blocked-authority-") as tmp:
        root = Path(tmp)
        base = root / ".autoreskill"
        write_common_project(root, basis_id)
        contract = replacement_contract(root, basis_id)
        contract["contract_status"] = "superseded"
        contract["enforcement_mode"] = "legacy"
        write_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", CONTRACT.bind_hash(contract))
        intervention = intervention_payload(basis_id, 8)
        intervention["status"] = "blocked_manual_review"
        write_json(base / "control/REPLENISHMENT_INTERVENTION_REQUEST.json", intervention)
        recovery = DECISION.program_recovery_status(base)
        if recovery.get("class") != "hard_stop":
            raise AssertionError(recovery)
        results.append({"case": "blocked_authority_stays_hard_stop", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-replenishment-over-cap-") as tmp:
        root = Path(tmp)
        contract = replacement_contract(root, basis_id, 8)
        write_replacement_authorities(root, contract, basis_id, authorization_max=1)
        authority = CONTRACT.validate_replacement_authority(root, contract)
        if authority.get("complete") or not any("exceeds" in error for error in authority.get("errors") or []):
            raise AssertionError(authority)
        candidate_path = root / ".autoreskill/control/PROGRAM_CLAIM_CONTRACT_REPLACEMENT_CANDIDATE.json"
        write_json(candidate_path, contract)
        rejected = run_json(
            [
                sys.executable,
                str(SCRIPTS / "program_claim_contract.py"),
                "commit",
                "--project",
                str(root),
                "--input",
                str(candidate_path),
            ],
            expect=1,
        )
        if rejected.get("ok") is not False or "exceeds direct user authorization" not in str(rejected.get("error") or ""):
            raise AssertionError(rejected)
        results.append({"case": "replacement_contract_cannot_exceed_user_cap", "ok": True})

    with tempfile.TemporaryDirectory(prefix="autoreskill-replenishment-review-hash-") as tmp:
        root = Path(tmp)
        contract = replacement_contract(root, basis_id, 8)
        write_replacement_authorities(root, contract, basis_id, authorization_max=8)
        review_path = root / ".autoreskill/reviewer/PROGRAM_CLAIM_CONTRACT_REPLACEMENT_REVIEW.fixture.json"
        review = read_json(review_path)
        review["reviewed_semantic_sha256"] = "0" * 64
        write_json(review_path, review)
        authority = CONTRACT.validate_replacement_authority(root, contract)
        if authority.get("complete") or not any("approving review" in error for error in authority.get("errors") or []):
            raise AssertionError(authority)
        results.append({"case": "replacement_review_hash_must_match", "ok": True})
    return results


def main() -> None:
    results = test_authorized_recovery_and_idempotence() + test_negative_authority_cases()
    print(json.dumps({"ok": True, "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
