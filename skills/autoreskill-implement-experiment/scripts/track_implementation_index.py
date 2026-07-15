#!/usr/bin/env python3
"""Build and check per-track implementation proof index."""

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


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def exp_manifest_rows(base: Path) -> list[tuple[Path, dict[str, Any]]]:
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json")):
        payload = read_json(path, {}) or {}
        if isinstance(payload, dict):
            rows.append((path, payload))
    return rows


def patch_status(manifest: dict[str, Any], audit: dict[str, Any]) -> str:
    patch = {}
    for source in [manifest, audit]:
        for key in ["baseline_patch_proof", "baseline_patch", "proposed_patch_proof"]:
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, dict) and value:
                patch = value
                break
        if patch:
            break
    if not patch:
        return "missing"
    if patch.get("patch_applies_to_baseline") is True and present(patch.get("patch_path")) and present(patch.get("changed_paths")):
        return "complete"
    return "incomplete"


def implementation_row(base: Path, manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    exp_dir = manifest_path.parent
    audit_rel = str(manifest.get("baseline_data_audit") or "BASELINE_DATA_AUDIT.json")
    audit_path = exp_dir / audit_rel
    audit = read_json(audit_path, {}) or {}
    remote_path = exp_dir / str(manifest.get("remote_run") or "REMOTE_RUN.json")
    dry_run = manifest.get("dry_run_log")
    return {
        "experiment_manifest_path": rel(base, manifest_path),
        "experiment_id": manifest.get("experiment_id") or exp_dir.name,
        "track_id": manifest.get("track_id") or exp_dir.parent.name,
        "claim_ids": manifest.get("claim_ids") or [],
        "promotion_stage": manifest.get("promotion_stage") or (manifest.get("innovation_search_contract") or {}).get("promotion_stage"),
        "project_execution_passport_ref": manifest.get("project_execution_passport_ref"),
        "project_execution_passport_index_sha256": manifest.get("project_execution_passport_index_sha256"),
        "execution_profile_id": manifest.get("execution_profile_id"),
        "execution_profile_sha256": manifest.get("execution_profile_sha256"),
        "innovation_delta_sha256": manifest.get("innovation_delta_sha256"),
        "resolved_execution_contract_projection_sha256": manifest.get(
            "resolved_execution_contract_projection_sha256"
        ),
        "baseline_code": manifest.get("baseline_code") if isinstance(manifest.get("baseline_code"), dict) else {},
        "baseline_data_audit_path": rel(base, audit_path) if audit_path.exists() else "",
        "baseline_patch_proof_status": patch_status(manifest, audit),
        "remote_run_path": rel(base, remote_path) if remote_path.exists() else "",
        "dry_run_log": dry_run,
        "one_variable_change": manifest.get("one_variable_change") is True,
        "dataset": manifest.get("dataset"),
        "primary_metric": manifest.get("primary_metric"),
        "fixture": manifest.get("fixture") is True or str(manifest.get("dry_run_kind") or "").lower() in {"fixture", "synthetic", "synthetic_fixture"},
    }


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
    plan_rows = rows_from_payload(matrix)
    manifests = exp_manifest_rows(base)
    impl_rows = [implementation_row(base, path, manifest) for path, manifest in manifests]
    by_track: dict[str, list[dict[str, Any]]] = {}
    for row in impl_rows:
        by_track.setdefault(str(row.get("track_id") or ""), []).append(row)
    tracks = []
    for plan in plan_rows:
        track_id = str(plan.get("track_id") or "")
        experiments = by_track.get(track_id, [])
        tracks.append(
            {
                "track_id": track_id,
                "idea_id": plan.get("idea_id"),
                "launch_status": plan.get("launch_status"),
                "selected_for_review": plan.get("selected_for_review") is True,
                "project_execution_passport_ref": plan.get("project_execution_passport_ref"),
                "project_execution_passport_index_sha256": plan.get("project_execution_passport_index_sha256"),
                "execution_profile_id": plan.get("execution_profile_id"),
                "execution_profile_sha256": plan.get("execution_profile_sha256"),
                "innovation_delta_sha256": plan.get("innovation_delta_sha256"),
                "implementation_status": "implemented" if experiments else "planned_only",
                "experiments": experiments,
                "patch_proof_status": "complete" if experiments and all(exp.get("baseline_patch_proof_status") == "complete" for exp in experiments) else "missing" if not experiments else "incomplete",
            }
        )
    for track_id, experiments in sorted(by_track.items()):
        if track_id and not any(str(plan.get("track_id") or "") == track_id for plan in plan_rows):
            tracks.append(
                {
                    "track_id": track_id,
                    "idea_id": None,
                    "launch_status": "unplanned",
                    "selected_for_review": False,
                    "implementation_status": "unplanned_implementation",
                    "experiments": experiments,
                    "patch_proof_status": "complete" if all(exp.get("baseline_patch_proof_status") == "complete" for exp in experiments) else "incomplete",
                }
            )
    return {
        "schema_version": 1,
        "generated_at": now(),
        "artifact": "TRACK_IMPLEMENTATION_INDEX",
        "source_track_plan_matrix_path": "orchestrator/TRACK_PLAN_MATRIX.json",
        "tracks": tracks,
    }


def lint(project: str) -> dict[str, Any]:
    base = ar(project)
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
    index = read_json(base / "coder/TRACK_IMPLEMENTATION_INDEX.json", {}) or {}
    missing: list[str] = []
    warnings: list[str] = []
    plan_rows = rows_from_payload(matrix)
    index_rows = rows_from_payload(index)
    if not isinstance(index, dict) or not index_rows:
        missing.append("coder/TRACK_IMPLEMENTATION_INDEX.json tracks")
        index_rows = []
    index_by_track = {str(row.get("track_id") or ""): row for row in index_rows if present(row.get("track_id"))}
    for plan in plan_rows:
        track_id = str(plan.get("track_id") or "")
        if not track_id:
            continue
        row = index_by_track.get(track_id)
        if row is None:
            missing.append(f"TRACK_IMPLEMENTATION_INDEX missing planned track {track_id}")
            continue
        launch_status = str(plan.get("launch_status") or "").lower()
        selected = plan.get("selected_for_review") is True
        if launch_status == "ready" or selected:
            if row.get("implementation_status") != "implemented":
                missing.append(f"{track_id} implementation_status=implemented")
            if row.get("patch_proof_status") != "complete":
                missing.append(f"{track_id} patch_proof_status=complete")
            experiments = row.get("experiments")
            if not isinstance(experiments, list) or not experiments:
                missing.append(f"{track_id} experiments")
            else:
                for exp_index, exp in enumerate(exp for exp in experiments if isinstance(exp, dict)):
                    prefix = f"{track_id}.experiments[{exp_index}]"
                    if exp.get("fixture") is True:
                        missing.append(f"{prefix}.fixture must be false for launchable code")
                    if exp.get("one_variable_change") is not True:
                        missing.append(f"{prefix}.one_variable_change=true")
                    if not present(exp.get("baseline_data_audit_path")):
                        missing.append(f"{prefix}.baseline_data_audit_path")
                    if not present(exp.get("experiment_manifest_path")):
                        missing.append(f"{prefix}.experiment_manifest_path")
        elif row.get("implementation_status") == "planned_only":
            warnings.append(f"{track_id} has no implementation yet")
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "track_count": len(index_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        out = lint(args.project)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        raise SystemExit(0 if out["complete"] else 1)
    payload = build(args.project)
    write_json(ar(args.project) / "coder/TRACK_IMPLEMENTATION_INDEX.json", payload)
    append_jsonl(
        ar(args.project) / "decision_log.jsonl",
        {"ts": now(), "stage": "code", "action": "track_implementation_index", "details": {"track_count": len(payload["tracks"])}},
    )
    print(json.dumps({"ok": True, "path": "coder/TRACK_IMPLEMENTATION_INDEX.json", "track_count": len(payload["tracks"])}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
