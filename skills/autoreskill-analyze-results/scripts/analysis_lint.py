#!/usr/bin/env python3
"""Lint analysis artifacts before paper writing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def lint(project: str, strict: bool) -> dict[str, object]:
    base = ar(project)
    missing: list[str] = []
    warnings: list[str] = []

    for rel in ["analyzer/CLAIM_EVIDENCE_MATRIX.md", "analyzer/TRACK_VERDICTS.md"]:
        if not nonempty(base / rel):
            missing.append(rel)

    if not (nonempty(base / "coder/EXPERIMENT_LEDGER.json") or nonempty(base / "coder/EXPERIMENT_INDEX.md")):
        missing.append("coder/EXPERIMENT_LEDGER.json or coder/EXPERIMENT_INDEX.md")

    if not nonempty(base / "analyzer/UNSUPPORTED_CLAIMS.md"):
        target = missing if strict else warnings
        target.append("analyzer/UNSUPPORTED_CLAIMS.md")

    if not (nonempty(base / "analyzer/NARRATIVE_REPORT.md") or nonempty(base / "analyzer/ANALYSIS_REPORT.md")):
        target = missing if strict else warnings
        target.append("analyzer/NARRATIVE_REPORT.md or analyzer/ANALYSIS_REPORT.md")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.strict)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
