# Experiment Next Actions

Use this reference for project experiment planning, concurrent launch ownership,
and the rendered WIKI dashboard. The JSON queue schedules evidence acquisition;
it does not establish run status, scientific truth, or claim promotion.

## Authority

- `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json`: scheduling authority.
- `orchestrator/TRACK_PLAN_MATRIX.json`: track and causal-contract authority.
- `orchestrator/tracks/<track-id>/INNOVATION_PACKET.json` and
  `planner/tracks/<track-id>/EXPERIMENT_REVIEW_PACKET.json`: per-track mechanism,
  protocol, and evidence-ceiling authority. Top-level packets project only the
  current primary.
- `ideation/IDEA_DECISION_LEDGER.json`: current selection and belief authority.
- `.autoreskill/resources/PROJECT_EXECUTION_PASSPORT.json`: component-addressed
  baseline, code, dataset, metric, runtime, launcher, and path authority. A row
  binds one `execution_profile_sha256`; its track packet owns only the
  innovation delta.
- `.autoreskill/resources/RESOURCE_CAPABILITY_PASSPORT.json`: verified,
  component-scoped pool compatibility. It does not own current GPU availability.
- A fresh normalized resource snapshot: volatile queue, slot, memory, and
  resource-id evidence. Idle hardware without a fitting capability profile is
  non-fitting.
- Per-run `REMOTE_RUN.json`: backend/runtime evidence.
- A hashed global schedule: ephemeral shared-resource proposal only; it never
  replaces a project queue or backend preflight.
- Rendered Markdown and chat summaries: views or inputs only.

If the WIKI differs from JSON, re-render JSON. If a lease differs from live
backend state, reconcile the backend before changing ownership.

## Commands

```bash
python <skill-root>/scripts/experiment_next_actions.py init --project <root> --direction <direction>
python <skill-root>/scripts/experiment_next_actions.py check --project <root>
python <skill-root>/scripts/experiment_next_actions.py frontier --project <root>
python <skill-root>/scripts/experiment_next_actions.py schedule --project <root>
python <skill-root>/scripts/experiment_next_actions.py schedule-global --project <a> --project <b> --resource-snapshot <shared.json> --out <schedule.json>
python <skill-root>/scripts/experiment_next_actions.py render --project <root>
python <skill-root>/scripts/experiment_next_actions.py render-global --project <a> --project <b> --out <rollup.md>
python <skill-root>/scripts/experiment_next_actions.py set-policy --project <root> --expected-revision <n> --portfolio-capacity-target 4 --reason <why>

python <skill-root>/scripts/experiment_next_actions.py commit-resource-snapshot --project <root> --input <normalized-proposal.json> --owner <worker> --expected-revision <n>
python <skill-root>/scripts/experiment_next_actions.py claim --project <root> --row-id <id> --owner <worker> --expected-revision <n>
python <skill-root>/scripts/experiment_next_actions.py claim-assignment --project <root> --row-id <id> --pool-id <pool> --owner <worker> --expected-revision <n>
# In admission_scope=global, also pass:
# --global-plan <schedule.json> --global-schedule-sha256 <sha> --assignment-sha256 <sha> --global-lease-file <lease.json>
python <skill-root>/scripts/experiment_next_actions.py record-backend-preflight --project <root> --row-id <id> --owner <worker> --expected-revision <n> --input <preflight.json>
python <skill-root>/scripts/experiment_next_actions.py prepare-backend-submit --project <root> --row-id <id> --owner <worker> --expected-revision <n> --input <intent.json>
python <skill-root>/scripts/experiment_next_actions.py abort-backend-submit --project <root> --row-id <id> --owner <worker> --expected-revision <n> --input <no-live-run-evidence.json>
python <skill-root>/scripts/experiment_next_actions.py record-backend-submit --project <root> --row-id <id> --owner <worker> --expected-revision <n> --input <receipt.json>
python <skill-root>/scripts/experiment_next_actions.py record-backend-observation --project <root> --row-id <id> --owner <worker> --expected-revision <n> --input <observation.json>
python <skill-root>/scripts/experiment_next_actions.py renew --project <root> --row-id <id> --owner <worker> --expected-revision <n>
python <skill-root>/scripts/experiment_next_actions.py release --project <root> --row-id <id> --owner <worker> --expected-revision <n> --reason <why>
python <skill-root>/scripts/experiment_next_actions.py complete --project <root> --row-id <id> --owner <worker> --expected-revision <n> --status <terminal-status> --evidence <path>

python <skill-root>/scripts/portfolio_batch.py --project <root> --dry-run
python <skill-root>/scripts/portfolio_batch.py --project <root>
python <skill-root>/scripts/portfolio_batch.py --project <root> --recover-operation <operation-id>
python <skill-root>/scripts/resource_passport.py build-project --project <root>
python <skill-root>/scripts/resource_passport.py lint-project --project <root>
python <skill-root>/scripts/resource_passport.py plan-capability --project <root> --pool <pool> --out <staging-plan.json>
python <skill-root>/scripts/resource_passport.py enrich-snapshot --project <root> --input <live-snapshot.json> --out <enriched.json>
python <skill-root>/scripts/research_efficiency_report.py observe --project <root>
python <skill-root>/scripts/research_efficiency_report.py report --project <root> --markdown-out <report.md>
```

