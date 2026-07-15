#!/usr/bin/env python3
"""Own short-lived AutoResearch project-control or global-admission mutations."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: datetime) -> str:
    return value.isoformat()


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


@contextmanager
def lock(path: Path) -> Any:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def default_global_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    return codex_home / "autoreskill/GLOBAL_ADMISSION_LEASE.json"


def lease_path(args: argparse.Namespace) -> Path:
    if args.project:
        return Path(args.project).expanduser().resolve() / ".autoreskill/control/PROJECT_CONTROL_LEASE.json"
    return Path(args.lease_file).expanduser().resolve() if args.lease_file else default_global_path()


def lease_scope(args: argparse.Namespace) -> str:
    if args.scope:
        return str(args.scope)
    return "project-control" if args.project else "global-admission"


def live_status(payload: dict[str, Any], at: datetime | None = None) -> tuple[bool, str]:
    at = at or now()
    expires = parse_time(payload.get("expires_at"))
    if not payload:
        return False, "missing"
    if expires is None:
        return False, "invalid_expiry"
    if expires <= at:
        return False, "expired"
    return True, "live"


def status_payload(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    live, status = live_status(payload)
    return {
        "ok": True,
        "path": str(path),
        "status": status,
        "live": live,
        "lease": payload or None,
    }


def acquire(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    path = lease_path(args)
    owner = str(args.owner or "").strip()
    operation = str(args.operation or "control_plane_mutation").strip()
    ttl = int(args.ttl_minutes)
    if not owner or ttl <= 0:
        return 3, {"ok": False, "error": "owner is required and ttl-minutes must be positive"}
    with lock(path):
        previous = read_json(path)
        live, previous_status = live_status(previous)
        current_time = now()
        if live and str(previous.get("owner_id") or "") != owner:
            return 2, {
                "ok": False,
                "status": "busy",
                "path": str(path),
                "owner_id": previous.get("owner_id"),
                "operation": previous.get("operation"),
                "expires_at": previous.get("expires_at"),
            }
        same_owner = live and str(previous.get("owner_id") or "") == owner
        revision = int(previous.get("revision") or 0) + (0 if same_owner else 1)
        acquired_at = previous.get("acquired_at") if same_owner else iso(current_time)
        payload = {
            "schema_version": 1,
            "scope": lease_scope(args),
            "owner_id": owner,
            "operation": operation,
            "revision": revision,
            "acquired_at": acquired_at,
            "heartbeat_at": iso(current_time),
            "expires_at": iso(current_time + timedelta(minutes=ttl)),
        }
        if previous and not live and previous_status == "expired" and str(previous.get("owner_id") or "") != owner:
            append_jsonl(
                path.with_suffix(path.suffix + ".recovery.jsonl"),
                {
                    "timestamp": iso(current_time),
                    "action": "expired_lease_takeover",
                    "new_owner_id": owner,
                    "previous_lease": previous,
                    "reconcile_backend_before_retry": True,
                },
            )
        atomic_write(path, payload)
        append_jsonl(
            path.with_suffix(path.suffix + ".audit.jsonl"),
            {
                "timestamp": iso(current_time),
                "action": "renew" if same_owner else "acquire",
                "owner_id": owner,
                "operation": operation,
                "revision": revision,
            },
        )
        return 0, {
            "ok": True,
            "status": "renewed" if same_owner else "acquired",
            "idempotent": same_owner,
            "path": str(path),
            "lease": payload,
        }


def renew(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    path = lease_path(args)
    owner = str(args.owner or "").strip()
    ttl = int(args.ttl_minutes)
    if not owner or ttl <= 0:
        return 3, {"ok": False, "error": "owner is required and ttl-minutes must be positive"}
    with lock(path):
        payload = read_json(path)
        live, status = live_status(payload)
        if not live:
            return 3, {"ok": False, "status": status, "path": str(path), "lease": payload or None}
        if str(payload.get("owner_id") or "") != owner:
            return 2, {"ok": False, "status": "busy", "path": str(path), "owner_id": payload.get("owner_id")}
        current_time = now()
        payload["heartbeat_at"] = iso(current_time)
        payload["expires_at"] = iso(current_time + timedelta(minutes=ttl))
        if args.operation:
            payload["operation"] = str(args.operation)
        atomic_write(path, payload)
        append_jsonl(
            path.with_suffix(path.suffix + ".audit.jsonl"),
            {"timestamp": iso(current_time), "action": "renew", "owner_id": owner, "revision": payload.get("revision")},
        )
        return 0, {"ok": True, "status": "renewed", "path": str(path), "lease": payload}


def release(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    path = lease_path(args)
    owner = str(args.owner or "").strip()
    if not owner:
        return 3, {"ok": False, "error": "owner is required"}
    with lock(path):
        payload = read_json(path)
        if not payload:
            return 0, {"ok": True, "status": "already_released", "idempotent": True, "path": str(path)}
        if str(payload.get("owner_id") or "") != owner:
            return 2, {"ok": False, "status": "busy", "path": str(path), "owner_id": payload.get("owner_id")}
        current_time = now()
        path.unlink(missing_ok=True)
        append_jsonl(
            path.with_suffix(path.suffix + ".audit.jsonl"),
            {
                "timestamp": iso(current_time),
                "action": "release",
                "owner_id": owner,
                "reason": str(args.reason or "lease complete"),
                "released_lease": payload,
            },
        )
        return 0, {"ok": True, "status": "released", "path": str(path), "released_lease": payload}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["acquire", "status", "renew", "release"]:
        item = sub.add_parser(command)
        selector = item.add_mutually_exclusive_group()
        selector.add_argument("--project")
        selector.add_argument("--lease-file")
        item.add_argument("--scope", choices=["project-control", "global-admission"])
        item.add_argument("--owner")
        item.add_argument("--operation")
        item.add_argument("--ttl-minutes", type=int, default=10)
        item.add_argument("--reason")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = lease_path(args)
    if args.command == "status":
        with lock(path):
            code, payload = 0, status_payload(path, read_json(path))
    elif args.command == "acquire":
        code, payload = acquire(args)
    elif args.command == "renew":
        code, payload = renew(args)
    else:
        code, payload = release(args)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
