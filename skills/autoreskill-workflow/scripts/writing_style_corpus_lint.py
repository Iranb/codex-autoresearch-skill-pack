#!/usr/bin/env python3
"""Lint CCF-A/top-tier writing-style corpus audit artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ARTIFACTS = [
    "writing_style/WRITING_STYLE_CORPUS_PLAN.json",
    "writing_style/RAW_SOURCE_HARVEST.jsonl",
    "writing_style/STYLE_CANDIDATE_LEDGER.json",
    "writing_style/CORPUS_SCOPE_AUDIT.json",
    "writing_style/PRESENTATION_TYPE_NORMALIZATION.json",
    "writing_style/AWARD_SOURCE_AUDIT.json",
    "writing_style/FULLTEXT_COVERAGE_AUDIT.json",
    "writing_style/RHETORICAL_MOVE_ANNOTATION.json",
    "writing_style/EVIDENCE_SYNTHESIS.json",
    "writing_style/WRITING_STYLE_REPORT.md",
]

WRITING_STYLE_TOKENS = (
    "writing-style",
    "writing style",
    "papers.cool",
    "ccf-a",
    "ccfa",
    "oral",
    "spotlight",
    "best paper",
    "award",
    "rhetorical",
    "style corpus",
    "写作",
    "最佳论文",
    "风格",
)

MANUSCRIPT_TOKENS = (
    "manuscript",
    "paper revision",
    "polish",
    "revise my paper",
    "writing audit",
    "润色",
    "修改论文",
)

ALLOWED_EVIDENCE_TIERS = {"observed_corpus", "sample_fulltext", "expert_heuristic"}
AWARD_UNVERIFIED = {"secondary_only", "ambiguous", "unmatched", "not_checked"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


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


def read_jsonl(path: Path, base: Path, missing: list[str], warnings: list[str]) -> list[dict[str, Any]]:
    label = rel(base, path)
    if not path.exists():
        missing.append(label)
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            missing.append(f"{label}:{line_no} invalid JSON at column {exc.colno}")
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            warnings.append(f"{label}:{line_no} is not a JSON object")
    if not rows:
        missing.append(f"{label} at least one raw source row")
    return rows


def rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def has_any(obj: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(present(obj.get(field)) for field in fields)


def contains_token(text: str, token: str) -> bool:
    if token.isascii():
        return re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text) is not None
    return token in text


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


def audit_required(base: Path) -> bool:
    if any((base / rel_path).exists() for rel_path in ARTIFACTS):
        return True
    text = goal_text(base).lower()
    return any(contains_token(text, token) for token in WRITING_STYLE_TOKENS)


def manuscript_revision_required(base: Path) -> bool:
    if (base / "paper/CCFA_WRITING_AUDIT.md").exists():
        return True
    text = goal_text(base).lower()
    return any(contains_token(text, token) for token in MANUSCRIPT_TOKENS)


def require_any(obj: dict[str, Any], fields: tuple[str, ...], label: str, missing: list[str]) -> None:
    if not has_any(obj, fields):
        missing.append(f"{label} {' or '.join(fields)}")


def lint_plan(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/WRITING_STYLE_CORPUS_PLAN.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        return
    if not isinstance(payload, dict):
        missing.append("writing_style/WRITING_STYLE_CORPUS_PLAN.json must be a JSON object")
        return
    require_any(payload, ("analysis_questions", "questions"), rel(base, path), missing)
    require_any(payload, ("target_venues", "venue_scope"), rel(base, path), missing)
    require_any(payload, ("source_priority", "sources"), rel(base, path), missing)
    require_any(payload, ("harvest_queries", "harvest_sources", "source_urls"), rel(base, path), missing)
    require_any(payload, ("inclusion_rules", "inclusion_criteria"), rel(base, path), missing)
    require_any(payload, ("exclusion_rules", "exclusion_criteria"), rel(base, path), missing)
    require_any(payload, ("sample_strategy", "sampling_strategy"), rel(base, path), missing)
    if not has_any(payload, ("ccf_source_url", "ccf_source")):
        warnings.append("writing_style/WRITING_STYLE_CORPUS_PLAN.json should pin ccf_source_url for CCF-A audits")
    details["plan_loaded"] = True


def lint_raw_harvest(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "writing_style/RAW_SOURCE_HARVEST.jsonl"
    raw_rows = read_jsonl(path, base, missing, warnings)
    details["raw_source_rows"] = len(raw_rows)
    ids: set[str] = set()
    for index, row in enumerate(raw_rows):
        prefix = f"writing_style/RAW_SOURCE_HARVEST.jsonl row[{index}]"
        paper_id = row.get("paper_id") or row.get("id") or row.get("stable_id")
        if present(paper_id):
            ids.add(str(paper_id))
        else:
            warnings.append(f"{prefix}.paper_id or stable id")
        if not present(row.get("title")):
            missing.append(f"{prefix}.title")
        if not has_any(row, ("source_url", "source_name", "source")):
            missing.append(f"{prefix}.source_url or source_name")
        if not has_any(row, ("venue_id", "venue_family", "venue")):
            warnings.append(f"{prefix}.venue_id or venue_family")
    return ids


def lint_candidate_ledger(base: Path, raw_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> set[str]:
    path = base / "writing_style/STYLE_CANDIDATE_LEDGER.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["candidate_count"] = 0
        return set()
    candidate_rows = rows(payload, ("candidates", "papers", "rows"))
    details["candidate_count"] = len(candidate_rows)
    if not candidate_rows:
        missing.append("writing_style/STYLE_CANDIDATE_LEDGER.json candidates[]")
        return set()
    ids: set[str] = set()
    for index, row in enumerate(candidate_rows):
        prefix = f"writing_style/STYLE_CANDIDATE_LEDGER.json candidates[{index}]"
        paper_id = row.get("paper_id") or row.get("id") or row.get("stable_id")
        if present(paper_id):
            ids.add(str(paper_id))
            if raw_ids and str(paper_id) not in raw_ids and not present(row.get("source_row_refs")):
                warnings.append(f"{prefix}.paper_id not found in raw harvest and has no source_row_refs")
        else:
            missing.append(f"{prefix}.paper_id")
        for field in ("title", "year"):
            if not present(row.get(field)):
                missing.append(f"{prefix}.{field}")
        if not has_any(row, ("venue_family", "venue_id", "venue")):
            missing.append(f"{prefix}.venue_family or venue_id")
        if not present(row.get("candidate_role")):
            warnings.append(f"{prefix}.candidate_role")
        if not present(row.get("inclusion_decision")):
            missing.append(f"{prefix}.inclusion_decision")
        if not present(row.get("decision_reason")):
            warnings.append(f"{prefix}.decision_reason")
    return ids


def lint_scope(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/CORPUS_SCOPE_AUDIT.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        return
    if not isinstance(payload, dict):
        missing.append("writing_style/CORPUS_SCOPE_AUDIT.json must be a JSON object")
        return
    require_any(payload, ("included_venue_families", "included_venues"), rel(base, path), missing)
    require_any(payload, ("year_coverage", "years"), rel(base, path), missing)
    require_any(payload, ("generalization_limits", "claim_limits"), rel(base, path), missing)
    if not has_any(payload, ("ccf_source_url", "ccf_source")):
        warnings.append("writing_style/CORPUS_SCOPE_AUDIT.json should record ccf_source_url")
    if not has_any(payload, ("excluded_venue_families", "missing_venue_families", "excluded_venues")):
        warnings.append("writing_style/CORPUS_SCOPE_AUDIT.json should record excluded or missing venue families")
    details["scope_loaded"] = True


def lint_presentation(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/PRESENTATION_TYPE_NORMALIZATION.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["presentation_label_count"] = 0
        return
    label_rows = rows(payload, ("labels", "normalizations", "rows"))
    details["presentation_label_count"] = len(label_rows)
    if not label_rows:
        missing.append("writing_style/PRESENTATION_TYPE_NORMALIZATION.json labels[]")
        return
    for index, row in enumerate(label_rows):
        prefix = f"writing_style/PRESENTATION_TYPE_NORMALIZATION.json labels[{index}]"
        require_any(row, ("source_name", "source_url", "source"), prefix, missing)
        require_any(row, ("raw_label", "source_label"), prefix, missing)
        if not present(row.get("normalized_label")):
            missing.append(f"{prefix}.normalized_label")
        require_any(row, ("normalization_basis", "evidence_source", "basis"), prefix, missing)
        if not present(row.get("confidence")):
            warnings.append(f"{prefix}.confidence")


def lint_awards(base: Path, candidate_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/AWARD_SOURCE_AUDIT.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["award_rows"] = 0
        return
    award_rows = rows(payload, ("awards", "rows", "matches"))
    details["award_rows"] = len(award_rows)
    if not award_rows:
        if isinstance(payload, dict) and payload.get("award_claims_in_scope") is False:
            return
        warnings.append("writing_style/AWARD_SOURCE_AUDIT.json has no award rows; set award_claims_in_scope=false if intentional")
        return
    verified = 0
    for index, row in enumerate(award_rows):
        prefix = f"writing_style/AWARD_SOURCE_AUDIT.json awards[{index}]"
        require_any(row, ("award_name", "award_text"), prefix, missing)
        require_any(row, ("candidate_paper_id", "paper_id"), prefix, missing)
        require_any(row, ("candidate_title", "title", "matched_title"), prefix, missing)
        status = normalized(row.get("verification_status") or row.get("status"))
        if not status:
            missing.append(f"{prefix}.verification_status")
        elif status not in AWARD_UNVERIFIED:
            verified += 1
            if not has_any(row, ("official_source_url", "source_url")):
                warnings.append(f"{prefix} verified without official_source_url/source_url")
        if candidate_ids and present(row.get("candidate_paper_id")) and str(row.get("candidate_paper_id")) not in candidate_ids:
            warnings.append(f"{prefix}.candidate_paper_id not found in candidate ledger")
        if not present(row.get("claim_limit")):
            warnings.append(f"{prefix}.claim_limit")
    details["verified_award_rows"] = verified


def lint_fulltext(base: Path, candidate_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/FULLTEXT_COVERAGE_AUDIT.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["fulltext_rows"] = 0
        return
    fulltext_rows = rows(payload, ("papers", "rows", "coverage"))
    details["fulltext_rows"] = len(fulltext_rows)
    if not fulltext_rows:
        missing.append("writing_style/FULLTEXT_COVERAGE_AUDIT.json rows[]")
        return
    parsed = 0
    for index, row in enumerate(fulltext_rows):
        prefix = f"writing_style/FULLTEXT_COVERAGE_AUDIT.json rows[{index}]"
        require_any(row, ("paper_id", "title"), prefix, missing)
        require_any(row, ("pdf_url", "fulltext_url", "source_url"), prefix, warnings)
        require_any(row, ("download_status", "fulltext_status"), prefix, missing)
        require_any(row, ("extraction_status", "extraction_quality"), prefix, missing)
        if normalized(row.get("extraction_status")) in {"parsed", "complete", "full"}:
            parsed += 1
        if candidate_ids and present(row.get("paper_id")) and str(row.get("paper_id")) not in candidate_ids:
            warnings.append(f"{prefix}.paper_id not found in candidate ledger")
        if not present(row.get("claim_limit")):
            warnings.append(f"{prefix}.claim_limit")
    details["parsed_fulltext_rows"] = parsed
    if parsed == 0:
        warnings.append("No parsed full-text rows; section-level writing claims must be disabled or source-limited")


def lint_annotations(base: Path, candidate_ids: set[str], missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/RHETORICAL_MOVE_ANNOTATION.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["annotation_rows"] = 0
        return
    if isinstance(payload, dict):
        if not present(payload.get("annotation_codebook_version")):
            warnings.append("writing_style/RHETORICAL_MOVE_ANNOTATION.json annotation_codebook_version")
        if not present(payload.get("sample_strategy")):
            missing.append("writing_style/RHETORICAL_MOVE_ANNOTATION.json sample_strategy")
    annotation_rows = rows(payload, ("rows", "annotations", "moves"))
    details["annotation_rows"] = len(annotation_rows)
    if not annotation_rows:
        missing.append("writing_style/RHETORICAL_MOVE_ANNOTATION.json rows[]")
        return
    tiers: dict[str, int] = {}
    for index, row in enumerate(annotation_rows):
        prefix = f"writing_style/RHETORICAL_MOVE_ANNOTATION.json rows[{index}]"
        require_any(row, ("paper_id", "title"), prefix, missing)
        if not present(row.get("section")):
            missing.append(f"{prefix}.section")
        require_any(row, ("move", "rhetorical_move"), prefix, missing)
        require_any(row, ("evidence_basis", "span", "sentence_id", "paragraph_id", "note"), prefix, missing)
        tier = normalized(row.get("evidence_tier"))
        if not tier:
            warnings.append(f"{prefix}.evidence_tier")
        elif tier not in ALLOWED_EVIDENCE_TIERS:
            warnings.append(f"{prefix}.evidence_tier unknown: {tier}")
        tiers[tier or "missing"] = tiers.get(tier or "missing", 0) + 1
        if candidate_ids and present(row.get("paper_id")) and str(row.get("paper_id")) not in candidate_ids:
            warnings.append(f"{prefix}.paper_id not found in candidate ledger")
    details["annotation_evidence_tiers"] = tiers


def lint_synthesis(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/EVIDENCE_SYNTHESIS.json"
    payload = read_artifact_json(path, base, missing)
    if payload is None:
        details["synthesis_rows"] = 0
        return
    synthesis_rows = rows(payload, ("findings", "rows", "synthesis"))
    details["synthesis_rows"] = len(synthesis_rows)
    if not synthesis_rows:
        missing.append("writing_style/EVIDENCE_SYNTHESIS.json findings[]")
        return
    for index, row in enumerate(synthesis_rows):
        prefix = f"writing_style/EVIDENCE_SYNTHESIS.json findings[{index}]"
        require_any(row, ("finding_id", "id"), prefix, warnings)
        require_any(row, ("finding", "pattern", "recommendation"), prefix, missing)
        tier = normalized(row.get("evidence_tier"))
        if not tier:
            missing.append(f"{prefix}.evidence_tier")
        elif tier not in ALLOWED_EVIDENCE_TIERS:
            warnings.append(f"{prefix}.evidence_tier unknown: {tier}")
        require_any(row, ("supporting_artifact_refs", "supporting_rows", "evidence_refs"), prefix, missing)
        require_any(row, ("claim_limit", "generalization_limit"), prefix, missing)
        require_any(row, ("manuscript_check", "writing_check"), prefix, missing)


def lint_report(base: Path, missing: list[str], warnings: list[str], details: dict[str, Any]) -> None:
    path = base / "writing_style/WRITING_STYLE_REPORT.md"
    text = read_text(path)
    if not text.strip():
        missing.append(rel(base, path))
        return
    details["report_chars"] = len(text)
    required_terms = ["scope", "coverage", "evidence", "claim"]
    lower = text.lower()
    for term in required_terms:
        if term not in lower:
            warnings.append(f"writing_style/WRITING_STYLE_REPORT.md should mention {term}")


def lint_ccfa_writing_audit(base: Path, required: bool, warnings: list[str], missing: list[str], details: dict[str, Any]) -> None:
    path = base / "paper/CCFA_WRITING_AUDIT.md"
    text = read_text(path)
    if not text.strip():
        if required:
            missing.append(rel(base, path))
        else:
            warnings.append("paper/CCFA_WRITING_AUDIT.md missing; required when manuscript revision/polishing is requested")
        return
    details["ccfa_writing_audit_chars"] = len(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint CCF-A/top-tier writing-style corpus audit artifacts.")
    parser.add_argument("--project", required=True, help="Project root containing .autoreskill")
    parser.add_argument("--required", action="store_true", help="Fail if writing-style audit artifacts are absent")
    args = parser.parse_args()

    base = ar(args.project)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"base": str(base)}

    required = args.required or audit_required(base)
    details["required"] = required
    if not required:
        print(json.dumps({"status": "not_required", "details": details}, indent=2, ensure_ascii=False))
        return 0

    raw_ids = lint_raw_harvest(base, missing, warnings, details)
    candidate_ids = lint_candidate_ledger(base, raw_ids, missing, warnings, details)
    lint_plan(base, missing, warnings, details)
    lint_scope(base, missing, warnings, details)
    lint_presentation(base, missing, warnings, details)
    lint_awards(base, candidate_ids, missing, warnings, details)
    lint_fulltext(base, candidate_ids, missing, warnings, details)
    lint_annotations(base, candidate_ids, missing, warnings, details)
    lint_synthesis(base, missing, warnings, details)
    lint_report(base, missing, warnings, details)
    lint_ccfa_writing_audit(base, manuscript_revision_required(base), warnings, missing, details)

    status = "pass" if not missing else "fail"
    print(json.dumps(
        {
            "status": status,
            "missing": missing,
            "warnings": warnings,
            "details": details,
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
