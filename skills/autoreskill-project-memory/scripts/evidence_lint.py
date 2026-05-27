#!/usr/bin/env python3
"""Lint evidence cart rows for reuse and provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--require-reuse", action="store_true")
    args = parser.parse_args()
    evidence = rows(ar(args.project) / "evidence_cart.jsonl")
    missing = []
    ids = set()
    for idx, row in enumerate(evidence):
        prefix = f"evidence_cart[{idx}]"
        evid = row.get("evidence_id")
        if not evid:
            missing.append(f"{prefix}.evidence_id")
        elif evid in ids:
            missing.append(f"{prefix}.duplicate evidence_id {evid}")
        ids.add(evid)
        for key in ["source_type", "source_id", "text", "provenance"]:
            if not row.get(key):
                missing.append(f"{prefix}.{key}")
    if args.require_reuse:
        used = set()
        base = ar(args.project)
        for rel in ["ideation/CANDIDATE_POOL.json", "orchestrator/INNOVATION_PACKET.json", "analyzer/CLAIM_EVIDENCE_MATRIX.md", "paper/write_package.json"]:
            path = base / rel
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore")
                used.update(eid for eid in ids if eid and eid in text)
        if ids and not used:
            missing.append("no evidence_id reused by ideation/plan/analysis/writing artifacts")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "evidence_count": len(evidence)}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
