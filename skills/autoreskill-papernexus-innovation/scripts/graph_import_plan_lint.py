#!/usr/bin/env python3
"""Lint PaperNexus graph/material import plans before submission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LANES = {"target_domain", "near_neighbor", "far_neighbor"}


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


def papers(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("selected_papers"), list):
        return [row for row in payload["selected_papers"] if isinstance(row, dict)]
    return []


def lint(project: str, rel: str) -> dict[str, Any]:
    base = ar(project)
    path = base / rel
    payload = read_json(path)
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": [rel], "warnings": [], "path": str(path)}
    rows = papers(payload)
    if not rows:
        missing.append("selected_papers")
    lane_seen: set[str] = set()
    role_seen: set[str] = set()
    idempotency_keys: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"selected_papers[{index}]"
        lane = str(row.get("lane") or "").strip()
        if lane not in LANES:
            missing.append(f"{prefix}.lane")
        else:
            lane_seen.add(lane)
        roles = row.get("roles") if isinstance(row.get("roles"), list) else []
        if not roles:
            missing.append(f"{prefix}.roles")
        role_seen.update(str(role) for role in roles)
        for key in ["paper_ref", "title", "selection_reason", "source_resolution_status", "import_action"]:
            if not present(row.get(key)):
                missing.append(f"{prefix}.{key}")
        action = str(row.get("import_action") or "")
        if action not in {"import", "supplement", "material_view", "skip_existing"}:
            missing.append(f"{prefix}.import_action import/supplement/material_view/skip_existing")
        idem = str(row.get("idempotency_key") or "").strip()
        if idem:
            if idem in idempotency_keys:
                missing.append(f"{prefix}.idempotency_key duplicate")
            idempotency_keys.add(idem)
    missing_lanes = sorted(LANES - lane_seen)
    if missing_lanes:
        missing.append("selected_papers missing lanes: " + ", ".join(missing_lanes))
    for key in ["lane_balance", "role_balance", "import_batches", "material_requests", "split_reading_requests", "blocked_papers", "idempotency_keys"]:
        if key not in payload:
            missing.append(key)
    if not ({"closest_prior", "baseline_protocol", "mechanism", "limitation_future", "negative_evidence"} & role_seen):
        warnings.append("selected roles do not include the core evidence roles; split-reading gate will likely fail")
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(path),
        "selected_paper_count": len(rows),
        "lanes": sorted(lane_seen),
        "roles": sorted(role_seen),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", default="papernexus/GRAPH_IMPORT_PLAN.json")
    args = parser.parse_args()
    out = lint(args.project, args.plan)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
