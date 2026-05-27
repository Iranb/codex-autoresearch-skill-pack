# Decision Log Schema

Each `decision_log.jsonl` row:

```json
{
  "ts": "ISO-8601",
  "stage": "experiment_plan",
  "actor": "WorkflowGuard",
  "action": "advance|block|repair|degrade|dispatch|rollback|hard_stop",
  "reason": "machine_readable_reason",
  "inputs": ["artifact paths"],
  "outputs": ["artifact paths"],
  "next_action": "bounded next step"
}
```

The log explains why the workflow moved, not just what file appeared.
