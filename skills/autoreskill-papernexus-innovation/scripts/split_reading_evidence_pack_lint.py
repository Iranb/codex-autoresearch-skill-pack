#!/usr/bin/env python3
"""Lint PaperNexus split-reading evidence packs for pre-idea ideation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROLE_FIELDS = {
    "closest_prior": ["closest_prior_anchors", "closest_priors"],
    "baseline_protocol": ["baseline_protocol_anchors", "protocol_anchors", "baseline_anchors"],
    "dataset_metric": ["dataset_metric_anchors", "dataset_anchors", "metric_anchors"],
    "mechanism": ["mechanism_layers", "mechanisms"],
    "limitation_future": ["future_layers", "limitation_layers", "limitations", "future_work"],
    "negative_evidence": ["negative_evidence_layers", "negative_evidence"],
    "challenge_anchor": ["challenge_anchors", "target_challenges"],
    "transfer_bridge": ["transfer_takeaways", "transfer_bridges"],
}
REQUIRED_ROLES = ["closest_prior", "baseline_protocol", "mechanism", "limitation_future", "negative_evidence"]


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


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def role_count(payload: dict[str, Any], role: str) -> int:
    count = 0
    for field in ROLE_FIELDS.get(role, []):
        value = payload.get(field)
        if isinstance(value, list):
            count += len(value)
        elif present(value):
            count += 1
    for overlay in as_list(payload.get("role_overlays")):
        if isinstance(overlay, dict):
            roles = overlay.get("roles") or overlay.get("role_tags") or []
            if isinstance(roles, str):
                roles = [roles]
            if role in {str(item) for item in roles}:
                count += 1
    for view in as_list(payload.get("paper_material_views")):
        if isinstance(view, dict):
            roles = view.get("roles") or view.get("role_tags") or []
            if isinstance(roles, str):
                roles = [roles]
            if role in {str(item) for item in roles}:
                count += 1
    return count


def lint(project: str, rel: str) -> dict[str, Any]:
    base = ar(project)
    path = base / rel
    payload = read_json(path)
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": [rel], "warnings": [], "path": str(path)}

    for key in ["packet_id", "source", "paper_material_views", "source_spans", "provenance_refs", "evidence_boundaries"]:
        if not present(payload.get(key)):
            missing.append(key)
    source = str(payload.get("source") or "").lower()
    if source and "papernexus" not in source:
        missing.append("source must identify papernexus-remote or PaperNexus")

    counts = {role: role_count(payload, role) for role in ROLE_FIELDS}
    for role in REQUIRED_ROLES:
        if counts.get(role, 0) < 1:
            missing.append(f"role coverage missing: {role}")
    if counts.get("transfer_bridge", 0) < 1:
        warnings.append("transfer_bridge role missing; far-neighbor storyline may be weak")
    if counts.get("dataset_metric", 0) < 1:
        warnings.append("dataset_metric role missing; experiment_plan must close protocol anchors")

    boundaries = payload.get("evidence_boundaries") if isinstance(payload.get("evidence_boundaries"), dict) else {}
    if not present(boundaries.get("source_backed")) and not present(boundaries.get("source-backed")):
        missing.append("evidence_boundaries.source_backed")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(path),
        "role_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--pack", default="papernexus/SPLIT_READING_EVIDENCE_PACK.json")
    args = parser.parse_args()
    out = lint(args.project, args.pack)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
