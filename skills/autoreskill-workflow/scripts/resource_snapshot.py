#!/usr/bin/env python3
"""Normalize and conservatively merge captured GPU resource snapshots offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AVAILABLE = {"available", "idle", "ready", "partial"}
BLOCKED = {"blocked", "pending", "queued", "full", "stale", "unreachable", "auth_invalid", "disabled", "unknown"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def raw_pools(payload: dict[str, Any], backend: str) -> list[dict[str, Any]]:
    if isinstance(payload.get("pools"), list):
        return [item for item in payload["pools"] if isinstance(item, dict)]
    pools: list[dict[str, Any]] = []
    for key in ["hosts", "accounts", "nodes", "servers"]:
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            pool = dict(row)
            pool.setdefault("pool_id", row.get("host") or row.get("account") or row.get("node") or f"{backend}-{index}")
            pools.append(pool)
    if pools:
        return pools
    gpus = payload.get("gpus")
    if isinstance(gpus, list):
        return [{"pool_id": f"{backend}-captured", "gpus": gpus}]
    return []


def normalize_pool(raw: dict[str, Any], backend: str, index: int) -> dict[str, Any]:
    gpu_rows = [item for item in raw.get("gpus", []) if isinstance(item, dict)]
    uuids = as_list(raw.get("gpu_uuids"))
    ids = as_list(raw.get("resource_ids"))
    for gpu in gpu_rows:
        uuid = str(gpu.get("uuid") or gpu.get("gpu_uuid") or "").strip()
        resource_id = str(gpu.get("resource_id") or gpu.get("id") or gpu.get("index") or "").strip()
        if uuid and uuid not in uuids:
            uuids.append(uuid)
        if resource_id and resource_id not in ids:
            ids.append(resource_id)
    slots = None
    for key in ["launch_slots", "available_gpu_slots", "idle_gpu_count", "free_gpu_count"]:
        if raw.get(key) is not None:
            slots = nonnegative_int(raw.get(key))
            break
    if slots is None:
        idle = [
            gpu
            for gpu in gpu_rows
            if gpu.get("idle") is True
            or str(gpu.get("status") or "").strip().lower() in {"idle", "available", "free"}
        ]
        slots = len(idle) if gpu_rows else 0
    status = str(raw.get("status") or ("available" if slots else "full")).strip().lower()
    if status not in AVAILABLE | BLOCKED:
        status = "blocked"
    route = str(raw.get("execution_route") or backend).strip().lower()
    pool = {
        **raw,
        "pool_id": str(raw.get("pool_id") or f"{backend}-pool-{index}"),
        "backend": str(raw.get("backend") or backend).strip().lower(),
        "execution_route": route,
        "status": status,
        "launch_slots": slots,
        "gpu_uuids": sorted(set(uuids)),
        "resource_ids": sorted(set(ids)),
    }
    return pool


def canonicalize_snapshot(payload: dict[str, Any], backend: str | None = None, source_ref: str | None = None) -> dict[str, Any]:
    inner = payload.get("resource_snapshot") if isinstance(payload.get("resource_snapshot"), dict) else payload
    route = str(backend or inner.get("execution_route") or inner.get("backend") or "local").strip().lower()
    pools = [normalize_pool(item, route, index) for index, item in enumerate(raw_pools(inner, route))]
    checked_at = str(inner.get("checked_at") or inner.get("captured_at") or now_iso())
    fresh = inner.get("fresh") is True and inner.get("stale") is not True
    if "fresh" not in inner and "stale" not in inner:
        fresh = True
    snapshot = {
        **inner,
        "schema_version": 1,
        "kind": "proposed_resource_snapshot",
        "execution_route": route,
        "source_ref": source_ref or inner.get("source_ref"),
        "checked_at": checked_at,
        "fresh": fresh,
        "stale": not fresh,
        "status": "fresh" if fresh else "stale",
        "pools": sorted(pools, key=lambda item: str(item.get("pool_id") or "")),
    }
    snapshot["source_sha256"] = str(inner.get("source_sha256") or canonical_sha256(payload))
    snapshot["resource_snapshot_sha256"] = canonical_sha256(
        {key: value for key, value in snapshot.items() if key != "resource_snapshot_sha256"}
    )
    return snapshot


def physical_keys(pool: dict[str, Any]) -> set[str]:
    keys = {f"gpu:{value}" for value in as_list(pool.get("gpu_uuids"))}
    if not keys:
        keys = {f"resource:{value}" for value in as_list(pool.get("resource_ids"))}
    if not keys:
        keys = {f"pool:{pool.get('pool_id')}"}
    return keys


def merge_pool(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    statuses = {str(left.get("status") or ""), str(right.get("status") or "")}
    status = "blocked" if any(value in BLOCKED for value in statuses) else "available"
    return {
        **left,
        "status": status,
        "launch_slots": min(nonnegative_int(left.get("launch_slots")), nonnegative_int(right.get("launch_slots"))),
        "gpu_uuids": sorted(set(as_list(left.get("gpu_uuids")) + as_list(right.get("gpu_uuids")))),
        "resource_ids": sorted(set(as_list(left.get("resource_ids")) + as_list(right.get("resource_ids")))),
        "alias_pool_ids": sorted(set(as_list(left.get("alias_pool_ids")) + as_list(right.get("alias_pool_ids")) + [str(right.get("pool_id") or "")])),
        "duplicate_physical_resource_merged": True,
    }


def conservative_merge(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    for snapshot in snapshots:
        for raw in snapshot.get("pools", []):
            if not isinstance(raw, dict):
                continue
            keys = physical_keys(raw)
            match = next((item for item in merged if physical_keys(item) & keys), None)
            if match is None:
                merged.append(dict(raw))
            else:
                replacement = merge_pool(match, raw)
                merged[merged.index(match)] = replacement
    fresh = bool(snapshots) and all(item.get("fresh") is True and item.get("stale") is not True for item in snapshots)
    output = {
        "schema_version": 1,
        "kind": "merged_resource_snapshot",
        "checked_at": now_iso(),
        "fresh": fresh,
        "stale": not fresh,
        "status": "fresh" if fresh else "stale",
        "source_snapshot_sha256s": sorted(str(item.get("resource_snapshot_sha256") or canonical_sha256(item)) for item in snapshots),
        "pools": sorted(merged, key=lambda item: str(item.get("pool_id") or "")),
    }
    output["resource_snapshot_sha256"] = canonical_sha256(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    normalize = sub.add_parser("normalize")
    normalize.add_argument("--input", required=True)
    normalize.add_argument("--backend")
    normalize.add_argument("--out", required=True)
    merge = sub.add_parser("merge")
    merge.add_argument("--input", action="append", required=True)
    merge.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "normalize":
        source = Path(args.input).expanduser().resolve()
        result = canonicalize_snapshot(read_json(source), args.backend, str(source))
    else:
        result = conservative_merge(
            [canonicalize_snapshot(read_json(Path(value).expanduser().resolve()), source_ref=str(Path(value).expanduser().resolve())) for value in args.input]
        )
    out = Path(args.out).expanduser().resolve()
    atomic_write_json(out, result)
    print(json.dumps({"ok": True, "out": str(out), "pool_count": len(result.get("pools") or []), "resource_snapshot_sha256": result.get("resource_snapshot_sha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
