# Async Wait Policy

Use this reference when `goal.py tick` returns a `wakeup` recommendation or when
a heartbeat resume needs to decide whether to keep, update, or delete a managed
Codex heartbeat.

## Table Of Contents

- Allowed Heartbeat Scopes
- Bounded Continuation Before Waiting
- Stale External Polls
- Managed Heartbeat Lifecycle
- Result-Aware Poll Classification
- PaperNexus Graph Import Heartbeats

## Allowed Heartbeat Scopes

Create or update a heartbeat only for external waits in these scopes:

- PaperNexus literature discovery submit/progress/report waits.
- PaperNexus graph import, fast commit, semantic readiness, or authoritative sync
  waits.
- Experiment runtime, queue, GPU/resource, or remote monitor waits.

Do not create a heartbeat for stage transitions, locally ready repairs, lint
triage, planning, writing, review, stale job reconciliation, or any state where
the parent agent can continue the bounded loop locally.

## Bounded Continuation Before Waiting

In `full_auto_bounded`, an `advanced` result is an instruction to continue, not a
wait request. A heartbeat resume is also not limited to one job plus one follow-up
tick. Continue running local ticks/jobs until one of these conditions is reached:

- `hard_stop` or terminal completion.
- `queued_async_wait` for an allowed external wait.
- `repair_already_queued` with no due packet.
- External live run/resource wait.
- User, budget, credential, or safety gate.
- Active loop budget is exhausted.

Default loop budget is 5 tick/job actions or about 10 minutes of active work.

## Stale External Polls

If the latest experiment monitor reports no active live run, all runs terminal,
or launch/repair readiness with no external runtime wait, treat any existing
`poll_experiment_run` heartbeat as obsolete. Supersede the async job and continue
local WorkflowGuard classification so idle resources can trigger launch, repair,
rollback, or stage advancement.

Apply the same local-first rule to non-experiment external waits:

- `poll_literature_discovery` is obsolete when the discovery packet already
  exists, the report is terminal/ready and only local capture remains, the run id
  is missing and a local submit/capture repair is required, or the job belongs to
  a previous stage.
- `poll_graph_import_sync` is obsolete when selected graph import tasks are
  terminal complete, graph-visible, semantic-ready, and authoritative-synced;
  when the status artifact says planned imports have not been submitted and
  local submission is required; when the status is failed/source-limited and
  repair or claim downgrade is required; or when the job belongs to a previous
  stage.
- A due async row may be left pending when it still describes a valid external
  wait but the current contract has a more immediate local repair. It must not be
  dispatched until the current contract again identifies the same external wait
  as the blocker.

`next_retry_at` is an unattended backoff, not a hard block after a human/resource
update. If the user provides a new endpoint, credential, GPU allocation, dataset
path, or other readiness signal, the parent agent may force the matching repair:

```bash
python <skill-root>/scripts/goal.py tick --project <project-root> --force-due-repair --force-job-id <job_id>
```

or write `.autoreskill/control/ACTIVE_RETRY_OVERRIDE.json`. Record the override
reason in the repair/status artifact and return to normal intervals afterward.

## Managed Heartbeat Lifecycle

Every heartbeat created by this workflow is managed state. On every resume:

1. Read live progress, previous ETA/progress snapshot, async job status, and the
   current stage blocker.
2. Decide whether the wait condition is terminal, still external, stale, or now
   locally actionable.
3. Keep, update, or delete the heartbeat.
4. Update the async job state, meaning the queue row and packet snapshot when
   present, with an action signature, result signature, progress marker,
   progress flag, and stale count.
5. Record `poll_interval_decision`, observed progress, ETA or wait condition, and
   reason in the status summary or project artifact.

Delete the heartbeat when the wait is terminal, superseded, user-paused, or no
longer an allowed external async wait.

Deleting a heartbeat is not a workflow stop condition. After deletion, run the
local successor check (`goal.py status`, `goal.py reconcile --stale-minutes 60`,
then `goal.py tick`) and continue the bounded loop if a repair, analysis,
planning, launch, rollback/degrade route, or stage transition is locally
actionable. Only return after recording an explicit terminal completion,
allowed external wait, safety/user/budget/credential gate, or exhausted loop
budget.

## Result-Aware Poll Classification

Repeated polls are allowed only when the observed result or progress marker can
change. Classify each poll before scheduling another heartbeat:

| Observation | Decision |
| --- | --- |
| Same action signature, changed result signature or progress marker | Continue adaptive wait and reset or hold stale count |
| Same action signature, same result signature, unchanged progress marker | Increment stale count and apply the stale-poll policy |
| Terminal result | Complete or fail the async job, delete heartbeat, and tick locally |
| Superseded wait | Mark job superseded, delete heartbeat, and continue local routing |
| Locally actionable repair or launch state | Stop waiting and dispatch/queue repair in the bounded loop |

Use compact normalized status for signatures. Store only enough progress to make
the next resume deterministic: remote status, task/run id, queue position,
completed/submitted counts, last step, metric-row count, ETA basis, or terminal
state. Do not store large raw logs, secrets, datasets, checkpoints, or full tool
payloads in `runtime_observation`.

## PaperNexus Graph Import Heartbeats

For `import_workflow` graph-build waits, choose the interval dynamically from live
queue and graph state. Do not use a universal fixed cadence.

Base the interval on:

- selected task terminal/risky states;
- running task progress, stage, processed unit rate, recent transitions, and
  timeout risk;
- queued selected task position, queued-ahead count, worker count, queue
  completion delta, and selected-position delta;
- authoritative sync state and semantic graph readiness;
- the nearest plausible decision point when no reliable ETA exists.

Record `poll_interval_decision`, `estimated_next_event_at` or `eta_basis`, and
the reason in `papernexus/IMPORT_WORKFLOW_STATUS.json` or the stage monitor
artifact.

Delete a graph heartbeat only after every selected task needed for the wait is
terminal complete with graph visibility, semantic readiness when required, and
authoritative sync complete, superseded, or explicitly not required. If a
heartbeat combines graph import with another active wait, compute intervals for
each wait independently and use the earliest meaningful next-check time.
