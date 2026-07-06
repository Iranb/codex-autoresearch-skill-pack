#!/usr/bin/env python3
"""Record local/remote experiment run metadata and reconcile ledgers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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
                host = (
                    remote.get("seetacloud_ssh_host")
                    or manifest.get("seetacloud_ssh_host")
                    or os.environ.get("SEETACLOUD_SSH_HOST")
                )
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
    write_json(
        base / "experiment/EXPERIMENT_MONITOR_PLAN.json",
        {
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
        },
    )
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
    selected_idea_id = first_present(
        manifest.get("selected_idea_id"),
        manifest.get("selected_candidate_id"),
        contract.get("selected_idea_id"),
        contract.get("idea_id"),
        review.get("selected_idea_id"),
        innovation.get("selected_idea_id"),
    )
    track_id = first_present(manifest.get("track_id"), contract.get("track_id"), review.get("track_id"), innovation.get("selected_idea_fragment_id"))
    stage = normalize_stage(first_present(manifest.get("promotion_stage"), contract.get("promotion_stage"), gate.get("stage")))
    return {
        "track_id": track_id,
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
    }


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--backend", choices=["local", "ssh", "autodl", "bjtu_hpc", "manual"], default="local")
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
    args = parser.parse_args()
    base = ar(args.project)
    project_root = Path(args.project).expanduser().resolve()
    automation_registry = read_json(base / "automation_registry.json", {})
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json", {})
    innovation = read_json(base / "orchestrator/INNOVATION_PACKET.json", {})
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
        previous_remote = read_json(exp_dir / "REMOTE_RUN.json", {})
        status = args.status or normalized_status(previous_remote.get("status") if isinstance(previous_remote, dict) else None)
        identity = run_identity(manifest, review, innovation)
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
        command = args.command or manifest.get("evaluate_command") or "recorded external command required"
        remote = {
            "schema_version": 1,
            "created_at": now(),
            "backend": args.backend,
            "status": status,
            "track_id": identity.get("track_id"),
            "experiment_id": manifest.get("experiment_id"),
            "selected_idea_id": identity.get("selected_idea_id"),
            "innovation_mechanism": identity.get("innovation_mechanism"),
            "mechanism_type": identity.get("mechanism_type"),
            "promotion_stage": identity.get("promotion_stage"),
            "ablation_of": identity.get("ablation_of"),
            "confirmation_of": identity.get("confirmation_of"),
            "hpo_search_policy": identity.get("hpo_search_policy"),
            "hpo_trial": identity.get("hpo_trial"),
            "command": "fixture/manual reconcile" if args.fixture_result else command,
            "remote_path": args.remote_path,
            "session_id": args.session_id,
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
            "protected_path_hashes": hashes,
            "metrics": metric_info,
            "metrics_path": metrics_rel,
            "promotion_decision": decision,
            "promotion_reason": reason,
            "next_action": next_action(decision, identity),
            "result_paths": (previous_remote.get("result_paths") if isinstance(previous_remote, dict) else None) or manifest.get("result_paths") or [],
            "log_paths": (previous_remote.get("log_paths") if isinstance(previous_remote, dict) else None) or manifest.get("log_paths") or [],
        }
        log_sync, local_log_paths = sync_remote_logs(
            exp_dir=exp_dir,
            remote=remote,
            previous=previous_remote if isinstance(previous_remote, dict) else {},
            manifest=manifest,
            args=args,
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
        entry = {
            "manifest": str(manifest_path.relative_to(base)),
            "remote_run": str((exp_dir / "REMOTE_RUN.json").relative_to(base)),
            "status": status,
            "track_id": identity.get("track_id"),
            "parent_track_id": manifest.get("parent_track_id"),
            "derived_from_run_id": manifest.get("derived_from_run_id"),
            "iteration": manifest.get("iteration", 1),
            "experiment_id": manifest.get("experiment_id"),
            "selected_idea_id": identity.get("selected_idea_id"),
            "innovation_mechanism": identity.get("innovation_mechanism"),
            "mechanism_type": identity.get("mechanism_type"),
            "promotion_stage": identity.get("promotion_stage"),
            "ablation_of": identity.get("ablation_of"),
            "confirmation_of": identity.get("confirmation_of"),
            "hpo_search_policy": identity.get("hpo_search_policy"),
            "hpo_trial": identity.get("hpo_trial"),
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
            "next_action": next_action(decision, identity),
            "metric_direction": direction,
            "retire_reason": reason if decision in {"not_promoted", "rollback_to_best"} else None,
            "spec_violation_status": manifest.get("spec_violation_status") or "not_checked",
            "source_snapshot": source_snapshot,
        }
        ledger_entries.append(entry)
        if decision == "candidate_supported":
            candidate_runs.append(entry)
        if decision == "promoted" and better(entry, best_run, str(direction)):
            best_run = entry
        track_key = str(identity.get("track_id") or "unknown")
        if decision == "promoted" and better(entry, track_best_runs.get(track_key), str(direction)):
            track_best_runs[track_key] = entry
    ready_for_analysis = best_run is not None
    ledger = {
        "schema_version": 3,
        "created_at": now(),
        "ready_for_analysis": ready_for_analysis,
        "analysis_claim_scope": "promoted_only" if ready_for_analysis else "pilot_only_no_improvement_claim",
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
                "backend": args.backend,
                "status": args.status or "preserved",
                "count": len(ledger_entries),
                "promoted_count": len([row for row in ledger_entries if row.get("promotion_decision") == "promoted"]),
                "candidate_supported_count": len(candidate_runs),
            },
        },
    )
    print(json.dumps({"ok": True, "ledger": "coder/EXPERIMENT_LEDGER.json", "count": len(ledger_entries)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
