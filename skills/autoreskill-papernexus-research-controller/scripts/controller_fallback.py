#!/usr/bin/env python3
"""Materialize a degraded research_controller fallback design review."""

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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--reason", default="research_controller unavailable from current papernexus-remote MCP session")
    args = parser.parse_args()
    base = ar(args.project)
    caps = read_json(base / "capabilities.json", {"schema_version": 1})
    caps["research_controller_available"] = False
    caps["updated_at"] = now()
    notes = list(caps.get("notes") or [])
    notes.append(args.reason)
    caps["notes"] = notes
    write_json(base / "capabilities.json", caps)
    review = {
        "schema_version": 1,
        "created_at": now(),
        "status": "degraded_fallback",
        "verdict": "open_with_constraints",
        "source": "ideation-panel fallback",
        "reason": args.reason,
        "required_before_innovation_packet": [
            "PaperNexus evidence ids must be present",
            "negative evidence must be present or absence_confidence documented",
            "falsifier and weakest assumption must be explicit",
        ],
        "blocking_issues": [],
        "limitations": [
            "No live research_controller export was available in this Codex session.",
            "Do not call downstream claims graph-grounded unless PaperNexus MCP artifacts exist.",
        ],
    }
    write_json(base / "ideation/PANEL_DESIGN_REVIEW.json", review)
    write_json(base / "papernexus/research_controller/design-review.json", review)
    write_text(
        base / "papernexus/research_controller/design-review.md",
        "# Research Controller Design Review\n\n"
        "Status: degraded fallback.\n\n"
        f"Reason: {args.reason}\n\n"
        "This is a workflow continuity artifact, not graph-grounded PaperNexus evidence.\n",
    )
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "ideation", "action": "controller_fallback_design_review", "details": review})
    print(json.dumps({"ok": True, "design_review": ".autoreskill/papernexus/research_controller/design-review.json"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
