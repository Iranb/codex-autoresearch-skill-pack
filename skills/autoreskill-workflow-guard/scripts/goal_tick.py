#!/usr/bin/env python3
"""Run one atomic /goal tick for portable AutoResearch projects."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from contract_lint import lint
from goal_state import NEXT_ACTIONS, OWNERS, STAGES, ar, load_state, next_stage, save_state


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")


def classify(reason: str) -> tuple[str, str]:
    text = reason.lower()
    if any(key in text for key in ["import", "queue", "running", "remote", "async", "wait"]):
        return "async_wait", "schedule_async_poll"
    if any(key in text for key in ["controller_unavailable", "single_seed", "cost_evidence", "provider", "sparse", "stale"]):
        return "degradable", "advance_with_downgrade_or_fallback"
    if any(key in text for key in ["budget", "license", "unsafe", "no_viable", "papernexus_unavailable_without_cached"]):
        return "hard_stop", "rollback_or_negative_result_route"
    return "auto_repairable", "schedule_repair"


def next_due_job(queue: list[dict[str, Any]]) -> dict[str, Any] | None:
    current = now()
    for row in queue:
        if row.get("status") not in {"pending", "retry"}:
            continue
        retry_at = str(row.get("next_retry_at") or row.get("next_poll_at") or "")
        if not retry_at:
            return row
        try:
            if datetime.fromisoformat(retry_at) <= current:
                return row
        except ValueError:
            return row
    return None


def mark_job_running(base: Path, queue_name: str, job: dict[str, Any]) -> None:
    path = base / queue_name
    data = rows(path)
    for row in data:
        if row.get("job_id") == job.get("job_id"):
            row["status"] = "running"
            row["attempts"] = int(row.get("attempts", 0)) + 1
            row["updated_at"] = iso(now())
    write_rows(path, data)


def job_contract(project: str, job: dict[str, Any]) -> dict[str, Any]:
    stage = str(job.get("stage", "init"))
    return lint(project, stage)


def queue_job(base: Path, kind: str, stage: str, action: str, reason: str, policy: dict[str, Any]) -> dict[str, Any]:
    queue_name = "async_jobs.jsonl" if kind == "async" else "repair_queue.jsonl"
    path = base / queue_name
    data = rows(path)
    for row in data:
        if (
            row.get("status") in {"pending", "retry", "running"}
            and row.get("stage") == stage
            and row.get("action") == action
            and row.get("reason") == reason
        ):
            existing = dict(row)
            existing["_reused"] = True
            return existing
    delay_key = "next_poll_at" if kind == "async" else "next_retry_at"
    row = {
        "schema_version": 1,
        "job_id": f"job_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "stage": stage,
        "action": action,
        "reason": reason,
        "status": "pending",
        "attempts": 0,
        "max_attempts": int(policy.get("max_repair_attempts_per_blocker", 3)),
        "created_at": iso(now()),
        delay_key: iso(now() + timedelta(minutes=5)),
        "fallback_action": "degrade_or_rollback",
    }
    data.append(row)
    write_rows(path, data)
    created = dict(row)
    created["_reused"] = False
    return created


def execution_spec(stage: str, state: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    corpus = (state.get("paperNexus") or {}).get("corpus")
    common = {
        "inputs": [
            ".autoreskill/goal_state.json",
            ".autoreskill/memory.md",
            ".autoreskill/evidence_cart.jsonl",
        ],
        "missing": contract.get("missing", []),
    }
    specs: dict[str, dict[str, Any]] = {
        "topic_search": {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Run bounded PaperNexus literature discovery for the research goal and capture discovery evidence.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "plan", "corpus": corpus}},
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus}},
            ],
            "capture": [
                "python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py --project <project-root> --kind literature_discovery_packet --input <mcp-result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note \"topic search evidence\" --tag topic_search"
            ],
            "outputs": [".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json"],
        },
        "graph_build": {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Probe PaperNexus corpus state and write a source-backed graph build decision.",
            "mcp_calls": [
                {"tool": "list_corpora", "args": {}},
                {"tool": "agent_materials", "args": {"operation": "source_discovery_plan", "corpus": corpus}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
            ],
            "capture": [
                "python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_probe_record.py --project <project-root> --callable true --corpus <corpus> --corpora-json <list-corpora-result.json>",
                "python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py --project <project-root> --kind source_discovery_plan --input <mcp-result.json> --stage graph_build --source papernexus-remote.agent_materials --tag graph",
                "python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py --project <project-root> --kind graph_build_decision --input <decision.json> --stage graph_build --source WorkflowGuard --status complete",
            ],
            "outputs": [".autoreskill/graph/GRAPH_BUILD_DECISION.json"],
        },
        "frontier_mapping": {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Build frontier, gap, source-transfer, and experiment norm materials from PaperNexus.",
            "mcp_calls": [
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
                {"tool": "agent_materials", "args": {"operation": "experiment_cost_materials", "corpus": corpus}},
                {"tool": "research_lookup", "args": {"operation": "interdisciplinary_potential", "corpus": corpus}},
            ],
            "capture": [
                "python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py --project <project-root> --kind research_material_pack --input <mcp-result.json> --stage frontier_mapping --source papernexus-remote.agent_materials --evidence-note \"frontier material evidence\" --tag frontier"
            ],
            "outputs": [".autoreskill/papernexus/research_material_pack.json"],
        },
        "ideation": {
            "skill": "autoreskill-ideation-panel",
            "role": "Researcher",
            "goal": "Use PaperNexus-backed evidence to generate and validate candidate ideas, including the 12-15 item experiment optimization idea pool, with negative evidence and falsifiers.",
            "mcp_calls": [
                {"tool": "agent_materials", "args": {"operation": "negative_evidence_pack", "corpus": corpus}},
                {"tool": "idea_catalyst", "args": {"mode": "hybrid", "outputMode": "packet_bundle", "corpus": corpus}},
            ],
            "capture": [
                "python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py --project <project-root> --kind negative_evidence_pack --input <mcp-result.json> --stage ideation --source papernexus-remote.agent_materials --tag ideation",
                "python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py --project <project-root> --kind graph_ideation_packet --input <mcp-result.json> --stage ideation --source papernexus-remote.idea_catalyst --tag ideation",
                "python ~/.codex/skills/autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json",
            ],
            "outputs": [
                ".autoreskill/ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
            ],
        },
        "literature_review": {
            "skill": "autoreskill-literature-review",
            "role": "Researcher",
            "goal": "Convert discovery and PaperNexus evidence into SOTA matrix, gap synthesis, and citation queue.",
            "mcp_calls": [
                {"tool": "research_briefing", "args": {"operation": "research_brief", "corpus": corpus}},
                {"tool": "research_briefing", "args": {"operation": "evidence_chain", "corpus": corpus}},
            ],
            "capture": [],
            "outputs": [
                ".autoreskill/literature/SOTA_MATRIX.md",
                ".autoreskill/literature/GAP_SYNTHESIS.md",
                ".autoreskill/literature/CITATION_QUEUE.json",
            ],
        },
        "idea_gate": {
            "skill": "autoreskill-ideation-panel",
            "role": "Reviewer",
            "goal": "Run Professor/Postdoc/PhDStudent/Critic gate, select one idea from the ideation-stage experiment idea pool, and select advance/park/kill tracks.",
            "mcp_calls": [],
            "capture": [
                "python ~/.codex/skills/autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json --require-selected"
            ],
            "outputs": [
                ".autoreskill/ideation/TOURNAMENT_SCOREBOARD.json",
                ".autoreskill/ideation/TOP3_DIRECTION_SUMMARY.md",
                ".autoreskill/reviewer/IDEA_GATE_REVIEW.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
            ],
        },
        "experiment_plan": {
            "skill": "autoreskill-experiment-plan",
            "role": "Orchestrator",
            "goal": "Materialize an INNOVATION_PACKET and reviewed experiment plan from the selected ideation-stage optimization idea.",
            "mcp_calls": [],
            "capture": [
                "python ~/.codex/skills/autoreskill-experiment-plan/scripts/prelaunch_lint.py --project <project-root>",
                "python ~/.codex/skills/autoreskill-experiment-plan/scripts/innovation_lint.py --project <project-root>",
            ],
            "outputs": [
                ".autoreskill/orchestrator/INNOVATION_PACKET.json",
                ".autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json",
            ],
        },
        "code": {
            "skill": "autoreskill-implement-experiment",
            "role": "Coder",
            "goal": "Implement the reviewed baseline/proposed experiment bundle and produce dry-run proof.",
            "mcp_calls": [],
            "capture": [],
            "outputs": [".autoreskill/coder/EXPERIMENT_INDEX.md", ".autoreskill/coder/experiments/"],
        },
        "experiment": {
            "skill": "autoreskill-run-experiment",
            "role": "Coder",
            "goal": "Launch or reconcile experiment runs without changing metric, dataset, or baseline protocol.",
            "mcp_calls": [],
            "capture": [],
            "outputs": [".autoreskill/coder/EXPERIMENT_LEDGER.json", ".autoreskill/coder/EXPERIMENT_INDEX.md"],
        },
        "analysis": {
            "skill": "autoreskill-analyze-results",
            "role": "Analyzer",
            "goal": "Convert experiment proof into claim-evidence matrix, verdicts, unsupported claims, and narrative report.",
            "mcp_calls": [],
            "capture": ["python ~/.codex/skills/autoreskill-analyze-results/scripts/analysis_lint.py --project <project-root>"],
            "outputs": [
                ".autoreskill/analyzer/CLAIM_EVIDENCE_MATRIX.md",
                ".autoreskill/analyzer/TRACK_VERDICTS.md",
            ],
        },
        "review_pressure": {
            "skill": "autoreskill-review-gate",
            "role": "Reviewer",
            "goal": "Run isolated review and close or downgrade blocking findings.",
            "mcp_calls": [],
            "capture": ["python ~/.codex/skills/autoreskill-review-gate/scripts/review_lint.py --project <project-root>"],
            "outputs": [".autoreskill/reviewer/REVIEW_FINDINGS.json"],
        },
        "writing": {
            "skill": "autoreskill-paper-write",
            "role": "Academic Writer",
            "goal": "Write evidence-bound manuscript material from approved claims, literature, and review guidance.",
            "mcp_calls": [],
            "capture": [],
            "outputs": [".autoreskill/paper/main.tex", ".autoreskill/paper/write_package.json"],
        },
        "submission_ready": {
            "skill": "autoreskill-review-gate",
            "role": "WorkflowGuard",
            "goal": "Verify final submission package, citation integrity, front matter, and target-venue readiness.",
            "mcp_calls": [],
            "capture": ["python ~/.codex/skills/autoreskill-review-gate/scripts/review_lint.py --project <project-root>"],
            "outputs": [
                ".autoreskill/paper/main.tex",
                ".autoreskill/paper/main.pdf",
                ".autoreskill/submission_ready.json",
            ],
        },
    }
    fallback_role = OWNERS.get(stage, "Researcher")
    spec = specs.get(
        stage,
        {
            "skill": f"autoreskill-{stage.replace('_', '-')}",
            "role": fallback_role,
            "goal": f"Satisfy the {stage} contract using the stage-specific autoreskill.",
            "mcp_calls": [],
            "capture": [],
            "outputs": contract.get("missing", []),
        },
    )
    spec.update(common)
    return spec


def write_job_packet(
    base: Path,
    state: dict[str, Any],
    job: dict[str, Any],
    contract: dict[str, Any],
    blocker: dict[str, Any] | None,
    queue_name: str,
) -> Path:
    stage = str(job.get("stage") or state.get("stage", "init"))
    spec = execution_spec(stage, state, contract)
    path = base / "job_packets" / f"{job['job_id']}.json"
    packet = {
        "schema_version": 1,
        "created_at": iso(now()),
        "job_id": job["job_id"],
        "job_kind": job.get("kind"),
        "queue": queue_name,
        "stage": stage,
        "status": "ready_for_execution",
        "skill": spec["skill"],
        "role": spec["role"],
        "goal": spec["goal"],
        "reason": job.get("reason"),
        "blocker": blocker,
        "inputs": spec["inputs"],
        "missing": spec["missing"],
        "mcp_calls": spec["mcp_calls"],
        "capture_commands": spec["capture"],
        "allowed_writes": stage_write_scopes(stage),
        "constraints": [
            "Use PaperNexus live graph work only through papernexus-remote MCP.",
            "Do not use local PaperNexus CLI, raw HTTP, local graph files, local MCP, or SSH graph commands as substitutes.",
            "Do not invent citations, evidence, or experiment results.",
            "After producing artifacts, rerun the relevant linter before marking this job complete.",
        ],
        "outputs": spec["outputs"],
        "acceptance_criteria": [
            "Required outputs exist under .autoreskill/",
            "contract_lint.py or the stage linter reports complete",
            "decision_log.jsonl records the produced artifact or explicit blocker",
        ],
    }
    write_json(path, packet)
    append_jsonl(
        base / "mailbox.jsonl",
        {
            "ts": iso(now()),
            "type": "job_packet",
            "job_id": job["job_id"],
            "stage": stage,
            "to": spec["role"],
            "skill": spec["skill"],
            "path": str(path),
        },
    )
    return path


def stage_write_scopes(stage: str) -> list[str]:
    common = [
        ".autoreskill/evidence_cart.jsonl",
        ".autoreskill/artifacts_index.json",
    ]
    scopes = {
        "init": [
            ".autoreskill/goal_state.json",
            ".autoreskill/autopilot_policy.json",
            ".autoreskill/capabilities.json",
            ".autoreskill/memory.md",
            ".autoreskill/decision_log.jsonl",
            ".autoreskill/repair_queue.jsonl",
            ".autoreskill/async_jobs.jsonl",
        ],
        "topic_search": [".autoreskill/literature/", ".autoreskill/papernexus/"],
        "graph_build": [".autoreskill/graph/", ".autoreskill/papernexus/"],
        "frontier_mapping": [".autoreskill/papernexus/", ".autoreskill/ideation/"],
        "literature_review": [".autoreskill/literature/"],
        "ideation": [".autoreskill/ideation/", ".autoreskill/papernexus/"],
        "idea_gate": [".autoreskill/ideation/", ".autoreskill/reviewer/"],
        "experiment_plan": [".autoreskill/orchestrator/", ".autoreskill/planner/"],
        "code": [".autoreskill/coder/"],
        "experiment": [".autoreskill/coder/"],
        "analysis": [".autoreskill/analyzer/"],
        "review_pressure": [".autoreskill/reviewer/"],
        "writing": [".autoreskill/paper/"],
        "submission_ready": [".autoreskill/paper/", ".autoreskill/submission_ready.json"],
    }
    stage_scopes = scopes.get(stage, [f".autoreskill/{stage}/"])
    return [*stage_scopes, *common]


def handoff_for_stage(base: Path, state: dict[str, Any], contract: dict[str, Any]) -> Path:
    stage = str(state.get("stage", "init"))
    owner = str(state.get("owner") or OWNERS.get(stage, "Researcher"))
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    path = base / "handoffs" / f"{stamp}__WorkflowGuard__to__{owner.replace(' ', '')}.json"
    packet = {
        "schema_version": 1,
        "created_at": iso(now()),
        "from": "WorkflowGuard",
        "to": owner,
        "stage": stage,
        "goal": f"Satisfy the {stage} contract without changing upstream evidence or protocol.",
        "inputs": [
            ".autoreskill/goal_state.json",
            ".autoreskill/memory.md",
            ".autoreskill/evidence_cart.jsonl",
        ],
        "missing": contract.get("missing", []),
        "allowed_writes": stage_write_scopes(stage),
        "constraints": [
            "Use PaperNexus live graph work only through papernexus-remote MCP.",
            "Do not invent citations, evidence, or experiment results.",
            "Write machine-readable artifacts when the stage contract defines them.",
        ],
        "outputs": contract.get("missing", []),
        "acceptance_criteria": [
            "contract_lint.py reports complete for the current stage",
            "decision_log.jsonl records the produced artifact or blocker",
        ],
    }
    write_json(path, packet)
    return path


def complete_current_stage(project: str, state: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    stage = str(state.get("stage", "init"))
    if stage == STAGES[-1]:
        state["next_action"] = "workflow_complete"
        state["blocking_reason"] = None
        save_state(project, state, "terminal_complete", {"contract": contract})
        return {"action": "terminal_complete", "stage": stage, "contract": contract}

    new_stage = next_stage(stage)
    state.update(
        {
            "stage": new_stage,
            "owner": OWNERS.get(new_stage, state.get("owner")),
            "next_action": NEXT_ACTIONS.get(new_stage),
            "blocking_reason": None,
        }
    )
    save_state(project, state, "advance_after_contract", {"from": stage, "to": new_stage, "contract": contract})
    return {"action": "advanced", "from": stage, "to": new_stage, "contract": contract}


def run_tick(args: argparse.Namespace) -> None:
    base = ar(args.project)
    state = load_state(args.project)
    policy = read_json(base / "autopilot_policy.json", {})
    repair_queue = rows(base / "repair_queue.jsonl")
    async_queue = rows(base / "async_jobs.jsonl")

    due_async = next_due_job(async_queue)
    if due_async:
        mark_job_running(base, "async_jobs.jsonl", due_async)
        packet = write_job_packet(base, state, due_async, job_contract(args.project, due_async), None, "async_jobs.jsonl")
        save_state(args.project, state, "dispatch_async_poll", {"job": due_async, "job_packet": str(packet)})
        print(json.dumps({"action": "dispatch_async_poll", "job": due_async, "job_packet": str(packet)}, indent=2, ensure_ascii=False))
        return

    due_repair = next_due_job(repair_queue)
    if due_repair:
        mark_job_running(base, "repair_queue.jsonl", due_repair)
        packet = write_job_packet(base, state, due_repair, job_contract(args.project, due_repair), None, "repair_queue.jsonl")
        save_state(args.project, state, "dispatch_repair", {"job": due_repair, "job_packet": str(packet)})
        print(json.dumps({"action": "dispatch_repair", "job": due_repair, "job_packet": str(packet)}, indent=2, ensure_ascii=False))
        return

    stage = str(state.get("stage", "init"))
    contract = lint(args.project, stage)
    if contract["complete"]:
        print(json.dumps(complete_current_stage(args.project, state, contract), indent=2, ensure_ascii=False))
        return

    reason = "; ".join(str(item) for item in contract.get("missing", [])) or f"{stage} contract incomplete"
    klass, recommended_action = classify(reason)
    blocker = {
        "schema_version": 1,
        "ts": iso(now()),
        "stage": stage,
        "reason": reason,
        "class": klass,
        "recommended_action": recommended_action,
        "contract": contract,
        "status": "triaged",
    }
    append_jsonl(base / "blocker_ledger.jsonl", blocker)

    if klass == "hard_stop":
        state["blocking_reason"] = reason
        state["next_action"] = recommended_action
        save_state(args.project, state, "hard_stop", blocker)
        print(json.dumps({"action": "hard_stop", "blocker": blocker}, indent=2, ensure_ascii=False))
        return

    if klass == "async_wait":
        job = queue_job(base, "async", stage, recommended_action, reason, policy)
        packet = None if job.get("_reused") else write_job_packet(base, state, job, contract, blocker, "async_jobs.jsonl")
        state["blocking_reason"] = reason
        state["next_action"] = recommended_action
        save_state(args.project, state, "queued_async_wait", {"blocker": blocker, "job": job, "job_packet": str(packet) if packet else None})
        print(
            json.dumps(
                {"action": "queued_async_wait", "blocker": blocker, "job": job, "job_packet": str(packet) if packet else None},
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    job = queue_job(base, "repair", stage, recommended_action, reason, policy)
    handoff = None if job.get("_reused") else handoff_for_stage(base, state, contract)
    packet = None if job.get("_reused") else write_job_packet(base, state, job, contract, blocker, "repair_queue.jsonl")
    action = "repair_already_queued" if job.get("_reused") else "queued_repair_handoff"
    state["blocking_reason"] = reason
    state["next_action"] = recommended_action
    save_state(
        args.project,
        state,
        action,
        {"blocker": blocker, "job": job, "handoff": str(handoff) if handoff else None, "job_packet": str(packet) if packet else None},
    )
    print(
        json.dumps(
            {
                "action": action,
                "blocker": blocker,
                "job": job,
                "handoff": str(handoff) if handoff else None,
                "job_packet": str(packet) if packet else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    run_tick(args)


if __name__ == "__main__":
    main()
