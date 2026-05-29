# Handoff Packet Schema

Handoff packets isolate child roles.

```json
{
  "schema_version": 1,
  "from": "WorkflowGuard",
  "to": "Coder",
  "stage": "code",
  "goal": "Implement the reviewed experiment bundle.",
  "inputs": [
    ".autoreskill/orchestrator/INNOVATION_PACKET.json",
    ".autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json"
  ],
  "allowed_writes": [".autoreskill/coder/"],
  "constraints": [
    "Preserve one-variable change.",
    "Do not change dataset or primary metric.",
    "Dry-run before launch."
  ],
  "outputs": [".autoreskill/coder/EXPERIMENT_INDEX.md"],
  "acceptance_criteria": [
    "baseline and proposed configs exist",
    "dry-run log exists",
    "manifest links track_id and claim_ids"
  ]
}
```

Reviewers should receive isolated packets and should not read hidden context from researcher/coder passes.
