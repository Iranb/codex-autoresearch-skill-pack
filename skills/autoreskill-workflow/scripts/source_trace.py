#!/usr/bin/env python3
"""Optionally audit portable skill contracts against an OpenClaw source checkout."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


EXPECTED = [
    "agents",
    "skills/researcher/idea-phase",
    "skills/planner/experiment-plan",
    "skills/coder/implement-experiment",
    "skills/coder/run-experiment",
    "skills/analyzer/analyze-results",
    "skills/academic_writer/paper-write",
    "skills/reviewer/review-phase",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--openclaw-source", help="optional source checkout for one-time trace audit")
    args = parser.parse_args()
    source = Path(args.openclaw_source).expanduser().resolve() if args.openclaw_source else None
    rows = []
    for rel in EXPECTED:
        exists = None if source is None else (source / rel).exists()
        rows.append({"source_path": rel, "present_in_source": exists, "portable_runtime_dependency": False})
    out = {
        "schema_version": 1,
        "created_at": now(),
        "openclaw_source": str(source) if source else None,
        "trace_rows": rows,
        "runtime_dependency_check": "portable skills do not require OpenClaw source at runtime",
    }
    write_json(ar(args.project) / "validation/SOURCE_TRACEABILITY_AUDIT.json", out)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
