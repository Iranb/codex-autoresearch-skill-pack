#!/usr/bin/env python3
"""Offline acceptance fixtures for multi-track and global admission behavior."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUEUE_HELPER = ROOT / "scripts/experiment_next_actions.py"
LEASE_HELPER = ROOT / "scripts/control_plane_lease.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_json(command: list[str], expected: int = 0) -> dict[str, Any]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != expected:
        raise AssertionError(
            f"unexpected exit {result.returncode}, expected {expected}: {' '.join(command)}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"command did not emit JSON: {result.stdout}\n{result.stderr}") from exc


def launch_row(row_id: str, priority: int, decision_class: str = "falsify_core_mechanism") -> dict[str, Any]:
    return {
        "id": row_id,
        "priority": priority,
        "status": "ready",
        "role": "single_innovation",
        "dataset": "CUB",
        "variant": row_id,
        "selected_idea_id": "idea-primary",
        "track_id": "track-primary",
        "track_role": "primary",
        "branch_id": "branch-primary",
        "selection_fingerprint": "selection-v1",
        "launch_identity_hash": f"launch-{row_id}",
        "track_plan_ref": ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json:track-primary",
        "causal_signature": "intervention | causal signal | matched metric change",
        "decision_class": decision_class,
        "why_now": "Cheapest current decision-changing discriminator.",
        "claim_target": f"decision target for {row_id}",
        "hypothesis_prediction": "The matched metric improves without material regression.",
        "falsifier": "The matched intervention does not improve the metric.",
        "outcome_routes": {
            "positive": "retain and confirm",
            "negative": "retire",
            "inconclusive": "run declared control",
            "invalid": "repair protocol",
        },
        "expected_decision_change": f"Retain or retire {row_id}.",
        "decision_target_refs": [f"IDEA_DECISION_LEDGER.json:{row_id}"],
        "comparison_source": "vs matched reproduced baseline",
        "baseline_anchor": "fixture frozen baseline",
        "protocol": "matched CUB split and evaluator",
        "metric_policy_ref": ".autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json:metric_policy",
        "launch_mode": "repeated_variant",
        "execution_route": "local",
        "resource_request": {"backend": "local", "gpu_count": 1, "estimated_gpu_hours": 1.0},
        "mutex_group": f"mutex-{row_id}",
        "parallel_safe": True,
        "owner_thread_id": "fixture-thread",
        "next_action": f"Run {row_id}.",
        "blocker": "",
        "evidence_paths": [f".autoreskill/experiment/{row_id}.json"],
        "updated_at": now_iso(),
    }


def initialize_project(project: Path, row_count: int) -> Path:
    run_json([sys.executable, str(QUEUE_HELPER), "init", "--project", str(project)])
    queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
    queue = read_json(queue_path)
    queue["policy"]["admission_scope"] = "global"
    queue["rows"] = [launch_row(f"{project.name}-row-{index + 1}", 10 + index) for index in range(row_count)]
    write_json(queue_path, queue)
    base = project / ".autoreskill"
    write_json(
        base / "orchestrator/TRACK_PLAN_MATRIX.json",
        {
            "schema_version": 2,
            "selection_fingerprint": "selection-v1",
            "tracks": [
                {
                    "idea_id": "idea-primary",
                    "track_id": "track-primary",
                    "track_role": "primary",
                    "branch_id": "branch-primary",
                    "selected_for_review": True,
                    "selection_fingerprint": "selection-v1",
                    "launch_status": "ready",
                    "hypothesis_contract": {
                        "causal_signature": "intervention | causal signal | matched metric change",
                        "belief_state": "active",
                    },
                }
            ],
        },
    )
    write_json(
        base / "ideation/IDEA_DECISION_LEDGER.json",
        {
            "selected_primary_idea_id": "idea-primary",
            "selection_fingerprint": "selection-v1",
            "decisions": [
                {
                    "idea_id": "idea-primary",
                    "track_id": "track-primary",
                    "lifecycle_status": "selected_primary",
                    "selection_fingerprint": "selection-v1",
                }
            ],
        },
    )
    return queue_path


def shared_snapshot(slot_count: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "proposed_resource_snapshot",
        "status": "fresh",
        "fresh": True,
        "stale": False,
        "checked_at": now_iso(),
        "source_kind": "offline_fixture",
        "source_ref": "fixture-shared-snapshot",
        "source_sha256": "a" * 64,
        "pools": [
            {
                "pool_id": "local-shared-pool",
                "status": "available",
                "backend": "local",
                "execution_route": "local",
                "launch_slots": slot_count,
                "free_vram_mb": 24576,
                "resource_ids": [f"fixture-gpu-{index}" for index in range(slot_count)],
                "fit_confidence": "verified_snapshot",
            }
        ],
    }


def schedule_global(projects: list[Path], snapshot_path: Path, out_path: Path) -> dict[str, Any]:
    command = [sys.executable, str(QUEUE_HELPER), "schedule-global"]
    for project in projects:
        command.extend(["--project", str(project)])
    command.extend(["--resource-snapshot", str(snapshot_path), "--out", str(out_path)])
    return run_json(command)


def acquire_lease(*, owner: str, operation: str, project: Path | None = None, lease_file: Path | None = None) -> None:
    command = [sys.executable, str(LEASE_HELPER), "acquire", "--owner", owner, "--operation", operation]
    if project is not None:
        command.extend(["--project", str(project)])
    elif lease_file is not None:
        command.extend(["--scope", "global-admission", "--lease-file", str(lease_file)])
    else:
        raise AssertionError("project or lease_file is required")
    run_json(command)


def test_three_projects_twelve_assignments(root: Path) -> None:
    projects = [root / name for name in ["project-a", "project-b", "project-c"]]
    for project in projects:
        initialize_project(project, 4)
    empty_project = root / "project-empty"
    initialize_project(empty_project, 0)
    snapshot_path = root / "shared-snapshot.json"
    write_json(snapshot_path, shared_snapshot(12))
    schedule_path = root / "global-schedule.json"
    result = schedule_global([*projects, empty_project], snapshot_path, schedule_path)
    require(result.get("ok") is True, f"global schedule failed: {result}")
    assignments = result.get("assignments") or []
    require(len(assignments) == 12, f"expected 12 advisory assignments: {result}")
    require(len({row["project"] for row in assignments[:3]}) == 3, "same-class first pass must rotate projects")
    require(not any(row["project"] == str(empty_project.resolve()) for row in assignments), "empty project reserved capacity")
    ids = [value for row in assignments for value in row.get("allocated_resource_ids") or []]
    require(len(ids) == len(set(ids)) == 12, f"concrete resources were duplicated: {ids}")
    require(sum(1 for row in assignments if row.get("claimable_first") is True) == 1, "exactly one assignment must be first")
    require(assignments[0].get("claimable_first") is True, "only assignment index zero may be claimable")

    second_path = root / "global-schedule-second.json"
    second = schedule_global([*projects, empty_project], snapshot_path, second_path)
    require(second["global_schedule_sha256"] == result["global_schedule_sha256"], "same inputs must hash identically")
    require(
        [row["assignment_sha256"] for row in second["assignments"]]
        == [row["assignment_sha256"] for row in assignments],
        "same inputs must preserve assignment hashes",
    )


def test_global_claim_and_leases(root: Path) -> None:
    projects = [root / "claim-a", root / "claim-b"]
    for project in projects:
        initialize_project(project, 1)
    snapshot_path = root / "claim-snapshot.json"
    schedule_path = root / "claim-schedule.json"
    write_json(snapshot_path, shared_snapshot(2))
    schedule_global(projects, snapshot_path, schedule_path)
    schedule = read_json(schedule_path)
    first, second = schedule["assignments"]
    owner = "fixture-global-controller"
    global_lease = root / "GLOBAL_ADMISSION_LEASE.json"
    run_json(
        [
            sys.executable,
            str(LEASE_HELPER),
            "acquire",
            "--scope",
            "global-admission",
            "--lease-file",
            str(global_lease),
            "--owner",
            owner,
            "--operation",
            "fixture_schedule_and_admit",
        ]
    )
    first_project = Path(first["project"])
    run_json(
        [
            sys.executable,
            str(LEASE_HELPER),
            "acquire",
            "--project",
            str(first_project),
            "--owner",
            owner,
            "--operation",
            "fixture_global_claim",
        ]
    )
    claim_command = [
        sys.executable,
        str(QUEUE_HELPER),
        "claim-assignment",
        "--project",
        str(first_project),
        "--row-id",
        first["row_id"],
        "--pool-id",
        first["pool_id"],
        "--owner",
        owner,
        "--expected-revision",
        str(first["queue_revision"]),
        "--global-plan",
        str(schedule_path),
        "--global-schedule-sha256",
        schedule["global_schedule_sha256"],
        "--assignment-sha256",
        first["assignment_sha256"],
        "--global-lease-file",
        str(global_lease),
    ]
    claimed = run_json(claim_command)
    allocation = claimed.get("planned_resource_allocation") or {}
    require(allocation.get("global_schedule_sha256") == schedule["global_schedule_sha256"], "claim lost schedule identity")
    require(allocation.get("assignment_sha256") == first["assignment_sha256"], "claim lost assignment identity")
    idempotent = run_json(claim_command)
    require(idempotent.get("idempotent") is True, f"identical global claim must be idempotent: {idempotent}")

    second_project = Path(second["project"])
    run_json(
        [
            sys.executable,
            str(LEASE_HELPER),
            "acquire",
            "--project",
            str(second_project),
            "--owner",
            owner,
            "--operation",
            "fixture_nonfirst_claim",
        ]
    )
    denied = run_json(
        [
            sys.executable,
            str(QUEUE_HELPER),
            "claim-assignment",
            "--project",
            str(second_project),
            "--row-id",
            second["row_id"],
            "--pool-id",
            second["pool_id"],
            "--owner",
            owner,
            "--expected-revision",
            str(second["queue_revision"]),
            "--global-plan",
            str(schedule_path),
            "--global-schedule-sha256",
            schedule["global_schedule_sha256"],
            "--assignment-sha256",
            second["assignment_sha256"],
            "--global-lease-file",
            str(global_lease),
        ],
        expected=1,
    )
    require(denied.get("error", {}).get("code") == "global_assignment_stale", f"non-first claim was not rejected: {denied}")


def test_global_ordering_and_busy_project(root: Path) -> None:
    optimize = root / "ordering-optimize"
    repair = root / "ordering-repair"
    optimize_queue = initialize_project(optimize, 1)
    repair_queue = initialize_project(repair, 1)
    optimize_payload = read_json(optimize_queue)
    repair_payload = read_json(repair_queue)
    optimize_payload["rows"][0]["decision_class"] = "optimize_supported_mechanism"
    repair_payload["rows"][0]["decision_class"] = "repair_validity"
    write_json(optimize_queue, optimize_payload)
    write_json(repair_queue, repair_payload)
    snapshot_path = root / "ordering-snapshot.json"
    write_json(snapshot_path, shared_snapshot(2))
    schedule_path = root / "ordering-schedule.json"
    schedule = schedule_global([optimize, repair], snapshot_path, schedule_path)
    require(
        schedule["assignments"][0]["project"] == str(repair.resolve()),
        f"acquisition class must dominate project fairness and row priority: {schedule}",
    )

    acquire_lease(owner="foreign-project-controller", operation="fixture_busy", project=repair)
    busy_path = root / "ordering-busy-schedule.json"
    busy = schedule_global([optimize, repair], snapshot_path, busy_path)
    require(
        all(item["project"] != str(repair.resolve()) for item in busy.get("assignments") or []),
        f"busy project must be excluded from global scheduling: {busy}",
    )
    require(
        any(item.get("reason") == "project_control_busy" for item in busy.get("rejections") or []),
        f"busy project needs an exact rejection reason: {busy}",
    )


def test_global_claim_staleness_guards(root: Path) -> None:
    project = root / "stale-claim-project"
    queue_path = initialize_project(project, 1)
    snapshot_path = root / "stale-claim-snapshot.json"
    schedule_path = root / "stale-claim-schedule.json"
    write_json(snapshot_path, shared_snapshot(1))
    schedule_global([project], snapshot_path, schedule_path)
    schedule = read_json(schedule_path)
    assignment = schedule["assignments"][0]
    owner = "stale-guard-controller"
    global_lease = root / "stale-guard-global-lease.json"
    acquire_lease(owner=owner, operation="fixture_stale_guard", lease_file=global_lease)
    acquire_lease(owner=owner, operation="fixture_stale_guard", project=project)
    command = [
        sys.executable,
        str(QUEUE_HELPER),
        "claim-assignment",
        "--project",
        str(project),
        "--row-id",
        assignment["row_id"],
        "--pool-id",
        assignment["pool_id"],
        "--owner",
        owner,
        "--expected-revision",
        str(assignment["queue_revision"]),
        "--global-plan",
        str(schedule_path),
        "--global-schedule-sha256",
        schedule["global_schedule_sha256"],
        "--assignment-sha256",
        assignment["assignment_sha256"],
        "--global-lease-file",
        str(global_lease),
    ]

    original_queue = read_json(queue_path)
    changed_queue = json.loads(json.dumps(original_queue))
    changed_queue["decision_log"].append({"decision": "fixture drift"})
    write_json(queue_path, changed_queue)
    stale_queue = run_json(command, expected=1)
    require(stale_queue["error"]["code"] == "global_queue_stale", f"queue hash drift must fail closed: {stale_queue}")
    write_json(queue_path, original_queue)

    original_snapshot = read_json(snapshot_path)
    changed_snapshot = json.loads(json.dumps(original_snapshot))
    changed_snapshot["source_ref"] = "changed-after-schedule"
    write_json(snapshot_path, changed_snapshot)
    stale_snapshot = run_json(command, expected=1)
    require(
        stale_snapshot["error"]["code"] == "global_snapshot_stale",
        f"snapshot hash drift must fail closed: {stale_snapshot}",
    )
    write_json(snapshot_path, original_snapshot)

    expired = read_json(global_lease)
    expired["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat()
    write_json(global_lease, expired)
    stale_lease = run_json(command, expected=1)
    require(stale_lease["error"]["code"] == "global_lease_conflict", f"expired lease must fail closed: {stale_lease}")


def test_lease_races(root: Path) -> None:
    lease_path = root / "race-global-lease.json"
    command_prefix = [
        sys.executable,
        str(LEASE_HELPER),
        "acquire",
        "--scope",
        "global-admission",
        "--lease-file",
        str(lease_path),
        "--operation",
        "race",
    ]
    first = subprocess.Popen(command_prefix + ["--owner", "racer-a"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    second = subprocess.Popen(command_prefix + ["--owner", "racer-b"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    first.communicate()
    second.communicate()
    require(sorted([first.returncode, second.returncode]) == [0, 2], "exactly one global lease racer must win")

    project = root / "race-project"
    project.mkdir(parents=True, exist_ok=True)
    project_prefix = [
        sys.executable,
        str(LEASE_HELPER),
        "acquire",
        "--project",
        str(project),
        "--operation",
        "race",
    ]
    writer_a = subprocess.Popen(project_prefix + ["--owner", "writer-a"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    writer_b = subprocess.Popen(project_prefix + ["--owner", "writer-b"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    writer_a.communicate()
    writer_b.communicate()
    require(sorted([writer_a.returncode, writer_b.returncode]) == [0, 2], "exactly one project writer must win")


def test_frontier_deficit(root: Path) -> None:
    project = root / "frontier-project"
    initialize_project(project, 0)
    base = project / ".autoreskill"
    tracks: list[dict[str, Any]] = []
    for index in range(4):
        track_id = f"track-{index + 1}"
        review_ref = f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json"
        write_json(
            base / review_ref,
            {
                "track_id": track_id,
                "dataset": "CUB",
                "minimum_pilot": {"decision": f"falsify {track_id}"},
            },
        )
        tracks.append(
            {
                "idea_id": f"idea-{index + 1}",
                "track_id": track_id,
                "track_role": "primary" if index == 0 else "alternate",
                "idea_lifecycle_status": "selected_primary" if index == 0 else "alternate_track",
                "planning_admitted": True,
                "review_packet_ref": review_ref,
                "review_packet_sha256": f"{index + 1}" * 64,
                "idea_decision_ref": f"ideation/IDEA_DECISION_LEDGER.json:{track_id}",
                "dataset": "CUB",
                "hypothesis_contract": {"belief_state": "active"},
            }
        )
    write_json(
        base / "orchestrator/TRACK_PLAN_MATRIX.json",
        {"schema_version": 3, "selection_fingerprint": "frontier-v1", "tracks": tracks},
    )
    frontier = run_json([sys.executable, str(QUEUE_HELPER), "frontier", "--project", str(project)])
    require(frontier["frontier_target"] == 4, f"frontier target must be bounded by four declared pilots: {frontier}")
    require(frontier["frontier_deficit"] == 4, f"expected four missing supplied rows: {frontier}")
    require(frontier["frontier_actionable"] is True, f"declared pilots should be locally actionable: {frontier}")
    require(len(frontier["candidate_track_ids"]) == 4, f"all admitted tracks should be visible: {frontier}")


def test_frontier_dependency_wait_and_idle_bound(root: Path) -> None:
    dependency_project = root / "frontier-dependency-project"
    queue_path = initialize_project(dependency_project, 0)
    base = dependency_project / ".autoreskill"
    queue = read_json(queue_path)
    running = launch_row("pending-primary-pilot", 1)
    running["status"] = "running"
    running["lease_owner"] = "fixture-running-worker"
    running["lease_acquired_at"] = now_iso()
    running["lease_expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(
        microsecond=0
    ).isoformat()
    running["resource_allocation"] = {"backend": "local", "gpu_id": "fixture-running-gpu"}
    queue["rows"] = [running]
    write_json(queue_path, queue)
    review_ref = "planner/tracks/track-primary/EXPERIMENT_REVIEW_PACKET.json"
    write_json(
        base / review_ref,
        {
            "track_id": "track-primary",
            "dataset": "CUB",
            "minimum_pilot": {"decision": "first pilot already running"},
            "frontier_candidates": [
                {
                    "id": "confirmation-after-pilot",
                    "kind": "confirmation",
                    "decision_target": "confirm-primary",
                    "depends_on_rows": ["pending-primary-pilot"],
                }
            ],
        },
    )
    write_json(
        base / "orchestrator/TRACK_PLAN_MATRIX.json",
        {
            "schema_version": 3,
            "selection_fingerprint": "selection-v1",
            "tracks": [
                {
                    "idea_id": "idea-primary",
                    "track_id": "track-primary",
                    "track_role": "primary",
                    "idea_lifecycle_status": "selected_primary",
                    "planning_admitted": True,
                    "selected_for_review": True,
                    "selection_fingerprint": "selection-v1",
                    "review_packet_ref": review_ref,
                    "review_packet_sha256": "d" * 64,
                    "idea_decision_ref": "ideation/IDEA_DECISION_LEDGER.json:idea-primary",
                    "dataset": "CUB",
                    "hypothesis_contract": {"belief_state": "active"},
                }
            ],
        },
    )
    waiting = run_json([sys.executable, str(QUEUE_HELPER), "frontier", "--project", str(dependency_project)])
    require(waiting["frontier_deficit"] == 1, f"dependency-locked follow-up should remain visible: {waiting}")
    require(waiting["frontier_actionable"] is False, f"dependency wait cannot materialize work: {waiting}")
    require(waiting["frontier_blocker_code"] == "scientific_dependency_wait", f"wrong wait blocker: {waiting}")
    require(not waiting["admissible_candidates"], f"dependency wait invented an actionable row: {waiting}")

    idle_project = root / "frontier-idle-bound-project"
    idle_queue_path = initialize_project(idle_project, 0)
    idle_base = idle_project / ".autoreskill"
    idle_review_ref = "planner/tracks/track-primary/EXPERIMENT_REVIEW_PACKET.json"
    write_json(
        idle_base / idle_review_ref,
        {"track_id": "track-primary", "dataset": "CUB", "minimum_pilot": {"decision": "one pilot"}},
    )
    write_json(
        idle_base / "orchestrator/TRACK_PLAN_MATRIX.json",
        {
            "schema_version": 3,
            "selection_fingerprint": "selection-v1",
            "tracks": [
                {
                    "idea_id": "idea-primary",
                    "track_id": "track-primary",
                    "track_role": "primary",
                    "idea_lifecycle_status": "selected_primary",
                    "planning_admitted": True,
                    "selected_for_review": True,
                    "selection_fingerprint": "selection-v1",
                    "review_packet_ref": idle_review_ref,
                    "review_packet_sha256": "e" * 64,
                    "idea_decision_ref": "ideation/IDEA_DECISION_LEDGER.json:idea-primary",
                    "dataset": "CUB",
                    "hypothesis_contract": {"belief_state": "active"},
                }
            ],
        },
    )
    idle_queue = read_json(idle_queue_path)
    idle_queue["resource_snapshot"] = shared_snapshot(26)
    write_json(idle_queue_path, idle_queue)
    bounded = run_json([sys.executable, str(QUEUE_HELPER), "frontier", "--project", str(idle_project)])
    require(bounded["fresh_fitting_idle_slots"] == 26, f"fixture did not expose 26 idle slots: {bounded}")
    require(bounded["frontier_target"] == 1, f"idle capacity must not invent extra rows: {bounded}")
    require(len(bounded["admissible_candidates"]) == 1, f"expected exactly one declared candidate: {bounded}")


def test_dashboard_control_and_frontier_fields(root: Path) -> None:
    projects = [root / "dashboard-a", root / "dashboard-b"]
    for project in projects:
        initialize_project(project, 1)
    project_dashboard = root / "project-dashboard.md"
    run_json(
        [
            sys.executable,
            str(QUEUE_HELPER),
            "render",
            "--project",
            str(projects[0]),
            "--out",
            str(project_dashboard),
        ]
    )
    project_text = project_dashboard.read_text(encoding="utf-8")
    for marker in ["Admission scope", "Project control owner", "Ready frontier", "Track Role", "Evidence Ceiling"]:
        require(marker in project_text, f"project dashboard omitted {marker!r}")

    global_dashboard = root / "global-dashboard.md"
    command = [sys.executable, str(QUEUE_HELPER), "render-global"]
    for project in projects:
        command.extend(["--project", str(project)])
    command.extend(["--out", str(global_dashboard)])
    run_json(command)
    global_text = global_dashboard.read_text(encoding="utf-8")
    for marker in ["Project Control", "Admission Scope", "Frontier Target", "Control Owner", "Track Role"]:
        require(marker in global_text, f"global dashboard omitted {marker!r}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="autoreskill-multi-track-") as raw:
        root = Path(raw)
        test_three_projects_twelve_assignments(root)
        test_global_claim_and_leases(root)
        test_global_ordering_and_busy_project(root)
        test_global_claim_staleness_guards(root)
        test_lease_races(root)
        test_frontier_deficit(root)
        test_frontier_dependency_wait_and_idle_bound(root)
        test_dashboard_control_and_frontier_fields(root)
    print("PASS multi_track_parallelism fixtures")


if __name__ == "__main__":
    main()
