#!/usr/bin/env python3
"""Lint ideation panel artifacts and candidate pool constraints."""

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


def candidates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["candidates", "tracks", "ideas"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    pool = read_json(base / "ideation/CANDIDATE_POOL.json")
    tournament = read_json(base / "ideation/TOURNAMENT_SCOREBOARD.json")
    contract = read_json(base / "ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json")
    missing = []
    if not pool:
        missing.append("ideation/CANDIDATE_POOL.json")
    if not tournament:
        missing.append("ideation/TOURNAMENT_SCOREBOARD.json")
    rows = candidates(pool)
    for idx, row in enumerate(rows):
        prefix = f"CANDIDATE_POOL[{idx}]"
        if str(row.get("status") or row.get("verdict") or "").lower() not in {"advance", "park", "kill", "advance_with_constraints"}:
            missing.append(f"{prefix}.status advance/park/kill")
        for key in ["evidence_ids", "weakest_assumption", "falsifier"]:
            if not row.get(key):
                missing.append(f"{prefix}.{key}")
    if contract and str(contract.get("status", "")).lower() == "ready" and not rows:
        missing.append("ready IDEA_CATALYST_CONTRACT requires candidate pool")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "candidate_count": len(rows)}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
