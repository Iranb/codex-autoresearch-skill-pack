#!/usr/bin/env python3
"""Render a job packet into a sub-agent or serialized role-pass prompt."""

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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing job packet: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_subagent_request(project: str, base: Path, packet: dict[str, Any], prompt_path: Path) -> Path:
    request_path = base / "job_packets" / f"{packet['job_id']}.subagent_request.json"
    request = {
        "schema_version": 1,
        "created_at": now(),
        "job_id": packet.get("job_id"),
        "agent_type": "worker",
        "role": packet.get("role"),
        "skill": packet.get("skill"),
        "project_root": str(Path(project).expanduser().resolve()),
        "message_path": str(prompt_path),
        "expected_result_recorder": (
            f"python {Path(__file__).with_name('goal_subagent_result.py')} "
            f"--project \"{Path(project).expanduser().resolve()}\" --job-id {packet.get('job_id')} "
            "--agent-id <agent-id> --status completed --artifact <artifact-path>"
        ),
        "spawn_policy": {
            "use_multi_agent_tool": "multi_agent_v1.spawn_agent",
            "do_not_spawn_from_python": True,
            "owner_agent_must_review_artifacts": True,
        },
    }
    write_json(request_path, request)
    return request_path


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def queue_path(base: Path, packet: dict[str, Any]) -> Path:
    queue = str(packet.get("queue") or "")
    if queue:
        return base / queue
    kind = str(packet.get("job_kind") or "repair")
    return base / ("async_jobs.jsonl" if kind == "async" else "repair_queue.jsonl")


def update_queue(base: Path, packet: dict[str, Any], status: str) -> None:
    path = queue_path(base, packet)
    data = rows(path)
    for row in data:
        if row.get("job_id") == packet.get("job_id"):
            row["status"] = status
            row["updated_at"] = now()
            row["dispatch_prompt"] = f".autoreskill/job_packets/{packet['job_id']}.prompt.md"
    write_rows(path, data)


def bullet(items: list[Any]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- `{item}`" if isinstance(item, str) else f"- `{json.dumps(item, ensure_ascii=False)}`" for item in items)


def render_prompt(project: str, packet: dict[str, Any], mode: str) -> str:
    mcp_calls = packet.get("mcp_calls") or []
    capture_commands = packet.get("capture_commands") or []
    constraints = packet.get("constraints") or []
    outputs = packet.get("outputs") or []
    acceptance = packet.get("acceptance_criteria") or []
    inputs = packet.get("inputs") or []

    return f"""# AutoResearch Job Packet

Mode: `{mode}`
Project root: `{Path(project).expanduser().resolve()}`
Job id: `{packet.get('job_id')}`
Stage: `{packet.get('stage')}`
Role: `{packet.get('role')}`
Skill to use: `{packet.get('skill')}`

## Goal

{packet.get('goal')}

## Required Inputs

{bullet(inputs)}

## Missing Contract Signals

{bullet(packet.get('missing') or [])}

## MCP Calls

{bullet(mcp_calls)}

If a PaperNexus MCP call fails at config, transport, auth, or session-tool-mount level, do not use local PaperNexus CLI, raw HTTP, local graph files, local MCP, or SSH graph commands as substitutes. Record the failure with `papernexus_probe_record.py` when relevant and update this job as `failed` or `retry`.

## Capture Commands

{bullet(capture_commands)}

Run capture commands only after the corresponding MCP or role-pass result exists. Replace placeholders such as `<project-root>`, `<mcp-result.json>`, and `<corpus>` with real values.

## Allowed Writes

{bullet(packet.get('allowed_writes') or [])}

## Constraints

{bullet(constraints)}

## Expected Outputs

{bullet(outputs)}

## Acceptance Criteria

{bullet(acceptance)}

## Completion Update

After successful execution:

```bash
python ~/.codex/skills/autoreskill-workflow/scripts/goal_job_update.py --project "{Path(project).expanduser().resolve()}" --kind {packet.get('job_kind') or 'repair'} --job-id {packet.get('job_id')} --status completed --artifact <artifact-path>
```

If execution fails:

```bash
python ~/.codex/skills/autoreskill-workflow/scripts/goal_job_update.py --project "{Path(project).expanduser().resolve()}" --kind {packet.get('job_kind') or 'repair'} --job-id {packet.get('job_id')} --status failed --error "<exact blocker>"
```
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--mode", choices=["serialized", "subagent"], default="serialized")
    parser.add_argument("--mark-running", action="store_true")
    args = parser.parse_args()

    base = ar(args.project)
    packet_path = base / "job_packets" / f"{args.job_id}.json"
    packet = read_json(packet_path)
    prompt_path = base / "job_packets" / f"{args.job_id}.prompt.md"
    prompt_path.write_text(render_prompt(args.project, packet, args.mode), encoding="utf-8")
    subagent_request = None
    if args.mode == "subagent":
        subagent_request = write_subagent_request(args.project, base, packet, prompt_path)

    packet["status"] = "prompt_ready"
    packet["dispatch_mode"] = args.mode
    packet["dispatch_prompt"] = str(prompt_path)
    if subagent_request:
        packet["subagent_request"] = str(subagent_request)
    packet["dispatched_at"] = now()
    write_json(packet_path, packet)
    if args.mark_running:
        update_queue(base, packet, "running")

    append_jsonl(
        base / "mailbox.jsonl",
        {
            "ts": now(),
            "type": "job_dispatch_prompt",
            "job_id": args.job_id,
            "stage": packet.get("stage"),
            "to": packet.get("role"),
            "skill": packet.get("skill"),
            "mode": args.mode,
            "path": str(prompt_path),
            "subagent_request": str(subagent_request) if subagent_request else None,
        },
    )
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": packet.get("stage"),
            "action": "job_dispatch_prompt",
            "details": {
                "job_id": args.job_id,
                "mode": args.mode,
                "path": str(prompt_path),
                "subagent_request": str(subagent_request) if subagent_request else None,
            },
        },
    )
    print(
        json.dumps(
            {
                "ok": True,
                "prompt": str(prompt_path),
                "packet": str(packet_path),
                "subagent_request": str(subagent_request) if subagent_request else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
