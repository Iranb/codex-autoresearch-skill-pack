#!/usr/bin/env python3
"""Append a role handoff packet under .autoreskill/handoffs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--from", dest="from_role", required=True)
    parser.add_argument("--to", dest="to_role", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--allowed-write", action="append", default=[])
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--acceptance", action="append", default=[])
    args = parser.parse_args()

    base = Path(args.project).expanduser().resolve() / ".autoreskill"
    out_dir = base / "handoffs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_to = args.to_role.replace(" ", "_")
    safe_from = args.from_role.replace(" ", "_")
    path = out_dir / f"{stamp}__{safe_from}__to__{safe_to}.json"
    packet = {
        "schema_version": 1,
        "created_at": now(),
        "from": args.from_role,
        "to": args.to_role,
        "stage": args.stage,
        "goal": args.goal,
        "inputs": args.input,
        "allowed_writes": args.allowed_write,
        "constraints": args.constraint,
        "outputs": args.output,
        "acceptance_criteria": args.acceptance,
    }
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(path), "packet": packet}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
