#!/usr/bin/env python3
"""Append concise durable memory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--section", default="Note")
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    path = Path(args.project).expanduser().resolve() / ".autoreskill" / "memory.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# AutoResearch Memory\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {args.section}\n\n")
        handle.write(f"- {datetime.now(timezone.utc).isoformat()}: {args.text}\n")
    print(str(path))


if __name__ == "__main__":
    main()
