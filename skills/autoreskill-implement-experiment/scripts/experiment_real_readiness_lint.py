#!/usr/bin/env python3
"""Block fixture-only implementation proofs from satisfying code readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SUCCESS_STATUSES = {"complete", "completed", "success", "succeeded", "passed", "ready"}
REAL_PROOF_KINDS = {"real_data_smoke", "real_feature_smoke", "pilot", "remote_pilot", "baseline_aligned_smoke"}
FIXTURE_MARKERS = {"fixture", "synthetic", "synthetic_fixture", "toy", "mock", "ok_only"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["tracks", "rows", "track_plans"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def active_track_ids(base: Path) -> set[str]:
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
    active: set[str] = set()
    for row in rows_from_payload(matrix):
        track_id = str(row.get("track_id") or "").strip()
        launch_status = normalized(row.get("launch_status"))
        selected = row.get("selected_for_review") is True
        if track_id and (launch_status == "ready" or selected):
            active.add(track_id)
    return active


def proof_status(remote: dict[str, Any]) -> str:
    for key in ["status", "smoke_status", "result_status", "run_status"]:
        status = normalized(remote.get(key))
        if status:
            return status
    return ""


def proof_kind(manifest: dict[str, Any], remote: dict[str, Any]) -> str:
    for source in [remote, manifest]:
        for key in ["proof_kind", "dry_run_kind", "run_kind", "data_proof_kind"]:
            value = normalized(source.get(key))
            if value:
                return value
    return ""


def lint(project: str) -> dict[str, Any]:
    base = ar(project)
    missing: list[str] = []
    warnings: list[str] = []
    active_tracks = active_track_ids(base)
    manifests = sorted(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json"))
    if not manifests:
        missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
    for manifest_path in manifests:
        manifest = read_json(manifest_path, {}) or {}
        label = rel(base, manifest_path)
        track_id = str(manifest.get("track_id") or manifest_path.parent.parent.name or "").strip()
        if active_tracks and track_id and track_id not in active_tracks:
            warnings.append(f"{label}: skipped inactive track {track_id}")
            continue
        if manifest.get("fixture") is True:
            missing.append(f"{label} fixture must be false for code readiness")
        kind = proof_kind(manifest, {})
        if kind in FIXTURE_MARKERS:
            missing.append(f"{label} dry_run_kind/proof_kind cannot be fixture-only")
        audit_rel = str(manifest.get("baseline_data_audit") or "BASELINE_DATA_AUDIT.json")
        audit_path = manifest_path.parent / audit_rel
        audit = read_json(audit_path, {}) or {}
        if not audit:
            missing.append(f"{label} BASELINE_DATA_AUDIT.json")
        else:
            if audit.get("fixture") is True or normalized(audit.get("data_kind")) in FIXTURE_MARKERS:
                missing.append(f"{rel(base, audit_path)} must not be fixture-only")
            if not (
                present(audit.get("dataset_root"))
                or present(audit.get("feature_manifest"))
                or present(audit.get("remote_dataset_root"))
                or present(audit.get("data_root"))
            ):
                missing.append(f"{rel(base, audit_path)} dataset_root/feature_manifest/remote_dataset_root")
        remote_rel = str(manifest.get("remote_run") or "REMOTE_RUN.json")
        remote_path = manifest_path.parent / remote_rel
        remote = read_json(remote_path, {}) or {}
        if not remote:
            missing.append(f"{label} REMOTE_RUN.json")
            continue
        status = proof_status(remote)
        if status not in SUCCESS_STATUSES:
            missing.append(f"{rel(base, remote_path)} status must be success/complete/passed")
        kind = proof_kind(manifest, remote)
        if kind in FIXTURE_MARKERS:
            missing.append(f"{rel(base, remote_path)} proof_kind must not be fixture/synthetic")
        elif kind and kind not in REAL_PROOF_KINDS:
            warnings.append(f"{rel(base, remote_path)} proof_kind `{kind}` is not a standard real-proof kind")
        if not (
            present(remote.get("command"))
            or present(remote.get("train_command"))
            or present(remote.get("evaluation_command"))
        ):
            missing.append(f"{rel(base, remote_path)} command/train_command/evaluation_command")
        if not (
            present(remote.get("host"))
            or present(remote.get("backend"))
            or present(remote.get("instance_id"))
        ):
            missing.append(f"{rel(base, remote_path)} host/backend/instance_id")
        if not (
            present(remote.get("dataset"))
            or present(remote.get("data_root"))
            or present(remote.get("feature_manifest"))
        ):
            missing.append(f"{rel(base, remote_path)} dataset/data_root/feature_manifest")
        if not (
            present(remote.get("artifact_paths"))
            or present(remote.get("result_paths"))
            or present(remote.get("metrics_path"))
        ):
            missing.append(f"{rel(base, remote_path)} artifact_paths/result_paths/metrics_path")
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    out = lint(args.project)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
