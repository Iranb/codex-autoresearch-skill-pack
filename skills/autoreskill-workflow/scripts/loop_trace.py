#!/usr/bin/env python3
"""Append compact recovery events to .autoreskill/LOOP_TRACE.jsonl."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    path = Path(project).expanduser().resolve()
    if path.name == ".autoreskill":
        return path
    return path / ".autoreskill"


def compact(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3:
        return "<truncated>"
    if isinstance(value, dict):
        return {str(key): compact(val, depth=depth + 1) for key, val in value.items()}
    if isinstance(value, list):
        return [compact(item, depth=depth + 1) for item in value[:25]]
    if isinstance(value, str) and len(value) > 1000:
        return value[:997] + "..."
    return value


def append_trace(
    base: Path,
    *,
    event: str,
    stage: str | None = None,
    job_id: str | None = None,
    authority: str,
    decision: str | None = None,
    evidence_refs: list[str] | None = None,
    next_action: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ts": now(),
        "event": event,
        "authority": authority,
    }
    if stage:
        entry["stage"] = stage
    if job_id:
        entry["job_id"] = job_id
    if decision:
        entry["decision"] = decision
    if evidence_refs:
        entry["evidence_refs"] = evidence_refs
    if next_action:
        entry["next_action"] = next_action
    if reason:
        entry["reason"] = reason
    if details:
        entry["details"] = compact(details)

    path = base / "LOOP_TRACE.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--stage", default="")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--authority", default="manual")
    parser.add_argument("--decision", default="")
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--next-action", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--details-json", default="")
    args = parser.parse_args()

    details: dict[str, Any] | None = None
    if args.details_json:
        loaded = json.loads(args.details_json)
        if not isinstance(loaded, dict):
            raise SystemExit("--details-json must decode to a JSON object")
        details = loaded

    base = ar(args.project)
    entry = append_trace(
        base,
        event=args.event,
        stage=args.stage or None,
        job_id=args.job_id or None,
        authority=args.authority,
        decision=args.decision or None,
        evidence_refs=args.evidence_ref,
        next_action=args.next_action or None,
        reason=args.reason or None,
        details=details,
    )
    print(json.dumps({"ok": True, "trace": str(base / "LOOP_TRACE.jsonl"), "entry": entry}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
