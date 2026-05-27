#!/usr/bin/env python3
"""Check whether an automated action is within policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_policy(project: str) -> dict[str, Any]:
    path = Path(project).expanduser().resolve() / ".autoreskill" / "autopilot_policy.json"
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--request", required=True, choices=["provider_evidence", "live_discovery", "literature_discovery", "open_access_import", "remote_experiment", "claim_downgrade"])
    parser.add_argument("--gpu-hours", type=float, default=0.0)
    parser.add_argument("--walltime-hours", type=float, default=0.0)
    args = parser.parse_args()

    policy = read_policy(args.project)
    allowed = True
    reasons: list[str] = []
    key = {
        "provider_evidence": "allow_provider_evidence",
        "live_discovery": "allow_live_discovery",
        "literature_discovery": "allow_literature_discovery",
        "open_access_import": "allow_open_access_imports",
        "remote_experiment": "allow_remote_experiment_launch",
        "claim_downgrade": "allow_claim_downgrade",
    }[args.request]
    if not policy.get(key, False):
        allowed = False
        reasons.append(f"{key}=false")
    if args.request == "remote_experiment":
        if args.gpu_hours > float(policy.get("max_experiment_gpu_hours", 0)):
            allowed = False
            reasons.append("gpu_hours_exceeds_policy")
        if args.walltime_hours > float(policy.get("max_experiment_walltime_hours", 0)):
            allowed = False
            reasons.append("walltime_hours_exceeds_policy")
    print(json.dumps({"allowed": allowed, "reasons": reasons, "policy": policy.get("autonomy_level")}, indent=2))
    raise SystemExit(0 if allowed else 1)


if __name__ == "__main__":
    main()
