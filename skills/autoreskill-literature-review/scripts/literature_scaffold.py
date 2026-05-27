#!/usr/bin/env python3
"""Create evidence-bounded literature review scaffolds from available artifacts."""

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


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                item = {"raw_text": line}
            if isinstance(item, dict):
                out.append(item)
    return out


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()
    base = ar(args.project)
    evidence = rows(base / "evidence_cart.jsonl")
    pn = read_json(base / "literature/LITERATURE_DISCOVERY_PACKET.json", {})
    if not evidence and not args.allow_empty:
        raise SystemExit("no evidence_cart entries; pass --allow-empty only for scaffold/demo")
    evidence_lines = "\n".join(f"- `{row.get('evidence_id')}`: {str(row.get('text') or '')[:220]}" for row in evidence) or "- no evidence yet"
    write_text(base / "literature/LITERATURE_REVIEW.md", f"# Literature Review\n\nEvidence-bound scaffold created {now()}.\n\n{evidence_lines}\n")
    write_text(base / "literature/SOTA_MATRIX.md", f"# SOTA Matrix\n\n## Evidence Anchors\n\n{evidence_lines}\n")
    write_text(base / "literature/GAP_SYNTHESIS.md", "# Gap Synthesis\n\nOpen gaps must be backed by evidence ids before claim promotion.\n")
    entries = []
    for row in evidence:
        entries.append(
            {
                "evidence_id": row.get("evidence_id"),
                "source_id": row.get("source_id"),
                "title": row.get("paper_title") or row.get("source_id") or row.get("evidence_id"),
                "status": "queued_for_bibtex",
            }
        )
    write_json(base / "literature/CITATION_QUEUE.json", {"schema_version": 1, "created_at": now(), "entries": entries, "discovery_payload_present": bool(pn)})
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "literature_review", "action": "literature_scaffold", "details": {"evidence_count": len(evidence)}})
    print(json.dumps({"ok": True, "evidence_count": len(evidence)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
