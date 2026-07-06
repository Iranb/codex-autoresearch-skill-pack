#!/usr/bin/env python3
"""Update .autoreskill repair/async job state after execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from loop_trace import append_trace


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def queue_path(base: Path, kind: str) -> Path:
    return base / ("async_jobs.jsonl" if kind == "async" else "repair_queue.jsonl")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def short_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(compact_json(value).encode("utf-8")).hexdigest()[:16]


def bounded_minutes(value: Any, default: int, *, minimum: int = 1, maximum: int = 24 * 60) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def unwrap_capture(payload: Any) -> Any:
    if isinstance(payload, dict) and "payload" in payload:
        return payload["payload"]
    return payload


def poll_decision_from_payload(payload: Any) -> dict[str, Any]:
    payload = unwrap_capture(payload)
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("poll_interval_decision")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in [
            "selected_interval_minutes",
            "interval_minutes",
            "poll_interval_minutes",
            "recommended_next_poll_minutes",
            "desired_rrule",
            "next_check_at",
            "next_check_after",
            "reason",
            "interval_reason",
            "eta_basis",
            "estimated_next_event_at",
            "estimated_remaining_minutes",
            "expected_finish_at",
            "status",
            "run_status",
            "wait_condition",
            "created_at",
            "updated_at",
        ]:
            if key in payload and key not in merged:
                merged[key] = payload[key]
        return merged
    return payload


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def decision_next_check_at(decision: dict[str, Any]) -> str | None:
    candidates = [
        decision.get("next_check_at"),
        decision.get("next_check_after"),
        decision.get("estimated_next_event_at"),
        decision.get("expected_finish_at"),
    ]
    parsed: list[tuple[datetime, str]] = []
    for value in candidates:
        dt = parse_datetime(value)
        if dt is not None:
            parsed.append((dt, str(value)))
    if parsed:
        current = datetime.now(timezone.utc)
        future = sorted((item for item in parsed if item[0] >= current), key=lambda item: item[0])
        selected = future[0] if future else max(parsed, key=lambda item: item[0])
        return selected[0].isoformat()
    for value in candidates:
        if value:
            return str(value)
    return None


def artifact_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == ".autoreskill":
        return base.parent / path
    return base / value


def artifact_interval(base: Path, artifacts: list[str]) -> dict[str, Any]:
    for artifact in reversed(artifacts):
        payload = read_json(artifact_path(base, artifact), {})
        decision = poll_decision_from_payload(payload)
        if not decision:
            continue
        interval_value = (
            decision.get("selected_interval_minutes")
            or decision.get("interval_minutes")
            or decision.get("poll_interval_minutes")
            or decision.get("recommended_next_poll_minutes")
        )
        if interval_value is None:
            continue
        interval = bounded_minutes(interval_value, 5)
        reason = str(
            decision.get("reason")
            or decision.get("interval_reason")
            or decision.get("eta_basis")
            or "dynamic interval recorded by job artifact"
        ).strip()
        return {
            "artifact": artifact,
            "interval_minutes": interval,
            "reason": reason,
            "next_check_at": decision_next_check_at(decision),
            "desired_rrule": decision.get("desired_rrule"),
            "estimated_remaining_minutes": decision.get("estimated_remaining_minutes"),
            "expected_finish_at": decision.get("expected_finish_at"),
            "external_wait": is_external_wait_decision(decision),
        }
    return {}


def is_external_wait_decision(decision: dict[str, Any]) -> bool:
    text = " ".join(
        str(decision.get(key) or "")
        for key in ["status", "run_status", "wait_condition", "reason", "interval_reason", "eta_basis"]
    ).lower()
    return any(
        marker in text
        for marker in [
            "external_wait",
            "external ssh",
            "external-resource",
            "ssh handshake",
            "batchmode ssh",
            "resource retry",
        ]
    )


PROGRESS_KEYS = [
    "status",
    "run_status",
    "stage",
    "wait_condition",
    "completed",
    "submitted",
    "completed_count",
    "submitted_count",
    "completed_import_count",
    "submitted_import_count",
    "authoritative_sync_completed_count",
    "effective_planned_import_count",
    "queue_position",
    "queued_ahead",
    "last_step",
    "metric_rows",
    "progress",
    "progress_percent",
    "estimated_remaining_minutes",
    "estimated_next_event_at",
    "expected_finish_at",
    "terminal",
]


def parse_runtime_observation_arg(value: str) -> dict[str, Any]:
    if not value:
        return {}
    text = value
    if value.startswith("@"):
        text = Path(value[1:]).expanduser().read_text(encoding="utf-8")
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise SystemExit("--runtime-observation-json must decode to a JSON object")
    nested = loaded.get("runtime_observation")
    if isinstance(nested, dict):
        return dict(nested)
    return loaded


def compact_progress_marker(payload: Any) -> dict[str, Any]:
    payload = unwrap_capture(payload)
    if not isinstance(payload, dict):
        return {}
    decision = poll_decision_from_payload(payload)
    marker: dict[str, Any] = {}
    for source in [payload, decision]:
        if not isinstance(source, dict):
            continue
        for key in PROGRESS_KEYS:
            if key in source and source[key] is not None:
                marker[key] = source[key]
    return marker


def runtime_observation_from_artifacts(
    base: Path,
    row: dict[str, Any],
    args: argparse.Namespace,
    artifacts: list[str],
) -> dict[str, Any]:
    explicit = parse_runtime_observation_arg(args.runtime_observation_json)
    if explicit:
        observation = explicit
    else:
        payload = None
        source_artifact = None
        for artifact in reversed(artifacts):
            candidate = read_json(artifact_path(base, artifact), None)
            if candidate is not None:
                payload = unwrap_capture(candidate)
                source_artifact = artifact
                break
        if payload is None:
            return {}
        marker = compact_progress_marker(payload)
        action_parts = [
            str(args.kind),
            str(row.get("stage") or ""),
            str(row.get("job_id") or args.job_id),
        ]
        for key in ["run_id", "task_id", "batch_id", "selected_task_id"]:
            value = payload.get(key) if isinstance(payload, dict) else None
            if value:
                action_parts.append(str(value))
        observation = {
            "action_signature": ":".join(part for part in action_parts if part),
            "result_signature": short_hash(poll_decision_from_payload(payload) or payload),
            "progress_marker": marker,
            "source_artifact": source_artifact,
        }

    previous = row.get("runtime_observation") if isinstance(row.get("runtime_observation"), dict) else {}
    has_previous = bool(previous)
    same_action = observation.get("action_signature") == previous.get("action_signature")
    same_result = observation.get("result_signature") == previous.get("result_signature")
    same_progress = observation.get("progress_marker") == previous.get("progress_marker")
    if same_action and same_result and same_progress:
        observation["progress_observed"] = False
        observation["stale_poll_count"] = int(previous.get("stale_poll_count", 0) or 0) + 1
    else:
        result_or_marker_changed = has_previous and (not same_result or not same_progress)
        observation.setdefault(
            "progress_observed",
            bool(observation.get("progress_marker")) or result_or_marker_changed,
        )
        observation["stale_poll_count"] = 0
    observation.setdefault("last_progress_at", now() if observation.get("progress_observed") else previous.get("last_progress_at"))
    return observation


def apply_artifact_interval(base: Path, row: dict[str, Any], args: argparse.Namespace, artifacts: list[str]) -> None:
    if args.kind != "async" or not artifacts:
        return
    interval = artifact_interval(base, artifacts)
    if not interval:
        return
    row["result_poll_interval_minutes"] = interval["interval_minutes"]
    row["result_poll_interval_reason"] = f"artifact {interval['artifact']}: {interval['reason']}"
    if interval.get("next_check_at"):
        row["result_next_check_at"] = interval["next_check_at"]
    if interval.get("desired_rrule"):
        row["result_desired_rrule"] = interval["desired_rrule"]
    if interval.get("estimated_remaining_minutes") is not None:
        row["result_estimated_remaining_minutes"] = interval["estimated_remaining_minutes"]
    if interval.get("expected_finish_at"):
        row["result_expected_finish_at"] = interval["expected_finish_at"]

    row["poll_interval_minutes"] = interval["interval_minutes"]
    row["poll_interval_reason"] = row["result_poll_interval_reason"]
    if args.status in {"pending", "running", "retry"}:
        row["next_poll_at"] = interval.get("next_check_at") or (datetime.now(timezone.utc) + timedelta(minutes=interval["interval_minutes"])).isoformat()


def apply_repair_retry_schedule(base: Path, row: dict[str, Any], args: argparse.Namespace, artifacts: list[str]) -> None:
    if args.kind != "repair" or args.status != "retry":
        return
    try:
        attempts = int(row.get("attempts", 0) or 0)
    except (TypeError, ValueError):
        attempts = 0
    row["attempts"] = max(1, attempts)

    interval = artifact_interval(base, artifacts)
    if interval:
        minutes = interval["interval_minutes"]
        row["retry_interval_minutes"] = minutes
        row["retry_interval_reason"] = f"artifact {interval['artifact']}: {interval['reason']}"
        row["next_retry_at"] = interval.get("next_check_at") or (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        if interval.get("external_wait"):
            row["external_wait_attempts"] = int(row.get("external_wait_attempts", 0) or 0) + 1
            row["attempts_do_not_count_reason"] = (
                f"artifact {interval['artifact']} records an external resource wait; "
                "heartbeat retries must not consume the bounded code repair budget"
            )
            row["attempts"] = 1
        else:
            # A previously external resource wait can turn into a local repair
            # once the remote/PaperNexus state becomes terminal. Do not carry
            # the old budget-exemption reason into that new state.
            row.pop("attempts_do_not_count_reason", None)
            row.pop("external_wait_run_id", None)
        if interval.get("desired_rrule"):
            row["result_desired_rrule"] = interval["desired_rrule"]
        if interval.get("estimated_remaining_minutes") is not None:
            row["result_estimated_remaining_minutes"] = interval["estimated_remaining_minutes"]
        if interval.get("expected_finish_at"):
            row["result_expected_finish_at"] = interval["expected_finish_at"]
        return

    minutes = bounded_minutes(row.get("retry_interval_minutes"), 5)
    row["retry_interval_minutes"] = minutes
    row["retry_interval_reason"] = str(
        row.get("retry_interval_reason")
        or f"retry after executed repair attempt: {minutes} minutes"
    )
    row["next_retry_at"] = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def apply_repair_failed_backoff(base: Path, row: dict[str, Any], args: argparse.Namespace, artifacts: list[str]) -> None:
    if args.kind != "repair" or args.status != "failed":
        return
    interval = artifact_interval(base, artifacts)
    if interval:
        minutes = interval["interval_minutes"]
        row["failed_backoff_minutes"] = minutes
        row["failed_backoff_reason"] = f"artifact {interval['artifact']}: {interval['reason']}"
        row["next_retry_at"] = interval.get("next_check_at") or (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        return

    minutes = bounded_minutes(row.get("retry_interval_minutes"), 5)
    row["failed_backoff_minutes"] = minutes
    row["failed_backoff_reason"] = str(
        row.get("failed_backoff_reason")
        or f"failed repair backoff before a same-blocker duplicate may be queued: {minutes} minutes"
    )
    row["next_retry_at"] = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def update_packet_snapshot(base: Path, job: dict[str, Any]) -> None:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        return
    packet_path = base / "job_packets" / f"{job_id}.json"
    packet = read_json(packet_path, None)
    if not isinstance(packet, dict):
        return
    for key in [
        "status",
        "updated_at",
        "artifacts",
        "last_error",
        "next_action",
        "runtime_observation",
    ]:
        if key in job:
            packet[key] = job[key]
    write_json(packet_path, packet)


def update_job(base: Path, path: Path, args: argparse.Namespace) -> dict[str, Any]:
    data = rows(path)
    changed: dict[str, Any] | None = None
    for row in data:
        if row.get("job_id") != args.job_id:
            continue
        row["status"] = args.status
        row["updated_at"] = now()
        if args.artifact:
            artifacts = list(row.get("artifacts") or [])
            for artifact in args.artifact:
                if artifact not in artifacts:
                    artifacts.append(artifact)
            row["artifacts"] = artifacts
        if args.error:
            row["last_error"] = args.error
        if args.next_action:
            row["next_action"] = args.next_action
        apply_artifact_interval(base, row, args, list(row.get("artifacts") or []))
        apply_repair_retry_schedule(base, row, args, list(row.get("artifacts") or []))
        apply_repair_failed_backoff(base, row, args, list(row.get("artifacts") or []))
        observation = runtime_observation_from_artifacts(base, row, args, list(row.get("artifacts") or []))
        if observation:
            row["runtime_observation"] = observation
        changed = dict(row)
    if changed is None:
        raise SystemExit(f"job not found: {args.job_id}")
    write_rows(path, data)
    update_packet_snapshot(base, changed)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--kind", choices=["repair", "async"], required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--status", choices=["pending", "running", "retry", "completed", "failed", "superseded"], required=True)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--error", default="")
    parser.add_argument("--next-action", default="")
    parser.add_argument(
        "--runtime-observation-json",
        default="",
        help="JSON object, or @path, to store as compact runtime_observation",
    )
    args = parser.parse_args()

    base = ar(args.project)
    job = update_job(base, queue_path(base, args.kind), args)
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": job.get("stage"),
            "action": "job_update",
            "details": {
                "job_id": args.job_id,
                "kind": args.kind,
                "status": args.status,
                "artifacts": args.artifact,
                "error": args.error or None,
                "next_action": args.next_action or None,
                "runtime_observation": job.get("runtime_observation"),
            },
        },
    )
    append_trace(
        base,
        event="job_update",
        stage=str(job.get("stage") or ""),
        job_id=args.job_id,
        authority="scripts/goal_job_update.py",
        decision=args.status,
        evidence_refs=args.artifact,
        next_action=args.next_action or str(job.get("next_action") or ""),
        reason=args.error or str(job.get("reason") or ""),
        details={
            "kind": args.kind,
            "status": args.status,
            "artifacts": args.artifact,
            "error": args.error or None,
            "next_action": args.next_action or job.get("next_action"),
            "attempts": job.get("attempts"),
            "runtime_observation": job.get("runtime_observation"),
        },
    )
    print(json.dumps({"ok": True, "job": job}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
