#!/usr/bin/env python3
"""Create metadata for a real experiment bundle without placeholder train/eval code."""

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--track-id")
    parser.add_argument("--experiment-id", default="exp_001")
    args = parser.parse_args()
    base = ar(args.project)
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json", {})
    innovation = read_json(base / "orchestrator/INNOVATION_PACKET.json", {})
    track_id = args.track_id or review.get("track_id") or innovation.get("selected_idea_fragment_id") or "track_001"
    exp_dir = base / "coder/experiments" / track_id / args.experiment_id
    manifest = {
        "schema_version": 1,
        "created_at": now(),
        "status": "metadata_scaffold_only",
        "track_id": track_id,
        "experiment_id": args.experiment_id,
        "claim_ids": review.get("claim_ids", []),
        "baseline_config": None,
        "proposed_config": None,
        "primary_metric": review.get("primary_metric") or innovation.get("primary_metric"),
        "dataset": review.get("dataset"),
        "data_split": review.get("data_split"),
        "one_variable_change": review.get("one_variable_change"),
        "baseline_code": review.get("baseline_code"),
        "compute_backend": review.get("compute_backend"),
        "path_mapping": review.get("path_mapping"),
        "dry_run_kind": None,
        "fixture": False,
        "launch_ready": False,
        "blocking_reason": (
            "experiment_scaffold.py no longer creates generated placeholder train/eval code; "
            "audit the locked baseline/data and implement thin adapters around the real baseline entrypoints."
        ),
        "required_next_artifacts": [
            "BASELINE_DATA_AUDIT.json",
            "REMOTE_UPLOAD.json when backend is remote",
            "REMOTE_RUN.json with real-data or real-feature smoke proof",
            "baseline_patch_proof",
        ],
    }
    write_json(exp_dir / "EXPERIMENT_MANIFEST.json", manifest)
    write_text(
        exp_dir / "README.md",
        "# Experiment Bundle Scaffold\n\n"
        "This is a metadata scaffold only. It intentionally contains no generated placeholder train/eval code.\n"
        "Before launch, audit the locked baseline and dataset, then add thin adapters or patches against the real baseline clone.\n",
    )
    write_text(base / "coder/EXPERIMENT_INDEX.md", f"# Experiment Index\n\n- `{track_id}/{args.experiment_id}`: {exp_dir}\n")
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": "code",
            "action": "experiment_metadata_scaffold",
            "details": {"track_id": track_id, "experiment_id": args.experiment_id, "launch_ready": False},
        },
    )
    print(json.dumps({"ok": True, "experiment_dir": str(exp_dir)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
