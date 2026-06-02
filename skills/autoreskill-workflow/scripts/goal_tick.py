#!/usr/bin/env python3
"""Run one atomic /goal tick for portable AutoResearch projects."""

from __future__ import annotations

import argparse
import json
import shlex
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from contract_lint import lint
from goal_state import NEXT_ACTIONS, OWNERS, STAGES, ar, load_state, next_stage, save_state


SKILLS_ROOT = Path(__file__).resolve().parents[2]
INNOVATION_STORY_STAGES = {"ideation", "idea_gate", "experiment_plan", "analysis", "review_pressure", "writing", "submission_ready"}
INNOVATION_STORY_FILES = [
    ".autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md",
    ".autoreskill/user_view/innovation_story/01_METHOD_INNOVATION_STORY.md",
    ".autoreskill/user_view/innovation_story/02_CLAIM_EVIDENCE_MAP.md",
]


def script_cmd(skill: str, script: str, args: str = "") -> str:
    script_path = SKILLS_ROOT / skill / "scripts" / script
    cmd = f"python {shlex.quote(str(script_path))}"
    if args:
        cmd = f"{cmd} {args}"
    return cmd


def has_literature_search(calls: list[Any]) -> bool:
    for call in calls:
        if not isinstance(call, dict) or call.get("tool") != "literature_discovery":
            continue
        args = call.get("args")
        if isinstance(args, dict) and args.get("operation") == "search":
            return True
    return False


def append_unique(items: list[str], additions: list[str]) -> list[str]:
    out = list(items)
    for item in additions:
        if item not in out:
            out.append(item)
    return out


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


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


def bounded_minutes(value: Any, default: int, *, minimum: int = 1, maximum: int = 24 * 60) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def poll_delay_minutes(policy: dict[str, Any], kind: str) -> int:
    if kind == "async":
        return bounded_minutes(policy.get("async_poll_interval_minutes"), 5)
    return bounded_minutes(policy.get("repair_retry_interval_minutes"), 5)


def unwrap_capture(payload: Any) -> Any:
    if isinstance(payload, dict) and "payload" in payload:
        return payload["payload"]
    return payload


def nested_get(payload: Any, path: list[str]) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def discovery_run_id(base: Path) -> str | None:
    payload = unwrap_capture(read_json(base / "literature/LITERATURE_DISCOVERY_RUN.json", {}))
    for path in [
        ["runId"],
        ["current", "runId"],
        ["progress", "runId"],
        ["next", "progress", "runId"],
    ]:
        value = nested_get(payload, path)
        if value:
            return str(value)
    return None


def discovery_report_ready(base: Path) -> bool:
    payload = unwrap_capture(read_json(base / "literature/LITERATURE_DISCOVERY_RUN.json", {}))
    for path in [["current", "reportAvailable"], ["reportAvailable"]]:
        if nested_get(payload, path) is True:
            return True
    for path in [["current", "isTerminal"], ["progress", "isTerminal"], ["isTerminal"]]:
        if nested_get(payload, path) is True:
            return True
    status = str(nested_get(payload, ["current", "status"]) or nested_get(payload, ["progress", "status"]) or nested_get(payload, ["status"]) or "").lower()
    stage = str(nested_get(payload, ["current", "stage"]) or nested_get(payload, ["progress", "stage"]) or nested_get(payload, ["stage"]) or "").lower()
    return status in {"completed", "complete", "succeeded", "success", "failed", "error"} or stage in {"completed", "complete", "report_ready"}


def classify_topic_search(base: Path) -> tuple[str, str]:
    has_run = nonempty(base / "literature/LITERATURE_DISCOVERY_RUN.json")
    has_packet = nonempty(base / "literature/LITERATURE_DISCOVERY_PACKET.json")
    if not has_run and not has_packet:
        return "auto_repairable", "submit_literature_discovery"
    if has_run and not has_packet and not discovery_report_ready(base):
        return "async_wait", "poll_literature_discovery"
    if has_run and not has_packet:
        return "auto_repairable", "capture_literature_discovery_report"
    return "auto_repairable", "screen_literature_discovery"


