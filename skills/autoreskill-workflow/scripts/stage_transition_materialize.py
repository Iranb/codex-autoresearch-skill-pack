#!/usr/bin/env python3
"""Materialize dependency-unlocked cross-dataset validation stages from ledger state."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import experiment_next_actions as queue_api  # noqa: E402
from parameter_transfer import required_dataset_ids  # noqa: E402


SKILLS_ROOT = Path(__file__).resolve().parents[2]
HPO_SCRIPT = SKILLS_ROOT / "autoreskill-run-experiment/scripts/dataset_group_hpo.py"
TERMINAL = {"terminal_positive", "terminal_negative"}


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def load_hpo() -> Any:
    spec = importlib.util.spec_from_file_location("stage_transition_group_hpo", HPO_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {HPO_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matrix_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in matrix.get("tracks", []) if isinstance(row, dict)]


def program_dataset_rows(program: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("dataset_id") or ""): row
        for row in program.get("target_datasets", [])
        if isinstance(row, dict) and row.get("required") is True and str(row.get("dataset_id") or "")
    }


def row_dataset(row: dict[str, Any]) -> str:
    return str(row.get("dataset_id") or row.get("dataset") or "")


def clear_runtime_fields(row: dict[str, Any]) -> None:
    for field in [
        "completed_at",
        "lease_owner",
        "lease_acquired_at",
        "lease_expires_at",
        "resource_allocation",
        "planned_resource_allocation",
        "backend_submit_intent",
        "backend_submit_intent_sha256",
        "backend_submit_receipt",
        "backend_submit_receipt_sha256",
        "backend_observations",
        "canonical_result_ref",
    ]:
        row.pop(field, None)


def stage2_support(
    queue: dict[str, Any],
    track_id: str,
    datasets: list[str],
    decision: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    group_id = str(decision.get("paired_dataset_group_id") or "")
    result: dict[str, dict[str, Any]] = {}
    for row in queue.get("rows", []):
        if not isinstance(row, dict) or str(row.get("track_id") or "") != track_id:
            continue
        if row.get("stage2_role") != "stage2_method_screen":
            continue
        if str(row.get("paired_dataset_group_id") or "") != group_id:
            continue
        dataset_id = row_dataset(row)
        if dataset_id in datasets:
            result[dataset_id] = row
    missing = sorted(set(datasets) - set(result))
    if missing:
        raise RuntimeError("paired Stage-2 rows are missing for: " + ", ".join(missing))
    nonpositive = sorted(dataset_id for dataset_id, row in result.items() if str(row.get("status") or "") != "terminal_positive")
    if nonpositive:
        raise RuntimeError("cross-dataset support requires terminal-positive Stage-2 rows for: " + ", ".join(nonpositive))
    return result


def latest_cross_decision(ledger: dict[str, Any], track_id: str) -> dict[str, Any]:
    rows = [
        row for row in ledger.get("cross_dataset_decisions", [])
        if isinstance(row, dict) and str(row.get("track_id") or "") == track_id
    ]
    return rows[-1] if rows else {}


def positive_decision_row_ids(ledger: dict[str, Any]) -> set[str]:
    return {
        str(row.get("queue_row_id") or "")
        for row in ledger.get("experiment_decisions", [])
        if isinstance(row, dict) and str(row.get("outcome_class") or "") == "valid_positive_candidate"
    }


def full_budget_support(queue: dict[str, Any], ledger: dict[str, Any], track_id: str, datasets: list[str]) -> dict[str, dict[str, Any]]:
    positive_ids = positive_decision_row_ids(ledger)
    result: dict[str, dict[str, Any]] = {}
    for row in queue.get("rows", []):
        if not isinstance(row, dict) or str(row.get("track_id") or "") != track_id:
            continue
        if row.get("validation_stage") not in {3, 4}:
            continue
        dataset_id = row_dataset(row)
        row_id = str(row.get("id") or "")
        if dataset_id in datasets and str(row.get("status") or "") == "terminal_positive" and row_id in positive_ids:
            result[dataset_id] = row
    return result


def budget_check(program: dict[str, Any], queue: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    budget = (program.get("search_budget") or {}).get("gpu_hour_budget")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(float(budget)) or float(budget) <= 0:
        raise RuntimeError("program claim contract lacks a finite positive gpu_hour_budget")
    existing = sum(queue_api.estimated_gpu_hours(row) or 0.0 for row in queue.get("rows", []) if isinstance(row, dict))
    proposed = sum(queue_api.estimated_gpu_hours(row) or 0.0 for row in rows)
    if existing + proposed > float(budget) + 1e-9:
        raise RuntimeError(
            f"stage materialization would exceed project GPU-hour budget ({existing + proposed:g} > {float(budget):g})"
        )


def full_budget_hours_by_dataset(review: dict[str, Any], datasets: list[str]) -> dict[str, float]:
    compute = review.get("compute_budget") if isinstance(review.get("compute_budget"), dict) else {}
    explicit = compute.get("full_budget_gpu_hours_by_dataset")
    result: dict[str, float] = {}
    if isinstance(explicit, dict):
        for dataset_id in datasets:
            value = explicit.get(dataset_id)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
                raise RuntimeError(f"full-budget GPU-hour estimate is invalid for {dataset_id}")
            result[dataset_id] = float(value)
        return result
    runtime = review.get("dataset_runtime_plan") if isinstance(review.get("dataset_runtime_plan"), dict) else {}
    candidates = runtime.get("candidate_datasets") if isinstance(runtime.get("candidate_datasets"), list) else []
    by_dataset = {
        str(row.get("dataset_id") or ""): row.get("estimated_gpu_hours")
        for row in candidates if isinstance(row, dict) and str(row.get("dataset_id") or "")
    }
    if set(datasets).issubset(by_dataset):
        for dataset_id in datasets:
            value = by_dataset[dataset_id]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
                raise RuntimeError(f"dataset_runtime_plan GPU-hour estimate is invalid for {dataset_id}")
            result[dataset_id] = float(value)
        return result
    total = compute.get("gpu_hours")
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not math.isfinite(float(total)) or float(total) <= 0:
        raise RuntimeError(
            "Stage-3/4 materialization requires compute_budget.full_budget_gpu_hours_by_dataset, "
            "dataset_runtime_plan estimates, or a finite compute_budget.gpu_hours total"
        )
    return {dataset_id: float(total) / len(datasets) for dataset_id in datasets}


def build_full_budget_rows(
    program: dict[str, Any],
    review: dict[str, Any],
    track_id: str,
    support: dict[str, dict[str, Any]],
    decision: dict[str, Any],
) -> list[dict[str, Any]]:
    dataset_contracts = program_dataset_rows(program)
    full_budget_hours = full_budget_hours_by_dataset(review, list(support))
    dependencies = [str(support[dataset_id]["id"]) for dataset_id in support]
    decision_ref = str(decision.get("aggregate_ref") or decision.get("decision_id") or "")
    rows: list[dict[str, Any]] = []
    for dataset_id, source in support.items():
        dataset_row = dataset_contracts.get(dataset_id, {})
        role = str(dataset_row.get("role") or "contrast")
        stage = 3 if role == "primary" else 4
        row = copy.deepcopy(source)
        clear_runtime_fields(row)
        source_group = row.pop("paired_dataset_group_id", None)
        row.pop("stage2_role", None)
        row_id = f"full-{track_id}-stage{stage}-{stable_hash(dataset_id)[:10]}"
        baseline_ref = str(dataset_row.get("matched_baseline_ref") or (review.get("dataset_group_plan") or {}).get(
            "baseline_ref_by_dataset", {}
        ).get(dataset_id) or "")
        row.update(
            {
                "id": row_id,
                "priority": 30 if stage == 3 else 31,
                "status": "ready",
                "role": "single_innovation",
                "dataset": dataset_id,
                "dataset_id": dataset_id,
                "dataset_role": role,
                "next_action": "run the frozen method and matched baseline at full budget",
                "updated_at": queue_api.now_iso(),
                "decision_class": "falsify_core_mechanism" if stage == 3 else "confirm_generalization",
                "why_now": "ledger-backed paired Stage-2 support unlocks both full-budget dataset legs",
                "expected_decision_change": "support on every required dataset unlocks HPO or crossed confirmation; a valid negative scopes the claim",
                "comparison_source": "vs matched reproduced baseline",
                "baseline_freeze_ref": baseline_ref,
                "estimated_gpu_hours": full_budget_hours[dataset_id],
                "resource_request": {
                    **(row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}),
                    "gpu_count": 1,
                    "estimated_gpu_hours": full_budget_hours[dataset_id],
                },
                "validation_stage": stage,
                "validation_stage_name": "full_budget_primary" if stage == 3 else "full_budget_contrast",
                "validation_prerequisites": [decision_ref],
                "depends_on_rows": dependencies,
                "unlock_rules": {"requires_positive_rows": dependencies},
                "reused_canonical_evidence_refs": [decision_ref],
                "evidence_tier": "claim_eligible",
                "claim_eligible": True,
                "claim_ceiling": "cross_dataset_candidate",
                "launch_mode": "first_use",
                "source_paired_dataset_group_id": source_group,
                "row_revision": 0,
            }
        )
        row["protocol"] = stable_hash(
            {
                "prior_protocol": source.get("protocol"),
                "validation_stage": stage,
                "dataset_id": dataset_id,
                "baseline_freeze_ref": baseline_ref,
                "frozen_parameter_profile_sha256": source.get("frozen_parameter_profile_sha256"),
            }
        )
        row["launch_identity_hash"] = stable_hash(
            {
                "track_id": track_id,
                "row_id": row_id,
                "validation_stage": stage,
                "dataset_id": dataset_id,
                "selection_fingerprint": row.get("selection_fingerprint"),
                "protocol": row["protocol"],
            }
        )
        rows.append(row)
    return rows


def registered_confirmation_seeds(review: dict[str, Any], program: dict[str, Any]) -> list[Any]:
    policy = review.get("stability_seed_policy") if isinstance(review.get("stability_seed_policy"), dict) else {}
    seeds = policy.get("planned_random_seeds") or policy.get("registered_seed_set") or []
    if not isinstance(seeds, list):
        return []
    unique: list[Any] = []
    for seed in seeds:
        if seed not in unique:
            unique.append(seed)
    maximum = int((program.get("promotion_rule") or {}).get("max_random_seeds") or 0)
    return unique if 1 <= len(unique) <= min(3, maximum) else []


def build_confirmation_rows(
    program: dict[str, Any],
    review: dict[str, Any],
    track_id: str,
    support: dict[str, dict[str, Any]],
    hpo_decision: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    seeds = registered_confirmation_seeds(review, program)
    if not seeds:
        raise RuntimeError("Stage-6 confirmation requires one to three preregistered planned_random_seeds")
    dependencies = [str(row["id"]) for row in support.values()]
    group_id = f"confirm-{track_id}-{stable_hash({'rows': dependencies, 'seeds': seeds, 'hpo': hpo_decision})[:16]}"
    dataset_contracts = program_dataset_rows(program)
    rows: list[dict[str, Any]] = []
    for dataset_id, source in support.items():
        baseline_ref = str(dataset_contracts.get(dataset_id, {}).get("matched_baseline_ref") or source.get("baseline_freeze_ref") or "")
        for arm in ["baseline", "method"]:
            row = copy.deepcopy(source)
            clear_runtime_fields(row)
            row.pop("stage2_role", None)
            row_id = f"{group_id}-{stable_hash({'dataset': dataset_id, 'arm': arm})[:10]}"
            row.update(
                {
                    "id": row_id,
                    "priority": 50,
                    "status": "ready",
                    "role": "stability",
                    "dataset": dataset_id,
                    "dataset_id": dataset_id,
                    "next_action": f"run crossed {arm} confirmation on the preregistered seed set",
                    "updated_at": queue_api.now_iso(),
                    "decision_class": "close_required_claim",
                    "why_now": "every full-budget dataset leg has ledger-backed positive support",
                    "expected_decision_change": "a complete matched dataset-by-seed-by-arm matrix can promote or downgrade the claim",
                    "baseline_freeze_ref": baseline_ref,
                    "comparison_source": "vs matched reproduced baseline",
                    "validation_stage": 6,
                    "validation_stage_name": "crossed_confirmation",
                    "validation_prerequisites": ["cross_dataset_full_budget_support"],
                    "depends_on_rows": dependencies,
                    "unlock_rules": {"requires_positive_rows": dependencies},
                    "evidence_tier": "claim_eligible",
                    "claim_eligible": True,
                    "claim_ceiling": "cross_dataset_promotable",
                    "launch_mode": "claim_promotion",
                    "experiment_family_id": f"family-{track_id}",
                    "replication_group_id": f"replication-{track_id}",
                    "crossed_confirmation_group_id": group_id,
                    "registered_seed_set": seeds,
                    "seeds": seeds,
                    "seed_count": len(seeds),
                    "confirmation_arm": arm,
                    "selected_hpo_configuration": (hpo_decision or {}).get("selected_configuration"),
                    "hpo_group_decision_id": (hpo_decision or {}).get("decision_id"),
                    "row_revision": 0,
                }
            )
            row["protocol"] = stable_hash(
                {
                    "prior_protocol": source.get("protocol"),
                    "dataset_id": dataset_id,
                    "arm": arm,
                    "seeds": seeds,
                    "hpo_decision": (hpo_decision or {}).get("decision_sha256"),
                }
            )
            row["launch_identity_hash"] = stable_hash(
                {
                    "track_id": track_id,
                    "row_id": row_id,
                    "dataset_id": dataset_id,
                    "arm": arm,
                    "seeds": seeds,
                    "protocol": row["protocol"],
                }
            )
            rows.append(row)
    return rows


def proposed_rows(project: Path, queue: dict[str, Any], track_filter: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    base = project / ".autoreskill"
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    if str(program.get("claim_scope") or "") != "cross_dataset_method":
        return [], [{"track_id": "", "code": "program_claim_not_cross_dataset_method"}]
    existing_ids = {str(row.get("id") or "") for row in queue.get("rows", []) if isinstance(row, dict)}
    additions: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    hpo = load_hpo()
    for plan_row in matrix_rows(matrix):
        track_id = str(plan_row.get("track_id") or "")
        if track_filter and track_id not in track_filter:
            continue
        if str(plan_row.get("claim_role") or "") != "method_candidate":
            continue
        if str(plan_row.get("track_role") or "") != "primary":
            blockers.append({"track_id": track_id, "code": "primary_reselection_required_before_claim_bearing_stages"})
            continue
        review = read_json(base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json", {}) or {}
        datasets = required_dataset_ids(program, review)
        decision = latest_cross_decision(ledger, track_id)
        if not decision:
            blockers.append({"track_id": track_id, "code": "cross_dataset_decision_missing"})
            continue
        if str(decision.get("verdict") or "") != "cross_dataset_supported":
            blockers.append({"track_id": track_id, "code": f"cross_dataset_{decision.get('verdict') or 'unresolved'}"})
            continue
        try:
            stage2 = stage2_support(queue, track_id, datasets, decision)
        except RuntimeError as exc:
            blockers.append({"track_id": track_id, "code": str(exc)})
            continue
        full_rows = [
            row for row in queue.get("rows", [])
            if isinstance(row, dict) and str(row.get("track_id") or "") == track_id and row.get("validation_stage") in {3, 4}
            and str(row.get("status") or "") not in {"dropped", "superseded"}
        ]
        if not full_rows:
            additions.extend(build_full_budget_rows(program, review, track_id, stage2, decision))
            continue
        full_support = full_budget_support(queue, ledger, track_id, datasets)
        if set(full_support) != set(datasets):
            blockers.append({"track_id": track_id, "code": "full_budget_scientific_decision_pending"})
            continue
        policy = review.get("hpo_search_policy") if isinstance(review.get("hpo_search_policy"), dict) else {}
        hpo_eligible = (
            str(policy.get("activation_status") or "").lower() == "eligible"
            and str(policy.get("sensitivity_question") or "").strip() != ""
        )
        hpo_decisions = [
            row for row in ledger.get("hpo_group_decisions", [])
            if isinstance(row, dict) and str(row.get("track_id") or "") == track_id
        ]
        hpo_decision = hpo_decisions[-1] if hpo_decisions else None
        if hpo_eligible and hpo_decision is None:
            try:
                hpo_rows, detail = hpo.build_trial_rows(base, queue, track_id)
            except RuntimeError as exc:
                blockers.append({"track_id": track_id, "code": str(exc)})
                continue
            additions.extend(hpo_rows)
            if not hpo_rows:
                blockers.append({"track_id": track_id, "code": str(detail.get("reason") or "hpo_reconcile_or_finalize_required")})
            continue
        confirmation_exists = any(
            isinstance(row, dict) and str(row.get("track_id") or "") == track_id and row.get("validation_stage") == 6
            and str(row.get("status") or "") not in {"dropped", "superseded"}
            for row in queue.get("rows", [])
        )
        if not confirmation_exists:
            try:
                additions.extend(build_confirmation_rows(program, review, track_id, full_support, hpo_decision))
            except RuntimeError as exc:
                blockers.append({"track_id": track_id, "code": str(exc)})
    return [row for row in additions if str(row.get("id") or "") not in existing_ids], blockers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--track-id", action="append")
    parser.add_argument("--expected-queue-revision", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    project = Path(args.project).expanduser().resolve()
    base = project / ".autoreskill"
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    mode = str(program.get("enforcement_mode") or "legacy")
    queue_path = project / queue_api.QUEUE_REL
    try:
        with queue_api.queue_lock(queue_path):
            queue = queue_api.load_queue(project)
            if not queue:
                raise RuntimeError("NEXT_EXPERIMENT_QUEUE.json is missing")
            revision = int(queue.get("queue_revision") or 0)
            if args.expected_queue_revision is not None and revision != args.expected_queue_revision:
                raise RuntimeError("queue revision changed before stage materialization")
            rows, blockers = proposed_rows(project, queue, set(args.track_id or []))
            payload = {
                "ok": True,
                "dry_run": args.dry_run,
                "enforcement_mode": mode,
                "queue_revision": revision,
                "proposed_row_ids": [str(row.get("id") or "") for row in rows],
                "blockers": blockers,
            }
            if args.dry_run or not rows:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                return 0
            if mode != "enforced":
                raise RuntimeError("stage-transition writes require enforcement_mode=enforced; use --dry-run in shadow")
            budget_check(program, queue, rows)
            queue.setdefault("rows", []).extend(rows)
            queue["queue_revision"] = revision + 1
            queue["updated_at"] = queue_api.now_iso()
            queue.setdefault("decision_log", []).append(
                {
                    "timestamp": queue_api.now_iso(),
                    "decision": "materialize_ledger_unlocked_validation_stages",
                    "rationale": "create every currently dependency-unlocked Stage 3-6 row without inferring scientific support",
                    "row_ids": payload["proposed_row_ids"],
                    "evidence_paths": ["ideation/IDEA_DECISION_LEDGER.json"],
                }
            )
            checked = queue_api.validate_queue(queue, project=project)
            if not checked.get("ok"):
                raise RuntimeError("materialized stage rows are invalid: " + "; ".join(checked.get("errors") or []))
            queue_api.atomic_write_json(queue_path, queue)
            payload["changed"] = True
            payload["queue_revision"] = queue["queue_revision"]
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
