#!/usr/bin/env python3
"""Lint PaperNexus graph/material import plans before submission."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


LANES = {"target_domain", "near_neighbor", "far_neighbor"}
IMPORT_ACTIONS = {"import", "supplement"}
STABLE_ID_FIELDS = {"idempotency_key", "paper_ref", "canonicalId", "canonical_id", "doi", "arxivId", "arxiv_id", "pmid", "pmcid"}
SOURCE_FIELDS = {"pdfUrl", "pdf_url", "sourcePath", "source_path", "serverFilePath", "server_file_path", "markdownPath", "markdown_path", "openAccessUrl", "open_access_url"}
STABLE_REF_RE = re.compile(
    r"^(doi|arxiv|arxivid|pmid|pmcid|canonical|openalex|s2|semantic|corpusid|corpus|paper):\S+",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
IMPORT_WORKFLOW_KEY_FIELDS = {
    "submittedImportKeys",
    "submitted_import_keys",
    "completedImportKeys",
    "completed_import_keys",
    "authoritativeSyncCompletedKeys",
    "authoritative_sync_completed_keys",
    "authoritativeSyncCompletedImportKeys",
    "authoritative_sync_completed_import_keys",
    "syncedImportKeys",
    "synced_import_keys",
}
SOURCE_LIMITED_KEY_FIELDS = {
    "source_limited_exception_keys",
    "sourceLimitedExceptionKeys",
    "source_unavailable_keys",
    "sourceUnavailableKeys",
    "sourcepath_required_keys",
    "sourcepathRequiredKeys",
    "claim_limited_missing_keys",
    "claimLimitedMissingKeys",
    "parked_keys",
    "parkedKeys",
    "approved_parked_keys",
    "approvedParkedKeys",
}
SOURCE_LIMITED_ROW_FIELDS = {
    "source_limited_exceptions",
    "sourceLimitedExceptions",
    "sourcepath_required_rows",
    "sourcepathRequiredRows",
    "metadata_only_candidates_not_counted",
    "remaining_rows",
    "remainingRows",
    "blocked_rows",
    "blockedRows",
    "records",
    "exceptions",
}
SOURCE_LIMITED_MARKERS = {
    "metadata_only_no_import_not_counted",
    "metadata_only",
    "needs_institution",
    "sourcepath_required",
    "source_unavailable",
    "no open pdf",
    "no open full text",
    "no server-acceptable pdf",
    "no server-acceptable sourcepath",
}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def iter_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            found.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def flattened(value: Any) -> list[Any]:
    if isinstance(value, list):
        out: list[Any] = []
        for item in value:
            out.extend(flattened(item))
        return out
    return [value]


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def papers(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("selected_papers"), list):
        return [row for row in payload["selected_papers"] if isinstance(row, dict)]
    return []


def stable_ref(value: Any, *, loose: bool = False) -> bool:
    if not present(value):
        return False
    text = str(value).strip()
    if STABLE_REF_RE.match(text) or DOI_RE.match(text):
        return True
    return loose and bool(re.fullmatch(r"[A-Za-z0-9_.:/-]{6,}", text))


def has_stable_identifier(row: dict[str, Any]) -> bool:
    direct_fields = ["doi", "arxivId", "arxiv_id", "pmid", "pmcid", "canonicalId", "canonical_id"]
    if any(stable_ref(row.get(key), loose=True) for key in direct_fields):
        return True
    return any(stable_ref(row.get(key)) for key in ["idempotency_key", "paper_ref"])


def key_variants(kind: str, value: Any) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    raw = value.strip()
    low = raw.lower()
    variants = {raw}
    if kind in {"idempotency_key", "paper_ref", "canonicalId", "canonical_id"}:
        if not raw.startswith("idempotency_key:"):
            variants.add(f"idempotency_key:{raw}")
        return variants
    if kind == "doi":
        variants.update({low, f"doi:{low}", f"idempotency_key:doi:{low}"})
    elif kind in {"arxivId", "arxiv_id"}:
        variants.update({f"arxivId:{raw}", f"idempotency_key:arxivId:{raw}"})
    elif kind in {"pmid", "pmcid"}:
        variants.update({f"{kind}:{raw}", f"idempotency_key:{kind}:{raw}"})
    else:
        variants.add(f"{kind}:{raw}")
    return variants


def row_key_variants(row: dict[str, Any]) -> set[str]:
    variants: set[str] = set()
    for key in ["idempotency_key", "paper_ref", "canonicalId", "canonical_id", "doi", "arxivId", "arxiv_id", "pmid", "pmcid"]:
        variants.update(key_variants(key, row.get(key)))
    return variants


def explicit_key_set(payload: Any, keys: set[str]) -> set[str]:
    out: set[str] = set()
    if not isinstance(payload, dict):
        return out
    for row in iter_dicts(payload):
        for key in keys:
            for value in flattened(row.get(key)):
                if isinstance(value, str) and value.strip():
                    out.add(value.strip())
    return out


def source_limited_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ["status", "state", "decision", "reason", "diagnosis", "source_status", "sourceStatus", "fullTextStatus", "sourceKind"]:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip().lower())
    return " ".join(parts)


def closed_or_exception_keys(base: Path) -> tuple[set[str], set[str]]:
    """Return import keys already accepted by PaperNexus and approved source-limited exceptions."""

    import_status = read_json(base / "papernexus/IMPORT_WORKFLOW_STATUS.json")
    decision = read_json(base / "graph/GRAPH_BUILD_DECISION.json")
    source_status = read_json(base / "papernexus/SOURCE_DISCOVERY_REPAIR_STATUS.json")
    debt_status = read_json(base / "papernexus/GRAPH_IMPORT_DEBT_REPAIR_STATUS.json")

    closed = explicit_key_set(import_status, IMPORT_WORKFLOW_KEY_FIELDS)
    exceptions: set[str] = set()
    for payload in [import_status, decision, source_status, debt_status]:
        if not isinstance(payload, dict):
            continue
        exceptions.update(explicit_key_set(payload, SOURCE_LIMITED_KEY_FIELDS))
        for row in iter_dicts(payload):
            for rows_key in SOURCE_LIMITED_ROW_FIELDS:
                rows = row.get(rows_key)
                if not isinstance(rows, list):
                    continue
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    text = source_limited_text(item)
                    if any(marker in text for marker in SOURCE_LIMITED_MARKERS):
                        exceptions.update(row_key_variants(item))
    return closed, exceptions


def has_server_visible_source(row: dict[str, Any]) -> bool:
    if any(present(row.get(key)) for key in SOURCE_FIELDS):
        return True
    sources = row.get("sources")
    if isinstance(sources, list):
        return any(isinstance(item, dict) and any(present(item.get(key)) for key in SOURCE_FIELDS | {"url", "path"}) for item in sources)
    if isinstance(sources, dict):
        return any(present(sources.get(key)) for key in SOURCE_FIELDS | {"url", "path"})
    return False


def lint(project: str, rel: str) -> dict[str, Any]:
    base = ar(project)
    path = base / rel
    payload = read_json(path)
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": [rel], "warnings": [], "path": str(path)}
    rows = papers(payload)
    closed_keys, exception_keys = closed_or_exception_keys(base)
    if not rows:
        missing.append("selected_papers")
    lane_seen: set[str] = set()
    role_seen: set[str] = set()
    idempotency_keys: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"selected_papers[{index}]"
        lane = str(row.get("lane") or "").strip()
        if lane not in LANES:
            missing.append(f"{prefix}.lane")
        else:
            lane_seen.add(lane)
        roles = row.get("roles") if isinstance(row.get("roles"), list) else []
        if not roles:
            missing.append(f"{prefix}.roles")
        role_seen.update(str(role) for role in roles)
        for key in ["paper_ref", "title", "selection_reason", "source_resolution_status", "import_action"]:
            if not present(row.get(key)):
                missing.append(f"{prefix}.{key}")
        action = str(row.get("import_action") or "")
        if action not in {"import", "supplement", "material_view", "skip_existing"}:
            missing.append(f"{prefix}.import_action import/supplement/material_view/skip_existing")
        if action in IMPORT_ACTIONS:
            if not has_stable_identifier(row):
                missing.append(f"{prefix}.stable_identifier doi/arxiv/pmid/pmcid/canonical_id/paper_ref/idempotency_key")
            row_keys = row_key_variants(row)
            already_accepted = bool(row_keys & closed_keys)
            source_limited = bool(row_keys & exception_keys)
            if not has_server_visible_source(row) and not already_accepted and not source_limited:
                missing.append(f"{prefix}.server_visible_source pdfUrl/sourcePath/serverFilePath/markdownPath/openAccessUrl")
        idem = str(row.get("idempotency_key") or "").strip()
        if idem:
            if idem in idempotency_keys:
                missing.append(f"{prefix}.idempotency_key duplicate")
            idempotency_keys.add(idem)
    missing_lanes = sorted(LANES - lane_seen)
    if missing_lanes:
        missing.append("selected_papers missing lanes: " + ", ".join(missing_lanes))
    for key in ["lane_balance", "role_balance", "import_batches", "material_requests", "split_reading_requests", "blocked_papers", "idempotency_keys"]:
        if key not in payload:
            missing.append(key)
    if not ({"closest_prior", "baseline_protocol", "mechanism", "limitation_future", "negative_evidence"} & role_seen):
        warnings.append("selected roles do not include the core evidence roles; split-reading gate will likely fail")
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(path),
        "selected_paper_count": len(rows),
        "lanes": sorted(lane_seen),
        "roles": sorted(role_seen),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", default="papernexus/GRAPH_IMPORT_PLAN.json")
    args = parser.parse_args()
    out = lint(args.project, args.plan)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
