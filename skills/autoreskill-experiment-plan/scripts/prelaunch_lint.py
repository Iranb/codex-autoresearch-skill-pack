#!/usr/bin/env python3
"""Lint EXPERIMENT_REVIEW_PACKET before experiment launch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED = [
    "track_id",
    "claim_ids",
    "hypothesis",
    "novelty_basis",
    "one_variable_change",
    "baseline_reference",
    "baseline_training_protocol",
    "baseline_eval_protocol",
    "dataset",
    "primary_metric",
    "secondary_metrics",
    "ablation_plan",
    "falsifiers",
    "stop_rules",
    "compute_budget",
    "expected_artifacts",
    "paperNexus_norms",
    "non_promotion_signals",
]


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def lint(packet: dict[str, Any] | None) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    if not packet:
        return {"complete": False, "status": "incomplete", "missing": ["planner/EXPERIMENT_REVIEW_PACKET.json"], "warnings": []}

    for key in REQUIRED:
        if not present(packet.get(key)):
            missing.append(f"EXPERIMENT_REVIEW_PACKET.{key}")

    if packet.get("one_variable_change") is not True:
        missing.append("EXPERIMENT_REVIEW_PACKET.one_variable_change must be true")

    cost_norms = packet.get("experiment_cost_norms") or packet.get("cost_evidence_gap")
    if not present(cost_norms):
        warnings.append("missing experiment_cost_norms or explicit cost_evidence_gap")

    launch = str(packet.get("launch_status") or packet.get("status") or "").lower()
    if launch and launch not in {"reviewed", "ready", "approved", "pass", "passed"}:
        missing.append("EXPERIMENT_REVIEW_PACKET.status must be reviewed/ready/approved before launch")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--packet")
    args = parser.parse_args()
    path = Path(args.packet).expanduser() if args.packet else ar(args.project) / "planner/EXPERIMENT_REVIEW_PACKET.json"
    out = lint(read_json(path))
    out["path"] = str(path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
