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


def manifest_track_id(path: Path, manifest: dict[str, Any]) -> str:
    if present(manifest.get("track_id")):
        return str(manifest.get("track_id"))
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "experiments" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json") or {}
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json") or {}
    active_plans = []
    for row in rows_from_payload(matrix):
        launch_status = str(row.get("launch_status") or "").lower()
        if launch_status == "ready" or row.get("selected_for_review") is True:
            active_plans.append(row)
    active_track_ids = {str(row.get("track_id") or "") for row in active_plans if present(row.get("track_id"))}
    active_plan_by_track = {str(row.get("track_id") or ""): row for row in active_plans if present(row.get("track_id"))}
    if not active_track_ids and present(review.get("track_id")):
        active_track_ids.add(str(review.get("track_id")))
    missing = []
    warnings = []
    manifest_paths = list(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json"))
    active_manifest_count = 0
    for manifest_path in manifest_paths:
        manifest = read_json(manifest_path) or {}
        track_id = manifest_track_id(manifest_path, manifest)
        if active_track_ids and track_id not in active_track_ids:
            warnings.append(f"{manifest_path}: skipped inactive track {track_id or '<unknown>'}")
            continue
        active_manifest_count += 1
        plan = active_plan_by_track.get(track_id, {})
        expected_metric = plan.get("primary_metric") or review.get("primary_metric")
        expected_dataset = plan.get("dataset") or review.get("dataset")
        if expected_metric and manifest.get("primary_metric") != expected_metric:
            missing.append(f"{manifest_path}: primary_metric drift")
        if expected_dataset and manifest.get("dataset") != expected_dataset:
            missing.append(f"{manifest_path}: dataset drift")
        if manifest.get("one_variable_change") is not True:
            missing.append(f"{manifest_path}: one_variable_change not true")
    if not manifest_paths:
        missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
    elif active_track_ids and active_manifest_count == 0:
        warnings.append("no active-track experiment manifest found; track_implementation_index owns implementation completeness")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "warnings": warnings}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
