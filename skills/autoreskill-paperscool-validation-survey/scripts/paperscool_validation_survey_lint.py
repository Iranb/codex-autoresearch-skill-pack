#!/usr/bin/env python3
"""Lint papers.cool validation survey artifacts for AutoResearch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DIRECT = "direct_field"
NEAR = "near_neighbor"
FAR = "far_neighbor"
BLOCKED = "blocked"
OUT_OF_SCOPE = "out_of_scope"
ALLOWED_FIELD_DISTANCES = {DIRECT, NEAR, FAR, BLOCKED, OUT_OF_SCOPE, "unknown", "needs_review"}
INNOVATION_ROLES = {"innovation_source", "diagnostic_source"}
NON_INNOVATION_DIRECT_ROLES = {"baseline_anchor", "novelty_risk", "related_work", "excluded"}
HEAVY_FLAGS = {"requires_large_model", "requires_diffusion_or_generation"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def read_json(path: Path, base: Path, missing: list[str]) -> Any:
    label = rel(base, path)
    if not path.exists():
        missing.append(label)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        missing.append(f"{label} invalid JSON at line {exc.lineno} column {exc.colno}")
        return None


def read_jsonl_count(path: Path, base: Path, missing: list[str], warnings: list[str]) -> int:
    label = rel(base, path)
    if not path.exists():
        missing.append(label)
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                missing.append(f"{label} invalid JSONL at line {lineno}: {exc.msg}")
                break
            count += 1
    if count == 0:
        warnings.append(f"{label} has zero records")
    return count


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def norm(value: Any) -> str:
    return str(value or "").strip().lower()


def rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def row_id(row: dict[str, Any], fallback: str) -> str:
    return str(row.get("paper_id") or row.get("source_paper_id") or row.get("id") or row.get("idea_id") or fallback)


def has_no_viable_reason(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("no_viable_candidate_reason", "no_viable_candidates_reason", "empty_reason", "survey_decision"):
        if present(payload.get(key)):
            return True
    return False


def lint_policy(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "survey/FIELD_DISTANCE_POLICY.json"
    policy = read_json(path, base, missing)
    if policy is None:
        return
    if not isinstance(policy, dict):
        missing.append("survey/FIELD_DISTANCE_POLICY.json must be a JSON object")
        return
    details["policy_path"] = rel(base, path)
    for field in ["target_task", "direct_field", "near_neighbor", "far_neighbor", "blocked"]:
        if not present(policy.get(field)):
            missing.append(f"survey/FIELD_DISTANCE_POLICY.json {field}")
    if not present(policy.get("usage_rules")):
        warnings.append("survey/FIELD_DISTANCE_POLICY.json should include usage_rules")


def lint_plan(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "survey/PAPER_CODE_SURVEY_PLAN.json"
    plan = read_json(path, base, missing)
    if plan is None:
        return
    if not isinstance(plan, dict):
        missing.append("survey/PAPER_CODE_SURVEY_PLAN.json must be a JSON object")
        return
    details["plan_path"] = rel(base, path)
    for field in ["target_task", "source_lanes", "exclusion_rules", "audit_policy"]:
        if not present(plan.get(field)):
            missing.append(f"survey/PAPER_CODE_SURVEY_PLAN.json {field}")
    if not (present(plan.get("venue_scope")) or present(plan.get("source_scope"))):
        missing.append("survey/PAPER_CODE_SURVEY_PLAN.json venue_scope or source_scope")
    if not (present(plan.get("year_range")) or present(plan.get("date_scope"))):
        warnings.append("survey/PAPER_CODE_SURVEY_PLAN.json should record year_range or date_scope")


def lint_screening(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> dict[str, dict[str, Any]]:
    path = base / "survey/TOPIC_SCREENING_LEDGER.json"
    payload = read_json(path, base, missing)
    by_paper: dict[str, dict[str, Any]] = {}
    if payload is None:
        details["screening_count"] = 0
        return by_paper
    screen_rows = rows(payload, ("papers", "screened", "rows", "candidates"))
    details["screening_count"] = len(screen_rows)
    if not screen_rows:
        missing.append("survey/TOPIC_SCREENING_LEDGER.json papers[] or screened[] or rows[]")
        return by_paper
    counts: dict[str, int] = {}
    for index, row in enumerate(screen_rows):
        prefix = f"survey/TOPIC_SCREENING_LEDGER.json rows[{index}]"
        paper_id = row_id(row, str(index))
        by_paper[paper_id] = row
        field_distance = norm(row.get("field_distance"))
        usage_role = norm(row.get("usage_role"))
        counts[field_distance or "missing"] = counts.get(field_distance or "missing", 0) + 1
        for field in ["paper_id", "title", "field_distance", "usage_role", "decision"]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if field_distance and field_distance not in ALLOWED_FIELD_DISTANCES:
            warnings.append(f"{prefix}.field_distance has nonstandard value: {field_distance}")
        if field_distance == DIRECT and usage_role in INNOVATION_ROLES and not present(row.get("override_reason")):
            missing.append(f"{prefix} direct_field cannot be {usage_role} without override_reason")
        if field_distance == DIRECT and usage_role and usage_role not in NON_INNOVATION_DIRECT_ROLES and not present(row.get("override_reason")):
            warnings.append(f"{prefix} direct_field should route to baseline/novelty/related/excluded")
        if field_distance == BLOCKED and usage_role != "excluded" and not present(row.get("override_reason")):
            missing.append(f"{prefix} blocked paper must be excluded unless override_reason is set")
    details["field_distance_counts"] = counts
    return by_paper


def lint_exclusion(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "survey/EXCLUSION_AUDIT.json"
    payload = read_json(path, base, missing)
    if payload is None:
        return
    if not isinstance(payload, dict):
        missing.append("survey/EXCLUSION_AUDIT.json must be a JSON object")
        return
    if not (present(payload.get("summary")) or present(payload.get("counts_by_reason"))):
        missing.append("survey/EXCLUSION_AUDIT.json summary or counts_by_reason")
    excluded_rows = rows(payload, ("excluded", "examples", "rows"))
    details["exclusion_example_count"] = len(excluded_rows)
    if not excluded_rows:
        warnings.append("survey/EXCLUSION_AUDIT.json should include excluded/examples rows")


def lint_candidates(base: Path, screening: dict[str, dict[str, Any]], missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "survey/PAPER_CODE_CANDIDATES.json"
    payload = read_json(path, base, missing)
    if payload is None:
        details["candidate_count"] = 0
        return set()
    candidate_rows = rows(payload, ("candidates", "papers", "rows"))
    details["candidate_count"] = len(candidate_rows)
    if not candidate_rows:
        if not has_no_viable_reason(payload):
            warnings.append("survey/PAPER_CODE_CANDIDATES.json has no candidates and no no_viable_candidate_reason")
        return set()
    candidate_ids: set[str] = set()
    for index, row in enumerate(candidate_rows):
        prefix = f"survey/PAPER_CODE_CANDIDATES.json candidates[{index}]"
        paper_id = row_id(row, str(index))
        candidate_ids.add(paper_id)
        field_distance = norm(row.get("field_distance") or screening.get(paper_id, {}).get("field_distance"))
        usage_role = norm(row.get("usage_role") or screening.get(paper_id, {}).get("usage_role"))
        for field in ["paper_id", "title", "field_distance", "source_lane", "usage_role", "decision"]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if not (present(row.get("code_url")) or present(row.get("repo_url")) or present(row.get("code_status"))):
            warnings.append(f"{prefix} should record code_url/repo_url or explicit code_status")
        if field_distance == DIRECT and usage_role in INNOVATION_ROLES and not present(row.get("override_reason")):
            missing.append(f"{prefix} direct_field cannot be an innovation candidate without override_reason")
        if field_distance == BLOCKED and not present(row.get("override_reason")):
            missing.append(f"{prefix} blocked paper cannot be a code candidate without override_reason")
    return candidate_ids


def lint_repo_evidence(base: Path, candidate_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "survey/REPO_STATIC_EVIDENCE.json"
    payload = read_json(path, base, missing)
    if payload is None:
        details["repo_evidence_count"] = 0
        return set()
    repo_rows = rows(payload, ("repositories", "repos", "rows"))
    details["repo_evidence_count"] = len(repo_rows)
    if not repo_rows:
        if not has_no_viable_reason(payload):
            warnings.append("survey/REPO_STATIC_EVIDENCE.json has no repositories and no no_viable_candidate_reason")
        return set()
    valid_source_ids: set[str] = set()
    for index, row in enumerate(repo_rows):
        prefix = f"survey/REPO_STATIC_EVIDENCE.json repositories[{index}]"
        paper_id = str(row.get("paper_id") or row.get("source_paper_id") or "")
        if not present(paper_id):
            missing.append(f"{prefix}.paper_id")
        elif candidate_ids and paper_id not in candidate_ids:
            warnings.append(f"{prefix}.paper_id not found in PAPER_CODE_CANDIDATES.json: {paper_id}")
        if not (present(row.get("repo_url")) or present(row.get("repo_ref")) or present(row.get("repository_url"))):
            missing.append(f"{prefix}.repo_url or repo_ref")
        for field in ["repo_status", "code_available", "paper_code_match", "static_evidence", "validity_decision"]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        evidence = row.get("static_evidence")
        if isinstance(evidence, dict):
            for field in ["entrypoints", "configs", "metrics"]:
                if not present(evidence.get(field)):
                    warnings.append(f"{prefix}.static_evidence.{field}")
        status = norm(row.get("repo_status") or row.get("validity_decision"))
        if status in {"valid", "usable", "reviewed_valid", "implementation_valid", "source_read"}:
            if paper_id:
                valid_source_ids.add(paper_id)
            for ref_field in ("repo_url", "repo_ref", "repository_url", "repo_id"):
                if present(row.get(ref_field)):
                    valid_source_ids.add(str(row.get(ref_field)))
    return valid_source_ids


def lint_mechanisms(base: Path, screening: dict[str, dict[str, Any]], valid_sources: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "survey/CODE_MECHANISM_MAP.json"
    payload = read_json(path, base, missing)
    if payload is None:
        details["mechanism_count"] = 0
        return set()
    mech_rows = rows(payload, ("mechanisms", "rows"))
    details["mechanism_count"] = len(mech_rows)
    if not mech_rows:
        if not has_no_viable_reason(payload):
            warnings.append("survey/CODE_MECHANISM_MAP.json has no mechanisms and no no_viable_candidate_reason")
        return set()
    mechanism_ids: set[str] = set()
    for index, row in enumerate(mech_rows):
        prefix = f"survey/CODE_MECHANISM_MAP.json mechanisms[{index}]"
        mech_id = str(row.get("mechanism_id") or row.get("id") or f"mechanism-{index}")
        mechanism_ids.add(mech_id)
        paper_id = str(row.get("source_paper_id") or row.get("paper_id") or "")
        field_distance = norm(row.get("field_distance") or screening.get(paper_id, {}).get("field_distance"))
        for field in ["mechanism_id", "source_paper_id", "source_repo_ref", "mechanism_summary", "active_path_evidence", "target_pressure", "evidence_boundary"]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if field_distance == DIRECT and not present(row.get("override_reason")):
            missing.append(f"{prefix} direct_field mechanism cannot enter CODE_MECHANISM_MAP without override_reason")
        if field_distance == BLOCKED and not present(row.get("override_reason")):
            missing.append(f"{prefix} blocked mechanism cannot enter CODE_MECHANISM_MAP without override_reason")
        source_ref = str(row.get("source_repo_ref") or row.get("repo_url") or row.get("source_paper_id") or "")
        if valid_sources and source_ref not in valid_sources and paper_id not in valid_sources:
            warnings.append(f"{prefix} source_repo_ref/source_paper_id not found in valid repo evidence")
    return mechanism_ids


def lint_migrations(base: Path, screening: dict[str, dict[str, Any]], mechanism_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "ideation/INNOVATION_MIGRATION_MATRIX.json"
    payload = read_json(path, base, missing)
    if payload is None:
        details["migration_count"] = 0
        return
    migration_rows = rows(payload, ("migrations", "ideas", "rows"))
    details["migration_count"] = len(migration_rows)
    if not migration_rows:
        if not has_no_viable_reason(payload):
            warnings.append("ideation/INNOVATION_MIGRATION_MATRIX.json has no rows and no no_viable_candidate_reason")
        return
    for index, row in enumerate(migration_rows):
        prefix = f"ideation/INNOVATION_MIGRATION_MATRIX.json rows[{index}]"
        paper_id = str(row.get("source_paper_id") or row.get("paper_id") or "")
        field_distance = norm(row.get("field_distance") or screening.get(paper_id, {}).get("field_distance"))
        mech_id = str(row.get("source_mechanism_id") or row.get("mechanism_id") or "")
        for field in ["migration_id", "source_mechanism_id", "target_task", "adaptation_plan", "validation_route", "falsifier", "lifecycle_status"]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if mechanism_ids and mech_id and mech_id not in mechanism_ids:
            warnings.append(f"{prefix}.source_mechanism_id not found in CODE_MECHANISM_MAP.json: {mech_id}")
        if field_distance == DIRECT and not present(row.get("override_reason")):
            missing.append(f"{prefix} direct_field cannot enter innovation migration without override_reason")
        if field_distance == BLOCKED and not present(row.get("override_reason")):
            missing.append(f"{prefix} blocked paper cannot enter innovation migration without override_reason")


def lint_fast_queue(base: Path, screening: dict[str, dict[str, Any]], missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "ideation/FAST_VALIDATION_QUEUE.json"
    payload = read_json(path, base, missing)
    if payload is None:
        details["fast_validation_count"] = 0
        return
    queue_rows = rows(payload, ("ideas", "queue", "rows"))
    details["fast_validation_count"] = len(queue_rows)
    if not queue_rows:
        if not has_no_viable_reason(payload):
            warnings.append("ideation/FAST_VALIDATION_QUEUE.json has no rows and no no_viable_candidate_reason")
        return
    for index, row in enumerate(queue_rows):
        prefix = f"ideation/FAST_VALIDATION_QUEUE.json rows[{index}]"
        paper_id = str(row.get("source_paper_id") or row.get("paper_id") or "")
        field_distance = norm(row.get("field_distance") or screening.get(paper_id, {}).get("field_distance"))
        required = [
            "idea_id",
            "target_task",
            "implementation_scope",
            "expected_files_to_edit",
            "requires_new_dataset",
            "requires_large_model",
            "requires_diffusion_or_generation",
            "estimated_gpu_cost",
            "minimal_validation_dataset",
            "success_metric",
            "falsifier",
            "priority",
        ]
        for field in required:
            if field not in row or not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if not (present(row.get("source_paper_id")) or present(row.get("source_mechanism_id"))):
            missing.append(f"{prefix}.source_paper_id or source_mechanism_id")
        if field_distance == DIRECT and not present(row.get("override_reason")):
            missing.append(f"{prefix} direct_field cannot enter FAST_VALIDATION_QUEUE without override_reason")
        if field_distance == BLOCKED and not present(row.get("override_reason")):
            missing.append(f"{prefix} blocked paper cannot enter FAST_VALIDATION_QUEUE without override_reason")
        for flag in HEAVY_FLAGS:
            if row.get(flag) is True and not present(row.get("override_reason")):
                missing.append(f"{prefix}.{flag}=true requires override_reason and should usually be excluded")
        if row.get("requires_new_dataset") is True:
            warnings.append(f"{prefix}.requires_new_dataset=true may violate fast-validation constraints")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="Project root containing .autoreskill")
    parser.add_argument("--required", action="store_true", help="Exit nonzero if required artifacts or policy checks are missing")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result only")
    args = parser.parse_args()

    base = ar(args.project)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"base": str(base)}

    lint_policy(base, missing, warnings, details)
    lint_plan(base, missing, warnings, details)
    details["raw_harvest_count"] = read_jsonl_count(base / "survey/RAW_PAPERSCOOL_HARVEST.jsonl", base, missing, warnings)
    screening = lint_screening(base, missing, warnings, details)
    lint_exclusion(base, missing, warnings, details)
    candidate_ids = lint_candidates(base, screening, missing, warnings, details)
    valid_sources = lint_repo_evidence(base, candidate_ids, missing, warnings, details)
    mechanism_ids = lint_mechanisms(base, screening, valid_sources, missing, warnings, details)
    lint_migrations(base, screening, mechanism_ids, missing, warnings, details)
    lint_fast_queue(base, screening, missing, warnings, details)

    result = {
        "ok": not missing,
        "missing": missing,
        "warnings": warnings,
        "details": details,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.required and missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
