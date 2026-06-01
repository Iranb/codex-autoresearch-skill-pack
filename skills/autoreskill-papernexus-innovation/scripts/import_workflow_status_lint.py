#!/usr/bin/env python3
"""Lint PaperNexus import_workflow queue/status/wait evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


COMPLETE_STATUSES = {"complete", "completed", "ready", "succeeded", "success"}
FAILED_STATUSES = {"failed", "error", "errored", "cancelled", "canceled"}
PENDING_STATUSES = {"pending", "queued", "running", "processing", "in_progress", "submitted", "waiting"}
AUTHORITATIVE_OK = {"complete", "completed", "ready", "succeeded", "success", "superseded", "not_required", "none", "skipped"}


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
    for key in ["tasks", "task", "relevantTasks", "relevant_tasks"]:
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


def authoritative_sync_states(payload: Any) -> list[str]:
    states: list[str] = []
    for row in iter_dicts(payload):
        value = row.get("authoritativeSync") or row.get("authoritative_sync")
        if isinstance(value, dict):
            status = str(value.get("status") or "").strip().lower()
            if status:
                states.append(status)
    return states


def planned_import_count(base: Path) -> int:
    plan = read_json(base / "papernexus/GRAPH_IMPORT_PLAN.json")
    if not isinstance(plan, dict):
        return 0
    count = 0
    for batch in plan.get("import_batches") or []:
        if isinstance(batch, list):
            for row in batch:
                if isinstance(row, dict) and str(row.get("import_action") or "") in {"import", "supplement"}:
                    count += 1
        elif isinstance(batch, dict) and str(batch.get("import_action") or "") in {"import", "supplement"}:
            count += 1
    if count:
        return count
    for row in plan.get("selected_papers") or []:
        if isinstance(row, dict) and str(row.get("import_action") or "") in {"import", "supplement"}:
            count += 1
    return count


def terminal_flag(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    truthy_keys = ["graph_visible", "graphVisible", "graph_ready", "graphReady", "complete", "completed"]
    if any(payload.get(key) is True for key in truthy_keys):
        return True
    status = str(payload.get("status") or payload.get("state") or "").strip().lower()
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
    details: dict[str, Any] = {
        "path": str(path),
        "planned_import_count": planned_import_count(base),
        "task_ids": [],
        "batch_ids": [],
        "authoritative_sync_statuses": [],
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

    tasks = task_rows(payload)
    task_ids = explicit_task_ids(payload)
    if task_ids:
        tasks = [row for row in tasks if str(row.get("id") or row.get("taskId") or row.get("task_id") or "").strip() in task_ids]

    details["task_ids"] = sorted(task_ids or {str(row.get("id") or row.get("taskId") or row.get("task_id")) for row in tasks if present(row.get("id") or row.get("taskId") or row.get("task_id"))})
    details["batch_ids"] = sorted(batch_ids(payload))
    details["authoritative_sync_statuses"] = authoritative_sync_states(payload)
    details["queue_summary"] = queue_summary(payload)

    if not task_ids and not terminal_flag(payload):
        missing.append("taskIds/relevantTaskIds from submitted PaperNexus import_workflow tasks")

    if tasks:
        status_pairs = [
            (
                str(row.get("id") or row.get("taskId") or row.get("task_id") or "<task>").strip(),
                str(row.get("status") or row.get("state") or "").strip().lower(),
                str(row.get("stage") or "").strip().lower(),
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
        if failed:
            missing.append("import_workflow failed tasks: " + ", ".join(failed[:8]))
        if pending:
            missing.append("import_workflow queued/running tasks; use operation=wait with waitForAuthoritativeSync=true: " + ", ".join(pending[:8]))
        if incomplete:
            missing.append("import_workflow tasks not completed: " + ", ".join(incomplete[:8]))
    elif not terminal_flag(payload):
        missing.append("import_workflow task rows or explicit graph_visible/complete status")

    sync_states = details["authoritative_sync_statuses"]
    if any(state in FAILED_STATUSES for state in sync_states):
        missing.append("authoritative graph sync failed")
    pending_sync = [state for state in sync_states if state not in AUTHORITATIVE_OK]
    if pending_sync:
        missing.append("authoritative graph sync not complete: " + ", ".join(sorted(set(pending_sync))))
    if not sync_states:
        warnings.append("authoritativeSync status absent; prefer import_workflow wait with waitForAuthoritativeSync=true")

    status = "complete" if not missing else ("async_wait" if any("queued/running" in item or "authoritative graph sync not complete" in item for item in missing) else "incomplete")
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