Broad project mutations require
`scripts/control_plane_lease.py acquire --project <root> --owner <worker>
--operation <operation>`. Cross-project admission additionally requires a live
global lease. Acquire in fixed order: global, then target project; row leases are
separate and remain mandatory.

`set-policy` uses queue-revision CAS. It refuses an admission-scope switch while
`planned`, `submitting`, `needs_sync`, or `running` rows retain launch authority.
`claim` is required before a backend launch. A repeated claim by the same owner
is idempotent. A competing owner receives a structured conflict. Lease expiry
only permits reconciliation; it never proves that a remote job stopped.

For a detailed GPU/HPC pool assignment, use `claim-assignment` instead of plain
`claim`. Under the same queue lock it recomputes the current first deterministic
assignment, binds both row and pool in `planned_resource_allocation`, consumes
the observed slot, marks the snapshot stale, and advances one queue revision.
It remains a local lease, not remote launch, reservation, or submit authority.
`commit-resource-snapshot` and `record-backend-preflight` use the same queue
lock, re-read the revision under that lock, validate exact route/resource
identity, and atomically replace the JSON file. A stale or competing writer gets
a structured CAS conflict and leaves no partial state.

## Schema V2

Top-level fields include `schema_version=2`, integer `queue_revision`, project
and WIKI configuration, `policy`, `rows`, and `decision_log`. Schema v1 remains
readable, but it must migrate before any new `ready`, `planned`, `submitting`,
`needs_sync`, or `running` transition.

Every row requires:

- `id`, numeric `priority`, `status`, `role`, `dataset`, `next_action`, and
  `updated_at`.

Every launchable `ready`, `planned`, `submitting`, `needs_sync`, or `running`
row additionally requires:

- `selected_idea_id`, `track_id`, `branch_id`;
- `selection_fingerprint` or `selected_primary_ref`;
- `launch_identity_hash`, `track_plan_ref`, and `causal_signature`;
- `decision_class`, `why_now`, and `expected_decision_change`;
- `claim_target`, `hypothesis_prediction`, and `falsifier`;
- `outcome_routes.positive`, `.negative`, `.inconclusive`, and `.invalid`;
- `baseline_anchor`, explicit `comparison_source`, `protocol`, and
  `metric_policy_ref`;
- `resource_request`, `mutex_group`, explicit boolean `parallel_safe`, and
  `evidence_paths`.

`planned`, `submitting`, `needs_sync`, and `running` rows also require
`lease_owner`, `lease_acquired_at`, and `lease_expires_at`. `submitting` requires
a durable submit intent; `needs_sync` requires its bound backend receipt; only
an authoritative backend observation may set `running` and its `run_id` or a
terminal state.

Work missing launch identity or a resolvable dependency reference belongs in
`candidate`; moving it to `ready` is a hard error. A pre-materialized row whose
referenced dependency exists but is not terminal is warned and locally rejected
by the scheduler so it cannot stall other independent ready rows. Current
selection, branch, causal signature, and lifecycle must match the track matrix
and decision ledger.

An external rapid pilot may arrive with six routes. The queue deterministically
projects valid positive, negative, and inconclusive to their canonical peers and
preserves infrastructure, implementation, and protocol failures as named
subroutes under `invalid`. For external rows,
`resource_request.backend == execution_route` is mandatory, and the selected
pool backend/route must match it exactly.

New queues use `policy.parallelism_mode=elastic_bounded` and
`max_new_launches_per_cycle=auto`. Automatic sizing is bounded by useful ready
rows, compatible idle GPU slots, optional `max_gpu_slots_in_flight`, optional
`max_gpu_hours_in_flight`, and `absolute_max_new_launches_per_cycle` (default
16). A positive numeric `max_new_launches_per_cycle` remains a compatibility
override but is still bounded by the absolute cap. `ready_frontier_multiplier`
and `max_ready_frontier_rows` bound planning breadth; they are never quotas.
GPU-slot limits are positive integers; GPU-hour limits are positive finite
numbers, so malformed fractional slot limits cannot silently disable a budget.
`policy.admission_scope` is `project` by default. Set it to `global` only when a
single cross-project dispatcher owns physical admission.
`policy.portfolio_capacity_target` is at most four and defaults to four. It is a
capacity/planning target, not a quota to invent tracks.

