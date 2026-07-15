#!/usr/bin/env python3
"""Offline regression fixture for external queued-intent reconciliation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import run_reconcile


SCRIPT = Path(__file__).with_name("run_reconcile.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(command: list[str], expect: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != expect:
        raise AssertionError(
            f"unexpected exit {proc.returncode}, expected {expect}: {' '.join(command)}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return proc


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="external-reconcile-fixture-"))
    try:
        base = root / ".autoreskill"
        track_id = "track-external"
        experiment_id = "exp-external-pilot"
        queue_row_id = "queue-external-pilot"
        candidate_id = "candidate-external-source"
        campaign_sha = "a" * 64
        commitment_sha = "b" * 64
        snapshot_sha = "c" * 64
        source_sha = "d" * 64
        backend_key = "e" * 64
        exp_dir = base / "coder/experiments" / track_id / experiment_id
        manifest = {
            "experiment_id": experiment_id,
            "track_id": track_id,
            "queue_row_id": queue_row_id,
            "selected_idea_id": "idea-fragment-external",
            "innovation_mechanism": "fixture external mechanism",
            "mechanism_type": "ALGO",
            "promotion_stage": "candidate",
            "evidence_source_mode": "external_material",
            "external_campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
            "external_campaign_sha256": campaign_sha,
            "external_candidate_id": candidate_id,
            "protected_commitment_sha256": commitment_sha,
            "evidence_tier": "pilot_only",
            "execution_route": "ssh",
            "resource_request": {"backend": "ssh", "gpu_count": 1, "estimated_gpu_hours": 0.25},
            "primary_metric": "accuracy",
            "metric_direction": "higher",
            "dataset": "fixture",
            "data_split": "fixture-split",
            "evaluate_command": "python evaluate.py --fixture",
            "locked_protocol": {"dataset": "fixture", "primary_metric": "accuracy"},
            "source_snapshot": {"fixture": True},
        }
        write(exp_dir / "EXPERIMENT_MANIFEST.json", manifest)
        write(exp_dir / "results/metrics.json", {"baseline": 0.5, "proposed": 0.7, "primary_metric": "accuracy"})
        write(
            base / "planner/EXPERIMENT_REVIEW_PACKET.json",
            {
                **{key: manifest[key] for key in (
                    "track_id",
                    "queue_row_id",
                    "selected_idea_id",
                    "external_campaign_ref",
                    "external_campaign_sha256",
                    "external_candidate_id",
                    "protected_commitment_sha256",
                    "evidence_tier",
                    "execution_route",
                    "resource_request",
                )},
                "metric_direction": "higher",
            },
        )
        write(
            base / "orchestrator/INNOVATION_PACKET.json",
            {
                "selected_idea_id": manifest["selected_idea_id"],
                "track_id": track_id,
                "innovation_mechanism": manifest["innovation_mechanism"],
                "mechanism_type": "ALGO",
                "external_campaign_ref": manifest["external_campaign_ref"],
                "external_campaign_sha256": campaign_sha,
                "external_candidate_id": candidate_id,
                "protected_commitment_sha256": commitment_sha,
                "evidence_tier": "pilot_only",
                "execution_route": "ssh",
            },
        )

        allocation = {
            "pool_id": "ssh-fixture-pool",
            "backend": "ssh",
            "execution_route": "ssh",
            "gpu_uuids": ["GPU-FIXTURE-EXTERNAL"],
            "gpu_count": 1,
            "estimated_gpu_hours": 0.25,
            "resource_snapshot_sha256": snapshot_sha,
            "resource_snapshot_source_ref": ".autoreskill/experiment/fixture-scan.json",
            "resource_snapshot_source_sha256": source_sha,
            "resource_snapshot_checked_at": "2026-07-11T00:00:00+00:00",
        }
        preflight = {
            "status": "passed",
            "checked_at": "2026-07-11T00:00:00+00:00",
            "pool_id": allocation["pool_id"],
            "execution_route": "ssh",
            "launch_spec_sha256": "f" * 64,
            "resource_snapshot_sha256": snapshot_sha,
            "assigned_gpu_uuid": "GPU-FIXTURE-EXTERNAL",
            "assigned_gpu_idle": True,
            "full_process_visibility": True,
        }
        launch_spec = {
            "command_argv": ["python", "train.py", "--seed", "7"],
            "command_sha256": "1" * 64,
            "launch_spec_sha256": "f" * 64,
            "code_ref": "code.tar",
            "code_sha256": "2" * 64,
            "dataset_ref": "dataset.json",
            "dataset_sha256": "3" * 64,
            "environment_ref": "environment.lock",
            "environment_sha256": "4" * 64,
            "launcher_template_sha256": "5" * 64,
            "resource_shape": {"gpus": 1},
            "seed": 7,
        }
        intent = {
            "schema_version": 1,
            "status": "queued",
            "prepared_at": "2026-07-11T00:00:01+00:00",
            "started_at": "",
            "run_id": "gpuidea_fixture_external",
            "experiment_id": experiment_id,
            "track_id": track_id,
            "queue_row_id": queue_row_id,
            "queue_revision": 3,
            "row_revision": 2,
            "lease_owner": "fixture-owner",
            "external_campaign_ref": manifest["external_campaign_ref"],
            "external_campaign_sha256": campaign_sha,
            "external_candidate_id": candidate_id,
            "protected_commitment_sha256": commitment_sha,
            "external_gate": {
                "gate_ref": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
                "gate_sha256": "7" * 64,
                "lint_ref": "ideation/committed/NON_PAPERNEXUS_IDEA_LINT.fixture.json",
                "lint_sha256": "8" * 64,
                "slot_map_ref": "ideation/committed/INNOVATION_SLOT_MAP.fixture.json",
                "slot_map_sha256": "9" * 64,
            },
            "backend": "ssh",
            "execution_route": "ssh",
            "command": "python train.py --seed 7",
            "working_dir": str(root),
            "environment": {"ref": "environment.lock", "sha256": "4" * 64},
            "resource_request": manifest["resource_request"],
            "resource_allocation": allocation,
            "planned_resource_allocation": allocation,
            "backend_preflight": preflight,
            "resource_pool_id": allocation["pool_id"],
            "resource_snapshot_ref": allocation["resource_snapshot_source_ref"],
            "resource_snapshot_sha256": snapshot_sha,
            "resource_snapshot_source_sha256": source_sha,
            "resource_snapshot_checked_at": allocation["resource_snapshot_checked_at"],
            "launch_spec": launch_spec,
            "budget": {"locked_gpu_hours": 0.25, "budget_commitment_sha256": "6" * 64},
            "authorization": {"all_three_authorities_passed": True, "approval_ref": "fixture-approval"},
            "backend_idempotency_key": backend_key,
            "evidence_tier": "pilot_only",
            "promotion_stage": "candidate",
            "promotion_decision": "record_only",
            "session_id": "ssh_fixture_external",
            "ssh_session_id": "ssh_fixture_external",
            "side_effects_performed": False,
            "launch_authorized": True,
            "auto_retry_allowed": False,
            "reconcile_exact_backend_id_before_retry": True,
            "authority_boundary": "queued local intent only",
        }
        intent["immutable_launch_intent_sha256"] = run_reconcile.stable_hash(
            run_reconcile.external_intent_payload(intent)
        )
        write(exp_dir / "REMOTE_RUN.json", intent)
        before = json.loads(json.dumps(intent))

        run([sys.executable, str(SCRIPT), "--project", str(root), "--status", "completed"])
        reconciled = json.loads((exp_dir / "REMOTE_RUN.json").read_text(encoding="utf-8"))
        for field in run_reconcile.EXTERNAL_INTENT_IMMUTABLE_FIELDS:
            require(reconciled.get(field) == before.get(field), f"reconcile changed immutable field {field}")
        require(
            reconciled["immutable_launch_intent_sha256"] == before["immutable_launch_intent_sha256"],
            "reconcile changed immutable intent digest",
        )
        require(reconciled["status"] == "completed", f"runtime status should reconcile: {reconciled}")
        require(
            reconciled["promotion_decision"] == "record_only",
            f"pilot-only intent must remain record_only: {reconciled}",
        )
        ledger = json.loads((base / "coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        entry = ledger["entries"][0]
        require(entry["run_id"] == intent["run_id"], f"ledger must retain backend run identity: {entry}")
        require(entry["promotion_decision"] == "record_only", f"pilot must not become candidate_supported: {entry}")
        require(entry["evidence_tier"] == "pilot_only", f"ledger must preserve evidence tier: {entry}")
        require(ledger["candidate_runs"] == [], f"pilot must not enter candidate_runs: {ledger}")

        tampered = dict(reconciled)
        tampered["launch_spec"] = {**launch_spec, "seed": 8}
        write(exp_dir / "REMOTE_RUN.json", tampered)
        rejected = run(
            [sys.executable, str(SCRIPT), "--project", str(root), "--status", "completed"],
            expect=1,
        )
        require("immutable_launch_intent_sha256" in rejected.stderr, f"tampered intent must fail closed: {rejected.stderr}")

        write(exp_dir / "REMOTE_RUN.json", reconciled)
        noncanonical = base / "coder/experiments/noncanonical"
        exp_dir.rename(noncanonical)
        rejected = run(
            [sys.executable, str(SCRIPT), "--project", str(root), "--status", "completed"],
            expect=1,
        )
        require("outside canonical" in rejected.stderr, f"noncanonical external run dir must fail: {rejected.stderr}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("PASS external queued-intent reconcile fixture")


if __name__ == "__main__":
    main()
