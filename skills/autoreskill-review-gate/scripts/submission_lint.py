#!/usr/bin/env python3
"""Lint final submission-ready package artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


READY = {"ready", "complete", "completed", "pass", "passed", "verified"}


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
    package = read_json(base / "submission_ready.json") or {}
    missing = []
    required = package.get("required_artifacts") if isinstance(package, dict) else None
    if not isinstance(required, list) or not required:
        required = [
            "paper/main.tex",
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
            "reviewer/CITATION_INTEGRITY_REPORT.md",
        ]
    else:
        required = ["paper/main.tex", *[str(rel) for rel in required]]
    for rel in dict.fromkeys(required):
        if not nonempty(base / rel):
            missing.append(rel)
    if not (base / "paper/main.pdf").exists():
        missing.append("paper/main.pdf")
    if str(package.get("status", "")).lower() not in READY:
        missing.append("submission_ready.json status ready")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
