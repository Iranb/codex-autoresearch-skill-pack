#!/usr/bin/env python3
"""Regression checks for experiment next-action queue helper."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/experiment_next_actions.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def valid_row(row_id: str, priority: int, role: str = "single_innovation", status: str = "ready") -> dict[str, Any]:
    return {
        "id": row_id,
        "priority": priority,
        "status": status,
        "role": role,
        "dataset": "CUB",
        "variant": "fixture_variant",
        "selected_idea_id": "idea-a",
        "track_id": "track-main",
        "branch_id": "branch-main",
        "selection_fingerprint": "idea-a/track-main/v1",
        "launch_identity_hash": f"launch-{row_id}",
        "track_plan_ref": ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json:track-main",
        "causal_signature": "activate component | restore signal | improve target metric",
        "decision_class": "falsify_core_mechanism",
        "why_now": "This is the cheapest test that can falsify the primary mechanism.",
        "claim_target": "fixture claim row",
        "hypothesis_prediction": "The target metric improves without material regression.",
        "falsifier": "The matched intervention does not improve the target metric.",
        "outcome_routes": {
            "positive": "queue ablation or confirmation",
            "negative": "weaken or retire track",
            "inconclusive": "run one discriminator",
            "invalid": "repair protocol",
        },
        "expected_decision_change": "Retain or retire track-main.",
        "decision_target_refs": ["IDEA_DECISION_LEDGER.json:track-main"],
        "comparison_source": "vs matched reproduced baseline",
        "baseline_anchor": "fixture baseline",
        "protocol": "matched CUB split and evaluator",
        "metric_policy_ref": ".autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json:metric_policy",
        "launch_mode": "repeated_variant",
        "resource_request": {"backend": "local", "gpu_count": 1, "estimated_gpu_hours": 1.0},
        "mutex_group": "fixture-readonly-data",
        "parallel_safe": True,
        "owner_thread_id": "fixture-thread",
        "next_action": "Run the fixture experiment.",
        "blocker": "",
        "evidence_paths": [".autoreskill/experiment/FIXTURE.json"],
        "updated_at": now_iso(),
    }


def write_authorities(project: Path) -> None:
    write_json(
        project / ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json",
        {
            "schema_version": 2,
            "selection_fingerprint": "idea-a/track-main/v1",
            "tracks": [
                {
                    "idea_id": "idea-a",
                    "track_id": "track-main",
                    "branch_id": "branch-main",
                    "selection_fingerprint": "idea-a/track-main/v1",
                    "launch_status": "ready",
                    "hypothesis_contract": {
                        "causal_signature": "activate component | restore signal | improve target metric",
                        "belief_state": "active",
                    },
                }
            ],
        },
    )
    write_json(
        project / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
        {
            "selected_primary_idea_id": "idea-a",
            "selection_fingerprint": "idea-a/track-main/v1",
            "decisions": [
                {
                    "idea_id": "idea-a",
                    "track_id": "track-main",
                    "selection_fingerprint": "idea-a/track-main/v1",
                    "lifecycle_status": "selected_primary",
                }
            ],
        },
    )


def test_init_check_render(tmp: Path) -> None:
    project = tmp / "02-ContinueGCD"
    wiki_root = tmp / "wiki" / "mypaper"
    out = run_json(
        [
            "python",
            str(HELPER),
            "init",
            "--project",
            str(project),
            "--direction",
            "ContinueGCD",
            "--wiki-root",
            str(wiki_root),
        ]
    )
    require(out["ok"] is True, f"init should pass: {out}")
    queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
    config_path = project / ".autoreskill/experiment/EXPERIMENT_PLANNER_CONFIG.json"
    require(queue_path.exists(), "queue should exist")
    require(config_path.exists(), "config should exist")
    config = read_json(config_path)
    require(config["direction"] == "ContinueGCD", f"direction should be configured: {config}")
    require("ContinueGCD" in config["project_dashboard_path"], f"default wiki path should include direction: {config}")

    queue = read_json(queue_path)
    queue["rows"] = [valid_row("cub-single-fixture", 10)]
    queue["updated_at"] = now_iso()
    write_json(queue_path, queue)
    write_authorities(project)

    check = run_json(["python", str(HELPER), "check", "--project", str(project)])
    require(check["ok"] is True, f"valid queue should check: {check}")
    require(check["details"]["row_count"] == 1, f"row count mismatch: {check}")

    rendered = run_json(["python", str(HELPER), "render", "--project", str(project)])
    require(rendered["ok"] is True, f"render should pass: {rendered}")
    dashboard = Path(rendered["dashboard_path"])
    require(dashboard.exists(), "dashboard should exist")
    text = dashboard.read_text(encoding="utf-8")
    require("cub-single-fixture" in text, "dashboard should include row id")
    require("dashboard only" in text, "dashboard should state rendered-view boundary")


def test_invalid_status_fails(tmp: Path) -> None:
    project = tmp / "03-GCD"
    wiki_root = tmp / "wiki" / "mypaper"
    run_json(
        [
            "python",
            str(HELPER),
            "init",
            "--project",
            str(project),
            "--direction",
            "GCD",
            "--wiki-root",
            str(wiki_root),
        ]
    )
    queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
    queue = read_json(queue_path)
    bad = valid_row("bad-row", 10)
    bad["status"] = "done"
    queue["rows"] = [bad]
    write_json(queue_path, queue)
    payload = run_json(["python", str(HELPER), "check", "--project", str(project)], expect_code=1)
    require(payload["ok"] is False, f"invalid queue should fail: {payload}")
    require(any("invalid status" in item for item in payload["errors"]), f"missing invalid status error: {payload}")


def test_global_render(tmp: Path) -> None:
    wiki_root = tmp / "wiki" / "mypaper"
    projects: list[Path] = []
    for name, direction, row_id in [
        ("00-DomainGCD", "DomainGCD", "domain-row"),
        ("02-ContinueGCD", "ContinueGCD", "continue-row"),
    ]:
        project = tmp / name
        projects.append(project)
        run_json(
            [
                "python",
                str(HELPER),
                "init",
                "--project",
                str(project),
                "--direction",
                direction,
                "--wiki-root",
                str(wiki_root),
            ]
        )
        queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
        queue = read_json(queue_path)
        queue["rows"] = [valid_row(row_id, 20)]
        write_json(queue_path, queue)
        write_authorities(project)

    out_path = tmp / "global.md"
    cmd = ["python", str(HELPER), "render-global"]
    for project in projects:
        cmd.extend(["--project", str(project)])
    cmd.extend(["--out", str(out_path)])
    payload = run_json(cmd)
    require(payload["ok"] is True, f"global render should pass: {payload}")
    text = out_path.read_text(encoding="utf-8")
    require("domain-row" in text, "global dashboard should include DomainGCD row")
    require("continue-row" in text, "global dashboard should include ContinueGCD row")


def test_hard_launch_identity_and_atomic_claim(tmp: Path) -> None:
    project = tmp / "04-QueueLease"
    run_json(["python", str(HELPER), "init", "--project", str(project), "--wiki-root", str(tmp / "wiki")])
    queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
    queue = read_json(queue_path)
    candidate = {
        "id": "candidate-incomplete",
        "priority": 50,
        "status": "candidate",
        "role": "single_innovation",
        "dataset": "CUB",
        "next_action": "Finish scientific identity.",
        "updated_at": now_iso(),
    }
    row = valid_row("claim-once", 10)
    queue["rows"] = [candidate, row]
    write_json(queue_path, queue)
    write_authorities(project)
    checked = run_json(["python", str(HELPER), "check", "--project", str(project)])
    require(checked["ok"] is True, f"incomplete candidate must remain readable: {checked}")

    broken = dict(row)
    broken["id"] = "broken-ready"
    broken.pop("falsifier")
    queue["rows"] = [broken]
    write_json(queue_path, queue)
    failed = run_json(["python", str(HELPER), "check", "--project", str(project)], expect_code=1)
    require(any("falsifier" in item for item in failed["errors"]), f"missing hard identity error: {failed}")

    queue["rows"] = [row]
    write_json(queue_path, queue)
    command = [
        "python",
        str(HELPER),
        "claim",
        "--project",
        str(project),
        "--row-id",
        "claim-once",
        "--expected-revision",
        "0",
    ]
    first = subprocess.Popen(command + ["--owner", "worker-a"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    second = subprocess.Popen(command + ["--owner", "worker-b"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    first_out, first_err = first.communicate()
    second_out, second_err = second.communicate()
    require(not first_err and not second_err, f"claim stderr: {first_err} {second_err}")
    outcomes = [(first.returncode, json.loads(first_out)), (second.returncode, json.loads(second_out))]
    winners = [payload for code, payload in outcomes if code == 0]
    losers = [payload for code, payload in outcomes if code != 0]
    require(len(winners) == 1 and len(losers) == 1, f"one claim must win: {outcomes}")
    require(losers[0]["error"]["code"] in {"stale_plan", "lease_conflict"}, f"structured conflict required: {losers}")
    owner = str(winners[0]["lease_owner"])
    repeated = run_json(command + ["--owner", owner])
    require(repeated["idempotent"] is True, f"same owner claim must be idempotent: {repeated}")

    current = read_json(queue_path)
    released = run_json(
        [
            "python",
            str(HELPER),
            "release",
            "--project",
            str(project),
            "--row-id",
            "claim-once",
            "--owner",
            owner,
            "--expected-revision",
            str(current["queue_revision"]),
            "--reason",
            "fixture never launched backend work",
        ]
    )
    require(released["status"] == "ready", f"release should restore ready: {released}")


def initialized_project(tmp: Path, name: str) -> tuple[Path, Path, dict[str, Any]]:
    project = tmp / name
    run_json(["python", str(HELPER), "init", "--project", str(project), "--wiki-root", str(tmp / "wiki")])
    queue_path = project / ".autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json"
    queue = read_json(queue_path)
    write_authorities(project)
    return project, queue_path, queue


def pool(pool_id: str, backend: str = "local", slots: int = 1, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "pool_id": pool_id,
        "backend": backend,
        "status": "available",
        "launch_slots": slots,
        "free_vram_mb": 24000,
        "capabilities": ["single_gpu"],
        "checked_at": now_iso(),
    }
    payload.update(extra)
    return payload


def make_parallel(row_id: str, priority: int, decision_class: str = "falsify_core_mechanism") -> dict[str, Any]:
    row = valid_row(row_id, priority)
    row["mutex_group"] = f"mutex-{row_id}"
    row["decision_class"] = decision_class
    row["launch_identity_hash"] = f"launch-{row_id}"
    return row


def test_elastic_auto_sizing_and_determinism(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "05-Elastic")
    queue["resource_snapshot"] = {"pools": [pool("local-ten", slots=10)]}
    queue["rows"] = [make_parallel(f"row-{index:02d}", index) for index in range(10)]
    write_json(queue_path, queue)

    first = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    second = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(first["selected_count"] == 10, f"auto sizing should use all ten useful slots: {first}")
    require(first["selected_row_ids"] == second["selected_row_ids"], "same snapshot must schedule deterministically")
    require(first["limits"]["batch_cap"] == 16, f"new queue fail-safe should be 16: {first}")


def test_priority_diagnostics_and_no_work(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "06-Priority")
    queue["resource_snapshot"] = {"pools": [pool("local-two", slots=2)]}
    diagnostic = make_parallel("diagnostic", 1, "resource_fill_diagnostic")
    falsifier = make_parallel("falsifier", 100, "falsify_core_mechanism")
    competitor = make_parallel("competitor", 200, "resolve_competing_hypotheses")
    queue["rows"] = [diagnostic, falsifier, competitor]
    write_json(queue_path, queue)
    payload = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(payload["selected_row_ids"] == ["competitor", "falsifier"], f"diagnostic must not displace decision rows: {payload}")

    queue["rows"] = []
    write_json(queue_path, queue)
    empty = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(empty["selected_count"] == 0, f"idle GPUs with no useful rows must launch nothing: {empty}")
    require(empty["reason"] == "no_admissible_ready_rows", f"empty reason should be explicit: {empty}")


def test_acquisition_impact_cost_and_aggregate_fallback(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "07-Acquisition")
    queue["resource_snapshot"] = {"available_gpu_slots": 3}
    impact = make_parallel("impact-two", 100)
    impact["decision_target_refs"] = ["decision:a", "decision:b"]
    impact["resource_request"]["estimated_gpu_hours"] = 10
    cheap = make_parallel("cheap", 1)
    cheap["resource_request"]["estimated_gpu_hours"] = 0.1
    medium = make_parallel("medium", 100)
    medium["resource_request"]["estimated_gpu_hours"] = 1
    expensive = make_parallel("expensive", 0)
    expensive["resource_request"]["estimated_gpu_hours"] = 2
    queue["rows"] = [expensive, medium, cheap, impact]
    write_json(queue_path, queue)
    payload = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(
        payload["selected_row_ids"] == ["impact-two", "cheap", "medium"],
        f"ordering must be acquisition class, decision impact, cost, priority, id: {payload}",
    )
    require(payload["resource_snapshot"]["detailed_pools"] is False, f"aggregate snapshots must remain readable: {payload}")


def test_dependency_mutex_duplicate_and_lease_rejection(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "08-Guards")
    queue["resource_snapshot"] = {"pools": [pool("guard-pool", slots=5)]}
    running = make_parallel("running", 0)
    running.update(
        {
            "status": "running",
            "lease_owner": "worker-running",
            "lease_acquired_at": now_iso(),
            "lease_expires_at": "2099-01-01T00:00:00+00:00",
            "resource_allocation": {"backend": "local", "pool_id": "guard-pool", "gpu_count": 1},
        }
    )
    running["mutex_group"] = "active-mutex"

    eligible = make_parallel("eligible", 1)
    blocked_mutex = make_parallel("blocked-mutex", 2)
    blocked_mutex["mutex_group"] = "active-mutex"
    duplicate = make_parallel("duplicate", 3)
    duplicate["launch_identity_hash"] = running["launch_identity_hash"]
    source = {
        "id": "unfinished-source",
        "priority": 4,
        "status": "candidate",
        "role": "single_innovation",
        "dataset": "CUB",
        "next_action": "Finish source evidence.",
        "updated_at": now_iso(),
    }
    dependent = make_parallel("dependent", 5)
    dependent["depends_on_rows"] = ["unfinished-source"]
    leased = make_parallel("leased", 6)
    leased["lease_owner"] = "another-worker"
    queue["rows"] = [running, eligible, blocked_mutex, duplicate, source, dependent, leased]
    write_json(queue_path, queue)
    payload = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(payload["selected_row_ids"] == ["eligible"], f"only the unblocked row should schedule: {payload}")
    reasons = {item["row_id"]: item["reason"] for item in payload["rejected"]}
    require("mutex_group" in reasons.get("blocked-mutex", ""), f"active mutex must reject: {payload}")
    require(reasons.get("duplicate") == "duplicate_active_launch_identity", f"active duplicate must reject: {payload}")
    require("not terminal" in reasons.get("dependent", ""), f"unfinished dependency must reject: {payload}")
    require(reasons.get("leased") == "ready_row_has_lease", f"leased ready row must reject: {payload}")


def test_pool_pending_isolation_and_shared_limit(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "09-Pools")
    queue["resource_snapshot"] = {
        "pools": [
            pool("bjtu-a", backend="bjtu_hpc", status="pending", account_ref="account-a"),
            pool("bjtu-b", backend="bjtu_hpc", account_ref="account-b"),
            pool("ssh-c", backend="ssh", host_ref="host-c"),
        ]
    }
    row_a = make_parallel("row-a", 1)
    row_a["resource_request"].update({"backend": "bjtu_hpc", "account_ref": "account-a"})
    row_b = make_parallel("row-b", 2)
    row_b["resource_request"].update({"backend": "bjtu_hpc", "account_ref": "account-b"})
    row_c = make_parallel("row-c", 3)
    row_c["resource_request"].update({"backend": "ssh", "host_ref": "host-c"})
    queue["rows"] = [row_a, row_b, row_c]
    write_json(queue_path, queue)
    payload = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(payload["selected_row_ids"] == ["row-b", "row-c"], f"pending account A must not block B or SSH: {payload}")

    queue["resource_snapshot"]["pools"][0].update(
        {"status": "blocked_shared_limit", "shared_limit_ref": "qos-shared", "shared_limit_blocked": True}
    )
    queue["resource_snapshot"]["pools"][1]["shared_limit_ref"] = "qos-shared"
    write_json(queue_path, queue)
    shared = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(shared["selected_row_ids"] == ["row-c"], f"explicit shared limit should block only its group: {shared}")


def test_resource_fit_and_inflight_budgets(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "10-Budgets")
    queue["policy"]["max_gpu_slots_in_flight"] = 4
    queue["policy"]["max_gpu_hours_in_flight"] = 8
    queue["resource_snapshot"] = {
        "pools": [
            pool("small", slots=1, free_vram_mb=12000),
            pool("large", slots=4, free_vram_mb=48000, capabilities=["single_gpu", "multi_gpu_same_node"]),
        ]
    }
    running = make_parallel("already-running", 0)
    running.update(
        {
            "status": "running",
            "lease_owner": "worker-running",
            "lease_acquired_at": now_iso(),
            "lease_expires_at": "2099-01-01T00:00:00+00:00",
            "resource_allocation": {"backend": "local", "pool_id": "small", "gpu_count": 1},
        }
    )
    running["resource_request"]["estimated_gpu_hours"] = 2
    two_gpu = make_parallel("two-gpu", 1)
    two_gpu["resource_request"].update(
        {"gpu_count": 2, "min_vram_mb": 32000, "required_capabilities": ["multi_gpu_same_node"], "estimated_gpu_hours": 4}
    )
    another_two = make_parallel("another-two", 2)
    another_two["resource_request"].update(
        {"gpu_count": 2, "min_vram_mb": 32000, "required_capabilities": ["multi_gpu_same_node"], "estimated_gpu_hours": 4}
    )
    queue["rows"] = [running, two_gpu, another_two]
    write_json(queue_path, queue)
    payload = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(payload["selected_row_ids"] == ["two-gpu"], f"remaining slot/hour budget should admit only one 2-GPU row: {payload}")
    require(payload["assignments"][0]["pool_id"] == "large", f"VRAM/capability fit should choose large pool: {payload}")


def test_scarce_pool_preservation_and_integer_validation(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "11-ScarcePool")
    queue["resource_snapshot"] = {
        "pools": [
            pool("a-special", slots=1),
            pool("z-general", slots=1),
        ]
    }
    flexible = make_parallel("flexible", 1)
    constrained = make_parallel("constrained", 2)
    constrained["resource_request"]["pool_id"] = "a-special"
    queue["rows"] = [flexible, constrained]
    write_json(queue_path, queue)
    scheduled = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    assignments = {item["row_id"]: item["pool_id"] for item in scheduled["assignments"]}
    require(
        assignments == {"flexible": "z-general", "constrained": "a-special"},
        f"flexible work must preserve the constrained row's only compatible pool: {scheduled}",
    )

    queue["resource_snapshot"]["pools"] = [
        pool("zero-is-authoritative", slots=0, available_gpu_slots=3)
    ]
    queue["rows"] = [flexible]
    write_json(queue_path, queue)
    zero = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(zero["selected_count"] == 0, f"explicit zero launch_slots must not fall through to another field: {zero}")

    queue["resource_snapshot"]["pools"][0]["launch_slots"] = 1.5
    write_json(queue_path, queue)
    fractional_slots = run_json(
        ["python", str(HELPER), "check", "--project", str(project)],
        expect_code=1,
    )
    require(
        any("launch_slots must be a nonnegative integer" in item for item in fractional_slots["errors"]),
        f"fractional pool capacity must fail validation: {fractional_slots}",
    )

    queue["resource_snapshot"]["pools"][0]["launch_slots"] = 1
    queue["policy"]["max_new_launches_per_cycle"] = 1.5
    write_json(queue_path, queue)
    fractional_cap = run_json(
        ["python", str(HELPER), "check", "--project", str(project)],
        expect_code=1,
    )
    require(
        any("max_new_launches_per_cycle" in item for item in fractional_cap["errors"]),
        f"fractional launch caps must fail validation: {fractional_cap}",
    )

    queue["policy"]["max_new_launches_per_cycle"] = "auto"
    queue["policy"]["max_gpu_slots_in_flight"] = 1.5
    write_json(queue_path, queue)
    fractional_inflight = run_json(
        ["python", str(HELPER), "check", "--project", str(project)],
        expect_code=1,
    )
    require(
        any("max_gpu_slots_in_flight" in item for item in fractional_inflight["errors"]),
        f"fractional in-flight GPU slots must fail instead of disabling the budget: {fractional_inflight}",
    )


def test_replication_seed_cap_and_snapshot_refresh(tmp: Path) -> None:
    project, queue_path, queue = initialized_project(tmp, "12-Seeds")
    rows = []
    for seed in (1, 2, 3):
        row = make_parallel(f"seed-{seed}", seed, "close_required_claim")
        row.update(
            {
                "experiment_family_id": "family-a",
                "replication_group_id": "replication-a",
                "random_seed": seed,
                "evidence_tier": "claim_eligible",
                "baseline_freeze_ref": "EXPERIMENT_REVIEW_PACKET.json:baseline_freeze",
            }
        )
        rows.append(row)
    queue["resource_snapshot"] = {"pools": [pool("seed-pool", slots=3)]}
    queue["rows"] = rows
    write_json(queue_path, queue)
    payload = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(payload["selected_count"] == 3, f"three final seeds should schedule concurrently: {payload}")

    fourth = make_parallel("seed-4", 4, "close_required_claim")
    fourth.update(
        {
            "experiment_family_id": "family-a",
            "replication_group_id": "replication-a",
            "random_seed": 4,
            "evidence_tier": "claim_eligible",
            "baseline_freeze_ref": "EXPERIMENT_REVIEW_PACKET.json:baseline_freeze",
        }
    )
    queue["rows"] = rows + [fourth]
    write_json(queue_path, queue)
    rejected = run_json(["python", str(HELPER), "schedule", "--project", str(project)], expect_code=1)
    require(any("hard maximum of 3" in item for item in rejected["errors"]), f"fourth unique seed must hard fail: {rejected}")

    queue["rows"] = rows
    queue.pop("resource_snapshot")
    write_json(queue_path, queue)
    refresh = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(refresh["selected_count"] == 0 and refresh["requires_resource_refresh"] is True, f"missing snapshot must request refresh, not authorize launch: {refresh}")

    queue["resource_snapshot"] = {"status": "stale", "pools": [pool("stale-pool", slots=3)]}
    write_json(queue_path, queue)
    stale = run_json(["python", str(HELPER), "schedule", "--project", str(project)])
    require(
        stale["selected_count"] == 0
        and stale["requires_resource_refresh"] is True
        and stale["reason"] == "resource_snapshot_stale",
        f"explicit stale snapshots must trigger refresh instead of heartbeat or launch: {stale}",
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        test_init_check_render(tmp)
        test_invalid_status_fails(tmp)
        test_global_render(tmp)
        test_hard_launch_identity_and_atomic_claim(tmp)
        test_elastic_auto_sizing_and_determinism(tmp)
        test_priority_diagnostics_and_no_work(tmp)
        test_acquisition_impact_cost_and_aggregate_fallback(tmp)
        test_dependency_mutex_duplicate_and_lease_rejection(tmp)
        test_pool_pending_isolation_and_shared_limit(tmp)
        test_resource_fit_and_inflight_budgets(tmp)
        test_scarce_pool_preservation_and_integer_validation(tmp)
        test_replication_seed_cap_and_snapshot_refresh(tmp)
    print("PASS experiment_next_actions fixtures")


if __name__ == "__main__":
    main()
