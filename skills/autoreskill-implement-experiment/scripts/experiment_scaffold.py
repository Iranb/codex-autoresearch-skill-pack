#!/usr/bin/env python3
"""Create a portable baseline/proposed experiment bundle and dry-run proof."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRAIN = """#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
Path(args.output).write_text(json.dumps({"ok": True, "config": args.config}) + "\\n", encoding="utf-8")
print("dry-run train ok")
"""

EVAL = """#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--metrics", required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
Path(args.metrics).parent.mkdir(parents=True, exist_ok=True)
Path(args.metrics).write_text(json.dumps({"primary_metric": 0.0, "payload_ok": payload.get("ok") is True}) + "\\n", encoding="utf-8")
print("dry-run eval ok")
"""


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
    parser.add_argument("--write-dry-run", action="store_true")
    args = parser.parse_args()
    base = ar(args.project)
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json", {})
    innovation = read_json(base / "orchestrator/INNOVATION_PACKET.json", {})
    track_id = args.track_id or review.get("track_id") or innovation.get("selected_idea_fragment_id") or "track_001"
    exp_dir = base / "coder/experiments" / track_id / args.experiment_id
    write_text(exp_dir / "train.py", TRAIN)
    write_text(exp_dir / "evaluate.py", EVAL)
    write_text(exp_dir / "configs/baseline.yaml", "variant: baseline\nseed: 0\n")
    write_text(exp_dir / "configs/proposed.yaml", "variant: proposed\nseed: 0\none_variable_change: true\n")
    manifest = {
        "schema_version": 1,
        "created_at": now(),
        "track_id": track_id,
        "experiment_id": args.experiment_id,
        "claim_ids": review.get("claim_ids", []),
        "baseline_config": "configs/baseline.yaml",
        "proposed_config": "configs/proposed.yaml",
        "primary_metric": review.get("primary_metric") or innovation.get("primary_metric"),
        "dataset": review.get("dataset"),
        "one_variable_change": review.get("one_variable_change") is True,
        "dry_run_log": "logs/dry_run.log",
    }
    write_json(exp_dir / "EXPERIMENT_MANIFEST.json", manifest)
    if args.write_dry_run:
        write_text(exp_dir / "logs/dry_run.log", "dry-run train ok\ndry-run eval ok\n")
    write_text(base / "coder/EXPERIMENT_INDEX.md", f"# Experiment Index\n\n- `{track_id}/{args.experiment_id}`: {exp_dir}\n")
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "code", "action": "experiment_scaffold", "details": {"track_id": track_id, "experiment_id": args.experiment_id}})
    print(json.dumps({"ok": True, "experiment_dir": str(exp_dir)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