def classify(stage: str, reason: str, base: Path) -> tuple[str, str]:
    if stage == "topic_search":
        return classify_topic_search(base)
    text = reason.lower()
    if stage == "graph_build":
        if "queued/running" in text or "authoritative graph sync not complete" in text:
            return "async_wait", "poll_graph_import_sync"
        if "taskids/relevanttaskids" in text or "task rows or explicit graph_visible" in text:
            return "auto_repairable", "submit_graph_import_tasks"
        if "graph_build_decision" in text:
            return "auto_repairable", "write_graph_build_decision"
    if stage == "literature_review":
        if any(name in text for name in ["sota_matrix", "gap_synthesis", "citation_queue"]):
            return "auto_repairable", "write_literature_review"
    if stage in {"ideation", "idea_gate", "experiment_plan"}:
        local_queue_artifact = any(name in text for name in ["citation_queue", "idea_track_seeds", "experiment_idea_pool"])
        if local_queue_artifact and not any(name in text for name in ["import_workflow", "remote", "async", "authoritative", "sync"]):
            return "auto_repairable", "schedule_repair"
    if stage == "experiment" and ("promoted best_run" in text or "ready_for_analysis" in text):
        negative_blocker = read_json(base / "coder/EXPERIMENT_NEGATIVE_BLOCKER.json", {})
        status = str(negative_blocker.get("status") or "").strip().lower() if isinstance(negative_blocker, dict) else ""
        if status in {"blocked_without_promoted_evidence", "no_promoted_evidence", "negative_result_route"}:
            return "hard_stop", "rollback_or_negative_result_route"
    if any(key in text for key in ["import", "import_workflow", "queue", "queued", "running", "remote", "async", "wait", "authoritative", "sync"]):
        return "async_wait", "schedule_async_poll"
    if any(key in text for key in ["controller_unavailable", "single_seed", "cost_evidence", "provider", "sparse", "stale"]):
        return "degradable", "advance_with_downgrade_or_fallback"
    if any(key in text for key in ["budget", "license", "unsafe", "no_viable", "papernexus_unavailable_without_cached"]):
        return "hard_stop", "rollback_or_negative_result_route"
    return "auto_repairable", "schedule_repair"


def next_due_job(queue: list[dict[str, Any]], *, include_running: bool = False) -> dict[str, Any] | None:
    current = now()
    eligible_statuses = {"pending", "retry"}
    if include_running:
        eligible_statuses.add("running")
    for row in queue:
        if row.get("status") not in eligible_statuses:
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
    delay_minutes = poll_delay_minutes(policy, kind)
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
        delay_key: iso(now() + timedelta(minutes=delay_minutes)),
        "fallback_action": "degrade_or_rollback",
    }
    if kind == "async":
        row["poll_interval_minutes"] = delay_minutes
    else:
        row["retry_interval_minutes"] = delay_minutes
    data.append(row)
    write_rows(path, data)
    created = dict(row)
    created["_reused"] = False
    return created


