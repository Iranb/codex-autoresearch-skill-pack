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

## Evaluator Packets

Use an Evaluator packet when the producer's output is high-risk enough that the
same role should not be the only judge. This is recommended before these
top-tier paper-producing transitions:

- `experiment_plan -> code`
- `experiment -> analysis`
- `analysis -> writing`
- `writing -> submission_ready`

Evaluator packets are findings, not stage authorities. They may block, repair, or
downgrade claims through the normal WorkflowGuard loop, but only the canonical
stage authority and `contract_lint.py` can advance a stage.

```json
{
  "schema_version": 1,
  "from": "WorkflowGuard",
  "to": "Evaluator",
  "stage": "analysis",
  "goal": "Stress-test the analysis package before writing.",
  "inputs": [
    ".autoreskill/coder/EXPERIMENT_LEDGER.json",
    ".autoreskill/analyzer/SCORE_VERIFICATION.json",
    ".autoreskill/analyzer/IDEA_OUTCOME_SUMMARY.json"
  ],
  "allowed_writes": [
    ".autoreskill/evaluator/analysis_EVALUATION.json",
    ".autoreskill/reviewer/"
  ],
  "constraints": [
    "Assume the producer missed something until evidence proves otherwise.",
    "Do not edit producer-owned artifacts.",
    "Do not advance goal_state.json.",
    "Tie every finding to an evidence ref, lint result, or missing authority."
  ],
  "outputs": [".autoreskill/evaluator/analysis_EVALUATION.json"],
  "acceptance_contract": {
    "must_produce": [".autoreskill/evaluator/analysis_EVALUATION.json"],
    "must_pass": [],
    "must_not_violate": ["Do not use evaluator judgment as the sole completion authority."],
    "claim_boundaries": ["Unsupported, pilot-only, or aggregate-only claims must be downgraded."],
    "done_when": ["Findings list blocking issues, accepted risks, and required repairs."]
  }
}
```

Evaluator output should contain:

- `status`: `passed`, `repair_required`, `claim_downgrade_required`, or
  `blocked`.
- `checked_authorities`: files and lint outputs read.
- `blocking_findings`: evidence-routed issues that prevent advancement.
- `accepted_risks`: explicit non-blocking risks and claim limits.
- `required_repairs`: next actions for WorkflowGuard.
