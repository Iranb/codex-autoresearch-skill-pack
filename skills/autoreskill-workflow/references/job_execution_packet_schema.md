# Job Execution Packet Schema

`goal_tick.py` writes job packets under `.autoreskill/job_packets/<job_id>.json`.

Purpose:

- Connect repair/async queues to executable child-skill work.
- Keep repair, async, retry, and approval-like pending execution state in the
  existing job system: `.autoreskill/repair_queue.jsonl` and
  `.autoreskill/async_jobs.jsonl` as authoritative queues, with
  `.autoreskill/job_packets/` as executable packet/snapshot storage. Do not add
  `.autoreskill/pending_actions/` or another parallel queue.
- Keep PaperNexus work explicit: Codex calls `papernexus-remote` MCP, then captures results with the PaperNexus helper scripts.
- Give WorkflowGuard a stable artifact to resume after context loss.
- Let the role pass know what "done" means before it starts, using either legacy
  `acceptance_criteria` or the structured `acceptance_contract`.
- Provide enough traceable state that an interrupted loop can resume from disk
  rather than hidden model context.
- For long-running PaperNexus discovery/import work and experiment runtime/resource waits, prefer async queue state plus Codex thread heartbeat wakeups over in-thread shell sleep polling.
- Limit heartbeat creation to PaperNexus literature discovery, PaperNexus graph import/authoritative sync, and experiment runtime/resource waits. Local stage transitions, ready repairs, linter failures, planning, review, writing, or generic queues must continue in the bounded loop or stop with an explicit blocker.

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
        "operation": "submit",
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
        "persist": true,
        "asyncLifecycle": "submit_progress_report"
      }
    }
  ],
  "capture_commands": ["python .../papernexus_artifact_capture.py ..."],
  "constraints": ["Do not invent citations, evidence, or experiment results."],
  "outputs": [".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json"],
  "acceptance_contract": {
    "must_produce": [".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json"],
    "must_pass": ["python <skill-root>/scripts/contract_lint.py --project <project-root> --stage topic_search --json"],
    "must_not_violate": ["Do not treat raw discovery results as graph-grounded evidence."],
    "claim_boundaries": ["Discovery output is recall evidence until graph/material evidence is captured."],
    "evaluator_commands": [],
    "done_when": ["Required artifact exists and the stage lint is complete or the next blocker is explicit."]
  },
  "runtime_observation": {
    "action_signature": "literature_discovery:topic_search:<run_id>",
    "result_signature": "sha256:<compact-normalized-result>",
    "progress_marker": {
      "status": "running",
      "completed": 12,
      "submitted": 16,
      "terminal": false
    },
    "progress_observed": true,
    "last_progress_at": "ISO-8601",
    "stale_poll_count": 0
  },
  "acceptance_criteria": ["contract_lint.py reports complete"]
}
```

`acceptance_contract` is additive. `goal_tick.py` generated packets include it;
existing or external packets that contain only `acceptance_criteria` remain
valid. Use the structured contract for nontrivial planning, experiment,
analysis, review, writing, repair, or submission-readiness jobs where a vague
"complete" would invite drift.

Fields:

- `must_produce`: artifacts the role must write or update.
- `must_pass`: commands, lints, or checks that must succeed.
- `must_not_violate`: protocol, scope, safety, evidence, or claim boundaries.
- `claim_boundaries`: wording or evidence limits that must survive the job.
- `evaluator_commands`: optional commands or review prompts for an independent
  Evaluator packet.
- `done_when`: observable completion criteria in user/system terms.

Map contract assertion types onto this existing schema instead of creating a
second contract format:

| Assertion type | Packet field |
| --- | --- |
| Functional assertion | `must_produce`, `done_when` |
| Counterexample or forbidden-behavior assertion | `must_not_violate` |
| Scope assertion | `claim_boundaries`, `constraints` |
| Evidence assertion | `must_pass`, `evaluator_commands`, `outputs` |
| Subjective assertion | rubric artifact named in `outputs` plus `evaluator_commands` |

## Runtime Observation For Repeated Or Async Work

Use `runtime_observation` on async-poll jobs and any repeated tool action where
the same command may be legitimate only if progress changes. This field is
recovery and stall-diagnosis evidence, not stage authority.

Recommended fields:

```json
{
  "action_signature": "poll_experiment_run:experiment:run_42",
  "result_signature": "sha256:abbrev",
  "progress_marker": {
    "remote_status": "running",
    "last_step": 1200,
    "metric_rows": 8,
    "terminal": false
  },
  "progress_observed": true,
  "last_progress_at": "ISO-8601",
  "stale_poll_count": 0,
  "wait_condition": "remote run still active",
  "next_retry_at": "ISO-8601"
}
```

Derive `action_signature` from stable inputs such as job kind, stage, remote run
id, selected task id, tool name, and normalized arguments. Derive
`result_signature` from a compact normalized status/result summary. Do not hash
or store raw logs, secrets, full model outputs, datasets, checkpoints, or large
tool payloads.

Classification rule:

- Same action plus changed result or changed progress marker: continue the
  adaptive wait; this is progress, not a doom loop.
- Same action plus same result and unchanged progress marker: increment
  `stale_poll_count` and classify against the stage policy.
- Terminal, superseded, or locally actionable result: mark the async job
  complete, superseded, failed, or repair-ready and continue the bounded local
  loop instead of scheduling another heartbeat.

`goal_job_dispatch.py` refuses to render broad `literature_discovery(operation="submit")` packets unless they use the broad configuration above. Synchronous `operation="search"` is allowed only for explicitly bounded targeted lookups, such as `targeted=true` with small candidate caps. For `topic_search`, the first executable packet must use `literature_discovery(operation="submit")` and capture `literature/LITERATURE_DISCOVERY_RUN.json` before any async wait is queued. Only after a run id exists may WorkflowGuard queue `poll_literature_discovery` and create a heartbeat. If the remote run is still active, update the async queue and let `goal_tick.py` return a `wakeup` recommendation for a Codex heartbeat; do not keep the current turn alive with shell sleep loops. Use `operation=resolve`, `import`, `ingest`, or `import_and_process` only after screening selected papers, and then track graph visibility through `import_workflow` with the adaptive graph-state cadence from `SKILL.md`.

`topic_search` uses a state-aware route:

1. No `literature/LITERATURE_DISCOVERY_RUN.json` and no `literature/LITERATURE_DISCOVERY_PACKET.json`: queue `submit_literature_discovery` as a repair job.
2. `LITERATURE_DISCOVERY_RUN.json` exists but no report packet and the run is not terminal/report-ready: queue `poll_literature_discovery` as an async wait.
3. The run is terminal/report-ready but no report packet exists: queue `capture_literature_discovery_report` as a repair job.
4. A report packet exists but screening artifacts are missing: queue `screen_literature_discovery` as a repair job.

Every packet containing broad `literature_discovery(operation="submit")` or targeted `operation="search"` must also close the post-discovery evidence loop in the serialized prompt:

1. Capture the submitted run/progress and final report as discovery artifacts; for targeted search, capture the search result directly.
2. Run candidate triage/screening and write `papernexus/PAPER_SELECTION_SCORECARD.json`.
3. Build `papernexus/GRAPH_IMPORT_PLAN.json` from selected usable papers, including `planned_import_count` and `required_graph_import_keys` for every `import`/`supplement` row.
4. Use the plan to request PaperNexus import/supplement for every actionable required graph-import row and material-view or split-reading work only for `material_view` rows. If a selected row cannot produce a task after exact source discovery, OA/index checks, and PaperNexus `pdfUrl/sourcePath/serverFilePath` attempts, record it as a source-limited exception instead of retrying metadata-only imports.
5. Capture `papernexus/IMPORT_WORKFLOW_STATUS.json` from `import_workflow queue_progress/status/wait`, including planned/effective-planned/submitted/completed/authoritative-sync counts, selected task ids or batch ids, any missing unsubmitted/incomplete/unsynced keys, and any `source_limited_exception_keys`.
6. Wait until every actionable graph-import task reports `status=completed`, `stage=completed`, and authoritative graph sync is complete, superseded, or explicitly not-required. If any task is pending, queue async wait and schedule a heartbeat from the tick `wakeup` recommendation instead of treating raw discovery as evidence. If only source-limited exceptions remain, write claim limits and allow WorkflowGuard to advance without using those rows as graph-grounded evidence.
7. Capture `papernexus/SPLIT_READING_EVIDENCE_PACK.json` before using the papers as novelty, method, baseline, limitation, or citation evidence.

Raw discovery results are recall evidence only. They are not graph-grounded evidence.

## Experiment Failure Repair Packets

When `goal_tick.py` emits a `repair_failed_experiment` job, the packet is not permission to blindly rerun the last command. The role pass must:

1. Read `coder/EXPERIMENT_LEDGER.json`, the relevant `REMOTE_RUN.json`, synced logs, `TRACK_PLAN_MATRIX.json`, and selected idea/track lineage.
2. Write `coder/EXPERIMENT_FAILURE_ANALYSIS.json` with root cause, `failure_class`, selected idea id, track id, branch/version lineage, evidence refs, and the chosen next action.
3. If fewer than two same-idea repair attempts have been used, launch exactly one bounded repair run under the locked protocol and record `repair_attempt` or `repair_iteration` in the ledger.
4. If two same-idea repairs have already failed to produce promoted improvement, do not launch another same-idea run. Write `coder/EXPERIMENT_NEGATIVE_BLOCKER.json` with `status=change_idea_or_innovation_required` so WorkflowGuard can route back to `experiment_plan`, `idea_gate`, or `ideation`.
5. Keep candidate-supported or diagnostic-only results as pilot/negative evidence unless they meet the stage's promotion requirements.

Failed, regressed, budget-stopped, spec-violating, or not-promoted ledger rows must drive a concrete route: same-branch repair, track switch, idea/innovation rebuild, downgrade/negative-evidence path, or hard stop. They must not remain as generic experiment incompletion. If the same cause repeats, prefer a clean restart at the branch, track, or idea level: retire the failed route, preserve its evidence, and re-enter planning or idea_gate with the negative result visible.

## Loop Trace

When a role pass, lint, evaluator, repair, or restart decision changes the
workflow route, append a compact JSON line to `.autoreskill/LOOP_TRACE.jsonl`.
The core scripts append trace entries for state saves, job dispatches, job
updates, actual stale-job reconcile changes, and sub-agent results. Use manual
trace entries for evaluator findings or restart decisions that happen outside those scripts.
This trace is recovery evidence, not a stage authority.

Recommended fields:

```json
{
  "ts": "ISO-8601",
  "stage": "analysis",
  "event": "lint_failed",
  "job_id": "job_x",
  "authority": "scripts/contract_lint.py",
  "decision": "queue_repair",
  "evidence_refs": [".autoreskill/analyzer/SCORE_VERIFICATION.json"],
  "next_action": "repair_score_verification",
  "action_signature": "analysis_lint:score_verification",
  "result_signature": "sha256:compact-lint-result",
  "progress_marker": {"blocking_findings": 1},
  "progress_observed": false,
  "reason": "critical slice regression was hidden by aggregate metric"
}
```

Use the trace to debug where the loop first diverged from the intended route.
Do not replace `goal_state.json`, job status, stage artifacts, or
`contract_lint.py` with trace entries.

Manual trace entry:

```bash
python <skill-root>/scripts/loop_trace.py --project <project-root> --event evaluator_block --stage analysis --authority Evaluator --decision queue_repair --reason "<exact finding>"
```

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
