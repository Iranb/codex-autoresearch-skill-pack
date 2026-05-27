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
  "mcp_calls": [{"tool": "literature_discovery", "args": {"operation": "search"}}],
  "capture_commands": ["python .../papernexus_artifact_capture.py ..."],
  "constraints": ["Do not invent citations, evidence, or experiment results."],
  "outputs": [".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json"],
  "acceptance_criteria": ["contract_lint.py reports complete"]
}
```

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
