# Goal State Schema

`goal_state.json` is the control plane, not proof of semantic completion.

Required fields:

```json
{
  "schema_version": 1,
  "project_root": "/absolute/project",
  "goal": "research problem",
  "target_venue": "unspecified_top_tier",
  "paperNexus": {
    "mode": "remote_mcp",
    "corpus": "PN-ICML-Ideation-Shared-240-v1"
  },
  "stage": "init",
  "owner": "WorkflowGuard",
  "next_action": "resolve_corpus_and_project_memory",
  "blocking_reason": null,
  "autonomy_level": "full_auto_bounded",
  "iteration": 0,
  "updated_at": "ISO-8601"
}
```

`blocking_reason` should be machine-readable. Human-facing explanation belongs in `decision_log.jsonl`.
