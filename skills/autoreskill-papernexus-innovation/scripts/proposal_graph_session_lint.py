#!/usr/bin/env python3
"""Lint PaperNexus proposal graph session artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


READY = {"committed", "ready", "passed", "complete", "completed"}


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


def resolve_path(base: Path, raw: Any) -> Path | None:
    if not present(raw):
        return None
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == ".autoreskill":
        return base.parent / path
    return base / path


def relpath(base: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def path_exists(base: Path, raw: Any) -> bool:
    path = resolve_path(base, raw)
    return bool(path and path.exists() and (path.is_file() or path.is_dir()))


def validate_manifest(base: Path, manifest: dict[str, Any], source: str) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    status = str(manifest.get("final_status") or manifest.get("status") or "").strip().lower()
    if status != "committed":
        missing.append(f"{source}.final_status=committed")
    if not present(manifest.get("committed_subgraph_id")):
        missing.append(f"{source}.committed_subgraph_id")

    proposal_paths = manifest.get("proposal_artifact_paths") if isinstance(manifest.get("proposal_artifact_paths"), dict) else {}
    for key in ["proposal_md", "proposal_json", "proposal_graph_json"]:
        if not present(proposal_paths.get(key)):
            missing.append(f"{source}.proposal_artifact_paths.{key}")
        elif not path_exists(base, proposal_paths.get(key)):
            warnings.append(f"{source}.proposal_artifact_paths.{key} target not found locally: {proposal_paths.get(key)}")

    for key in ["evidence_export_paths", "controller_trace_paths", "validation_report_paths"]:
        value = manifest.get(key)
        if not present(value):
            missing.append(f"{source}.{key}")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "source": source,
        "final_status": status,
        "committed_subgraph_id": manifest.get("committed_subgraph_id"),
    }


def validate_result(base: Path, payload: dict[str, Any], source: str) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    final_status = str(payload.get("final_status") or "").strip().lower()
    if final_status != "committed":
        missing.append(f"{source}.final_status=committed")
    if not present(payload.get("proposal_bundle")):
        missing.append(f"{source}.proposal_bundle")
    if not present(payload.get("commit_decisions")):
        missing.append(f"{source}.commit_decisions")
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    if not present(graph.get("committed_subgraph_id")) and not present(payload.get("committed_subgraph_id")):
        missing.append(f"{source}.graph.committed_subgraph_id")

    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else None
    if manifest:
        manifest_result = validate_manifest(base, manifest, f"{source}.manifest")
        missing.extend(manifest_result["missing"])
        warnings.extend(manifest_result["warnings"])
    elif not present(payload.get("artifact_paths")):
        warnings.append(f"{source}.manifest missing; pass outputDir so proposal graph artifacts are replayable")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "source": source,
        "final_status": final_status,
        "committed_subgraph_id": graph.get("committed_subgraph_id") or payload.get("committed_subgraph_id"),
    }


def lint(project: str, result_rel: str, manifest_rel: str | None, allow_diagnosis: bool) -> dict[str, Any]:
    base = ar(project)
    missing: list[str] = []
    warnings: list[str] = []
    checked: list[dict[str, Any]] = []

    result_path = resolve_path(base, result_rel)
    result_payload = read_json(result_path) if result_path else None
    if isinstance(result_payload, dict):
        checked.append(validate_result(base, result_payload, relpath(base, result_path) or result_rel))

    manifest_paths: list[Path] = []
    if manifest_rel:
        path = resolve_path(base, manifest_rel)
        if path:
            manifest_paths.append(path)
    manifest_paths.extend(sorted((base / "papernexus/proposal_graph_sessions").glob("*/proposal-session-manifest.json")))

    for path in manifest_paths:
        payload = read_json(path)
        if isinstance(payload, dict):
            checked.append(validate_manifest(base, payload, relpath(base, path) or str(path)))

    complete = any(row.get("complete") for row in checked)
    if not checked:
        missing.append("papernexus/proposal_graph_session.json or papernexus/proposal_graph_sessions/*/proposal-session-manifest.json")
    elif not complete:
        for row in checked:
            missing.extend(row.get("missing", []))
            warnings.extend(row.get("warnings", []))
        if allow_diagnosis and any(row.get("final_status") == "diagnosis" for row in checked):
            warnings.append("proposal graph session reached diagnosis only; downstream ideas must record repair/fallback evidence boundary")
            missing = []
            complete = True

    return {
        "schema_version": 1,
        "complete": complete and not missing,
        "status": "complete" if complete and not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "checked": checked,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--result", default="papernexus/proposal_graph_session.json")
    parser.add_argument("--manifest")
    parser.add_argument("--allow-diagnosis", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.result, args.manifest, args.allow_diagnosis)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
