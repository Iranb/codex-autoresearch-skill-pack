#!/usr/bin/env python3
"""Record PaperNexus MCP availability and feature observations."""

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


def parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    text = value.strip().lower()
    if text in {"1", "true", "yes", "y", "callable"}:
        return True
    if text in {"0", "false", "no", "n", "unavailable", "not_callable"}:
        return False
    if text in {"unknown", "null", "none"}:
        return None
    raise SystemExit(f"invalid boolean value: {value}")


def read_payload(path: str | None) -> Any:
    if not path:
        return None
    text = Path(path).expanduser().read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--callable", choices=["true", "false", "unknown"], required=True)
    parser.add_argument("--error", default="")
    parser.add_argument("--corpus")
    parser.add_argument("--corpora-json")
    parser.add_argument("--operation", action="append", default=[])
    parser.add_argument("--research-controller", choices=["true", "false", "unknown"])
    parser.add_argument("--method-atlas", choices=["true", "false", "unknown"])
    parser.add_argument("--note", action="append", default=[])
    args = parser.parse_args()

    base = ar(args.project)
    caps_path = base / "capabilities.json"
    caps = read_json(caps_path, {"schema_version": 1, "notes": []})
    operations = sorted(set(args.operation))
    research_controller = parse_bool(args.research_controller)
    if research_controller is None and operations:
        research_controller = "research_controller" in operations

    caps.update(
        {
            "schema_version": 1,
            "papernexus_remote_callable": parse_bool(args.callable),
            "papernexus_remote_error": args.error or None,
            "active_corpus": args.corpus or caps.get("active_corpus"),
            "agent_materials_operations": operations or caps.get("agent_materials_operations", []),
            "research_controller_available": research_controller,
            "method_atlas_lookup_available": parse_bool(args.method_atlas),
            "updated_at": now(),
        }
    )
    notes = list(caps.get("notes") or [])
    notes.extend(args.note)
    if args.error:
        notes.append(f"PaperNexus probe error: {args.error}")
    caps["notes"] = notes
    write_json(caps_path, caps)

    corpora_payload = read_payload(args.corpora_json)
    if corpora_payload is not None:
        write_json(
            base / "papernexus/corpus_status.json",
            {
                "schema_version": 1,
                "captured_at": now(),
                "source": "papernexus-remote.list_corpora",
                "active_corpus": args.corpus,
                "payload": corpora_payload,
            },
        )

    decision = {
        "ts": now(),
        "stage": "capability_probe",
        "action": "record_papernexus_probe",
        "details": {
            "papernexus_remote_callable": caps["papernexus_remote_callable"],
            "active_corpus": caps.get("active_corpus"),
            "agent_materials_operations": caps.get("agent_materials_operations", []),
            "research_controller_available": caps.get("research_controller_available"),
            "method_atlas_lookup_available": caps.get("method_atlas_lookup_available"),
            "error": args.error or None,
        },
    }
    append_jsonl(base / "decision_log.jsonl", decision)
    print(json.dumps(caps, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
