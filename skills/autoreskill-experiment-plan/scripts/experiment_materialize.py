#!/usr/bin/env python3
"""Materialize INNOVATION_PACKET and EXPERIMENT_REVIEW_PACKET from an advanced candidate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    candidate = first_candidate(pool)
    evidence_ids = candidate.get("evidence_ids") or []
    if not evidence_ids and not args.allow_fixture:
        raise SystemExit("cannot materialize experiment plan without candidate evidence_ids")
    track_id = args.track_id or candidate.get("track_id") or "track_001"
    evidence_paths = [".autoreskill/evidence_cart.jsonl"]
    design_path = ".autoreskill/papernexus/research_controller/design-review.json"
    innovation = {
        "schema_version": 1,
        "created_at": now(),
        "selected_idea_fragment_id": track_id,
        "supporting_idea_fragment_ids": [track_id],
        "baseline": args.baseline,
        "primary_metric": args.metric,
        "fixed_budget": {"gpu_hours": args.gpu_hours, "walltime_hours": args.walltime_hours},
        "evidence_paths": evidence_paths,
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
        "one_variable_change": True,
        "baseline_reference": args.baseline,
        "baseline_training_protocol": "same data, same budget, same evaluation pipeline",
        "baseline_eval_protocol": "same dataset split and primary metric",
        "dataset": args.dataset,
        "primary_metric": args.metric,
        "secondary_metrics": ["runtime", "stability"],
        "ablation_plan": ["remove the proposed one-variable change"],
        "falsifiers": [candidate.get("falsifier") or "no improvement over the matched baseline"],
        "stop_rules": ["stop if dry-run fails after bounded repair", "stop if metric/dataset drift is detected"],
        "compute_budget": {"gpu_hours": args.gpu_hours, "walltime_hours": args.walltime_hours},
        "expected_artifacts": ["EXPERIMENT_MANIFEST.json", "dry_run.log", "REMOTE_RUN.json", "EXPERIMENT_LEDGER.json"],
        "paperNexus_norms": ["See evidence_cart and PaperNexus artifacts."],
        "experiment_cost_norms": {"gpu_hours": args.gpu_hours, "walltime_hours": args.walltime_hours},
        "non_promotion_signals": ["single seed only", "fixture mode", "missing graph-grounded novelty evidence"],
    }
    write_json(base / "orchestrator/INNOVATION_PACKET.json", innovation)
    write_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json", review)
    write_text(base / "planner/EXPERIMENT_PLAN.md", "# Experiment Plan\n\nBaseline-first, one-variable, dry-run-gated plan.\n")
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "experiment_plan", "action": "materialize_experiment_plan", "details": {"track_id": track_id, "fixture": innovation["fixture"]}})
    print(json.dumps({"ok": True, "innovation_packet": "orchestrator/INNOVATION_PACKET.json", "experiment_review_packet": "planner/EXPERIMENT_REVIEW_PACKET.json"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
