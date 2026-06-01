#!/usr/bin/env python3
"""Lint user-facing innovation storyline documents."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STORY_ROOT = Path("user_view/innovation_story")

FILES = {
    "00_STORYLINE_DESIGN.md": {
        "min_words": 180,
        "headings": [
            "Paper Thesis",
            "Reader Belief Shift",
            "Opening Tension",
            "Hidden Cause",
            "Method As Resolution",
            "Novelty Positioning",
            "Proof Ladder",
            "Figure Story",
            "Reviewer Risk And Defense",
            "Final Narrative Spine",
        ],
    },
    "01_METHOD_INNOVATION_STORY.md": {
        "min_words": 160,
        "headings": [
            "Core Problem Tension",
            "Where The Method Comes From",
            "Method Idea In One Sentence",
            "Mechanism Construction",
            "What Is Actually New",
            "Evidence Chain",
            "Experiment Implications",
            "Current User-Facing Summary",
        ],
    },
    "02_CLAIM_EVIDENCE_MAP.md": {
        "min_words": 120,
        "headings": [
            "Main Claims",
            "Evidence Support",
            "Claim Limits",
            "Experiment Mapping",
            "Revision Notes",
        ],
    },
}

REQUIRED_BY_STAGE = {
    "ideation": ["00_STORYLINE_DESIGN.md"],
    "idea_gate": ["00_STORYLINE_DESIGN.md"],
    "experiment_plan": ["00_STORYLINE_DESIGN.md", "01_METHOD_INNOVATION_STORY.md", "02_CLAIM_EVIDENCE_MAP.md"],
    "analysis": ["00_STORYLINE_DESIGN.md", "01_METHOD_INNOVATION_STORY.md", "02_CLAIM_EVIDENCE_MAP.md"],
    "review_pressure": ["00_STORYLINE_DESIGN.md", "01_METHOD_INNOVATION_STORY.md", "02_CLAIM_EVIDENCE_MAP.md"],
    "writing": ["00_STORYLINE_DESIGN.md", "01_METHOD_INNOVATION_STORY.md", "02_CLAIM_EVIDENCE_MAP.md"],
    "submission_ready": ["00_STORYLINE_DESIGN.md", "01_METHOD_INNOVATION_STORY.md", "02_CLAIM_EVIDENCE_MAP.md"],
}

PLACEHOLDER_RE = re.compile(r"(?:\b(?:TBD|TODO|FIXME|placeholder|to be filled)\b|待补|待定|占位)", re.IGNORECASE)
METHOD_SOURCE_RE = re.compile(r"(near[-_ ]?neighbor|far[-_ ]?neighbor|cross[-_ ]?lane|transfer|近邻|远邻|邻域|迁移|跨域|跨领域)", re.IGNORECASE)
ANALYSIS_EVIDENCE_RE = re.compile(r"(CLAIM_EVIDENCE_MATRIX|TRACK_VERDICTS|promoted|downgrade|unsupported|实验证据|主张|证据|降级|支持)", re.IGNORECASE)


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)


def normalize_heading(line: str) -> str:
    return re.sub(r"\s+", " ", line.lstrip("#").strip()).strip()


def has_heading(text: str, heading: str) -> bool:
    for line in text.splitlines():
        if not line.lstrip().startswith("#"):
            continue
        if normalize_heading(line).lower() == heading.lower():
            return True
    return False


def section_has_body(text: str, heading: str) -> bool:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#") and normalize_heading(line).lower() == heading.lower():
            start = index + 1
            break
    if start is None:
        return False
    body: list[str] = []
    for line in lines[start:]:
        if line.lstrip().startswith("#"):
            break
        stripped = line.strip()
        if stripped and not stripped.startswith(("```", "---")):
            body.append(stripped)
    return len(" ".join(body)) >= 40 or len(body) >= 2


def prose_ratio(text: str) -> tuple[int, int, float]:
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    bullet_lines = [
        line
        for line in lines
        if line.startswith(("-", "*", "+")) or re.match(r"^\d+[\.)]\s+", line)
    ]
    ratio = len(bullet_lines) / len(lines) if lines else 0.0
    return len(lines), len(bullet_lines), ratio


def lint_file(base: Path, rel: str, stage: str) -> tuple[list[str], list[str], dict[str, Any]]:
    path = base / STORY_ROOT / rel
    missing: list[str] = []
    warnings: list[str] = []
    detail: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    spec = FILES[rel]
    if not path.exists() or not path.is_file():
        return [str(STORY_ROOT / rel)], warnings, detail
    text = path.read_text(encoding="utf-8", errors="ignore")
    word_count = len(words(text))
    line_count, bullet_count, bullet_ratio = prose_ratio(text)
    detail.update({"word_count": word_count, "line_count": line_count, "bullet_lines": bullet_count, "bullet_ratio": round(bullet_ratio, 3)})
    if word_count < int(spec["min_words"]):
        missing.append(f"{STORY_ROOT / rel} has too little narrative prose ({word_count} words/chars)")
    if PLACEHOLDER_RE.search(text):
        missing.append(f"{STORY_ROOT / rel} contains placeholder text")
    if line_count >= 8 and bullet_ratio > 0.55:
        missing.append(f"{STORY_ROOT / rel} is bullet-dominant; write a storyline, not a list")
    for heading in spec["headings"]:
        if not has_heading(text, str(heading)):
            missing.append(f"{STORY_ROOT / rel} missing section: {heading}")
        elif not section_has_body(text, str(heading)):
            missing.append(f"{STORY_ROOT / rel} section lacks narrative body: {heading}")
    if rel in {"00_STORYLINE_DESIGN.md", "01_METHOD_INNOVATION_STORY.md"} and not METHOD_SOURCE_RE.search(text):
        missing.append(f"{STORY_ROOT / rel} must explain near/far-neighbor, cross-lane, or transfer method source")
    if stage in {"analysis", "review_pressure", "writing", "submission_ready"} and rel == "02_CLAIM_EVIDENCE_MAP.md":
        if not ANALYSIS_EVIDENCE_RE.search(text):
            missing.append(f"{STORY_ROOT / rel} must connect claims to analysis evidence or downgraded claims")
    if rel == "00_STORYLINE_DESIGN.md" and "Final Narrative Spine" in text and len(re.findall(r"^\s*\d+[\.)]\s+", text, flags=re.MULTILINE)) < 3:
        warnings.append(f"{STORY_ROOT / rel} Final Narrative Spine should compress the paper into 5-7 sequential sentences")
    return missing, warnings, detail


def lint(project: str, stage: str) -> dict[str, Any]:
    base = ar(project)
    required = REQUIRED_BY_STAGE.get(stage, ["00_STORYLINE_DESIGN.md", "01_METHOD_INNOVATION_STORY.md", "02_CLAIM_EVIDENCE_MAP.md"])
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"root": str(base / STORY_ROOT), "required_files": required, "files": {}}
    if not (base / STORY_ROOT).exists():
        missing.append(str(STORY_ROOT) + "/")
    for rel in required:
        file_missing, file_warnings, detail = lint_file(base, rel, stage)
        missing.extend(file_missing)
        warnings.extend(file_warnings)
        details["files"][rel] = detail
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "stage": stage,
        "missing": missing,
        "warnings": warnings,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", default="experiment_plan")
    args = parser.parse_args()
    out = lint(args.project, args.stage)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
