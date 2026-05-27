#!/usr/bin/env python3
"""Create isolated review findings and citation/front-matter reports."""

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


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--mode", choices=["reviewer", "cross-reviewer"], default="reviewer")
    parser.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    base = ar(args.project)
    issues = []
    if not nonempty(base / "paper/main.tex"):
        issues.append({"severity": "high", "status": "open", "message": "missing paper/main.tex"})
    if not nonempty(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md"):
        issues.append({"severity": "high", "status": "open", "message": "missing claim-evidence matrix"})
    if args.ready:
        issues = [{"severity": "medium", "status": "waived", "message": "fixture/demo readiness waiver; do not use for real submission"}]
    findings = {
        "schema_version": 1,
        "created_at": now(),
        "mode": args.mode,
        "status": "ready" if not [i for i in issues if i["severity"] == "high" and i["status"] == "open"] else "needs_repair",
        "issues": issues,
        "scores": {
            "novelty": "requires PaperNexus graph-grounded confirmation",
            "soundness": "requires non-fixture experiment proof",
            "significance": "bounded by evidence strength",
            "clarity": "draft scaffold",
            "reproducibility": "requires code/data availability finalization",
        },
    }
    write_json(base / "reviewer/REVIEW_FINDINGS.json", findings)
    write_text(base / "reviewer/REVIEW_REPORT.md", "# Review Report\n\nSee REVIEW_FINDINGS.json.\n")
    write_text(base / "reviewer/CITATION_INTEGRITY_REPORT.md", "Status: provisional. Resolve CITATION_QUEUE into refs.bib before submission.\n")
    write_text(base / "reviewer/SUBMISSION_READINESS.md", f"Status: {findings['status']}\n")
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "review_pressure", "action": "review_scaffold", "details": {"status": findings["status"], "mode": args.mode}})
    print(json.dumps({"ok": True, "status": findings["status"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
