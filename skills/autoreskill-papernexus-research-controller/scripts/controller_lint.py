#!/usr/bin/env python3
"""Lint PaperNexus research_controller artifacts and fallback design review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


READY = {"ready", "pass", "passed", "complete", "completed", "approved"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def resolve_path(base: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == ".autoreskill":
        path = Path(*parts[1:])
    return base / path


def ready(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return str(payload.get("status") or payload.get("verdict") or payload.get("decision") or "").lower() in READY


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    caps = read_json(base / "capabilities.json") or {}
    export = read_json(base / "papernexus/research_controller/controller-export.json")
    sketches = read_json(base / "papernexus/research_controller/solution-sketches.json")
    design = read_json(base / "papernexus/research_controller/design-review.json")
    brief = read_json(base / "papernexus/research_controller/innovation-brief.json")
    packet = read_json(base / "orchestrator/INNOVATION_PACKET.json")
    fallback = read_json(base / "ideation/PANEL_DESIGN_REVIEW.json")
    missing = []
    warnings = []

    if caps.get("research_controller_available") is True:
        if not export:
            missing.append("papernexus/research_controller/controller-export.json")
        if not design:
            missing.append("papernexus/research_controller/design-review.json")
        if design and not ready(design):
            missing.append("research_controller design review status/verdict ready")
        if not brief:
            missing.append("papernexus/research_controller/innovation-brief.json")
        elif not ready(brief):
            missing.append("research_controller innovation brief status ready")
    else:
        if sketches and not design and not fallback:
            missing.append("solution sketches exist but no design review or fallback panel review")
        if not fallback:
            warnings.append("research_controller unavailable and no ideation/PANEL_DESIGN_REVIEW.json fallback")

    if isinstance(packet, dict):
        brief_value = packet.get("controller_innovation_brief_path") or packet.get("controllerInnovationBriefPath") or packet.get("innovation_brief_path")
        if brief_value:
            brief_path = resolve_path(base, brief_value)
            packet_brief = read_json(brief_path) if brief_path else None
            if not packet_brief:
                missing.append("INNOVATION_PACKET.controller_innovation_brief_path target missing")
            elif not ready(packet_brief):
                missing.append("INNOVATION_PACKET.controller_innovation_brief_path status ready")
        design_value = packet.get("controller_design_review_path") or packet.get("controllerDesignReviewPath") or packet.get("design_review_path")
        if design_value:
            design_path = resolve_path(base, design_value)
            packet_design = read_json(design_path) if design_path else None
            if not packet_design:
                missing.append("INNOVATION_PACKET.controller_design_review_path target missing")
            elif not ready(packet_design):
                missing.append("INNOVATION_PACKET.controller_design_review_path status ready")

    out = {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "research_controller_available": caps.get("research_controller_available"),
        "innovation_brief_present": bool(brief),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
