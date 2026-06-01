#!/usr/bin/env python3
"""Lint analysis artifacts before paper writing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def lint(project: str, strict: bool) -> dict[str, object]:
    base = ar(project)
    missing: list[str] = []
    warnings: list[str] = []

    for rel in ["analyzer/CLAIM_EVIDENCE_MATRIX.md", "analyzer/TRACK_VERDICTS.md"]:
        if not nonempty(base / rel):
            missing.append(rel)

    if not (nonempty(base / "coder/EXPERIMENT_LEDGER.json") or nonempty(base / "coder/EXPERIMENT_INDEX.md")):
        missing.append("coder/EXPERIMENT_LEDGER.json or coder/EXPERIMENT_INDEX.md")
    ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json")
    if ledger and not ledger.get("best_run"):
        warnings.append("coder/EXPERIMENT_LEDGER.json has no promoted best_run; analysis must stay pilot-only")
    if ledger and ledger.get("candidate_runs") and not ledger.get("track_best_runs"):
        warnings.append("candidate_supported runs require ablation/confirmation before strong improvement claims")
    if ledger and ledger.get("ready_for_analysis") is True:
        selection = read_json(base / "analyzer/BEST_RUN_SELECTION.json")
        score = read_json(base / "analyzer/SCORE_VERIFICATION.json")
        spec = read_json(base / "analyzer/SPEC_VIOLATION_AUDIT.json")
        if selection.get("final_promotion_status") != "promoted" or not selection.get("selected_run_id"):
            missing.append("analyzer/BEST_RUN_SELECTION.json final_promotion_status=promoted selected_run_id")
        if score.get("status") != "passed":
            missing.append("analyzer/SCORE_VERIFICATION.json status=passed")
        if spec.get("status") != "passed":
            missing.append("analyzer/SPEC_VIOLATION_AUDIT.json status=passed")
    elif ledger:
        warnings.append("no promoted evidence; write pilot-only findings or return to experiment")

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
