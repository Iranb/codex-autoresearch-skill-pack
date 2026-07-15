#!/usr/bin/env python3
"""Focused offline fixtures for GPU resource normalization, budget, and launch intent."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ADAPTER = Path(__file__).resolve().parents[2] / "autoreskill-gpu-idea-validation/scripts/resource_adapter.py"


def load_adapter_module() -> Any:
    spec = importlib.util.spec_from_file_location("gpu_idea_resource_adapter_fixture", ADAPTER)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load resource adapter module from {ADAPTER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def launch_spec_sha(spec: dict[str, Any]) -> str:
    normalized = {
        "command_argv": list(spec["command_argv"]),
        "code_ref": spec["code_ref"],
        "code_sha256": spec["code_sha256"],
        "dataset_ref": spec["dataset_ref"],
        "dataset_sha256": spec["dataset_sha256"],
        "environment_ref": spec["environment_ref"],
        "environment_sha256": spec["environment_sha256"],
        "working_dir": spec["working_dir"],
        "launcher_template_sha256": spec["launcher_template_sha256"],
        "resource_shape": spec["resource_shape"],
        "seed": spec["seed"],
    }
    normalized["command_sha256"] = canonical_sha(normalized["command_argv"])
    return canonical_sha(normalized)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_json(command: list[str], *, expected: int = 0, env: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False, env=env)
    if completed.returncode != expected:
        raise AssertionError(
            f"unexpected exit {completed.returncode}, expected {expected}: {' '.join(command)}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"adapter did not emit JSON: {completed.stdout}\n{completed.stderr}") from exc


def fake_path(tmp: Path) -> tuple[dict[str, str], Path]:
    bindir = tmp / "fake-bin"
    bindir.mkdir(parents=True, exist_ok=True)
    audit = tmp / "external-command-audit.txt"
    for name in ("ssh", "scp", "rsync", "sbatch", "scontrol", "curl", "wget"):
        shim = bindir / name
        shim.write_text(f"#!/bin/sh\nprintf '%s\\n' {name} >> '{audit}'\nexit 97\n", encoding="utf-8")
        shim.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bindir)
    env["RESOURCE_ADAPTER_FAKE_AUDIT"] = str(audit)
    return env, audit


def campaign_payload() -> dict[str, Any]:
    def candidate(candidate_id: str) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": candidate_id,
            "mechanism": {
                "falsifier": "metric does not move under the intervention",
                "predicted_observation": "metric moves only for the causal intervention",
                "load_bearing_variable": "fixture-variable",
            },
            "negative_control": {
                "intervention": "matched no-op control",
                "expected_if_mechanism_true": "no metric move",
            },
            "rapid_validation": {
                "evidence_tier": "pilot_only",
                "baseline_code": {
                    "source_ref": "code/baseline",
                    "revision": "fixture-revision",
                    "comparison_label": "vs matched reproduced baseline",
                },
                "dataset": {"name": "fixture-dataset", "split": "fixture-split"},
                "metric_policy": {"primary_metric": "fixture-metric", "direction": "higher"},
                "resource_request": {
                    "compute_backend": "local_gpu",
                    "execution_route": "ssh",
                    "gpu_count": 1,
                    "estimated_gpu_hours": 0.2,
                    "walltime_minutes": 60,
                    "smoke_minutes": 10,
                },
                "seed_policy": {
                    "planned_seed_count": 1,
                    "max_random_seeds": 3,
                    "seed": 7,
                    "retry_reuses_seed": True,
                },
                "outcome_routes": {
                    "valid_positive_candidate": "retain candidate",
                    "valid_negative": "retire candidate",
                    "valid_inconclusive": "one discriminator",
                    "infrastructure_failure": "repair infrastructure",
                    "implementation_failure": "repair implementation",
                    "protocol_invalid": "repair protocol",
                },
            },
        }
        rapid = value["rapid_validation"]
        resource = rapid["resource_request"]
        protected = {
            "falsifier": value["mechanism"]["falsifier"],
            "observable_prediction": value["mechanism"]["predicted_observation"],
            "load_bearing_variable": value["mechanism"]["load_bearing_variable"],
            "negative_control": value["negative_control"],
            "baseline": {
                "source_ref": rapid["baseline_code"]["source_ref"],
                "revision": rapid["baseline_code"]["revision"],
                "comparison_label": rapid["baseline_code"]["comparison_label"],
            },
            "dataset": rapid["dataset"],
            "metric_policy": rapid["metric_policy"],
            "resource_ceiling": {
                "compute_backend": resource["compute_backend"],
                "execution_route": resource["execution_route"],
                "gpu_count": resource["gpu_count"],
                "estimated_gpu_hours": resource["estimated_gpu_hours"],
                "walltime_minutes": resource["walltime_minutes"],
                "smoke_minutes": resource["smoke_minutes"],
            },
            "seed_policy": rapid["seed_policy"],
            "evidence_tier": rapid["evidence_tier"],
            "outcome_routes": rapid["outcome_routes"],
        }
        value["protected_commitments"] = {"payload": protected, "sha256": canonical_sha(protected)}
        return value

    return {
        "schema_version": 1,
        "campaign_id": "fixture-campaign",
        "campaign_revision": 1,
        "source_mode": "external_material",
        "papernexus_used": False,
        "constraints": {
            "quick_campaign_gpu_hours": 4,
            "max_candidate_gpu_hours": 1,
        },
        "execution_policy": {
            "routes": {"ssh": {"allow_launch": True, "policy_ref": "fixture/backend-policy:ssh"}}
        },
        "candidates": [candidate("candidate-a"), candidate("candidate-b")],
        "shortlisted_candidate_ids": ["candidate-a", "candidate-b"],
        "admitted_candidate_ids": ["candidate-a", "candidate-b"],
    }


def materialize_gate_fixture(project: Path, campaign_path: Path, campaign: dict[str, Any]) -> dict[str, Any]:
    campaign_sha = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    campaign_ref = "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"

    def committed(stem: str, payload: dict[str, Any]) -> tuple[str, str]:
        encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        ref = f"ideation/committed/{stem}.{digest}.json"
        path = project / ".autoreskill" / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
        return ref, digest

    slot = {
        "schema_version": 1,
        "source_mode": "external_material",
        "campaign_ref": campaign_ref,
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign["campaign_id"],
        "campaign_revision": campaign["campaign_revision"],
    }
    slot_ref, slot_sha = committed("INNOVATION_SLOT_MAP", slot)
    lint = {
        "schema_version": 1,
        "complete": True,
        "status": "passed",
        "campaign_ref": campaign_ref,
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign["campaign_id"],
        "campaign_revision": campaign["campaign_revision"],
        "slot_map_ref": slot_ref,
        "slot_map_sha256": slot_sha,
    }
    lint_ref, lint_sha = committed("NON_PAPERNEXUS_IDEA_LINT", lint)
    gate = {
        "schema_version": 1,
        "status": "passed",
        "evidence_source_mode": "external_material",
        "lane_attempts_satisfied": True,
        "screening_completed": True,
        "allowed_next_action": "generate_experiment_idea_pool",
        "commit_layout": "content_addressed_v1",
        "campaign_ref": campaign_ref,
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign["campaign_id"],
        "campaign_revision": campaign["campaign_revision"],
        "lint_ref": lint_ref,
        "lint_sha256": lint_sha,
        "innovation_slot_map_path": slot_ref,
        "slot_map_ref": slot_ref,
        "slot_map_sha256": slot_sha,
    }
    write_json(project / ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json", gate)
    return gate


def test_normalizers(tmp: Path, env: dict[str, str]) -> None:
    project = tmp / "normalize-project"
    queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
    write_json(
        queue_path,
        {
            "schema_version": 2,
            "queue_revision": 17,
            "rows": [
                {
                    "id": "local-row",
                    "execution_route": "local",
                    "resource_request": {"backend": "local", "execution_route": "local"},
                }
            ],
        },
    )
    queue_before = queue_path.read_bytes()
    ssh_capture = project / "captures/ssh.json"
    write_json(
        ssh_capture,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "results": [
                {
                    "status": "idle_available",
                    "ssh_alias": "fixture-host",
                    "user": "fixture-user",
                    "gpus": [
                        {
                            "index": 0,
                            "uuid": "GPU-idle",
                            "name": "Fixture GPU",
                            "memory_free_mib": 22000,
                            "idle": True,
                        },
                        {
                            "index": 1,
                            "uuid": "GPU-busy",
                            "name": "Fixture GPU",
                            "memory_free_mib": 2000,
                            "idle": False,
                        },
                        {
                            "index": 2,
                            "name": "Fixture GPU without stable identity",
                            "memory_free_mib": 24000,
                            "idle": True,
                        },
                    ],
                },
                {"status": "timeout", "ssh_alias": "unknown-host", "gpus": []},
            ],
        },
    )
    normalized = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "normalize-ssh-scan",
            "--project",
            str(project),
            "--input",
            str(ssh_capture),
        ],
        env=env,
    )["resource_snapshot"]
    require(normalized["available_gpu_slots"] == 1, f"only one physical idle GPU is assignable: {normalized}")
    require(len(normalized["pools"]) == 4, f"busy and unknown resources must remain explicit: {normalized}")
    require(sum(pool["launch_slots"] for pool in normalized["pools"]) == 1, f"one UUID means one slot: {normalized}")
    missing_uuid = [pool for pool in normalized["pools"] if pool.get("fit_confidence") == "captured_missing_gpu_uuid"]
    require(
        len(missing_uuid) == 1 and missing_uuid[0]["status"] == "unknown" and missing_uuid[0]["launch_slots"] == 0,
        f"missing GPU UUID must be unknown and non-assignable: {normalized}",
    )
    require(
        normalized.get("compute_backend") == {"backend": "local_gpu"}
        and all(pool.get("compute_backend") == {"backend": "local_gpu"} for pool in normalized["pools"]),
        f"SSH is an execution route under the local_gpu compute class: {normalized}",
    )
    require(queue_path.read_bytes() == queue_before, "normalization must not mutate the scheduling authority")

    local_capture = project / "captures/local.json"
    write_json(
        local_capture,
        {
            "schema": "local-gpu-scan/v1",
            "checked_at": now_iso(),
            "fresh": True,
            "machine_id": "fixture-local-machine",
            "gpus": [
                {
                    "index": 0,
                    "uuid": "GPU-local-idle",
                    "name": "Fixture Local GPU",
                    "memory_free_mib": 16000,
                    "idle": True,
                    "full_process_visibility": True,
                },
                {
                    "index": 1,
                    "uuid": "GPU-local-hidden",
                    "name": "Fixture Local GPU",
                    "idle": True,
                    "full_process_visibility": False,
                },
            ],
        },
    )
    local = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "normalize-local-scan",
            "--project",
            str(project),
            "--input",
            str(local_capture),
        ],
        env=env,
    )["resource_snapshot"]
    require(
        local["execution_route"] == "local" and local["available_gpu_slots"] == 1,
        f"local capture must expose only the UUID-bound fully visible idle GPU: {local}",
    )
    require(
        sum(pool["launch_slots"] for pool in local["pools"]) == 1,
        f"local capture must map one physical GPU UUID to one slot: {local}",
    )
    proposal_path = project / "captures/local-proposal.json"
    routed_local = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "normalize-for-row",
            "--project",
            str(project),
            "--row-id",
            "local-row",
            "--input",
            str(local_capture),
            "--output",
            str(proposal_path),
        ],
        env=env,
    )
    require(
        routed_local["resource_snapshot"]["execution_route"] == "local"
        and read_json(proposal_path)["execution_route"] == "local",
        f"row-aware normalization must dispatch the local route and persist only a proposal: {routed_local}",
    )
    require(queue_path.read_bytes() == queue_before, "row-aware normalization must not mutate the scheduling authority")

    stale_payload = read_json(ssh_capture)
    stale_payload["fresh"] = False
    stale_capture = project / "captures/ssh-stale.json"
    write_json(stale_capture, stale_payload)
    stale = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "normalize-ssh-scan",
            "--project",
            str(project),
            "--input",
            str(stale_capture),
        ],
        env=env,
    )["resource_snapshot"]
    require(stale["fresh"] is False and stale["available_gpu_slots"] == 0, f"stale scans must expose zero slots: {stale}")

    old_payload = read_json(ssh_capture)
    old_payload["created_at"] = "2020-01-01T00:00:00+00:00"
    old_capture = project / "captures/ssh-old.json"
    write_json(old_capture, old_payload)
    old = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "normalize-ssh-scan",
            "--project",
            str(project),
            "--input",
            str(old_capture),
        ],
        env=env,
    )["resource_snapshot"]
    require(old["fresh"] is False and old["available_gpu_slots"] == 0, f"aged scans must fail closed: {old}")

    bjtu_capture = project / "captures/bjtu.json"
    base_action = {
        "account": "private-account-a",
        "recommendation": {
            "mode": "immediate",
            "requested": {"gpus": 1, "cpus": 6},
            "selected_node": {"name": "gpu03"},
        },
        "current": {"shared_limit_ref": "private-qos"},
        "requires_refresh_before_submit": False,
        "requires_exact_script_preflight": True,
        "do_not_batch_submit": True,
    }
    second_action = json.loads(json.dumps(base_action))
    second_action["account"] = "private-account-b"
    second_action["requires_refresh_before_submit"] = True
    write_json(
        bjtu_capture,
        {
            "schema": "bjtu-hpc-resource-plan/v1",
            "checked_at_local": now_iso(),
            "planner_options": {"admission_mode": "direct-start", "allow_queued_probe": False},
            "admission_frontier": [base_action, second_action],
            "accounts": [],
        },
    )
    bjtu = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "normalize-bjtu-plan",
            "--project",
            str(project),
            "--input",
            str(bjtu_capture),
        ],
        env=env,
    )["resource_snapshot"]
    require(bjtu["available_gpu_slots"] == 1, f"only the first direct-start action is fresh enough: {bjtu}")
    require(
        bjtu.get("compute_backend") == {"backend": "local_gpu"}
        and all(pool.get("compute_backend") == {"backend": "local_gpu"} for pool in bjtu["pools"]),
        f"BJTU HPC is an execution route under the local_gpu compute class: {bjtu}",
    )
    require(bjtu["pools"][1]["launch_slots"] == 0, f"later frontier action must refresh first: {bjtu}")
    require(
        all("private-account" not in str(pool) for pool in bjtu["pools"]),
        f"normalized BJTU account refs must be opaque: {bjtu}",
    )

    raw_summary = project / "captures/bjtu-raw.json"
    write_json(raw_summary, {"checked_at_local": now_iso(), "accounts": []})
    rejected = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "normalize-bjtu-plan",
            "--project",
            str(project),
            "--input",
            str(raw_summary),
        ],
        env=env,
    )["resource_snapshot"]
    require(rejected["fresh"] is False and rejected["available_gpu_slots"] == 0, f"raw HPC state is not allocatability: {rejected}")


def write_usage_record(project: Path, name: str, payload: dict[str, Any]) -> None:
    write_json(project / f".autoreskill/coder/experiments/{name}/REMOTE_RUN.json", payload)


def test_budget_and_prepare_intent(tmp: Path, env: dict[str, str]) -> None:
    project = tmp / "budget-project"
    campaign_path = project / ".autoreskill/ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
    campaign = campaign_payload()
    write_json(campaign_path, campaign)
    campaign_sha = hashlib.sha256(campaign_path.read_bytes()).hexdigest()

    ghost_campaign = json.loads(json.dumps(campaign))
    ghost_campaign["metadata"] = {"external_candidate_id": "ghost-candidate"}
    write_json(campaign_path, ghost_campaign)
    ghost = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "budget-check",
            "--project",
            str(project),
            "--candidate-id",
            "ghost-candidate",
            "--reserve-gpu-hours",
            "0",
        ],
        expected=1,
        env=env,
    )
    require(ghost["error"]["code"] == "candidate_missing", f"nested ghost candidate must be rejected: {ghost}")

    nan_campaign = json.loads(json.dumps(campaign))
    nan_campaign["candidates"][0]["rapid_validation"]["resource_request"]["estimated_gpu_hours"] = float("nan")
    write_json(campaign_path, nan_campaign)
    nan_campaign_result = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "budget-check",
            "--project",
            str(project),
            "--candidate-id",
            "candidate-a",
            "--reserve-gpu-hours",
            "0",
        ],
        expected=1,
        env=env,
    )
    require(nan_campaign_result["error"]["code"] == "invalid_json", f"NaN JSON must be rejected: {nan_campaign_result}")
    write_json(campaign_path, campaign)
    campaign_sha = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    write_json(
        project / ".autoreskill/autopilot_policy.json",
        {"allow_remote_experiment_launch": True, "max_experiment_gpu_hours": 3.0},
    )
    launch_spec = {
        "command_argv": ["python", "train_fixture.py", "--seed", "7"],
        "code_ref": "manifests/CODE.json",
        "code_sha256": "1" * 64,
        "dataset_ref": "manifests/DATASET.json",
        "dataset_sha256": "2" * 64,
        "environment_ref": "manifests/ENV.json",
        "environment_sha256": "3" * 64,
        "working_dir": "/remote/fixture-worktree",
        "launcher_template_sha256": "4" * 64,
        "resource_shape": {"gpus": 1, "cpus": 4},
        "seed": 7,
    }
    launch_spec_path = project / "manifests/LAUNCH_SPEC.json"
    write_json(launch_spec_path, launch_spec)
    digest_result = run_json(
        [sys.executable, str(ADAPTER), "launch-spec-digest", "--input", str(launch_spec_path)],
        env=env,
    )
    require(
        digest_result["launch_spec_sha256"] == launch_spec_sha(launch_spec)
        and digest_result["side_effects_performed"] is False,
        f"launch-spec digest must be deterministic and offline: {digest_result}",
    )
    seed_zero_spec = json.loads(json.dumps(launch_spec))
    seed_zero_spec["seed"] = 0
    seed_zero_path = project / "manifests/LAUNCH_SPEC_SEED_ZERO.json"
    write_json(seed_zero_path, seed_zero_spec)
    seed_zero = run_json(
        [sys.executable, str(ADAPTER), "launch-spec-digest", "--input", str(seed_zero_path)],
        env=env,
    )
    require(seed_zero["normalized_launch_spec"]["seed"] == 0, f"seed 0 must remain a valid identity: {seed_zero}")
    pool_id = "ssh:fixture:gpu:one"
    snapshot_sha = "a" * 64
    row = {
        "id": "queue-plan-a",
        "track_id": "track-a",
        "experiment_id": "experiment-a",
        "status": "planned",
        "external_candidate_id": "candidate-a",
        "external_campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
        "external_campaign_sha256": campaign_sha,
        "protected_commitment_sha256": campaign["candidates"][0]["protected_commitments"]["sha256"],
        "evidence_tier": "pilot_only",
        "execution_route": "ssh",
        "lease_owner": "fixture-worker",
        "lease_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(microsecond=0).isoformat(),
        "row_revision": 1,
        "resource_request": {
            "backend": "ssh",
            "execution_route": "ssh",
            "gpu_count": 1,
            "estimated_gpu_hours": 0.2,
        },
        "planned_resource_allocation": {
            "pool_id": pool_id,
            "backend": "ssh",
            "execution_route": "ssh",
            "host_ref": "fixture-host",
            "gpu_uuids": ["GPU-fixture"],
            "resource_ids": ["GPU-fixture"],
            "gpu_count": 1,
            "estimated_gpu_hours": 0.2,
            "requires_fresh_backend_preflight": True,
            "resource_snapshot_sha256": snapshot_sha,
            "resource_snapshot_source_ref": ".autoreskill/experiment/GPU_IDLE_SCAN.json",
            "resource_snapshot_source_sha256": "b" * 64,
            "resource_snapshot_checked_at": now_iso(),
        },
        "backend_policy": {"allow_launch": True, "policy_ref": "fixture/backend-policy:ssh"},
        "backend_preflight": {
            "status": "passed",
            "checked_at": now_iso(),
            "pool_id": pool_id,
            "execution_route": "ssh",
            "launch_spec_sha256": launch_spec_sha(launch_spec),
            "resource_snapshot_sha256": snapshot_sha,
            "assigned_gpu_uuid": "GPU-fixture",
            "assigned_gpu_idle": True,
            "full_process_visibility": True,
        },
        "launch_spec": launch_spec,
    }
    write_json(
        project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json",
        {
            "schema_version": 2,
            "queue_revision": 1,
            "resource_snapshot": {"status": "stale", "fresh": False, "pools": []},
            "rows": [row],
        },
    )
    materialize_gate_fixture(project, campaign_path, campaign)
    write_usage_record(
        project,
        "completed",
        {"run_id": "completed", "external_candidate_id": "candidate-a", "status": "completed", "actual_gpu_hours": 0.2},
    )
    write_usage_record(
        project,
        "failed",
        {"run_id": "failed", "external_candidate_id": "candidate-a", "status": "failed", "actual_gpu_hours": 0.1},
    )
    write_usage_record(
        project,
        "running",
        {"run_id": "running", "external_candidate_id": "candidate-a", "status": "running", "reserved_gpu_hours": 0.2},
    )
    write_usage_record(
        project,
        "retry",
        {
            "run_id": "retry",
            "external_candidate_id": "candidate-a",
            "status": "completed",
            "actual_gpu_hours": 0.1,
            "attempt_kind": "retry",
        },
    )

    checked = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "budget-check",
            "--project",
            str(project),
            "--candidate-id",
            "candidate-a",
            "--reserve-gpu-hours",
            "0.1",
        ],
        env=env,
    )
    usage = checked["usage"]
    require(usage["completed_actual"] == 0.3, f"completed and retry actual usage must count: {checked}")
    require(usage["failed_actual"] == 0.1, f"failed actual usage must count: {checked}")
    require(usage["running_reserved"] == 0.2, f"running reservation must count: {checked}")
    require(usage["planned_reserved"] == 0.2, f"planned queue reservation must count: {checked}")
    require(usage["total_committed_gpu_hours"] == 0.8, f"all categories must be charged exactly once: {checked}")
    require(checked["remaining"]["candidate_after_request_gpu_hours"] == 0.1, f"candidate ceiling includes smoke/retry: {checked}")

    unknown_path = project / ".autoreskill/coder/experiments/unknown/REMOTE_RUN.json"
    write_json(unknown_path, {"run_id": "unknown", "external_candidate_id": "candidate-a", "status": "failed"})
    unknown = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "budget-check",
            "--project",
            str(project),
            "--candidate-id",
            "candidate-a",
            "--reserve-gpu-hours",
            "0",
        ],
        expected=1,
        env=env,
    )
    require(unknown["unknown_records"], f"unknown consumption must fail closed: {unknown}")
    unknown_path.unlink()

    unscoped_path = project / ".autoreskill/coder/experiments/unscoped/REMOTE_RUN.json"
    write_json(unscoped_path, {"run_id": "unscoped", "status": "running", "reserved_gpu_hours": 0.2})
    unscoped = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "budget-check",
            "--project",
            str(project),
            "--candidate-id",
            "candidate-a",
            "--reserve-gpu-hours",
            "0",
        ],
        expected=1,
        env=env,
    )
    require(
        any("no verifiable external campaign scope" in item["reason"] for item in unscoped["unknown_records"]),
        f"unscoped runtime consumption must fail closed: {unscoped}",
    )
    unscoped_path.unlink()

    for retry_id in ("retry-shared-a", "retry-shared-b"):
        write_usage_record(
            project,
            retry_id,
            {
                "run_id": retry_id,
                "queue_row_id": "shared-retry-row",
                "external_candidate_id": "candidate-b",
                "status": "completed",
                "actual_gpu_hours": 0.1,
            },
        )
    retry_budget = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "budget-check",
            "--project",
            str(project),
            "--candidate-id",
            "candidate-b",
            "--reserve-gpu-hours",
            "0",
        ],
        env=env,
    )
    require(
        retry_budget["usage"]["candidate"]["completed_actual"] == 0.2,
        f"distinct retry run ids sharing a queue row must both be charged: {retry_budget}",
    )

    nan_ceiling = run_json(
        [
            sys.executable,
            str(ADAPTER),
            "budget-check",
            "--project",
            str(project),
            "--candidate-id",
            "candidate-a",
            "--reserve-gpu-hours",
            "0",
            "--user-ceiling-gpu-hours",
            "nan",
        ],
        expected=1,
        env=env,
    )
    require(nan_ceiling["error"]["code"] == "budget_invalid", f"NaN ceiling must fail closed: {nan_ceiling}")

    run_dir = project / ".autoreskill/coder/experiments/track-a/experiment-a"
    command = [
        sys.executable,
        str(ADAPTER),
        "prepare-launch-intent",
        "--project",
        str(project),
        "--row-id",
        "queue-plan-a",
        "--pool-id",
        "ssh:fixture:gpu:one",
        "--run-dir",
        str(run_dir),
        "--approval-ref",
        "user-request:fixture-launch",
    ]

    tampered_campaign = json.loads(json.dumps(campaign))
    tampered_campaign["candidates"][0]["mechanism"]["falsifier"] = "tampered without commitment refresh"
    write_json(campaign_path, tampered_campaign)
    stale_commitment = run_json(command, expected=1, env=env)
    require(
        stale_commitment["error"]["code"] == "commitment_payload_mismatch",
        f"protected candidate fields must be recomputed instead of trusting a copied digest: {stale_commitment}",
    )
    write_json(campaign_path, campaign)

    gate_path = project / ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json"
    committed_gate = read_json(gate_path)
    blocked_gate = json.loads(json.dumps(committed_gate))
    blocked_gate["status"] = "blocked"
    write_json(gate_path, blocked_gate)
    rejected_gate = run_json(command, expected=1, env=env)
    require(
        rejected_gate["error"]["code"] == "external_gate_invalid",
        f"blocked/torn external gate must prevent launch intent: {rejected_gate}",
    )
    write_json(gate_path, committed_gate)

    def expect_prepare_failure(label: str, mutate: Any, code: str) -> None:
        bad_row = json.loads(json.dumps(row))
        mutate(bad_row)
        write_json(
            project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json",
            {
                "schema_version": 2,
                "queue_revision": 1,
                "resource_snapshot": {"status": "stale", "fresh": False, "pools": []},
                "rows": [bad_row],
            },
        )
        rejected = run_json(command, expected=1, env=env)
        require(rejected["error"]["code"] == code, f"{label} must fail as {code}: {rejected}")
        require(not (run_dir / "REMOTE_RUN.json").exists(), f"{label} must not persist a queued intent")

    expect_prepare_failure("missing backend preflight", lambda value: value.pop("backend_preflight"), "backend_preflight_missing")
    expect_prepare_failure(
        "expired atomic lease",
        lambda value: value.__setitem__("lease_expires_at", "2020-01-01T00:00:00+00:00"),
        "lease_invalid",
    )
    expect_prepare_failure(
        "missing SSH GPU UUID",
        lambda value: value["planned_resource_allocation"].__setitem__("gpu_uuids", []),
        "gpu_identity_missing",
    )
    expect_prepare_failure(
        "stale backend preflight",
        lambda value: value["backend_preflight"].__setitem__("checked_at", "2020-01-01T00:00:00+00:00"),
        "backend_preflight_stale",
    )
    expect_prepare_failure(
        "multi-GPU launch shape",
        lambda value: value["launch_spec"]["resource_shape"].__setitem__("gpus", 8),
        "resource_shape_invalid",
    )
    expect_prepare_failure(
        "scout seed drift",
        lambda value: value["launch_spec"].__setitem__("seed", 8),
        "seed_identity_mismatch",
    )
    expect_prepare_failure(
        "protected route drift",
        lambda value: value.__setitem__("execution_route", "bjtu_hpc"),
        "route_identity_mismatch",
    )
    expect_prepare_failure(
        "allocation backend route drift",
        lambda value: value["planned_resource_allocation"].__setitem__("backend", "bjtu_hpc"),
        "route_identity_mismatch",
    )
    expect_prepare_failure(
        "protected GPU-hour drift",
        lambda value: value["planned_resource_allocation"].__setitem__("estimated_gpu_hours", 0.1),
        "budget_identity_mismatch",
    )
    expect_prepare_failure(
        "invalid immutable hash",
        lambda value: value["launch_spec"].__setitem__("code_sha256", "not-a-sha"),
        "launch_identity_invalid",
    )
    expect_prepare_failure(
        "queue commitment drift",
        lambda value: value.__setitem__("protected_commitment_sha256", "f" * 64),
        "commitment_identity_mismatch",
    )
    write_json(
        project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json",
        {
            "schema_version": 2,
            "queue_revision": 1,
            "resource_snapshot": {"status": "stale", "fresh": False, "pools": []},
            "rows": [row],
        },
    )

    # Reproduce an authority change after the final pre-write gate check.  The
    # post-write CAS must remove only the intent it just wrote and fail closed.
    adapter_module = load_adapter_module()
    original_validate_external_gate = adapter_module.validate_external_gate
    gate_validation_calls = 0

    def race_external_gate(*args: Any, **kwargs: Any) -> Any:
        nonlocal gate_validation_calls
        gate_validation_calls += 1
        result = original_validate_external_gate(*args, **kwargs)
        if gate_validation_calls == 2:
            write_json(gate_path, blocked_gate)
        return result

    adapter_module.validate_external_gate = race_external_gate
    race_args = type(
        "PrepareArgs",
        (),
        {
            "project": str(project),
            "row_id": "queue-plan-a",
            "pool_id": "ssh:fixture:gpu:one",
            "run_dir": str(run_dir),
            "approval_ref": "user-request:fixture-launch",
            "launch_spec": None,
        },
    )()
    try:
        adapter_module.prepare_launch_intent(race_args)
    except adapter_module.AdapterError as exc:
        require(
            exc.code in {"external_gate_invalid", "authority_cas_mismatch"},
            f"authority race must fail closed, got {exc.code}: {exc}",
        )
    else:
        raise AssertionError("authority mutation between validation and commit unexpectedly prepared an intent")
    finally:
        adapter_module.validate_external_gate = original_validate_external_gate
        write_json(gate_path, committed_gate)
    require(gate_validation_calls >= 3, "race probe must reach the post-write authority revalidation")
    require(not (run_dir / "REMOTE_RUN.json").exists(), "failed post-write authority CAS must roll back its new intent")

    first_prepare = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    second_prepare = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    prepare_results = []
    for process in (first_prepare, second_prepare):
        stdout, stderr = process.communicate()
        require(process.returncode == 0 and not stderr, f"concurrent intent preparation failed: {stdout} {stderr}")
        prepare_results.append(json.loads(stdout))
    require(
        sorted(result["idempotent"] for result in prepare_results) == [False, True],
        f"concurrent identical intent preparation must have one writer and one idempotent reader: {prepare_results}",
    )
    prepared = next(result for result in prepare_results if not result["idempotent"])
    require(prepared["side_effects_performed"] is False and prepared["status"] == "queued", f"intent is not a launch: {prepared}")
    intent_path = run_dir / "REMOTE_RUN.json"
    intent = read_json(intent_path)
    require(intent["launch_spec"]["command_sha256"], f"exact command digest must be persisted: {intent}")
    require(intent["backend_preflight"]["assigned_gpu_uuid"] == "GPU-fixture", f"exact SSH preflight must be persisted: {intent}")
    require(intent["protected_commitment_sha256"] == row["protected_commitment_sha256"], f"queue/campaign commitment identity must be preserved: {intent}")
    require(intent["backend_idempotency_key"], f"backend idempotency key must be persisted before side effects: {intent}")
    require(
        intent["experiment_id"] == "experiment-a"
        and intent["track_id"] == "track-a"
        and intent["command"]
        and intent["working_dir"] == launch_spec["working_dir"]
        and intent["resource_request"]["execution_route"] == "ssh",
        f"queued intent must satisfy canonical launch metadata identity: {intent}",
    )
    require(
        intent["external_gate"]["gate_sha256"]
        and intent["external_gate"]["lint_sha256"]
        and intent["external_gate"]["slot_map_sha256"],
        f"queued intent must bind the exact committed external gate chain: {intent}",
    )
    require(stat.S_IMODE(intent_path.stat().st_mode) == 0o600, "queued launch intent should be private mode 0600")
    repeated = run_json(command, env=env)
    require(repeated["idempotent"] is True, f"identical intent preparation must be idempotent: {repeated}")

    pristine_intent = read_json(intent_path)
    immutable_policy_tampers = {
        "launch_authorized": False,
        "auto_retry_allowed": True,
        "reconcile_exact_backend_id_before_retry": False,
        "authority_boundary": "tampered authority boundary",
    }
    for field, bad_value in immutable_policy_tampers.items():
        tampered_intent = json.loads(json.dumps(pristine_intent))
        tampered_intent[field] = bad_value
        write_json(intent_path, tampered_intent)
        policy_conflict = run_json(command, expected=1, env=env)
        require(
            policy_conflict["error"]["code"] == "intent_conflict",
            f"tampered immutable policy field {field} must not be accepted idempotently: {policy_conflict}",
        )
        write_json(intent_path, pristine_intent)

    pristine_intent["run_id"] = "tampered-run"
    write_json(intent_path, pristine_intent)
    conflict = run_json(command, expected=1, env=env)
    require(conflict["error"]["code"] == "intent_conflict", f"tampered existing intent must not be overwritten: {conflict}")


def main() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    require("import subprocess" not in source, "resource adapter must not invoke external commands")
    require("import socket" not in source, "resource adapter must not open network sockets")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        env, audit = fake_path(tmp)
        test_normalizers(tmp, env)
        test_budget_and_prepare_intent(tmp, env)
        require(not audit.exists() or not audit.read_text(encoding="utf-8").strip(), "offline adapter invoked an external command")
    print("PASS GPU resource adapter fixtures")


if __name__ == "__main__":
    main()