def minutes_until(value: str, fallback: int) -> int:
    try:
        due_at = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback
    seconds = max(60, int((due_at - now()).total_seconds()))
    return max(1, (seconds + 59) // 60)


def async_wakeup_recommendation(project: str, job: dict[str, Any], reason: str) -> dict[str, Any]:
    due_at = str(job.get("next_poll_at") or "")
    interval_minutes = bounded_minutes(job.get("poll_interval_minutes"), 5)
    resume_minutes = minutes_until(due_at, interval_minutes)
    stage = str(job.get("stage") or "current")
    job_id = str(job.get("job_id") or "")
    prompt = (
        "Resume AutoResearch async polling for project "
        f"{project}. Run goal.py status, goal.py reconcile --stale-minutes 60, then goal.py tick. "
        "If tick dispatches this async poll job, execute the rendered packet through the named child skill, "
        "capture PaperNexus progress/report artifacts, update the job, and run one follow-up tick. "
        "If PaperNexus discovery/import is still running, do not sleep in-thread; record the status and create the next heartbeat from the new tick output. "
        f"Target job_id={job_id}, stage={stage}, due_at={due_at}, blocker={reason}"
    )
    return {
        "recommended": True,
        "tool": "codex_app.automation_update",
        "kind": "heartbeat",
        "destination": "thread",
        "interval_minutes": resume_minutes,
        "name": f"AutoResearch async poll: {stage}",
        "prompt": prompt,
        "job_id": job_id,
        "stage": stage,
        "due_at": due_at,
    }


def continuation_wakeup_recommendation(project: str, from_stage: str, to_stage: str) -> dict[str, Any]:
    prompt = (
        "Continue AutoResearch full_auto_bounded workflow for project "
        f"{project}. Run goal.py status, goal.py reconcile --stale-minutes 60, then goal.py tick. "
        "If tick returns a ready repair or async job, dispatch it through the named child skill, "
        "write the required artifacts, update the job, and run one follow-up tick. "
        "If tick returns queued_async_wait, create or update the async heartbeat from its wakeup recommendation. "
        "Do not sleep in-thread and do not treat raw literature discovery rows as graph-grounded evidence. "
        f"Continuation target: advanced from {from_stage} to {to_stage}."
    )
    return {
        "recommended": True,
        "tool": "codex_app.automation_update",
        "kind": "heartbeat",
        "destination": "thread",
        "interval_minutes": 1,
        "name": f"AutoResearch continuation: {to_stage}",
        "prompt": prompt,
        "stage": to_stage,
        "from_stage": from_stage,
    }


def execution_spec(stage: str, state: dict[str, Any], contract: dict[str, Any], job: dict[str, Any] | None = None, base: Path | None = None) -> dict[str, Any]:
    corpus = (state.get("paperNexus") or {}).get("corpus")
    goal_topic = state.get("goal") or state.get("objective") or ""
    job_action = str((job or {}).get("action") or "")
    run_id = discovery_run_id(base) if base is not None else None
    broad_metadata_discovery = {
        "depth": "deep",
        "searchMode": "deep",
        "planningMode": "llm_augmented",
        "llmQueryPlanner": True,
        "citationExpansion": True,
        "openAlexRelatedExpansion": True,
        "maxCandidates": 10000,
        "maxQueries": 48,
        "maxQueriesPerProvider": 8,
        "maxResultsPerQuery": 150,
        "maxLlmQueries": 16,
        "maxCitationSeeds": 24,
        "maxCitationsPerSeed": 50,
        "maxRelatedPerSeed": 50,
        "maxEntityQueries": 48,
        "maxExtractedEntities": 160,
        "maxSeedEntities": 100,
        "maxSeedPapers": 50,
        "maxSeedQueries": 40,
        "papersCoolMaxQueries": 48,
        "pasaMaxQueries": 20,
        "providerConcurrency": 4,
        "retryCount": 5,
        "timeoutMs": 300000,
        "searchBudgetMs": 300000,
        "preferMarkdown": True,
        "generateArxivMarkdownSources": True,
        "allowDownloads": False,
        "importBatchEnabled": True,
        "importBatchInitialTasks": 4,
        "importBatchMaxTasks": 16,
        "importBatchProgressive": True,
        "importResolved": False,
        "processImports": False,
        "returnPartial": True,
        "persist": True,
    }
    lane_topics = {
        "target_domain": (
            f"{goal_topic}\n\n"
            "Search lane: target_domain. Focus on closest priors, SOTA methods already present in the current field, "
            "baselines, datasets, metrics, protocols, limitations, future work, negative evidence, and reviewer overlap risk."
        ),
        "near_neighbor": (
            f"{goal_topic}\n\n"
            "Search lane: near_neighbor. Focus on adjacent tasks with similar evaluation pressure "
            "but different mechanisms, assumptions, optimization routes, or continual/open-world settings that could become the primary method source."
        ),
        "far_neighbor": (
            f"{goal_topic}\n\n"
            "Search lane: far_neighbor. Focus on transferable mechanisms from domain-agnostic challenges "
            "such as identity preservation, non-stationarity, streaming discovery, memory, novelty calibration, "
            "and duplicate prevention that could become the primary method source or story bridge."
        ),
    }
    common = {
        "inputs": [
            ".autoreskill/goal_state.json",
            ".autoreskill/memory.md",
            ".autoreskill/evidence_cart.jsonl",
        ],
        "missing": contract.get("missing", []),
    }
    topic_search_spec = {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Submit broad PaperNexus literature discovery for the research goal and capture the server-side run id before waiting.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "plan", "corpus": corpus}},
                {"tool": "literature_discovery", "args": {"operation": "submit", "corpus": corpus, "topic": goal_topic, **broad_metadata_discovery}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_run --input <mcp-submit-result.json> --stage topic_search --source papernexus-remote.literature_discovery --status submitted --evidence-note \"topic search broad discovery submitted\" --tag topic_search --tag literature_discovery --tag async_submit",
                )
            ],
            "outputs": [".autoreskill/literature/LITERATURE_DISCOVERY_RUN.json"],
        }
    if job_action in {"poll_literature_discovery", "schedule_async_poll"} and run_id:
        topic_search_spec = {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Poll the submitted PaperNexus literature discovery run; when the report is available, capture it and screen candidates.",
            "mcp_calls": [
                {"tool": "literature_discovery_progress", "args": {"corpus": corpus, "runId": run_id, "pollIntervalMinutes": 5, "staleAfterMinutes": 10}},
                {"tool": "literature_discovery", "args": {"operation": "report", "corpus": corpus, "runId": run_id}},
                {"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 20}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_run --input <progress-result.json> --stage topic_search --source papernexus-remote.literature_discovery_progress --status running --evidence-note \"topic search discovery progress\" --tag topic_search --tag literature_discovery --tag async_progress",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_packet --input <report-result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note \"topic search broad discovery report\" --tag topic_search --tag literature_discovery",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    "--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage topic_search",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind import_workflow_status --input <import-workflow-queue-result.json> --stage topic_search --source papernexus-remote.import_workflow --tag topic_search --tag import_workflow",
                ),
            ],
            "outputs": [
                ".autoreskill/literature/LITERATURE_DISCOVERY_RUN.json",
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
                ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json",
            ],
        }
    elif job_action in {"capture_literature_discovery_report", "screen_literature_discovery"}:
        report_call = {"tool": "literature_discovery", "args": {"operation": "report", "corpus": corpus, "runId": run_id or "<runId from .autoreskill/literature/LITERATURE_DISCOVERY_RUN.json>"}}
        topic_search_spec = {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Capture the completed PaperNexus discovery report if needed, then screen candidates into a scorecard and graph import plan.",
            "mcp_calls": [] if job_action == "screen_literature_discovery" else [report_call],
            "capture": [
                *(
                    [
                        script_cmd(
                            "autoreskill-papernexus-innovation",
                            "papernexus_artifact_capture.py",
                            "--project <project-root> --kind literature_discovery_packet --input <report-result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note \"topic search broad discovery report\" --tag topic_search --tag literature_discovery",
                        )
                    ]
                    if job_action == "capture_literature_discovery_report"
                    else []
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    "--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage topic_search",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "paper_selection_scorecard_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "graph_import_plan_lint.py",
                    "--project <project-root>",
                ),
            ],
            "outputs": [
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
            ],
        }

    specs: dict[str, dict[str, Any]] = {
        "topic_search": topic_search_spec,
        "graph_build": {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Submit or poll PaperNexus import/material tasks for selected graph import plan papers, then write a source-backed graph build decision only after selected evidence is graph-visible or explicitly routed to split-reading/material evidence.",
            "mcp_calls": [
                {"tool": "list_corpora", "args": {}},
                {"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 20}},
                {
                    "tool": "import_workflow",
                    "args": {
                        "operation": "submit",
                        "corpus": corpus,
                        "identifiers": "<repeat for each GRAPH_IMPORT_PLAN selected_papers import_action=import/supplement with DOI/arxivId/PMID/PMCID/ISBN/ISSN; capture returned taskIds>",
                        "trigger": "graph_build_selected_import_plan",
                    },
                },
                {"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 50}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_probe_record.py",
                    "--project <project-root> --callable true --corpus <corpus> --corpora-json <list-corpora-result.json>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind import_workflow_status --input <import-workflow-result.json> --stage graph_build --source papernexus-remote.import_workflow --tag graph --tag import_workflow",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind graph_build_decision --input <decision.json> --stage graph_build --source WorkflowGuard --status complete",
                ),
            ],
            "outputs": [".autoreskill/graph/GRAPH_BUILD_DECISION.json", ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json"],
        },
        "frontier_mapping": {
            "skill": "autoreskill-papernexus-innovation",
            "role": "Researcher",
            "goal": "Build frontier, gap, source-transfer, negative-evidence, and experiment norm materials from PaperNexus; trigger follow-up literature discovery when material packs leave missing gap/limitation/transfer roles.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: frontier mapping, limitations, failure modes, negative evidence, transfer sources, and experiment norms.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
                {"tool": "agent_materials", "args": {"operation": "experiment_cost_materials", "corpus": corpus}},
                {"tool": "research_lookup", "args": {"operation": "interdisciplinary_potential", "corpus": corpus}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind research_material_pack --input <mcp-result.json> --stage frontier_mapping --source papernexus-remote.agent_materials --evidence-note \"frontier material evidence\" --tag frontier",
                )
            ],
            "outputs": [".autoreskill/papernexus/research_material_pack.json"],
        },
        "ideation": {
            "skill": "autoreskill-ideation-panel",
            "role": "Researcher",
            "goal": "Generate a broad 12-15 item academic-paper-oriented experiment idea pool only after the pre-idea evidence gate passes. Trigger target-domain, near-neighbor, and far-neighbor discovery through papernexus-remote; use target-domain evidence to anchor problem/baseline/protocol and overlap risk, and use near/far-neighbor or cross-lane transfer as the preferred primary method source for top-tier ideas. Actively screen raw discovery; satisfy the venue-agnostic breadth lint, not just one attempt per lane; submit import/supplement work for roughly 60-80% of the high-signal eligible set through PaperNexus import_workflow with progressive batching, wait for completed task/stage plus authoritative sync before graph-grounded use, and split-read/materialize the selected evidence roles; build INNOVATION_SLOT_MAP.json; write PRE_IDEA_EVIDENCE_GATE.json status=passed; then generate ideas tied to innovation_slot_refs. Every paper idea must include at least three mutually necessary innovation points covering problem/protocol/evaluation, method/mechanism, and training/integration/analysis/validation, plus a coherent paper storyline; score every idea against target/near/far evidence before idea_gate selection.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": lane_topics["target_domain"], **broad_metadata_discovery}},
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": lane_topics["near_neighbor"], **broad_metadata_discovery}},
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": lane_topics["far_neighbor"], **broad_metadata_discovery}},
            ],
            "capture": [
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "pre_idea_discovery_plan.py",
                    "--project <project-root> --topic \"<topic>\" --target-domain \"<target-domain>\"",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    "--project <project-root> --kind literature_discovery_packet --input <mcp-result.json> --stage ideation --source papernexus-remote.literature_discovery --evidence-note \"Ideation broad metadata-only literature discovery\" --tag ideation --tag literature_discovery",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    "--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage ideation",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "pre_idea_discovery_config_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "paper_selection_scorecard_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "pre_idea_breadth_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "graph_import_plan_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "import_workflow_status_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "split_reading_evidence_pack_lint.py",
                    "--project <project-root>",
                ),
                script_cmd(
                    "autoreskill-ideation-panel",
                    "pre_idea_evidence_gate_lint.py",
                    "--project <project-root> --write-gate",
                ),
                script_cmd(
                    "autoreskill-experiment-plan",
                    "idea_pool_lint.py",
                    "--project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json",
                ),
                script_cmd("autoreskill-ideation-panel", "idea_scorecard_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage ideation"),
            ],
            "outputs": [
                ".autoreskill/literature/PRE_IDEA_DISCOVERY_PLAN.json",
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/literature/TARGET_DOMAIN_DISCOVERY_PACKET.json",
                ".autoreskill/literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
                ".autoreskill/literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_STATUS.json",
                ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json",
                ".autoreskill/papernexus/SPLIT_READING_EVIDENCE_PACK.json",
                ".autoreskill/ideation/INNOVATION_SLOT_MAP.json",
                ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.md",
                ".autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md",
            ],
        },
        "literature_review": {
            "skill": "autoreskill-literature-review",
            "role": "Researcher",
            "goal": "Convert discovery and PaperNexus evidence into SOTA matrix, gap synthesis, and citation queue. If SOTA, baseline, dataset, metric, venue, or citation coverage is thin, trigger targeted PaperNexus literature discovery before declaring the review complete.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: SOTA matrix, related work, baseline/dataset/metric anchors, target-venue context, and citation queue closure.", **broad_metadata_discovery}},
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
            "goal": "Run Professor/Postdoc/PhDStudent/Critic gate after the post-idea novelty and venue scorecard exists, select one idea from the ideation-stage experiment idea pool, and assign every idea a lifecycle decision. Write IDEA_DECISION_LEDGER.json so selected, alternate, risk-repair, repair_needed, parked, killed, and degraded speculative ideas all have decision reasons, failure classes, claim scopes, and reentry conditions. Reject or repair ideas whose three-or-more innovation bundle does not form one paper storyline, even if one module looks promising. Trigger targeted PaperNexus discovery if top ideas still lack closest-prior comparison, overlap-risk closure, negative evidence, or a credible near/far-neighbor transfer bridge.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: selected/top idea novelty gate, closest priors, overlap risk, negative evidence, and transfer-bridge validation.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-ideation-panel", "idea_scorecard_lint.py", "--project <project-root>"),
                script_cmd(
                    "autoreskill-experiment-plan",
                    "idea_pool_lint.py",
                    "--project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json --require-selected",
                ),
                script_cmd("autoreskill-ideation-panel", "idea_track_seeds.py", "--project <project-root> --check"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage idea_gate"),
            ],
            "outputs": [
                ".autoreskill/ideation/TOURNAMENT_SCOREBOARD.json",
                ".autoreskill/ideation/TOP3_DIRECTION_SUMMARY.md",
                ".autoreskill/reviewer/IDEA_GATE_REVIEW.json",
                ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
                ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
                ".autoreskill/ideation/IDEA_DECISION_LEDGER_AUDIT.json",
                ".autoreskill/ideation/IDEA_TRACK_SEEDS.json",
                ".autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md",
            ],
        },
        "experiment_plan": {
            "skill": "autoreskill-experiment-plan",
            "role": "Orchestrator",
            "goal": "Materialize an INNOVATION_PACKET, TRACK_PLAN_MATRIX, and reviewed experiment plan from the selected ideation-stage optimization idea while preserving its three-or-more paper innovation bundle and complete storyline. Consume IDEA_DECISION_LEDGER.json and IDEA_TRACK_SEEDS.json so primary, alternate, and risk-repair tracks carry lifecycle refs, launch status, and bounded B/I/E search settings: B=branch budget, I=search iterations, E=versions per branch under the locked protocol. Before launch, trigger targeted PaperNexus discovery/material closure for selected-idea novelty, current-field overlap risk, baseline/protocol/metric norms, negative evidence, and target-domain absence evidence when required.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: selected idea experiment-plan closure, novelty risk, baseline/protocol/metric norms, negative evidence, and current-field absence evidence if the method is target-domain-only.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
                {"tool": "agent_materials", "args": {"operation": "closest_prior_materials", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-experiment-plan", "track_plan_matrix.py", "--project <project-root> --check"),
                script_cmd("autoreskill-experiment-plan", "prelaunch_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-experiment-plan", "innovation_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage experiment_plan"),
            ],
            "outputs": [
                ".autoreskill/orchestrator/INNOVATION_PACKET.json",
                ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json",
                ".autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json",
                *INNOVATION_STORY_FILES,
            ],
        },
        "code": {
            "skill": "autoreskill-implement-experiment",
            "role": "Coder",
            "goal": "Audit the locked baseline code and dataset, stage/upload the bundle through the selected SSH/local-GPU or AutoDL backend, implement comparable baseline/proposed real experiment entrypoints, and produce real-data or real-feature smoke proof.",
            "mcp_calls": [],
            "capture": [
                script_cmd("autoreskill-implement-experiment", "baseline_clone_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-implement-experiment", "experiment_drift_lint.py", "--project <project-root>"),
                script_cmd(
                    "autoreskill-implement-experiment",
                    "experiment_real_readiness_lint.py",
                    "--project <project-root>",
                ),
            ],
            "outputs": [
                ".autoreskill/coder/EXPERIMENT_INDEX.md",
                ".autoreskill/coder/experiments/**/EXPERIMENT_MANIFEST.json",
                ".autoreskill/coder/experiments/**/BASELINE_DATA_AUDIT.json",
                ".autoreskill/coder/experiments/**/REMOTE_UPLOAD.json",
                ".autoreskill/coder/experiments/**/REMOTE_RUN.json",
                ".autoreskill/coder/experiments/**/logs/real_*",
            ],
        },
        "experiment": {
            "skill": "autoreskill-run-experiment",
            "role": "Coder",
            "goal": "Launch or reconcile candidate, ablation, and confirmation runs only after baseline-protocol preflight passes. Preserve selected_idea_id, track_id, branch_id, search_iteration, and version_index lineage from TRACK_PLAN_MATRIX into every REMOTE_RUN and EXPERIMENT_LEDGER entry. Failed, regressed, budget-stopped, spec-violating, or diagnostic-only runs must record failure_class and next_action such as repair_same_branch, switch_track, leap_idea, negative_result_route, or hard_stop. Do not substitute a small model or unregistered feature pilot for the locked baseline; off-protocol probes must stop after one diagnostic run and stay not_promoted.",
            "mcp_calls": [],
            "capture": [
                script_cmd("autoreskill-implement-experiment", "baseline_clone_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-run-experiment", "baseline_protocol_launch_lint.py", "--project <project-root>"),
            ],
            "outputs": [".autoreskill/coder/EXPERIMENT_LEDGER.json", ".autoreskill/coder/TRACK_RANKING.json", ".autoreskill/coder/EXPERIMENT_INDEX.md"],
        },
        "analysis": {
            "skill": "autoreskill-analyze-results",
            "role": "Analyzer",
            "goal": "Convert experiment proof into claim-evidence matrix, track verdicts, idea outcome summary, unsupported claims, and narrative report. Consume IDEA_DECISION_LEDGER, TRACK_PLAN_MATRIX, EXPERIMENT_LEDGER, BEST_RUN_SELECTION, SCORE_VERIFICATION, and SPEC_VIOLATION_AUDIT so every idea is classified as promoted evidence, candidate/pilot-only, failed/regressed negative evidence, parked, killed, or downgraded. Trigger targeted PaperNexus discovery when results contradict the expected mechanism, expose a hidden confound, or need source-backed negative evidence or limitation framing.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: post-result claim repair, contradictory evidence, negative results, limitations, failure modes, and mechanism diagnosis.", **broad_metadata_discovery}},
                {"tool": "agent_materials", "args": {"operation": "research_material_pack", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-analyze-results", "best_run_selector.py", "--project <project-root> --check"),
                script_cmd("autoreskill-analyze-results", "analysis_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage analysis"),
            ],
            "outputs": [
                ".autoreskill/analyzer/BEST_RUN_SELECTION.json",
                ".autoreskill/analyzer/SCORE_VERIFICATION.json",
                ".autoreskill/analyzer/SPEC_VIOLATION_AUDIT.json",
                ".autoreskill/analyzer/IDEA_OUTCOME_SUMMARY.json",
                ".autoreskill/analyzer/CLAIM_EVIDENCE_MATRIX.md",
                ".autoreskill/analyzer/TRACK_VERDICTS.md",
                ".autoreskill/analyzer/UNSUPPORTED_CLAIMS.md",
                *INNOVATION_STORY_FILES,
            ],
        },
        "review_pressure": {
            "skill": "autoreskill-review-gate",
            "role": "Reviewer",
            "goal": "Run isolated review and close or downgrade blocking findings. Trigger targeted PaperNexus discovery for reviewer objections about novelty, related work, missing baselines, missing citations, protocol norms, threat models, or unsupported significance.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: reviewer-pressure repair for novelty, related work, missing baselines/citations, protocol norms, threat models, and significance claims.", **broad_metadata_discovery}},
                {"tool": "research_briefing", "args": {"operation": "evidence_chain", "corpus": corpus}},
            ],
            "capture": [
                script_cmd("autoreskill-review-gate", "review_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-review-gate", "citation_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage review_pressure"),
            ],
            "outputs": [".autoreskill/reviewer/REVIEW_FINDINGS.json", *INNOVATION_STORY_FILES],
        },
        "writing": {
            "skill": "autoreskill-paper-write",
            "role": "Academic Writer",
            "goal": "Write evidence-bound manuscript material from approved claims, literature, review guidance, and IDEA_OUTCOME_SUMMARY. Promoted runs may support strong improvement claims; failed, regressed, killed, or parked ideas may only appear as negative evidence, limitations, future work, or downgraded claims. Trigger targeted literature discovery when related-work contrast, must-cite papers, citation ids, or claim support are missing.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: manuscript related-work and citation closure, closest-prior contrast, must-cite papers, and claim support.", **broad_metadata_discovery}},
                {"tool": "research_briefing", "args": {"operation": "research_brief", "corpus": corpus}},
            ],
            "capture": [script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage writing")],
            "outputs": [".autoreskill/paper/main.tex", ".autoreskill/paper/write_package.json", *INNOVATION_STORY_FILES],
        },
        "submission_ready": {
            "skill": "autoreskill-review-gate",
            "role": "WorkflowGuard",
            "goal": "Verify final submission package, citation integrity, front matter, and target-venue readiness. Trigger final targeted discovery only for citation/source blockers that prevent readiness.",
            "mcp_calls": [
                {"tool": "literature_discovery", "args": {"operation": "search", "corpus": corpus, "topic": f"{goal_topic}\n\nSearch purpose: final citation/source verification and unresolved bibliography blockers before submission.", **broad_metadata_discovery}},
            ],
            "capture": [
                script_cmd("autoreskill-review-gate", "review_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-review-gate", "citation_lint.py", "--project <project-root>"),
                script_cmd("autoreskill-workflow", "innovation_story_lint.py", "--project <project-root> --stage submission_ready"),
            ],
            "outputs": [
                ".autoreskill/paper/main.tex",
                ".autoreskill/paper/main.pdf",
                ".autoreskill/submission_ready.json",
                *INNOVATION_STORY_FILES,
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
    spec = execution_spec(stage, state, contract, job, base)
    mcp_calls = list(spec["mcp_calls"])
    capture_commands = list(spec["capture"])
    outputs = list(spec["outputs"])
    literature_search = has_literature_search(mcp_calls)
    if literature_search:
        corpus = (state.get("paperNexus") or {}).get("corpus")
        if not any(isinstance(call, dict) and call.get("tool") == "import_workflow" for call in mcp_calls):
            mcp_calls.append({"tool": "import_workflow", "args": {"operation": "queue_progress", "corpus": corpus, "limit": 20}})
        if not any("--kind literature_discovery_packet" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    f"--project <project-root> --kind literature_discovery_packet --input <mcp-result.json> --stage {stage} --source papernexus-remote.literature_discovery --evidence-note \"{stage} literature discovery evidence\" --tag {stage} --tag literature_discovery",
                )
            )
        if not any("--kind import_workflow_status" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "papernexus_artifact_capture.py",
                    f"--project <project-root> --kind import_workflow_status --input <import-workflow-queue-or-wait-result.json> --stage {stage} --source papernexus-remote.import_workflow --tag {stage} --tag import_workflow",
                )
            )
        if not any("discovery_metadata_triage.py" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "discovery_metadata_triage.py",
                    f"--project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage {stage}",
                )
            )
        if not any("import_workflow_status_lint.py" in command for command in capture_commands):
            capture_commands.append(
                script_cmd(
                    "autoreskill-papernexus-innovation",
                    "import_workflow_status_lint.py",
                    "--project <project-root>",
                )
            )
        outputs = append_unique(
            outputs,
            [
                ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json",
                ".autoreskill/papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
                ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_PLAN.json",
                ".autoreskill/papernexus/GRAPH_IMPORT_STATUS.json",
                ".autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json",
                ".autoreskill/papernexus/SPLIT_READING_EVIDENCE_PACK.json",
            ],
        )
    if stage in INNOVATION_STORY_STAGES:
        outputs = append_unique(outputs, INNOVATION_STORY_FILES if stage not in {"ideation", "idea_gate"} else [INNOVATION_STORY_FILES[0]])
        if not any("innovation_story_lint.py" in command for command in capture_commands):
            capture_commands.append(script_cmd("autoreskill-workflow", "innovation_story_lint.py", f"--project <project-root> --stage {stage}"))
    constraints = [
        "Use PaperNexus live graph work only through papernexus-remote MCP.",
        "Do not use local PaperNexus CLI, raw HTTP, local graph files, local MCP, or SSH graph commands as substitutes.",
        "Do not invent citations, evidence, or experiment results.",
        "After producing artifacts, rerun the relevant linter before marking this job complete.",
    ]
    acceptance_criteria = [
        "Required outputs exist under .autoreskill/",
        "contract_lint.py or the stage linter reports complete",
        "decision_log.jsonl records the produced artifact or explicit blocker",
    ]
    if literature_search:
        constraints.extend(
            [
                "Treat literature_discovery search results as recall only, not graph-grounded evidence.",
                "For broad or long-running discovery/import work, prefer literature_discovery operation=submit plus progress/report polling; do not lose server-side state to an MCP client timeout.",
                "After every useful discovery result, screen candidates into papernexus/PAPER_SELECTION_SCORECARD.json and reject duplicates, weak relevance, unresolved sources, survey noise, and generic benchmark-only papers.",
                "Build papernexus/GRAPH_IMPORT_PLAN.json from selected usable papers, then request PaperNexus import/supplement/material-view or split-reading evidence before using those papers for novelty, baseline, mechanism, limitation, or citation claims.",
                "Use PaperNexus import_workflow queue_progress/status/wait for selected import tasks; capture papernexus/IMPORT_WORKFLOW_STATUS.json and require status=completed, stage=completed, plus authoritative sync completion or supersession before treating a paper as graph-visible.",
                "Use progressive import batching defaults unless the server overrides them: importBatchEnabled=true, importBatchInitialTasks=4, importBatchMaxTasks=16, importBatchProgressive=true.",
                "A fast commit with authoritativeSync pending is an async wait condition, not graph-grounded evidence closure.",
            ]
        )
        acceptance_criteria.extend(
            [
                "Raw discovery candidates are screened before any graph/material evidence claim",
                "Selected usable papers have explicit graph_import, split_read_only, watchlist, or rejection decisions",
                "IMPORT_WORKFLOW_STATUS.json records taskIds/batchIds/queue progress or wait results for selected import tasks",
                "Graph/material import, authoritative-sync wait, or split-reading blockers are recorded instead of silently treating raw search rows as evidence",
            ]
        )
    if stage in INNOVATION_STORY_STAGES:
        constraints.extend(
            [
                "Maintain the project-bound user-facing innovation story under .autoreskill/user_view/innovation_story/.",
                "Write the story as a narrative persuasion design, not a bullet list of modules or contribution points.",
                "Keep 00_STORYLINE_DESIGN.md focused on reader belief shift, opening tension, hidden cause, method-as-resolution, proof ladder, figures, reviewer risk, and final narrative spine.",
                "Keep 01_METHOD_INNOVATION_STORY.md focused on how the method grows from current-field pressure plus near/far-neighbor or cross-lane transfer mechanisms.",
                "Keep 02_CLAIM_EVIDENCE_MAP.md focused on which paper claims are supported, limited, downgraded, or still waiting for evidence.",
            ]
        )
        acceptance_criteria.extend(
            [
                "innovation_story_lint.py reports complete for this stage",
                "The user-facing innovation story explains the paper storyline and method logic rather than only listing innovation points",
            ]
        )
    if stage in {"ideation", "idea_gate", "experiment_plan"}:
        constraints.extend(
            [
                "Every paper idea or selected paper plan must preserve at least three mutually necessary innovation points.",
                "The innovation bundle must cover problem/protocol/evaluation, method/mechanism, and training/integration/analysis/validation; three module names are not sufficient.",
                "At least one innovation point must be grounded in near-neighbor, far-neighbor, proposal-graph, external-domain, or cross-lane transfer evidence unless current-field absence evidence is explicitly source-backed.",
                "The storyline must explain the opening tension, hidden cause, method-as-resolution, proof ladder, reviewer risk/defense, and a sequential narrative spine.",
            ]
        )
        acceptance_criteria.extend(
            [
                "Machine-readable artifacts preserve the three-or-more innovation bundle and complete storyline",
                "The selected idea would not remain a coherent paper if any one innovation point were removed",
            ]
        )
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
        "mcp_calls": mcp_calls,
        "capture_commands": capture_commands,
        "allowed_writes": stage_write_scopes(stage),
        "constraints": constraints,
        "outputs": outputs,
        "acceptance_criteria": acceptance_criteria,
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
        "frontier_mapping": [".autoreskill/papernexus/", ".autoreskill/literature/", ".autoreskill/ideation/"],
        "literature_review": [".autoreskill/literature/", ".autoreskill/papernexus/"],
        "ideation": [".autoreskill/ideation/", ".autoreskill/papernexus/", ".autoreskill/literature/", ".autoreskill/user_view/"],
        "idea_gate": [".autoreskill/ideation/", ".autoreskill/reviewer/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "experiment_plan": [".autoreskill/orchestrator/", ".autoreskill/planner/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "code": [".autoreskill/coder/"],
        "experiment": [".autoreskill/coder/"],
        "analysis": [".autoreskill/analyzer/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "review_pressure": [".autoreskill/reviewer/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "writing": [".autoreskill/paper/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/user_view/"],
        "submission_ready": [".autoreskill/paper/", ".autoreskill/literature/", ".autoreskill/papernexus/", ".autoreskill/submission_ready.json", ".autoreskill/user_view/"],
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
    out = {"action": "advanced", "from": stage, "to": new_stage, "contract": contract}
    if str(state.get("autonomy_level") or "") == "full_auto_bounded":
        out["wakeup"] = continuation_wakeup_recommendation(project, stage, new_stage)
    return out


def run_tick(args: argparse.Namespace) -> None:
    base = ar(args.project)
    state = load_state(args.project)
    policy = read_json(base / "autopilot_policy.json", {})
    repair_queue = rows(base / "repair_queue.jsonl")
    async_queue = rows(base / "async_jobs.jsonl")

    due_async = next_due_job(async_queue, include_running=True)
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
    klass, recommended_action = classify(stage, reason, base)
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
        wakeup = async_wakeup_recommendation(args.project, job, reason)
        state["blocking_reason"] = reason
        state["next_action"] = recommended_action
        save_state(
            args.project,
            state,
            "queued_async_wait",
            {"blocker": blocker, "job": job, "job_packet": str(packet) if packet else None, "wakeup": wakeup},
        )
        print(
            json.dumps(
                {
                    "action": "queued_async_wait",
                    "blocker": blocker,
                    "job": job,
                    "job_packet": str(packet) if packet else None,
                    "wakeup": wakeup,
                },
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