`resource_snapshot.pools` is optional and preferred. Each pool records a stable
`pool_id`, backend, account/host reference, status, free `launch_slots`, memory
and model/capabilities when relevant, snapshot time, and optional
`shared_limit_ref`. A `pending` pool blocks itself. It blocks other pools only
when live evidence marks the shared limit blocked. Aggregate idle-slot fields
remain readable as an unverified compatibility fallback; backend preflight is
still required. A snapshot explicitly marked `status=stale|expired`,
`stale=true`, or `fresh=false` produces `requires_resource_refresh=true` and no
assignment. This explicit state keeps scheduling deterministic; backend tools,
not wall-clock guessing in the scheduler, decide when to mark a snapshot stale.
When capability enforcement is active, each pool also lists the currently
satisfied `execution_profile_sha256s`; a stale/suspect/invalid component removes
only dependent profiles. A component-scoped negative cache suppresses repeated
placement until reverified, while unrelated profiles remain usable.

Rows may add `decision_target_refs`, `experiment_family_id`,
`replication_group_id`, `evidence_tier=pilot_only|claim_eligible`, and
`baseline_freeze_ref`. Decision impact is derived from unique target references,
not a free-form score. Claim-closing `claim_eligible` rows require a frozen
baseline reference; `pilot_only` rows cannot close or promote a claim.
Rows on the validation ladder also bind `validation_stage` (0-7), prerequisites,
claim ceiling, project passport index, execution profile, and innovation-delta
hash. Those identities propagate into implementation and run manifests.

Every planning-admitted row resolves to a current matrix row and packet hashes.
Exactly one track has role `primary`; at most three have role `alternate` or
`risk_repair`. A non-primary queue row must use `evidence_tier=pilot_only`, may
not use a claim-closing decision effect, and cannot become claim-eligible until
explicit primary reselection and matched rerun.

## Acquisition Order

Rows are ordered lexicographically, not by an invented scientific probability:

1. `repair_validity`: recover canonical evidence after parser/protocol/spec failure.
2. `resolve_competing_hypotheses`: distinguish mechanisms with different predictions.
3. `falsify_core_mechanism`: run the cheapest valid test of the primary mechanism.
4. `close_required_claim`: fill a mandatory baseline, ablation, or metric component.
5. `confirm_generalization`: test a supported mechanism on another target dataset.
6. `optimize_supported_mechanism`: bounded DEHB/HPO after mechanism support.
7. `resource_fill_diagnostic`: non-claim work that may use otherwise idle capacity.

Within a class, prefer more unique `decision_target_refs`, then lower estimated
GPU-hours, then numeric `priority` and stable row id. Resource placement first
preserves pools that are the only fit for later constrained rows, then chooses
the smallest fitting pool, so flexible work does not consume scarce memory,
backend, or capability capacity. A diagnostic never displaces a fitting
decision-changing experiment, but it may use capacity left over after every
higher-class fitting row is considered. Acquisition order is not a global
barrier: a 48-GiB high-class row does not idle an unrelated 24-GiB pool that can
run a lower-class decision-bearing row.

## Experiment Design Rules

- For one selection revision, generate 8-12 lightweight hypothesis cards once,
  normalize causal signatures, merge semantic duplicates, and batch-screen to a
  3-5 item shortlist. Deep literature/causal/experiment contracts are
  shortlist-only. Reuse that shortlist until an explicit lifecycle decision
  exhausts, invalidates, or supersedes it.
- Deterministically rank hard-gate survivors by claim-changing decision targets,
  competing explanations distinguished, lower falsifier GPU-hours, reuse of
  locked project components, then lower novelty/confound risk. Report
  `validation_density = unique_decision_targets / estimated_gpu_hours` as an
  explanatory metric, not a fabricated success probability.
- Test each causal innovation independently on the target dataset family before
  claim-bearing combinations. A one-dataset result stays dataset-scoped.
- A combo names exact `component_innovation_ids` and terminal supporting rows.
  Negative, protocol-mismatched, or unsupported components cannot unlock it.
- Use a small greedy/beam combo set, not exhaustive power-set search.
- Cross-dataset confirmation outranks parameter tuning once a mechanism has
  initial support.
- `PARAM` and target sweeps use resource-constrained DEHB. Low-fidelity scouts
  are search evidence only; the fidelity axis is not random seed.
