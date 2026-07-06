#!/usr/bin/env python3
"""Lint paper-reported baseline authority for AutoResearch workflows.

The linter is opt-in for generic projects and mandatory when the project
policy declares paper-reported baselines as the primary authority. Local or
reproduced baselines may still be recorded, but only as diagnostic evidence
unless there is an explicit no-paper-report internal-ablation boundary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PAPER_AUTHORITY = "paper_reported_metrics"
DIAGNOSTIC_ROLE = "diagnostic_sanity_check_only"
REPORT_METRIC_AUTHORITY = "paper_report_primary"
METRIC_UNIT = "percentage_points"


def read_json(path: Path, errors: list[str] | None = None) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        if errors is not None:
            errors.append(f"invalid JSON in {path}: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


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


def metric_triplet_ok(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for key in ("all", "old", "new"):
        if key not in value or not isinstance(value[key], (int, float)):
            return False
    return True


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in [
        "entries",
        "runs",
        "candidate_runs",
        "terminal_diagnostic_runs",
        "terminal_reconciliations",
        "track_best_runs",
        "best_runs",
        "rows",
        "results",
    ]:
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
        elif isinstance(value, dict):
            rows.extend(row for row in value.values() if isinstance(row, dict))
    for key in ["best_run", "promoted_best", "promoted_best_run", "selected_run", "run"]:
        value = payload.get(key)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def alignment_required(project: Path, explicit_required: bool, autopilot: dict[str, Any]) -> bool:
    if explicit_required:
        return True
    if autopilot.get("analysis_requires_paper_report_baseline_lint") is True:
        return True
    policy = autopilot.get("baseline_report_metric_policy")
    if isinstance(policy, dict) and policy.get("primary_baseline_authority") == PAPER_AUTHORITY:
        return True
    ar = project / ".autoreskill"
    return any(
        (ar / rel).exists()
        for rel in [
            "experiment/BASELINE_ALIGNMENT_POLICY.json",
            "experiment/BASELINE_REPORT_METRICS.json",
            "experiment/BASELINE_ALIGNMENT_AUDIT.md",
        ]
    )


def validate_policy(project: Path, policy: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if not policy:
        return
    if policy.get("primary_baseline_authority") != PAPER_AUTHORITY:
        errors.append("BASELINE_ALIGNMENT_POLICY.primary_baseline_authority must be paper_reported_metrics")
    if policy.get("reproduced_baseline_role") != DIAGNOSTIC_ROLE:
        errors.append("BASELINE_ALIGNMENT_POLICY.reproduced_baseline_role must be diagnostic_sanity_check_only")
    if policy.get("metric_unit") and policy.get("metric_unit") != METRIC_UNIT:
        errors.append("BASELINE_ALIGNMENT_POLICY.metric_unit must be percentage_points")
    required_artifacts = policy.get("required_artifacts")
    if isinstance(required_artifacts, dict):
        for name, rel_path in required_artifacts.items():
            path = project / str(rel_path)
            if not path.exists():
                errors.append(f"policy required_artifacts.{name} does not exist: {rel_path}")
    elif required_artifacts is not None:
        warnings.append("BASELINE_ALIGNMENT_POLICY.required_artifacts should be an object")


def validate_report_metrics(metrics: dict[str, Any], errors: list[str], warnings: list[str]) -> set[str]:
    baseline_ids: set[str] = set()
    if not metrics:
        return baseline_ids
    if metrics.get("metric_authority") != REPORT_METRIC_AUTHORITY:
        errors.append("BASELINE_REPORT_METRICS.metric_authority must be paper_report_primary")
    if metrics.get("metric_unit") != METRIC_UNIT:
        errors.append("BASELINE_REPORT_METRICS.metric_unit must be percentage_points")
    sources = metrics.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("BASELINE_REPORT_METRICS.sources must not be empty")
    elif not any(isinstance(source, dict) and source.get("authority") == "primary" for source in sources):
        errors.append("BASELINE_REPORT_METRICS.sources must contain a primary source")
    baselines = metrics.get("baselines")
    if not isinstance(baselines, list) or not baselines:
        errors.append("BASELINE_REPORT_METRICS.baselines must not be empty")
        return baseline_ids
    for index, row in enumerate(baselines):
        if not isinstance(row, dict):
            errors.append(f"baselines[{index}] must be an object")
            continue
        row_id = str(row.get("baseline_id") or f"baselines[{index}]")
        baseline_ids.add(row_id)
        for field in ["paper", "method", "dataset"]:
            if not present(row.get(field)):
                errors.append(f"{row_id}: {field} is required")
        report_metrics = row.get("paper_reported_metrics")
        if not isinstance(report_metrics, dict) or not report_metrics:
            errors.append(f"{row_id}: paper_reported_metrics must be a non-empty object")
            continue
        for domain, values in report_metrics.items():
            if not metric_triplet_ok(values):
                errors.append(f"{row_id}.{domain}: must contain numeric all/old/new")
    for index, row in enumerate(metrics.get("current_local_alignment", [])):
        if not isinstance(row, dict):
            errors.append(f"current_local_alignment[{index}] must be an object")
            continue
        run_id = row.get("local_run_id", f"current_local_alignment[{index}]")
        if row.get("claim_role") == "primary":
            errors.append(f"{run_id}: local reproduction cannot have claim_role=primary")
        if row.get("gap_valid_for_claim") is True:
            errors.append(f"{run_id}: local reproduction gap_valid_for_claim must not be true")
        if row.get("strict_alignment_status") == "strictly_aligned" and row.get("claim_role") != "diagnostic_only":
            warnings.append(f"{run_id}: strict local reproduction still must not override paper report metrics")
    for row in metrics.get("current_experiment_policy", []):
        if not isinstance(row, dict):
            continue
        experiment_id = row.get("experiment_id", "<unknown>")
        if row.get("local_reproduction_primary") is True:
            errors.append(f"{experiment_id}: local_reproduction_primary must not be true")
        if row.get("paper_claim_allowed_from_local_reproduction") is True:
            errors.append(f"{experiment_id}: paper claims from local reproduction are forbidden")
    return baseline_ids


def validate_github_issue_audit(issue_audit: dict[str, Any], errors: list[str], warnings: list[str]) -> dict[str, Any]:
    details: dict[str, Any] = {
        "present": bool(issue_audit),
        "issue_count": 0,
        "blocking_reproduction_issue_count": 0,
        "public_successful_report_metric_alignment_found": None,
    }
    if not issue_audit:
        return details

    repository = issue_audit.get("repository")
    if not isinstance(repository, dict) or not present(repository.get("full_name")):
        errors.append("BASELINE_GITHUB_ISSUE_AUDIT.repository.full_name is required")

    conclusion = issue_audit.get("conclusion")
    if not isinstance(conclusion, dict):
        errors.append("BASELINE_GITHUB_ISSUE_AUDIT.conclusion is required")
    else:
        details["public_successful_report_metric_alignment_found"] = conclusion.get(
            "public_successful_report_metric_alignment_found"
        )
        if "public_successful_report_metric_alignment_found" not in conclusion:
            errors.append(
                "BASELINE_GITHUB_ISSUE_AUDIT.conclusion.public_successful_report_metric_alignment_found is required"
            )
        if conclusion.get("paper_report_metrics_remain_primary") is not True:
            warnings.append("GitHub issue audit should not override paper-reported baseline metrics")

    issues = issue_audit.get("issues")
    if not isinstance(issues, list) or not issues:
        errors.append("BASELINE_GITHUB_ISSUE_AUDIT.issues must be a non-empty list")
        return details

    details["issue_count"] = len(issues)
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            errors.append(f"BASELINE_GITHUB_ISSUE_AUDIT.issues[{index}] must be an object")
            continue
        prefix = f"BASELINE_GITHUB_ISSUE_AUDIT.issues[{index}]"
        for field in ["number", "title", "state", "url", "alignment_impact", "strict_baseline_reproduction_impact"]:
            if not present(issue.get(field)):
                errors.append(f"{prefix}.{field} is required")
        impact = normalized(issue.get("strict_baseline_reproduction_impact"))
        if "blocking" in impact or "block" in impact:
            details["blocking_reproduction_issue_count"] += 1
            if not present(issue.get("required_action")):
                errors.append(f"{prefix}.required_action is required for blocking reproduction issues")

    if details["blocking_reproduction_issue_count"]:
        warnings.append(
            "GitHub issue audit contains unresolved blocking reproduction risks; local baselines must stay diagnostic_only until reconciled"
        )
    return details


def row_baseline_ref(row: dict[str, Any]) -> str:
    for key in ["paper_report_baseline_id", "report_baseline_id", "baseline_id"]:
        if present(row.get(key)):
            return str(row[key])
    for key in ["baseline_ref", "paper_report_baseline_ref", "baseline_report_ref", "matched_baseline"]:
        value = row.get(key)
        if isinstance(value, dict):
            for nested in ["baseline_id", "paper_report_baseline_id", "report_baseline_id"]:
                if present(value.get(nested)):
                    return str(value[nested])
        elif present(value):
            return str(value)
    refs = row.get("baseline_report_refs")
    if isinstance(refs, list) and refs:
        first = refs[0]
        if isinstance(first, dict) and present(first.get("baseline_id")):
            return str(first["baseline_id"])
        if present(first):
            return str(first)
    return ""


def is_evidence_bearing(row: dict[str, Any]) -> bool:
    status = normalized(row.get("status") or row.get("run_status") or row.get("promotion_status"))
    decision = normalized(row.get("promotion_decision") or row.get("verdict") or row.get("final_promotion_status"))
    return (
        row.get("candidate_supported") is True
        or row.get("ready_for_analysis") is True
        or row.get("paper_claim_allowed") is True
        or decision in {"promoted", "candidate_supported", "candidate_supported_not_promoted", "candidate_supported_requires_confirmation"}
        or decision.startswith("promoted")
        or status.startswith("completed_promoted")
    )


def diagnostic_only(row: dict[str, Any]) -> bool:
    scope = normalized(row.get("promotion_scope") or row.get("claim_scope") or row.get("protocol_status") or row.get("claim_role"))
    decision = normalized(row.get("promotion_decision") or row.get("promotion_status") or row.get("final_promotion_status"))
    return (
        row.get("paper_claim_allowed") is False
        or row.get("paper_claim_allowed_from_local_reproduction") is False
        or row.get("gap_valid_for_claim") is False
        or "diagnostic" in scope
        or "mini_proxy" in scope
        or "candidate_signal_only" in decision
        or "not_paper_promoted" in decision
    )


def validate_experiment_rows(base: Path, baseline_ids: set[str], errors: list[str], warnings: list[str]) -> dict[str, Any]:
    checked = 0
    diagnostic_rows = 0
    missing_refs = 0
    invalid_refs = 0
    sources = {
        "coder/EXPERIMENT_LEDGER.json": read_json(base / "coder/EXPERIMENT_LEDGER.json", errors),
        "analyzer/BEST_RUN_SELECTION.json": read_json(base / "analyzer/BEST_RUN_SELECTION.json", errors),
        "analyzer/SCORE_VERIFICATION.json": read_json(base / "analyzer/SCORE_VERIFICATION.json", errors),
    }
    for rel, payload in sources.items():
        for index, row in enumerate(rows_from_payload(payload)):
            if not is_evidence_bearing(row):
                continue
            checked += 1
            prefix = f"{rel} row[{index}]"
            ref = row_baseline_ref(row)
            if not ref:
                if diagnostic_only(row):
                    diagnostic_rows += 1
                    warnings.append(f"{prefix}: evidence-bearing local/proxy row is diagnostic-only and has no paper report baseline ref")
                    continue
                missing_refs += 1
                errors.append(f"{prefix}: evidence-bearing result must reference a paper_report_baseline_id/report_baseline_id")
                continue
            if baseline_ids and ref not in baseline_ids and not any(ref.endswith(bid) or bid in ref for bid in baseline_ids):
                invalid_refs += 1
                errors.append(f"{prefix}: baseline ref {ref} is not present in BASELINE_REPORT_METRICS.baselines")
    return {
        "checked_evidence_rows": checked,
        "diagnostic_only_rows_without_report_ref": diagnostic_rows,
        "missing_report_baseline_refs": missing_refs,
        "invalid_report_baseline_refs": invalid_refs,
    }


def validate_analyzer_policy(base: Path, stage: str, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if stage not in {"analysis", "review_pressure", "writing", "submission_ready"}:
        return details
    best = read_json(base / "analyzer/BEST_RUN_SELECTION.json", errors)
    score = read_json(base / "analyzer/SCORE_VERIFICATION.json", errors)
    details["best_run_selection_present"] = bool(best)
    details["score_verification_present"] = bool(score)
    if best:
        override = best.get("report_baseline_policy_override")
        final_status = normalized(best.get("final_promotion_status"))
        if not isinstance(override, dict) or override.get("primary_baseline_authority") != PAPER_AUTHORITY:
            errors.append("analyzer/BEST_RUN_SELECTION.json must record report_baseline_policy_override.primary_baseline_authority=paper_reported_metrics")
        if final_status in {"promoted", "paper_promoted", "candidate_supported"}:
            errors.append("analyzer/BEST_RUN_SELECTION.json final_promotion_status must not promote a run without paper-report baseline alignment")
    elif stage in {"writing", "submission_ready"}:
        errors.append("analyzer/BEST_RUN_SELECTION.json is required before writing/submission")
    if score:
        policy = score.get("report_baseline_policy")
        if not isinstance(policy, dict) or policy.get("primary_baseline_authority") != PAPER_AUTHORITY:
            errors.append("analyzer/SCORE_VERIFICATION.json must record report_baseline_policy.primary_baseline_authority=paper_reported_metrics")
        status = normalized(score.get("status"))
        if status in {"passed", "complete", "ready", "verified"} and stage in {"writing", "submission_ready"}:
            warnings.append("SCORE_VERIFICATION passed; confirm it used paper-report baselines, not reproduced baseline values")
    elif stage in {"writing", "submission_ready"}:
        errors.append("analyzer/SCORE_VERIFICATION.json is required before writing/submission")
    return details


def lint(project: Path, stage: str, required: bool) -> dict[str, Any]:
    project = project.expanduser().resolve()
    base = project / ".autoreskill"
    errors: list[str] = []
    warnings: list[str] = []
    autopilot = read_json(base / "autopilot_policy.json", errors)
    must_check = alignment_required(project, required, autopilot)
    policy_path = base / "experiment/BASELINE_ALIGNMENT_POLICY.json"
    metrics_path = base / "experiment/BASELINE_REPORT_METRICS.json"
    audit_path = base / "experiment/BASELINE_ALIGNMENT_AUDIT.md"
    issue_audit_path = base / "experiment/BASELINE_GITHUB_ISSUE_AUDIT.json"

    if not must_check:
        return {
            "status": "skipped",
            "complete": True,
            "project": str(project),
            "stage": stage,
            "required": False,
            "errors": [],
            "missing": [],
            "warnings": [],
            "details": {"reason": "no required policy or baseline alignment artifacts found"},
        }

    if not policy_path.exists():
        errors.append(f"missing required artifact: {policy_path.relative_to(project)}")
    if not metrics_path.exists():
        errors.append(f"missing required artifact: {metrics_path.relative_to(project)}")
    if not audit_path.exists():
        errors.append(f"missing required artifact: {audit_path.relative_to(project)}")

    policy = read_json(policy_path, errors)
    metrics = read_json(metrics_path, errors)
    issue_audit = read_json(issue_audit_path, errors) if issue_audit_path.exists() else {}
    validate_policy(project, policy, errors, warnings)
    baseline_ids = validate_report_metrics(metrics, errors, warnings)
    issue_audit_details = validate_github_issue_audit(issue_audit, errors, warnings)
    experiment_details = validate_experiment_rows(base, baseline_ids, errors, warnings)
    analyzer_details = validate_analyzer_policy(base, stage, errors, warnings)

    checked_artifacts = [
        str(policy_path.relative_to(project)),
        str(metrics_path.relative_to(project)),
        str(audit_path.relative_to(project)),
    ]
    if issue_audit_path.exists():
        checked_artifacts.append(str(issue_audit_path.relative_to(project)))

    details = {
        "baseline_count": len(baseline_ids),
        "checked_artifacts": checked_artifacts,
        "github_issue_audit": issue_audit_details,
        "experiment_rows": experiment_details,
        "analyzer_policy": analyzer_details,
        "autopilot_requires_alignment": autopilot.get("analysis_requires_paper_report_baseline_lint") is True,
    }
    return {
        "status": "failed" if errors else "passed",
        "complete": not errors,
        "project": str(project),
        "stage": stage,
        "required": True,
        "errors": errors,
        "missing": errors,
        "warnings": warnings,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint paper-report baseline alignment artifacts.")
    parser.add_argument("--project", default=".", help="Project root. Defaults to current directory.")
    parser.add_argument("--stage", default="analysis", help="Workflow stage using this check.")
    parser.add_argument("--required", action="store_true", help="Force paper-report baseline artifacts to exist.")
    args = parser.parse_args()

    out = lint(Path(args.project), args.stage, args.required)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("complete") else 1


if __name__ == "__main__":
    sys.exit(main())
