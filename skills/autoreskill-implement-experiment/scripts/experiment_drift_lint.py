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


def review_for_plan(base: Path, plan: dict[str, Any], primary_review: dict[str, Any]) -> tuple[dict[str, Any], str]:
    ref = str(plan.get("review_packet_ref") or "").strip()
    if ref:
        packet = read_json(base / ref)
        return (packet if isinstance(packet, dict) else {}), ref
    return primary_review, "planner/EXPERIMENT_REVIEW_PACKET.json"


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
        track_review, review_ref = review_for_plan(base, plan, review)
        if not track_review:
            missing.append(f"{manifest_path}: missing current review packet {review_ref}")
            continue
        expected_metric = plan.get("primary_metric") or track_review.get("primary_metric")
        expected_dataset = plan.get("dataset") or track_review.get("dataset")
        if expected_metric and manifest.get("primary_metric") != expected_metric:
            missing.append(f"{manifest_path}: primary_metric drift")
        if expected_dataset and manifest.get("dataset") != expected_dataset:
            missing.append(f"{manifest_path}: dataset drift")
        if manifest.get("one_variable_change") is not True:
            missing.append(f"{manifest_path}: one_variable_change not true")
        for field in [
            "track_role",
            "evidence_tier_ceiling",
            "selection_fingerprint",
            "project_execution_passport_ref",
            "project_execution_passport_index_sha256",
            "execution_profile_id",
            "execution_profile_sha256",
            "innovation_delta_sha256",
            "resolved_execution_contract_projection_sha256",
        ]:
            expected = plan.get(field) or track_review.get(field)
            if present(expected) and manifest.get(field) != expected:
                missing.append(f"{manifest_path}: {field} drift")
        passport_ref = str(track_review.get("project_execution_passport_ref") or "").strip()
        if passport_ref:
            passport = read_json(base / passport_ref) or {}
            if not passport:
                missing.append(f"{manifest_path}: project execution passport missing")
            elif str(passport.get("index_semantic_sha256") or "") != str(
                track_review.get("project_execution_passport_index_sha256") or ""
            ):
                missing.append(f"{manifest_path}: project execution passport index drift")
            else:
                profile = next(
                    (
                        item
                        for item in passport.get("execution_profiles", [])
                        if isinstance(item, dict)
                        and str(item.get("profile_id") or "") == str(track_review.get("execution_profile_id") or "")
                    ),
                    None,
                )
                if profile is None or str(profile.get("execution_profile_sha256") or "") != str(
                    track_review.get("execution_profile_sha256") or ""
                ):
                    missing.append(f"{manifest_path}: execution profile drift")
        expected_matrix_sha = matrix.get("semantic_sha256") if isinstance(matrix, dict) else None
        if present(expected_matrix_sha) and manifest.get("track_plan_matrix_sha256") != expected_matrix_sha:
            missing.append(f"{manifest_path}: track_plan_matrix_sha256 drift")
        expected_seed_sha = plan.get("source_track_seed_sha256") or track_review.get("source_track_seed_sha256")
        if present(expected_seed_sha) and manifest.get("source_track_seed_sha256") != expected_seed_sha:
            missing.append(f"{manifest_path}: source_track_seed_sha256 drift")
        expected_packet_sha = plan.get("review_packet_sha256") or track_review.get("semantic_sha256")
        if present(expected_packet_sha) and manifest.get("review_packet_sha256") != expected_packet_sha:
            missing.append(f"{manifest_path}: review_packet_sha256 drift")
        if str(plan.get("track_role") or track_review.get("track_role") or "").lower() in {"alternate", "risk_repair"}:
            if manifest.get("evidence_tier") != "pilot_only" or manifest.get("evidence_tier_ceiling") != "pilot_only":
                missing.append(f"{manifest_path}: non-primary manifest must remain pilot_only")
    if not manifest_paths:
        missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
    elif active_track_ids and active_manifest_count == 0:
        warnings.append("no active-track experiment manifest found; track_implementation_index owns implementation completeness")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "warnings": warnings}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
