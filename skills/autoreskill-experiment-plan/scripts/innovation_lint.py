#!/usr/bin/env python3
"""Lint INNOVATION_PACKET experiment-plan authority."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[2]
PAPERNEXUS_SCRIPTS = SKILL_ROOT / "autoreskill-papernexus-innovation/scripts"
if str(PAPERNEXUS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PAPERNEXUS_SCRIPTS))

from idea_support_lint import lint_idea_support, resolve_artifact_path  # noqa: E402


REQUIRED = ["selected_idea_fragment_id", "baseline", "primary_metric", "fixed_budget"]
ONE_VARIABLE_KEYS = ["one_variable_change", "oneVariableChange", "method_delta", "methodDelta", "intervention", "variable_change"]
FALSIFIER_KEYS = ["falsifier", "falsifiers", "failure_condition", "failure_conditions", "failureCondition", "stop_condition"]
DATASET_KEYS = ["dataset_or_benchmark", "datasetOrBenchmark", "dataset", "datasets", "benchmark", "benchmarks"]
READY = {"ready", "complete", "completed", "pass", "passed", "approved", "verified"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if present(mapping.get(key)):
            return mapping[key]
    return None


def relpath(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def resolve_path(base: Path, value: Any) -> Path | None:
    return resolve_artifact_path(base, value)


def boundary_summary(packet: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    boundaries = packet.get("evidence_boundaries") or packet.get("evidenceBoundaries")
    missing: list[str] = []
    summary: dict[str, int] = {}
    if not isinstance(boundaries, dict):
        return summary, ["INNOVATION_PACKET.evidence_boundaries"]
    for key in ["source_backed", "agent_inferred", "speculative", "unsupported"]:
        value = boundaries.get(key) or boundaries.get(key.replace("_", "-")) or boundaries.get(key.replace("_", " "))
        if not present(value):
            missing.append(f"INNOVATION_PACKET.evidence_boundaries.{key}")
            summary[key] = 0
        elif isinstance(value, list):
            summary[key] = len(value)
        elif isinstance(value, dict):
            summary[key] = len(value)
        else:
            summary[key] = 1
    return summary, missing


def design_review_ready(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or payload.get("verdict") or payload.get("decision") or "").lower()
    return status in READY


def find_design_review(base: Path, packet: dict[str, Any]) -> tuple[Path | None, Any, bool]:
    explicit = first_present(packet, ["controller_design_review_path", "controllerDesignReviewPath", "design_review_path", "designReviewPath"])
    candidates: list[Path] = []
    if explicit:
        path = resolve_path(base, explicit)
        if path:
            candidates.append(path)
    candidates.extend(
        [
            base / "papernexus/research_controller/design-review.json",
            base / "ideation/PANEL_DESIGN_REVIEW.json",
        ]
    )
    for path in candidates:
        payload = read_json(path)
        if payload is not None:
            return path, payload, design_review_ready(payload)
    return None, None, False


def lint_packet(project: str, packet_path: Path | None = None) -> dict[str, Any]:
    base = ar(project)
    path = packet_path or base / "orchestrator/INNOVATION_PACKET.json"
    packet = read_json(path)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    if not isinstance(packet, dict):
        missing.append(relpath(base, path))
        return {"complete": False, "status": "incomplete", "missing": missing, "warnings": warnings, "path": str(path)}

    for key in REQUIRED:
        if not present(packet.get(key)):
            missing.append(f"INNOVATION_PACKET.{key}")
    if not present(packet.get("supporting_idea_fragment_ids")) and not present(packet.get("supportingIdeaFragmentIds")):
        missing.append("INNOVATION_PACKET.supporting_idea_fragment_ids")
    if not present(first_present(packet, ONE_VARIABLE_KEYS)):
        missing.append("INNOVATION_PACKET.one_variable_change")
    if not present(first_present(packet, FALSIFIER_KEYS)):
        missing.append("INNOVATION_PACKET.falsifier or failure_condition")
    if not present(first_present(packet, DATASET_KEYS)):
        missing.append("INNOVATION_PACKET.dataset_or_benchmark")

    summary, boundary_missing = boundary_summary(packet)
    missing.extend(boundary_missing)
    details["evidence_boundary_summary"] = summary

    idea_support = lint_idea_support(project, path)
    details["idea_support"] = idea_support
    missing.extend(f"idea_support: {item}" for item in idea_support.get("missing", []))
    warnings.extend(f"idea_support: {item}" for item in idea_support.get("warnings", []))

    caps = read_json(base / "capabilities.json") or {}
    controller_available = caps.get("research_controller_available") is True
    brief_value = first_present(packet, ["controller_innovation_brief_path", "controllerInnovationBriefPath", "innovation_brief_path"])
    brief_path = resolve_path(base, brief_value) if brief_value else None
    if controller_available and not brief_path:
        missing.append("INNOVATION_PACKET.controller_innovation_brief_path")
    if brief_path:
        brief = read_json(brief_path)
        if brief is None:
            missing.append(f"controller_innovation_brief_path target missing: {relpath(base, brief_path)}")
        elif str(brief.get("status", "")).lower() not in READY:
            missing.append("controller innovation brief status ready")
        details["controller_innovation_brief_path"] = relpath(base, brief_path)
    elif not controller_available:
        warnings.append("research_controller unavailable or unrecorded; controller innovation brief not required")

    design_path, design_payload, design_ready = find_design_review(base, packet)
    if design_payload is None:
        missing.append("controller design review or fallback panel review")
    elif not design_ready:
        missing.append("controller design review status/verdict ready")
    details["design_review_path"] = relpath(base, design_path) if design_path else None

    evidence = first_present(packet, ["evidence_paths", "evidencePaths", "supporting_papers", "supportingPapers"])
    if not present(evidence):
        missing.append("INNOVATION_PACKET.evidence_paths or supporting_papers")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(path),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--packet")
    args = parser.parse_args()
    base = ar(args.project)
    path = resolve_artifact_path(base, args.packet) if args.packet else None
    out = lint_packet(args.project, path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
