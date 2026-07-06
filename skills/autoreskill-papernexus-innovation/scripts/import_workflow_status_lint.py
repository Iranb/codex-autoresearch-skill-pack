#!/usr/bin/env python3
"""Lint PaperNexus import_workflow queue/status/wait evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


COMPLETE_STATUSES = {"complete", "completed", "ready", "succeeded", "success", "graph_visible", "semantic_complete"}
FAILED_STATUSES = {"failed", "error", "errored", "cancelled", "canceled"}
PENDING_STATUSES = {"pending", "queued", "running", "processing", "in_progress", "submitted", "waiting"}
AUTHORITATIVE_OK = {"complete", "completed", "ready", "succeeded", "success", "synced", "superseded", "not_required", "none", "skipped"}
IMPORT_ACTIONS = {"import", "supplement"}
SOURCE_LIMITED_PARENT_MARKERS = {
    "sourcepath_required",
    "source_unavailable",
    "source_discovery_exhausted",
    "external_source_blocker",
    "external_papernexus_source_blocker",
}
SOURCE_LIMITED_ROW_MARKERS = {
    "metadata_only_no_import_not_counted",
    "metadata_only",
    "needs_institution",
    "sourcepath_required",
    "source_unavailable",
    "no open pdf",
    "no open full text",
    "no server-acceptable pdf",
    "no server-acceptable sourcepath",
    "no papernexus-downloadable full text",
}
SOURCE_LIMITED_KEY_FIELDS = {
    "source_unavailable_keys",
    "sourceUnavailableKeys",
    "sourcepath_required_keys",
    "sourcepathRequiredKeys",
    "source_limited_exception_keys",
    "sourceLimitedExceptionKeys",
    "claim_limited_missing_keys",
    "claimLimitedMissingKeys",
    "parked_keys",
    "parkedKeys",
    "approved_parked_keys",
    "approvedParkedKeys",
}
SOURCE_LIMITED_ROW_FIELDS = {
    "remaining_rows",
    "remainingRows",
    "blocked_rows",
    "blockedRows",
    "source_discovery_records",
    "sourceDiscoveryRecords",
    "source_limited_exceptions",
    "sourceLimitedExceptions",
    "records",
    "exceptions",
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


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalize_state(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def first_state(*values: Any) -> str:
    for value in values:
        state = normalize_state(value)
        if state:
            return state
    return ""


def unwrap_payload(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
        nested = payload["payload"]
        if any(key in nested for key in ["tasks", "queueSummary", "summary", "task", "result"]):
            return nested
    return payload


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


def flattened(values: Any) -> list[Any]:
    if values is None:
        return []
    if isinstance(values, list):
        out: list[Any] = []
        for value in values:
            out.extend(flattened(value))
        return out
    return [values]


def task_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in ["tasks", "task", "relevantTasks", "relevant_tasks", "targetTasks", "target_tasks", "selectedTasks", "selected_tasks"]:
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
        elif isinstance(value, dict):
            rows.append(value)
    for key in ["result", "data", "response"]:
        value = payload.get(key)
        if isinstance(value, dict):
            rows.extend(task_rows(value))
    unique: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for row in rows:
        task_id = str(row.get("id") or row.get("taskId") or row.get("task_id") or "").strip()
        if task_id:
            unique[task_id] = row
        else:
            anonymous.append(row)
    return [*unique.values(), *anonymous]


def explicit_task_ids(payload: Any) -> set[str]:
    keys = {
        "taskId",
        "task_id",
        "taskIds",
        "task_ids",
        "selectedTaskIds",
        "selected_task_ids",
        "submittedTaskIds",
        "submitted_task_ids",
        "relevantTaskIds",
        "relevant_task_ids",
    }
    ids: set[str] = set()
    if not isinstance(payload, dict):
        return ids
    for row in iter_dicts(payload):
        for key in keys:
            for value in flattened(row.get(key)):
                if isinstance(value, str) and value.strip():
                    ids.add(value.strip())
    return ids


def batch_ids(payload: Any) -> set[str]:
    ids: set[str] = set()
    for row in iter_dicts(payload):
        for key in ["batchId", "batch_id"]:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                ids.add(value.strip())
    return ids


def queue_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ["queueSummary", "queue_summary", "summary"]:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def state_values(payload: Any, keys: set[str]) -> list[str]:
    states: list[str] = []
    for row in iter_dicts(payload):
        for key in keys:
            value = row.get(key)
            if isinstance(value, dict):
                status = first_state(value.get("status"), value.get("state"), value.get("stage"))
            else:
                status = normalize_state(value)
            if status:
                states.append(status)
    return states


def authoritative_sync_states(payload: Any) -> list[str]:
    states = state_values(payload, {"authoritativeSyncStatus", "authoritative_sync_status", "authoritativeSyncState", "authoritative_sync_state"})
    for row in iter_dicts(payload):
        value = row.get("authoritativeSync") or row.get("authoritative_sync")
        if isinstance(value, dict):
            status = first_state(value.get("status"), value.get("state"), value.get("stage"))
            if status:
                states.append(status)
    return states


def graph_visibility_states(payload: Any) -> list[str]:
    return state_values(payload, {"graphVisibilityStatus", "graph_visibility_status", "graphVisibility", "graph_visible"})


def semantic_states(payload: Any) -> list[str]:
    return state_values(payload, {"semanticStatus", "semantic_status", "semantic"})


def wait_states(payload: Any) -> list[str]:
    return state_values(payload, {"waitStatus", "wait_status", "waitState", "wait_state"})


def missing_task_ids(payload: Any) -> set[str]:
    return explicit_key_set(payload, {"missingTaskIds", "missing_task_ids", "missingTasks", "missing_tasks"})


def stable_paper_key(row: dict[str, Any]) -> str:
    for key in ["idempotency_key", "paper_ref", "canonicalId", "canonical_id", "doi", "arxivId", "arxiv_id", "pmid", "pmcid"]:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return f"{key}:{value.strip()}"
    title = row.get("title")
    return f"title:{title.strip()}" if isinstance(title, str) and title.strip() else ""


def paper_key_variants(kind: str, value: Any) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    raw = value.strip()
    if kind in {"idempotency_key", "paper_ref", "canonicalId", "canonical_id"}:
        return {raw}
    if kind in {"doi", "pmid", "pmcid", "isbn", "issn"}:
        raw = raw.lower()
        canonical = kind
    elif kind in {"arxivId", "arxiv_id"}:
        canonical = "arxivId"
    else:
        canonical = kind
    return {f"{canonical}:{raw}", f"idempotency_key:{canonical}:{raw}"}


def source_limited_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    for key in [
        "status",
        "state",
        "decision",
        "reason",
        "diagnosis",
        "current_blocker",
        "next_action",
        "failure_class",
        "source_status",
        "sourceStatus",
        "fullTextStatus",
        "sourceKind",
    ]:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            parts.append(item.strip().lower())
    return " ".join(parts)


def source_limited_exception_keys(base: Path, payload: Any, planned_keys: list[str]) -> tuple[set[str], list[str]]:
    planned = set(planned_keys)
    out: set[str] = set()
    sources: list[tuple[str, Any]] = [
        ("IMPORT_WORKFLOW_STATUS", payload),
        ("SOURCE_DISCOVERY_REPAIR_STATUS", read_json(base / "papernexus/SOURCE_DISCOVERY_REPAIR_STATUS.json")),
        ("GRAPH_IMPORT_DEBT_REPAIR_STATUS", read_json(base / "papernexus/GRAPH_IMPORT_DEBT_REPAIR_STATUS.json")),
        ("GRAPH_BUILD_DECISION", read_json(base / "graph/GRAPH_BUILD_DECISION.json")),
    ]
    source_names: list[str] = []

    for source_name, source in sources:
        if not isinstance(source, dict):
            continue
        parent_text = source_limited_text(source)
        parent_allows = any(marker in parent_text for marker in SOURCE_LIMITED_PARENT_MARKERS)
        source_added = False

        for row in iter_dicts(source):
            for key in SOURCE_LIMITED_KEY_FIELDS:
                for value in flattened(row.get(key)):
                    if isinstance(value, str) and value.strip():
                        variants = {value.strip()}
                        if value.strip().startswith("doi:"):
                            variants.add("idempotency_key:" + value.strip())
                        out.update(variants & planned)
                        source_added = source_added or bool(variants & planned)

        for rows_key in SOURCE_LIMITED_ROW_FIELDS:
            rows = source.get(rows_key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_text = source_limited_text(row)
                row_allows = parent_allows or any(marker in row_text for marker in SOURCE_LIMITED_ROW_MARKERS)
                if not row_allows:
                    continue
                variants: set[str] = set()
                for ident_key in [
                    "idempotency_key",
                    "paper_ref",
                    "canonicalId",
                    "canonical_id",
                    "doi",
                    "arxivId",
                    "arxiv_id",
                    "pmid",
                    "pmcid",
                    "isbn",
                    "issn",
                ]:
                    variants.update(paper_key_variants(ident_key, row.get(ident_key)))
                matched = variants & planned
                out.update(matched)
                source_added = source_added or bool(matched)

        if source_added:
            source_names.append(source_name)

    return out, sorted(set(source_names))


def plan_required_import_keys(base: Path) -> list[str]:
    plan = read_json(base / "papernexus/GRAPH_IMPORT_PLAN.json")
    if not isinstance(plan, dict):
        return []
    explicit = plan.get("required_graph_import_keys")
    if isinstance(explicit, list) and explicit:
        return sorted({str(item).strip() for item in explicit if str(item).strip()})
    keys: list[str] = []
    for row in plan.get("selected_papers") or []:
        if isinstance(row, dict) and str(row.get("import_action") or "") in IMPORT_ACTIONS:
            key = stable_paper_key(row)
            if key:
                keys.append(key)
    if not keys:
        for batch in plan.get("import_batches") or []:
            batch_rows = batch if isinstance(batch, list) else [batch]
            for row in batch_rows:
                if isinstance(row, dict) and str(row.get("import_action") or "") in IMPORT_ACTIONS:
                    key = stable_paper_key(row)
                    if key:
                        keys.append(key)
    return sorted(set(keys))


def planned_import_count(base: Path) -> int:
    return len(plan_required_import_keys(base))


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


def explicit_int(payload: Any, keys: set[str]) -> int | None:
    if not isinstance(payload, dict):
        return None
    values: list[int] = []
    for row in iter_dicts(payload):
        for key in keys:
            value = row.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                values.append(value)
            elif isinstance(value, float) and value.is_integer():
                values.append(int(value))
            elif isinstance(value, str) and value.strip().isdigit():
                values.append(int(value.strip()))
    return max(values) if values else None


def terminal_flag(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    truthy_keys = ["graph_visible", "graphVisible", "graph_ready", "graphReady", "complete", "completed"]
    if any(payload.get(key) is True for key in truthy_keys):
        return True
    status = first_state(payload.get("status"), payload.get("state"), payload.get("waitStatus"), payload.get("graphVisibilityStatus"))
    if status in COMPLETE_STATUSES:
        return True
    result = payload.get("result")
    return isinstance(result, dict) and terminal_flag(result)


def lint(project: str, rel: str) -> dict[str, Any]:
    base = ar(project)
    path = base / rel
    payload = unwrap_payload(read_json(path))
    legacy_path = base / "papernexus/GRAPH_IMPORT_STATUS.json"
    if payload is None and rel != "papernexus/GRAPH_IMPORT_STATUS.json":
        payload = unwrap_payload(read_json(legacy_path))
        path = legacy_path

    missing: list[str] = []
    warnings: list[str] = []
    planned_keys = plan_required_import_keys(base)
    details: dict[str, Any] = {
        "path": str(path),
        "planned_import_count": len(planned_keys),
        "planned_import_keys": planned_keys,
        "effective_planned_import_count": len(planned_keys),
        "source_limited_exception_count": 0,
        "source_limited_exception_keys": [],
        "source_limited_exception_sources": [],
        "task_ids": [],
        "batch_ids": [],
        "authoritative_sync_statuses": [],
        "graph_visibility_statuses": [],
        "semantic_statuses": [],
        "wait_statuses": [],
        "missing_task_ids": [],
        "submitted_import_count": 0,
        "completed_import_count": 0,
        "authoritative_sync_completed_count": 0,
        "missing_unsubmitted_keys": [],
        "missing_incomplete_keys": [],
        "missing_unsynced_keys": [],
        "queue_summary": {},
    }

    if details["planned_import_count"] == 0:
        return {
            "complete": True,
            "status": "not_required",
            "missing": [],
            "warnings": ["GRAPH_IMPORT_PLAN has no import/supplement actions requiring import_workflow tracking"],
            "details": details,
        }
    if not isinstance(payload, dict):
        return {
            "complete": False,
            "status": "incomplete",
            "missing": [f"{rel} with import_workflow queue_progress/status/wait result"],
            "warnings": [],
            "details": details,
        }

    source_exceptions, source_exception_sources = source_limited_exception_keys(base, payload, planned_keys)
    source_exceptions &= set(planned_keys)
    details["source_limited_exception_keys"] = sorted(source_exceptions)
    details["source_limited_exception_count"] = len(source_exceptions)
    details["source_limited_exception_sources"] = source_exception_sources
    details["effective_planned_import_count"] = len(set(planned_keys) - source_exceptions)

    tasks = task_rows(payload)
    task_ids = explicit_task_ids(payload)
    if task_ids:
        tasks = [row for row in tasks if str(row.get("id") or row.get("taskId") or row.get("task_id") or "").strip() in task_ids]

    details["task_ids"] = sorted(task_ids or {str(row.get("id") or row.get("taskId") or row.get("task_id")) for row in tasks if present(row.get("id") or row.get("taskId") or row.get("task_id"))})
    details["batch_ids"] = sorted(batch_ids(payload))
    details["authoritative_sync_statuses"] = authoritative_sync_states(payload)
    details["graph_visibility_statuses"] = graph_visibility_states(payload)
    details["semantic_statuses"] = semantic_states(payload)
    details["wait_statuses"] = wait_states(payload)
    details["missing_task_ids"] = sorted(missing_task_ids(payload))
    details["queue_summary"] = queue_summary(payload)

    submitted_keys = explicit_key_set(payload, {"submittedImportKeys", "submitted_import_keys", "submittedGraphImportKeys", "submitted_graph_import_keys"})
    completed_keys = explicit_key_set(payload, {"completedImportKeys", "completed_import_keys", "completedGraphImportKeys", "completed_graph_import_keys"})
    synced_keys = explicit_key_set(payload, {"authoritativeSyncCompletedKeys", "authoritative_sync_completed_keys", "syncedImportKeys", "synced_import_keys"})
    submitted_count = explicit_int(payload, {"submitted_import_count", "submittedImportCount", "submitted_graph_import_count", "submittedGraphImportCount"})
    completed_count = explicit_int(payload, {"completed_import_count", "completedImportCount", "completed_graph_import_count", "completedGraphImportCount"})
    sync_count = explicit_int(payload, {"authoritative_sync_completed_count", "authoritativeSyncCompletedCount", "synced_import_count", "syncedImportCount"})

    if submitted_count is None:
        submitted_count = len(submitted_keys) if submitted_keys else len(details["task_ids"])

    if not task_ids and not terminal_flag(payload) and submitted_count == 0:
        missing.append("taskIds/relevantTaskIds from submitted PaperNexus import_workflow tasks")

    completed_task_ids: set[str] = set()
    if tasks:
        status_pairs = [
            (
                str(row.get("id") or row.get("taskId") or row.get("task_id") or "<task>").strip(),
                first_state(row.get("status"), row.get("state")),
                first_state(row.get("stage"), row.get("phase")),
            )
            for row in tasks
        ]
        failed = [task_id for task_id, status, _stage in status_pairs if status in FAILED_STATUSES]
        pending = [task_id for task_id, status, stage in status_pairs if status in PENDING_STATUSES or stage in PENDING_STATUSES]
        incomplete = [
            task_id
            for task_id, status, stage in status_pairs
            if task_id not in failed
            and task_id not in pending
            and not (status in COMPLETE_STATUSES and (not stage or stage in COMPLETE_STATUSES))
        ]
        completed_task_ids = {
            task_id
            for task_id, status, stage in status_pairs
            if status in COMPLETE_STATUSES and (not stage or stage in COMPLETE_STATUSES)
        }
        if failed:
            missing.append("import_workflow failed tasks: " + ", ".join(failed[:8]))
        if pending:
            missing.append("import_workflow queued/running tasks; use operation=wait with waitForAuthoritativeSync=true: " + ", ".join(pending[:8]))
        if incomplete:
            missing.append("import_workflow tasks not completed: " + ", ".join(incomplete[:8]))
    elif not terminal_flag(payload):
        missing.append("import_workflow task rows or explicit graph_visible/complete status")

    if completed_count is None:
        if completed_keys:
            completed_count = len(completed_keys)
        elif completed_task_ids:
            completed_count = len(completed_task_ids)
        elif terminal_flag(payload) and submitted_count >= details["planned_import_count"]:
            completed_count = submitted_count
        else:
            completed_count = 0
    elif completed_task_ids:
        completed_count = max(completed_count, len(completed_task_ids))

    sync_states = details["authoritative_sync_statuses"]
    graph_states = details["graph_visibility_statuses"]
    semantic_statuses = details["semantic_statuses"]
    wait_statuses = details["wait_statuses"]
    authoritative_ok_count = sum(1 for state in sync_states if state in AUTHORITATIVE_OK)
    if sync_count is None:
        if synced_keys:
            sync_count = len(synced_keys)
        else:
            sync_count = authoritative_ok_count
    else:
        sync_count = max(sync_count, authoritative_ok_count)

    details["submitted_import_count"] = submitted_count
    details["completed_import_count"] = completed_count
    details["authoritative_sync_completed_count"] = sync_count

    if submitted_keys:
        details["missing_unsubmitted_keys"] = sorted(set(planned_keys) - submitted_keys - source_exceptions)
    if completed_keys:
        details["missing_incomplete_keys"] = sorted(set(planned_keys) - completed_keys - source_exceptions)
    if synced_keys:
        details["missing_unsynced_keys"] = sorted(set(planned_keys) - synced_keys - source_exceptions)

    planned_count = details["planned_import_count"]
    effective_planned_count = details["effective_planned_import_count"]
    if submitted_count < effective_planned_count:
        missing.append(f"unsubmitted graph_import papers: planned={effective_planned_count} submitted={submitted_count}")
    if completed_count < effective_planned_count:
        missing.append(f"incomplete graph_import papers: planned={effective_planned_count} completed={completed_count}")
    if sync_count < effective_planned_count:
        missing.append(f"authoritative graph sync incomplete for graph_import papers: planned={effective_planned_count} synced={sync_count}")
    if source_exceptions:
        warnings.append(
            "source-limited graph_import exceptions are not graph-grounded evidence: "
            + ", ".join(sorted(source_exceptions))
        )

    if any(state in FAILED_STATUSES for state in sync_states):
        missing.append("authoritative graph sync failed")
    pending_sync = [state for state in sync_states if state not in AUTHORITATIVE_OK]
    if pending_sync:
        missing.append("authoritative graph sync not complete: " + ", ".join(sorted(set(pending_sync))))
    if details["missing_task_ids"]:
        missing.append("import_workflow status missing requested task ids: " + ", ".join(details["missing_task_ids"][:8]))
    if graph_states and not any(state in COMPLETE_STATUSES or state in AUTHORITATIVE_OK for state in graph_states):
        missing.append("graph visibility not complete: " + ", ".join(sorted(set(graph_states))))
    if semantic_statuses and not any(state in COMPLETE_STATUSES or state in AUTHORITATIVE_OK for state in semantic_statuses):
        missing.append("semantic enrichment not complete: " + ", ".join(sorted(set(semantic_statuses))))
    if wait_statuses and any(state in FAILED_STATUSES for state in wait_statuses):
        missing.append("import_workflow wait failed: " + ", ".join(sorted(set(wait_statuses))))
    if not sync_states:
        warnings.append("authoritativeSync status absent; prefer import_workflow wait with waitForAuthoritativeSync=true")

    status = (
        "complete_with_source_limited_exceptions"
        if not missing and source_exceptions
        else "complete"
        if not missing
        else (
        "async_wait"
        if any(
            "queued/running" in item
            or "authoritative graph sync not complete" in item
            or "incomplete graph_import papers" in item
            or "authoritative graph sync incomplete" in item
            for item in missing
        )
        else "incomplete"
    )
    )
    return {
        "complete": not missing,
        "status": status,
        "missing": missing,
        "warnings": warnings,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--status", default="papernexus/IMPORT_WORKFLOW_STATUS.json")
    args = parser.parse_args()
    out = lint(args.project, args.status)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
