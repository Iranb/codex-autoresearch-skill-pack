#!/usr/bin/env python3
"""Lint writer package for evidence-bound drafting."""

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
    missing = []
    if not nonempty(base / "paper/main.tex"):
        missing.append("paper/main.tex")
    package = read_json(base / "paper/write_package.json")
    if not package:
        missing.append("paper/write_package.json")
    if not nonempty(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md"):
        missing.append("analyzer/CLAIM_EVIDENCE_MATRIX.md")
    representation = read_json(base / "paper/RESEARCH_REPRESENTATION.json")
    if not representation:
        missing.append("paper/RESEARCH_REPRESENTATION.json")
    if not nonempty(base / "paper/RESEARCH_REPRESENTATION.md"):
        missing.append("paper/RESEARCH_REPRESENTATION.md")
    grounded = read_json(base / "paper/GROUNDED_WRITE_PACKAGE.json")
    if not grounded:
        missing.append("paper/GROUNDED_WRITE_PACKAGE.json")
    elif grounded.get("ground_status") != "passed":
        missing.append("paper/GROUNDED_WRITE_PACKAGE.json ground_status=passed")
    verifier = read_json(base / "paper/PAPER_CLAIM_VERIFICATION.json")
    if not verifier:
        missing.append("paper/PAPER_CLAIM_VERIFICATION.json")
    elif verifier.get("status") != "passed":
        missing.append("paper/PAPER_CLAIM_VERIFICATION.json status=passed")
    best = read_json(base / "analyzer/BEST_RUN_SELECTION.json")
    score = read_json(base / "analyzer/SCORE_VERIFICATION.json")
    if representation and isinstance(representation.get("performance_claims"), list) and representation["performance_claims"]:
        if not best or best.get("final_promotion_status") != "promoted":
            missing.append("performance claims require analyzer/BEST_RUN_SELECTION.json final_promotion_status=promoted")
        if not score or score.get("status") != "passed":
            missing.append("performance claims require analyzer/SCORE_VERIFICATION.json status=passed")
    warnings = []
    if verifier and verifier.get("warnings"):
        warnings.append("paper/PAPER_CLAIM_VERIFICATION.json has non-blocking warnings")
    out = {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "warnings": warnings}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
