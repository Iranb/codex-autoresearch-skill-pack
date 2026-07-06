#!/usr/bin/env python3
"""Lint per-candidate abstract/metadata screening audits."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


LANES = {"target_domain", "near_neighbor", "far_neighbor"}
DECISIONS = {
    "graph_import",
    "import_recommended",
    "split_read_only",
    "material_view",
    "selected",
    "selected_for_scorecard",
    "watchlist",
    "defer",
    "needs_import",
    "needs_abstract",
    "reject_duplicate",
    "reject_irrelevant",
    "reject_low_value",
    "reject_weak_relevance",
    "reject_weak_identity",
    "reject_method_unrelated",
    "reject_closed_set_only",
    "reject_unresolved_source",
    "reject_survey_noise",
    "reject_generic_benchmark",
    "reject_out_of_scope",
    "reject_no_abstract",
}
ROW_LIST_KEYS = ["rows", "screening_rows", "audit_rows", "papers", "candidates"]
ABSTRACT_KEYS = ["abstract", "abstract_text", "abstractSnippet", "abstract_snippet"]
IDENTIFIER_KEYS = [
    "identifier",
    "identifiers",
    "candidate_id",
    "paper_id",
    "doi",
    "DOI",
    "arxiv_id",
    "arxivId",
    "openalex_id",
    "openalexId",
    "semantic_scholar_id",
    "semanticScholarId",
    "s2_id",
    "corpusId",
]
REASON_KEYS = ["reason", "rationale", "decision_reason", "screening_reason"]
SOURCE_KEYS = ["provider", "providers", "query_id", "queryId", "run_id", "source_run_id", "discovery_run_id", "source"]
READ_KEYS = ["abstract_read", "abstract_screened", "read_abstract"]


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def resolve(base: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return base.parent / raw
    return base / path


def read_json(path: Path) -> Any:
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


def bool_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "read", "screened"}
    return False


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ROW_LIST_KEYS:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    rows_by_lane = payload.get("rows_by_lane") or payload.get("candidates_by_lane")
    if isinstance(rows_by_lane, dict):
        out: list[dict[str, Any]] = []
        for lane, lane_rows in rows_by_lane.items():
            if not isinstance(lane_rows, list):
                continue
            for row in lane_rows:
                if isinstance(row, dict):
                    merged = dict(row)
                    merged.setdefault("lane", lane)
                    out.append(merged)
        return out
    return []


def first_present(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if present(value):
            return value
    return None


def discovery_count(run: Any) -> int | None:
    if not isinstance(run, dict):
        return None
    for key in ["mergedPaperCount", "merged_paper_count", "metadataOnly", "metadata_only_count", "candidateCount", "candidate_count"]:
        value = run.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    return None


def expected_count_from_payload(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ["expected_candidate_count", "expected_row_count", "merged_paper_count", "mergedPaperCount", "candidate_count", "candidateCount"]:
        value = payload.get(key)
        if isinstance(value, int) and value > 0:
            return value
    runs = payload.get("discovery_runs")
    if isinstance(runs, list):
        counts = [count for count in (discovery_count(run) for run in runs) if count is not None]
        if counts:
            return sum(counts)
    return None


def coverage_exception_approved(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    approval = payload.get("coverage_exception_approval") or payload.get("manual_coverage_review")
    if not isinstance(approval, dict):
        return False
    return (
        approval.get("approved") is True
        and present(approval.get("approved_by") or approval.get("reviewer"))
        and present(approval.get("reason") or approval.get("rationale"))
    )


def row_identifier(row: dict[str, Any]) -> str | None:
    value = first_present(row, IDENTIFIER_KEYS)
    if isinstance(value, dict):
        for subvalue in value.values():
            if present(subvalue):
                return str(subvalue)
        return None
    if isinstance(value, list):
        for item in value:
            if present(item):
                return str(item)
        return None
    if present(value):
        return str(value)
    return None


def lint(project: str, audit_rel: str, scorecard_rel: str) -> dict[str, Any]:
    base = ar(project)
    audit_path = resolve(base, audit_rel)
    scorecard_path = resolve(base, scorecard_rel)
    payload = read_json(audit_path)
    scorecard = read_json(scorecard_path)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    if not isinstance(payload, (dict, list)):
        expected = expected_count_from_payload(scorecard)
        return {
            "complete": False,
            "status": "incomplete",
            "missing": [audit_rel],
            "warnings": [],
            "path": str(audit_path),
            "scorecard_path": str(scorecard_path),
            "expected_candidate_count": expected,
        }

    rows = rows_from_payload(payload)
    if not rows:
        missing.append("rows[] with one entry per merged discovery candidate")

    if isinstance(payload, dict):
        if payload.get("screening_completed") is not True:
            missing.append("screening_completed=true")
        if not present(payload.get("screening_basis")):
            warnings.append("screening_basis recommended, e.g. abstract_or_metadata_when_abstract_missing")
    expected = expected_count_from_payload(payload)
    if expected is None:
        expected = expected_count_from_payload(scorecard)
    if expected is not None and len(rows) != expected:
        if coverage_exception_approved(payload):
            warnings.append(f"row count {len(rows)} does not match expected {expected}, covered by explicit coverage exception")
        else:
            missing.append(f"row count must equal expected merged candidate count: rows={len(rows)} expected={expected}")

    lane_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    abstract_present_count = 0
    abstract_missing_count = 0
    source_count = 0
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    for index, row in enumerate(rows):
        prefix = f"rows[{index}]"
        lane = str(row.get("lane") or "").strip()
        decision = str(row.get("decision") or row.get("screening_decision") or "").strip()
        identifier = row_identifier(row)
        abstract_text = first_present(row, ABSTRACT_KEYS)
        abstract_missing = bool_true(row.get("abstract_missing") or row.get("no_abstract_available"))
        reason = first_present(row, REASON_KEYS)
        read_marker = any(bool_true(row.get(key)) for key in READ_KEYS)

        if lane not in LANES:
            missing.append(f"{prefix}.lane target_domain/near_neighbor/far_neighbor")
        else:
            lane_counts[lane] += 1
        if not present(row.get("title")):
            missing.append(f"{prefix}.title")
        if not identifier:
            missing.append(f"{prefix}.identifier or candidate_id/paper_id/provider id")
        elif identifier in seen_ids:
            duplicate_ids.add(identifier)
        else:
            seen_ids.add(identifier)
        if decision not in DECISIONS:
            missing.append(f"{prefix}.decision valid abstract-screening decision")
        else:
            decision_counts[decision] += 1
        if not present(reason):
            missing.append(f"{prefix}.reason or rationale")
        if present(first_present(row, SOURCE_KEYS)):
            source_count += 1

        if present(abstract_text):
            abstract_present_count += 1
            if not read_marker:
                missing.append(f"{prefix}.abstract_read=true")
        else:
            abstract_missing_count += 1
            if not abstract_missing:
                missing.append(f"{prefix}.abstract_missing=true when no abstract text is available")
            if not (present(row.get("decision_basis")) or bool_true(row.get("metadata_read"))):
                missing.append(f"{prefix}.decision_basis or metadata_read=true for no-abstract fallback")

    if duplicate_ids:
        warnings.append(f"duplicate row identifiers detected: {len(duplicate_ids)}")
    if rows and source_count < len(rows):
        warnings.append(f"{len(rows) - source_count} rows lack provider/query/run provenance")
    if rows and abstract_present_count == 0:
        warnings.append("no rows contain abstract text; this is metadata fallback, not abstract-level screening")

    details["lane_counts"] = dict(sorted(lane_counts.items()))
    details["decision_counts"] = dict(sorted(decision_counts.items()))
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(audit_path),
        "scorecard_path": str(scorecard_path),
        "row_count": len(rows),
        "expected_candidate_count": expected,
        "abstract_present_count": abstract_present_count,
        "abstract_missing_count": abstract_missing_count,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--audit", default="papernexus/ABSTRACT_SCREENING_AUDIT.json")
    parser.add_argument("--scorecard", default="papernexus/PAPER_SELECTION_SCORECARD.json")
    args = parser.parse_args()
    out = lint(args.project, args.audit, args.scorecard)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
