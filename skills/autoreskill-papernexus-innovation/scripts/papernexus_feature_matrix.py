#!/usr/bin/env python3
"""Write a PaperNexus feature matrix from MCP probe observations."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--callable", choices=["true", "false", "unknown"], default="unknown")
    parser.add_argument("--operation", action="append", default=[])
    parser.add_argument("--tool", action="append", default=[])
    parser.add_argument("--error", default="")
    args = parser.parse_args()

    base = ar(args.project)
    callable_value = {"true": True, "false": False, "unknown": None}[args.callable]
    operations = sorted(set(args.operation))
    tools = sorted(set(args.tool))
    matrix = {
        "schema_version": 1,
        "updated_at": now(),
        "papernexus_remote_callable": callable_value,
        "mcp_tools_observed": tools,
        "agent_materials_operations": operations,
        "research_controller_available": "research_controller" in operations if operations else None,
        "method_atlas_lookup_available": any("method" in tool or "method" in op for tool in tools for op in operations) if (tools or operations) else None,
        "error": args.error or None,
    }
    write_json(base / "papernexus/FEATURE_MATRIX.json", matrix)
    caps = read_json(base / "capabilities.json", {"schema_version": 1})
    caps.update({k: v for k, v in matrix.items() if k not in {"schema_version", "mcp_tools_observed", "error"}})
    caps["papernexus_remote_error"] = args.error or caps.get("papernexus_remote_error")
    caps["updated_at"] = now()
    write_json(base / "capabilities.json", caps)
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "capability_probe", "action": "papernexus_feature_matrix", "details": matrix})
    print(json.dumps(matrix, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
