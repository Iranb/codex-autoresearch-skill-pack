#!/usr/bin/env python3
"""Lint final submission-ready package artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
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


def pdf_page_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        proc = subprocess.run(
            ["pdfinfo", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def validate_page_policy(base: Path, package: dict[str, Any], missing: list[str], warnings: list[str]) -> dict[str, Any] | None:
    policy = package.get("venue_page_policy")
    if not isinstance(policy, dict):
        return None
    pdf_path = base / "paper/main.pdf"
    pages = pdf_page_count(pdf_path)
    if pages is None:
        missing.append("paper/main.pdf page_count unavailable")
        return {"status": "failed", "pages": None, "policy": policy}

    min_pages = policy.get("min_pages")
    max_pages = policy.get("max_pages")
    target_pages = policy.get("target_main_pages")
    status = "passed"
    if isinstance(min_pages, int) and pages < min_pages:
        missing.append(f"paper/main.pdf page_count {pages} below venue_page_policy.min_pages {min_pages}")
        status = "failed"
    if isinstance(max_pages, int) and pages > max_pages:
        missing.append(f"paper/main.pdf page_count {pages} above venue_page_policy.max_pages {max_pages}")
        status = "failed"
    if isinstance(target_pages, int) and pages != target_pages:
        warnings.append(f"paper/main.pdf page_count {pages} differs from venue_page_policy.target_main_pages {target_pages}")
    return {"status": status, "pages": pages, "policy": policy}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    package = read_json(base / "submission_ready.json") or {}
    missing = []
    warnings = []
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
    page_policy = validate_page_policy(base, package, missing, warnings) if isinstance(package, dict) else None
    out = {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
    }
    if warnings:
        out["warnings"] = warnings
    if page_policy is not None:
        out["page_policy"] = page_policy
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
