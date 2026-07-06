#!/usr/bin/env python3
"""Regression checks for local-first heartbeat and async wait policy."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GOAL = ROOT / "scripts/goal.py"
TRIAGE = ROOT.parent / "autoreskill-autopilot-controller/scripts/blocker_triage.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def run_json(cmd: list[str], expect_code: int = 0) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != expect_code:
        raise AssertionError(
            f"unexpected exit code {proc.returncode}, expected {expect_code}: {' '.join(cmd)}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"command did not emit JSON: {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}") from exc


def make_project(tmp: Path, stage: str) -> Path:
    project = tmp / stage
    base = project / ".autoreskill"
    base.mkdir(parents=True, exist_ok=True)
    write_json(
        base / "goal_state.json",
        {
            "schema_version": 1,
            "project_root": str(project),
            "goal": "async wait policy fixture",
            "paperNexus": {"mode": "remote_mcp", "corpus": "fixture"},
            "stage": stage,
            "owner": "WorkflowGuard",
            "next_action": "fixture_next_action",
            "blocking_reason": None,
            "autonomy_level": "full_auto_bounded",
            "goal_type": "paper_producing_top_tier",
            "claim_mode": "strong_paper_claims",
            "iteration": 0,
            "updated_at": now_iso(),
        },
    )
    write_json(
        base / "autopilot_policy.json",
        {
            "schema_version": 1,
            "autonomy_level": "full_auto_bounded",
            "async_poll_interval_minutes": 1,
            "experiment_monitor_default_interval_minutes": 5,
            "repair_retry_interval_minutes": 1,
            "max_repair_attempts_per_blocker": 5,
            "goal_type": "paper_producing_top_tier",
            "claim_mode": "strong_paper_claims",
        },
    )
    for rel in ["decision_log.jsonl", "blocker_ledger.jsonl", "repair_queue.jsonl", "async_jobs.jsonl", "mailbox.jsonl"]:
        touch(base / rel)
    (base / "memory.md").write_text("# Fixture\n", encoding="utf-8")
    return project


def async_job(stage: str, action: str, reason: str, job_id: str = "async_job") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "job_id": job_id,
        "kind": "async",
        "stage": stage,
        "action": action,
        "reason": reason,
        "status": "pending",
        "attempts": 0,
        "max_attempts": 5,
        "created_at": now_iso(),
        "next_poll_at": now_iso(),
    }


def repair_job(stage: str, action: str = "schedule_repair", reason: str = "local repair is ready") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "job_id": "repair_job",
        "kind": "repair",
        "stage": stage,
        "action": action,
        "reason": reason,
        "status": "pending",
        "attempts": 0,
        "max_attempts": 5,
        "created_at": now_iso(),
        "next_retry_at": now_iso(),
    }


def write_active_discovery(project: Path) -> None:
    write_json(
        project / ".autoreskill/literature/LITERATURE_DISCOVERY_RUN.json",
        {"runId": "run-active", "current": {"status": "running", "reportAvailable": False}},
    )


def write_ready_discovery(project: Path) -> None:
    write_json(
        project / ".autoreskill/literature/LITERATURE_DISCOVERY_RUN.json",
        {"runId": "run-ready", "current": {"status": "completed", "reportAvailable": True, "isTerminal": True}},
    )


def write_graph_plan(project: Path) -> None:
    write_json(
        project / ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
        {"selected_papers": [{"paper_ref": "paper-1", "import_action": "import", "title": "Fixture Paper"}]},
    )


def write_graph_decision_complete(project: Path) -> None:
    write_json(
        project / ".autoreskill/graph/GRAPH_BUILD_DECISION.json",
        {"decision": "complete", "source_backed_graph_claim": True},
    )


def write_graph_import_status(project: Path, status: str) -> None:
    if status == "complete":
        task = {
            "id": "task-1",
            "status": "completed",
            "stage": "completed",
            "graphVisibilityStatus": "complete",
            "semanticStatus": "complete",
            "authoritativeSyncStatus": "complete",
        }
        counts = {
            "submitted_import_count": 1,
            "completed_import_count": 1,
            "authoritative_sync_completed_count": 1,
        }
    else:
        task = {
            "id": "task-1",
            "status": "running",
            "stage": "processing",
            "graphVisibilityStatus": "pending",
            "semanticStatus": "pending",
            "authoritativeSyncStatus": "pending",
        }
        counts = {
            "submitted_import_count": 1,
            "completed_import_count": 0,
            "authoritative_sync_completed_count": 0,
        }
    write_json(
        project / ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json",
        {
            "taskIds": ["task-1"],
            "targetTasks": [task],
            "tasks": [task],
            **counts,
        },
    )


def write_active_experiment(project: Path) -> None:
    base = project / ".autoreskill"
    write_json(base / "coder/EXPERIMENT_LEDGER.json", {"ready_for_analysis": False})
    write_json(base / "coder/experiments/idea/track/REMOTE_RUN.json", {"status": "running", "run_id": "run-active"})


def run_tick(project: Path) -> dict[str, Any]:
    return run_json(["python", str(GOAL), "tick", "--project", str(project)])


def test_due_repair_preempts_due_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "topic_search")
        base = project / ".autoreskill"
        write_active_discovery(project)
        append_jsonl(base / "async_jobs.jsonl", async_job("topic_search", "poll_literature_discovery", "literature_discovery run pending"))
        append_jsonl(
            base / "repair_queue.jsonl",
            repair_job(
                "topic_search",
                reason="papernexus/LITERATURE_DISCOVERY_TRIAGE.json; papernexus/PAPER_SELECTION_SCORECARD.json; papernexus/GRAPH_IMPORT_PLAN.json",
            ),
        )
        payload = run_tick(project)
        require(payload["action"] == "dispatch_repair", f"due repair should dispatch before due async: {payload}")


def test_active_discovery_dispatches_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "topic_search")
        base = project / ".autoreskill"
        write_active_discovery(project)
        append_jsonl(base / "async_jobs.jsonl", async_job("topic_search", "poll_literature_discovery", "literature_discovery run pending"))
        payload = run_tick(project)
        require(payload["action"] == "dispatch_async_poll", f"active discovery should dispatch async poll: {payload}")
        require(payload["job"].get("wait_kind") == "papernexus_literature_discovery", f"wait_kind missing: {payload}")


def test_ready_discovery_supersedes_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "topic_search")
        base = project / ".autoreskill"
        write_ready_discovery(project)
        append_jsonl(base / "async_jobs.jsonl", async_job("topic_search", "poll_literature_discovery", "literature_discovery report ready"))
        payload = run_tick(project)
        require(payload["action"] in {"queued_repair_handoff", "repair_already_queued"}, f"ready discovery should route local capture: {payload}")
        statuses = [row["status"] for row in rows(base / "async_jobs.jsonl")]
        require("superseded" in statuses, f"ready discovery async should be superseded, got {statuses}")


def test_graph_import_complete_supersedes_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "graph_build")
        base = project / ".autoreskill"
        write_graph_plan(project)
        write_graph_decision_complete(project)
        write_graph_import_status(project, "complete")
        append_jsonl(base / "async_jobs.jsonl", async_job("graph_build", "poll_graph_import_sync", "import_workflow authoritative sync not complete"))
        payload = run_tick(project)
        require(payload["action"] == "advanced", f"complete graph import should advance after superseding stale async: {payload}")
        statuses = [row["status"] for row in rows(base / "async_jobs.jsonl")]
        require("superseded" in statuses, f"complete graph import async should be superseded, got {statuses}")


def test_active_graph_import_dispatches_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "graph_build")
        base = project / ".autoreskill"
        write_graph_plan(project)
        write_graph_import_status(project, "running")
        append_jsonl(base / "async_jobs.jsonl", async_job("graph_build", "poll_graph_import_sync", "import_workflow queued/running task"))
        payload = run_tick(project)
        require(payload["action"] == "dispatch_async_poll", f"active graph import should dispatch async poll: {payload}")
        require(payload["job"].get("wait_kind") == "papernexus_graph_import_sync", f"wait_kind missing: {payload}")


def test_active_experiment_dispatches_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "experiment")
        base = project / ".autoreskill"
        write_active_experiment(project)
        append_jsonl(base / "async_jobs.jsonl", async_job("experiment", "poll_experiment_run", "promoted best_run waiting for active experiment"))
        payload = run_tick(project)
        require(payload["action"] == "dispatch_async_poll", f"active experiment should dispatch async poll: {payload}")
        require(payload["job"].get("wait_kind") == "experiment_runtime_or_resource", f"wait_kind missing: {payload}")


def test_experiment_poll_wrong_stage_supersedes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "topic_search")
        base = project / ".autoreskill"
        append_jsonl(base / "async_jobs.jsonl", async_job("topic_search", "poll_experiment_run", "experiment runtime wait in wrong stage"))
        payload = run_tick(project)
        require(payload["action"] in {"queued_repair_handoff", "repair_already_queued"}, f"wrong-stage experiment poll should become local routing: {payload}")
        statuses = [row["status"] for row in rows(base / "async_jobs.jsonl")]
        require("superseded" in statuses, f"wrong-stage experiment poll should be superseded, got {statuses}")


def test_blocker_triage_local_wait_not_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "review_pressure")
        cases = [
            "waiting for local review repair packet",
            "queued sub-agent reviewer pass needs parent dispatch",
            "writing lint wait for local artifact repair",
        ]
        for reason in cases:
            payload = run_json(
                [
                    "python",
                    str(TRIAGE),
                    "--project",
                    str(project),
                    "--stage",
                    "review_pressure",
                    "--reason",
                    reason,
                    "--dry-run",
                ]
            )
            require(payload["class"] != "async_wait", f"local wait text should not be async_wait: {payload}")


def test_blocker_triage_external_wait_still_async() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), "graph_build")
        cases = [
            "PaperNexus literature discovery run is pending report",
            "import_workflow graph import task is queued",
            "experiment runtime remote GPU training is running",
        ]
        for reason in cases:
            payload = run_json(
                [
                    "python",
                    str(TRIAGE),
                    "--project",
                    str(project),
                    "--stage",
                    "graph_build",
                    "--reason",
                    reason,
                    "--dry-run",
                ]
            )
            require(payload["class"] == "async_wait", f"external wait text should stay async_wait: {payload}")


def main() -> None:
    test_due_repair_preempts_due_async()
    test_active_discovery_dispatches_async()
    test_ready_discovery_supersedes_async()
    test_graph_import_complete_supersedes_async()
    test_active_graph_import_dispatches_async()
    test_active_experiment_dispatches_async()
    test_experiment_poll_wrong_stage_supersedes()
    test_blocker_triage_local_wait_not_async()
    test_blocker_triage_external_wait_still_async()


if __name__ == "__main__":
    main()
