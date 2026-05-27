#!/usr/bin/env python3
"""Detect metric/dataset/baseline drift between plan and experiment manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json") or {}
    missing = []
    for manifest_path in base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json"):
        manifest = read_json(manifest_path) or {}
        if review.get("primary_metric") and manifest.get("primary_metric") != review.get("primary_metric"):
            missing.append(f"{manifest_path}: primary_metric drift")
        if review.get("dataset") and manifest.get("dataset") != review.get("dataset"):
            missing.append(f"{manifest_path}: dataset drift")
        if manifest.get("one_variable_change") is not True:
            missing.append(f"{manifest_path}: one_variable_change not true")
    if not list(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json")):
        missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
