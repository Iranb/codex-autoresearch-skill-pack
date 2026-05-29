#!/usr/bin/env python3
"""Materialize explicit non-live fixture artifacts for end-to-end contract testing."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from goal_state import ar


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def fixture_ideas() -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    for index in range(12):
        idea_type = "ALGO" if index < 6 else "CODE"
        source_backed = index < 3
        ideas.append(
            {
                "id": f"IDEA-{index + 1:03d}",
                "type": idea_type,
                "priority": "HIGH" if index == 0 else "MEDIUM",
                "risk": "LOW",
                "source": "papernexus" if source_backed else "code_analysis",
                "source_paper_or_technique": f"fixture technique {index + 1}" if source_backed else "",
                "paperNexus_evidence_ids": [f"fixture_ev_{index + 1}"] if source_backed else [],
                "derived_from_idea_fragment_ids": ["fixture_idea"] if source_backed else [],
                "description": f"Fixture {idea_type} optimization idea {index + 1}.",
                "hypothesis": "Fixture idea may improve fixture_metric under the locked protocol.",
                "one_variable_change": f"fixture one-variable change {index + 1}",
                "expected_metric_impact": "improve fixture_metric without changing evaluation",
                "implementation_scope": "fixture implementation scope",
                "red_line_audit": {
                    "metric_drift": False,
                    "eval_drift": False,
                    "dataset_drift": False,
                    "data_leakage": False,
                    "prediction_cheating": False,
                    "training_budget_drift": False,
                },
                "status": "SELECTED" if index == 0 else "PENDING",
            }
        )
    return ideas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--track-id", default="fixture_track")
    parser.add_argument("--force-ready", action="store_true", help="write schema-complete fixture contracts for linter testing only")
    args = parser.parse_args()

    base = ar(args.project)
    marker = {
        "schema_version": 1,
        "created_at": now(),
        "fixture": True,
        "fixture_warning": "Non-live contract fixture for validation only. Do not cite as PaperNexus graph-grounded evidence.",
    }
    write_json(base / "literature/LITERATURE_DISCOVERY_PACKET.json", {**marker, "queries": ["fixture query"], "papers": []})
    write_json(base / "papernexus/research_material_pack.json", {**marker, "frontier_gaps": ["fixture gap"], "transfer_methods": []})
    write_text(base / "literature/SOTA_MATRIX.md", "# SOTA Matrix\n\nFixture only; replace with PaperNexus/literature evidence.\n")
    write_text(base / "literature/GAP_SYNTHESIS.md", "# Gap Synthesis\n\nFixture only; replace with PaperNexus/literature evidence.\n")
    write_json(
        base / "ideation/CANDIDATE_POOL.json",
        {
            **marker,
            "candidates": [
                {
                    "track_id": args.track_id,
                    "status": "advance_with_constraints",
                    "evidence_ids": ["fixture_ev"],
                    "weakest_assumption": "fixture candidate is not live PaperNexus evidence",
                    "falsifier": "no improvement on fixture metric",
                }
            ],
        },
    )
    write_json(base / "ideation/TOURNAMENT_SCOREBOARD.json", {**marker, "tracks": [{"track_id": args.track_id, "verdict": "advance_with_constraints"}]})
    write_text(base / "ideation/TOP3_DIRECTION_SUMMARY.md", "# Top Directions\n\nFixture track for contract testing.\n")
    write_json(
        base / "papernexus/research_controller/design-review.json",
        {**marker, "status": "ready", "verdict": "pass", "blocking_issues": []},
    )

    if args.force_ready:
        write_json(base / "graph/GRAPH_BUILD_DECISION.json", {**marker, "decision": "complete", "source_backed_graph_claim": True})
        write_json(
            base / "ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json",
            {**marker, "status": "ready", "selected_idea_fragment_id": "fixture_idea", "evidence_ids": ["fixture_ev"]},
        )
        write_json(
            base / "papernexus/idea_catalyst_evidence_export.json",
            {
                **marker,
                "source": "papernexus-remote",
                "fragments": [
                    {
                        "fragment_id": "fixture_idea",
                        "evidence_status": "source_backed",
                        "paper_id": "fixture_paper",
                        "title": "Fixture PaperNexus source",
                        "span": "Fixture source span for selected idea.",
                    }
                ],
            },
        )
        write_json(
            base / "ideation/EXPERIMENT_IDEA_POOL.json",
            {
                **marker,
                "idea_generation_scope": "ideation-stage experiment idea pool; no experiment-plan generation",
                "locked_protocol": {
                    "dataset": "fixture_dataset",
                    "data_split": "fixture_split",
                    "primary_metric": "fixture_metric",
                    "metric_direction": "higher",
                    "baseline_reference": "fixture_baseline",
                    "baseline_training_protocol": "same fixture training protocol",
                    "baseline_eval_protocol": "same fixture evaluation protocol",
                    "evaluation_command": "python evaluate.py --config fixture_eval.yaml --metrics results/metrics.json",
                    "protected_paths": [],
                },
                "selected_idea_id": "IDEA-001",
                "ideas": fixture_ideas(),
            },
        )
        write_json(
            base / "orchestrator/INNOVATION_PACKET.json",
            {
                **marker,
                "selected_idea_fragment_id": "fixture_idea",
                "supporting_idea_fragment_ids": ["fixture_idea"],
                "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
                "selected_idea_id": "IDEA-001",
                "baseline": "fixture_baseline",
                "primary_metric": "fixture_metric",
                "dataset_or_benchmark": "fixture_dataset",
                "dataset": "fixture_dataset",
                "one_variable_change": "fixture one-variable change",
                "falsifier": "no improvement on fixture metric",
                "falsifiers": ["no improvement on fixture metric"],
                "fixed_budget": {"gpu_hours": 0, "walltime_hours": 0},
                "evidence_paths": [".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json"],
                "idea_evidence_export_path": ".autoreskill/papernexus/idea_catalyst_evidence_export.json",
                "evidence_boundaries": {
                    "source_backed": ["fixture_ev"],
                    "agent_inferred": ["fixture one-variable change"],
                    "speculative": ["fixture metric impact"],
                    "unsupported": ["fixture-only manuscript claim"],
                },
                "paperNexus_corpus": "fixture",
                "controller_design_review_path": ".autoreskill/papernexus/research_controller/design-review.json",
            },
        )
        write_json(
            base / "planner/EXPERIMENT_REVIEW_PACKET.json",
            {
                **marker,
                "status": "reviewed",
                "track_id": args.track_id,
                "claim_ids": ["fixture_claim"],
                "hypothesis": "Fixture hypothesis.",
                "novelty_basis": "Fixture novelty basis; not for manuscript claims.",
                "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
                "selected_idea_id": "IDEA-001",
                "idea_generation_scope": "ideation-stage experiment idea pool; no experiment-plan generation",
                "one_variable_change": True,
                "baseline_reference": "fixture_baseline",
                "baseline_training_protocol": "same fixture training protocol",
                "baseline_eval_protocol": "same fixture evaluation protocol",
                "evaluation_command": "python evaluate.py --config fixture_eval.yaml --metrics results/metrics.json",
                "dataset": "fixture_dataset",
                "data_split": "fixture_split",
                "primary_metric": "fixture_metric",
                "metric_direction": "higher",
                "secondary_metrics": ["fixture_secondary_metric"],
                "ablation_plan": ["remove fixture change"],
                "falsifiers": ["no improvement on fixture metric"],
                "stop_rules": ["stop after dry-run"],
                "compute_budget": {"gpu_hours": 0, "walltime_hours": 0},
                "protected_paths": [],
                "expected_artifacts": ["EXPERIMENT_MANIFEST.json"],
                "paperNexus_norms": ["fixture_norm"],
                "experiment_cost_norms": {"source": "fixture"},
                "non_promotion_signals": ["fixture only"],
            },
        )

    append_jsonl(
        base / "decision_log.jsonl",
        {"ts": now(), "stage": "fixture", "action": "materialize_contract_fixture", "details": {"force_ready": args.force_ready}},
    )
    print(json.dumps({"ok": True, "fixture": True, "force_ready": args.force_ready}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
