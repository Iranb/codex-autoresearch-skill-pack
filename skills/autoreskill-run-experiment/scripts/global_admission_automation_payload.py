#!/usr/bin/env python3
"""Build one fail-closed global AutoResearch admission heartbeat payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("~/.codex/autoreskill/GLOBAL_ADMISSION_CONFIG.json").expanduser()
V1_START = "[global-admission-controller-v1:start]"
V1_END = "[global-admission-controller-v1:end]"
SECRET_KEY_PARTS = {"api_key", "credential", "password", "private_key", "secret", "token"}


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def secret_field_paths(value: Any, prefix: str = "config") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            path = f"{prefix}.{key}"
            if any(part in normalized for part in SECRET_KEY_PARTS):
                paths.append(path)
            paths.extend(secret_field_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(secret_field_paths(child, f"{prefix}[{index}]"))
    return paths


def validate(config: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    secret_paths = sorted(set(secret_field_paths(config)))
    if secret_paths:
        errors.append("global admission config must contain references, not secrets: " + ", ".join(secret_paths))
    if config.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    controller_task_id = str(config.get("controller_task_id") or "").strip()
    if not controller_task_id:
        errors.append("controller_task_id is required; do not create or redirect a task implicitly")
    project_values = config.get("project_roots")
    if not isinstance(project_values, list) or not project_values:
        errors.append("project_roots must be a non-empty list")
        project_values = []
    projects: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for index, value in enumerate(project_values):
        project = Path(str(value)).expanduser()
        if not project.is_absolute():
            errors.append(f"project_roots[{index}] must be absolute")
            continue
        project = project.resolve()
        if project in seen:
            errors.append(f"duplicate project root: {project}")
            continue
        seen.add(project)
        queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
        queue = read_json(queue_path)
        if not queue:
            errors.append(f"queue missing or invalid: {queue_path}")
            continue
        scope = str((queue.get("policy") or {}).get("admission_scope") or "project")
        projects.append(
            {
                "project_root": str(project),
                "queue_revision": queue.get("queue_revision"),
                "admission_scope": scope,
                "queue_sha256": canonical_sha256(queue),
            }
        )
    rollout_phase = str(config.get("rollout_phase") or "prepare").strip().lower()
    if rollout_phase not in {"prepare", "canary", "active"}:
        errors.append("rollout_phase must be prepare, canary, or active")
    global_count = sum(1 for item in projects if item["admission_scope"] == "global")
    if rollout_phase in {"canary", "active"} and global_count == 0:
        errors.append(f"rollout_phase={rollout_phase} requires at least one admission_scope=global project")
    if rollout_phase == "active" and any(item["admission_scope"] != "global" for item in projects):
        errors.append("rollout_phase=active requires every configured project to use admission_scope=global")
    snapshot = Path(str(config.get("shared_resource_snapshot") or "")).expanduser()
    if not str(config.get("shared_resource_snapshot") or "").strip() or not snapshot.is_absolute():
        errors.append("shared_resource_snapshot must be an absolute private path")
    interval = config.get("heartbeat_interval_minutes", 5)
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 60:
        errors.append("heartbeat_interval_minutes must be an integer from 1 through 60")
    max_submits = config.get("max_submits_per_wake", 4)
    if isinstance(max_submits, bool) or not isinstance(max_submits, int) or not 1 <= max_submits <= 16:
        errors.append("max_submits_per_wake must be an integer from 1 through 16")
    if config.get("launch_authorized") is True and rollout_phase == "prepare":
        errors.append("prepare rollout cannot authorize physical launch")
    return errors, projects


def build_payload(config: dict[str, Any]) -> dict[str, Any]:
    errors, projects = validate(config)
    if errors:
        return {"ok": False, "status": "invalid_config", "errors": errors, "payload": None, "projects": projects}
    rollout_phase = str(config.get("rollout_phase") or "prepare")
    launch_authorized = config.get("launch_authorized") is True
    controller_task_id = str(config["controller_task_id"])
    project_args = " ".join(f"--project '{item['project_root']}'" for item in projects)
    project_state = json.dumps(projects, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    shared_snapshot = str(Path(str(config["shared_resource_snapshot"])).expanduser().resolve())
    schedule_out = str(
        Path(str(config.get("schedule_out") or "~/.codex/autoreskill/GLOBAL_ADMISSION_SCHEDULE.json"))
        .expanduser()
        .resolve()
    )
    owner = str(config.get("owner_id") or "global-admission-controller")
    max_submits = int(config.get("max_submits_per_wake", 4))
    prompt = (
        f"{V1_START}\n"
        f"Controller task: {controller_task_id}; rollout_phase={rollout_phase}; launch_authorized={str(launch_authorized).lower()}; "
        f"owner={owner}; max_submits_per_wake={max_submits}.\n"
        f"Configured projects: {project_state}\n"
        "On every wake, acquire or renew the single global-admission lease, reconcile every submitting/needs_sync row by native id or "
        "embedded trace before any retry, ask project controllers to materialize locally admissible rows, refresh one shared normalized "
        "capability-enriched resource snapshot, then run deterministic schedule-global with "
        f"{project_args} --resource-snapshot '{shared_snapshot}' --out '{schedule_out}'. "
        "If there is no claimable first assignment, record the exact blocker and stop. For a first assignment, acquire the target-project "
        "control lease after the global lease, atomically claim only that assignment using its schedule/assignment/snapshot hashes, run the "
        "route-specific preflight, durably prepare submit intent, and only then perform one authorized backend submit. Record the receipt "
        "immediately, reconcile authoritative state, invalidate the consumed snapshot/schedule, refresh, and repeat up to the bounded wake "
        "limit. Never reuse a stale assignment, never infer compatibility from idle hardware alone, never retry an ambiguous prepared "
        "attempt, and never create experiments merely to occupy GPUs. "
    )
    if not launch_authorized:
        prompt += "Physical submission is disabled: stop after dry scheduling and report the proposed first assignment. "
    prompt += f"Release leases only after queue/backend reconciliation.\n{V1_END}"
    mode = "update" if str(config.get("automation_id") or "").strip() else "create"
    status = "PAUSED" if rollout_phase == "prepare" or not launch_authorized else "ACTIVE"
    payload: dict[str, Any] = {
        "mode": mode,
        "kind": "heartbeat",
        "destination": "thread",
        "name": str(config.get("automation_name") or "AutoResearch global admission"),
        "prompt": prompt,
        "status": status,
    }
    if mode == "update":
        payload["id"] = str(config["automation_id"])
    if status == "ACTIVE":
        payload["rrule"] = f"FREQ=MINUTELY;INTERVAL={int(config.get('heartbeat_interval_minutes', 5))}"
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "ok": True,
        "status": "ready",
        "payload": payload,
        "projects": projects,
        "config_semantic_sha256": canonical_sha256(
            {key: value for key, value in config.items() if key not in {"updated_at", "notes"}}
        ),
        "prompt_sha256": prompt_sha256,
        "readback_expectation": {
            "automation_id": config.get("automation_id"),
            "controller_task_id": controller_task_id,
            "name": payload["name"],
            "status": status,
            "rrule": payload.get("rrule"),
            "prompt_sha256": prompt_sha256,
            "contract_count": prompt.count(V1_START),
        },
    }


def verify_readback(expectation: dict[str, Any], readback: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    expected_id = str(expectation.get("automation_id") or "").strip()
    observed_id = str(readback.get("id") or readback.get("automation_id") or "").strip()
    if expected_id and observed_id != expected_id:
        errors.append(f"automation id mismatch: expected {expected_id}, observed {observed_id or '<missing>'}")
    for key in ["name", "rrule"]:
        expected = expectation.get(key)
        if expected is not None and readback.get(key) != expected:
            errors.append(f"{key} mismatch: expected {expected!r}, observed {readback.get(key)!r}")
    expected_status = str(expectation.get("status") or "").upper()
    observed_status = str(readback.get("status") or "").upper()
    if expected_status and observed_status != expected_status:
        errors.append(f"status mismatch: expected {expected_status}, observed {observed_status or '<missing>'}")
    prompt = str(readback.get("prompt") or "")
    expected_prompt_sha256 = str(expectation.get("prompt_sha256") or "")
    observed_prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None
    if expected_prompt_sha256 and observed_prompt_sha256 != expected_prompt_sha256:
        errors.append("prompt_sha256 mismatch")
    expected_count = int(expectation.get("contract_count") or 0)
    if expected_count and prompt.count(V1_START) != expected_count:
        errors.append(
            f"global controller block count mismatch: expected {expected_count}, observed {prompt.count(V1_START)}"
        )
    return {
        "ok": not errors,
        "errors": errors,
        "observed_prompt_sha256": observed_prompt_sha256,
        "observed_contract_count": prompt.count(V1_START),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--out")
    parser.add_argument("--expected-payload", help="Previously generated payload result used as readback authority")
    parser.add_argument("--readback", help="JSON state captured after App mutation")
    args = parser.parse_args()
    config_path = Path(args.config).expanduser().resolve()
    result = (
        read_json(Path(args.expected_payload).expanduser().resolve())
        if args.expected_payload
        else build_payload(read_json(config_path))
    )
    if not result:
        result = {"ok": False, "status": "missing_expected_payload", "payload": None}
    result["config_path"] = str(config_path)
    if args.readback and result.get("payload"):
        verification = verify_readback(
            result.get("readback_expectation") or {},
            read_json(Path(args.readback).expanduser().resolve()),
        )
        result["readback_verification"] = verification
        if not verification["ok"]:
            result["ok"] = False
            result["status"] = "readback_mismatch"
    if args.out and result.get("ok"):
        out = Path(args.out).expanduser().resolve()
        atomic_write_json(out, result)
        result["out"] = str(out)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
