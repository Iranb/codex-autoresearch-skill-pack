#!/usr/bin/env python3
"""Offline GPU resource adapters and launch-intent preparation.

This module only reads captured JSON and project-local authorities.  It never
opens a network connection, scans a host, invokes SSH/Slurm, or launches work.
Resource normalization produces a proposal for the canonical experiment queue;
it never mutates that queue itself.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shlex
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WORKFLOW_SCRIPTS = Path(__file__).resolve().parents[2] / "autoreskill-workflow/scripts"
if str(WORKFLOW_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_SCRIPTS))

from resource_snapshot import canonicalize_snapshot  # noqa: E402


CAMPAIGN_REL = Path(".autoreskill/ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json")
GATE_REL = Path(".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json")
POLICY_REL = Path(".autoreskill/autopilot_policy.json")
QUEUE_REL = Path(".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json")
LEDGER_REL = Path(".autoreskill/coder/EXPERIMENT_LEDGER.json")
QUICK_CAMPAIGN_CEILING_GPU_HOURS = 4.0
QUICK_CANDIDATE_CEILING_GPU_HOURS = 1.0

ACTUAL_COMPLETE_STATUSES = {
    "complete",
    "completed",
    "success",
    "succeeded",
    "terminal_positive",
    "terminal_negative",
    "terminal_not_promoted",
    "valid_positive_candidate",
    "valid_negative",
    "valid_inconclusive",
}
ACTUAL_FAILED_STATUSES = {
    "failed",
    "error",
    "errored",
    "timeout",
    "timed_out",
    "oom",
    "cancelled",
    "canceled",
    "budget_stopped",
    "infrastructure_failure",
    "implementation_failure",
    "protocol_failure",
    "invalid",
}
RUNNING_STATUSES = {"running", "active", "submitted", "launching", "dispatched", "needs_sync"}
PLANNED_STATUSES = {"planned", "queued", "pending", "prepared", "created", "leased"}
REMOTE_ROUTES = {"ssh", "bjtu_hpc"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
COMMITTED_REF_RE = re.compile(
    r"^ideation/committed/(?P<stem>NON_PAPERNEXUS_IDEA_LINT|INNOVATION_SLOT_MAP)\.(?P<sha>[0-9a-f]{64})\.json$"
)
PREFLIGHT_MAX_AGE_SECONDS = 600
MATERIALIZE_LOCK_REL = Path(".autoreskill/ideation/.non_papernexus_materialize.lock")


class AdapterError(RuntimeError):
    """Structured, user-facing fail-closed adapter error."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    def reject_nonfinite(token: str) -> None:
        raise ValueError(f"non-finite JSON number {token!r} is forbidden")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
    except FileNotFoundError as exc:
        raise AdapterError("file_missing", f"required JSON file is missing: {path}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise AdapterError("invalid_json", f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AdapterError("invalid_json_root", f"JSON root must be an object: {path}")
    return payload


def atomic_write_json(path: Path, payload: Any, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        if mode is not None:
            os.chmod(path, mode)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@contextmanager
def local_file_lock(path: Path) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def canonical_json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AdapterError("noncanonical_json", f"payload is not strict canonical JSON: {exc}") from exc


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_root(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def source_ref(path: Path, project: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(project).as_posix()
    except ValueError:
        return str(resolved)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def nonnegative_number(value: Any) -> float | None:
    number = finite_number(value)
    return number if number is not None and number >= 0 else None


def nonnegative_int(value: Any) -> int | None:
    number = finite_number(value)
    if number is None or number < 0 or not number.is_integer():
        return None
    return int(number)


def path_value(payload: dict[str, Any], path: Iterable[str]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def first_number(payload: dict[str, Any], paths: Iterable[tuple[str, ...]]) -> float | None:
    for path in paths:
        number = nonnegative_number(path_value(payload, path))
        if number is not None:
            return number
    return None


def strict_optional_nonnegative_number(
    payload: dict[str, Any],
    paths: Iterable[tuple[str, ...]],
    *,
    field_group: str,
) -> float | None:
    for path in paths:
        value = path_value(payload, path)
        if value is None:
            continue
        number = nonnegative_number(value)
        if number is None:
            raise AdapterError(
                "budget_invalid",
                f"{field_group} must be a nonnegative finite number",
                field=".".join(path),
                observed=value,
            )
        return number
    return None


def parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def explicit_fresh(payload: dict[str, Any], checked_at: Any, *, max_age_seconds: int = 600) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if payload.get("stale") is True or payload.get("fresh") is False or status in {"stale", "expired", "unknown"}:
        return False
    observed = parse_timestamp(checked_at)
    if observed is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - observed).total_seconds()
    return -60 <= age_seconds <= max_age_seconds


def opaque_ref(prefix: str, value: str, length: int = 16) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]}"


def safe_fragment(value: str, fallback: str = "unknown") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    return text[:64] or fallback


def conservative_pool_merge(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate physical pools without ever increasing trusted capacity."""

    merged = dict(existing)
    merged["launch_slots"] = min(int(existing.get("launch_slots") or 0), int(candidate.get("launch_slots") or 0))
    if merged["launch_slots"] == 0:
        statuses = {str(existing.get("status") or "unknown"), str(candidate.get("status") or "unknown")}
        merged["status"] = "stale" if "stale" in statuses else "full" if statuses == {"full"} else "unreachable"
    merged["fresh"] = bool(existing.get("fresh") is True and candidate.get("fresh") is True)
    old_free = nonnegative_number(existing.get("free_vram_mb"))
    new_free = nonnegative_number(candidate.get("free_vram_mb"))
    if old_free is not None and new_free is not None:
        merged["free_vram_mb"] = min(old_free, new_free)
    return merged


def normalize_ssh_payload(payload: dict[str, Any], *, project: Path, input_path: Path) -> dict[str, Any]:
    checked_at = payload.get("created_at") or payload.get("checked_at") or payload.get("generated_at")
    snapshot_fresh = explicit_fresh(payload, checked_at)
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    warnings: list[str] = []
    if not results:
        warnings.append("captured SSH scan contains no endpoint results; capacity is unknown")

    pools_by_id: dict[str, dict[str, Any]] = {}
    for result_index, raw_result in enumerate(results):
        if not isinstance(raw_result, dict):
            warnings.append(f"results[{result_index}] is not an object")
            continue
        host_ref = str(
            raw_result.get("ssh_alias")
            or raw_result.get("host")
            or raw_result.get("remote_hostname")
            or raw_result.get("label")
            or ""
        ).strip()
        if not host_ref:
            host_ref = f"captured-endpoint-{result_index}"
            warnings.append(f"results[{result_index}] lacks a host reference")
        endpoint_key = "|".join(
            [
                str(raw_result.get("user") or raw_result.get("remote_user") or ""),
                host_ref.lower(),
                str(raw_result.get("port") or 22),
            ]
        )
        endpoint_ref = opaque_ref("ssh-endpoint", endpoint_key, 12)
        result_status = str(raw_result.get("status") or "unknown").strip().lower()
        gpus = raw_result.get("gpus") if isinstance(raw_result.get("gpus"), list) else []
        if not gpus and isinstance(raw_result.get("idle_gpus"), list):
            gpus = raw_result["idle_gpus"]

        if not gpus:
            pool_id = f"ssh:{endpoint_ref.split(':', 1)[1]}:probe"
            status = "stale" if not snapshot_fresh else "unreachable"
            pool = {
                "pool_id": pool_id,
                "backend": "ssh",
                "compute_backend": {"backend": "local_gpu"},
                "execution_route": "ssh",
                "host_ref": host_ref,
                "endpoint_ref": endpoint_ref,
                "status": status,
                "fresh": False,
                "launch_slots": 0,
                "capabilities": ["single_gpu"],
                "checked_at": checked_at,
                "source_ref": source_ref(input_path, project),
                "source_sha256": file_sha256(input_path),
                "source_status": result_status,
                "fit_confidence": "captured_unknown",
            }
            pools_by_id[pool_id] = pool
            continue

        for gpu_index, raw_gpu in enumerate(gpus):
            if not isinstance(raw_gpu, dict):
                warnings.append(f"results[{result_index}].gpus[{gpu_index}] is not an object")
                continue
            gpu_uuid = str(raw_gpu.get("uuid") or "").strip()
            gpu_id = str(raw_gpu.get("index") if raw_gpu.get("index") is not None else gpu_index)
            physical_key = gpu_uuid or f"index-{gpu_id}"
            physical_digest = hashlib.sha256(f"{endpoint_key}|{physical_key}".encode("utf-8")).hexdigest()[:16]
            pool_id = f"ssh:{endpoint_ref.split(':', 1)[1]}:gpu:{physical_digest}"
            idle = bool(gpu_uuid) and raw_gpu.get("idle") is True and result_status == "idle_available"
            launch_slots = 1 if snapshot_fresh and idle else 0
            status = "unknown" if not gpu_uuid else "available" if launch_slots else "stale" if not snapshot_fresh else "full"
            if not gpu_uuid:
                warnings.append(
                    f"results[{result_index}].gpus[{gpu_index}] lacks a GPU UUID; physical identity is unknown and capacity is zero"
                )
            free_vram = nonnegative_number(
                raw_gpu.get("memory_free_mib", raw_gpu.get("free_vram_mb", raw_gpu.get("memory_free_mb")))
            )
            pool = {
                "pool_id": pool_id,
                "backend": "ssh",
                "compute_backend": {"backend": "local_gpu"},
                "execution_route": "ssh",
                "host_ref": host_ref,
                "endpoint_ref": endpoint_ref,
                "status": status,
                "fresh": bool(snapshot_fresh and gpu_uuid),
                "launch_slots": launch_slots,
                "gpu_model": raw_gpu.get("name"),
                "gpu_uuids": [gpu_uuid] if gpu_uuid else [],
                "gpu_ids": [gpu_id],
                "resource_ids": [gpu_uuid] if gpu_uuid else [],
                "capabilities": ["single_gpu", "physical_gpu_identity"] if gpu_uuid else ["single_gpu"],
                "checked_at": checked_at,
                "source_ref": source_ref(input_path, project),
                "source_sha256": file_sha256(input_path),
                "source_status": result_status,
                "fit_confidence": "captured_gpu_uuid" if gpu_uuid else "captured_missing_gpu_uuid",
            }
            if free_vram is not None:
                pool["free_vram_mb"] = free_vram
            existing = pools_by_id.get(pool_id)
            pools_by_id[pool_id] = conservative_pool_merge(existing, pool) if existing else pool

    pools = [pools_by_id[key] for key in sorted(pools_by_id)]
    available = sum(int(pool.get("launch_slots") or 0) for pool in pools)
    snapshot_status = "fresh" if snapshot_fresh else "stale"
    if not results:
        snapshot_status = "unknown"
    return {
        "schema_version": 1,
        "kind": "proposed_resource_snapshot",
        "source_kind": "gpu_idle_scan_capture",
        "compute_backend": {"backend": "local_gpu"},
        "execution_route": "ssh",
        "source_ref": source_ref(input_path, project),
        "source_sha256": file_sha256(input_path),
        "checked_at": checked_at,
        "normalized_at": now_iso(),
        "status": snapshot_status,
        "fresh": bool(snapshot_fresh and results),
        "stale": not bool(snapshot_fresh and results),
        "available_gpu_slots": available,
        "pools": pools,
        "warnings": warnings,
        "authority_boundary": "resource observation only; does not create ideas, queue rows, claims, or launches",
    }


def normalize_local_payload(payload: dict[str, Any], *, project: Path, input_path: Path) -> dict[str, Any]:
    """Normalize a captured local-GPU observation without probing the machine.

    The deliberately small input contract is ``local-gpu-scan/v1``.  A GPU is
    assignable only when the capture is fresh, has an immutable UUID, reports
    the device idle, and states that process visibility was complete.  This is
    observation normalization only; a fresh backend preflight is still
    required after the queue assignment.
    """

    checked_at = payload.get("checked_at") or payload.get("created_at") or payload.get("generated_at")
    valid_shape = str(payload.get("schema") or "") == "local-gpu-scan/v1"
    snapshot_fresh = bool(valid_shape and explicit_fresh(payload, checked_at))
    gpus = payload.get("gpus") if isinstance(payload.get("gpus"), list) else []
    warnings: list[str] = []
    if not valid_shape:
        warnings.append("local input must declare schema=local-gpu-scan/v1")
    if not gpus:
        warnings.append("captured local scan contains no GPUs; capacity is unknown")

    machine_ref = opaque_ref(
        "local-machine",
        str(payload.get("machine_id") or payload.get("hostname") or "captured-local-machine"),
        12,
    )
    pools: list[dict[str, Any]] = []
    seen_uuids: set[str] = set()
    for index, raw_gpu in enumerate(gpus):
        if not isinstance(raw_gpu, dict):
            warnings.append(f"gpus[{index}] is not an object")
            continue
        gpu_uuid = str(raw_gpu.get("uuid") or "").strip()
        gpu_id = str(raw_gpu.get("index") if raw_gpu.get("index") is not None else index)
        duplicate_uuid = bool(gpu_uuid and gpu_uuid in seen_uuids)
        if gpu_uuid:
            seen_uuids.add(gpu_uuid)
        full_visibility = raw_gpu.get("full_process_visibility") is True
        idle = raw_gpu.get("idle") is True
        assignable = bool(snapshot_fresh and gpu_uuid and not duplicate_uuid and full_visibility and idle)
        if not gpu_uuid:
            warnings.append(f"gpus[{index}] lacks a GPU UUID; capacity is zero")
        if duplicate_uuid:
            warnings.append(f"gpus[{index}] duplicates GPU UUID {gpu_uuid}; duplicate capacity is zero")
        if not full_visibility:
            warnings.append(f"gpus[{index}] lacks full process visibility; capacity is zero")
        physical = gpu_uuid or f"index-{gpu_id}"
        physical_digest = hashlib.sha256(
            f"{machine_ref}|{physical}|{index if duplicate_uuid else ''}".encode("utf-8")
        ).hexdigest()[:16]
        free_vram = nonnegative_number(
            raw_gpu.get("memory_free_mib", raw_gpu.get("free_vram_mb", raw_gpu.get("memory_free_mb")))
        )
        pool = {
            "pool_id": f"local:{machine_ref.split(':', 1)[1]}:gpu:{physical_digest}",
            "backend": "local",
            "compute_backend": {"backend": "local_gpu"},
            "execution_route": "local",
            "machine_ref": machine_ref,
            "status": "available" if assignable else "stale" if not snapshot_fresh else "full",
            "fresh": bool(snapshot_fresh and gpu_uuid and not duplicate_uuid),
            "launch_slots": 1 if assignable else 0,
            "gpu_model": raw_gpu.get("name"),
            "gpu_uuids": [gpu_uuid] if gpu_uuid else [],
            "gpu_ids": [gpu_id],
            "resource_ids": [gpu_uuid] if gpu_uuid else [],
            "capabilities": ["single_gpu", "physical_gpu_identity", "full_process_visibility"]
            if gpu_uuid and full_visibility
            else ["single_gpu"],
            "checked_at": checked_at,
            "source_ref": source_ref(input_path, project),
            "source_sha256": file_sha256(input_path),
            "fit_confidence": "captured_local_gpu_uuid" if assignable else "captured_local_unassignable",
        }
        if free_vram is not None:
            pool["free_vram_mb"] = free_vram
        pools.append(pool)

    pools.sort(key=lambda item: str(item.get("pool_id") or ""))
    available = sum(int(pool.get("launch_slots") or 0) for pool in pools)
    return {
        "schema_version": 1,
        "kind": "proposed_resource_snapshot",
        "source_kind": "local_gpu_scan_capture",
        "compute_backend": {"backend": "local_gpu"},
        "execution_route": "local",
        "source_ref": source_ref(input_path, project),
        "source_sha256": file_sha256(input_path),
        "checked_at": checked_at,
        "normalized_at": now_iso(),
        "status": "fresh" if snapshot_fresh else "stale" if checked_at else "unknown",
        "fresh": snapshot_fresh,
        "stale": not snapshot_fresh,
        "available_gpu_slots": available,
        "pools": pools,
        "warnings": warnings,
        "authority_boundary": "captured local observation only; assignment, preflight, intent, and launch remain separate",
    }


def normalize_shared_limit(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[A-Za-z0-9_-]+:[0-9a-fA-F]{10,64}", text):
        return text
    return opaque_ref("bjtu-shared", text, 16)


def normalize_bjtu_payload(payload: dict[str, Any], *, project: Path, input_path: Path) -> dict[str, Any]:
    checked_at = payload.get("checked_at_local") or payload.get("checked_at") or payload.get("generated_at")
    options = payload.get("planner_options") if isinstance(payload.get("planner_options"), dict) else {}
    valid_plan = (
        str(payload.get("schema") or "") == "bjtu-hpc-resource-plan/v1"
        and str(options.get("admission_mode") or "") == "direct-start"
        and options.get("allow_queued_probe") is False
    )
    snapshot_fresh = bool(valid_plan and explicit_fresh(payload, checked_at))
    warnings: list[str] = []
    if not valid_plan:
        warnings.append(
            "BJTU input is not a direct-start/no-queued hpc_resource_planner capture; raw queue or nvidia-smi state is not allocatability"
        )

    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
    accounts_by_name = {
        str(item.get("name") or ""): item for item in accounts if isinstance(item, dict) and str(item.get("name") or "")
    }
    frontier = payload.get("admission_frontier") if isinstance(payload.get("admission_frontier"), list) else []
    pools: list[dict[str, Any]] = []
    represented_accounts: set[str] = set()
    for action_index, raw_action in enumerate(frontier):
        if not isinstance(raw_action, dict):
            warnings.append(f"admission_frontier[{action_index}] is not an object")
            continue
        account_name = str(raw_action.get("account") or raw_action.get("cluster_account") or "unknown")
        represented_accounts.add(account_name)
        account_ref = opaque_ref("bjtu-account", account_name, 16)
        recommendation = raw_action.get("recommendation") if isinstance(raw_action.get("recommendation"), dict) else {}
        requested = recommendation.get("requested") if isinstance(recommendation.get("requested"), dict) else {}
        requested_gpus = nonnegative_int(requested.get("gpus"))
        node = recommendation.get("selected_node") if isinstance(recommendation.get("selected_node"), dict) else {}
        node_name = str(node.get("name") or "unbound-node")
        node_ref = opaque_ref("bjtu-node", node_name, 12)
        immediate = str(recommendation.get("mode") or "") == "immediate"
        refresh_required = raw_action.get("requires_refresh_before_submit") is not False
        one_gpu = requested_gpus == 1
        assignable = bool(
            snapshot_fresh
            and action_index == 0
            and immediate
            and one_gpu
            and node_name != "unbound-node"
            and not refresh_required
            and raw_action.get("requires_exact_script_preflight") is True
            and raw_action.get("do_not_batch_submit") is True
            and raw_action.get("do_not_submit") is not True
            and recommendation.get("do_not_submit") is not True
        )
        status = "available" if assignable else "stale" if snapshot_fresh and refresh_required else "blocked"
        current = raw_action.get("current") if isinstance(raw_action.get("current"), dict) else {}
        shared_ref = normalize_shared_limit(current.get("shared_limit_ref"))
        pool = {
            "pool_id": f"bjtu:{account_ref.split(':', 1)[1]}:{node_ref.split(':', 1)[1]}:direct-start",
            "backend": "bjtu_hpc",
            "compute_backend": {"backend": "local_gpu"},
            "execution_route": "bjtu_hpc",
            "account_ref": account_ref,
            "node_ref": node_ref,
            "status": status,
            "fresh": bool(snapshot_fresh and not refresh_required),
            "launch_slots": 1 if assignable else 0,
            "gpu_count_per_launch": requested_gpus,
            "capabilities": ["single_gpu", "slurm_direct_start", "exact_script_preflight_required"],
            "checked_at": checked_at,
            "source_ref": source_ref(input_path, project),
            "source_sha256": file_sha256(input_path),
            "fit_confidence": "captured_bjtu_direct_start_plan" if assignable else "refresh_or_preflight_required",
            "requires_exact_script_preflight": True,
            "requires_refresh_before_submit": refresh_required,
            "do_not_batch_submit": True,
            "resource_ids": [f"{account_ref}:{node_ref}"],
        }
        if shared_ref:
            pool["shared_limit_ref"] = shared_ref
        pools.append(pool)

    for account_name, account in sorted(accounts_by_name.items()):
        if account_name in represented_accounts:
            continue
        account_ref = opaque_ref("bjtu-account", account_name, 16)
        current = account.get("current") if isinstance(account.get("current"), dict) else {}
        status = str(account.get("status") or "blocked").strip().lower()
        if status in {"ok", "available", "idle", "ready"}:
            status = "full"
        if not snapshot_fresh:
            status = "stale"
        pool = {
            "pool_id": f"bjtu:{account_ref.split(':', 1)[1]}:account",
            "backend": "bjtu_hpc",
            "compute_backend": {"backend": "local_gpu"},
            "execution_route": "bjtu_hpc",
            "account_ref": account_ref,
            "status": status,
            "fresh": bool(snapshot_fresh),
            "launch_slots": 0,
            "capabilities": ["single_gpu", "slurm_direct_start", "exact_script_preflight_required"],
            "checked_at": checked_at,
            "source_ref": source_ref(input_path, project),
            "source_sha256": file_sha256(input_path),
            "fit_confidence": "captured_bjtu_account_blocker",
            "requires_exact_script_preflight": True,
            "do_not_batch_submit": True,
        }
        shared_ref = normalize_shared_limit(current.get("shared_limit_ref"))
        if shared_ref:
            pool["shared_limit_ref"] = shared_ref
            if status == "blocked_shared_limit":
                pool["shared_limit_blocked"] = True
        pools.append(pool)

    pools.sort(key=lambda item: str(item.get("pool_id") or ""))
    available = sum(int(pool.get("launch_slots") or 0) for pool in pools)
    return {
        "schema_version": 1,
        "kind": "proposed_resource_snapshot",
        "source_kind": "bjtu_hpc_direct_start_plan_capture",
        "compute_backend": {"backend": "local_gpu"},
        "execution_route": "bjtu_hpc",
        "source_ref": source_ref(input_path, project),
        "source_sha256": file_sha256(input_path),
        "checked_at": checked_at,
        "normalized_at": now_iso(),
        "status": "fresh" if snapshot_fresh else "stale" if checked_at else "unknown",
        "fresh": snapshot_fresh,
        "stale": not snapshot_fresh,
        "available_gpu_slots": available,
        "pools": pools,
        "warnings": warnings,
        "authority_boundary": "captured Slurm planning only; exact-script test-only and backend authorization remain mandatory",
    }


def candidate_id_of(payload: dict[str, Any]) -> str:
    for key in ("external_candidate_id", "candidate_id", "idea_candidate_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def find_candidate(campaign: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    candidates = campaign.get("candidates") if isinstance(campaign.get("candidates"), list) else []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        observed = candidate_id_of(candidate) or str(candidate.get("id") or "").strip()
        if observed == candidate_id:
            return candidate
    return None


def identity_values(record: dict[str, Any], keys: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    containers = [record]
    for name in ("external_identity", "launch_identity", "identity", "budget", "metadata"):
        value = record.get(name)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        for key in keys:
            value = str(container.get(key) or "").strip()
            if value:
                values.add(value)
    return values


def record_matches_campaign(record: dict[str, Any], *, campaign_sha: str, campaign_ref: str, candidate_ids: set[str]) -> bool:
    if record.get("budget_scope_unknown") is True:
        return True
    candidate_values = identity_values(
        record, ("external_candidate_id", "candidate_id", "idea_candidate_id", "selected_idea_id")
    )
    if candidate_values & candidate_ids:
        return True
    sha_values = identity_values(record, ("external_campaign_sha256", "campaign_sha256"))
    if campaign_sha in sha_values:
        return True
    ref_values = identity_values(record, ("external_campaign_ref", "campaign_ref"))
    normalized_ref = campaign_ref.lstrip("./")
    return any(value.lstrip("./").endswith(normalized_ref) for value in ref_values)


def record_matches_candidate(record: dict[str, Any], candidate_id: str) -> bool:
    values = identity_values(
        record, ("external_candidate_id", "candidate_id", "idea_candidate_id", "selected_idea_id")
    )
    return candidate_id in values


def record_aliases(record: dict[str, Any], source_kind: str, source_ref_value: str) -> set[str]:
    aliases: set[str] = set()
    run_id = str(record.get("run_id") or "").strip()
    if run_id:
        aliases.add(f"run:{run_id}")
    for key in ("queue_row_id", "next_action_row_id", "row_id"):
        value = str(record.get(key) or "").strip()
        if value:
            aliases.add(f"row:{value}")
    if source_kind == "queue":
        row_id = str(record.get("id") or "").strip()
        if row_id:
            aliases.add(f"row:{row_id}")
    if not aliases:
        aliases.add(f"source:{source_kind}:{source_ref_value}")
    return aliases


def record_run_id(record: dict[str, Any]) -> str:
    return str(record.get("run_id") or "").strip()


def record_row_ids(record: dict[str, Any], source_kind: str) -> set[str]:
    values = {
        str(record.get(key) or "").strip()
        for key in ("queue_row_id", "next_action_row_id", "row_id")
        if str(record.get(key) or "").strip()
    }
    if source_kind == "queue":
        value = str(record.get("id") or "").strip()
        if value:
            values.add(value)
    return values


def explicitly_scoped_to_other_campaign(record: dict[str, Any], campaign_sha: str, campaign_ref: str) -> bool:
    """Return true only for an explicit, internally consistent different campaign scope.

    A candidate id by itself is not a campaign scope: legacy and PaperNexus rows
    commonly carry generic candidate ids.  Unknown project runtime consumption is
    deliberately fail-closed until a campaign hash/ref is recorded.
    """

    shas = identity_values(record, ("external_campaign_sha256", "campaign_sha256"))
    refs = identity_values(record, ("external_campaign_ref", "campaign_ref"))
    if not shas or not refs:
        return False
    normalized_ref = campaign_ref.lstrip("./")
    is_current_ref = any(value.lstrip("./").endswith(normalized_ref) for value in refs)
    return campaign_sha not in shas and not is_current_ref


def gpu_count(record: dict[str, Any]) -> int:
    for container in (
        record,
        record.get("resource_request") if isinstance(record.get("resource_request"), dict) else {},
        record.get("resource_allocation") if isinstance(record.get("resource_allocation"), dict) else {},
        record.get("planned_resource_allocation") if isinstance(record.get("planned_resource_allocation"), dict) else {},
    ):
        value = nonnegative_int(container.get("gpu_count"))
        if value is not None:
            return max(1, value)
    return 1


def actual_gpu_hours(record: dict[str, Any]) -> float | None:
    direct = first_number(
        record,
        [
            ("actual_gpu_hours",),
            ("usage", "actual_gpu_hours"),
            ("budget", "actual_gpu_hours"),
            ("runtime", "actual_gpu_hours"),
            ("accounting", "actual_gpu_hours"),
            ("gpu_hours",),
        ],
    )
    if direct is not None:
        return direct
    gpu_seconds = first_number(record, [("gpu_seconds",), ("usage", "gpu_seconds"), ("runtime", "gpu_seconds")])
    if gpu_seconds is not None:
        return gpu_seconds / 3600.0
    duration = first_number(
        record,
        [("duration_seconds",), ("elapsed_seconds",), ("runtime", "duration_seconds"), ("usage", "duration_seconds")],
    )
    if duration is not None:
        return duration * gpu_count(record) / 3600.0
    return None


def reserved_gpu_hours(record: dict[str, Any]) -> float | None:
    direct = first_number(
        record,
        [
            ("reserved_gpu_hours",),
            ("locked_gpu_hours",),
            ("budget", "reserved_gpu_hours"),
            ("budget", "locked_gpu_hours"),
            ("budget", "gpu_hours"),
            ("resource_request", "estimated_gpu_hours"),
            ("planned_resource_allocation", "estimated_gpu_hours"),
            ("estimated_gpu_hours",),
        ],
    )
    if direct is not None:
        return direct
    minutes = first_number(
        record,
        [
            ("max_walltime_minutes",),
            ("budget", "max_walltime_minutes"),
            ("resource_request", "max_walltime_minutes"),
        ],
    )
    return minutes * gpu_count(record) / 60.0 if minutes is not None else None


def status_of(record: dict[str, Any]) -> str:
    return str(record.get("status") or record.get("state") or record.get("scheduler_status") or "").strip().lower()


def classify_usage(record: dict[str, Any], source_kind: str) -> tuple[str | None, float | None, str | None]:
    status = status_of(record)
    if status in ACTUAL_COMPLETE_STATUSES:
        value = actual_gpu_hours(record)
        return "completed_actual", value, None if value is not None else "terminal completed record lacks actual GPU usage"
    if status in ACTUAL_FAILED_STATUSES:
        value = actual_gpu_hours(record)
        return "failed_actual", value, None if value is not None else "terminal failed record lacks actual GPU usage"
    if status in RUNNING_STATUSES:
        value = reserved_gpu_hours(record)
        return "running_reserved", value, None if value is not None else "running record lacks a conservative GPU reservation"
    if status in PLANNED_STATUSES:
        value = reserved_gpu_hours(record)
        return "planned_reserved", value, None if value is not None else "planned record lacks a conservative GPU reservation"
    if source_kind == "queue" and status in {"ready", "candidate", "blocked", "dropped", "superseded"}:
        return None, None, None
    if any(record.get(key) for key in ("run_id", "launch_started_at", "remote_run_ref", "resource_allocation")):
        return None, None, f"launched record has unknown status {status or '<missing>'}"
    return None, None, None


def campaign_candidate_ids(campaign: dict[str, Any]) -> set[str]:
    values = {
        str(item)
        for key in ("shortlisted_candidate_ids", "admitted_candidate_ids")
        for item in (campaign.get(key) if isinstance(campaign.get(key), list) else [])
        if str(item).strip()
    }
    candidates = campaign.get("candidates") if isinstance(campaign.get("candidates"), list) else []
    for candidate in candidates:
        if isinstance(candidate, dict):
            value = candidate_id_of(candidate) or str(candidate.get("id") or "").strip()
            if value:
                values.add(value)
    return values


def ledger_records(payload: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for key in (
        "entries",
        "candidate_runs",
        "running_runs",
        "terminal_runs",
        "failed_runs",
        "parallel_runs",
        "diagnostic_runs",
    ):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if isinstance(row, dict):
                yield f"{LEDGER_REL.as_posix()}#{key}[{index}]", row


def usage_records(project: Path) -> Iterable[tuple[str, str, dict[str, Any]]]:
    experiment_root = project / ".autoreskill/coder/experiments"
    if experiment_root.exists():
        for path in sorted(experiment_root.rglob("REMOTE_RUN.json")):
            try:
                yield "remote_run", source_ref(path, project), read_json(path)
            except AdapterError:
                yield "remote_run", source_ref(path, project), {
                    "status": "unknown",
                    "run_id": str(path),
                    "budget_scope_unknown": True,
                    "launch_started_at": "unknown",
                }
    ledger_path = project / LEDGER_REL
    if ledger_path.exists():
        ledger = read_json(ledger_path)
        for ref, row in ledger_records(ledger):
            yield "experiment_ledger", ref, row
    queue_path = project / QUEUE_REL
    if queue_path.exists():
        queue = read_json(queue_path)
        rows = queue.get("rows") if isinstance(queue.get("rows"), list) else []
        for index, row in enumerate(rows):
            if isinstance(row, dict):
                yield "queue", f"{QUEUE_REL.as_posix()}#rows[{index}]", row


def candidate_ceiling(candidate: dict[str, Any]) -> float:
    # A candidate's estimated pilot cost is one reservation, not its cumulative
    # campaign ceiling.  Only fields that explicitly denote a maximum may
    # tighten the default one-GPU-hour cap; otherwise retries/smokes would make
    # a correctly budgeted candidate invalid as soon as the first pilot ran.
    explicit = strict_optional_nonnegative_number(
        candidate,
        [
            ("protected_commitments", "resource_ceiling", "gpu_hours_max"),
            ("protected_commitments", "resource_ceiling", "max_gpu_hours"),
            ("protected_commitments", "resource_ceiling", "gpu_hours"),
            ("resource_ceiling", "gpu_hours_max"),
            ("resource_ceiling", "max_gpu_hours"),
            ("resource_ceiling", "gpu_hours"),
            ("pilot", "resource_ceiling", "gpu_hours"),
            ("quick_validation", "max_gpu_hours"),
            ("max_gpu_hours",),
        ],
        field_group="candidate GPU-hour ceiling",
    )
    return min(QUICK_CANDIDATE_CEILING_GPU_HOURS, explicit) if explicit is not None else QUICK_CANDIDATE_CEILING_GPU_HOURS


def campaign_ceiling(campaign: dict[str, Any]) -> float:
    explicit = strict_optional_nonnegative_number(
        campaign,
        [
            ("quick_validation_budget", "campaign_gpu_hours_max"),
            ("campaign_budget", "max_gpu_hours"),
            ("budget", "max_gpu_hours"),
            ("resource_ceiling", "campaign_gpu_hours"),
            ("constraints", "quick_campaign_gpu_hours"),
            ("gpu_budget_hours",),
            ("max_gpu_hours",),
        ],
        field_group="campaign GPU-hour ceiling",
    )
    return min(QUICK_CAMPAIGN_CEILING_GPU_HOURS, explicit) if explicit is not None else QUICK_CAMPAIGN_CEILING_GPU_HOURS


def explicit_user_ceiling(campaign: dict[str, Any], cli_value: float | None) -> float | None:
    if cli_value is not None:
        return cli_value
    return strict_optional_nonnegative_number(
        campaign,
        [
            ("explicit_user_budget", "gpu_hours"),
            ("user_budget", "gpu_hours"),
            ("user_budget_gpu_hours",),
        ],
        field_group="explicit user GPU-hour ceiling",
    )


def derive_budget(
    project: Path,
    *,
    candidate_id: str,
    requested_gpu_hours: float,
    user_ceiling_gpu_hours: float | None = None,
) -> dict[str, Any]:
    if requested_gpu_hours < 0 or not math.isfinite(requested_gpu_hours):
        raise AdapterError("budget_invalid", "reserve_gpu_hours must be a nonnegative finite number")
    if user_ceiling_gpu_hours is not None and (
        not math.isfinite(user_ceiling_gpu_hours) or user_ceiling_gpu_hours < 0
    ):
        raise AdapterError("budget_invalid", "user ceiling must be a nonnegative finite number")
    campaign_path = project / CAMPAIGN_REL
    campaign = read_json(campaign_path)
    candidate = find_candidate(campaign, candidate_id)
    if candidate is None:
        raise AdapterError("candidate_missing", f"candidate {candidate_id!r} is absent from the external campaign")
    campaign_sha = file_sha256(campaign_path)
    campaign_ref_value = CAMPAIGN_REL.as_posix().removeprefix(".autoreskill/")
    all_candidate_ids = campaign_candidate_ids(campaign)

    policy_path = project / POLICY_REL
    policy = read_json(policy_path) if policy_path.exists() else {}
    project_ceiling = strict_optional_nonnegative_number(
        policy,
        [("max_experiment_gpu_hours",)],
        field_group="project policy max_experiment_gpu_hours",
    )
    locked_campaign_ceiling = campaign_ceiling(campaign)
    locked_candidate_ceiling = candidate_ceiling(candidate)
    constraint_candidate_ceiling = strict_optional_nonnegative_number(
        campaign,
        [("constraints", "max_candidate_gpu_hours")],
        field_group="campaign constraint max_candidate_gpu_hours",
    )
    if constraint_candidate_ceiling is not None:
        locked_candidate_ceiling = min(locked_candidate_ceiling, constraint_candidate_ceiling)
    user_ceiling = explicit_user_ceiling(campaign, user_ceiling_gpu_hours)
    campaign_limits = [QUICK_CAMPAIGN_CEILING_GPU_HOURS, locked_campaign_ceiling]
    if project_ceiling is not None:
        campaign_limits.append(project_ceiling)
    if user_ceiling is not None:
        campaign_limits.append(user_ceiling)
    effective_campaign_ceiling = min(campaign_limits)

    totals = {
        "completed_actual": 0.0,
        "failed_actual": 0.0,
        "running_reserved": 0.0,
        "planned_reserved": 0.0,
    }
    candidate_totals = {key: 0.0 for key in totals}
    counted: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    seen_run_ids: set[str] = set()
    rows_backed_by_runs: set[str] = set()
    seen_row_only_records: set[str] = set()
    seen_fallback_records: set[str] = set()
    for source_kind, record_ref, record in usage_records(project):
        category, hours, error = classify_usage(record, source_kind)
        matches_campaign = record_matches_campaign(
            record,
            campaign_sha=campaign_sha,
            campaign_ref=campaign_ref_value,
            candidate_ids=all_candidate_ids,
        )
        if not matches_campaign:
            if category is None and error is None:
                continue
            if explicitly_scoped_to_other_campaign(record, campaign_sha, campaign_ref_value):
                continue
            unknown.append(
                {
                    "source_kind": source_kind,
                    "source_ref": record_ref,
                    "identity": sorted(record_aliases(record, source_kind, record_ref))[0],
                    "status": status_of(record),
                    "reason": "runtime consumption has no verifiable external campaign scope",
                }
            )
            continue

        run_id = record_run_id(record)
        row_ids = record_row_ids(record, source_kind)
        if run_id:
            if run_id in seen_run_ids:
                continue
            seen_run_ids.add(run_id)
            rows_backed_by_runs.update(row_ids)
        elif row_ids:
            # A queue reservation (or a row-only ledger mirror) is an alias for
            # one or more concrete runs.  Distinct run ids sharing the same row
            # remain separate attempts and are all charged; the row reservation
            # itself is charged only when no concrete run exists.
            if row_ids & rows_backed_by_runs or row_ids & seen_row_only_records:
                continue
            seen_row_only_records.update(row_ids)
        else:
            fallback = f"{source_kind}:{record_ref}"
            if fallback in seen_fallback_records:
                continue
            seen_fallback_records.add(fallback)

        aliases = record_aliases(record, source_kind, record_ref)
        record_candidate = record_matches_candidate(record, candidate_id)
        identity = f"run:{run_id}" if run_id else sorted(aliases)[0]
        if error:
            unknown.append(
                {
                    "source_kind": source_kind,
                    "source_ref": record_ref,
                    "identity": identity,
                    "status": status_of(record),
                    "reason": error,
                }
            )
            continue
        if category is None or hours is None:
            continue
        totals[category] += hours
        if record_candidate:
            candidate_totals[category] += hours
        counted.append(
            {
                "source_kind": source_kind,
                "source_ref": record_ref,
                "identity": identity,
                "candidate_id": candidate_id if record_candidate else None,
                "status": status_of(record),
                "category": category,
                "gpu_hours": round(hours, 8),
                "attempt_kind": record.get("attempt_kind") or record.get("run_kind"),
            }
        )

    total_committed = sum(totals.values())
    candidate_committed = sum(candidate_totals.values())
    campaign_remaining_before = effective_campaign_ceiling - total_committed
    candidate_remaining_before = locked_candidate_ceiling - candidate_committed
    reasons: list[str] = []
    if unknown:
        reasons.append("unknown matching runtime consumption must be reconciled before another reservation")
    if campaign_remaining_before + 1e-12 < requested_gpu_hours:
        reasons.append("campaign/project/user quick GPU-hour ceiling would be exceeded")
    if candidate_remaining_before + 1e-12 < requested_gpu_hours:
        reasons.append("candidate one-GPU-hour ceiling would be exceeded; smoke and retries are included")
    if project_ceiling is None:
        reasons.append("project max_experiment_gpu_hours is absent; the stricter four-hour quick ceiling is used")

    hard_fail_reasons = [reason for reason in reasons if not reason.startswith("project max_experiment_gpu_hours is absent")]
    ok = not hard_fail_reasons
    result = {
        "ok": ok,
        "schema_version": 1,
        "candidate_id": candidate_id,
        "campaign_ref": campaign_ref_value,
        "campaign_sha256": campaign_sha,
        "requested_reservation_gpu_hours": round(requested_gpu_hours, 8),
        "limits": {
            "quick_campaign_ceiling_gpu_hours": QUICK_CAMPAIGN_CEILING_GPU_HOURS,
            "locked_campaign_ceiling_gpu_hours": locked_campaign_ceiling,
            "project_policy_ceiling_gpu_hours": project_ceiling,
            "explicit_user_ceiling_gpu_hours": user_ceiling,
            "effective_campaign_ceiling_gpu_hours": effective_campaign_ceiling,
            "quick_candidate_ceiling_gpu_hours": QUICK_CANDIDATE_CEILING_GPU_HOURS,
            "locked_candidate_ceiling_gpu_hours": locked_candidate_ceiling,
        },
        "usage": {
            **{key: round(value, 8) for key, value in totals.items()},
            "total_committed_gpu_hours": round(total_committed, 8),
            "candidate": {
                **{key: round(value, 8) for key, value in candidate_totals.items()},
                "total_committed_gpu_hours": round(candidate_committed, 8),
            },
        },
        "remaining": {
            "campaign_before_request_gpu_hours": round(campaign_remaining_before, 8),
            "campaign_after_request_gpu_hours": round(campaign_remaining_before - requested_gpu_hours, 8),
            "candidate_before_request_gpu_hours": round(candidate_remaining_before, 8),
            "candidate_after_request_gpu_hours": round(candidate_remaining_before - requested_gpu_hours, 8),
        },
        "counted_records": counted,
        "unknown_records": unknown,
        "reasons": reasons,
        "accounting_boundary": "derived view only; no separate budget ledger or refund authority is created",
    }
    result["budget_commitment_sha256"] = canonical_sha256(
        {
            "candidate_id": candidate_id,
            "campaign_sha256": campaign_sha,
            "requested_reservation_gpu_hours": requested_gpu_hours,
            "limits": result["limits"],
            "usage": result["usage"],
            "remaining": result["remaining"],
            "unknown_records": unknown,
        }
    )
    return result


def find_queue_row(queue: dict[str, Any], row_id: str) -> dict[str, Any] | None:
    rows = queue.get("rows") if isinstance(queue.get("rows"), list) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or "") == row_id:
            return row
    return None


def launch_spec_for(row: dict[str, Any], launch_spec_path: Path | None) -> dict[str, Any]:
    if launch_spec_path is not None:
        return read_json(launch_spec_path)
    value = row.get("launch_spec")
    if isinstance(value, dict):
        return value
    raise AdapterError(
        "launch_spec_missing",
        "prepare-launch-intent requires --launch-spec or row.launch_spec with an exact argv and immutable code/data/environment refs",
    )


def first_text(payload: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def validate_launch_spec(spec: dict[str, Any]) -> dict[str, Any]:
    argv = spec.get("command_argv") if isinstance(spec.get("command_argv"), list) else spec.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise AdapterError("command_missing", "launch spec must contain a nonempty string array command_argv/argv")
    normalized = {
        "command_argv": list(argv),
        "code_ref": first_text(spec, ("code_ref", "code_export_ref")),
        "code_sha256": first_text(spec, ("code_sha256", "code_export_sha256", "code_export_hash")),
        "dataset_ref": first_text(spec, ("dataset_ref", "dataset_profile_ref", "data_ref")),
        "dataset_sha256": first_text(spec, ("dataset_sha256", "dataset_profile_sha256", "dataset_hash")),
        "environment_ref": first_text(spec, ("environment_ref", "runtime_environment_ref", "env_ref")),
        "environment_sha256": first_text(spec, ("environment_sha256", "runtime_environment_sha256", "env_hash")),
        "working_dir": first_text(spec, ("working_dir", "remote_working_dir", "code_root")),
        "launcher_template_sha256": first_text(spec, ("launcher_template_sha256", "launcher_template_hash")),
        "resource_shape": spec.get("resource_shape"),
        "seed": spec.get("seed"),
    }
    missing = [
        key
        for key in (
            "code_ref",
            "code_sha256",
            "dataset_ref",
            "dataset_sha256",
            "environment_ref",
            "environment_sha256",
            "working_dir",
            "launcher_template_sha256",
            "resource_shape",
            "seed",
        )
        if (
            normalized.get(key) is None
            or (isinstance(normalized.get(key), str) and not str(normalized.get(key)).strip())
            or (key == "resource_shape" and not isinstance(normalized.get(key), dict))
        )
    ]
    if missing:
        raise AdapterError("launch_identity_missing", "launch spec lacks immutable launch identity fields", fields=missing)
    invalid_hashes = [
        key
        for key in (
            "code_sha256",
            "dataset_sha256",
            "environment_sha256",
            "launcher_template_sha256",
        )
        if not SHA256_RE.fullmatch(str(normalized.get(key) or ""))
    ]
    if invalid_hashes:
        raise AdapterError(
            "launch_identity_invalid",
            "launch identity hashes must be exact 64-hex SHA-256 values",
            fields=invalid_hashes,
        )
    shape = normalized.get("resource_shape")
    if not isinstance(shape, dict):
        raise AdapterError("resource_shape_invalid", "launch spec resource_shape must be an object")
    shape_gpus = nonnegative_int(shape.get("gpus", shape.get("gpu_count")))
    if shape_gpus != 1:
        raise AdapterError("resource_shape_invalid", "rapid-validation launch_spec.resource_shape must request exactly one GPU")
    launch_seed = nonnegative_int(normalized.get("seed"))
    if launch_seed is None:
        raise AdapterError("seed_identity_invalid", "launch spec seed must be a nonnegative integer")
    normalized["seed"] = launch_seed
    normalized["command_sha256"] = canonical_sha256(normalized["command_argv"])
    normalized["launch_spec_sha256"] = canonical_sha256(normalized)
    return normalized


def validate_backend_preflight(
    row: dict[str, Any],
    allocation: dict[str, Any],
    route: str,
    normalized_spec: dict[str, Any],
) -> dict[str, Any]:
    preflight = row.get("backend_preflight")
    if not isinstance(preflight, dict):
        preflight = allocation.get("backend_preflight")
    if not isinstance(preflight, dict):
        raise AdapterError(
            "backend_preflight_missing",
            "prepare-launch-intent requires a recorded route-specific backend_preflight after the atomic claim",
        )
    if str(preflight.get("status") or "").strip().lower() != "passed":
        raise AdapterError("backend_preflight_invalid", "backend_preflight.status must be passed")
    checked_at = parse_timestamp(preflight.get("checked_at"))
    if checked_at is None:
        raise AdapterError("backend_preflight_invalid", "backend_preflight.checked_at must be a timezone-aware ISO timestamp")
    age_seconds = (datetime.now(timezone.utc) - checked_at).total_seconds()
    if age_seconds < -60 or age_seconds > PREFLIGHT_MAX_AGE_SECONDS:
        raise AdapterError(
            "backend_preflight_stale",
            "backend_preflight is stale or implausibly future-dated; refresh and recheck the assigned route",
            age_seconds=age_seconds,
        )
    if str(preflight.get("pool_id") or "") != str(allocation.get("pool_id") or ""):
        raise AdapterError("backend_preflight_mismatch", "backend_preflight.pool_id must match the planned allocation")
    if str(preflight.get("execution_route") or "").strip().lower() != route:
        raise AdapterError("backend_preflight_mismatch", "backend_preflight.execution_route must match the planned route")
    if preflight.get("launch_spec_sha256") != normalized_spec.get("launch_spec_sha256"):
        raise AdapterError("backend_preflight_mismatch", "backend_preflight must bind the exact immutable launch spec")
    if preflight.get("resource_snapshot_sha256") != allocation.get("resource_snapshot_sha256"):
        raise AdapterError("backend_preflight_mismatch", "backend_preflight must bind the claimed resource snapshot")

    if route == "ssh":
        gpu_uuids = [str(value) for value in allocation.get("gpu_uuids", []) if str(value).strip()]
        if len(gpu_uuids) != 1:
            raise AdapterError("gpu_identity_missing", "SSH launch intent requires exactly one assigned physical GPU UUID")
        if str(preflight.get("assigned_gpu_uuid") or "") != gpu_uuids[0]:
            raise AdapterError("backend_preflight_mismatch", "SSH preflight GPU UUID must match the atomic allocation")
        if preflight.get("assigned_gpu_idle") is not True or preflight.get("full_process_visibility") is not True:
            raise AdapterError(
                "backend_preflight_invalid",
                "SSH preflight must record assigned_gpu_idle=true and full_process_visibility=true",
            )
    elif route == "bjtu_hpc":
        if (
            preflight.get("exact_script_checks_passed") is not True
            or preflight.get("sbatch_test_only_passed") is not True
            or preflight.get("no_queued") is not True
            or nonnegative_int(preflight.get("requested_gpus")) != 1
        ):
            raise AdapterError(
                "backend_preflight_invalid",
                "BJTU preflight requires exact-script checks, sbatch --test-only, no_queued=true, and one requested GPU",
            )
    return preflight


def backend_policy(row: dict[str, Any], campaign: dict[str, Any], route: str) -> tuple[bool, str]:
    containers: list[dict[str, Any]] = []
    for value in (
        row.get("backend_policy"),
        row.get("launch_policy"),
        (row.get("resource_request") or {}).get("backend_policy") if isinstance(row.get("resource_request"), dict) else None,
    ):
        if isinstance(value, dict):
            containers.append(value)
    execution_policy = campaign.get("execution_policy") if isinstance(campaign.get("execution_policy"), dict) else {}
    routes = execution_policy.get("routes") if isinstance(execution_policy.get("routes"), dict) else {}
    route_policy = routes.get(route)
    if isinstance(route_policy, dict):
        containers.append(route_policy)
    for container in containers:
        allowed = container.get("allow_launch") is True or container.get("allow_remote_launch") is True
        ref = first_text(container, ("policy_ref", "ref", "backend_policy_ref"))
        if allowed and ref:
            return True, ref
    if row.get("backend_launch_allowed") is True and str(row.get("backend_policy_ref") or "").strip():
        return True, str(row["backend_policy_ref"])
    return False, ""


def canonical_protected_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    """Mirror the campaign linter's protected scientific launch contract.

    The adapter recomputes this value from candidate source fields.  It never
    treats a copied digest or an arbitrary nested payload as authority.
    """

    rapid = candidate.get("rapid_validation") if isinstance(candidate.get("rapid_validation"), dict) else {}
    resource = rapid.get("resource_request") if isinstance(rapid.get("resource_request"), dict) else {}
    mechanism = candidate.get("mechanism") if isinstance(candidate.get("mechanism"), dict) else {}
    baseline = rapid.get("baseline_code") if isinstance(rapid.get("baseline_code"), dict) else {}
    return {
        "falsifier": mechanism.get("falsifier"),
        "observable_prediction": mechanism.get("predicted_observation"),
        "load_bearing_variable": mechanism.get("load_bearing_variable"),
        "negative_control": candidate.get("negative_control"),
        "baseline": {
            "source_ref": baseline.get("source_ref"),
            "revision": baseline.get("revision"),
            "comparison_label": baseline.get("comparison_label"),
        },
        "dataset": rapid.get("dataset"),
        "metric_policy": rapid.get("metric_policy"),
        "resource_ceiling": {
            "compute_backend": resource.get("compute_backend"),
            "execution_route": resource.get("execution_route"),
            "gpu_count": resource.get("gpu_count"),
            "estimated_gpu_hours": resource.get("estimated_gpu_hours"),
            "walltime_minutes": resource.get("walltime_minutes"),
            "smoke_minutes": resource.get("smoke_minutes"),
        },
        "seed_policy": rapid.get("seed_policy"),
        "evidence_tier": rapid.get("evidence_tier"),
        "outcome_routes": rapid.get("outcome_routes"),
    }


def commitment_sha(candidate: dict[str, Any]) -> str:
    commitments = candidate.get("protected_commitments")
    if not isinstance(commitments, dict):
        raise AdapterError("commitment_hash_missing", "candidate lacks protected_commitments")
    expected_payload = canonical_protected_payload(candidate)
    if commitments.get("payload") != expected_payload:
        raise AdapterError(
            "commitment_payload_mismatch",
            "protected_commitments.payload differs from the candidate's canonical protected fields",
        )
    computed = canonical_sha256(expected_payload)
    nested = str(commitments.get("sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(nested) or nested != computed:
        raise AdapterError(
            "commitment_hash_mismatch",
            "protected_commitments.sha256 must equal the recomputed canonical protected payload digest",
            expected_protected_commitment_sha256=computed,
            observed_protected_commitment_sha256=nested or None,
        )
    for key in ("protected_commitments_sha256", "protected_commitment_sha256", "protected_commitments_hash"):
        copied = str(candidate.get(key) or "").strip().lower()
        if copied and copied != computed:
            raise AdapterError(
                "commitment_hash_mismatch",
                f"candidate.{key} differs from the recomputed protected commitment digest",
            )
    return computed


def queue_row_commitment_sha(row: dict[str, Any]) -> str:
    containers = [row]
    for key in ("external_identity", "launch_identity", "scientific_identity"):
        value = row.get(key)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        for key in (
            "protected_commitment_sha256",
            "protected_commitments_sha256",
            "protected_commitments_hash",
        ):
            value = str(container.get(key) or "").strip().lower()
            if SHA256_RE.fullmatch(value):
                return value
    return ""


def inside_project(path: Path, project: Path) -> bool:
    try:
        path.resolve().relative_to(project)
        return True
    except ValueError:
        return False


def resolve_ar_ref(project: Path, ref: str) -> Path:
    base = (project / ".autoreskill").resolve()
    if not ref or "\\" in ref:
        raise AdapterError("external_gate_invalid", "external gate contains an empty or unsafe artifact ref")
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts:
        raise AdapterError("external_gate_invalid", "external gate artifact refs must remain project-relative")
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise AdapterError("external_gate_invalid", "external gate artifact ref escapes .autoreskill") from exc
    return resolved


def validate_external_gate(project: Path, campaign: dict[str, Any], campaign_sha: str) -> dict[str, Any]:
    gate_path = project / GATE_REL
    gate = read_json(gate_path)
    campaign_ref = CAMPAIGN_REL.as_posix().removeprefix(".autoreskill/")
    expected = {
        "status": "passed",
        "evidence_source_mode": "external_material",
        "lane_attempts_satisfied": True,
        "screening_completed": True,
        "allowed_next_action": "generate_experiment_idea_pool",
        "commit_layout": "content_addressed_v1",
        "campaign_ref": campaign_ref,
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign.get("campaign_id"),
        "campaign_revision": campaign.get("campaign_revision"),
    }
    mismatched = [key for key, value in expected.items() if gate.get(key) != value]
    if mismatched:
        raise AdapterError(
            "external_gate_invalid",
            "launch preparation requires the exact current passed external-material gate",
            fields=mismatched,
        )

    lint_ref = str(gate.get("lint_ref") or "").strip()
    slot_ref = str(gate.get("innovation_slot_map_path") or "").strip()
    lint_sha = str(gate.get("lint_sha256") or "").strip().lower()
    slot_sha = str(gate.get("slot_map_sha256") or "").strip().lower()
    if gate.get("slot_map_ref") != slot_ref:
        raise AdapterError("external_gate_invalid", "slot_map_ref must equal innovation_slot_map_path")
    for ref, digest, stem in (
        (lint_ref, lint_sha, "NON_PAPERNEXUS_IDEA_LINT"),
        (slot_ref, slot_sha, "INNOVATION_SLOT_MAP"),
    ):
        match = COMMITTED_REF_RE.fullmatch(ref)
        if not match or match.group("stem") != stem or match.group("sha") != digest:
            raise AdapterError(
                "external_gate_invalid",
                "gate lint/slot refs must be immutable content-addressed paths named by their SHA-256",
                ref=ref,
            )

    lint_path = resolve_ar_ref(project, lint_ref)
    slot_path = resolve_ar_ref(project, slot_ref)
    if not lint_path.is_file() or file_sha256(lint_path) != lint_sha:
        raise AdapterError("external_gate_invalid", "committed external lint is missing or hash-mismatched")
    if not slot_path.is_file() or file_sha256(slot_path) != slot_sha:
        raise AdapterError("external_gate_invalid", "committed external slot map is missing or hash-mismatched")
    lint_payload = read_json(lint_path)
    slot_payload = read_json(slot_path)
    lint_expected = {
        "complete": True,
        "status": "passed",
        "campaign_ref": campaign_ref,
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign.get("campaign_id"),
        "campaign_revision": campaign.get("campaign_revision"),
        "slot_map_ref": slot_ref,
        "slot_map_sha256": slot_sha,
    }
    slot_expected = {
        "source_mode": "external_material",
        "campaign_ref": campaign_ref,
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign.get("campaign_id"),
        "campaign_revision": campaign.get("campaign_revision"),
    }
    if any(lint_payload.get(key) != value for key, value in lint_expected.items()):
        raise AdapterError("external_gate_invalid", "committed external lint is incomplete or stale")
    if any(slot_payload.get(key) != value for key, value in slot_expected.items()):
        raise AdapterError("external_gate_invalid", "committed external slot map is incomplete or stale")
    return {
        "gate_ref": GATE_REL.as_posix().removeprefix(".autoreskill/"),
        "gate_sha256": file_sha256(gate_path),
        "lint_ref": lint_ref,
        "lint_sha256": lint_sha,
        "slot_map_ref": slot_ref,
        "slot_map_sha256": slot_sha,
    }


IMMUTABLE_INTENT_FIELDS = (
    "schema_version",
    "run_id",
    "experiment_id",
    "track_id",
    "queue_row_id",
    "queue_revision",
    "row_revision",
    "lease_owner",
    "external_campaign_ref",
    "external_campaign_sha256",
    "external_candidate_id",
    "protected_commitment_sha256",
    "external_gate",
    "backend",
    "execution_route",
    "command",
    "working_dir",
    "environment",
    "resource_request",
    "planned_resource_allocation",
    "backend_preflight",
    "resource_pool_id",
    "resource_snapshot_ref",
    "resource_snapshot_sha256",
    "resource_snapshot_source_sha256",
    "resource_snapshot_checked_at",
    "launch_spec",
    "budget",
    "authorization",
    "backend_idempotency_key",
    "evidence_tier",
    "promotion_stage",
    "promotion_decision",
    "launch_authorized",
    "auto_retry_allowed",
    "reconcile_exact_backend_id_before_retry",
    "authority_boundary",
    "session_id",
    "ssh_session_id",
    "anonymous_trace_id",
)


def immutable_intent_payload(intent: dict[str, Any]) -> dict[str, Any]:
    return {key: intent.get(key) for key in IMMUTABLE_INTENT_FIELDS}


def prepare_launch_intent(args: argparse.Namespace) -> dict[str, Any]:
    project = project_root(args.project)
    queue_path = project / QUEUE_REL
    queue = read_json(queue_path)
    row = find_queue_row(queue, str(args.row_id))
    if row is None:
        raise AdapterError("row_missing", f"queue row {args.row_id!r} does not exist")
    observed_queue_revision = queue.get("queue_revision")
    observed_row_sha256 = canonical_sha256(row)
    if str(row.get("status") or "") != "planned":
        raise AdapterError("row_not_planned", "launch intent requires an atomically planned queue row")
    lease_owner = str(row.get("lease_owner") or "").strip()
    lease_expires_at = parse_timestamp(row.get("lease_expires_at"))
    if not lease_owner or lease_expires_at is None or lease_expires_at <= datetime.now(timezone.utc):
        raise AdapterError("lease_invalid", "launch intent requires a live claim-assignment lease with owner and future expiry")
    allocation = row.get("planned_resource_allocation")
    if not isinstance(allocation, dict):
        raise AdapterError("allocation_missing", "row lacks claim-assignment planned_resource_allocation")
    if allocation.get("requires_fresh_backend_preflight") is not True:
        raise AdapterError("allocation_invalid", "planned allocation must require a fresh route-specific backend preflight")
    if str(allocation.get("pool_id") or "") != str(args.pool_id):
        raise AdapterError(
            "pool_mismatch",
            "requested pool differs from the atomically planned allocation",
            planned_pool_id=allocation.get("pool_id"),
        )
    snapshot_identity_fields = (
        "resource_snapshot_sha256",
        "resource_snapshot_source_ref",
        "resource_snapshot_source_sha256",
        "resource_snapshot_checked_at",
    )
    missing_snapshot_identity = [field for field in snapshot_identity_fields if not str(allocation.get(field) or "").strip()]
    if missing_snapshot_identity:
        raise AdapterError(
            "snapshot_identity_missing",
            "planned allocation lacks its captured source resource identity",
            fields=missing_snapshot_identity,
        )
    invalid_snapshot_hashes = [
        field
        for field in ("resource_snapshot_sha256", "resource_snapshot_source_sha256")
        if not SHA256_RE.fullmatch(str(allocation.get(field) or ""))
    ]
    if invalid_snapshot_hashes:
        raise AdapterError(
            "snapshot_identity_invalid",
            "planned allocation resource snapshot hashes must be exact 64-hex SHA-256 values",
            fields=invalid_snapshot_hashes,
        )

    campaign_path = project / CAMPAIGN_REL
    campaign = read_json(campaign_path)
    candidate_id = candidate_id_of(row)
    if not candidate_id:
        candidate_id = str((row.get("external_identity") or {}).get("external_candidate_id") or "").strip() if isinstance(row.get("external_identity"), dict) else ""
    if not candidate_id:
        raise AdapterError("candidate_identity_missing", "queue row lacks external_candidate_id")
    candidate = find_candidate(campaign, candidate_id)
    if candidate is None:
        raise AdapterError("candidate_missing", f"candidate {candidate_id!r} is absent from the current campaign")
    commitment = commitment_sha(candidate)
    row_commitment = queue_row_commitment_sha(row)
    if row_commitment != commitment:
        raise AdapterError(
            "commitment_identity_mismatch",
            "queue row protected commitment SHA-256 is missing or differs from the current campaign candidate",
            expected_protected_commitment_sha256=commitment,
            observed_protected_commitment_sha256=row_commitment or None,
        )
    campaign_sha = file_sha256(campaign_path)
    external_gate = validate_external_gate(project, campaign, campaign_sha)
    row_campaign_shas = identity_values(row, ("external_campaign_sha256", "campaign_sha256"))
    row_campaign_refs = identity_values(row, ("external_campaign_ref", "campaign_ref"))
    canonical_campaign_ref = CAMPAIGN_REL.as_posix().removeprefix(".autoreskill/")
    if campaign_sha not in row_campaign_shas:
        raise AdapterError(
            "campaign_identity_mismatch",
            "queue row is not bound to the current external campaign SHA-256",
            expected_campaign_sha256=campaign_sha,
            observed_campaign_sha256=sorted(row_campaign_shas),
        )
    if not any(value.lstrip("./").endswith(canonical_campaign_ref) for value in row_campaign_refs):
        raise AdapterError(
            "campaign_identity_mismatch",
            "queue row is not bound to the canonical external campaign ref",
            expected_campaign_ref=canonical_campaign_ref,
            observed_campaign_refs=sorted(row_campaign_refs),
        )
    rapid = candidate.get("rapid_validation") if isinstance(candidate.get("rapid_validation"), dict) else {}
    rapid_resource = rapid.get("resource_request") if isinstance(rapid.get("resource_request"), dict) else {}
    seed_policy = rapid.get("seed_policy") if isinstance(rapid.get("seed_policy"), dict) else {}
    if rapid.get("evidence_tier") != "pilot_only" or str(row.get("evidence_tier") or "") != "pilot_only":
        raise AdapterError("claim_boundary_invalid", "rapid-validation candidate and queue row must both be pilot_only")
    if rapid_resource.get("gpu_count") != 1 or nonnegative_int(allocation.get("gpu_count")) != 1:
        raise AdapterError("resource_shape_invalid", "rapid validation is restricted to exactly one GPU")
    if seed_policy.get("planned_seed_count") != 1 or seed_policy.get("retry_reuses_seed") is not True:
        raise AdapterError("seed_policy_invalid", "rapid validation requires one planned seed and retry reuse of that seed")

    request = row.get("resource_request") if isinstance(row.get("resource_request"), dict) else {}
    row_route = str(row.get("execution_route") or "").strip().lower()
    allocation_route = str(allocation.get("execution_route") or "").strip().lower()
    request_route = str(request.get("execution_route") or "").strip().lower()
    candidate_route = str(rapid_resource.get("execution_route") or "").strip().lower()
    route_bindings = {
        "row.execution_route": row_route,
        "planned_resource_allocation.execution_route": allocation_route,
        "resource_request.execution_route": request_route,
        "candidate.rapid_validation.resource_request.execution_route": candidate_route,
    }
    if len(set(route_bindings.values())) != 1 or not row_route:
        raise AdapterError(
            "route_identity_mismatch",
            "row, request, allocation, and protected candidate must bind the same explicit execution route",
            observed=route_bindings,
        )
    route = row_route
    backend = str(allocation.get("backend") or "").strip().lower()
    if route not in {"local", "ssh", "bjtu_hpc"}:
        raise AdapterError("route_invalid", f"unsupported rapid-validation execution route {route!r}")
    allowed_backends = {"local", "local_gpu"} if route == "local" else {route}
    request_backend = str(request.get("backend") or "").strip().lower()
    if backend not in allowed_backends or request_backend not in allowed_backends:
        raise AdapterError(
            "route_identity_mismatch",
            "request/allocation backend must map exactly to the protected execution route",
            execution_route=route,
            allocation_backend=backend or None,
            request_backend=request_backend or None,
        )
    if route == "local":
        backend = "local"
    if str(rapid_resource.get("compute_backend") or "").strip() != "local_gpu":
        raise AdapterError("route_identity_mismatch", "rapid-validation candidate compute_backend must remain local_gpu")

    approval_ref = str(args.approval_ref or "").strip()
    policy_path = project / POLICY_REL
    policy = read_json(policy_path)
    policy_sha256 = file_sha256(policy_path)
    project_policy_allowed = policy.get("allow_remote_experiment_launch") is True
    backend_allowed, backend_policy_ref = backend_policy(row, campaign, route)
    if route in REMOTE_ROUTES:
        failures = []
        if not approval_ref:
            failures.append("current action lacks an explicit approval_ref")
        if not project_policy_allowed:
            failures.append("autopilot policy does not allow remote experiment launch")
        if not backend_allowed:
            failures.append("selected backend policy does not explicitly allow launch with a policy ref")
        if failures:
            raise AdapterError("launch_authority_missing", "three-authority launch gate failed", failures=failures)

    spec_path = Path(args.launch_spec).expanduser().resolve() if args.launch_spec else None
    normalized_spec = validate_launch_spec(launch_spec_for(row, spec_path))
    if normalized_spec.get("seed") != nonnegative_int(seed_policy.get("seed")):
        raise AdapterError("seed_identity_mismatch", "launch spec seed differs from the protected campaign scout seed")
    preflight = validate_backend_preflight(row, allocation, route, normalized_spec)
    estimated_hours = nonnegative_number(allocation.get("estimated_gpu_hours"))
    if estimated_hours is None:
        estimated_hours = first_number(
            row,
            [("resource_request", "estimated_gpu_hours"), ("estimated_gpu_hours",)],
        )
    if estimated_hours is None:
        raise AdapterError("budget_reservation_missing", "planned allocation lacks estimated GPU hours")
    protected_estimated_hours = nonnegative_number(rapid_resource.get("estimated_gpu_hours"))
    if protected_estimated_hours is None or abs(estimated_hours - protected_estimated_hours) > 1e-12:
        raise AdapterError(
            "budget_identity_mismatch",
            "planned allocation estimated GPU hours differ from the protected campaign candidate",
        )
    budget = derive_budget(project, candidate_id=candidate_id, requested_gpu_hours=0.0)
    if not budget["ok"]:
        raise AdapterError("budget_exhausted", "existing planned reservation is outside the locked quick budget", budget=budget)
    if estimated_hours > float(budget["limits"]["locked_candidate_ceiling_gpu_hours"]) + 1e-12:
        raise AdapterError("budget_exhausted", "planned row exceeds the candidate quick ceiling", budget=budget)

    track_id = str(row.get("track_id") or "").strip()
    experiment_id = str(row.get("experiment_id") or "").strip()
    if not track_id or not experiment_id or any(
        value in {".", ".."} or "/" in value or "\\" in value for value in (track_id, experiment_id)
    ):
        raise AdapterError(
            "run_identity_missing",
            "queue row must carry safe, explicit track_id and experiment_id values",
        )
    run_dir = Path(args.run_dir).expanduser()
    if not run_dir.is_absolute():
        run_dir = project / run_dir
    run_dir = run_dir.resolve()
    expected_run_dir = (project / ".autoreskill/coder/experiments" / track_id / experiment_id).resolve()
    if not inside_project(run_dir, project) or run_dir != expected_run_dir:
        raise AdapterError(
            "run_dir_noncanonical",
            "run-dir must equal .autoreskill/coder/experiments/<track_id>/<experiment_id>",
            expected_run_dir=str(expected_run_dir),
        )
    intent_path = run_dir / "REMOTE_RUN.json"

    key_material = {
        "campaign_sha256": campaign_sha,
        "candidate_id": candidate_id,
        "commitment_sha256": commitment,
        "external_gate_sha256": external_gate["gate_sha256"],
        "queue_row_id": args.row_id,
        "row_revision": int(row.get("row_revision") or 0),
        "pool_id": args.pool_id,
        "resource_snapshot_sha256": allocation.get("resource_snapshot_sha256"),
        "backend_preflight_sha256": canonical_sha256(preflight),
        "command_sha256": normalized_spec["command_sha256"],
        "budget_commitment_sha256": budget["budget_commitment_sha256"],
        "approval_ref": approval_ref or None,
        "project_policy_sha256": policy_sha256,
        "backend_policy_ref": backend_policy_ref or None,
    }
    backend_key = canonical_sha256(key_material)
    run_id = f"gpuidea_{backend_key[:16]}"
    session_id = ""
    if route == "ssh":
        session_id = f"ssh_{backend_key[:16]}"
    elif route == "bjtu_hpc":
        session_id = f"hpc_{backend_key[:16]}"
    intent: dict[str, Any] = {
        "schema_version": 1,
        "status": "queued",
        "prepared_at": now_iso(),
        "started_at": "",
        "run_id": run_id,
        "experiment_id": experiment_id,
        "track_id": track_id,
        "queue_row_id": args.row_id,
        "queue_revision": queue.get("queue_revision"),
        "row_revision": row.get("row_revision", 0),
        "lease_owner": row.get("lease_owner"),
        "external_campaign_ref": CAMPAIGN_REL.as_posix().removeprefix(".autoreskill/"),
        "external_campaign_sha256": campaign_sha,
        "external_candidate_id": candidate_id,
        "protected_commitment_sha256": commitment,
        "external_gate": external_gate,
        "backend": backend,
        "execution_route": route,
        "command": shlex.join(normalized_spec["command_argv"]),
        "working_dir": normalized_spec["working_dir"],
        "environment": {
            "ref": normalized_spec["environment_ref"],
            "sha256": normalized_spec["environment_sha256"],
        },
        "resource_request": request,
        "resource_allocation": allocation,
        "planned_resource_allocation": allocation,
        "backend_preflight": preflight,
        "resource_pool_id": allocation.get("pool_id"),
        "resource_snapshot_ref": allocation.get("resource_snapshot_source_ref"),
        "resource_snapshot_sha256": allocation.get("resource_snapshot_sha256"),
        "resource_snapshot_source_sha256": allocation.get("resource_snapshot_source_sha256"),
        "resource_snapshot_checked_at": allocation.get("resource_snapshot_checked_at"),
        "launch_spec": normalized_spec,
        "session_id": session_id,
        "evidence_tier": "pilot_only",
        "promotion_stage": "candidate",
        "promotion_decision": "record_only",
        "budget": {
            "locked_gpu_hours": estimated_hours,
            "budget_commitment_sha256": budget["budget_commitment_sha256"],
            "limits": budget["limits"],
            "usage_at_prepare": budget["usage"],
            "remaining_at_prepare": budget["remaining"],
        },
        "authorization": {
            "approval_ref": approval_ref or None,
            "project_policy_ref": POLICY_REL.as_posix(),
            "project_policy_allowed": project_policy_allowed if route in REMOTE_ROUTES else True,
            "backend_policy_ref": backend_policy_ref or None,
            "backend_policy_allowed": backend_allowed if route in REMOTE_ROUTES else True,
            "all_three_authorities_passed": True,
        },
        "backend_idempotency_key": backend_key,
        "side_effects_performed": False,
        "launch_authorized": True,
        "auto_retry_allowed": False,
        "reconcile_exact_backend_id_before_retry": True,
        "authority_boundary": "queued local intent only; this file does not perform or prove a remote launch",
    }
    if route == "ssh":
        intent["ssh_session_id"] = session_id
    elif route == "bjtu_hpc":
        intent["anonymous_trace_id"] = session_id
    intent["immutable_launch_intent_sha256"] = canonical_sha256(immutable_intent_payload(intent))

    materialize_lock_path = project / MATERIALIZE_LOCK_REL
    queue_lock_path = queue_path.with_suffix(queue_path.suffix + ".lock")
    intent_lock_path = intent_path.with_suffix(intent_path.suffix + ".lock")
    with local_file_lock(materialize_lock_path):
        with local_file_lock(queue_lock_path):
            current_queue = read_json(queue_path)
            current_row = find_queue_row(current_queue, str(args.row_id))
            if (
                current_queue.get("queue_revision") != observed_queue_revision
                or current_row is None
                or canonical_sha256(current_row) != observed_row_sha256
            ):
                raise AdapterError(
                    "queue_cas_mismatch",
                    "queue row or revision changed during launch-intent preparation; reread, revalidate, and retry",
                )
            current_expiry = parse_timestamp(current_row.get("lease_expires_at"))
            if (
                str(current_row.get("status") or "") != "planned"
                or str(current_row.get("lease_owner") or "") != lease_owner
                or current_expiry is None
                or current_expiry <= datetime.now(timezone.utc)
            ):
                raise AdapterError("lease_invalid", "claim-assignment lease expired or changed before intent commit")
            if file_sha256(campaign_path) != campaign_sha or file_sha256(policy_path) != policy_sha256:
                raise AdapterError("authority_cas_mismatch", "campaign or launch policy changed before intent commit")
            if validate_external_gate(project, campaign, campaign_sha) != external_gate:
                raise AdapterError("authority_cas_mismatch", "committed external gate changed before intent commit")
            validate_backend_preflight(current_row, current_row["planned_resource_allocation"], route, normalized_spec)
            refreshed_budget = derive_budget(project, candidate_id=candidate_id, requested_gpu_hours=0.0)
            if not refreshed_budget["ok"] or refreshed_budget.get("budget_commitment_sha256") != budget.get("budget_commitment_sha256"):
                raise AdapterError("budget_cas_mismatch", "runtime budget facts changed before intent commit")

            wrote_new_intent = False
            idempotent_result: dict[str, Any] | None = None
            with local_file_lock(intent_lock_path):
                if intent_path.exists():
                    existing = read_json(intent_path)
                    expected_immutable = immutable_intent_payload(intent)
                    observed_immutable = immutable_intent_payload(existing)
                    expected_immutable_sha = intent["immutable_launch_intent_sha256"]
                    observed_immutable_sha = str(existing.get("immutable_launch_intent_sha256") or "").strip().lower()
                    if (
                        str(existing.get("backend_idempotency_key") or "") == backend_key
                        and str(existing.get("run_id") or "") == run_id
                        and observed_immutable == expected_immutable
                        and observed_immutable_sha == expected_immutable_sha
                        and canonical_sha256(observed_immutable) == expected_immutable_sha
                    ):
                        idempotent_result = {
                            "ok": True,
                            "idempotent": True,
                            "intent_path": source_ref(intent_path, project),
                            "run_id": existing.get("run_id"),
                            "backend_idempotency_key": backend_key,
                            "side_effects_performed": bool(existing.get("side_effects_performed") is True),
                            "status": existing.get("status"),
                        }
                    else:
                        raise AdapterError(
                            "intent_conflict",
                            "REMOTE_RUN.json already exists with a different immutable launch intent; reconcile it instead of overwriting",
                            intent_path=source_ref(intent_path, project),
                            expected_run_id=run_id,
                            observed_run_id=existing.get("run_id"),
                            expected_immutable_launch_intent_sha256=expected_immutable_sha,
                            observed_immutable_launch_intent_sha256=observed_immutable_sha or None,
                        )
                else:
                    atomic_write_json(intent_path, intent, mode=0o600)
                    wrote_new_intent = True

                try:
                    if file_sha256(campaign_path) != campaign_sha or file_sha256(policy_path) != policy_sha256:
                        raise AdapterError("authority_cas_mismatch", "campaign or launch policy changed during intent commit")
                    if validate_external_gate(project, campaign, campaign_sha) != external_gate:
                        raise AdapterError("authority_cas_mismatch", "committed external gate changed during intent commit")
                    post_budget = derive_budget(project, candidate_id=candidate_id, requested_gpu_hours=0.0)
                    if not post_budget["ok"] or post_budget.get("budget_commitment_sha256") != budget.get("budget_commitment_sha256"):
                        raise AdapterError("budget_cas_mismatch", "runtime budget facts changed during intent commit")
                except Exception:
                    if wrote_new_intent and intent_path.exists():
                        written = read_json(intent_path)
                        if (
                            str(written.get("run_id") or "") == run_id
                            and str(written.get("immutable_launch_intent_sha256") or "")
                            == intent["immutable_launch_intent_sha256"]
                        ):
                            intent_path.unlink()
                    raise
                if idempotent_result is not None:
                    return idempotent_result
    return {
        "ok": True,
        "idempotent": False,
        "intent_path": source_ref(intent_path, project),
        "run_id": run_id,
        "backend_idempotency_key": backend_key,
        "side_effects_performed": False,
        "status": "queued",
    }


def write_or_emit_snapshot(args: argparse.Namespace, snapshot: dict[str, Any]) -> int:
    snapshot = canonicalize_snapshot(
        snapshot,
        backend=str(snapshot.get("execution_route") or ""),
        source_ref=str(snapshot.get("source_ref") or ""),
    )
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    if output_path is not None:
        atomic_write_json(output_path, snapshot)
    print(
        json.dumps(
            {
                "ok": True,
                "output_path": str(output_path) if output_path else None,
                "resource_snapshot": snapshot,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_normalize_ssh(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    input_path = Path(args.input).expanduser().resolve()
    snapshot = normalize_ssh_payload(read_json(input_path), project=project, input_path=input_path)
    return write_or_emit_snapshot(args, snapshot)


def cmd_normalize_local(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    input_path = Path(args.input).expanduser().resolve()
    snapshot = normalize_local_payload(read_json(input_path), project=project, input_path=input_path)
    return write_or_emit_snapshot(args, snapshot)


def cmd_normalize_bjtu(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    input_path = Path(args.input).expanduser().resolve()
    snapshot = normalize_bjtu_payload(read_json(input_path), project=project, input_path=input_path)
    return write_or_emit_snapshot(args, snapshot)


def cmd_normalize_for_row(args: argparse.Namespace) -> int:
    project = project_root(args.project)
    queue = read_json(project / QUEUE_REL)
    row = find_queue_row(queue, str(args.row_id))
    if row is None:
        raise AdapterError("row_missing", f"queue row {args.row_id!r} does not exist")
    route = str(
        row.get("execution_route")
        or (row.get("resource_request") or {}).get("execution_route")
        or (row.get("resource_request") or {}).get("backend")
        or ""
    ).strip().lower()
    input_path = Path(args.input).expanduser().resolve()
    payload = read_json(input_path)
    if route == "local":
        snapshot = normalize_local_payload(payload, project=project, input_path=input_path)
    elif route == "ssh":
        snapshot = normalize_ssh_payload(payload, project=project, input_path=input_path)
    elif route == "bjtu_hpc":
        snapshot = normalize_bjtu_payload(payload, project=project, input_path=input_path)
    else:
        raise AdapterError("route_invalid", f"queue row has unsupported execution route {route!r}")
    return write_or_emit_snapshot(args, snapshot)


def cmd_budget_check(args: argparse.Namespace) -> int:
    reserve = finite_number(args.reserve_gpu_hours)
    if reserve is None or reserve < 0:
        raise AdapterError("budget_invalid", "--reserve-gpu-hours must be a nonnegative finite number")
    user_ceiling = finite_number(args.user_ceiling_gpu_hours) if args.user_ceiling_gpu_hours is not None else None
    if args.user_ceiling_gpu_hours is not None and (user_ceiling is None or user_ceiling < 0):
        raise AdapterError("budget_invalid", "--user-ceiling-gpu-hours must be a nonnegative finite number")
    payload = derive_budget(
        project_root(args.project),
        candidate_id=str(args.candidate_id),
        requested_gpu_hours=reserve,
        user_ceiling_gpu_hours=user_ceiling,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def cmd_launch_spec_digest(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    normalized = validate_launch_spec(read_json(input_path))
    print(
        json.dumps(
            {
                "ok": True,
                "input_path": str(input_path),
                "launch_spec_sha256": normalized["launch_spec_sha256"],
                "command_sha256": normalized["command_sha256"],
                "normalized_launch_spec": normalized,
                "side_effects_performed": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_prepare_intent(args: argparse.Namespace) -> int:
    payload = prepare_launch_intent(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    local = sub.add_parser("normalize-local-scan", help="Normalize a captured local-gpu-scan/v1 JSON without probing.")
    local.add_argument("--project", required=True)
    local.add_argument("--input", required=True)
    local.add_argument("--output", help="Optional proposed snapshot output path; the queue is never edited.")
    local.set_defaults(func=cmd_normalize_local)

    ssh = sub.add_parser("normalize-ssh-scan", help="Normalize a captured gpu-idle-scan JSON without scanning.")
    ssh.add_argument("--project", required=True)
    ssh.add_argument("--input", required=True)
    ssh.add_argument("--output", help="Optional proposed snapshot output path; the queue is never edited.")
    ssh.set_defaults(func=cmd_normalize_ssh)

    bjtu = sub.add_parser("normalize-bjtu-plan", help="Normalize a captured BJTU direct-start planner JSON.")
    bjtu.add_argument("--project", required=True)
    bjtu.add_argument("--input", required=True)
    bjtu.add_argument("--output", help="Optional proposed snapshot output path; the queue is never edited.")
    bjtu.set_defaults(func=cmd_normalize_bjtu)

    auto = sub.add_parser(
        "normalize-for-row",
        help="Read one queue row's explicit local/ssh/bjtu_hpc route and normalize its captured observation without mutation.",
    )
    auto.add_argument("--project", required=True)
    auto.add_argument("--row-id", required=True)
    auto.add_argument("--input", required=True)
    auto.add_argument("--output", help="Optional proposed snapshot output path; the queue is never edited.")
    auto.set_defaults(func=cmd_normalize_for_row)

    budget = sub.add_parser("budget-check", help="Derive remaining quick-pilot GPU budget from canonical records.")
    budget.add_argument("--project", required=True)
    budget.add_argument("--candidate-id", required=True)
    budget.add_argument("--reserve-gpu-hours", required=True, type=float)
    budget.add_argument("--user-ceiling-gpu-hours", type=float)
    budget.set_defaults(func=cmd_budget_check)

    digest = sub.add_parser("launch-spec-digest", help="Validate and hash an immutable one-GPU launch spec offline.")
    digest.add_argument("--input", required=True)
    digest.set_defaults(func=cmd_launch_spec_digest)

    intent = sub.add_parser("prepare-launch-intent", help="Persist an idempotent queued REMOTE_RUN intent without launching.")
    intent.add_argument("--project", required=True)
    intent.add_argument("--row-id", required=True)
    intent.add_argument("--pool-id", required=True)
    intent.add_argument("--run-dir", required=True)
    intent.add_argument("--approval-ref", default="")
    intent.add_argument("--launch-spec", help="Optional JSON launch spec; otherwise row.launch_spec is required.")
    intent.set_defaults(func=cmd_prepare_intent)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except AdapterError as exc:
        payload: dict[str, Any] = {"ok": False, "error": {"code": exc.code, "message": exc.message}}
        if exc.details:
            payload["error"]["details"] = exc.details
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
