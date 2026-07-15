#!/usr/bin/env python3
"""Offline acceptance fixtures for innovation-throughput and admission hardening."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT.parent
QUEUE_PATH = ROOT / "scripts/experiment_next_actions.py"
PASSPORT_PATH = ROOT / "scripts/resource_passport.py"
BATCH_PATH = ROOT / "scripts/portfolio_batch.py"
EFFICIENCY_PATH = ROOT / "scripts/research_efficiency_report.py"
GLOBAL_PAYLOAD_PATH = SKILLS / "autoreskill-run-experiment/scripts/global_admission_automation_payload.py"
RESEARCH_DECISION_PATH = ROOT / "scripts/research_decision.py"
CONTRACT_LINT_PATH = ROOT / "scripts/contract_lint.py"


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUEUE = load("throughput_queue", QUEUE_PATH)
PASSPORT = load("throughput_passport", PASSPORT_PATH)
BATCH = load("throughput_batch", BATCH_PATH)
EFFICIENCY = load("throughput_efficiency", EFFICIENCY_PATH)
GLOBAL_PAYLOAD = load("throughput_global_payload", GLOBAL_PAYLOAD_PATH)
RESEARCH_DECISION = load("throughput_research_decision", RESEARCH_DECISION_PATH)
CONTRACT_LINT = load("throughput_contract_lint", CONTRACT_LINT_PATH)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_json(command: list[str], expected: int = 0) -> dict[str, Any]:
    process = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if process.returncode != expected:
        raise AssertionError(
            f"unexpected exit {process.returncode}, expected {expected}: {' '.join(command)}\n"
            f"stdout={process.stdout}\nstderr={process.stderr}"
        )
    return json.loads(process.stdout)


def now_iso(offset_minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).replace(microsecond=0).isoformat()


def candidate(idea_id: str, signature: str, mutexes: list[str], core: bool, cost: float) -> dict[str, Any]:
    return {
        "id": idea_id,
        "promotion_recommendation": "advance",
        "causal_signature": signature,
        "estimated_falsifier_gpu_hours": cost,
        "unique_decision_targets": [f"decision:{idea_id}"],
        "cheapest_discriminating_experiment": f"pilot {idea_id}",
        "mutex_groups": mutexes,
        "changes_core_claim": core,
        "portfolio_eligible": True,
    }


def case_exact_portfolio_subset() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-portfolio-exact-") as temp:
        project = Path(temp)
        rows = [
            candidate("idea-a", "sig-a", ["m1", "m2"], True, 0.2),
            candidate("idea-b", "sig-b", ["m1"], False, 0.3),
            candidate("idea-c", "sig-c", ["m2"], False, 0.3),
        ]
        write_json(
            project / ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            {"selection_revision": "selection-1", "shortlisted_idea_ids": ["idea-a", "idea-b", "idea-c"], "rows": rows},
        )
        write_json(project / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json", {"ideas": rows})
        queue = QUEUE.default_queue(project, QUEUE.merged_config(project))
        queue["policy"]["portfolio_capacity_target"] = 2
        queue["rows"] = []
        frontier = QUEUE.frontier_status(queue, matrix={}, project=project)
        require(frontier["portfolio_admission_deficit"] == 2, f"zero active tracks must leave deficit: {frontier}")
        require(
            frontier["portfolio_fillable_candidate_ids"] == ["idea-b", "idea-c"],
            f"exact set selection must prefer two compatible candidates over one blocking high-rank candidate: {frontier}",
        )
        require(frontier["portfolio_actionable"] is True, f"fillable zero-active portfolio cannot be satisfied: {frontier}")
        return {"case": "exact_portfolio_subset", "selected": frontier["portfolio_fillable_candidate_ids"]}


def component(component_id: str, value: str) -> dict[str, Any]:
    return {"component_id": component_id, "component_type": "runtime", "semantic_payload": {"value": value}}


def passport_spec(extra_value: str) -> dict[str, Any]:
    return {
        "project_id": "fixture",
        "components": [component("runtime:core", "v1"), component("dataset:main", "v1"), component("checkpoint:extra", extra_value)],
        "execution_profiles": [
            {"profile_id": "core", "required_component_ids": ["runtime:core", "dataset:main"], "route_requirements": {"execution_route": "ssh"}},
            {"profile_id": "extra", "required_component_ids": ["runtime:core", "checkpoint:extra"], "route_requirements": {"execution_route": "ssh"}},
        ],
    }


def case_scoped_passport_and_negative_cache() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-passport-scope-") as temp:
        project = Path(temp)
        first = PASSPORT.normalize_project_passport(passport_spec("v1"), project, 1)
        second = PASSPORT.normalize_project_passport(passport_spec("v2"), project, 2)
        first_profiles = {item["profile_id"]: item["execution_profile_sha256"] for item in first["execution_profiles"]}
        second_profiles = {item["profile_id"]: item["execution_profile_sha256"] for item in second["execution_profiles"]}
        require(first["index_semantic_sha256"] != second["index_semantic_sha256"], "changed component must change passport index")
        require(first_profiles["core"] == second_profiles["core"], "unrelated component change must preserve core profile identity")
        require(first_profiles["extra"] != second_profiles["extra"], "dependent profile must change")
        write_json(project / PASSPORT.PROJECT_REL, first)
        expires = now_iso(120)
        proofs = [
            {
                "component_id": item["component_id"],
                "semantic_sha256": item["semantic_sha256"],
                "state": "verified",
                "verified_at": now_iso(),
                "expires_at": expires,
                "evidence_ref": f"probe:{item['component_id']}",
            }
            for item in first["components"]
        ]
        capability = PASSPORT.empty_capability(first)
        pool = {"pool_id": "ssh:fixture", "components": proofs}
        capability["pools"] = [pool]
        pool["satisfied_execution_profile_sha256s"] = PASSPORT.satisfied_profiles(first, pool)
        capability["capability_semantic_sha256"] = PASSPORT.capability_semantic_sha256(capability)
        write_json(project / PASSPORT.CAPABILITY_REL, capability)
        result = run_json(
            [
                sys.executable,
                str(PASSPORT_PATH),
                "invalidate-capability",
                "--project",
                str(project),
                "--pool",
                "ssh:fixture",
                "--component-id",
                "checkpoint:extra",
                "--reason",
                "fixture mismatch",
                "--evidence-ref",
                "fixture:mismatch",
                "--expected-revision",
                "0",
            ]
        )
        updated = read_json(project / PASSPORT.CAPABILITY_REL)
        updated_pool = updated["pools"][0]
        require(first_profiles["core"] in updated_pool["satisfied_execution_profile_sha256s"], f"unrelated profile lost fit: {updated_pool}")
        require(first_profiles["extra"] not in updated_pool["satisfied_execution_profile_sha256s"], f"invalidated profile still fits: {updated_pool}")
        require(PASSPORT.pool_components(updated_pool).get("runtime:core"), "negative cache must not suppress unrelated components")
        require("checkpoint:extra" not in PASSPORT.pool_components(updated_pool), "negative cache must suppress implicated component")
        legacy_negative = {
            **pool,
            "negative_cache": {"reason": "legacy whole-pool failure", "expires_at": now_iso(30)},
        }
        require(PASSPORT.pool_components(legacy_negative) == {}, "unscoped legacy negative cache must fail closed")
        return {"case": "scoped_passport_negative_cache", "capability_revision": result["capability_revision"]}


def case_transaction_recovery() -> dict[str, Any]:
    states: list[str] = []
    for state in BATCH.OPERATION_STATES[:-1]:
        with tempfile.TemporaryDirectory(prefix=f"autoreskill-batch-{state}-") as temp:
            base = Path(temp) / ".autoreskill"
            existing = base / "ideation/IDEA_TRACK_SEEDS.json"
            created = base / "orchestrator/tracks/new/INNOVATION_PACKET.json"
            write_json(existing, {"before": True})
            journal_path, backup_root = BATCH.operation_paths(base, f"op-{state}")
            manifest = BATCH.backup_targets(
                base,
                backup_root,
                ["ideation/IDEA_TRACK_SEEDS.json", "orchestrator/tracks/new/INNOVATION_PACKET.json"],
            )
            journal = {"operation_id": f"op-{state}", "state": "", "target_manifest": manifest}
            BATCH.advance_journal(journal_path, journal, state)
            write_json(existing, {"after": True})
            write_json(created, {"partial": True})
            recovered = BATCH.restore_operation(base, journal_path, read_json(journal_path))
            require(read_json(existing) == {"before": True}, f"{state} did not restore exact before-state")
            require(not created.exists(), f"{state} did not remove partial new target")
            require(recovered["state"] == "ROLLED_BACK", f"{state} recovery state mismatch")
            states.append(state)
    return {"case": "transaction_recovery", "states": states}


def submit_project() -> tuple[Path, dict[str, Any]]:
    project = Path(tempfile.mkdtemp(prefix="autoreskill-submit-state-"))
    queue = QUEUE.default_queue(project, QUEUE.merged_config(project))
    preflight = {"status": "passed", "checked_at": now_iso(), "pool_id": "local-pool", "execution_route": "local", "launch_spec_sha256": "a" * 64, "resource_snapshot_sha256": "b" * 64}
    row = {
        "id": "row-submit",
        "priority": 1,
        "status": "planned",
        "role": "single_innovation",
        "dataset": "fixture",
        "next_action": "submit fixture",
        "updated_at": now_iso(),
        "launch_identity_hash": "c" * 64,
        "lease_owner": "owner",
        "lease_acquired_at": now_iso(),
        "lease_expires_at": now_iso(60),
        "planned_resource_allocation": {"pool_id": "local-pool", "backend": "local", "execution_route": "local", "resource_snapshot_sha256": "b" * 64},
        "backend_preflight": preflight,
        "backend_preflight_sha256": QUEUE.canonical_payload_sha256(preflight),
        "row_revision": 0,
    }
    queue["rows"] = [row]
    queue["queue_revision"] = 0
    write_json(project / QUEUE.QUEUE_REL, queue)
    return project, row


def mutation_args(project: Path, revision: int, input_path: Path) -> argparse.Namespace:
    return argparse.Namespace(project=str(project), row_id="row-submit", owner="owner", expected_revision=revision, input=str(input_path), reason="fixture")


def submit_intent(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "submit_attempt_id": "attempt-1",
        "backend_idempotency_key": "idempotency-1",
        "anonymous_trace_id": "trace-1",
        "launch_identity_hash": row["launch_identity_hash"],
        "script_or_command_sha256": "d" * 64,
        "preflight_sha256": row["backend_preflight_sha256"],
        "pool_id": "local-pool",
        "execution_route": "local",
        "queue_revision": 0,
        "trace_embedding": {"surface": "process_identity", "anonymous_trace_id": "trace-1"},
        "lookup_strategy": {"search_fields": ["anonymous_trace_id", "script_or_command_sha256"]},
    }


def case_durable_submit_state() -> dict[str, Any]:
    project, row = submit_project()
    try:
        intent = submit_intent(row)
        intent_path = project / "intent.json"
        write_json(intent_path, {"submit_intent": intent})
        code, prepared = QUEUE.mutate_submit_artifact(mutation_args(project, 0, intent_path), "prepare-backend-submit")
        require(code == 0 and prepared["status"] == "submitting", f"intent did not become submitting: {prepared}")
        claim_args = argparse.Namespace(project=str(project), row_id="row-submit", owner="owner", expected_revision=1)
        code, repeated_claim = QUEUE.mutate_queue(claim_args, "claim")
        require(code == 0 and repeated_claim.get("idempotent") is True and repeated_claim.get("status") == "submitting", f"same-owner recovery claim was not idempotent: {repeated_claim}")
        bad_receipt = {**intent, "anonymous_trace_id": "wrong", "native_id": "42", "accepted_at": now_iso(), "evidence_ref": "fixture:receipt"}
        bad_path = project / "bad-receipt.json"
        write_json(bad_path, {"submit_receipt": bad_receipt})
        code, conflict = QUEUE.mutate_submit_artifact(mutation_args(project, 1, bad_path), "record-backend-submit")
        require(code != 0 and conflict.get("error", {}).get("code") == "submit_receipt_invalid", f"conflicting receipt was accepted: {conflict}")
        receipt = {**intent, "native_id": "42", "accepted_at": now_iso(), "evidence_ref": "fixture:receipt"}
        receipt_path = project / "receipt.json"
        write_json(receipt_path, {"submit_receipt": receipt})
        code, accepted = QUEUE.mutate_submit_artifact(mutation_args(project, 1, receipt_path), "record-backend-submit")
        require(code == 0 and accepted["status"] == "needs_sync", f"receipt did not become needs_sync: {accepted}")
        observation = {"submit_attempt_id": "attempt-1", "anonymous_trace_id": "trace-1", "native_id": "42", "backend_state": "running", "observed_at": now_iso(), "evidence_ref": "fixture:backend"}
        observation_path = project / "observation.json"
        write_json(observation_path, {"backend_observation": observation})
        code, running = QUEUE.mutate_submit_artifact(mutation_args(project, 2, observation_path), "record-backend-observation")
        require(code == 0 and running["status"] == "running", f"observation did not become running: {running}")
    finally:
        shutil.rmtree(project, ignore_errors=True)

    abort_project, abort_row = submit_project()
    try:
        intent = submit_intent(abort_row)
        intent_path = abort_project / "intent.json"
        write_json(intent_path, intent)
        require(QUEUE.mutate_submit_artifact(mutation_args(abort_project, 0, intent_path), "prepare-backend-submit")[0] == 0, "prepare failed")
        abort_path = abort_project / "abort.json"
        write_json(abort_path, {"submit_attempt_id": "attempt-1", "command_started": False, "checked_at": now_iso(), "evidence_ref": "fixture:local-precommand"})
        code, aborted = QUEUE.mutate_submit_artifact(mutation_args(abort_project, 1, abort_path), "abort-backend-submit")
        require(code == 0 and aborted["status"] == "planned", f"pre-command abort did not restore planned: {aborted}")
    finally:
        shutil.rmtree(abort_project, ignore_errors=True)
    return {"case": "durable_submit_state", "states": ["submitting", "needs_sync", "running", "planned_after_abort"]}


def case_set_policy_cas() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-set-policy-") as temp:
        project = Path(temp)
        queue = QUEUE.default_queue(project, QUEUE.merged_config(project))
        write_json(project / QUEUE.QUEUE_REL, queue)
        args = argparse.Namespace(project=str(project), admission_scope="global", portfolio_capacity_target=3, expected_revision=0, owner="fixture", reason="fixture migration")
        code, changed = QUEUE.set_policy(args)
        require(code == 0 and changed["queue_revision"] == 1 and changed["policy"]["admission_scope"] == "global", f"policy CAS failed: {changed}")
        code, stale = QUEUE.set_policy(args)
        require(code != 0 and stale.get("error", {}).get("code") == "stale_plan", f"stale policy CAS did not fail: {stale}")
        return {"case": "set_policy_cas", "revision": changed["queue_revision"]}


def case_validation_ladder_guards() -> dict[str, Any]:
    queue = {"schema_version": 2, "queue_revision": 0, "policy": {"portfolio_capacity_target": 4, "admission_scope": "project"}, "rows": []}
    common = {
        "id": "stage6",
        "priority": 1,
        "status": "ready",
        "role": "stability",
        "dataset": "fixture",
        "next_action": "paired stability",
        "updated_at": now_iso(),
        "validation_stage": 6,
        "validation_prerequisites": ["stage5 complete"],
        "baseline_freeze_ref": "baseline:freeze",
        "comparison_source": "vs matched reproduced baseline",
        "experiment_family_id": "family",
        "replication_group_id": "pair",
        "seeds": [0, 1, 2, 3],
        "seed_count": 4,
    }
    queue["rows"] = [common]
    checked = QUEUE.validate_queue(queue)
    require(any("one to three unique paired seeds" in value for value in checked["errors"]), f"four-seed Stage 6 was not rejected: {checked}")

    calibration = {**common, "id": "calibration", "role": "baseline_calibration", "validation_stage": 5, "evidence_tier": "pilot_only"}
    queue["rows"] = [calibration]
    checked = QUEUE.validate_queue(queue)
    require(any("baseline_calibration" in value and "stage=5" in value.lower() for value in checked["errors"]), f"baseline calibration entered Stage 5: {checked}")
    return {"case": "validation_ladder_guards", "four_seed_rejected": True, "calibration_stage5_rejected": True}


def case_efficiency_unknowns_and_global_payload() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-efficiency-") as temp:
        project = Path(temp)
        queue = QUEUE.default_queue(project, QUEUE.merged_config(project))
        write_json(project / QUEUE.QUEUE_REL, queue)
        report = EFFICIENCY.project_report(QUEUE, project)
        require(report["gpu_hours_per_decision"]["value"] is None, "missing runtime evidence must not be imputed")
        require(report["portfolio_starvation_rate"]["value"] is None, "one/no observation cannot fabricate starvation")
        rendered = EFFICIENCY.markdown({"generated_at": "2026-07-13T00:00:00+00:00", "projects": [report]})
        require(
            "Stage-2 cross-dataset coverage" in rendered
            and "Cross-dataset decisions" in rendered
            and "Contradiction closure" in rendered,
            "human-readable efficiency report omitted cross-dataset stability metrics",
        )
        write_json(
            project / ".autoreskill/coder/EXPERIMENT_LEDGER.json",
            {
                "entries": [
                    {
                        "scientific_outcome_status": "accepted",
                        "research_transition": "refine",
                        "scientific_decision_id": "decision-without-runtime",
                    }
                ]
            },
        )
        report = EFFICIENCY.project_report(QUEUE, project)
        gpu_metric = report["gpu_hours_per_decision"]
        require(gpu_metric["decision_count"] == 1, f"fixture decision was not counted: {gpu_metric}")
        require(gpu_metric["terminal_runs"] == 0, f"fixture unexpectedly found terminal runs: {gpu_metric}")
        require(gpu_metric["value"] is None, "zero terminal runs must not fabricate zero GPU-hours per decision")
        require(gpu_metric["unknown_reason"] == "no terminal run accounting evidence", f"wrong unknown reason: {gpu_metric}")
        aggregate = EFFICIENCY.aggregate([report])["gpu_hours_per_decision"]
        require(aggregate["value"] is None, "aggregate zero terminal runs must remain unknown")
        require(aggregate["unknown_reason"] == "no terminal run accounting evidence", f"wrong aggregate reason: {aggregate}")
        snapshot = project / "shared-snapshot.json"
        write_json(snapshot, {"kind": "merged_resource_snapshot", "pools": []})
        config = {
            "schema_version": 1,
            "controller_task_id": "fixture-controller-task",
            "project_roots": [str(project)],
            "shared_resource_snapshot": str(snapshot),
            "rollout_phase": "prepare",
            "launch_authorized": False,
            "heartbeat_interval_minutes": 5,
            "max_submits_per_wake": 4,
        }
        payload = GLOBAL_PAYLOAD.build_payload(config)
        require(payload["ok"] and payload["payload"]["status"] == "PAUSED", f"prepare controller must be paused: {payload}")
        require("Physical submission is disabled" in payload["payload"]["prompt"], "dry controller omitted no-submit guard")
        readback = {
            "name": payload["payload"]["name"],
            "status": payload["payload"]["status"],
            "prompt": payload["payload"]["prompt"],
        }
        verified = GLOBAL_PAYLOAD.verify_readback(payload["readback_expectation"], readback)
        require(verified["ok"], f"matching global readback did not verify: {verified}")
        drifted = dict(readback)
        drifted["prompt"] += " drift"
        require(
            not GLOBAL_PAYLOAD.verify_readback(payload["readback_expectation"], drifted)["ok"],
            "drifted global readback was accepted",
        )
        config["rollout_phase"] = "active"
        active = GLOBAL_PAYLOAD.build_payload(config)
        require(not active["ok"] and any("admission_scope=global" in value for value in active["errors"]), f"active controller accepted project scope: {active}")
        config["api_token"] = "must-not-be-stored-here"
        secret = GLOBAL_PAYLOAD.build_payload(config)
        require(not secret["ok"] and any("not secrets" in value for value in secret["errors"]), f"secret-bearing global config was accepted: {secret}")
        return {"case": "efficiency_unknowns_global_payload", "prepare_status": payload["payload"]["status"]}


def case_submitting_blocks_terminal_program() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="autoreskill-terminal-submit-") as temp:
        base = Path(temp) / ".autoreskill"
        write_json(
            base / "experiment/NEXT_EXPERIMENT_QUEUE.json",
            {"rows": [{"id": "prepared-at-backend-boundary", "status": "submitting"}]},
        )
        decision = {
            "status": "no_valid_gain",
            "active_track_ids": ["track-a"],
            "final_track_states": [{"track_id": "track-a", "lifecycle_status": "retired"}],
            "evidence_refs": ["fixture:evidence"],
            "remaining_claim_scope": "none",
            "mandatory_downgrade": "no improvement claim",
            "budget_or_value_rationale": "fixture",
            "target_stage": "analysis",
            "decision_id": "fixture-decision",
            "terminal": True,
            "improvement_claim_allowed": False,
        }
        missing, _, details = CONTRACT_LINT.validate_terminal_program_decision(base, decision)
        require(details["live_queue_rows"] == ["prepared-at-backend-boundary"], f"submitting row disappeared from terminal guard: {details}")
        require(any("unresolved live queue rows" in value for value in missing), f"terminal guard accepted submitting row: {missing}")
        require("submitting" in RESEARCH_DECISION.LIVE_QUEUE_STATUSES, "research decision terminal guard omitted submitting")
        return {"case": "submitting_blocks_terminal_program", "live_rows": details["live_queue_rows"]}


def main() -> None:
    results = [
        case_exact_portfolio_subset(),
        case_scoped_passport_and_negative_cache(),
        case_transaction_recovery(),
        case_durable_submit_state(),
        case_set_policy_cas(),
        case_validation_ladder_guards(),
        case_efficiency_unknowns_and_global_payload(),
        case_submitting_blocks_terminal_program(),
    ]
    print(json.dumps({"ok": True, "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
