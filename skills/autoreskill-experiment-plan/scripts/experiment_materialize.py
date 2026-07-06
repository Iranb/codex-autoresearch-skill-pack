#!/usr/bin/env python3
"""Materialize INNOVATION_PACKET and EXPERIMENT_REVIEW_PACKET from a selected idea."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hpo_policy_lint import default_hpo_search_policy


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def first_candidate(pool: Any) -> dict[str, Any]:
    rows = []
    if isinstance(pool, dict):
        for key in ["candidates", "tracks", "ideas"]:
            if isinstance(pool.get(key), list):
                rows = pool[key]
                break
    elif isinstance(pool, list):
        rows = pool
    for row in rows:
        if isinstance(row, dict) and str(row.get("status") or row.get("verdict") or "").lower() in {"advance", "advance_with_constraints"}:
            return row
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def selected_idea_from_pool(pool: Any) -> dict[str, Any]:
    if not isinstance(pool, dict):
        return {}
    ideas = pool.get("ideas")
    if not isinstance(ideas, list):
        ideas = pool.get("candidates")
    if not isinstance(ideas, list):
        return {}
    selected_id = str(pool.get("selected_idea_id") or pool.get("selected_candidate_id") or "").strip()
    for row in ideas:
        if isinstance(row, dict) and selected_id and str(row.get("id") or "").strip() == selected_id:
            return row
    for row in ideas:
        if isinstance(row, dict) and str(row.get("status") or "").lower() == "selected":
            return row
    return {}


def locked_protocol(pool: Any) -> dict[str, Any]:
    if isinstance(pool, dict) and isinstance(pool.get("locked_protocol"), dict):
        return pool["locked_protocol"]
    return {}


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def jsonish_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def selected_paper_bundle(idea: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
    bundle = (
        idea.get("paper_innovation_bundle")
        or idea.get("innovation_bundle")
        or idea.get("three_innovation_bundle")
        or paper.get("innovation_bundle")
        or paper.get("innovation_points")
    )
    storyline = (
        idea.get("paper_storyline")
        or idea.get("storyline")
        or paper.get("storyline")
        or paper.get("paper_storyline")
    )

    bundle_out = jsonish_copy(bundle) if isinstance(bundle, list) else []
    storyline_out = jsonish_copy(storyline) if isinstance(storyline, dict) else {}
    thesis = paper.get("paper_thesis") or idea.get("paper_thesis") or idea.get("thesis")
    if present(thesis) and isinstance(storyline_out, dict) and not present(storyline_out.get("paper_thesis")):
        storyline_out["paper_thesis"] = thesis
    return bundle_out, storyline_out


def choose(cli_value: str, default_value: str, fallback: Any) -> Any:
    if cli_value != default_value:
        return cli_value
    return fallback if fallback not in (None, "", [], {}) else default_value


def default_dataset_runtime_plan(dataset: str, gpu_hours: float, walltime_hours: float) -> dict[str, Any]:
    walltime = walltime_hours if walltime_hours > 0 else 1.0
    gpu = gpu_hours if gpu_hours > 0 else walltime
    return {
        "candidate_datasets": [
            {
                "dataset_id": dataset,
                "scale_class": "small_multiclass",
                "num_classes": "estimate_required",
                "train_samples": "estimate_required",
                "eval_samples": "estimate_required",
                "epochs_or_steps": "estimate_required",
                "estimated_minutes_per_epoch": round(max(walltime * 60.0, 1.0), 3),
                "estimated_walltime_hours": walltime,
                "estimated_gpu_hours": gpu,
                "estimation_basis": "placeholder from materialize; replace with dataset counts, epoch count, batch size, backend GPU probe, and prior logs before launch",
                "purpose": "feasibility_first",
            }
        ],
        "feasibility_first_dataset_id": dataset,
        "first_run_scale_class": "small_multiclass",
        "largest_dataset_id": dataset,
        "largest_dataset_deferred": True,
        "escalation_criteria": [
            "smoke run passes",
            "metric parser and data split are verified",
            "innovation mechanism shows non-degenerate behavior on the feasibility dataset",
        ],
        "runtime_risk": "Replace placeholder estimates before launch; largest dataset remains deferred for confirmation/final-scale evidence.",
    }


def default_dataset_requirement_inventory(dataset: str) -> dict[str, Any]:
    return {
        "required_datasets": [
            {
                "dataset_id": dataset,
                "dataset_name": dataset,
                "claim_role": "method_validation",
                "reason_required": "placeholder from materialize; replace with a full dataset inventory from baseline scripts, evidence, benchmark norms, and selected claim before launch",
                "baseline_supported": "probe_required",
                "availability": "unknown",
                "scale_class": "small_multiclass",
                "num_classes": "estimate_required",
                "train_samples": "estimate_required",
                "eval_samples": "estimate_required",
                "native_protocol_ref": "probe_required",
                "native_epochs_or_steps": "probe_required",
                "native_warmup_or_schedule": "probe_required",
                "data_root_or_probe": "probe_required",
                "selection_status": "selected_first",
            }
        ],
        "selection_rule": "choose_smallest_available_baseline_supported_required_dataset_for_method_validation",
        "method_validation_dataset_id": dataset,
        "smallest_available_required_dataset_id": dataset,
        "deferred_dataset_ids": [],
        "rejected_datasets": [],
    }


def selected_mechanism_type(idea: dict[str, Any], pool_candidate: dict[str, Any], protocol: dict[str, Any]) -> str:
    contract = idea.get("innovation_search_contract") if isinstance(idea.get("innovation_search_contract"), dict) else {}
    for value in [
        contract.get("mechanism_type"),
        idea.get("mechanism_type"),
        idea.get("type"),
        pool_candidate.get("mechanism_type"),
        pool_candidate.get("type"),
        protocol.get("mechanism_type"),
    ]:
        text = str(value or "").strip().upper()
        if text in {"ALGO", "CODE", "PARAM"}:
            return text
    return "ALGO"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--track-id")
    parser.add_argument("--baseline", default="baseline_protocol")
    parser.add_argument("--metric", default="primary_metric")
    parser.add_argument("--dataset", default="target_dataset")
    parser.add_argument("--gpu-hours", type=float, default=0)
    parser.add_argument("--walltime-hours", type=float, default=1)
    parser.add_argument("--allow-fixture", action="store_true")
    args = parser.parse_args()

    base = ar(args.project)
    pool = read_json(base / "ideation/CANDIDATE_POOL.json", {})
    idea_pool_path = "ideation/EXPERIMENT_IDEA_POOL.json"
    legacy_planner_idea_pool_path = "planner/EXPERIMENT_IDEA_POOL.json"
    legacy_candidate_library_path = "planner/EXPERIMENT_CANDIDATE_LIBRARY.json"
    idea_pool = read_json(base / idea_pool_path, {})
    if not idea_pool:
        idea_pool_path = legacy_planner_idea_pool_path
        idea_pool = read_json(base / idea_pool_path, {})
    if not idea_pool:
        idea_pool_path = legacy_candidate_library_path
        idea_pool = read_json(base / idea_pool_path, {})
    pool_candidate = first_candidate(pool)
    idea = selected_idea_from_pool(idea_pool) or pool_candidate
    protocol = locked_protocol(idea_pool)
    evidence_ids = idea.get("paperNexus_evidence_ids") or idea.get("evidence_ids") or pool_candidate.get("evidence_ids") or []
    if not evidence_ids and not args.allow_fixture:
        raise SystemExit("cannot materialize experiment plan without idea evidence_ids")
    track_id = args.track_id or idea.get("track_id") or pool_candidate.get("track_id") or "track_001"
    selected_idea_id = idea.get("id") or idea.get("idea_id") or idea.get("candidate_id") or track_id
    baseline = choose(args.baseline, "baseline_protocol", protocol.get("baseline_reference") or protocol.get("baseline_training_protocol"))
    dataset = choose(args.dataset, "target_dataset", protocol.get("dataset"))
    data_split = protocol.get("data_split") or "locked split required before launch"
    primary_metric = choose(args.metric, "primary_metric", protocol.get("primary_metric"))
    metric_direction = protocol.get("metric_direction") or "higher"
    mechanism_type = selected_mechanism_type(idea, pool_candidate, protocol)
    baseline_training_protocol = protocol.get("baseline_training_protocol") or baseline
    baseline_eval_protocol = protocol.get("baseline_eval_protocol") or "same dataset split and primary metric"
    evaluation_command = protocol.get("evaluation_command") or "locked evaluation command required before launch"
    protected_paths = protocol.get("protected_paths", [])
    one_variable_change = idea.get("one_variable_change") or "selected idea changes exactly one planned variable"
    falsifier = idea.get("falsifier") or "no improvement over the matched baseline"
    paper_innovation_bundle, paper_storyline = selected_paper_bundle(idea)
    dataset_runtime_plan = (
        protocol.get("dataset_runtime_plan")
        or idea.get("dataset_runtime_plan")
        or default_dataset_runtime_plan(dataset, args.gpu_hours, args.walltime_hours)
    )
    dataset_requirement_inventory = (
        protocol.get("dataset_requirement_inventory")
        or idea.get("dataset_requirement_inventory")
        or default_dataset_requirement_inventory(dataset)
    )
    stability_seed_policy = (
        protocol.get("stability_seed_policy")
        or idea.get("stability_seed_policy")
        or {
            "max_random_seeds": 3,
            "planned_seed_count": 1,
            "planned_random_seeds": [],
            "claim_rule": "Use at most three random seeds for stability validation; single-seed evidence remains pilot-only unless supported by ablation/confirmation.",
            "scope_note": "This caps experiment random seeds, not IDEA_TRACK_SEEDS track candidates.",
        }
    )
    hpo_search_policy = (
        protocol.get("hpo_search_policy")
        or idea.get("hpo_search_policy")
        or default_hpo_search_policy(mechanism_type)
    )
    evidence_paths = [".autoreskill/evidence_cart.jsonl"]
    design_path = ".autoreskill/papernexus/research_controller/design-review.json"
    innovation = {
        "schema_version": 1,
        "created_at": now(),
        "selected_idea_fragment_id": track_id,
        "supporting_idea_fragment_ids": [track_id],
        "idea_pool_path": idea_pool_path,
        "selected_idea_id": selected_idea_id,
        "baseline": baseline,
        "primary_metric": primary_metric,
        "dataset_or_benchmark": dataset,
        "dataset": dataset,
        "paper_innovation_bundle": paper_innovation_bundle,
        "paper_storyline": paper_storyline,
        "one_variable_change": one_variable_change,
        "falsifier": falsifier,
        "falsifiers": [falsifier],
        "fixed_budget": {"gpu_hours": args.gpu_hours, "walltime_hours": args.walltime_hours},
        "dataset_requirement_inventory": dataset_requirement_inventory,
        "dataset_runtime_plan": dataset_runtime_plan,
        "stability_seed_policy": stability_seed_policy,
        "hpo_search_policy": hpo_search_policy,
        "evidence_paths": evidence_paths,
        "idea_evidence_export_path": ".autoreskill/papernexus/idea_catalyst_evidence_export.json",
        "evidence_boundaries": {
            "source_backed": evidence_ids or evidence_paths,
            "agent_inferred": [one_variable_change],
            "speculative": ["expected metric impact remains unverified until experiment reconciliation"],
            "unsupported": ["do not promote manuscript claims before non-fixture results and analysis"],
        },
        "paperNexus_corpus": read_json(base / "goal_state.json", {}).get("paperNexus", {}).get("corpus"),
        "source_backing_summary": "Evidence ids are required for claim promotion; fixture mode is not graph-grounded.",
        "controller_design_review_path": design_path if (base / design_path.removeprefix(".autoreskill/")).exists() else None,
        "claim_strength": "provisional" if not evidence_ids else "bounded",
        "fixture": bool(args.allow_fixture and not evidence_ids),
    }
    review = {
        "schema_version": 1,
        "created_at": now(),
        "status": "reviewed",
        "track_id": track_id,
        "claim_ids": [f"{track_id}_claim"],
        "hypothesis": "The selected one-variable change improves the primary metric under a fixed baseline protocol.",
        "novelty_basis": "Must be grounded in PaperNexus evidence before strong manuscript claims.",
        "idea_pool_path": idea_pool_path,
        "selected_idea_id": selected_idea_id,
        "idea_generation_scope": "ideation-stage experiment idea pool; no experiment-plan generation",
        "paper_innovation_bundle": paper_innovation_bundle,
        "paper_storyline": paper_storyline,
        "one_variable_change": True,
        "baseline_reference": baseline,
        "baseline_training_protocol": baseline_training_protocol,
        "baseline_eval_protocol": baseline_eval_protocol,
        "evaluation_command": evaluation_command,
        "dataset": dataset,
        "dataset_requirement_inventory": dataset_requirement_inventory,
        "dataset_runtime_plan": dataset_runtime_plan,
        "stability_seed_policy": stability_seed_policy,
        "hpo_search_policy": hpo_search_policy,
        "data_split": data_split,
        "primary_metric": primary_metric,
        "metric_direction": metric_direction,
        "secondary_metrics": ["runtime", "stability"],
        "ablation_plan": ["remove the proposed one-variable change"],
        "falsifiers": [falsifier],
        "stop_rules": ["stop if dry-run fails after bounded repair", "stop if metric/dataset drift is detected"],
        "compute_budget": {"gpu_hours": args.gpu_hours, "walltime_hours": args.walltime_hours},
        "protected_paths": protected_paths,
        "expected_artifacts": ["EXPERIMENT_MANIFEST.json", "dry_run.log", "REMOTE_RUN.json", "EXPERIMENT_LEDGER.json"],
        "paperNexus_norms": ["See evidence_cart and PaperNexus artifacts."],
        "experiment_cost_norms": {"gpu_hours": args.gpu_hours, "walltime_hours": args.walltime_hours},
        "non_promotion_signals": ["single seed only", "fixture mode", "missing graph-grounded novelty evidence", "low-fidelity HPO scout evidence"],
    }
    write_json(base / "orchestrator/INNOVATION_PACKET.json", innovation)
    write_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json", review)
    write_text(base / "planner/EXPERIMENT_PLAN.md", "# Experiment Plan\n\nBaseline-first, one-variable, dry-run-gated plan.\n")
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "experiment_plan", "action": "materialize_experiment_plan", "details": {"track_id": track_id, "fixture": innovation["fixture"]}})
    print(json.dumps({"ok": True, "innovation_packet": "orchestrator/INNOVATION_PACKET.json", "experiment_review_packet": "planner/EXPERIMENT_REVIEW_PACKET.json"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
