#!/usr/bin/env python3
"""Manage .autoreskill evidence cart."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cart(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill" / "evidence_cart.jsonl"


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_add(args: argparse.Namespace) -> None:
    path = cart(args.project)
    evidence_id = args.evidence_id or f"ev_{uuid.uuid4().hex[:12]}"
    row = {
        "schema_version": 1,
        "evidence_id": evidence_id,
        "created_at": now(),
        "stage": args.stage,
        "source_type": args.source_type,
        "source_id": args.source_id,
        "item_type": args.item_type,
        "paper_id": args.paper_id,
        "text": args.text,
        "tags": args.tag,
        "confidence": args.confidence,
        "provenance": args.provenance,
    }
    append(path, row)
    print(json.dumps(row, indent=2, ensure_ascii=False))


def matches(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.tag and args.tag not in row.get("tags", []):
        return False
    if args.stage and args.stage != row.get("stage"):
        return False
    if args.source_type and args.source_type != row.get("source_type"):
        return False
    return True


def cmd_list(args: argparse.Namespace) -> None:
    selected = [row for row in rows(cart(args.project)) if matches(row, args)]
    if args.limit:
        selected = selected[-args.limit :]
    print(json.dumps(selected, indent=2, ensure_ascii=False))


def cmd_export(args: argparse.Namespace) -> None:
    selected = [row for row in rows(cart(args.project)) if matches(row, args)]
    if args.limit:
        selected = selected[-args.limit :]
    packet = {"schema_version": 1, "exported_at": now(), "count": len(selected), "evidence": selected}
    print(json.dumps(packet, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add")
    p.add_argument("--project", required=True)
    p.add_argument("--evidence-id")
    p.add_argument("--stage")
    p.add_argument("--source-type", required=True)
    p.add_argument("--source-id")
    p.add_argument("--item-type", required=True)
    p.add_argument("--paper-id")
    p.add_argument("--text", required=True)
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--confidence", default="medium")
    p.add_argument("--provenance")
    p.set_defaults(func=cmd_add)

    for name, func in [("list", cmd_list), ("export", cmd_export)]:
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)
        p.add_argument("--tag")
        p.add_argument("--stage")
        p.add_argument("--source-type")
        p.add_argument("--limit", type=int)
        p.set_defaults(func=func)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
