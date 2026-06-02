#!/usr/bin/env python3
"""Manage portable .autoreskill goal state."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = [
    "init",
    "topic_search",
    "graph_build",
    "frontier_mapping",
    "literature_review",
    "ideation",
    "idea_gate",
    "experiment_plan",
    "code",
    "experiment",
    "analysis",
    "review_pressure",
    "writing",
    "submission_ready",
]

OWNERS = {
    "init": "WorkflowGuard",
    "topic_search": "Researcher",
    "graph_build": "Researcher",
    "frontier_mapping": "Researcher",
    "literature_review": "Researcher",
    "ideation": "Researcher",
    "idea_gate": "Reviewer",
    "experiment_plan": "Orchestrator",
    "code": "Coder",
    "experiment": "Coder",
    "analysis": "Analyzer",
    "review_pressure": "Reviewer",
    "writing": "Academic Writer",
    "submission_ready": "WorkflowGuard",
}

NEXT_ACTIONS = {
    "init": "resolve_corpus_and_project_memory",
    "topic_search": "run_literature_discovery",
    "graph_build": "write_graph_build_decision",
    "frontier_mapping": "map_frontier_and_transfer",
    "literature_review": "write_sota_matrix",
    "ideation": "run_papernexus_ideation",
    "idea_gate": "review_candidate_ideas",
    "experiment_plan": "materialize_innovation_packet",
    "code": "implement_experiment_bundle",
    "experiment": "launch_or_reconcile_experiment",
    "analysis": "build_claim_evidence_matrix",
    "review_pressure": "run_isolated_review",
    "writing": "write_evidence_bound_manuscript",
    "submission_ready": "package_for_submission",
}

DEFAULT_CORPUS = os.environ.get("AUTORESEARCH_DEFAULT_CORPUS", "default-papernexus-corpus")
DEFAULT_TARGET_VENUE = "unspecified_top_tier"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def root(project: str) -> Path:
    return Path(project).expanduser().resolve()


def ar(project: str) -> Path:
    return root(project) / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def default_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "autonomy_level": "full_auto_bounded",
        "allow_provider_evidence": True,
        "allow_live_discovery": True,
        "allow_literature_discovery": True,
        "allow_open_access_imports": True,
        "allow_remote_experiment_launch": True,
        "allow_claim_downgrade": True,
        "allow_negative_result_route": True,
        "max_literature_imports_per_round": 24,
        "max_provider_queries_per_round": 24,
        "max_live_discovery_questions": 6,
        "max_experiment_walltime_hours": 12,
        "max_experiment_gpu_hours": 24,
        "max_repair_attempts_per_blocker": 5,
        "max_stage_iterations": 16,
        "async_poll_interval_minutes": 5,
        "repair_retry_interval_minutes": 5,
        "experiment_launch_requires_baseline_protocol_lint": True,
        "experiment_requires_baseline_clone_patch": True,
        "allow_protocol_substitution": False,
        "max_off_protocol_probe_runs": 1,
        "off_protocol_probe_requires_user_approval": True,
        "fallback_when_resource_missing": "environment_smoke_only_then_plan_revision",
        "stop_only_on": [
            "paperNexus_unavailable_without_cached_evidence",
            "budget_exceeded",
            "data_license_blocked",
            "unsafe_or_irreproducible_experiment",
            "no_viable_claim_after_review",
        ],
    }


def default_capabilities() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "papernexus_remote_callable": None,
        "research_controller_available": None,
        "method_atlas_lookup_available": None,
        "can_spawn_subagents": None,
        "can_run_remote_experiments": None,
        "updated_at": now(),
        "notes": [],
    }


def initialize(args: argparse.Namespace) -> None:
    base = ar(args.project)
    for rel in [
        "handoffs",
        "job_packets",
        "graph",
        "papernexus/research_controller",
        "ideation/idea-catalyst",
        "literature",
        "orchestrator",
        "planner",
        "coder/experiments",
        "analyzer/figures",
        "analyzer/tables",
        "paper/story",
        "paper/sections",
        "paper/figures",
        "reviewer",
    ]:
        (base / rel).mkdir(parents=True, exist_ok=True)

    state = {
        "schema_version": 1,
        "project_root": str(root(args.project)),
        "goal": args.goal,
        "target_venue": args.venue,
        "paperNexus": {"mode": "remote_mcp", "corpus": args.corpus},
        "stage": "init",
        "owner": "WorkflowGuard",
        "next_action": NEXT_ACTIONS["init"],
        "blocking_reason": None,
        "autonomy_level": args.autonomy,
        "iteration": 0,
        "updated_at": now(),
    }
    write_json(base / "goal_state.json", state)
    write_json(base / "autopilot_policy.json", default_policy())
    write_json(base / "capabilities.json", default_capabilities())
    write_json(base / "retry_budget.json", {"schema_version": 1, "blockers": {}, "updated_at": now()})
    write_json(base / "artifacts_index.json", {"schema_version": 1, "artifacts": [], "updated_at": now()})
    for rel in [
        "decision_log.jsonl",
        "blocker_ledger.jsonl",
        "repair_queue.jsonl",
        "async_jobs.jsonl",
        "mailbox.jsonl",
        "evidence_cart.jsonl",
    ]:
        touch(base / rel)
    memory = base / "memory.md"
    if not memory.exists():
        memory.write_text(f"# AutoResearch Memory\n\nGoal: {args.goal}\n", encoding="utf-8")
    append_decision(base, "init", "initialized", {"goal": args.goal, "corpus": args.corpus})
    print(json.dumps(state, indent=2, ensure_ascii=False))


def append_decision(base: Path, stage: str, action: str, details: dict[str, Any]) -> None:
    append_jsonl(
        base / "decision_log.jsonl",
        {"ts": now(), "stage": stage, "action": action, "details": details},
    )


def load_state(project: str) -> dict[str, Any]:
    state_path = ar(project) / "goal_state.json"
    if not state_path.exists():
        raise SystemExit(f"missing {state_path}; run goal_state.py init first")
    return read_json(state_path, {})


def save_state(project: str, state: dict[str, Any], action: str, details: dict[str, Any]) -> None:
    state["updated_at"] = now()
    state["iteration"] = int(state.get("iteration", 0)) + 1
    write_json(ar(project) / "goal_state.json", state)
    append_decision(ar(project), str(state.get("stage", "unknown")), action, details)


def status(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    print(json.dumps(state, indent=2, ensure_ascii=False))


def advance(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    stage = args.stage or next_stage(str(state.get("stage", "init")))
    state.update(
        {
            "stage": stage,
            "owner": args.owner or OWNERS.get(stage, state.get("owner")),
            "next_action": args.next_action or NEXT_ACTIONS.get(stage),
            "blocking_reason": None,
        }
    )
    save_state(args.project, state, "advance", {"stage": stage})
    print(json.dumps(state, indent=2, ensure_ascii=False))


def block(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    if args.stage:
        state["stage"] = args.stage
    if args.owner:
        state["owner"] = args.owner
    if args.next_action:
        state["next_action"] = args.next_action
    state["blocking_reason"] = args.reason
    save_state(args.project, state, "block", {"reason": args.reason})
    print(json.dumps(state, indent=2, ensure_ascii=False))


def next_stage(stage: str) -> str:
    try:
        idx = STAGES.index(stage)
    except ValueError:
        return "init"
    return STAGES[min(idx + 1, len(STAGES) - 1)]


def append_decision_cmd(args: argparse.Namespace) -> None:
    base = ar(args.project)
    append_decision(base, args.stage, args.action, {"message": args.message})
    print(json.dumps({"ok": True, "decision_log": str(base / "decision_log.jsonl")}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--project", required=True)
    p.add_argument("--goal", required=True)
    p.add_argument("--corpus", default=DEFAULT_CORPUS)
    p.add_argument("--venue", default=DEFAULT_TARGET_VENUE)
    p.add_argument("--autonomy", default="full_auto_bounded")
    p.set_defaults(func=initialize)

    p = sub.add_parser("status")
    p.add_argument("--project", required=True)
    p.set_defaults(func=status)

    p = sub.add_parser("advance")
    p.add_argument("--project", required=True)
    p.add_argument("--stage")
    p.add_argument("--owner")
    p.add_argument("--next-action")
    p.set_defaults(func=advance)

    p = sub.add_parser("block")
    p.add_argument("--project", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--stage")
    p.add_argument("--owner")
    p.add_argument("--next-action")
    p.set_defaults(func=block)

    p = sub.add_parser("append-decision")
    p.add_argument("--project", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--message", default="")
    p.set_defaults(func=append_decision_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
