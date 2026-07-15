#!/usr/bin/env python3
"""Record local/remote experiment run metadata and reconcile ledgers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


QUEUE_HELPER = Path(__file__).resolve().parents[2] / "autoreskill-workflow/scripts/experiment_next_actions.py"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def monitor_plan_semantic_sha256(payload: dict[str, Any]) -> str:
    semantic = json.loads(json.dumps(payload))
    for key in [
        "monitor_plan_revision",
        "monitor_plan_semantic_sha256",
        "prompt",
        "prompt_plan_revision",
        "prompt_plan_sha256",
        "prompt_sha256",
    ]:
        semantic.pop(key, None)
    scheduled = semantic.get("scheduled_wakeup")
    if isinstance(scheduled, dict):
        for key in ["prompt", "prompt_plan_revision", "prompt_plan_sha256", "prompt_sha256"]:
            scheduled.pop(key, None)
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


LOG_SUFFIXES = {".log", ".txt", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".out", ".err"}
CHECKPOINT_SUFFIXES = {".pt", ".pth", ".ckpt", ".safetensors", ".bin", ".onnx"}
CHECKPOINT_PARTS = {"checkpoint", "checkpoints"}


def is_checkpoint_like(raw: str) -> bool:
    text = raw.strip().lower()
    parts = {part for part in re.split(r"[/\\]+", text) if part}
    if parts & CHECKPOINT_PARTS:
        return True
    return Path(text).suffix in CHECKPOINT_SUFFIXES


def is_lightweight_log(raw: str) -> bool:
    if is_checkpoint_like(raw):
        return False
    suffix = Path(raw.strip()).suffix.lower()
    return suffix in LOG_SUFFIXES


def git_capture(project: str, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=Path(project).expanduser().resolve(),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def shell_quote_single(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def ssh_target(remote: dict[str, Any], manifest: dict[str, Any], args: argparse.Namespace) -> tuple[str | None, int | None]:
    host = args.ssh_host or remote.get("ssh_host") or manifest.get("ssh_host")
    port_value: Any = args.ssh_port or remote.get("ssh_port") or manifest.get("ssh_port")
    user = args.ssh_user or remote.get("ssh_user") or manifest.get("ssh_user") or "root"
    if not host:
        raw_host = str(remote.get("host") or manifest.get("host") or "").strip()
        if raw_host:
            if raw_host.startswith("seetacloud:"):
                port_value = port_value or raw_host.split(":", 1)[1]
                host = "connect.bjb2.seetacloud.com"
            elif ":" in raw_host and not raw_host.count(":") > 1:
                maybe_host, maybe_port = raw_host.rsplit(":", 1)
                host = maybe_host
                port_value = port_value or maybe_port
            else:
                host = raw_host
    if not host:
        return None, None
    try:
        port = int(port_value) if port_value else None
    except (TypeError, ValueError):
        port = None
    return f"{user}@{host}", port


def sync_one_log(target: str, port: int | None, remote_path: str, local_path: Path) -> dict[str, Any]:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    remote_spec = f"{target}:{shell_quote_single(remote_path)}"
    ssh_cmd = "ssh"
    if port:
        ssh_cmd += f" -p {port}"
    rsync_cmd = ["rsync", "-az", "-e", ssh_cmd, remote_spec, str(local_path)]
    try:
        proc = subprocess.run(rsync_cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        scp_cmd = ["scp"]
        if port:
            scp_cmd.extend(["-P", str(port)])
        scp_cmd.extend([f"{target}:{remote_path}", str(local_path)])
        try:
            proc = subprocess.run(scp_cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            return {"remote": remote_path, "local": str(local_path), "status": "failed", "reason": str(exc)}
    if proc.returncode == 0:
        return {"remote": remote_path, "local": str(local_path), "status": "synced", "reason": ""}
    return {"remote": remote_path, "local": str(local_path), "status": "failed", "reason": (proc.stderr or proc.stdout).strip()[-500:]}


def collect_log_paths(remote: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ["log_paths", "result_paths"]:
        value = remote.get(key) or manifest.get(key) or []
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if item)
    for component in remote.get("run_components") or manifest.get("run_components") or []:
        if not isinstance(component, dict):
            continue
        for key in ["nohup_log", "train_log", "command_path", "metrics_path", "result_path"]:
            if component.get(key):
                candidates.append(str(component[key]))
    seen: set[str] = set()
    out: list[str] = []
    for raw in candidates:
        text = raw.strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def sync_remote_logs(exp_dir: Path, remote: dict[str, Any], previous: dict[str, Any], manifest: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    policy = {
        "status": "not_required",
        "synced_at": now(),
        "policy": "sync logs and lightweight text/metadata only; checkpoints excluded by default",
        "included_suffixes": sorted(LOG_SUFFIXES),
        "excluded_patterns": ["checkpoint/", "checkpoints/", "*.pt", "*.pth", "*.ckpt", "*.safetensors", "*.bin", "*.onnx"],
        "items": [],
    }
    if not args.sync_logs or args.backend == "local":
        policy["status"] = "skipped"
        return policy, []
    merged_remote = {**previous, **remote}
    target, port = ssh_target(merged_remote, manifest, args)
    if not target:
        policy["status"] = "failed"
        policy["items"].append({"remote": "", "local": "", "status": "failed", "reason": "missing ssh target"})
        return policy, []
    sync_root = exp_dir / "logs" / "synced"
    items: list[dict[str, Any]] = []
    local_paths: list[str] = []
    for remote_path in collect_log_paths(merged_remote, manifest):
        if is_checkpoint_like(remote_path):
            items.append({"remote": remote_path, "local": "", "status": "skipped", "reason": "checkpoint/model artifact excluded"})
            continue
        if not is_lightweight_log(remote_path):
            items.append({"remote": remote_path, "local": "", "status": "skipped", "reason": "not a recognized lightweight log suffix"})
            continue
        local_path = sync_root / Path(remote_path.replace("~", "HOME")).name
        row = sync_one_log(target, port, remote_path, local_path)
        items.append(row)
        if row["status"] == "synced":
            local_paths.append(str(local_path.relative_to(exp_dir)))
    policy["items"] = items
    synced = sum(1 for item in items if item.get("status") == "synced")
    failed = sum(1 for item in items if item.get("status") == "failed")
    if synced and not failed:
        policy["status"] = "synced"
    elif synced and failed:
        policy["status"] = "partial"
    elif failed:
        policy["status"] = "failed"
    else:
        policy["status"] = "skipped"
    return policy, local_paths


def resolve_project_path(project: str, raw: str) -> Path:
    root = Path(project).expanduser().resolve()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return root / raw


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protected_hashes(project: str, manifest: dict[str, Any], review: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("protected_paths") or review.get("protected_paths") or []
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, dict):
            raw = str(row.get("path") or "").strip()
            expected = row.get("sha256")
            purpose = row.get("purpose")
        else:
            raw = str(row).strip()
            expected = None
            purpose = None
        if not raw:
            continue
        path = resolve_project_path(project, raw)
        actual = sha256_file(path)
        out.append(
            {
                "path": raw,
                "purpose": purpose,
                "exists": path.exists(),
                "sha256": actual,
                "expected_sha256": expected,
                "matches_expected": bool(not expected or actual == expected),
            }
        )
    return out


def number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalized_status(value: Any) -> str:
    raw = str(value or "running").strip().lower()
    return "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_") or "running"


def parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def inferred_remaining_minutes(
    explicit: float | None,
    previous_remote: dict[str, Any],
    checked_at: datetime,
) -> float | None:
    if explicit is not None:
        return explicit
    previous_monitoring = previous_remote.get("monitoring") if isinstance(previous_remote.get("monitoring"), dict) else {}
    previous_remaining = number(previous_monitoring.get("estimated_remaining_minutes"))
    if previous_remaining is None:
        previous_remaining = number(previous_remote.get("estimated_remaining_minutes"))
    if previous_remaining is not None:
        previous_checked = parse_iso(previous_monitoring.get("last_checked_at") or previous_remote.get("updated_at") or previous_remote.get("created_at"))
        if previous_checked is not None:
            elapsed = max(0.0, (checked_at - previous_checked).total_seconds() / 60)
            return max(0.0, previous_remaining - elapsed)
        return previous_remaining
    runtime = number(previous_remote.get("estimated_runtime_minutes"))
    started_at = parse_iso(previous_remote.get("started_at") or previous_remote.get("created_at"))
    if runtime is not None and started_at is not None:
        elapsed = max(0.0, (checked_at - started_at).total_seconds() / 60)
        return max(0.0, runtime - elapsed)
    return None


def compute_monitoring_plan(
    *,
    project_root: Path,
    base: Path,
    remote_run_path: Path,
    remote: dict[str, Any],
    existing_registry: dict[str, Any],
    automation_id: str,
    estimated_remaining_minutes: float | None,
    last_progress_at: str | None,
) -> dict[str, Any]:
    checked_at = datetime.now(timezone.utc)
    status = normalized_status(remote.get("status"))
    backend = normalized_status(remote.get("backend"))
    previous = remote.get("monitoring") if isinstance(remote.get("monitoring"), dict) else {}
    terminal = status in {
        "completed",
        "complete",
        "done",
        "succeeded",
        "success",
        "failed",
        "failure",
        "cancelled",
        "canceled",
        "stopped",
        "timeout",
        "timed_out",
        "budget_stopped",
        "killed",
    }
    previous_stale_count = number(previous.get("stale_count")) or 0
    progress_at = parse_iso(last_progress_at or remote.get("updated_at") or remote.get("created_at"))
    paid = backend in {"autodl", "autodl_gpu"} or remote.get("paid_resource") is True
    stale_threshold_minutes = 10 if paid else 20
    progress_age_minutes = (
        (checked_at - progress_at).total_seconds() / 60 if progress_at else None
    )
    stale = progress_age_minutes is not None and progress_age_minutes >= stale_threshold_minutes
    stale_count = int(previous_stale_count + 1) if stale else 0

    interval: int | None
    reason: str
    monitor_status = "active"
    if terminal:
        monitor_status = "paused"
        interval = None
        reason = "terminal_status_pause_monitor"
    elif status in {"queued", "submitted", "pending", "waiting"}:
        interval = 30 if backend in {"bjtu_hpc", "hpc"} else 15
        reason = "queued_hpc_backoff" if interval == 30 else "queued_scheduler_wait"
    elif status in {"launching", "provisioning", "starting", "submitted_running"}:
        interval = 3
        reason = "startup_or_provisioning_fast_check"
    elif status in {"stale", "hung", "no_progress"}:
        interval = 3
        reason = "explicit_stale_fast_check"
    elif stale:
        interval = 3 if paid else 5
        reason = "paid_resource_no_progress_fast_check" if paid else "no_recent_progress_check"
    elif estimated_remaining_minutes is not None:
        interval = max(1, int(round(estimated_remaining_minutes)))
        reason = "stable_training_estimated_finish_wakeup"
    else:
        interval = 15
        reason = "running_without_eta_default"
    expected_finish_at = (
        (checked_at + timedelta(minutes=estimated_remaining_minutes)).isoformat()
        if estimated_remaining_minutes is not None
        else None
    )

    slug = "".join(ch if ch.isalnum() else "-" for ch in project_root.name.lower()).strip("-") or "project"
    automation_key = existing_registry.get("automation_key") or f"autoreskill-experiment-monitor:{slug}"
    automation_name = existing_registry.get("automation_name") or automation_key
    persisted_automation_id = automation_id or str(existing_registry.get("automation_id") or "").strip() or None
    next_check_at = (
        (checked_at + timedelta(minutes=interval)).isoformat() if interval is not None else None
    )
    desired_rrule = f"FREQ=MINUTELY;INTERVAL={interval}" if interval is not None else None
    action = (
        "update"
        if monitor_status == "active" and persisted_automation_id
        else "create"
        if monitor_status == "active"
        else "pause"
        if persisted_automation_id
        else "none"
    )
    monitoring = {
        "schema_version": 1,
        "status": monitor_status,
        "last_checked_at": checked_at.isoformat(),
        "next_check_at": next_check_at,
        "interval_minutes": interval,
        "desired_rrule": desired_rrule,
        "cadence_reason": reason,
        "estimated_remaining_minutes": estimated_remaining_minutes,
        "expected_finish_at": expected_finish_at,
        "stale_count": stale_count,
        "last_progress_at": last_progress_at,
        "automation": {
            "key": automation_key,
            "name": automation_name,
            "kind": "heartbeat",
            "destination": "thread",
            "action": action,
            "automation_id": persisted_automation_id,
            "desired_rrule": desired_rrule,
        },
    }
    relative_run_path = str(remote_run_path.relative_to(base))
    registry_path = base / "automation_registry.json"
    runs = [
        row for row in existing_registry.get("runs", [])
        if isinstance(row, dict) and row.get("remote_run_path") != relative_run_path
    ]
    runs.append(
        {
            "remote_run_path": relative_run_path,
            "experiment_id": remote.get("experiment_id"),
            "status": status,
            "monitor_status": monitor_status,
            "interval_minutes": interval,
            "next_check_at": next_check_at,
            "cadence_reason": reason,
            "updated_at": checked_at.isoformat(),
        }
    )
    write_json(
        registry_path,
        {
            "schema_version": 1,
            "automation_key": automation_key,
            "automation_name": automation_name,
            "automation_id": persisted_automation_id,
            "kind": "heartbeat",
            "destination": "thread",
            "status": monitor_status,
            "desired_rrule": desired_rrule,
            "interval_minutes": interval,
            "next_check_at": next_check_at,
            "active_remote_run_path": relative_run_path if monitor_status == "active" else None,
            "active_experiment_id": remote.get("experiment_id") if monitor_status == "active" else None,
            "last_cadence_reason": reason,
            "updated_at": checked_at.isoformat(),
            "prompt": (
                "Monitor the active AutoResearch experiment for this project. "
                f"Project root: {project_root}. Registry: .autoreskill/automation_registry.json. "
                "Read the registry and active REMOTE_RUN.json, check job/GPU/log status, "
                "run run_reconcile.py or record durable runtime signals, and update the same "
                "monitor automation instead of creating a duplicate."
            ),
            "runs": runs,
        },
    )
    monitor_plan_path = base / "experiment/EXPERIMENT_MONITOR_PLAN.json"
    previous_monitor_plan = read_json(monitor_plan_path, {})
    monitor_plan = {
            "schema_version": 1,
            "run_id": remote.get("run_id") or remote.get("experiment_id") or relative_run_path,
            "remote_run_path": relative_run_path,
            "backend": backend,
            "estimated_runtime_minutes": remote.get("estimated_runtime_minutes"),
            "estimated_remaining_minutes": estimated_remaining_minutes,
            "expected_finish_at": expected_finish_at,
            "state": status,
            "monitor_id": persisted_automation_id,
            "automation_kind": "heartbeat",
            "reuse_policy": {
                "key": automation_key,
                "reuse_existing_monitor": True,
                "no_duplicate_monitor_per_run": True,
                "action": action,
            },
            "check_interval_policy": {
                "interval_minutes": interval,
                "desired_rrule": desired_rrule,
                "reason": reason,
                "adaptive_inputs": {
                    "backend": backend,
                    "paid_resource": paid,
                    "progress_age_minutes": progress_age_minutes,
                    "stale_count": stale_count,
                    "estimated_remaining_minutes": estimated_remaining_minutes,
                    "expected_finish_at": expected_finish_at,
                    "eta_scheduler_mode": "completion_wakeup" if estimated_remaining_minutes is not None else None,
                    "completion_buffer_minutes": 0 if estimated_remaining_minutes is not None else None,
                    "completion_wakeup_interval_minutes": interval if estimated_remaining_minutes is not None else None,
                },
            },
            "last_check_at": checked_at.isoformat(),
            "next_check_after": next_check_at,
            "stop_conditions": ["completed", "failed", "cancelled", "timeout", "budget_stopped"],
            "escalation_conditions": [
                "stalled_no_log_growth",
                "paid_resource_no_progress",
                "missing_remote_run_status",
                "metric_dataset_baseline_drift",
            ],
            "registry_path": "automation_registry.json",
            "status": monitor_status,
        }
    monitor_plan_sha256 = monitor_plan_semantic_sha256(monitor_plan)
    previous_revision = int(previous_monitor_plan.get("monitor_plan_revision") or 0) if isinstance(previous_monitor_plan, dict) else 0
    previous_sha256 = (
        str(previous_monitor_plan.get("monitor_plan_semantic_sha256") or "")
        if isinstance(previous_monitor_plan, dict)
        else ""
    )
    monitor_plan["monitor_plan_revision"] = previous_revision + (0 if previous_sha256 == monitor_plan_sha256 else 1)
    monitor_plan["monitor_plan_semantic_sha256"] = monitor_plan_sha256
    write_json(monitor_plan_path, monitor_plan)
    return monitoring


def read_metrics(exp_dir: Path) -> tuple[dict[str, Any], str | None]:
    for rel in ["results/metrics.json", "results/metrics_summary.json"]:
        path = exp_dir / rel
        data = read_json(path, None)
        if isinstance(data, dict):
            return data, rel
    return {}, None


def metric_payload(metrics: dict[str, Any], direction: str) -> dict[str, Any]:
    baseline_raw = metrics.get("baseline") if "baseline" in metrics else metrics.get("baseline_result")
    proposed_raw = metrics.get("proposed") if "proposed" in metrics else metrics.get("proposed_result")
    baseline = number(baseline_raw)
    proposed = number(proposed_raw)
    primary = number(metrics.get("primary_metric"))
    if proposed is None:
        proposed = primary
    score_delta = None
    improved = None
    if baseline is not None and proposed is not None:
        score_delta = proposed - baseline
        improved = score_delta > 0 if direction != "lower" else score_delta < 0
    return {
        "baseline": baseline,
        "proposed": proposed,
        "primary_metric": primary,
        "score_delta": score_delta,
        "improved": improved,
    }


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def first_present(*values: Any) -> Any:
    for value in values:
        if present(value):
            return value
    return None


def normalize_stage(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "candidate_supported": "candidate",
        "pilot": "candidate",
        "ablation_check": "ablation",
        "mechanism_ablation": "ablation",
        "confirm": "confirmation",
        "confirmed": "confirmation",
        "multi_seed": "confirmation",
        "repeat": "confirmation",
    }
    text = aliases.get(text, text)
    return text if text in {"candidate", "ablation", "confirmation"} else "candidate"


def normalize_mechanism_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"ALGO", "CODE", "PARAM"} else "ALGO"


def run_identity(manifest: dict[str, Any], review: dict[str, Any], innovation: dict[str, Any]) -> dict[str, Any]:
    manifest_contract = as_dict(manifest.get("innovation_search_contract"))
    review_contract = as_dict(review.get("innovation_search_contract"))
    innovation_contract = as_dict(innovation.get("innovation_search_contract"))
    contract = manifest_contract or review_contract or innovation_contract
    gate = as_dict(review.get("promotion_gate"))
    hpo_search_policy = (
        as_dict(manifest.get("hpo_search_policy"))
        or as_dict(review.get("hpo_search_policy"))
        or as_dict(innovation.get("hpo_search_policy"))
        or as_dict(contract.get("hpo_search_policy"))
    )
    hpo_trial = as_dict(manifest.get("hpo_trial")) or as_dict(manifest.get("dehb_trial"))
    planned_allocation = as_dict(manifest.get("planned_resource_allocation"))
    external_identity = (
        as_dict(manifest.get("external_identity"))
        or as_dict(review.get("external_identity"))
        or as_dict(innovation.get("external_identity"))
    )
    selected_idea_id = first_present(
        manifest.get("selected_idea_id"),
        manifest.get("selected_candidate_id"),
        contract.get("selected_idea_id"),
        contract.get("idea_id"),
        review.get("selected_idea_id"),
        innovation.get("selected_idea_id"),
    )
    track_id = first_present(
        manifest.get("track_id"),
        contract.get("track_id"),
        review.get("track_id"),
        innovation.get("track_id"),
        innovation.get("selected_idea_fragment_id"),
    )
    stage = normalize_stage(first_present(manifest.get("promotion_stage"), contract.get("promotion_stage"), gate.get("stage")))
    return {
        "run_id": first_present(manifest.get("run_id"), manifest.get("experiment_id")),
        "track_id": track_id,
        "track_role": first_present(manifest.get("track_role"), review.get("track_role"), innovation.get("track_role")),
        "idea_lifecycle_status": first_present(
            manifest.get("idea_lifecycle_status"),
            review.get("idea_lifecycle_status"),
            innovation.get("idea_lifecycle_status"),
        ),
        "evidence_tier_ceiling": first_present(
            manifest.get("evidence_tier_ceiling"),
            review.get("evidence_tier_ceiling"),
            innovation.get("evidence_tier_ceiling"),
        ),
        "idea_decision_ref": first_present(
            manifest.get("idea_decision_ref"), review.get("idea_decision_ref"), innovation.get("idea_decision_ref")
        ),
        "source_track_seed_ref": first_present(
            manifest.get("source_track_seed_ref"),
            review.get("source_track_seed_ref"),
            innovation.get("source_track_seed_ref"),
        ),
        "source_track_seed_sha256": first_present(
            manifest.get("source_track_seed_sha256"),
            review.get("source_track_seed_sha256"),
            innovation.get("source_track_seed_sha256"),
        ),
        "track_plan_ref": manifest.get("track_plan_ref"),
        "track_plan_matrix_sha256": manifest.get("track_plan_matrix_sha256"),
        "branch_id": first_present(manifest.get("branch_id"), contract.get("branch_id"), review.get("branch_id")),
        "queue_row_id": first_present(manifest.get("queue_row_id"), contract.get("queue_row_id"), review.get("queue_row_id")),
        "selection_fingerprint": first_present(
            manifest.get("selection_fingerprint"),
            manifest.get("selected_primary_ref"),
            contract.get("selection_fingerprint"),
            contract.get("selected_primary_ref"),
            review.get("selection_fingerprint"),
            review.get("selected_primary_ref"),
            innovation.get("selection_fingerprint"),
            innovation.get("selected_primary_ref"),
        ),
        "launch_identity_hash": first_present(
            manifest.get("launch_identity_hash"), contract.get("launch_identity_hash"), review.get("launch_identity_hash")
        ),
        "selected_idea_id": selected_idea_id,
        "innovation_search_contract": contract,
        "innovation_mechanism": first_present(
            manifest.get("innovation_mechanism"),
            contract.get("innovation_mechanism"),
            review.get("innovation_mechanism"),
            innovation.get("innovation_mechanism"),
            manifest.get("one_variable_change_description"),
            innovation.get("one_variable_change"),
        ),
        "mechanism_type": normalize_mechanism_type(
            first_present(manifest.get("mechanism_type"), contract.get("mechanism_type"), review.get("mechanism_type"), innovation.get("mechanism_type"))
        ),
        "promotion_stage": stage,
        "ablation_of": first_present(manifest.get("ablation_of"), review.get("ablation_of"), innovation.get("ablation_of")),
        "confirmation_of": first_present(manifest.get("confirmation_of"), review.get("confirmation_of"), innovation.get("confirmation_of")),
        "hpo_search_policy": hpo_search_policy,
        "hpo_trial": hpo_trial,
        "evidence_source_mode": first_present(
            manifest.get("evidence_source_mode"),
            external_identity.get("evidence_source_mode"),
            review.get("evidence_source_mode"),
            innovation.get("evidence_source_mode"),
        ),
        "external_campaign_ref": first_present(
            manifest.get("external_campaign_ref"),
            external_identity.get("external_campaign_ref"),
            review.get("external_campaign_ref"),
            innovation.get("external_campaign_ref"),
        ),
        "external_campaign_sha256": first_present(
            manifest.get("external_campaign_sha256"),
            external_identity.get("external_campaign_sha256"),
            review.get("external_campaign_sha256"),
            innovation.get("external_campaign_sha256"),
        ),
        "external_candidate_id": first_present(
            manifest.get("external_candidate_id"),
            external_identity.get("external_candidate_id"),
            review.get("external_candidate_id"),
            innovation.get("external_candidate_id"),
        ),
        "protected_commitment_sha256": first_present(
            manifest.get("protected_commitment_sha256"),
            external_identity.get("protected_commitment_sha256"),
            review.get("protected_commitment_sha256"),
            innovation.get("protected_commitment_sha256"),
        ),
        "evidence_tier": first_present(
            manifest.get("evidence_tier"),
            contract.get("evidence_tier"),
            review.get("evidence_tier"),
            innovation.get("evidence_tier"),
            "pilot_only"
            if first_present(
                manifest.get("evidence_tier_ceiling"),
                review.get("evidence_tier_ceiling"),
                innovation.get("evidence_tier_ceiling"),
            )
            == "pilot_only"
            else None,
        ),
        "global_schedule_sha256": first_present(
            manifest.get("global_schedule_sha256"), planned_allocation.get("global_schedule_sha256")
        ),
        "assignment_sha256": first_present(
            manifest.get("assignment_sha256"), planned_allocation.get("assignment_sha256")
        ),
        "execution_route": first_present(
            manifest.get("execution_route"), review.get("execution_route"), innovation.get("execution_route")
        ),
        "resource_request": first_present(
            manifest.get("resource_request"), review.get("resource_request"), innovation.get("resource_request")
        ),
    }


def require_consistent_track_identity(
    manifest: dict[str, Any], review: dict[str, Any], innovation: dict[str, Any], identity: dict[str, Any]
) -> list[str]:
    conflicts: list[str] = []
    for field in ["track_id", "track_role", "selected_idea_id", "selection_fingerprint", "evidence_tier_ceiling"]:
        values = {
            str(payload.get(field) or "").strip()
            for payload in [manifest, review, innovation]
            if str(payload.get(field) or "").strip()
        }
        if len(values) > 1:
            conflicts.append(field)
    hard_conflicts = [field for field in conflicts if field in {"track_id", "selected_idea_id"}]
    if hard_conflicts:
        raise SystemExit(f"run identity conflict for immutable fields: {hard_conflicts}")
    if conflicts and "selection_fingerprint" not in conflicts:
        raise SystemExit(f"run identity conflict without a primary-selection revision: {conflicts}")
    if conflicts and not str(manifest.get("selection_fingerprint") or manifest.get("selected_primary_ref") or "").strip():
        raise SystemExit("historical run reconciliation requires launch-time selection identity in the manifest")
    role = str(identity.get("track_role") or "").strip().lower()
    ceiling = str(identity.get("evidence_tier_ceiling") or "").strip()
    evidence_tier = str(identity.get("evidence_tier") or "").strip()
    if role in {"alternate", "risk_repair"} and ceiling != "pilot_only":
        raise SystemExit("non-primary run requires evidence_tier_ceiling=pilot_only")
    if ceiling == "pilot_only" and evidence_tier != "pilot_only":
        raise SystemExit("pilot-only ceiling requires evidence_tier=pilot_only")
    return conflicts


SCIENTIFIC_OUTCOME_FIELDS = [
    "scientific_outcome_ref",
    "scientific_outcome_status",
    "scientific_outcome_hash",
    "scientific_decision_id",
    "outcome_class",
    "belief_effect",
    "research_transition",
    "operational_attempt",
    "scientific_revision",
    "claim_effect",
    "claim_limits",
    "falsifier_evaluation",
]


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


EXTERNAL_INTENT_IMMUTABLE_FIELDS = (
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

EXTERNAL_INTENT_PRESERVE_FIELDS = set(EXTERNAL_INTENT_IMMUTABLE_FIELDS) | {
    "prepared_at",
    "started_at",
    "resource_allocation",
    "immutable_launch_intent_sha256",
    "side_effects_performed",
    "launch_authorized",
    "auto_retry_allowed",
    "reconcile_exact_backend_id_before_retry",
    "authority_boundary",
}


def external_intent_payload(intent: dict[str, Any]) -> dict[str, Any]:
    return {key: intent.get(key) for key in EXTERNAL_INTENT_IMMUTABLE_FIELDS}


def is_external_launch_intent(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(
        present(value.get(field))
        for field in (
            "external_campaign_ref",
            "external_campaign_sha256",
            "external_candidate_id",
            "protected_commitment_sha256",
            "backend_idempotency_key",
        )
    )


def validate_external_launch_intent(
    *,
    base: Path,
    exp_dir: Path,
    previous: dict[str, Any],
    identity: dict[str, Any],
    manifest: dict[str, Any],
    requested_backend: str | None,
    requested_command: str | None,
    requested_session_id: str,
) -> None:
    errors: list[str] = []
    required_text = (
        "run_id",
        "experiment_id",
        "track_id",
        "queue_row_id",
        "external_campaign_ref",
        "external_campaign_sha256",
        "external_candidate_id",
        "protected_commitment_sha256",
        "backend",
        "execution_route",
        "command",
        "working_dir",
        "resource_pool_id",
        "resource_snapshot_ref",
        "resource_snapshot_sha256",
        "resource_snapshot_source_sha256",
        "resource_snapshot_checked_at",
        "backend_idempotency_key",
        "immutable_launch_intent_sha256",
    )
    for field in required_text:
        if not present(previous.get(field)):
            errors.append(f"queued external intent missing {field}")
    for field in (
        "external_gate",
        "environment",
        "resource_request",
        "planned_resource_allocation",
        "backend_preflight",
        "launch_spec",
        "budget",
        "authorization",
    ):
        if not isinstance(previous.get(field), dict) or not previous.get(field):
            errors.append(f"queued external intent {field} must be a nonempty object")
    for field in (
        "external_campaign_sha256",
        "protected_commitment_sha256",
        "resource_snapshot_sha256",
        "resource_snapshot_source_sha256",
        "backend_idempotency_key",
        "immutable_launch_intent_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(previous.get(field) or "")):
            errors.append(f"queued external intent {field} must be a lowercase 64-hex digest")

    observed_immutable_sha = str(previous.get("immutable_launch_intent_sha256") or "")
    expected_immutable_sha = stable_hash(external_intent_payload(previous))
    if observed_immutable_sha != expected_immutable_sha:
        errors.append("queued external intent immutable_launch_intent_sha256 does not match its immutable payload")
    external_gate = as_dict(previous.get("external_gate"))
    for field in ("gate_sha256", "lint_sha256", "slot_map_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(external_gate.get(field) or "")):
            errors.append(f"queued external intent external_gate.{field} must be a lowercase 64-hex digest")
    for field in ("gate_ref", "lint_ref", "slot_map_ref"):
        if not present(external_gate.get(field)):
            errors.append(f"queued external intent external_gate.{field} is required")

    track_id = str(previous.get("track_id") or "")
    experiment_id = str(previous.get("experiment_id") or "")
    if any(value in {"", ".", ".."} or "/" in value or "\\" in value for value in (track_id, experiment_id)):
        errors.append("queued external intent track_id and experiment_id must be safe path components")
    else:
        expected_dir = (base / "coder/experiments" / track_id / experiment_id).resolve()
        if exp_dir.resolve() != expected_dir:
            errors.append("queued external intent is outside canonical coder/experiments/<track_id>/<experiment_id>")

    identity_pairs = {
        "experiment_id": manifest.get("experiment_id"),
        "track_id": identity.get("track_id"),
        "queue_row_id": identity.get("queue_row_id"),
        "external_campaign_ref": identity.get("external_campaign_ref"),
        "external_campaign_sha256": identity.get("external_campaign_sha256"),
        "external_candidate_id": identity.get("external_candidate_id"),
        "protected_commitment_sha256": identity.get("protected_commitment_sha256"),
    }
    for field, observed in identity_pairs.items():
        if present(observed) and str(observed) != str(previous.get(field) or ""):
            errors.append(f"queued external intent {field} conflicts with canonical manifest/review identity")

    route = str(previous.get("execution_route") or "").strip().lower()
    backend = str(previous.get("backend") or "").strip().lower()
    request = as_dict(previous.get("resource_request"))
    allocation = as_dict(previous.get("planned_resource_allocation"))
    if route not in {"local", "ssh", "bjtu_hpc"}:
        errors.append("queued external intent execution_route is unsupported")
    allowed_route_backends = {"local", "local_gpu"} if route == "local" else {route}
    if backend != route or str(request.get("backend") or "").strip().lower() not in allowed_route_backends:
        errors.append("queued external intent backend and resource_request.backend must equal execution_route")
    if str(allocation.get("execution_route") or "").strip().lower() != route:
        errors.append("queued external intent allocation execution_route must equal execution_route")
    if str(allocation.get("backend") or "").strip().lower() not in allowed_route_backends:
        errors.append("queued external intent allocation backend must equal execution_route")
    if str(allocation.get("pool_id") or "") != str(previous.get("resource_pool_id") or ""):
        errors.append("queued external intent resource_pool_id must match planned allocation")
    if previous.get("evidence_tier") != "pilot_only" or previous.get("promotion_decision") != "record_only":
        errors.append("queued external rapid-validation intent must remain pilot_only with promotion_decision=record_only")
    if requested_backend and requested_backend != backend:
        errors.append("--backend conflicts with immutable queued external backend")
    if requested_command and requested_command != str(previous.get("command") or ""):
        errors.append("--command conflicts with immutable queued external command")
    if requested_session_id and requested_session_id != str(previous.get("session_id") or ""):
        errors.append("--session-id conflicts with immutable queued external session_id")
    if errors:
        raise SystemExit("invalid queued external launch intent: " + "; ".join(errors))


def preserve_external_launch_intent(remote: dict[str, Any], previous: dict[str, Any]) -> None:
    for key in EXTERNAL_INTENT_PRESERVE_FIELDS:
        if key in previous:
            remote[key] = previous[key]
    expected = str(previous.get("immutable_launch_intent_sha256") or "")
    if stable_hash(external_intent_payload(remote)) != expected:
        raise SystemExit("reconcile changed immutable queued external launch identity")


def accepted_decision_for_run(decision_ledger: dict[str, Any], run_id: str, digest: str) -> dict[str, Any]:
    for row in decision_ledger.get("experiment_decisions") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("run_id") or "") == run_id and str(row.get("outcome_hash") or "") == digest:
            return row
    return {}


def outcome_projection(
    *,
    base: Path,
    exp_dir: Path,
    identity: dict[str, Any],
    experiment_id: str,
    previous_entry: dict[str, Any],
    decision_ledger: dict[str, Any],
    terminal: bool,
) -> dict[str, Any]:
    path = exp_dir / "SCIENTIFIC_OUTCOME.json"
    relative = str(path.relative_to(base))
    outcome = read_json(path, None)
    if not isinstance(outcome, dict):
        if previous_entry.get("scientific_outcome_status") == "accepted":
            return {field: previous_entry.get(field) for field in SCIENTIFIC_OUTCOME_FIELDS if field in previous_entry}
        return {
            "scientific_outcome_ref": relative,
            "scientific_outcome_status": "awaiting_adjudication" if terminal else "pending_runtime",
        }

    digest = stable_hash({key: value for key, value in outcome.items() if key not in {"decision_id", "outcome_hash", "updated_at"}})
    errors: list[str] = []
    expected = {
        "run_id": str(identity.get("run_id") or experiment_id),
        "selected_idea_id": str(identity.get("selected_idea_id") or ""),
        "track_id": str(identity.get("track_id") or ""),
        "branch_id": str(identity.get("branch_id") or ""),
        "queue_row_id": str(identity.get("queue_row_id") or ""),
        "launch_identity_hash": str(identity.get("launch_identity_hash") or ""),
    }
    for field, value in expected.items():
        observed = str(outcome.get(field) or "")
        if not observed:
            errors.append(f"missing {field}")
        elif value and observed != value:
            errors.append(f"{field} mismatch: expected {value}, observed {observed}")
    expected_selection = str(identity.get("selection_fingerprint") or "")
    observed_selection = str(outcome.get("selection_fingerprint") or outcome.get("selected_primary_ref") or "")
    if not observed_selection:
        errors.append("missing selection_fingerprint or selected_primary_ref")
    elif expected_selection and observed_selection != expected_selection:
        errors.append(f"selection_fingerprint mismatch: expected {expected_selection}, observed {observed_selection}")
    for field in ["outcome_class", "belief_effect", "recommended_transition"]:
        if not present(outcome.get(field)):
            errors.append(f"missing {field}")

    previous_hash = str(previous_entry.get("scientific_outcome_hash") or "")
    if previous_entry.get("scientific_outcome_status") == "accepted" and previous_hash and previous_hash != digest:
        preserved = {field: previous_entry.get(field) for field in SCIENTIFIC_OUTCOME_FIELDS if field in previous_entry}
        preserved["scientific_outcome_quarantine"] = {
            "status": "conflict_with_accepted_outcome",
            "candidate_hash": digest,
            "accepted_hash": previous_hash,
            "errors": errors,
        }
        return preserved
    if errors:
        return {
            "scientific_outcome_ref": relative,
            "scientific_outcome_status": "quarantined",
            "scientific_outcome_hash": digest,
            "scientific_outcome_errors": errors,
        }

    decision = accepted_decision_for_run(decision_ledger, expected["run_id"], digest)
    return {
        "scientific_outcome_ref": relative,
        "scientific_outcome_status": "accepted" if decision else "pending_decision",
        "scientific_outcome_hash": digest,
        "scientific_decision_id": decision.get("decision_id"),
        "outcome_class": outcome.get("outcome_class"),
        "belief_effect": outcome.get("belief_effect"),
        "research_transition": outcome.get("recommended_transition"),
        "operational_attempt": outcome.get("operational_attempt"),
        "scientific_revision": outcome.get("scientific_revision"),
        "claim_effect": outcome.get("claim_effect"),
        "claim_limits": outcome.get("claim_limits"),
        "falsifier_evaluation": outcome.get("falsifier_evaluation"),
    }


def failure_projection(status: str, outcome: dict[str, Any]) -> dict[str, Any]:
    outcome_class = normalized_status(outcome.get("outcome_class"))
    transition = str(outcome.get("research_transition") or "")
    if outcome_class in {"infrastructure_failure", "implementation_failure", "protocol_invalid"}:
        intervention = {
            "infrastructure_failure": "runtime_or_resource",
            "implementation_failure": "implementation",
            "protocol_invalid": "experiment_plan_or_protocol",
        }[outcome_class]
        return {
            "failure_class": outcome_class,
            "failure_diagnosis": {
                "primary_cause": outcome_class,
                "evidence_sufficiency": "scientific_outcome_sidecar",
                "intervention_level": intervention,
                "repair_route": transition or "typed_reconciliation_required",
            },
        }
    if outcome_class in {
        "valid_negative",
        "valid_inconclusive",
        "cross_dataset_contradiction",
        "duplicate_or_non_discriminating",
        "budget_stopped_no_scientific_conclusion",
    }:
        return {"failure_class": outcome_class}
    if status in {"failed", "budget_stopped"}:
        return {
            "failure_class": "unadjudicated_terminal",
            "failure_diagnosis": {
                "primary_cause": "unadjudicated_terminal",
                "evidence_sufficiency": "insufficient_until_scientific_outcome",
                "intervention_level": "reconcile_before_retry",
                "repair_route": "write_and_validate_scientific_outcome",
            },
        }
    return {}


def hpo_low_fidelity_scout(identity: dict[str, Any]) -> bool:
    trial = as_dict(identity.get("hpo_trial"))
    if not trial:
        return False
    role = str(trial.get("role") or trial.get("trial_role") or trial.get("stage") or "").strip().lower()
    if role in {"scout", "dehb_scout", "low_fidelity"}:
        return True
    fraction = float_value(trial.get("resource_fraction") or trial.get("fidelity_fraction"))
    if fraction is not None and fraction < 1.0:
        return True
    return False


def promotion_decision(
    status: str,
    fixture: bool,
    metrics: dict[str, Any],
    metric_info: dict[str, Any],
    hashes: list[dict[str, Any]],
    identity: dict[str, Any],
) -> tuple[str, str]:
    if status != "completed":
        return "not_promoted", f"run status is {status}"
    if fixture or metrics.get("fixture") is True:
        return "not_promoted", "fixture result cannot support promotion"
    if any(item.get("matches_expected") is False for item in hashes):
        return "not_promoted", "protected path hash changed"
    if not metrics:
        return "not_promoted", "metrics file not found"
    if identity.get("historical_plan_stale") is True:
        return "record_only", "launch-time evidence belongs to a superseded primary-selection revision"
    if str(identity.get("evidence_tier_ceiling") or "").strip() == "pilot_only" or str(
        identity.get("evidence_tier") or ""
    ).strip() == "pilot_only":
        return "record_only", "pilot_only rapid-validation evidence cannot support candidate_supported or promotion"
    if hpo_low_fidelity_scout(identity):
        return "record_only", "low-fidelity HPO scout cannot support candidate or promoted evidence"
    if metric_info.get("improved") is True:
        stage = identity.get("promotion_stage") or "candidate"
        if stage == "candidate":
            return "candidate_supported", "positive candidate requires linked ablation or confirmation before promotion"
        if stage == "ablation":
            if not present(identity.get("ablation_of")):
                return "record_only", "ablation stage missing ablation_of link"
            return "promoted", "linked ablation supports the innovation mechanism"
        if stage == "confirmation":
            if not present(identity.get("confirmation_of")):
                return "record_only", "confirmation stage missing confirmation_of link"
            return "promoted", "linked confirmation supports the innovation mechanism"
        return "candidate_supported", "positive run stayed below promotion gate"
    if metric_info.get("improved") is False:
        return "rollback_to_best", "proposed regressed against matched baseline"
    return "record_only", "missing matched baseline/proposed metric pair"


def next_action(decision: str, identity: dict[str, Any]) -> str:
    if identity.get("historical_plan_stale") is True:
        return "reconcile_historical_only_no_follow_up"
    if decision == "candidate_supported":
        return "run_ablation_or_confirmation"
    if decision == "promoted":
        return "analyze_or_continue_next_track"
    if decision == "rollback_to_best":
        return "rollback_to_best_or_select_new_mechanism"
    if decision == "not_promoted":
        return "repair_or_prune_candidate"
    if identity.get("promotion_stage") == "ablation" and not present(identity.get("ablation_of")):
        return "record_ablation_link"
    if identity.get("promotion_stage") == "confirmation" and not present(identity.get("confirmation_of")):
        return "record_confirmation_link"
    return "record_evidence"


def better(entry: dict[str, Any], current: dict[str, Any] | None, direction: str) -> bool:
    score = entry.get("metrics", {}).get("proposed")
    current_score = None if current is None else current.get("metrics", {}).get("proposed")
    if score is None:
        return False
    if current_score is None:
        return True
    return score < current_score if direction == "lower" else score > current_score


def reconcile_queue_observation(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.backend_observation:
        return None
    if not args.queue_owner or args.queue_expected_revision is None:
        raise SystemExit("--backend-observation requires --queue-owner and --queue-expected-revision")
    observation_path = Path(args.backend_observation).expanduser().resolve()
    payload = read_json(observation_path, {})
    observation = payload.get("backend_observation") if isinstance(payload.get("backend_observation"), dict) else payload
    row_id = str(args.queue_row_id or observation.get("queue_row_id") or "").strip()
    if not row_id:
        raise SystemExit("backend observation reconciliation requires --queue-row-id or backend_observation.queue_row_id")
    completed = subprocess.run(
        [
            sys.executable,
            str(QUEUE_HELPER),
            "record-backend-observation",
            "--project",
            args.project,
            "--row-id",
            row_id,
            "--owner",
            args.queue_owner,
            "--expected-revision",
            str(args.queue_expected_revision),
            "--input",
            str(observation_path),
            "--reason",
            "run_reconcile consumed authoritative backend observation",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        result = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        result = {"stdout": completed.stdout}
    if completed.returncode != 0:
        raise SystemExit(
            "queue backend observation reconciliation failed: "
            + (completed.stderr.strip() or json.dumps(result, ensure_ascii=False))
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--backend", choices=["local", "ssh", "autodl", "bjtu_hpc", "manual"])
    parser.add_argument("--status", choices=["queued", "running", "completed", "failed", "budget_stopped"])
    parser.add_argument("--command")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--remote-path", default="")
    parser.add_argument("--ssh-host", default="")
    parser.add_argument("--ssh-user", default="")
    parser.add_argument("--ssh-port", type=int)
    parser.add_argument("--sync-logs", action="store_true")
    parser.add_argument("--metric-direction", choices=["higher", "lower"])
    parser.add_argument("--fixture-result", action="store_true")
    parser.add_argument("--estimated-remaining-minutes", type=float)
    parser.add_argument("--last-progress-at", default="")
    parser.add_argument("--automation-id", default="")
    parser.add_argument("--backend-observation")
    parser.add_argument("--queue-row-id")
    parser.add_argument("--queue-owner")
    parser.add_argument("--queue-expected-revision", type=int)
    args = parser.parse_args()
    base = ar(args.project)
    project_root = Path(args.project).expanduser().resolve()
    automation_registry = read_json(base / "automation_registry.json", {})
    primary_review_path = base / "planner/EXPERIMENT_REVIEW_PACKET.json"
    primary_innovation_path = base / "orchestrator/INNOVATION_PACKET.json"
    primary_review = read_json(primary_review_path, {})
    primary_innovation = read_json(primary_innovation_path, {})
    previous_ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json", {}) or {}
    decision_ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    previous_entries: dict[str, dict[str, Any]] = {}
    for row in previous_ledger.get("entries") or []:
        if not isinstance(row, dict):
            continue
        stable_id = str(row.get("run_id") or row.get("experiment_id") or "")
        if stable_id:
            previous_entries[stable_id] = row
    experiments = list(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json"))
    if not experiments:
        raise SystemExit("no EXPERIMENT_MANIFEST.json found")
    ledger_entries = []
    best_run: dict[str, Any] | None = None
    track_best_runs: dict[str, dict[str, Any]] = {}
    candidate_runs: list[dict[str, Any]] = []
    for manifest_path in experiments:
        manifest = read_json(manifest_path, {})
        exp_dir = manifest_path.parent
        manifest_contract = as_dict(manifest.get("innovation_search_contract"))
        track_hint = str(manifest.get("track_id") or manifest_contract.get("track_id") or "").strip()
        if track_hint and (Path(track_hint).name != track_hint or track_hint in {".", ".."}):
            raise SystemExit(f"invalid manifest track_id path component: {track_hint!r}")
        track_review_path = base / f"planner/tracks/{track_hint}/EXPERIMENT_REVIEW_PACKET.json"
        track_innovation_path = base / f"orchestrator/tracks/{track_hint}/INNOVATION_PACKET.json"
        if track_hint and track_review_path.exists() and track_innovation_path.exists():
            review_path = track_review_path
            innovation_path = track_innovation_path
            review = read_json(review_path, {})
            innovation = read_json(innovation_path, {})
        elif track_hint and (
            str(primary_review.get("track_id") or "").strip() == track_hint
            or str(primary_innovation.get("track_id") or "").strip() == track_hint
        ):
            review_path = primary_review_path
            innovation_path = primary_innovation_path
            review = primary_review
            innovation = primary_innovation
        elif track_hint:
            review_path = track_review_path
            innovation_path = track_innovation_path
            review = {}
            innovation = {}
        else:
            review_path = primary_review_path
            innovation_path = primary_innovation_path
            review = primary_review
            innovation = primary_innovation
        previous_remote = read_json(exp_dir / "REMOTE_RUN.json", {})
        status = args.status or normalized_status(previous_remote.get("status") if isinstance(previous_remote, dict) else None)
        identity = run_identity(manifest, review, innovation)
        identity_conflicts = require_consistent_track_identity(manifest, review, innovation, identity)
        identity["historical_plan_stale"] = bool(identity_conflicts)
        identity["historical_identity_conflicts"] = identity_conflicts
        identity["follow_up_allowed"] = not identity_conflicts
        identity["review_packet_ref"] = str(review_path.relative_to(base))
        identity["review_packet_sha256"] = first_present(
            manifest.get("review_packet_sha256"), review.get("semantic_sha256")
        )
        identity["innovation_packet_ref"] = str(innovation_path.relative_to(base))
        identity["innovation_packet_sha256"] = first_present(
            manifest.get("innovation_packet_sha256"), innovation.get("semantic_sha256")
        )
        external_intent = is_external_launch_intent(previous_remote)
        if external_intent:
            validate_external_launch_intent(
                base=base,
                exp_dir=exp_dir,
                previous=previous_remote,
                identity=identity,
                manifest=manifest,
                requested_backend=args.backend,
                requested_command=args.command,
                requested_session_id=args.session_id,
            )
            for field in (
                "track_id",
                "track_role",
                "idea_lifecycle_status",
                "idea_decision_ref",
                "source_track_seed_ref",
                "source_track_seed_sha256",
                "track_plan_ref",
                "track_plan_matrix_sha256",
                "historical_plan_stale",
                "historical_identity_conflicts",
                "follow_up_allowed",
                "queue_row_id",
                "selection_fingerprint",
                "external_campaign_ref",
                "external_campaign_sha256",
                "external_candidate_id",
                "protected_commitment_sha256",
                "evidence_tier",
                "evidence_tier_ceiling",
                "innovation_packet_ref",
                "innovation_packet_sha256",
                "review_packet_ref",
                "review_packet_sha256",
                "global_schedule_sha256",
                "assignment_sha256",
                "execution_route",
                "resource_request",
                "promotion_stage",
            ):
                if field in previous_remote:
                    identity[field] = previous_remote[field]
        run_id = str(
            previous_remote.get("run_id")
            if external_intent
            else identity.get("run_id") or manifest.get("experiment_id") or manifest_path.parent.name
        )
        identity["run_id"] = run_id
        previous_entry = previous_entries.get(run_id, {})
        direction = args.metric_direction or manifest.get("metric_direction") or review.get("metric_direction") or "higher"
        metrics, metrics_rel = read_metrics(exp_dir)
        metric_info = metric_payload(metrics, str(direction))
        hashes = protected_hashes(args.project, manifest, review)
        decision, reason = promotion_decision(status, args.fixture_result, metrics, metric_info, hashes, identity)
        source_snapshot = manifest.get("source_snapshot") or {
            "git_commit": git_capture(args.project, ["rev-parse", "HEAD"]),
            "git_status_porcelain": git_capture(args.project, ["status", "--porcelain"]),
            "git_diff_stat": git_capture(args.project, ["diff", "--stat"]),
        }
        command = (
            previous_remote.get("command")
            if external_intent
            else args.command or manifest.get("evaluate_command") or "recorded external command required"
        )
        resolved_backend = str(
            previous_remote.get("backend")
            if external_intent
            else args.backend or previous_remote.get("backend") or manifest.get("backend") or "local"
        )
        remote = {
            "schema_version": 1,
            "created_at": previous_remote.get("created_at") or previous_remote.get("prepared_at") or now(),
            "backend": resolved_backend,
            "status": status,
            "run_id": run_id,
            "track_id": identity.get("track_id"),
            "track_role": identity.get("track_role"),
            "idea_lifecycle_status": identity.get("idea_lifecycle_status"),
            "idea_decision_ref": identity.get("idea_decision_ref"),
            "source_track_seed_ref": identity.get("source_track_seed_ref"),
            "source_track_seed_sha256": identity.get("source_track_seed_sha256"),
            "track_plan_ref": identity.get("track_plan_ref"),
            "track_plan_matrix_sha256": identity.get("track_plan_matrix_sha256"),
            "historical_plan_stale": identity.get("historical_plan_stale"),
            "historical_identity_conflicts": identity.get("historical_identity_conflicts"),
            "follow_up_allowed": identity.get("follow_up_allowed"),
            "evidence_tier_ceiling": identity.get("evidence_tier_ceiling"),
            "innovation_packet_ref": identity.get("innovation_packet_ref"),
            "innovation_packet_sha256": identity.get("innovation_packet_sha256"),
            "review_packet_ref": identity.get("review_packet_ref"),
            "review_packet_sha256": identity.get("review_packet_sha256"),
            "branch_id": identity.get("branch_id"),
            "queue_row_id": identity.get("queue_row_id"),
            "selection_fingerprint": identity.get("selection_fingerprint"),
            "launch_identity_hash": identity.get("launch_identity_hash"),
            "experiment_id": manifest.get("experiment_id"),
            "selected_idea_id": identity.get("selected_idea_id"),
            "innovation_mechanism": identity.get("innovation_mechanism"),
            "mechanism_type": identity.get("mechanism_type"),
            "scientific_claim_class": "parameter_evidence" if identity.get("mechanism_type") == "PARAM" else "mechanism_evidence",
            "promotion_stage": identity.get("promotion_stage"),
            "ablation_of": identity.get("ablation_of"),
            "confirmation_of": identity.get("confirmation_of"),
            "hpo_search_policy": identity.get("hpo_search_policy"),
            "hpo_trial": identity.get("hpo_trial"),
            "evidence_source_mode": identity.get("evidence_source_mode"),
            "external_campaign_ref": identity.get("external_campaign_ref"),
            "external_campaign_sha256": identity.get("external_campaign_sha256"),
            "external_candidate_id": identity.get("external_candidate_id"),
            "protected_commitment_sha256": identity.get("protected_commitment_sha256"),
            "evidence_tier": identity.get("evidence_tier"),
            "global_schedule_sha256": identity.get("global_schedule_sha256"),
            "assignment_sha256": identity.get("assignment_sha256"),
            "execution_route": identity.get("execution_route"),
            "command": "fixture/manual reconcile" if args.fixture_result else command,
            "working_dir": previous_remote.get("working_dir") or manifest.get("working_dir"),
            "environment": previous_remote.get("environment") or manifest.get("environment") or {},
            "started_at": previous_remote.get("started_at") or manifest.get("started_at") or "",
            "remote_path": args.remote_path,
            "session_id": args.session_id or previous_remote.get("session_id") or "",
            "host": previous_remote.get("host") if isinstance(previous_remote, dict) else manifest.get("host"),
            "ssh_host": args.ssh_host or (previous_remote.get("ssh_host") if isinstance(previous_remote, dict) else None) or manifest.get("ssh_host"),
            "ssh_user": args.ssh_user or (previous_remote.get("ssh_user") if isinstance(previous_remote, dict) else None) or manifest.get("ssh_user"),
            "ssh_port": args.ssh_port or (previous_remote.get("ssh_port") if isinstance(previous_remote, dict) else None) or manifest.get("ssh_port"),
            "source_snapshot": source_snapshot,
            "protocol_locked": True,
            "metric": manifest.get("primary_metric"),
            "metric_direction": direction,
            "dataset": manifest.get("dataset"),
            "data_split": manifest.get("data_split"),
            "locked_protocol": manifest.get("locked_protocol", {}),
            "resource_request": previous_remote.get("resource_request") or identity.get("resource_request") or {},
            "resource_pool_id": previous_remote.get("resource_pool_id") or manifest.get("resource_pool_id"),
            "resource_allocation": previous_remote.get("resource_allocation") or manifest.get("resource_allocation") or {},
            "protected_path_hashes": hashes,
            "metrics": metric_info,
            "metrics_path": metrics_rel,
            "promotion_decision": decision,
            "promotion_reason": reason,
            "next_action": next_action(decision, identity),
            "result_paths": (previous_remote.get("result_paths") if isinstance(previous_remote, dict) else None) or manifest.get("result_paths") or [],
            "log_paths": (previous_remote.get("log_paths") if isinstance(previous_remote, dict) else None) or manifest.get("log_paths") or [],
        }
        if external_intent:
            preserve_external_launch_intent(remote, previous_remote)
        sync_args = argparse.Namespace(**vars(args))
        sync_args.backend = resolved_backend
        log_sync, local_log_paths = sync_remote_logs(
            exp_dir=exp_dir,
            remote=remote,
            previous=previous_remote if isinstance(previous_remote, dict) else {},
            manifest=manifest,
            args=sync_args,
        )
        previous_local_logs = previous_remote.get("local_log_paths") if isinstance(previous_remote, dict) else []
        merged_local_logs: list[str] = []
        for path in [*(previous_local_logs if isinstance(previous_local_logs, list) else []), *local_log_paths]:
            if path not in merged_local_logs:
                merged_local_logs.append(path)
        remote["local_log_paths"] = merged_local_logs
        remote["log_sync"] = log_sync
        estimated_remaining = inferred_remaining_minutes(
            args.estimated_remaining_minutes,
            previous_remote if isinstance(previous_remote, dict) else {},
            datetime.now(timezone.utc),
        )
        last_progress = args.last_progress_at or (
            ((previous_remote.get("monitoring") or {}).get("last_progress_at") if isinstance(previous_remote, dict) and isinstance(previous_remote.get("monitoring"), dict) else None)
            or (previous_remote.get("updated_at") if isinstance(previous_remote, dict) else None)
            or (previous_remote.get("created_at") if isinstance(previous_remote, dict) else None)
            or None
        )
        remote["monitoring"] = compute_monitoring_plan(
            project_root=project_root,
            base=base,
            remote_run_path=exp_dir / "REMOTE_RUN.json",
            remote=remote,
            existing_registry=automation_registry if isinstance(automation_registry, dict) else {},
            automation_id=args.automation_id,
            estimated_remaining_minutes=estimated_remaining,
            last_progress_at=last_progress,
        )
        automation_registry = read_json(base / "automation_registry.json", {})
        write_json(exp_dir / "REMOTE_RUN.json", remote)
        if args.fixture_result:
            write_json(exp_dir / "results/metrics.json", {"primary_metric": 0.0, "baseline": 0.0, "proposed": 0.0, "fixture": True})
        terminal = status in {"completed", "failed", "budget_stopped", "cancelled", "canceled", "timeout", "timed_out"}
        scientific = outcome_projection(
            base=base,
            exp_dir=exp_dir,
            identity=identity,
            experiment_id=str(manifest.get("experiment_id") or run_id),
            previous_entry=previous_entry,
            decision_ledger=decision_ledger if isinstance(decision_ledger, dict) else {},
            terminal=terminal,
        )
        generated_entry = {
            "manifest": str(manifest_path.relative_to(base)),
            "remote_run": str((exp_dir / "REMOTE_RUN.json").relative_to(base)),
            "status": status,
            "run_id": run_id,
            "track_id": identity.get("track_id"),
            "track_role": identity.get("track_role"),
            "idea_lifecycle_status": identity.get("idea_lifecycle_status"),
            "idea_decision_ref": identity.get("idea_decision_ref"),
            "source_track_seed_ref": identity.get("source_track_seed_ref"),
            "source_track_seed_sha256": identity.get("source_track_seed_sha256"),
            "track_plan_ref": identity.get("track_plan_ref"),
            "track_plan_matrix_sha256": identity.get("track_plan_matrix_sha256"),
            "historical_plan_stale": identity.get("historical_plan_stale"),
            "historical_identity_conflicts": identity.get("historical_identity_conflicts"),
            "follow_up_allowed": identity.get("follow_up_allowed"),
            "evidence_tier_ceiling": identity.get("evidence_tier_ceiling"),
            "innovation_packet_ref": identity.get("innovation_packet_ref"),
            "innovation_packet_sha256": identity.get("innovation_packet_sha256"),
            "review_packet_ref": identity.get("review_packet_ref"),
            "review_packet_sha256": identity.get("review_packet_sha256"),
            "branch_id": identity.get("branch_id"),
            "queue_row_id": identity.get("queue_row_id"),
            "selection_fingerprint": identity.get("selection_fingerprint"),
            "launch_identity_hash": identity.get("launch_identity_hash"),
            "parent_track_id": manifest.get("parent_track_id"),
            "derived_from_run_id": manifest.get("derived_from_run_id"),
            "iteration": manifest.get("iteration", 1),
            "experiment_id": manifest.get("experiment_id"),
            "selected_idea_id": identity.get("selected_idea_id"),
            "innovation_mechanism": identity.get("innovation_mechanism"),
            "mechanism_type": identity.get("mechanism_type"),
            "scientific_claim_class": "parameter_evidence" if identity.get("mechanism_type") == "PARAM" else "mechanism_evidence",
            "promotion_stage": identity.get("promotion_stage"),
            "ablation_of": identity.get("ablation_of"),
            "confirmation_of": identity.get("confirmation_of"),
            "hpo_search_policy": identity.get("hpo_search_policy"),
            "hpo_trial": identity.get("hpo_trial"),
            "evidence_source_mode": identity.get("evidence_source_mode"),
            "external_campaign_ref": identity.get("external_campaign_ref"),
            "external_campaign_sha256": identity.get("external_campaign_sha256"),
            "external_candidate_id": identity.get("external_candidate_id"),
            "protected_commitment_sha256": identity.get("protected_commitment_sha256"),
            "evidence_tier": identity.get("evidence_tier"),
            "global_schedule_sha256": identity.get("global_schedule_sha256"),
            "assignment_sha256": identity.get("assignment_sha256"),
            "execution_route": identity.get("execution_route"),
            "resource_pool_id": remote.get("resource_pool_id"),
            "backend_idempotency_key": remote.get("backend_idempotency_key"),
            "metrics": metric_info,
            "metric_value": metric_info.get("proposed"),
            "metric_source": metrics_rel,
            "remote_run_log_sync_status": log_sync.get("status") if isinstance(log_sync, dict) else None,
            "local_log_paths": merged_local_logs,
            "canonical_eval_status": "passed" if status == "completed" and metrics_rel else "missing_or_pending",
            "metrics_path": metrics_rel,
            "promotion_decision": decision,
            "promotion_status": decision,
            "verdict": decision,
            "promotion_reason": reason,
            "next_action": scientific.get("research_transition") or next_action(decision, identity),
            "metric_direction": direction,
            "retire_reason": reason if decision in {"not_promoted", "rollback_to_best"} else None,
            "spec_violation_status": manifest.get("spec_violation_status") or "not_checked",
            "source_snapshot": source_snapshot,
            **scientific,
            **failure_projection(status, scientific),
        }
        entry = {**previous_entry, **generated_entry}
        ledger_entries.append(entry)
        if decision == "candidate_supported":
            candidate_runs.append(entry)
        if decision == "promoted" and better(entry, best_run, str(direction)):
            best_run = entry
        track_key = str(identity.get("track_id") or "unknown")
        if decision == "promoted" and better(entry, track_best_runs.get(track_key), str(direction)):
            track_best_runs[track_key] = entry
    program_decision = decision_ledger.get("program_decision") if isinstance(decision_ledger, dict) and isinstance(decision_ledger.get("program_decision"), dict) else {}
    terminal_program_ready = bool(
        program_decision.get("terminal") is True
        and program_decision.get("target_stage") == "analysis"
        and present(program_decision.get("mandatory_downgrade"))
        and present(program_decision.get("remaining_claim_scope"))
    )
    ready_for_analysis = best_run is not None or terminal_program_ready
    analysis_claim_scope = (
        "promoted_only"
        if best_run is not None
        else program_decision.get("remaining_claim_scope")
        if terminal_program_ready
        else "pilot_only_no_improvement_claim"
    )
    ledger = {
        "schema_version": 4,
        "created_at": now(),
        "ready_for_analysis": ready_for_analysis,
        "analysis_claim_scope": analysis_claim_scope,
        "terminal_program_decision": program_decision if terminal_program_ready else None,
        "improvement_claim_allowed": best_run is not None,
        "best_run": best_run,
        "track_best_runs": track_best_runs,
        "candidate_runs": candidate_runs,
        "entries": ledger_entries,
    }
    write_json(base / "coder/EXPERIMENT_LEDGER.json", ledger)
    ranked = sorted(
        ledger_entries,
        key=lambda row: (
            row.get("metric_value") is None,
            -float(row.get("metric_value") or 0) if str(row.get("metric_direction") or "higher") != "lower" else float(row.get("metric_value") or 0),
        ),
    )
    write_json(
        base / "coder/TRACK_RANKING.json",
        {
            "schema_version": 1,
            "created_at": now(),
            "ranking_source": "coder/EXPERIMENT_LEDGER.json",
            "selection_policy": "canonical_metric_then_promotion_gate",
            "ready_for_analysis": ready_for_analysis,
            "ranked_tracks": [
                {
                    "rank": index + 1,
                    "track_id": row.get("track_id"),
                    "experiment_id": row.get("experiment_id"),
                    "metric_value": row.get("metric_value"),
                    "metric_source": row.get("metric_source"),
                    "promotion_status": row.get("promotion_status"),
                    "canonical_eval_status": row.get("canonical_eval_status"),
                    "spec_violation_status": row.get("spec_violation_status"),
                    "retire_reason": row.get("retire_reason"),
                }
                for index, row in enumerate(ranked)
            ],
        },
    )
    write_text(
        base / "coder/EXPERIMENT_INDEX.md",
        "# Experiment Index\n\n"
        + "\n".join(
            f"- `{row['manifest']}` stage `{row.get('promotion_stage')}` idea `{row.get('selected_idea_id')}` "
            f"status `{row['status']}` decision `{row['promotion_decision']}` next `{row.get('next_action')}`"
            for row in ledger_entries
        )
        + "\n",
    )
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": "experiment",
            "action": "run_reconcile",
            "details": {
                "backend": args.backend or "preserved_per_run",
                "status": args.status or "preserved",
                "count": len(ledger_entries),
                "promoted_count": len([row for row in ledger_entries if row.get("promotion_decision") == "promoted"]),
                "candidate_supported_count": len(candidate_runs),
            },
        },
    )
    queue_reconciliation = reconcile_queue_observation(args)
    print(
        json.dumps(
            {
                "ok": True,
                "ledger": "coder/EXPERIMENT_LEDGER.json",
                "count": len(ledger_entries),
                "queue_reconciliation": queue_reconciliation,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
