# Async Wait Policy

Use this reference when `goal.py tick` returns a `wakeup` recommendation or when
a heartbeat resume needs to decide whether to keep, update, or delete a managed
Codex heartbeat.

## Table Of Contents

- Allowed Heartbeat Scopes
- Bounded Continuation Before Waiting
- Stale External Polls
- Experiment Opportunity Scan
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
- External live run/resource wait with no eligible parallel experiment launch.
- User, budget, credential, or safety gate.
- Active loop budget is exhausted.

Default loop budget is 5 tick/job actions or about 10 minutes of active work.

## Stale External Polls

If the latest experiment monitor reports no active live run, all runs terminal,
or launch/repair readiness with no external runtime wait, treat any existing
`poll_experiment_run` heartbeat as obsolete. Supersede the async job and continue
local WorkflowGuard classification so idle resources can trigger launch, repair,
rollback, or stage advancement.

Also treat `poll_experiment_run` as obsolete when the next-action queue contains
an independent `ready` or `planned` launch row that can fit remaining resources.
A running experiment is not a global barrier: before continuing a heartbeat,
check `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json`, reconcile stale
running rows, refresh live GPU/HPC capacity, and dispatch a parallel launch when
the candidate row has no blocker, satisfied dependencies, no mutex/resource
conflict, and `parallel_safe` is not false.

Before waiting, also run the queue `frontier` check. An actionable
`missing_track_packet` or `admissible_frontier_deficit` is synchronous planning,
not a heartbeat. `scientific_dependency_wait` is a valid experiment wait only
when the referenced authoritative run is live. In `admission_scope=global`, a
project monitor reports `global_admission_required` and leaves physical launch
to the global dispatcher.

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

## Experiment Opportunity Scan

Every experiment heartbeat runs this scan after reconciling live/terminal rows
and before choosing the next wait:

1. Validate the current next-action queue and selection/packet authorities, then
   run `experiment_next_actions.py frontier`.
2. Refresh live resource pools when a ready/planned row, positive portfolio
   deficit, or capacity-dependent blocker exists; run project or global
   scheduling under its current authority. Count only fresh capability-known
   slots, not raw SSH hosts or unverified GPUs.
3. Continue synchronously for an actionable missing packet, control, ablation,
   cross-dataset confirmation, or other packet-declared frontier row.
4. Compute `portfolio_admission_deficit = 4 - active_nonterminal_tracks`. From
   the committed evidence-gated shortlist, select the exact deterministic
   feasible subset of causally distinct untested candidates, bounded by the
   deficit and aggregate budget, then batch-admit and materialize every selected
   candidate's cheapest single-seed `pilot_only` test in one recoverable
   transaction. This direct-admission step does not regenerate/rescore the
   shortlist, admit from GPU availability, or serialize the batch to one
   candidate per heartbeat; use step 5 only when its stricter conditions hold.
5. If the deficit is positive and the current-revision committed shortlist has
   no fillable candidate, dispatch one bounded `replenish_experiment_portfolio`
   action when the ledger records a named unresolved program claim and the
   evidence/compute/revision budgets permit it. Candidate construction is local;
   it does not wait for or require idle GPUs. Zero active tracks are eligible;
   they are not proof that the program is complete. Before generation, commit one
   idempotent changed-basis `replenishment_event` with
   `research_decision.py --replenishment --write`. Preserve any selected primary
   and its selection fingerprint; record `shortlist_exhausted`, `invalid`, or
   `strategically_superseded` in existing lifecycle/decision authorities; reuse
   the current canonical evidence source and corpus; run targeted incremental
   discovery only for missing evidence roles; generate 8-12 lightweight cards,
   merge causal duplicates, and batch-screen one 3-5 item shortlist. Bind the
   pool and scorecard to the active program revision; do not select a primary or
   generate track seeds in this action. Deep-plan only the exact feasible
   candidates needed by the deficit in the following admission action. Reuse the prior
   event or rejection instead of repeating research when the program, lifecycle,
   evidence-source, selection, and decision fingerprints are unchanged. If the
   old route is track-terminal but project-nonterminal, first follow the explicit
   replacement-authority and program-revision recovery route; a project-terminal
   route cannot reopen.
6. Before seeds or HPO, materialize every missing preregistered
   `stage2_parameter_probe` row for the selected load-bearing parameter across all
   required datasets. After the ledger-owned calibration decision freezes one
   profile, materialize every paired `stage2_method_screen` leg. Open DEHB only
   after cross-dataset support and a named coupled-parameter sensitivity question;
   a valid negative, missing matched baseline, or idle GPU is not such a question.
   After each ledger write, run `stage_transition_materialize.py --dry-run`, then
   apply against the reported queue revision. It creates all currently unlocked
   Stage 3/4 rows together, creates one complete dataset-group HPO trial when
   eligible, and creates Stage 6 only after ledger-backed full-budget support
   plus an optional finalized HPO decision. Reconcile grouped HPO evidence with
   `dataset_group_hpo.py reconcile --write`; use `--finalize` only after the
   registered full-resource budget is resolved, or pass a recorded
   `--stop-reason` for a deliberate bounded early stop. An incomplete group has no
   optimizer objective.
7. Route every fitting assignment through the current launch authority. In
   project mode, atomically claim one assignment, persist intent, launch as
   authorized, record receipt/observation, refresh, and repeat until no fitting
   row remains or the wake budget is reached. In global mode, expose rows to the
   global dispatcher; the project monitor must not claim them. One submit before
   refresh is a safety rule, not a one-submit-per-heartbeat limit.

Priority is not a project-wide barrier: lower-priority fitting work may use a
resource pool that no higher-priority row can use. However, ready validity
repairs, causal discriminators, controls, and new single-innovation pilots outrank
parameter optimization on the same fitting pool.

Checking is mandatory, launching is conditional. When no action can proceed,
record the current scheduler or gate rejection rather than writing a generic
`waiting` result. If queue revision, track/selection/lifecycle fingerprints,
result evidence, evidence-source authority, HPO budget, and relevant resource
observations are unchanged, reuse the previous scientific or replenishment
rejection and avoid repeating heavy idea review; a ready row with a capacity
blocker still requires a fresh resource observation.

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
| Independent ready experiment row plus free resource slot | Stop waiting and dispatch `launch_parallel_experiment` |

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
