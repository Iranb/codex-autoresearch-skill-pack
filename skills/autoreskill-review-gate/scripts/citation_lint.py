#!/usr/bin/env python3
"""Lint citation queue/reporting integrity before package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    queue = read_json(base / "literature/CITATION_QUEUE.json")
    refs = nonempty(base / "paper/refs.bib")
    missing = []
    if queue is None:
        missing.append("literature/CITATION_QUEUE.json")
    if not refs:
        missing.append("paper/refs.bib")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
