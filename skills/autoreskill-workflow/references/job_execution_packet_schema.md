# Job Execution Packet Schema

`goal_tick.py` writes job packets under `.autoreskill/job_packets/<job_id>.json`.

Purpose:

- Connect repair/async queues to executable child-skill work.
- Keep PaperNexus work explicit: Codex calls `papernexus-remote` MCP, then captures results with the PaperNexus helper scripts.
- Give WorkflowGuard a stable artifact to resume after context loss.
- For long-running PaperNexus discovery/import work, prefer async queue state plus Codex thread heartbeat wakeups over in-thread shell sleep polling.

Required fields:

```json
{
  "schema_version": 1,
  "job_id": "job_x",
  "job_kind": "repair",
  "stage": "topic_search",
  "status": "ready_for_execution",
  "skill": "autoreskill-papernexus-innovation",
  "role": "Researcher",
  "goal": "bounded task",
  "mcp_calls": [
    {
      "tool": "literature_discovery",
      "args": {
        "operation": "search",
        "depth": "deep",
        "searchMode": "deep",
        "planningMode": "llm_augmented",
        "llmQueryPlanner": true,
        "citationExpansion": true,
        "openAlexRelatedExpansion": true,
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
        "allowDownloads": false,
        "importBatchEnabled": true,
        "importBatchInitialTasks": 4,
        "importBatchMaxTasks": 16,
        "importBatchProgressive": true,
        "importResolved": false,
        "processImports": false,
        "returnPartial": true,
        "persist": true
      }
    }
  ],
  "capture_commands": ["python .../papernexus_artifact_capture.py ..."],
  "constraints": ["Do not invent citations, evidence, or experiment results."],
  "outputs": [".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json"],
  "acceptance_criteria": ["contract_lint.py reports complete"]
}
```

`goal_job_dispatch.py` refuses to render any job packet containing `literature_discovery(operation="search")` unless the search uses the broad configuration above. This applies to ideation lanes and later targeted discovery repair packets; the topic may be narrow, but the discovery configuration must remain recall-oriented. For `topic_search`, the first executable packet must use `literature_discovery(operation="submit")` and capture `literature/LITERATURE_DISCOVERY_RUN.json` before any async wait is queued. Only after a run id exists may WorkflowGuard queue `poll_literature_discovery` and create a heartbeat. If the remote run is still active, update the async queue and let `goal_tick.py` return a `wakeup` recommendation for a Codex heartbeat, default 5 minutes; do not keep the current turn alive with shell sleep loops. Use `operation=resolve`, `import`, `ingest`, or `import_and_process` only after screening selected papers, and then track graph visibility through `import_workflow`.

`topic_search` uses a state-aware route:

1. No `literature/LITERATURE_DISCOVERY_RUN.json` and no `literature/LITERATURE_DISCOVERY_PACKET.json`: queue `submit_literature_discovery` as a repair job.
2. `LITERATURE_DISCOVERY_RUN.json` exists but no report packet and the run is not terminal/report-ready: queue `poll_literature_discovery` as an async wait.
3. The run is terminal/report-ready but no report packet exists: queue `capture_literature_discovery_report` as a repair job.
4. A report packet exists but screening artifacts are missing: queue `screen_literature_discovery` as a repair job.

Every packet containing `literature_discovery(operation="search")` must also close the post-discovery evidence loop in the serialized prompt:

1. Capture the search result as a discovery artifact.
2. Run candidate triage/screening and write `papernexus/PAPER_SELECTION_SCORECARD.json`.
3. Build `papernexus/GRAPH_IMPORT_PLAN.json` from selected usable papers, including `planned_import_count` and `required_graph_import_keys` for every `import`/`supplement` row.
4. Use the plan to request PaperNexus import/supplement for every required graph-import row and material-view or split-reading work only for `material_view` rows.
5. Capture `papernexus/IMPORT_WORKFLOW_STATUS.json` from `import_workflow queue_progress/status/wait`, including planned/submitted/completed/authoritative-sync counts, selected task ids or batch ids, and any missing unsubmitted/incomplete/unsynced keys.
6. Wait until every required graph-import task reports `status=completed`, `stage=completed`, and authoritative graph sync is complete or superseded. If any task is pending, queue async wait and schedule a heartbeat from the tick `wakeup` recommendation instead of treating raw discovery as evidence.
7. Capture `papernexus/SPLIT_READING_EVIDENCE_PACK.json` before using the papers as novelty, method, baseline, limitation, or citation evidence.

Raw discovery results are search evidence only. They are not graph-grounded evidence.

Packets for `ideation`, `idea_gate`, `experiment_plan`, `analysis`, `review_pressure`, `writing`, or `submission_ready` must also maintain the project-bound user-facing story directory when their outputs include `.autoreskill/user_view/innovation_story/`:

```text
.autoreskill/user_view/innovation_story/
  00_STORYLINE_DESIGN.md
  01_METHOD_INNOVATION_STORY.md
  02_CLAIM_EVIDENCE_MAP.md
```

The rendered prompt must tell the role pass to write narrative prose, not a bullet list of novelty points. `00_STORYLINE_DESIGN.md` starts at `ideation` and is revised at `idea_gate`; all three files are required from `experiment_plan` onward. Before completion, run:

```bash
python <skill-root>/scripts/innovation_story_lint.py --project <project-root> --stage <stage>
```

These files are a user view derived from evidence artifacts. They do not replace `EXPERIMENT_IDEA_POOL.json`, `INNOVATION_PACKET.json`, `EXPERIMENT_REVIEW_PACKET.json`, analysis matrices, review gates, or manuscript/package authorities.

After executing a packet, update the queue:

Render a prompt for a serialized role pass or sub-agent:

```bash
python scripts/goal_job_dispatch.py --project <project-root> --job-id <job-id> --mode serialized --mark-running
```

The prompt is written to `.autoreskill/job_packets/<job_id>.prompt.md` and copied to `mailbox.jsonl`.

After executing the rendered prompt, update the queue:

```bash
python scripts/goal_job_update.py --project <project-root> --kind repair --job-id <job-id> --status completed --artifact .autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json
```

If execution fails, record the exact blocker:

```bash
python scripts/goal_job_update.py --project <project-root> --kind repair --job-id <job-id> --status failed --error "<reason>"
```

On resume, reconcile stale running jobs:

```bash
python scripts/goal_job_reconcile.py --project <project-root> --stale-minutes 60
```