- Maintain a bounded ready frontier from already justified baseline calibration,
  active-track discriminators, cross-dataset tests, controls, ablations, bounded
  HPO trials, and confirmations. Never create a row because a GPU is idle.
- Baseline calibration trials may overlap with `pilot_only` innovation scouts.
  Freeze the matched baseline before claim promotion and rerun surviving scouts
  against that freeze.
- Use the 0-7 ladder: static/config (0), active-path smoke or small-batch overfit
  (1), complete parameter probes then paired low-fidelity method screens (2),
  primary full-budget matched control (3), remaining required-dataset full-budget
  legs (4), sensitivity-justified dataset-group DEHB (5), at
  most three paired seeds (6), and a small supported-component combo search (7).
  Baseline calibration is separate `pilot_only` work, not Stage 5. Stage 5
  requires initial support/explicit ambiguity and a named sensitivity question;
  Stage 7 accepts only independently supported components.
- Random-seed stability validation is capped at three unique seeds per
  `experiment_family_id`, including HPO scouts. Final matched baseline/proposed
  seeds form one paired replication group and may launch concurrently. A retry
  reuses its declared seed; seed is never a tuning axis.
- Paper-reported, reproduced, and matched reproduced baselines remain separate.

## Bounded Ready Frontier

`frontier` reports two independent signals without writing rows.
`launch_frontier_*` counts current decision-bearing ready, planned, submitting,
needs-sync, and running rows plus only packet-declared, dependency-unlocked
discriminators, datasets, controls, ablations, combinations, and confirmations.
Deduplicate by decision target, track, dataset, protocol, variant, and seed
profile.

`portfolio_capacity_target`, `portfolio_active_track_count`,
`portfolio_admission_deficit`, `portfolio_fillable_count`, and
`portfolio_fillable_candidate_ids` describe hypothesis supply. Fillable ids are
the exact deterministic feasible subset after causal-diversity, dependency,
mutex, per-candidate cost, aggregate GPU-hour budget, and deficit checks. The
batch transaction admits/materializes every id in that subset. It journals
packet, matrix, and queue mutations and restores all targets after any
pre-commit interruption. Zero active tracks are never "satisfied" while this
subset is non-empty.

`method_portfolio_target`, `active_method_candidate_count`, and
`method_portfolio_deficit` count only real method candidates. Diagnostic,
baseline-support, and protocol-support rows remain schedulable outside the
hypothesis portfolio. `parameter_profile_status_by_track`,
`parameter_coverage_deficit_by_track_and_dataset`, and `parameter_blockers`
explain why a method track needs probes, a ledger decision, or a frozen profile;
they are projections, not another authority.

For enforced cross-dataset projects, `dataset_coverage_deficit_by_track`,
`paired_group_incomplete_count`, `paired_group_missing_dataset_legs`,
`cross_dataset_full_budget_ready_count`, `robust_hpo_ready_count`, and
`cross_dataset_blockers` expose the next scientific coverage gap. These fields
remain read-only projections. They never freeze a profile, adjudicate a result,
or authorize a launch.

`missing_track_packet`, `admissible_frontier_deficit`, and
`portfolio_admission_deficit` with a non-empty feasible subset route to
synchronous batch planning. `scientific_dependency_wait` permits runtime waiting
only when its authoritative run exists. A fresh snapshot may expose zero fitting
placement capacity, but it does not prevent preparing already admitted work.
Idle slots never invent candidates or expand four-track, three-seed, HPO, or
GPU-hour budgets.

When `portfolio_admission_deficit > 0`, `portfolio_fillable_count=0`, and a named
program claim remains unresolved, WorkflowGuard may route one
`replenish_experiment_portfolio` planning action even when zero tracks are active.
This local planning action does not require a GPU snapshot. It first commits one
changed-basis `replenishment_event` to the idea ledger, preserves any active
primary selection fingerprint, performs bounded evidence-backed candidate
replenishment, binds the pool and scorecard to the active program revision, and
returns to this frontier. An unchanged basis is idempotently rejected. The action
does not choose a primary, generate track seeds, create a queue row from capacity,
bypass candidate admission, or authorize a backend launch. A replacement program
must archive and activate its reviewed revision before this transaction.

## Cross-Project Admission

`schedule-global` reads several `admission_scope=global` project queues and one
fresh normalized shared snapshot. It validates queue revisions/hashes, excludes
projects held by another live project-control owner, and returns a deterministic
advisory schedule. Acquisition class dominates; within one class use soft
project round-robin, decision impact, lower GPU-hours, project/row priorities,
and stable ids. Assign to the smallest fitting pool, decrement `launch_slots`,
and never reuse a concrete resource id. Before global scheduling, enrich each
project view with its capability passport; shared idle hardware is not fitting
unless it satisfies the row's exact execution profile.

