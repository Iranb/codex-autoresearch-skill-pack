#!/usr/bin/env python3
"""Lint paper-code survey, source mechanism, and innovation transfer artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


READY = {"ready", "complete", "completed", "pass", "passed", "valid", "verified", "selected_candidate"}
VALID_REPO_STATUSES = {
    "valid",
    "usable",
    "reviewed",
    "reviewed_usable",
    "reviewed_valid",
    "source_read",
    "implementation_valid",
}
INVALID_REPO_STATUSES = {"thin", "project_page", "benchmark_only", "mismatch", "dead_link", "invalid", "no_code"}
PAPER_CODE_TOKENS = (
    "paper_code_transfer_lint",
    "paper-code",
    "code survey",
    "code analysis",
    "source code",
    "source-code",
    "repository validation",
    "repo",
    "repos",
    "repository",
    "repositories",
    "github",
    "源码",
    "代码",
    "仓库",
)
PAPER_CODE_INTENT_TOKENS = (
    "survey",
    "analysis",
    "analyze",
    "validation",
    "innovation",
    "transfer",
    "migration",
    "调研",
    "分析",
    "验证",
    "创新",
    "迁移",
)


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_artifact_json(path: Path, base: Path, missing: list[str]) -> Any:
    label = rel(base, path)
    if not path.exists():
        missing.append(label)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        missing.append(f"{label} invalid JSON at line {exc.lineno} column {exc.colno}")
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def normalized_values(*values: Any) -> set[str]:
    return {normalized(value) for value in values if normalized(value)}


def contains_trigger_token(text: str, token: str) -> bool:
    if token.isascii():
        return re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text) is not None
    return token in text


def rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def goal_text(base: Path) -> str:
    state = read_json(base / "goal_state.json")
    if isinstance(state, dict):
        fields = [
            state.get("goal"),
            state.get("objective"),
            state.get("research_goal"),
            state.get("topic"),
            state.get("next_action"),
        ]
        return "\n".join(str(field) for field in fields if field)
    return ""


def survey_required(base: Path) -> bool:
    survey_dir = base / "survey"
    if any((survey_dir / name).exists() for name in [
        "PAPER_CODE_SURVEY_PLAN.json",
        "PAPER_CODE_CANDIDATES.json",
        "REPO_STATIC_EVIDENCE.json",
        "CODE_MECHANISM_MAP.json",
    ]):
        return True
    if (base / "ideation/INNOVATION_MIGRATION_MATRIX.json").exists():
        return True
    text = goal_text(base).lower()
    if "paper_code_transfer_lint" in text:
        return True
    return any(contains_trigger_token(text, token) for token in PAPER_CODE_TOKENS) and any(
        contains_trigger_token(text, token) for token in PAPER_CODE_INTENT_TOKENS
    )


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def lint_plan(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "survey/PAPER_CODE_SURVEY_PLAN.json"
    plan = read_artifact_json(path, base, missing)
    if plan is None:
        return
    if not isinstance(plan, dict):
        missing.append("survey/PAPER_CODE_SURVEY_PLAN.json must be a JSON object")
        return
    details["plan_path"] = rel(base, path)
    for field in ["target_task", "source_lanes"]:
        if not present(plan.get(field)):
            missing.append(f"survey/PAPER_CODE_SURVEY_PLAN.json {field}")
    if not (present(plan.get("year_range")) or present(plan.get("date_scope"))):
        missing.append("survey/PAPER_CODE_SURVEY_PLAN.json year_range or date_scope")
    if not (present(plan.get("venue_scope")) or present(plan.get("source_scope"))):
        missing.append("survey/PAPER_CODE_SURVEY_PLAN.json venue_scope or source_scope")
    if not (present(plan.get("paper_count_goal")) or present(plan.get("coverage_policy"))):
        warnings.append("survey/PAPER_CODE_SURVEY_PLAN.json should record paper_count_goal or coverage_policy")


def lint_candidates(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "survey/PAPER_CODE_CANDIDATES.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["candidate_count"] = 0
        return set()
    candidate_rows = rows(payload, ("papers", "candidates", "rows"))
    details["candidate_count"] = len(candidate_rows)
    if not candidate_rows:
        missing.append("survey/PAPER_CODE_CANDIDATES.json papers[] or candidates[]")
        return set()
    ids: set[str] = set()
    with_code = 0
    for index, row in enumerate(candidate_rows):
        prefix = f"survey/PAPER_CODE_CANDIDATES.json candidates[{index}]"
        paper_id = row.get("paper_id") or row.get("id") or row.get("stable_id")
        if not present(paper_id):
            missing.append(f"{prefix}.paper_id")
        else:
            ids.add(str(paper_id))
        for field in ["title", "year", "lane"]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if not (present(row.get("venue")) or present(row.get("source"))):
            missing.append(f"{prefix}.venue or source")
        if present(row.get("code_url") or row.get("repo_url") or row.get("repository_url")):
            with_code += 1
        elif normalized(row.get("code_status")) not in {"no_code", "not_found", "source_limited", "unavailable"}:
            warnings.append(f"{prefix} has no code URL and no explicit no-code/source-limited status")
        if not present(row.get("decision") or row.get("inclusion_decision")):
            warnings.append(f"{prefix}.decision")
    details["candidate_with_code_count"] = with_code
    if with_code == 0:
        missing.append("survey/PAPER_CODE_CANDIDATES.json at least one candidate with code_url/repo_url")
    return ids


def lint_repo_evidence(base: Path, candidate_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "survey/REPO_STATIC_EVIDENCE.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["repo_evidence_count"] = 0
        return set()
    repo_rows = rows(payload, ("repositories", "repos", "rows"))
    details["repo_evidence_count"] = len(repo_rows)
    if not repo_rows:
        missing.append("survey/REPO_STATIC_EVIDENCE.json repositories[]")
        return set()
    valid_refs: set[str] = set()
    valid_count = 0
    for index, row in enumerate(repo_rows):
        prefix = f"survey/REPO_STATIC_EVIDENCE.json repositories[{index}]"
        paper_id = row.get("paper_id") or row.get("source_paper_id")
        if not present(paper_id):
            missing.append(f"{prefix}.paper_id")
        elif candidate_ids and str(paper_id) not in candidate_ids:
            warnings.append(f"{prefix}.paper_id not found in candidate ledger: {paper_id}")
        repo_ref = row.get("repo_url") or row.get("repository_url") or row.get("repo_ref")
        if not present(repo_ref):
            missing.append(f"{prefix}.repo_url or repo_ref")
        status_values = normalized_values(
            row.get("repo_status"),
            row.get("status"),
            row.get("validity_decision"),
            row.get("review_decision"),
        )
        if not status_values:
            missing.append(f"{prefix}.repo_status")
        evidence = row.get("static_evidence") or row.get("evidence") or {}
        invalid_status = bool(status_values & INVALID_REPO_STATUSES)
        valid_status = bool(status_values & VALID_REPO_STATUSES)
        if valid_status and not invalid_status:
            valid_count += 1
            for ref in [repo_ref, row.get("repo_ref"), row.get("repo_id"), row.get("id"), paper_id]:
                if present(ref):
                    valid_refs.add(str(ref))
            for field in ["entrypoints", "configs", "metrics"]:
                if isinstance(evidence, dict) and not present(evidence.get(field)):
                    warnings.append(f"{prefix}.static_evidence.{field}")
            if not present(row.get("paper_code_match")):
                warnings.append(f"{prefix}.paper_code_match")
        elif row.get("code_available") is True:
            warnings.append(f"{prefix} has code_available=true but is not reviewed valid/usable yet")
        if invalid_status and not present(row.get("failure_reason") or row.get("reject_reason")):
            missing.append(f"{prefix}.failure_reason for invalid/thin/mismatch repo")
        if not present(row.get("validity_decision") or row.get("review_decision")):
            missing.append(f"{prefix}.validity_decision")
    details["valid_repo_count"] = valid_count
    if valid_count == 0:
        missing.append("survey/REPO_STATIC_EVIDENCE.json at least one valid/usable repository")
    return valid_refs


def lint_mechanisms(base: Path, valid_repo_refs: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "survey/CODE_MECHANISM_MAP.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["mechanism_count"] = 0
        return set()
    mechanism_rows = rows(payload, ("mechanisms", "rows", "items"))
    details["mechanism_count"] = len(mechanism_rows)
    if not mechanism_rows:
        missing.append("survey/CODE_MECHANISM_MAP.json mechanisms[]")
        return set()
    ids: set[str] = set()
    for index, row in enumerate(mechanism_rows):
        prefix = f"survey/CODE_MECHANISM_MAP.json mechanisms[{index}]"
        mechanism_id = row.get("mechanism_id") or row.get("id")
        if not present(mechanism_id):
            missing.append(f"{prefix}.mechanism_id")
        else:
            ids.add(str(mechanism_id))
        for field in ["source_paper_id", "mechanism_summary", "target_pressure", "transfer_axis", "evidence_boundary"]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if not present(row.get("code_evidence_refs") or row.get("source_repo_ref")):
            missing.append(f"{prefix}.code_evidence_refs or source_repo_ref")
        source_repo = row.get("source_repo_ref")
        if present(source_repo) and valid_repo_refs and str(source_repo) not in valid_repo_refs:
            warnings.append(f"{prefix}.source_repo_ref does not match a valid repo ref: {source_repo}")
        if not present(row.get("active_path_evidence")):
            warnings.append(f"{prefix}.active_path_evidence")
        if normalized(row.get("claim_scope")) in {"strong", "promoted", "performance"}:
            missing.append(f"{prefix}.claim_scope must not be strong/performance from static code evidence alone")
    return ids


def lint_migrations(base: Path, mechanism_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "ideation/INNOVATION_MIGRATION_MATRIX.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["migration_count"] = 0
        return
    migration_rows = rows(payload, ("migrations", "ideas", "rows", "items"))
    details["migration_count"] = len(migration_rows)
    if not migration_rows:
        missing.append("ideation/INNOVATION_MIGRATION_MATRIX.json migrations[] or rows[]")
        return
    selected_like = 0
    for index, row in enumerate(migration_rows):
        prefix = f"ideation/INNOVATION_MIGRATION_MATRIX.json migrations[{index}]"
        migration_id = row.get("migration_id") or row.get("idea_id") or row.get("id")
        if not present(migration_id):
            missing.append(f"{prefix}.migration_id")
        source_mechanism = row.get("source_mechanism_id") or row.get("mechanism_id")
        if not present(source_mechanism):
            missing.append(f"{prefix}.source_mechanism_id")
        elif mechanism_ids and str(source_mechanism) not in mechanism_ids:
            missing.append(f"{prefix}.source_mechanism_id must reference CODE_MECHANISM_MAP")
        for field in [
            "target_task",
            "adaptation_plan",
            "required_code_changes",
            "required_protocol_changes",
            "novelty_or_overlap_risk",
            "claim_scope",
            "validation_route",
            "falsifier",
            "lifecycle_status",
        ]:
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        objective = normalized(row.get("objective_class"))
        if objective == "parameter_tuning" and row.get("reclassified_by_idea_gate") is not True:
            missing.append(f"{prefix}.objective_class parameter_tuning cannot be a migrated innovation without reclassified_by_idea_gate=true")
        if normalized(row.get("claim_scope")) in {"strong", "promoted", "performance"} and not present(row.get("promoted_evidence_ref")):
            missing.append(f"{prefix}.claim_scope must not be strong/promoted/performance before target-task evidence is promoted")
        lifecycle = normalized(row.get("lifecycle_status"))
        if lifecycle in {"selected_candidate", "direct_transfer", "needs_adaptation", "advance_with_constraints"}:
            selected_like += 1
            if not present(row.get("evidence_boundary")):
                missing.append(f"{prefix}.evidence_boundary")
            if not present(row.get("implementation_route") or row.get("validation_route")):
                missing.append(f"{prefix}.implementation_route or validation_route")
    details["migration_selected_like_count"] = selected_like
    if selected_like == 0:
        warnings.append("No migration row is selected/direct-transfer/needs-adaptation; standalone survey may be complete but has no actionable migrated idea yet")


def lint(project: str, force_required: bool = False) -> dict[str, Any]:
    base = ar(project)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    required = force_required or survey_required(base)
    details["required"] = required
    if not required:
        details["skipped_reason"] = "paper-code transfer artifacts not required by goal or existing survey files"
        return {
            "complete": True,
            "status": "complete",
            "missing": [],
            "warnings": [],
            "details": details,
        }
    lint_plan(base, missing, warnings, details)
    candidate_ids = lint_candidates(base, missing, warnings, details)
    valid_repo_refs = lint_repo_evidence(base, candidate_ids, missing, warnings, details)
    mechanism_ids = lint_mechanisms(base, valid_repo_refs, missing, warnings, details)
    lint_migrations(base, mechanism_ids, missing, warnings, details)
    complete = not missing
    return {
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--required",
        action="store_true",
        help="Force paper-code transfer artifacts to be required, even when the goal/artifact auto-detection has not triggered.",
    )
    args = parser.parse_args()
    result = lint(args.project, force_required=args.required)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
