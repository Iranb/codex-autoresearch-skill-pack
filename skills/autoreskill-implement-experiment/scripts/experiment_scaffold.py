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


def safe_component(value: str, label: str) -> str:
    component = value.strip()
    if not component or component in {".", ".."} or Path(component).name != component:
        raise SystemExit(f"{label} must be one safe path component")
    return component


def packet_paths(base: Path, requested_track_id: str | None) -> tuple[Path, Path]:
    if requested_track_id:
        requested_track_id = safe_component(requested_track_id, "--track-id")
        return (
            base / f"planner/tracks/{requested_track_id}/EXPERIMENT_REVIEW_PACKET.json",
            base / f"orchestrator/tracks/{requested_track_id}/INNOVATION_PACKET.json",
        )
    return (
        base / "planner/EXPERIMENT_REVIEW_PACKET.json",
        base / "orchestrator/INNOVATION_PACKET.json",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--track-id")
    parser.add_argument("--experiment-id", default="exp_001")
    args = parser.parse_args()
    base = ar(args.project)
    if args.track_id:
        args.track_id = safe_component(args.track_id, "--track-id")
    args.experiment_id = safe_component(args.experiment_id, "--experiment-id")
    review_path, innovation_path = packet_paths(base, args.track_id)
    review = read_json(review_path, {})
    innovation = read_json(innovation_path, {})
    if not review or not innovation:
        raise SystemExit(f"missing per-track planning packets: {review_path}, {innovation_path}")
    track_id = str(review.get("track_id") or innovation.get("track_id") or "").strip()
    if not track_id or (args.track_id and track_id != args.track_id):
        raise SystemExit(f"requested track {args.track_id!r} does not match packet track_id={track_id!r}")
    if str(innovation.get("track_id") or track_id).strip() != track_id:
        raise SystemExit("innovation/review packet track identity mismatch")
    selected_idea_id = str(review.get("selected_idea_id") or "").strip()
    if selected_idea_id != str(innovation.get("selected_idea_id") or "").strip():
        raise SystemExit("innovation/review packet selected_idea_id mismatch")
    track_role = str(review.get("track_role") or innovation.get("track_role") or "primary").strip().lower()
    ceiling = str(
        review.get("evidence_tier_ceiling")
        or innovation.get("evidence_tier_ceiling")
        or ("claim_eligible_after_gates" if track_role == "primary" else "pilot_only")
    ).strip()
    if track_role != "primary" and ceiling != "pilot_only":
        raise SystemExit("non-primary experiment scaffold requires evidence_tier_ceiling=pilot_only")
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {})
    matrix_rows = []
    if isinstance(matrix, dict):
        for key in ["tracks", "rows", "track_plans"]:
            if isinstance(matrix.get(key), list):
                matrix_rows = [row for row in matrix[key] if isinstance(row, dict)]
                break
    matching_plan_rows = [row for row in matrix_rows if str(row.get("track_id") or "").strip() == track_id]
    if len(matching_plan_rows) > 1:
        raise SystemExit(f"TRACK_PLAN_MATRIX contains duplicate track_id={track_id!r}")
    if args.track_id and not matching_plan_rows:
        raise SystemExit(f"TRACK_PLAN_MATRIX does not admit requested track_id={track_id!r}")
    plan_row = matching_plan_rows[0] if matching_plan_rows else {}
    for field, expected in [
        ("track_role", track_role),
        ("selection_fingerprint", review.get("selection_fingerprint")),
        ("evidence_tier_ceiling", ceiling),
    ]:
        if plan_row and plan_row.get(field) != expected:
            raise SystemExit(f"TRACK_PLAN_MATRIX {field} does not match the per-track packet")
    passport_ref = str(
        review.get("project_execution_passport_ref")
        or innovation.get("project_execution_passport_ref")
        or ""
    ).strip()
    passport = read_json(base / passport_ref, {}) if passport_ref else {}
    if passport_ref:
        if not passport:
            raise SystemExit(f"missing project execution passport: {passport_ref}")
        expected_index = str(review.get("project_execution_passport_index_sha256") or "")
        if expected_index != str(passport.get("index_semantic_sha256") or ""):
            raise SystemExit("project execution passport index does not match the review packet")
        profile_id = str(review.get("execution_profile_id") or "")
        profile = next(
            (
                item
                for item in passport.get("execution_profiles", [])
                if isinstance(item, dict) and str(item.get("profile_id") or "") == profile_id
            ),
            None,
        )
        if profile is None or str(profile.get("execution_profile_sha256") or "") != str(
            review.get("execution_profile_sha256") or ""
        ):
            raise SystemExit("review packet execution profile is absent or stale in the project passport")
    exp_dir = base / "coder/experiments" / track_id / args.experiment_id
    manifest = {
        "schema_version": 1,
        "created_at": now(),
        "status": "metadata_scaffold_only",
        "track_id": track_id,
        "track_role": track_role,
        "evidence_tier_ceiling": ceiling,
        "evidence_tier": "pilot_only" if ceiling == "pilot_only" else "claim_eligible",
        "selection_fingerprint": review.get("selection_fingerprint"),
        "selected_idea_id": selected_idea_id,
        "idea_lifecycle_status": review.get("idea_lifecycle_status"),
        "idea_decision_ref": review.get("idea_decision_ref"),
        "source_track_seed_ref": review.get("source_track_seed_ref"),
        "source_track_seed_sha256": review.get("source_track_seed_sha256"),
        "track_plan_ref": f"orchestrator/TRACK_PLAN_MATRIX.json:{track_id}" if plan_row else None,
        "track_plan_matrix_sha256": matrix.get("semantic_sha256") if isinstance(matrix, dict) else None,
        "innovation_packet_ref": str(innovation_path.relative_to(base)),
        "innovation_packet_sha256": innovation.get("semantic_sha256"),
        "review_packet_ref": str(review_path.relative_to(base)),
        "review_packet_sha256": review.get("semantic_sha256"),
        "project_execution_passport_ref": passport_ref or None,
        "project_execution_passport_index_sha256": review.get("project_execution_passport_index_sha256"),
        "execution_profile_id": review.get("execution_profile_id"),
        "execution_profile_sha256": review.get("execution_profile_sha256"),
        "innovation_delta_sha256": review.get("innovation_delta_sha256"),
        "resolved_execution_contract_projection_sha256": review.get(
            "resolved_execution_contract_projection_sha256"
        ),
        "experiment_id": args.experiment_id,
        "claim_ids": review.get("claim_ids", []),
        "baseline_config": None,
        "proposed_config": None,
        "primary_metric": review.get("primary_metric") or innovation.get("primary_metric"),
        "dataset": review.get("dataset"),
        "data_split": review.get("data_split"),
        "one_variable_change": review.get("one_variable_change"),
        "one_variable_change_description": review.get("one_variable_change_description"),
        "innovation_search_contract": review.get("innovation_search_contract"),
        "metric_policy": review.get("metric_policy"),
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
