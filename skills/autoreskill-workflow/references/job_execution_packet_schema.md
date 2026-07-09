# Job Execution Packet Schema

`goal_tick.py` writes job packets under `.autoreskill/job_packets/<job_id>.json`.

This file owns packet shape, acceptance contracts, runtime observations, and
queue update protocol. It does not own stage completion, PaperNexus discovery
policy, heartbeat cadence, or user-facing innovation story content.

## Table Of Contents

- Purpose
- Required Packet Shape
- Acceptance Contract
- Runtime Observation
- Dispatch And Queue Updates
- Special Packet Notes
- Loop Trace

## Purpose

Use job packets to:

- connect `.autoreskill/repair_queue.jsonl` and `.autoreskill/async_jobs.jsonl`
  to executable child-skill work;
- keep `.autoreskill/job_packets/` as the durable prompt/snapshot surface;
- tell the role pass what done means before execution starts;
- provide enough disk state to resume after context loss;
- avoid adding parallel queues such as `.autoreskill/pending_actions/`.

## Required Packet Shape

Minimum packet:

```json
{
  "schema_version": 1,
  "job_id": "job_x",
  "job_kind": "repair",
  "stage": "experiment_plan",
  "status": "ready_for_execution",
  "skill": "autoreskill-experiment-plan",
  "role": "Orchestrator",
  "goal": "bounded task",
  "inputs": [".autoreskill/ideation/IDEA_DECISION_LEDGER.json"],
  "mcp_calls": [],
  "capture_commands": [],
  "constraints": ["Do not invent citations, evidence, or experiment results."],
  "outputs": [".autoreskill/orchestrator/INNOVATION_PACKET.json"],
  "acceptance_contract": {
    "must_produce": [".autoreskill/orchestrator/INNOVATION_PACKET.json"],
    "must_pass": [
      "python <skill-root>/scripts/contract_lint.py --project <project-root> --stage experiment_plan --json"
    ],
    "must_not_violate": ["Do not change locked dataset, metric, or baseline."],
    "claim_boundaries": ["Pilot evidence remains pilot-only until promoted."],
    "evaluator_commands": [],
    "done_when": ["Required artifact exists and the next blocker is explicit."]
  },
  "runtime_observation": null,
  "acceptance_criteria": ["contract_lint.py reports complete or next blocker is explicit"]
}
```

`acceptance_criteria` remains backward-compatible for legacy packets. New
nontrivial planning, experiment, analysis, review, writing, repair, or
submission-readiness packets should include `acceptance_contract`.

Use `mcp_calls` only to describe intended tool calls. Concrete PaperNexus search
budgets and discovery policies belong to the PaperNexus child skill and
`literature_discovery_triggers.md`, not this schema.

## Acceptance Contract

Fields:

- `must_produce`: artifacts the role must write or update.
- `must_pass`: commands, lints, or checks that must succeed.
- `must_not_violate`: protocol, scope, safety, evidence, or claim boundaries.
- `claim_boundaries`: wording or evidence limits that must survive the job.
- `evaluator_commands`: optional commands or review prompts for an independent
  Evaluator packet.
- `done_when`: observable completion criteria in user/system terms.

Map contract assertion types onto this schema instead of creating a second
contract format:

| Assertion type | Packet field |
| --- | --- |
| Functional assertion | `must_produce`, `done_when` |
| Counterexample or forbidden behavior | `must_not_violate` |
| Scope assertion | `claim_boundaries`, `constraints` |
| Evidence assertion | `must_pass`, `evaluator_commands`, `outputs` |
| Subjective assertion | rubric artifact named in `outputs` plus `evaluator_commands` |

## Runtime Observation

Use `runtime_observation` on async-poll jobs and repeated tool actions where the
same action is legitimate only if progress changes. This field is recovery and
stall-diagnosis evidence, not stage authority.

Recommended shape:

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

- Same action plus changed result or progress marker: continue adaptive wait.
- Same action plus same result and unchanged progress marker: increment
  `stale_poll_count` and classify against `async_wait_policy.md`.
- Terminal, superseded, or locally actionable result: update the async job and
  continue the bounded local loop instead of scheduling another heartbeat.

## Dispatch And Queue Updates

Render a prompt for a serialized role pass or sub-agent:

```bash
python <skill-root>/scripts/goal_job_dispatch.py --project <project-root> --job-id <job-id> --mode serialized --mark-running
```

The prompt is written to `.autoreskill/job_packets/<job_id>.prompt.md` and copied
to `mailbox.jsonl`.

When `goal_job_dispatch.py --mode subagent` writes a
`.subagent_request.json`, the parent Codex agent must call the configured
multi-agent tool and then record the result with:

```bash
python <skill-root>/scripts/goal_subagent_result.py --project <project-root> --job-id <job-id> --agent-id <agent-id> --status completed --artifact <artifact-path>
```

After executing the rendered prompt, update the queue:

```bash
python <skill-root>/scripts/goal_job_update.py --project <project-root> --kind repair --job-id <job-id> --status completed --artifact <artifact-path>
```

If execution fails, record the exact blocker:

```bash
python <skill-root>/scripts/goal_job_update.py --project <project-root> --kind repair --job-id <job-id> --status failed --error "<reason>"
```

On resume, reconcile stale running jobs:

```bash
python <skill-root>/scripts/goal_job_reconcile.py --project <project-root> --stale-minutes 60
```

## Special Packet Notes

`repair_failed_experiment` is not permission to blindly rerun the last command.
The role pass must read the experiment ledger and selected idea/track lineage,
write a failure analysis, and choose one route: same-branch repair, track switch,
idea or innovation rebuild, downgrade/negative-evidence path, or hard stop. After
two same-idea repairs without promoted improvement, route back to planning,
idea_gate, or ideation instead of launching another same-idea run.

If a packet writes user-facing innovation story files, apply
`innovation_story_contract.md`. Story files are derived views and do not replace
machine-readable authorities.

If a packet triggers an external wait, apply `async_wait_policy.md`. Heartbeats
are allowed only for PaperNexus literature discovery, PaperNexus graph
import/authoritative sync, and experiment runtime/resource waits.

## Loop Trace

When a role pass, lint, evaluator, repair, or restart decision changes the
workflow route, append a compact JSON line to `.autoreskill/LOOP_TRACE.jsonl`.
Core scripts append trace entries for state saves, job dispatches, job updates,
actual stale-job reconcile changes, and sub-agent results. Use manual trace
entries only for evaluator findings or restart decisions that happen outside
those scripts.

The trace is recovery evidence, not a stage authority. Do not replace
`goal_state.json`, job status, stage artifacts, or `contract_lint.py` with trace
entries.

Manual trace entry:

```bash
python <skill-root>/scripts/loop_trace.py --project <project-root> --event evaluator_block --stage analysis --authority Evaluator --decision queue_repair --reason "<exact finding>"
```
