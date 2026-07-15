#!/usr/bin/env python3
"""Select the best validated run and emit analysis provenance artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_NONPOSITIVE_STATUSES = {
    "core_hypotheses_refuted",
    "no_valid_gain",
    "inconclusive_budget_exhausted",
    "protocol_unresolvable",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def entries_from_ledger(ledger: Any) -> list[dict[str, Any]]:
    if isinstance(ledger, dict) and isinstance(ledger.get("entries"), list):
        return [row for row in ledger["entries"] if isinstance(row, dict)]
    return []


def run_id(row: dict[str, Any]) -> str:
    return str(row.get("experiment_id") or row.get("remote_run") or row.get("manifest") or "unknown")


def terminal_nonpositive_program(base: Path, ledger: dict[str, Any]) -> dict[str, Any]:
    decision_ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {})
    decision = decision_ledger.get("program_decision") if isinstance(decision_ledger, dict) else None
    if not isinstance(decision, dict):
        return {}
    status = str(decision.get("status") or "").strip().lower()
    if (
        decision.get("terminal") is True
        and status in TERMINAL_NONPOSITIVE_STATUSES
        and str(decision.get("target_stage") or "").strip().lower() == "analysis"
        and ledger.get("improvement_claim_allowed") is False
    ):
        return decision
    return {}


def build(project: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = ar(project)
    ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json", {})
    entries = entries_from_ledger(ledger)
    promoted = [row for row in entries if str(row.get("promotion_status") or row.get("promotion_decision") or "") == "promoted"]
    selected = ledger.get("best_run") if isinstance(ledger, dict) and isinstance(ledger.get("best_run"), dict) else None
    if not selected and promoted:
        selected = promoted[0]
    terminal_program = terminal_nonpositive_program(base, ledger if isinstance(ledger, dict) else {})
    terminal_no_promotion = bool(terminal_program and not selected)
    excluded = []
    for row in entries:
        if selected and run_id(row) == run_id(selected):
            continue
        reason = row.get("promotion_reason") or row.get("retire_reason") or "not selected by promoted-run policy"
        excluded.append({"run_id": run_id(row), "track_id": row.get("track_id"), "reason": reason, "promotion_status": row.get("promotion_status") or row.get("promotion_decision")})
    selection = {
        "schema_version": 1,
        "created_at": now(),
        "selector": "deterministic_promoted_best_run",
        "selected_track_id": selected.get("track_id") if selected else None,
        "selected_run_id": run_id(selected) if selected else None,
        "candidate_runs_considered": [run_id(row) for row in entries],
        "canonical_metric_values": [
            {"run_id": run_id(row), "track_id": row.get("track_id"), "metric_value": row.get("metric_value") or (row.get("metrics") or {}).get("proposed"), "metric_source": row.get("metric_source") or row.get("metrics_path")}
            for row in entries
        ],
        "excluded_runs": excluded,
        "exclusion_reasons": {row["run_id"]: row["reason"] for row in excluded},
        "ablation_or_confirmation_ref": selected.get("ablation_of") or selected.get("confirmation_of") if selected else None,
        "final_promotion_status": "promoted" if selected else "terminal_program_no_promoted_run" if terminal_no_promotion else "blocked_no_promoted_run",
        "program_decision_status": terminal_program.get("status") if terminal_program else None,
        "program_decision_ref": "ideation/IDEA_DECISION_LEDGER.json#program_decision" if terminal_program else None,
        "claim_policy": "strong_improvement_claims_require_selected_promoted_run" if selected else "no_positive_improvement_claim",
    }
    score_failures = []
    for row in promoted:
        metric = row.get("metric_value") or (row.get("metrics") or {}).get("proposed")
        if metric is None:
            score_failures.append({"run_id": run_id(row), "reason": "missing canonical metric"})
    score = {
        "schema_version": 1,
        "created_at": now(),
        "status": "not_applicable_no_positive_claim" if terminal_no_promotion else "passed" if selected and not score_failures else "blocked",
        "selected_run_id": selection["selected_run_id"],
        "checks": [
            {"run_id": run_id(row), "metric_value": row.get("metric_value") or (row.get("metrics") or {}).get("proposed"), "metric_source": row.get("metric_source") or row.get("metrics_path"), "status": "passed" if (row.get("metric_value") or (row.get("metrics") or {}).get("proposed")) is not None else "blocked"}
            for row in promoted
        ],
        "failures": score_failures,
    }
    spec_failures = [
        {"run_id": run_id(row), "track_id": row.get("track_id"), "status": row.get("spec_violation_status")}
        for row in entries
        if str(row.get("spec_violation_status") or "").strip().lower() in {"flagged", "violation", "failed"}
    ]
    spec = {
        "schema_version": 1,
        "created_at": now(),
        "status": (
            "not_applicable_no_valid_result"
            if terminal_no_promotion and str(terminal_program.get("status") or "") == "protocol_unresolvable"
            else "passed" if not spec_failures else "blocked"
        ),
        "checks": [
            {"run_id": run_id(row), "track_id": row.get("track_id"), "status": row.get("spec_violation_status") or "not_checked"}
            for row in entries
        ],
        "failures": spec_failures,
    }
    return selection, score, spec


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    selection = read_json(base / "analyzer/BEST_RUN_SELECTION.json", {})
    score = read_json(base / "analyzer/SCORE_VERIFICATION.json", {})
    spec = read_json(base / "analyzer/SPEC_VIOLATION_AUDIT.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    terminal_no_promotion = (
        isinstance(selection, dict)
        and selection.get("final_promotion_status") == "terminal_program_no_promoted_run"
        and not present(selection.get("selected_run_id"))
        and present(selection.get("program_decision_ref"))
    )
    if terminal_no_promotion:
        if not isinstance(score, dict) or score.get("status") != "not_applicable_no_positive_claim":
            missing.append("analyzer/SCORE_VERIFICATION.json status=not_applicable_no_positive_claim")
        if not isinstance(spec, dict) or spec.get("status") not in {"passed", "not_applicable_no_valid_result"}:
            missing.append("analyzer/SPEC_VIOLATION_AUDIT.json passed or not_applicable_no_valid_result")
    else:
        if not isinstance(selection, dict) or not present(selection.get("selected_run_id")):
            missing.append("analyzer/BEST_RUN_SELECTION.json selected_run_id")
        elif selection.get("final_promotion_status") != "promoted":
            missing.append("analyzer/BEST_RUN_SELECTION.json final_promotion_status=promoted")
        if not isinstance(score, dict) or score.get("status") != "passed":
            missing.append("analyzer/SCORE_VERIFICATION.json status=passed")
        if not isinstance(spec, dict) or spec.get("status") != "passed":
            missing.append("analyzer/SPEC_VIOLATION_AUDIT.json status=passed")
    if selection and not terminal_no_promotion and not present(selection.get("ablation_or_confirmation_ref")):
        warnings.append("selected run has no explicit ablation_or_confirmation_ref; keep claims moderate unless ledger proves promotion")
    return {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        out = check(args.project)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        raise SystemExit(0 if out["complete"] else 1)
    selection, score, spec = build(args.project)
    base = ar(args.project)
    write_json(base / "analyzer/BEST_RUN_SELECTION.json", selection)
    write_json(base / "analyzer/SCORE_VERIFICATION.json", score)
    write_json(base / "analyzer/SPEC_VIOLATION_AUDIT.json", spec)
    out = check(args.project)
    print(json.dumps({"ok": out["complete"], "artifacts": ["analyzer/BEST_RUN_SELECTION.json", "analyzer/SCORE_VERIFICATION.json", "analyzer/SPEC_VIOLATION_AUDIT.json"], **out}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
