#!/usr/bin/env python3
"""Materialize and lint TRACK_PLAN_MATRIX from IDEA_TRACK_SEEDS."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
]

READY_EVIDENCE = {"passed", "complete", "completed", "graph_closed", "source_backed", "not_required"}
LAUNCH_STATUSES = {"ready", "blocked", "diagnostic_only", "parked"}
READY_PACKET_STATUSES = {"reviewed", "ready", "approved", "pass", "passed"}
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


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def review_ready(review: dict[str, Any]) -> bool:
    status = normalized(review.get("status") or review.get("launch_status"))
    if status and status not in READY_PACKET_STATUSES:
        return False
    gate = review.get("evidence_import_gate") if isinstance(review.get("evidence_import_gate"), dict) else {}
    gate_status = normalized(gate.get("status"))
    return (
        present(review.get("baseline_code"))
        and present(review.get("dataset"))
        and present(review.get("dataset_runtime_plan"))
        and present(review.get("data_split"))
        and present(review.get("primary_metric"))
        and present(review.get("evaluation_command"))
        and gate_status in {"passed", "not_required"}
    )


def evidence_status(seed: dict[str, Any], review: dict[str, Any], selected: bool) -> str:
    if selected:
        gate = review.get("evidence_import_gate") if isinstance(review.get("evidence_import_gate"), dict) else {}
        status = str(gate.get("status") or "").strip()
        if status:
            return status
    if present(seed.get("evidence_debt")):
        return "blocked"
    return "source_backed"


def blocked_reason(seed: dict[str, Any], review: dict[str, Any], selected: bool) -> str:
    reasons: list[str] = []
    if selected and not review_ready(review):
        reasons.append("selected track is waiting for baseline/protocol/evidence closure")
    if present(seed.get("evidence_debt")):
        debt = seed.get("evidence_debt")
        reasons.append("evidence debt: " + ", ".join(str(item) for item in debt) if isinstance(debt, list) else f"evidence debt: {debt}")
    if not reasons and not selected:
        reasons.append("alternate seed parked until the primary track fails or reviewer risk requires repair")
    return "; ".join(reasons)


def default_promotion_gate(seed: dict[str, Any], review: dict[str, Any], selected: bool) -> dict[str, Any]:
    if selected and isinstance(review.get("promotion_gate"), dict):
        return review["promotion_gate"]
    return {
        "stage": "candidate",
        "promotion_requires": ["linked_ablation", "confirmation_or_second_seed"],
        "claim_policy": "seed rows are not launch approval; promoted evidence is required for manuscript claims",
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


def row_from_seed(seed: dict[str, Any], review: dict[str, Any], innovation: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    selected = str(seed.get("track_id") or "") == str(review.get("track_id") or "") or str(seed.get("idea_id") or "") == str(review.get("selected_idea_id") or "")
    ready = selected and review_ready(review)
    status = "ready" if ready else "blocked" if selected else "parked"
    baseline_code = review.get("baseline_code") if selected and present(review.get("baseline_code")) else {"status": "unresolved", "reason": "baseline lock required before launch"}
    compute_budget = review.get("compute_budget") if selected and present(review.get("compute_budget")) else {"status": "bounded_seed", "gpu_hours": 0, "walltime_hours": 0}
    hpo_policy = review.get("hpo_search_policy") or innovation.get("hpo_search_policy")
    return {
        "track_id": seed.get("track_id"),
        "branch_id": branch_id(seed, selected, decision),
        "idea_id": seed.get("idea_id"),
        "idea_decision_ref": decision_ref(seed, decision),
        "idea_lifecycle_status": decision.get("lifecycle_status"),
        "idea_failure_class": decision.get("failure_class"),
        "track_role": seed.get("track_role"),
        "selected_for_review": selected,
        "source_seed_path": "ideation/IDEA_TRACK_SEEDS.json",
        "idea_pool_path": review.get("idea_pool_path") or innovation.get("idea_pool_path") or "ideation/EXPERIMENT_IDEA_POOL.json",
        "baseline_code": baseline_code,
        "dataset": review.get("dataset") if selected and present(review.get("dataset")) else "unresolved_dataset_for_track",
        "dataset_runtime_plan_ref": "planner/EXPERIMENT_REVIEW_PACKET.json:dataset_runtime_plan" if selected and present(review.get("dataset_runtime_plan")) else "unresolved_dataset_runtime_plan_for_track",
        "split": review.get("data_split") if selected and present(review.get("data_split")) else "unresolved_split_for_track",
        "primary_metric": review.get("primary_metric") if selected and present(review.get("primary_metric")) else "unresolved_primary_metric",
        "metric_direction": review.get("metric_direction") or "higher",
        "eval_command": review.get("evaluation_command") if selected and present(review.get("evaluation_command")) else "unresolved_eval_command",
        "compute_budget": compute_budget,
        "evidence_closure_status": evidence_status(seed, review, selected),
        "launch_status": status,
        "blocked_reason": "" if ready else blocked_reason(seed, review, selected),
        "promotion_gate": default_promotion_gate(seed, review, selected),
        "hpo_search_policy_ref": "planner/EXPERIMENT_REVIEW_PACKET.json:hpo_search_policy" if selected and present(hpo_policy) else "not_applicable_until_track_selected",
        "hpo_search_method": hpo_policy.get("search_method") if selected and isinstance(hpo_policy, dict) else "not_applicable",
        "one_variable_change": seed.get("one_variable_change"),
        "expected_metric_effect": seed.get("expected_metric_effect"),
        "minimum_pilot": seed.get("minimum_pilot"),
        "kill_condition": seed.get("kill_condition"),
        "red_line_risks": seed.get("red_line_risks") or [],
        "evidence_debt": seed.get("evidence_debt") or [],
        "ablation_required": seed.get("ablation_required") is True,
        "confirmation_required": seed.get("confirmation_required") is True,
    }


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json", {}) or {}
    decisions = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json", {}) or {}
    innovation = read_json(base / "orchestrator/INNOVATION_PACKET.json", {}) or {}
    rows = rows_from_payload(seeds)
    decisions_by_idea = decision_rows_by_idea(decisions)
    matrix = {
        "schema_version": 1,
        "generated_at": now(),
        "artifact": "TRACK_PLAN_MATRIX",
        "source_track_seed_path": "ideation/IDEA_TRACK_SEEDS.json",
        "source_review_packet_path": "planner/EXPERIMENT_REVIEW_PACKET.json",
        "source_idea_decision_ledger_path": "ideation/IDEA_DECISION_LEDGER.json",
        "bie_config": DEFAULT_BIE_CONFIG,
        "policy": "bounded_explore_exploit_matrix_seed_rows_are_not_launch_approval",
        "tracks": [row_from_seed(seed, review, innovation, decisions_by_idea.get(str(seed.get("idea_id")), {})) for seed in rows],
    }
    return matrix


def lint(project: str) -> dict[str, Any]:
    base = ar(project)
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
    rows_by_track = {str(row.get("track_id")): row for row in rows if present(row.get("track_id"))}
    for seed in seed_rows:
        track_id = str(seed.get("track_id") or "")
        if track_id and track_id not in rows_by_track:
            missing.append(f"TRACK_PLAN_MATRIX missing seed track {track_id}")
    for index, row in enumerate(rows):
        prefix = f"tracks[{index}]"
        for field in REQUIRED_ROW_FIELDS:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        launch_status = normalized(row.get("launch_status"))
        if launch_status and launch_status not in LAUNCH_STATUSES:
            missing.append(f"{prefix}.launch_status must be ready/blocked/diagnostic_only/parked")
        if row.get("ablation_required") is not True:
            missing.append(f"{prefix}.ablation_required=true")
        if row.get("confirmation_required") is not True:
            missing.append(f"{prefix}.confirmation_required=true")
        if launch_status == "ready":
            if normalized(row.get("evidence_closure_status")) not in READY_EVIDENCE:
                missing.append(f"{prefix}.evidence_closure_status must be ready for launch")
            if present(row.get("blocked_reason")):
                missing.append(f"{prefix}.blocked_reason must be empty for ready tracks")
            gate = row.get("promotion_gate") if isinstance(row.get("promotion_gate"), dict) else {}
            if gate.get("ablation_required") is False or gate.get("confirmation_required") is False:
                missing.append(f"{prefix}.promotion_gate must preserve ablation/confirmation requirements")
        elif not present(row.get("blocked_reason")):
            warnings.append(f"{prefix}.blocked_reason recommended for non-ready tracks")
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
    write_json(ar(args.project) / "orchestrator/TRACK_PLAN_MATRIX.json", payload)
    append_jsonl(
        ar(args.project) / "decision_log.jsonl",
        {"ts": now(), "stage": "experiment_plan", "action": "track_plan_matrix", "details": {"track_count": len(payload["tracks"])}},
    )
    print(json.dumps({"ok": True, "path": "orchestrator/TRACK_PLAN_MATRIX.json", "track_count": len(payload["tracks"])}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
