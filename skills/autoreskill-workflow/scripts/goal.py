#!/usr/bin/env python3
"""Single dispatcher for portable AutoResearch /goal commands."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPT = {
    "init": HERE / "goal_state.py",
    "status": HERE / "goal_state.py",
    "advance": HERE / "goal_state.py",
    "block": HERE / "goal_state.py",
    "tick": HERE / "goal_tick.py",
    "repair": HERE / "goal_repair.py",
    "evidence": HERE / "goal_evidence.py",
    "review": HERE / "goal_review.py",
    "package": HERE / "goal_package.py",
    "validate": HERE / "goal_validate.py",
    "fixture": HERE / "goal_fixture.py",
    "lint": HERE / "contract_lint.py",
    "dispatch": HERE / "goal_job_dispatch.py",
    "update-job": HERE / "goal_job_update.py",
    "reconcile": HERE / "goal_job_reconcile.py",
    "subagent-result": HERE / "goal_subagent_result.py",
}


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", choices=sorted(SCRIPT))
    args, rest = parser.parse_known_args()
    subargs = [args.command, *rest] if args.command in {"init", "status", "advance", "block"} else rest
    proc = subprocess.run([sys.executable, str(SCRIPT[args.command]), *subargs], check=False)
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