Only assignment zero has `claimable_first=true`. In global mode,
`claim-assignment` verifies the schedule, assignment, queue, snapshot, pool, and
both control leases under the project queue lock. It writes only the row lease
and planned allocation. Then run backend preflight and exactly one physical
launch, mark resource evidence stale, refresh, and recompute. A changed queue,
snapshot, packet/selection authority, hash, non-first assignment, or expired
lease fails closed. A project with no fitting row reserves nothing.

## Parallel Launch Protocol

1. Reconcile `submitting`, `needs_sync`, and `running` rows against backend
   state. For `submitting`, search the backend-searchable intent trace before any
   retry; ambiguity blocks resubmission.
2. Validate the queue and current track/selection authorities.
3. Normalize one captured backend/account/host observation, then install its
   `proposed_resource_snapshot` with `commit-resource-snapshot` CAS. Run the
   read-only `schedule` command; a missing snapshot requests refresh and does not
   authorize launch.
4. Use only deterministic assignments whose dependencies, mutex, duplicate,
   in-flight budget, seed, claim-boundary, and resource-fit checks pass.
5. For a physical/account pool, atomically `claim-assignment` for only the first
   deterministic row/pool pair with the observed `queue_revision` and worker
   id. In global mode this means the first hashed global assignment and a live
   global-then-project lease chain. Plain `claim` remains for project-mode routes
   without a detailed pool assignment.
6. Only the lease winner performs route-specific backend preflight, records it
   with `record-backend-preflight` CAS against the same allocation/snapshot and
   exact launch-spec digest, then calls `prepare-backend-submit` to durably move
   `planned -> submitting` before the physical side effect.
7. Submit exactly the prepared script/spec with its trace. Immediately persist
   the native receipt through `record-backend-submit`, which moves
   `submitting -> needs_sync`. If the submit is proven not to have started, use
   `abort-backend-submit`; lease expiry or a missing local receipt is not proof.
8. Record authoritative scheduler/process observation through
   `record-backend-observation`, moving to `running` or terminal. Preserve the
   planned allocation and all intent/receipt/observation hashes.
9. Mark resource evidence stale, refresh, recompute, and repeat from the current
   first assignment until no fitting row or the bounded wake limit remains.
   Complete with an evidence path; release only after explicit no-live-run proof.

A running experiment is a resource-scoped lock, not a project-wide wait. Launch
the automatic bounded batch, not an insertion-order prefix. `planned` rows are
already leased and are not selected for another worker. If no row fits, preserve
the exact scheduler rejection reason; an underfilled frontier is a planning
signal, not permission to invent work. Only then may monitoring wait.

Remote safety is unchanged: claiming a row does not authorize kill, cancel,
paid provisioning, GPU reservation, or Slurm submission outside the relevant
backend skill and user policy.

## Status And Role Values

Statuses: `candidate`, `ready`, `planned`, `submitting`, `needs_sync`, `running`,
`terminal_positive`, `terminal_negative`, `blocked`, `dropped`, `superseded`.

Roles: `baseline_anchor`, `baseline_calibration`, `single_innovation`, `combo`,
`stability`, `adapter_unblock`, `monitor_sync`, `negative_control`,
`parameter_probe`.

Comparison labels:

- `vs paper-reported baseline`
- `vs reproduced baseline`
- `vs matched reproduced baseline`
- `paper-report comparison not established`

## WIKI Projection

Read `wiki_projection_and_naming.md` before creating, moving, or linking a Wiki
artifact. The project dashboard is a derived view inside the project's single
canonical AutoResearch hub; it must not create a parallel experiment workspace.
Offline fixtures must pass temporary `--wiki-root` and `--global-path` values
and must never render into the live default Wiki.

The portable default dashboard is:

```text
${AUTORESEARCH_WIKI_ROOT:-$HOME/Documents/001-WIKI/mypaper}/<direction>/03-创新点/AutoResearch-<project>/NEXT_EXPERIMENT_ACTIONS.md
```

Override it through
`.autoreskill/experiment/EXPERIMENT_PLANNER_CONFIG.json`. Update and render only
when a result, first useful metric, blocker, selection, resource decision, or
explicit planning request changes the next action. A heartbeat with no decision
change must not rewrite the queue or WIKI.

Project and global dashboards expose track role, evidence ceiling, separate
launch and portfolio target/supply/deficit/blockers, capability-fit coverage,
admission scope, and current live project-control owner. These remain derived
views.
