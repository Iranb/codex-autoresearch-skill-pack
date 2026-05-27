#!/usr/bin/env python3
"""Convert academic-paper-reviewer output into AutoResearch REVIEW_FINDINGS.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BLOCKING = {"critical", "high"}
RESOLVED = {"closed", "resolved", "waived", "accepted_risk", "fixed"}
SELF_TEST_MARKDOWN = """# Editorial Decision Package

## Reviewer Information
### Reviewer Role
Devil's Advocate

## Weaknesses
### W1: Missing fair baseline
**Problem**: The paper compares against a weak baseline.
**Suggestion**: Add a fair literature baseline.
**Severity**: Critical

### W2: Minor writing issue
**Problem**: The abstract is verbose.
**Severity**: Minor
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


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


def read_input(path: Path) -> tuple[str, Any | None]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        return text, json.loads(text)
    except json.JSONDecodeError:
        return text, None


def severity(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"critical", "blocker", "fatal"}:
        return "critical"
    if raw in {"major", "high", "serious"}:
        return "high"
    if raw in {"minor", "medium", "moderate"}:
        return "medium"
    if raw in {"low", "editorial", "style"}:
        return "low"
    return "medium"


def issue_status(value: Any, mode: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in RESOLVED:
        return raw
    if mode == "re-review" and raw in {"addressed", "repaired"}:
        return "resolved"
    return "open"


def recommendation_from_text(text: str) -> str | None:
    match = re.search(r"(?:Recommendation|Decision)\s*[:：]\s*(.+)", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def clean_markdown(value: str) -> str:
    return re.sub(r"[*_`>#-]+", " ", value).strip()


def extract_markdown_issues(text: str, mode: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    issues: list[dict[str, Any]] = []
    reviewer = "academic-paper-reviewer"
    current_title = ""
    block: list[str] = []

    def flush_with_severity(raw_severity: str, line_no: int) -> None:
        sev = severity(raw_severity)
        body = "\n".join(block[-8:]).strip()
        message = clean_markdown(current_title or body.splitlines()[0] if body else f"{sev} review issue")
        evidence = clean_markdown(body)
        issues.append(
            {
                "id": f"APR-{len(issues) + 1:03d}",
                "severity": sev,
                "status": issue_status(None, mode),
                "source_reviewer": reviewer,
                "message": message,
                "evidence": evidence,
                "recommendation": recommendation_from_text(body),
                "source_span": {"line": line_no, "heading": current_title},
                "blocks_submission": sev in BLOCKING,
            }
        )

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        plain = re.sub(r"[*_`]", "", stripped)
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            title = heading.group(2).strip()
            if "reviewer role" in title.lower():
                reviewer = "academic-paper-reviewer"
            elif any(token in title.lower() for token in ["reviewer", "eic", "devil", "editor"]):
                reviewer = clean_markdown(title)
            if re.match(r"W\d+[:. ]", title, flags=re.IGNORECASE) or any(token in title.lower() for token in ["weakness", "issue", "concern"]):
                current_title = title
                block = [stripped]
            else:
                block.append(stripped)
            continue

        role_match = re.search(r"(?:Reviewer Role|Role)\s*[:：]\s*(.+)", plain, flags=re.IGNORECASE)
        if role_match:
            reviewer = clean_markdown(role_match.group(1))
        block.append(stripped)
        sev_match = re.search(r"Severity\s*[:：]\s*(Critical|Major|Minor|High|Medium|Low)", plain, flags=re.IGNORECASE)
        if sev_match:
            flush_with_severity(sev_match.group(1), idx)
            block = []
            current_title = ""
    return issues


def walk(value: Any) -> list[Any]:
    out = [value]
    if isinstance(value, dict):
        for item in value.values():
            out.extend(walk(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(walk(item))
    return out


def extract_json_issues(payload: Any, mode: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in walk(payload):
        if not isinstance(item, dict):
            continue
        if not any(key in item for key in ["severity", "priority", "problem", "message", "weakness", "suggestion"]):
            continue
        sev = severity(item.get("severity") or item.get("priority"))
        message = str(item.get("message") or item.get("problem") or item.get("weakness") or item.get("title") or "review issue").strip()
        issues.append(
            {
                "id": f"APR-{len(issues) + 1:03d}",
                "severity": sev,
                "status": issue_status(item.get("status") or item.get("state"), mode),
                "source_reviewer": str(item.get("reviewer") or item.get("source_reviewer") or item.get("role") or "academic-paper-reviewer"),
                "message": message,
                "evidence": str(item.get("evidence") or item.get("why_it_matters") or item.get("why") or ""),
                "recommendation": item.get("recommendation") or item.get("suggestion"),
                "source_span": item.get("source_span") or {},
                "blocks_submission": sev in BLOCKING,
            }
        )
    return issues


def build_findings(project: str, text: str, payload: Any | None, mode: str, source_name: str, source_hash: str) -> dict[str, Any]:
    issues = extract_json_issues(payload, mode) if payload is not None else extract_markdown_issues(text, mode)
    blocking = [issue for issue in issues if issue["severity"] in BLOCKING and str(issue["status"]).lower() not in RESOLVED]
    return {
        "schema_version": 1,
        "created_at": now(),
        "status": "needs_repair" if blocking else "ready",
        "source_adapter": "academic-paper-reviewer",
        "mode": mode,
        "source_input": source_name,
        "source_input_hash": source_hash,
        "reviewer_count": len({issue["source_reviewer"] for issue in issues}),
        "decision": recommendation_from_text(text),
        "issues": issues,
        "blocking_issue_count": len(blocking),
    }


def adapt(project: str, input_path: Path | None, output_path: Path | None, mode: str, dry_run: bool, self_test: bool) -> dict[str, Any]:
    base = ar(project)
    if self_test:
        text = SELF_TEST_MARKDOWN
        payload = None
        source_name = "self-test"
    elif input_path is not None:
        text, payload = read_input(input_path)
        source_name = str(input_path)
    else:
        raise SystemExit("--input is required unless --self-test is used")

    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    findings = build_findings(project, text, payload, mode, source_name, source_hash)
    if not dry_run:
        raw_dir = base / "reviewer/academic-paper-reviewer/raw"
        raw_path = raw_dir / f"{source_hash}.md"
        write_text(raw_path, text)
        out = output_path or base / "reviewer/REVIEW_FINDINGS.json"
        write_json(out, findings)
        append_jsonl(
            base / "decision_log.jsonl",
            {
                "ts": now(),
                "stage": "review_pressure",
                "action": "academic_review_adapter",
                "details": {"output": str(out), "source_hash": source_hash, "status": findings["status"]},
            },
        )
        findings["output_path"] = str(out)
        findings["raw_input_path"] = str(raw_path)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--mode", default="full", choices=["full", "quick", "methodology-focus", "re-review", "calibration"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    base = ar(args.project)
    input_path = Path(args.input).expanduser() if args.input else None
    output_path = Path(args.output).expanduser() if args.output else None
    if output_path and not output_path.is_absolute():
        output_path = base / output_path
    out = adapt(args.project, input_path, output_path, args.mode, args.dry_run, args.self_test)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
