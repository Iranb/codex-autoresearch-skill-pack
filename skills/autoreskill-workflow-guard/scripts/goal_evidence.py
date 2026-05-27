#!/usr/bin/env python3
"""Summarize and export .autoreskill evidence, artifacts, and stage contracts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contract_lint import lint
from goal_state import STAGES, ar, load_state


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            item = {"raw_text": line}
        if isinstance(item, dict):
            out.append(item)
    return out


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def as_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# AutoResearch Evidence Packet",
        "",
        f"Created: {packet['created_at']}",
        f"Project: `{packet['project_root']}`",
        f"Stage: `{packet['state'].get('stage')}`",
        f"PaperNexus callable: `{packet['capabilities'].get('papernexus_remote_callable')}`",
        "",
        "## Stage Contracts",
        "",
    ]
    for row in packet["stage_contracts"]:
        missing = ", ".join(row.get("missing") or [])
        lines.append(f"- `{row['stage']}`: `{row['status']}`" + (f" missing: {missing}" if missing else ""))
    lines.extend(["", "## Evidence Cart", ""])
    if not packet["evidence"]:
        lines.append("- none")
    for row in packet["evidence"]:
        evid = row.get("evidence_id") or "unknown"
        source = row.get("source_id") or row.get("source_type") or "unknown"
        text = str(row.get("text") or row.get("note") or "").strip()
        lines.append(f"- `{evid}` from `{source}`: {text[:240]}")
    lines.extend(["", "## Artifacts", ""])
    artifacts = packet["artifacts"].get("artifacts", []) if isinstance(packet["artifacts"], dict) else []
    if not artifacts:
        lines.append("- none")
    for row in artifacts:
        lines.append(f"- `{row.get('path')}` ({row.get('kind')}, stage `{row.get('stage')}`)")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", action="append")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--output", help="write JSON evidence packet to this path")
    parser.add_argument("--markdown", help="write Markdown evidence packet to this path")
    args = parser.parse_args()

    project = str(Path(args.project).expanduser().resolve())
    base = ar(project)
    state = load_state(project)
    evidence = rows(base / "evidence_cart.jsonl")
    if args.tag:
        wanted = set(args.tag)
        evidence = [row for row in evidence if wanted.intersection(set(row.get("tags") or []))]
    stages = args.stage or STAGES
    packet = {
        "schema_version": 1,
        "created_at": now(),
        "project_root": project,
        "state": state,
        "capabilities": read_json(base / "capabilities.json", {}),
        "stage_contracts": [lint(project, stage) for stage in stages],
        "evidence": evidence,
        "artifacts": read_json(base / "artifacts_index.json", {"schema_version": 1, "artifacts": []}),
        "recent_blockers": rows(base / "blocker_ledger.jsonl")[-20:],
        "recent_decisions": rows(base / "decision_log.jsonl")[-20:],
    }
    if args.output:
        out = Path(args.output).expanduser()
        if not out.is_absolute():
            out = base / out
        write_json(out, packet)
    if args.markdown:
        out_md = Path(args.markdown).expanduser()
        if not out_md.is_absolute():
            out_md = base / out_md
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(as_markdown(packet), encoding="utf-8")
    print(json.dumps(packet, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
