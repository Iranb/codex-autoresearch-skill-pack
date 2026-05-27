#!/usr/bin/env python3
"""Materialize a research-controller innovation brief boundary artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


READY = {"ready", "complete", "completed", "pass", "passed", "approved", "verified"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any = None) -> Any:
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


def relpath(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def first_present(*values: Any) -> Any:
    for value in values:
        if present(value):
            return value
    return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def design_ready(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return str(payload.get("status") or payload.get("verdict") or payload.get("decision") or "").lower() in READY


def collect_boundary(payload: Any, keys: list[str]) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    for key in keys:
        if present(payload.get(key)):
            return as_list(payload[key])
    nested = payload.get("evidence_boundaries") or payload.get("evidenceBoundaries")
    if isinstance(nested, dict):
        for key in keys:
            if present(nested.get(key)):
                return as_list(nested[key])
    return []


def build_brief(project: str, output: Path | None = None) -> dict[str, Any]:
    base = ar(project)
    export_path = base / "papernexus/research_controller/controller-export.json"
    design_path = base / "papernexus/research_controller/design-review.json"
    fallback_path = base / "ideation/PANEL_DESIGN_REVIEW.json"
    selected_subgraphs_path = base / "papernexus/research_controller/selected-subgraphs.json"

    export = read_json(export_path, {})
    design = read_json(design_path, None)
    fallback = read_json(fallback_path, None)
    selected_subgraphs = read_json(selected_subgraphs_path, [])
    review_payload = design if design is not None else fallback
    review_path = design_path if design is not None else fallback_path
    source = "research_controller" if design is not None else "fallback_panel"

    selected_id = first_present(
        export.get("selected_idea_fragment_id") if isinstance(export, dict) else None,
        export.get("selectedIdeaFragmentId") if isinstance(export, dict) else None,
        review_payload.get("selected_idea_fragment_id") if isinstance(review_payload, dict) else None,
        review_payload.get("selectedIdeaFragmentId") if isinstance(review_payload, dict) else None,
    )

    source_backed = collect_boundary(export, ["source_backed", "sourceBacked", "what_is_evidence_supported", "evidence_supported"])
    agent_inferred = collect_boundary(export, ["agent_inferred", "agentInferred", "what_is_agent_inferred"])
    speculative = collect_boundary(export, ["speculative", "what_is_speculative"])
    unsupported = collect_boundary(export, ["unsupported", "unsupported_or_open_gaps", "open_gaps"])

    brief = {
        "schema_version": 1,
        "created_at": now(),
        "status": "ready" if design_ready(review_payload) else "needs_review",
        "source": source,
        "selected_idea_fragment_id": selected_id,
        "selected_subgraph_ids": [row.get("id") if isinstance(row, dict) else row for row in as_list(selected_subgraphs)],
        "controller_export_path": relpath(base, export_path),
        "design_review_path": relpath(base, review_path),
        "what_is_evidence_supported": source_backed,
        "what_is_agent_inferred": agent_inferred,
        "what_is_speculative": speculative,
        "unsupported_or_open_gaps": unsupported,
        "evidence_boundaries": {
            "source_backed": source_backed,
            "agent_inferred": agent_inferred,
            "speculative": speculative,
            "unsupported": unsupported,
        },
    }
    out = output or base / "papernexus/research_controller/innovation-brief.json"
    write_json(out, brief)
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": "experiment_plan",
            "action": "controller_innovation_brief",
            "details": {"path": relpath(base, out), "status": brief["status"], "source": source},
        },
    )
    brief["path"] = relpath(base, out)
    return brief


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    base = ar(args.project)
    output = Path(args.output).expanduser() if args.output else None
    if output and not output.is_absolute():
        output = base / output
    out = build_brief(args.project, output)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if str(out.get("status", "")).lower() in READY else 1)


if __name__ == "__main__":
    main()
