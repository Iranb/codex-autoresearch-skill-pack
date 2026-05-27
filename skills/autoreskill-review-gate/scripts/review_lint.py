#!/usr/bin/env python3
"""Lint review findings before writing or packaging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


OPEN_STATUSES = {"open", "todo", "unresolved", "active", "needs_fix", "needs-repair"}
BLOCKING_SEVERITIES = {"critical", "high"}
RESOLVED_STATUSES = {"closed", "resolved", "waived", "accepted_risk", "fixed"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def normalize_issues(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["issues", "findings", "review_findings", "items"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def issue_open(issue: dict[str, Any]) -> bool:
    status = str(issue.get("status") or issue.get("state") or "open").lower()
    if status in RESOLVED_STATUSES:
        return False
    if status in OPEN_STATUSES:
        return True
    return status not in RESOLVED_STATUSES


def lint(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {"complete": False, "status": "incomplete", "blocking_issues": [], "missing": ["reviewer/REVIEW_FINDINGS.json"]}

    issues = normalize_issues(payload)
    blocking = []
    for issue in issues:
        severity = str(issue.get("severity") or issue.get("priority") or "").lower()
        if severity in BLOCKING_SEVERITIES and issue_open(issue):
            blocking.append(issue)

    overall = str((payload or {}).get("status", "")).lower() if isinstance(payload, dict) else ""
    complete = not blocking and overall not in {"failed", "blocked", "needs_repair"}
    missing = [] if complete else ["open high/critical review findings"]
    return {
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "blocking_issues": blocking,
        "missing": missing,
        "issue_count": len(issues),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--findings")
    args = parser.parse_args()
    path = Path(args.findings).expanduser() if args.findings else ar(args.project) / "reviewer/REVIEW_FINDINGS.json"
    out = lint(read_json(path))
    out["path"] = str(path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
