#!/usr/bin/env python3
"""Transactionally admit and materialize a feasible shortlist batch."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parents[1]
IDEA_SEEDS = SKILLS_ROOT / "autoreskill-ideation-panel/scripts/idea_track_seeds.py"
MATERIALIZE = SKILLS_ROOT / "autoreskill-experiment-plan/scripts/experiment_materialize.py"
INNOVATION_LINT = SKILLS_ROOT / "autoreskill-experiment-plan/scripts/innovation_lint.py"
PRELAUNCH_LINT = SKILLS_ROOT / "autoreskill-experiment-plan/scripts/prelaunch_lint.py"
TRACK_MATRIX = SKILLS_ROOT / "autoreskill-experiment-plan/scripts/track_plan_matrix.py"
QUEUE_SCRIPT = HERE / "experiment_next_actions.py"
OPERATION_STATES = [
    "PREPARED",
    "packets_written_and_linted",
    "matrix_committed",
    "queue_rows_committed",
    "COMMITTED",
]
IMMUTABLE_SOURCE_RELS = [
    "ideation/EXPERIMENT_IDEA_POOL.json",
    "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
    "ideation/IDEA_DECISION_LEDGER.json",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def assert_source_hashes(base: Path, expected: dict[str, str | None], *, label: str) -> None:
    changed = [rel for rel, digest in expected.items() if file_sha256(base / rel) != digest]
    if changed:
        raise RuntimeError(f"{label} changed during portfolio batch: {', '.join(sorted(changed))}")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout}
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stderr.strip() or json.dumps(payload, ensure_ascii=False)}"
        )
    return payload if isinstance(payload, dict) else {"result": payload}


@contextmanager
def operation_lock(base: Path) -> Iterator[None]:
    path = base / "control/PORTFOLIO_BATCH.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def operation_paths(base: Path, operation_id: str) -> tuple[Path, Path]:
    journal = base / f"control/operations/{operation_id}.json"
    backup = base / f"control/operations/.backups/{operation_id}"
    return journal, backup


def advance_journal(path: Path, journal: dict[str, Any], state: str) -> None:
    current = str(journal.get("state") or "")
    if state not in OPERATION_STATES:
        raise RuntimeError(f"unsupported operation state {state}")
    if current and current in OPERATION_STATES and OPERATION_STATES.index(state) < OPERATION_STATES.index(current):
        raise RuntimeError(f"journal state regression: {current} -> {state}")
    journal["state"] = state
    journal["updated_at"] = now_iso()
    journal.setdefault("state_history", []).append({"state": state, "at": journal["updated_at"]})
    atomic_write_json(path, journal)


def target_paths(seed_payload: dict[str, Any]) -> list[str]:
    paths = {
        "ideation/IDEA_TRACK_SEEDS.json",
        "orchestrator/TRACK_PLAN_MATRIX.json",
        "experiment/NEXT_EXPERIMENT_QUEUE.json",
        "decision_log.jsonl",
    }
    for seed in seed_payload.get("tracks") or []:
        if not isinstance(seed, dict):
            continue
        track_id = str(seed.get("track_id") or "").strip()
        if not track_id:
            continue
        paths.update(
            {
                f"orchestrator/tracks/{track_id}/INNOVATION_PACKET.json",
                f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json",
                f"planner/tracks/{track_id}/EXPERIMENT_PLAN.md",
            }
        )
        if str(seed.get("track_role") or "") == "primary":
            paths.update(
                {
                    "orchestrator/INNOVATION_PACKET.json",
                    "planner/EXPERIMENT_REVIEW_PACKET.json",
                    "planner/EXPERIMENT_PLAN.md",
                }
            )
    return sorted(paths)


def backup_targets(base: Path, backup_root: Path, paths: list[str]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for rel in paths:
        source = base / rel
        backup = backup_root / rel
        exists = source.is_file()
        if exists:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup)
        manifest.append(
            {
                "path": rel,
                "existed": exists,
                "before_sha256": file_sha256(source),
                "backup_ref": str(backup.relative_to(base)) if exists else None,
            }
        )
    return manifest


def restore_operation(base: Path, journal_path: Path, journal: dict[str, Any]) -> dict[str, Any]:
    if str(journal.get("state") or "") == "COMMITTED":
        return {"ok": True, "operation_id": journal.get("operation_id"), "state": "COMMITTED", "restored": []}
    restored: list[str] = []
    for item in journal.get("target_manifest") or []:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        if not rel:
            continue
        target = base / rel
        if item.get("existed") is True:
            backup_ref = str(item.get("backup_ref") or "")
            backup = base / backup_ref
            if not backup.is_file():
                raise RuntimeError(f"missing recovery backup for {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        elif target.exists():
            target.unlink()
        restored.append(rel)
    journal["state"] = "ROLLED_BACK"
    journal["recovered_at"] = now_iso()
    journal["restored_paths"] = restored
    atomic_write_json(journal_path, journal)
    return {"ok": True, "operation_id": journal.get("operation_id"), "state": "ROLLED_BACK", "restored": restored}


def failpoint(value: str | None, state: str) -> None:
    if value == state:
        os._exit(86)


def minimum_queue_rows(
    ena: Any,
    base: Path,
    matrix_row: dict[str, Any],
    candidate_costs: dict[str, float],
) -> list[dict[str, Any]]:
    track_id = str(matrix_row.get("track_id") or "")
    review_ref = str(matrix_row.get("review_packet_ref") or "")
    review = read_json(base / review_ref)
    contract = matrix_row.get("hypothesis_contract") if isinstance(matrix_row.get("hypothesis_contract"), dict) else {}
    compute = review.get("compute_budget") if isinstance(review.get("compute_budget"), dict) else {}
    backend = str(review.get("execution_route") or review.get("compute_backend") or "local").strip().lower()
    if backend not in ena.EXECUTION_ROUTES:
        backend = "local"
    idea_id = str(matrix_row.get("idea_id") or "")
    gpu_hours = ena.numeric(compute.get("gpu_hours"), 0.0)
    if gpu_hours <= 0:
        gpu_hours = ena.numeric(candidate_costs.get(idea_id), 0.0)
    if gpu_hours <= 0:
        raise RuntimeError(f"track {track_id} lacks a positive falsifier GPU-hour estimate")
    dataset_plan = review.get("dataset_group_plan") if isinstance(review.get("dataset_group_plan"), dict) else {}
    dataset_ids = [str(value) for value in dataset_plan.get("required_dataset_ids") or [] if str(value)]
    if not dataset_ids:
        dataset_ids = [str(matrix_row.get("dataset") or review.get("dataset") or "")]
    parameter_contract = (
        review.get("parameter_transfer_contract")
        if isinstance(review.get("parameter_transfer_contract"), dict)
        else {}
    )
    claim_role = str(matrix_row.get("claim_role") or review.get("claim_role") or "")
    profile_status = str(review.get("parameter_profile_status") or "not_required")
    cross_dataset_method = (
        str(review.get("claim_scope") or matrix_row.get("claim_scope") or "") == "cross_dataset_method"
        and claim_role == "method_candidate"
        and bool(parameter_contract)
    )
    candidates_by_dataset = parameter_contract.get("candidate_values_by_dataset") or {}
    seeds_by_dataset = parameter_contract.get("selection_seed_by_dataset") or {}
    profile_ref = str(review.get("frozen_parameter_profile_ref") or "")
    profile = read_json(base / profile_ref) if profile_ref else {}
    selected_by_dataset = profile.get("selected_setting_by_dataset") if isinstance(profile, dict) else {}
    realized_by_dataset = profile.get("realized_value_by_dataset") if isinstance(profile, dict) else {}

    row_specs: list[dict[str, Any]] = []
    if cross_dataset_method and profile_status != "frozen":
        group_id = str(parameter_contract.get("parameter_calibration_group_id") or "")
        for dataset_id in dataset_ids:
            for value in candidates_by_dataset.get(dataset_id) or []:
                row_specs.append(
                    {
                        "dataset": dataset_id,
                        "role": "parameter_probe",
                        "stage2_role": "stage2_parameter_probe",
                        "decision_class": "resolve_competing_hypotheses",
                        "parameter_value": value,
                        "realized_parameter_value": value,
                        "seed": seeds_by_dataset.get(dataset_id),
                        "parameter_calibration_group_id": group_id,
                        "parameter_probe_kind": parameter_contract.get("parameter_probe_kind") or "bounded_calibration",
                        "next_action": "run one preregistered innovation-parameter value with the dataset scout seed",
                    }
                )
    elif cross_dataset_method:
        paired_identity = {
            "track_id": track_id,
            "program_claim_contract_sha256": review.get("program_claim_contract_sha256"),
            "method_formula_sha256": review.get("method_formula_sha256"),
            "parameter_transfer_contract_sha256": parameter_contract.get("parameter_transfer_contract_sha256"),
            "frozen_parameter_profile_sha256": profile.get("frozen_parameter_profile_sha256"),
            "selection_seed_by_dataset": seeds_by_dataset,
            "dataset_group_plan": dataset_plan,
            "primary_metric": review.get("primary_metric"),
            "fidelity": review.get("stage2_fidelity") or "minimum_valid",
        }
        paired_group_id = f"{track_id}:stage2:{canonical_sha256(paired_identity)[:16]}"
        for dataset_id in dataset_ids:
            row_specs.append(
                {
                    "dataset": dataset_id,
                    "role": "single_innovation",
                    "stage2_role": "stage2_method_screen",
                    "decision_class": "falsify_core_mechanism",
                    "parameter_value": selected_by_dataset.get(dataset_id),
                    "realized_parameter_value": realized_by_dataset.get(dataset_id),
                    "seed": seeds_by_dataset.get(dataset_id),
                    "paired_dataset_group_id": paired_group_id,
                    "next_action": "run the frozen method profile on one required low-fidelity dataset leg",
                }
            )
    else:
        row_specs.append(
            {
                "dataset": str(matrix_row.get("dataset") or review.get("dataset") or ""),
                "role": "single_innovation",
                "stage2_role": review.get("stage2_role"),
                "decision_class": "falsify_core_mechanism",
                "seed": 0,
                "next_action": "run the cheapest one-seed low-fidelity falsifier",
            }
        )
    if not row_specs:
        raise RuntimeError(f"track {track_id} has no materializable Stage-2 parameter/dataset rows")
    if any(spec.get("stage2_role") == "stage2_parameter_probe" for spec in row_specs):
        program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json")
        search_budget = program.get("search_budget") if isinstance(program.get("search_budget"), dict) else {}
        probe_cap = search_budget.get("max_parameter_probe_gpu_hours_per_track")
        if isinstance(probe_cap, bool) or not isinstance(probe_cap, (int, float)) or float(probe_cap) <= 0:
            raise RuntimeError(f"track {track_id} lacks a finite parameter-probe GPU-hour cap")
        if gpu_hours > float(probe_cap):
            raise RuntimeError(
                f"track {track_id} parameter-probe estimate {gpu_hours:g} exceeds cap {float(probe_cap):g} GPU-hours"
            )
    per_row_gpu_hours = gpu_hours / len(row_specs)
    baseline_by_dataset = dataset_plan.get("baseline_ref_by_dataset") or {}
    rows: list[dict[str, Any]] = []
    for spec in row_specs:
        dataset_id = str(spec["dataset"])
        suffix_payload = {
            "dataset": dataset_id,
            "stage2_role": spec.get("stage2_role"),
            "parameter_value": spec.get("parameter_value"),
        }
        suffix = canonical_sha256(suffix_payload)[:10]
        protocol_payload = {
            "baseline_training_protocol": review.get("baseline_training_protocol"),
            "baseline_eval_protocol": review.get("baseline_eval_protocol"),
            "data_split": review.get("data_split"),
            "metric": review.get("primary_metric"),
            "dataset": dataset_id,
            "parameter_transfer_contract_sha256": parameter_contract.get("parameter_transfer_contract_sha256"),
            "method_formula_sha256": review.get("method_formula_sha256"),
            "frozen_parameter_profile_sha256": review.get("frozen_parameter_profile_sha256"),
        }
        identity = {
            "selected_idea_id": matrix_row.get("idea_id"),
            "track_id": track_id,
            "branch_id": matrix_row.get("branch_id"),
            "selection_fingerprint": matrix_row.get("selection_fingerprint"),
            "track_plan_ref": review_ref,
            "causal_signature": contract.get("causal_signature"),
            "decision_class": spec["decision_class"],
            "dataset": dataset_id,
            "validation_stage": 2,
            "stage2_role": spec.get("stage2_role"),
            "parameter_value": spec.get("parameter_value"),
            "seed": spec.get("seed"),
            "frozen_parameter_profile_sha256": review.get("frozen_parameter_profile_sha256"),
        }
        row = {
        "id": f"pilot-{track_id}-stage2-{suffix}",
        "priority": 20,
        "status": "ready" if matrix_row.get("launch_status") == "ready" else "candidate",
        "role": spec["role"],
        "dataset": dataset_id,
        "dataset_id": dataset_id,
        "next_action": spec["next_action"],
        "updated_at": now_iso(),
        "selected_idea_id": matrix_row.get("idea_id"),
        "track_id": track_id,
        "track_role": matrix_row.get("track_role"),
        "branch_id": matrix_row.get("branch_id"),
        "selection_fingerprint": matrix_row.get("selection_fingerprint"),
        "track_plan_ref": review_ref,
        "causal_signature": contract.get("causal_signature"),
        "claim_role": claim_role or None,
        "decision_class": spec["decision_class"],
        "why_now": "cheapest dependency-unlocked discriminator for an admitted causal track",
        "claim_target": (review.get("claim_ids") or [f"{track_id}:mechanism"])[0],
        "hypothesis_prediction": contract.get("predicted_pattern") or review.get("observable_prediction"),
        "falsifier": contract.get("falsifier") or (review.get("falsifiers") or [None])[0],
        "expected_decision_change": "support advances to full-budget matched control; valid negative retires or pivots",
        "baseline_anchor": baseline_by_dataset.get(dataset_id) or review.get("baseline_reference") or matrix_row.get("baseline_code"),
        "comparison_source": "paper-report comparison not established",
        "protocol": canonical_sha256(protocol_payload),
        "metric_policy_ref": f"{review_ref}:primary_metric",
        "resource_request": {"backend": backend, "gpu_count": 1, "estimated_gpu_hours": per_row_gpu_hours},
        "estimated_gpu_hours": per_row_gpu_hours,
        "mutex_group": f"track:{track_id}:stage2:{suffix}",
        "parallel_safe": True,
        "evidence_paths": [review_ref, str(matrix_row.get("innovation_packet_ref") or "")],
        "outcome_routes": contract.get("outcome_routes"),
        "launch_mode": "first_use",
        "evidence_tier": "pilot_only",
        "evidence_tier_ceiling": matrix_row.get("evidence_tier_ceiling"),
        "decision_target_refs": [str(matrix_row.get("idea_decision_ref") or track_id)],
        "innovation_id": str(matrix_row.get("idea_id") or track_id),
        "validation_stage": 2,
        "validation_stage_name": str(spec.get("stage2_role") or "low_fidelity_single_seed_falsifier"),
        "stage2_role": spec.get("stage2_role"),
        "validation_prerequisites": ["stage_0_pass", "stage_1_pass"],
        "claim_ceiling": "pilot_only",
        "claim_eligible": False,
        "project_execution_passport_ref": matrix_row.get("project_execution_passport_ref"),
        "project_execution_passport_index_sha256": matrix_row.get(
            "project_execution_passport_index_sha256"
        ),
        "execution_profile_id": matrix_row.get("execution_profile_id"),
        "execution_profile_sha256": matrix_row.get("execution_profile_sha256"),
        "innovation_delta_sha256": matrix_row.get("innovation_delta_sha256"),
        "seed": spec.get("seed"),
        "seed_count": 1,
        "seeds": [spec.get("seed")],
        "parameter_profile_status": profile_status,
        "parameter_transfer_contract_sha256": parameter_contract.get("parameter_transfer_contract_sha256"),
        "method_formula_sha256": review.get("method_formula_sha256"),
        "parameter_calibration_group_id": spec.get("parameter_calibration_group_id"),
        "parameter_probe_kind": spec.get("parameter_probe_kind"),
        "parameter_name": parameter_contract.get("parameter_name"),
        "parameter_value": spec.get("parameter_value"),
        "realized_parameter_value": spec.get("realized_parameter_value"),
        "paired_dataset_group_id": spec.get("paired_dataset_group_id"),
        "frozen_parameter_profile_ref": review.get("frozen_parameter_profile_ref"),
        "frozen_parameter_profile_sha256": review.get("frozen_parameter_profile_sha256"),
        "program_claim_contract_ref": matrix_row.get("program_claim_contract_ref"),
        "program_claim_contract_sha256": matrix_row.get("program_claim_contract_sha256"),
        "program_claim_contract_revision": matrix_row.get("program_claim_contract_revision"),
        "claim_scope": matrix_row.get("claim_scope") or review.get("claim_scope"),
        "row_revision": 0,
        }
        row["launch_identity_hash"] = canonical_sha256(identity)
        rows.append({key: value for key, value in row.items() if value is not None})
    return rows


def commit_queue_rows(
    ena: Any,
    project: Path,
    base: Path,
    selected_ids: list[str],
    expected_revision: int,
    candidate_costs: dict[str, float],
) -> dict[str, Any]:
    queue_path = project / ena.QUEUE_REL
    with ena.queue_lock(queue_path):
        queue = ena.load_queue(project)
        if not queue:
            queue = ena.default_queue(project, ena.merged_config(project))
        if int(queue.get("queue_revision") or 0) != expected_revision:
            raise RuntimeError("queue revision changed during portfolio batch")
        matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json")
        existing_ids = {
            str(row.get("id") or "")
            for row in queue.get("rows") or []
            if isinstance(row, dict)
        }
        added: list[str] = []
        for matrix_row in matrix.get("tracks") or []:
            if not isinstance(matrix_row, dict) or str(matrix_row.get("idea_id") or "") not in selected_ids:
                continue
            for row in minimum_queue_rows(ena, base, matrix_row, candidate_costs):
                if row["id"] in existing_ids:
                    continue
                queue.setdefault("rows", []).append(row)
                existing_ids.add(row["id"])
                added.append(row["id"])
        queue.setdefault("policy", {}).setdefault("portfolio_capacity_target", 4)
        queue.setdefault("policy", {}).setdefault("method_portfolio_target", 2)
        program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json")
        if str(program.get("enforcement_mode") or "legacy") == "enforced":
            binding = ena.program_contract_binding(program)
            queue.update(binding)
            search_budget = program.get("search_budget") if isinstance(program.get("search_budget"), dict) else {}
            promotion = program.get("promotion_rule") if isinstance(program.get("promotion_rule"), dict) else {}
            queue["policy"].update(
                {
                    "portfolio_capacity_target": search_budget.get("portfolio_capacity_target"),
                    "method_portfolio_target": search_budget.get("method_portfolio_target"),
                    "portfolio_gpu_hour_budget": search_budget.get("gpu_hour_budget"),
                    "max_random_seed_count": promotion.get("max_random_seeds"),
                }
            )
        queue["queue_revision"] = int(queue.get("queue_revision") or 0) + 1
        queue["updated_at"] = now_iso()
        queue.setdefault("decision_log", []).append(
            {
                "timestamp": now_iso(),
                "decision": "batch_materialize_portfolio",
                "rationale": "materialize every set-feasible shortlist candidate in one bounded transaction",
                "idea_ids": selected_ids,
                "row_ids": added,
                "evidence_paths": ["ideation/IDEA_TRACK_SEEDS.json", "orchestrator/TRACK_PLAN_MATRIX.json"],
            }
        )
        validation = ena.validate_queue(queue, project=project)
        if not validation.get("ok"):
            raise RuntimeError("materialized queue is invalid: " + "; ".join(validation.get("errors") or []))
        ena.atomic_write_json(queue_path, queue)
        return {"added_row_ids": added, "queue_revision": queue["queue_revision"]}


def execute(args: argparse.Namespace) -> dict[str, Any]:
    project = Path(args.project).expanduser().resolve()
    base = project / ".autoreskill"
    ena = load_module("portfolio_experiment_next_actions", QUEUE_SCRIPT)
    seeds_module = load_module("portfolio_idea_track_seeds", IDEA_SEEDS)
    queue = ena.load_queue(project)
    if not queue:
        queue = ena.default_queue(project, ena.merged_config(project))
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json")
    frontier = ena.frontier_status(queue, matrix=matrix, project=project)
    selected_ids = list(frontier.get("portfolio_fillable_candidate_ids") or [])
    if args.idea_id:
        requested = [str(value) for value in args.idea_id]
        selected_ids = [value for value in selected_ids if value in requested]
        missing = sorted(set(requested) - set(selected_ids))
        if missing:
            raise RuntimeError("requested idea ids are not in the current feasible subset: " + ", ".join(missing))
    selected_ids = selected_ids[: int(frontier.get("portfolio_admission_deficit") or 0)]
    if not selected_ids:
        return {"ok": True, "dry_run": args.dry_run, "changed": False, "frontier": frontier, "reason": "no_fillable_candidate"}
    current_seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json")
    candidate_costs = {
        str(item.get("idea_id") or ""): float(item.get("estimated_falsifier_gpu_hours"))
        for item in frontier.get("portfolio_candidates", [])
        if isinstance(item, dict)
        and str(item.get("idea_id") or "") in selected_ids
        and isinstance(item.get("estimated_falsifier_gpu_hours"), (int, float))
        and not isinstance(item.get("estimated_falsifier_gpu_hours"), bool)
        and float(item.get("estimated_falsifier_gpu_hours")) > 0
    }
    if set(candidate_costs) != set(selected_ids):
        raise RuntimeError("feasible subset lost its positive cost evidence before batch materialization")
    materialize_gpu_hours = args.gpu_hours if args.gpu_hours > 0 else max(candidate_costs.values())
    current_count = len(current_seeds.get("tracks") or [])
    capacity = min(4, current_count + len(selected_ids))
    next_seeds = seeds_module.build(str(project), capacity_target=capacity, admit_idea_ids=selected_ids)
    source_hashes = {
        rel: file_sha256(base / rel)
        for rel in [
            "ideation/EXPERIMENT_IDEA_POOL.json",
            "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            "ideation/IDEA_DECISION_LEDGER.json",
            "ideation/IDEA_TRACK_SEEDS.json",
            "experiment/NEXT_EXPERIMENT_QUEUE.json",
        ]
    }
    assert_source_hashes(base, source_hashes, label="portfolio source authority")
    operation_id = args.operation_id or "portfolio-" + canonical_sha256(
        {"selection_revision": frontier.get("selection_revision"), "selected_ids": selected_ids, "source_hashes": source_hashes}
    )[:16]
    if args.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "changed": True,
            "operation_id": operation_id,
            "selected_idea_ids": selected_ids,
            "next_track_ids": [item.get("track_id") for item in next_seeds.get("tracks") or []],
            "frontier": frontier,
        }
    journal_path, backup_root = operation_paths(base, operation_id)
    existing = read_json(journal_path)
    if existing:
        state = str(existing.get("state") or "")
        if state == "COMMITTED":
            return {"ok": True, "changed": False, "idempotent": True, "operation_id": operation_id, "state": state}
        if state != "ROLLED_BACK":
            restore_operation(base, journal_path, existing)
    targets = target_paths(next_seeds)
    manifest = backup_targets(base, backup_root, targets)
    journal = {
        "schema_version": 1,
        "operation_id": operation_id,
        "owner": args.owner,
        "created_at": now_iso(),
        "state": "",
        "selection_revision": frontier.get("selection_revision"),
        "selected_idea_ids": selected_ids,
        "expected_source_hashes": source_hashes,
        "expected_queue_revision": int(queue.get("queue_revision") or 0),
        "target_manifest": manifest,
    }
    advance_journal(journal_path, journal, "PREPARED")
    failpoint(args.fail_after, "PREPARED")
    try:
        seeds_module.write_json(base / "ideation/IDEA_TRACK_SEEDS.json", next_seeds)
        expected_seed_file_sha256 = file_sha256(base / "ideation/IDEA_TRACK_SEEDS.json")
        journal["expected_track_seed_file_sha256"] = expected_seed_file_sha256
        atomic_write_json(journal_path, journal)
        materialize_command = [
            sys.executable,
            str(MATERIALIZE),
            "--project",
            str(project),
            "--all-admitted",
            "--baseline",
            args.baseline,
            "--metric",
            args.metric,
            "--dataset",
            args.dataset,
            "--gpu-hours",
            str(materialize_gpu_hours),
            "--walltime-hours",
            str(args.walltime_hours),
        ]
        if args.allow_fixture:
            materialize_command.append("--allow-fixture")
        materialized = run_json(materialize_command)
        for track in materialized.get("tracks") or []:
            if not isinstance(track, dict):
                continue
            track_id = str(track.get("track_id") or "")
            run_json([sys.executable, str(INNOVATION_LINT), "--project", str(project), "--packet", f"orchestrator/tracks/{track_id}/INNOVATION_PACKET.json"])
            run_json([sys.executable, str(PRELAUNCH_LINT), "--project", str(project), "--track-id", track_id])
        assert_source_hashes(
            base,
            {rel: source_hashes[rel] for rel in IMMUTABLE_SOURCE_RELS},
            label="immutable ideation authority",
        )
        assert_source_hashes(
            base,
            {"ideation/IDEA_TRACK_SEEDS.json": expected_seed_file_sha256},
            label="materialized track seeds",
        )
        journal["materialized_track_ids"] = [item.get("track_id") for item in materialized.get("tracks") or [] if isinstance(item, dict)]
        advance_journal(journal_path, journal, "packets_written_and_linted")
        failpoint(args.fail_after, "packets_written_and_linted")

        matrix_result = run_json([sys.executable, str(TRACK_MATRIX), "--project", str(project)])
        run_json([sys.executable, str(TRACK_MATRIX), "--project", str(project), "--check"])
        assert_source_hashes(
            base,
            {rel: source_hashes[rel] for rel in IMMUTABLE_SOURCE_RELS},
            label="immutable ideation authority",
        )
        assert_source_hashes(
            base,
            {"ideation/IDEA_TRACK_SEEDS.json": expected_seed_file_sha256},
            label="materialized track seeds",
        )
        journal["matrix_sha256"] = matrix_result.get("semantic_sha256")
        advance_journal(journal_path, journal, "matrix_committed")
        failpoint(args.fail_after, "matrix_committed")

        queue_result = commit_queue_rows(
            ena,
            project,
            base,
            selected_ids,
            int(journal["expected_queue_revision"]),
            candidate_costs,
        )
        journal["queue_result"] = queue_result
        advance_journal(journal_path, journal, "queue_rows_committed")
        failpoint(args.fail_after, "queue_rows_committed")
        advance_journal(journal_path, journal, "COMMITTED")
        return {
            "ok": True,
            "changed": True,
            "operation_id": operation_id,
            "state": "COMMITTED",
            "selected_idea_ids": selected_ids,
            "materialized_track_ids": journal.get("materialized_track_ids"),
            "queue_result": queue_result,
        }
    except BaseException as exc:
        journal = read_json(journal_path) or journal
        journal["failure"] = {"type": type(exc).__name__, "message": str(exc), "at": now_iso()}
        atomic_write_json(journal_path, journal)
        restore_operation(base, journal_path, journal)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--idea-id", action="append")
    parser.add_argument("--operation-id")
    parser.add_argument("--owner", default="portfolio-batch")
    parser.add_argument("--baseline", default="baseline_protocol")
    parser.add_argument("--metric", default="primary_metric")
    parser.add_argument("--dataset", default="target_dataset")
    parser.add_argument("--gpu-hours", type=float, default=0.0)
    parser.add_argument("--walltime-hours", type=float, default=1.0)
    parser.add_argument("--allow-fixture", action="store_true")
    parser.add_argument("--fail-after", choices=OPERATION_STATES[:-1], help=argparse.SUPPRESS)
    parser.add_argument("--recover-operation")
    args = parser.parse_args()
    project = Path(args.project).expanduser().resolve()
    base = project / ".autoreskill"
    try:
        with operation_lock(base):
            if args.recover_operation:
                journal_path, _ = operation_paths(base, args.recover_operation)
                journal = read_json(journal_path)
                if not journal:
                    raise RuntimeError(f"operation journal not found: {args.recover_operation}")
                payload = restore_operation(base, journal_path, journal)
            else:
                payload = execute(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
