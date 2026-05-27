#!/usr/bin/env python3
"""Lint ideation panel artifacts and candidate pool constraints."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"stdout": proc.stdout}
    parsed.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--require-selected", action="store_true")
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

    skill_root = Path(__file__).resolve().parents[2]
    pool_cmd = [
        sys.executable,
        str(skill_root / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
        "--project",
        str(Path(args.project).expanduser().resolve()),
        "--pool",
        "ideation/EXPERIMENT_IDEA_POOL.json",
    ]
    if args.require_selected:
        pool_cmd.append("--require-selected")
    pool_lint = run_json(pool_cmd)
    if not pool_lint.get("complete"):
        items = pool_lint.get("missing") if isinstance(pool_lint.get("missing"), list) else []
        missing.extend(f"idea_pool_lint: {item}" for item in items)
        if pool_lint.get("returncode", 1) != 0 and not items:
            missing.append("idea_pool_lint failed without structured missing output")

    out = {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "candidate_count": len(rows),
        "idea_pool_lint": pool_lint,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
