# Job Execution Packet Schema

`goal_tick.py` writes job packets under `.autoreskill/job_packets/<job_id>.json`.

Purpose:

- Connect repair/async queues to executable child-skill work.
- Keep PaperNexus work explicit: Codex calls `papernexus-remote` MCP, then captures results with the PaperNexus helper scripts.
- Give WorkflowGuard a stable artifact to resume after context loss.

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

`goal_job_dispatch.py` refuses to render any job packet containing `literature_discovery(operation="search")` unless the search uses the broad configuration above. This applies to topic search, ideation lanes, and later targeted discovery repair packets; the topic may be narrow, but the discovery configuration must remain recall-oriented. Use `operation=resolve`, `import`, `ingest`, or `import_and_process` only after screening selected papers.

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
