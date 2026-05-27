#!/usr/bin/env python3
"""Classify PaperNexus evidence as graph, discovery, inference, or open risk."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


GRAPH_KINDS = {
    "graph_build_decision",
    "research_material_pack",
    "negative_evidence_pack",
    "graph_ideation_packet",
    "idea_catalyst_contract",
    "idea_catalyst_evidence_export",
}
DISCOVERY_KINDS = {"literature_discovery_packet", "literature_discovery_run", "source_discovery_plan"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--ttl-hours", type=float, default=168)
    args = parser.parse_args()

    base = ar(args.project)
    index = read_json(base / "artifacts_index.json", {"artifacts": []})
    caps = read_json(base / "capabilities.json", {})
    cutoff = now() - timedelta(hours=args.ttl_hours)
    rows = []
    stale = []
    graph_count = 0
    discovery_count = 0
    for item in index.get("artifacts", []):
        kind = item.get("kind")
        updated = parse_ts(item.get("updated_at"))
        if kind in GRAPH_KINDS:
            category = "graph_grounded" if caps.get("papernexus_remote_callable") is True else "graph_claim_unverified_in_session"
            graph_count += 1
        elif kind in DISCOVERY_KINDS:
            category = "discovery_evidence"
            discovery_count += 1
        else:
            category = "inference_or_local_artifact"
        is_stale = bool(updated and updated < cutoff)
        if is_stale:
            stale.append(item.get("path"))
        rows.append({**item, "evidence_category": category, "stale": is_stale})

    missing = []
    if graph_count == 0:
        missing.append("no graph-grounded PaperNexus artifacts")
    if caps.get("papernexus_remote_callable") is not True:
        missing.append("papernexus_remote not callable in current session")

    out = {
        "schema_version": 1,
        "status": "complete" if not missing else "degraded",
        "complete": not missing,
        "missing": missing,
        "warnings": [f"stale artifact: {path}" for path in stale],
        "graph_artifact_count": graph_count,
        "discovery_artifact_count": discovery_count,
        "artifacts": rows,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
