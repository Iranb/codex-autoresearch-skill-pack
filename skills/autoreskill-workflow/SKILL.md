---
name: autoreskill-workflow
description: Main $autoreskill and /goal workflow conductor for portable AutoResearch + PaperNexus. Use when initializing, resuming, advancing, debugging, or fully driving a .autoreskill workflow; dispatching role/job packets; checking stage completion; recovering stalled state; organizing project/global Wiki projections and naming; running bounded full-auto research; or routing one-shot global route audits, paper-code surveys, DEHB/HPO planning, writing audit/polish, manuscript integrity, and remote/HPC experiment workflows.
---

# AutoResearch Workflow

Portable AutoResearch + PaperNexus conductor. It must run without
`openclaw-research`, `.openclaw-research/`, `PROJECT_MANIFEST.json`, or
`research_workflow` tools.

## First Principles

Use this skill as a conductor, not as a duplicate implementation of every child
policy.

- One authority per decision: state, contracts, jobs, references, and child
  artifacts each own a different decision surface.
- Disk state beats model memory: persist recoverable facts under `.autoreskill/`.
- Local work beats waiting: wait only for external PaperNexus or experiment
  runtime/resource conditions that cannot be advanced locally.
- Claims follow evidence: diagnostics, smoke tests, source-code inspection, and
  reproduced baselines do not authorize strong paper claims unless the relevant
  contract permits the exact claim boundary.
- Scientific progress means a result changed a recorded hypothesis, claim, or
  lifecycle decision. More jobs, retries, tokens, or GPU occupancy are not
  progress by themselves.
- Keep this prompt small: if a rule has a dedicated reference or linter, cite
  that authority instead of restating the rule here.

## Scope

Every new or resumed workflow must classify the goal in `goal_state.json` or
`autopilot_policy.json` before applying heavy gates.

`goal_type`:

- `paper_producing_top_tier`: default for top conference/journal paper goals.
- `paper_producing_light`: draft or pilot manuscript with reduced evidence.
- `standalone_survey`: paper-code survey, literature survey, or style corpus.
- `writing_style_corpus`: CCF-A/top-tier writing evidence collection only.
- `diagnostic_or_resource`: environment, data, GPU, or non-paper operations.

`claim_mode`:

- `strong_paper_claims`: default for `paper_producing_top_tier`.
- `pilot_evidence`
- `survey_only`
- `writing_guidance_only`
- `diagnostic_only`

Only `paper_producing_top_tier` with `strong_paper_claims` receives the full
paper-readiness contract. Other modes keep provenance and claim limits, but must
not be blocked by unrelated paper-submission gates. When a strong-paper gate is
out of scope, record `claim_limits` or `out_of_scope_claim_limits`.

## Authority Map

- Control plane: `.autoreskill/goal_state.json` and
  `.autoreskill/autopilot_policy.json`.
- Stage completion: `scripts/contract_lint.py --project <project-root> --stage
  <stage>`.
- Work queues: `.autoreskill/repair_queue.jsonl`,
  `.autoreskill/async_jobs.jsonl`, and `.autoreskill/job_packets/`.
- Experiment next-action planning:
  `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json`. Rendered wiki
  dashboards are views only and never complete stages, promote claims, or submit
  jobs.
- Per-track planning:
  `orchestrator/tracks/<track-id>/INNOVATION_PACKET.json` and
  `planner/tracks/<track-id>/EXPERIMENT_REVIEW_PACKET.json` bind each admitted
  track. The top-level packet pair is a primary-only compatibility projection.
- Stable execution compatibility:
  `.autoreskill/resources/PROJECT_EXECUTION_PASSPORT.json` owns reusable
  baseline/code/dataset/metric/runtime components and row-specific execution
  profiles. Each track packet and implementation manifest binds only its
  profile plus innovation-delta hash. The separate
  `RESOURCE_CAPABILITY_PASSPORT.json` proves which profiles a pool can run;
  fresh resource snapshots alone own volatile capacity and queue state.
- Coordination ownership: `.autoreskill/control/PROJECT_CONTROL_LEASE.json`
  protects broad project mutations. A hashed global schedule and the global
  admission lease coordinate shared resources but never replace a project queue
  or backend launch checks.
- Scientific lifecycle: `ideation/IDEA_DECISION_LEDGER.json` owns idea/track
  belief and terminal program decisions; `orchestrator/TRACK_PLAN_MATRIX.json`
  owns launch-plan hypotheses; `coder/EXPERIMENT_LEDGER.json` owns run/outcome
  history. `SCIENTIFIC_OUTCOME.json` is per-run evidence, not transition
  authority.
- Cross-dataset claim requirements:
  `orchestrator/PROGRAM_CLAIM_CONTRACT.json` owns target datasets, metrics,
  comparison requirements, parameter-transfer policy, promotion rules, and
  bounded search budgets. It never owns result-derived scientific status. A
  missing contract preserves legacy behavior; `shadow` is read-only.
- Handoffs: `.autoreskill/handoffs/` and
  `references/handoff_packet_schema.md`.
- Recovery trace: `.autoreskill/LOOP_TRACE.jsonl`; trace entries explain route
  decisions but never complete a stage.
- PaperNexus graph work: configured `papernexus-remote` MCP plus captured
  artifacts. Do not replace live graph work with local PaperNexus CLI, raw HTTP,
  local graph files, local MCP, or SSH graph commands.
- Explicit non-PaperNexus ResearchStudio-style idea campaigns:
  `$autoreskill-gpu-idea-validation` owns only the external evidence campaign,
  its deterministic gate/slot-map adapter, identity alignment, and bounded
  resource-intent helpers. It never replaces the idea ledger, track matrix,
  experiment queue, runtime controller, or scientific-outcome authority.
- Remote/HPC work: this skill owns portable project layout; `$bjtu-hpc` owns
  BJTU auth, live queue state, helper defaults, resource scheduling, dataset
  packing, and submit safety.

## Entry Loop

An explicit one-shot global route audit is routed to
`$autoreskill-global-route-audit` and skips this entry loop so the audit remains
read-only. On every other `$autoreskill`, `autoreskill`, or `/goal` workflow
entry:

1. Resolve `<project-root>` and `<skill-root>`.
2. Run `scripts/ensure_project_agents.py --project <project-root>`.
3. Run `scripts/goal.py status --project <project-root>`.
4. Run `scripts/goal.py reconcile --project <project-root> --stale-minutes 60`.
5. Run `scripts/goal.py tick --project <project-root>`.
6. If tick returns `dispatch_repair` or `dispatch_async_poll`, execute the
   rendered packet through the routed child skill, update the job, and tick
   again while local work remains actionable.

For `full_auto_bounded`, continue for at most 5 tick/job actions or about 10
minutes of active work. Stop only on terminal completion, `hard_stop`,
user/budget/credential/safety gate, loop budget exhaustion, or an allowed
external async wait with no eligible parallel experiment launch.

Before a final response, run the pre-stop guard: if `status`, `tick`, a due job
packet, or `contract_lint.py` exposes a concrete local next action, execute one
bounded tick/job cycle or record the exact external wait, budget/user gate, or
hard stop.

## Async Waits

Codex thread heartbeats are allowed only for external waits:

- PaperNexus literature discovery.
- PaperNexus graph import or authoritative sync.
- Experiment runtime, queue, GPU, or resource wait.

Never create heartbeats for stage transitions, ready repairs, local lint,
planning, writing, review, stale job reconciliation, or generic queue
bookkeeping. Dispatch async only when `goal.py tick` returns
`dispatch_async_poll`; a due async row alone is not proof of external blockage.
After a heartbeat is deleted, updated, or marked stale, run `status`,
`reconcile`, and `tick` again while local work is actionable.

For experiments, a running job is not a project-wide wait condition. Before
creating or keeping an experiment heartbeat, check
`.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json` plus live backend capacity.
If an independent `ready`/`planned` row has no blocker, satisfied dependencies,
no mutex/resource conflict with running rows, and can fit an idle GPU/resource,
dispatch `launch_parallel_experiment` instead of waiting.

Also run the queue `frontier` check before waiting. Materialize only its declared
admissible track packets/rows when the deficit is actionable. If all legal work
depends on a live run, wait on that run; if no authoritative run exists, return
the exact blocker instead of using a heartbeat. In `admission_scope=global`, a
project monitor may reconcile and expose ready work but only the global admission
controller may claim and physically dispatch it.

Read `references/async_wait_policy.md` for adaptive cadence, result-aware
polling, stale wait supersession, and managed heartbeat lifecycle.

## Evidence And Claims

Use `references/stage_contracts.md` plus `contract_lint.py` as the only stage
completion authority. Do not duplicate stage rules in prose when a linter or
reference owns them.

Frequent claim constraints:

- Paper-reported baseline numbers are primary when protocol-aligned. Label
  comparisons as `vs paper-reported baseline`, `vs reproduced baseline`, or
  `vs matched reproduced baseline`; otherwise write
  `paper-report comparison not established`.
- A gain over a reproduced baseline is not automatically a gain over the paper
  report. Keep baseline reproduction alignment separate from method improvement.
- Source-code evidence supports feasibility, active-code-path, and
  mechanism-transfer claims only. Effectiveness claims require matched
  experiment artifacts.
- Random-seed stability validation is capped at three experiment seeds.
  `IDEA_TRACK_SEEDS` are idea/track candidates, not random seeds.
- Launchable `PARAM` mechanisms use resource-constrained DEHB/HPO. Seed is never
  a search axis, low-fidelity scouts are pilot/search evidence only, and
  linear/grid tuning is not a launch plan.
- Strong top-tier writing or submission readiness requires manuscript integrity
  forensics. AIS style impressions carry zero verdict weight and are not
  authorship evidence.

For paper-producing workflows, choose experiments by manuscript need, not by GPU
utilization or candidate-list breadth. Every experiment job must name the paper
claim, table, figure, ablation, or limitation it can change.

### Per-Dataset Innovation Parameter Coverage

Before stability seeds, every selected human-chosen load-bearing innovation
parameter normally tests two or three preregistered values on each required
dataset under exactly one fixed scout seed for that dataset. Build ranges from
dataset scale, train-only/unlabeled distributions, update count, or measured
effective strength; copying one raw scalar requires a comparability rationale.
Several seeds at one value do not satisfy parameter coverage. After a reviewed
calibration decision, freeze one profile and use at most three paired seeds for
confirmation.

`shared_absolute` freezes one common raw value. `shared_normalized` freezes one
common dimensionless setting while its label-free formula may realize different
raw values. Different selected human-chosen settings by dataset are
`dataset_calibrated`. A preregistered one-value `zero_shot_only` test remains
legal but cannot establish calibrated-mechanism validity or refutation. The
canonical schema and claim ceilings are in
`references/program_claim_contract.md` and the experiment review packet schema.

## Scientific Decision Loop

Use this bounded loop:

```text
evidence -> falsifiable track hypothesis -> discriminating experiment
  -> canonical result -> scientific outcome -> lifecycle update
  -> proceed, refine, pivot, retire, or conclude
```

Every active track needs a causal signature, predicted pattern, falsifier,
alternative explanation, four outcome routes, belief state, and bounded revision
index. Every ready/running queue row must match the current selection and track
identity and say which decision it can change. Claim the row atomically before
backend launch; a running row locks only its dependencies, mutex, and allocated
resource.

`REMOTE_RUN.json` records runtime truth, canonical result artifacts record numeric
evidence, and `SCIENTIFIC_OUTCOME.json` proposes interpretation. Apply belief or
lifecycle changes only through `scripts/research_decision.py` after identity,
protocol, evaluator, and canonical evidence checks pass. Infrastructure and
implementation failures have no belief effect; protocol-invalid evidence is
quarantined; valid negatives pivot/scope/retire/conclude rather than defaulting to
code repair; positive candidates still require ablation or confirmation.

Keep exactly one paper primary and at most three admitted `alternate` or
`risk_repair` tracks, for at most four active tracks total. Each admitted track
needs its own packets before becoming planning-ready. Non-primary rows are
always `pilot_only`; a positive result records a reselection candidate. It
becomes claim-eligible only after the idea gate explicitly selects it as primary,
advances the selection fingerprint, rematerializes the plan, and reruns it
against the frozen matched baseline.

Operational repairs and scientific revisions have separate budgets. If every
track is terminal and no launchable/live row or mandatory confirmation remains, a
validated terminal program decision may advance to analysis with
`improvement_claim_allowed=false` instead of forcing a positive result.

Read `references/scientific_decision_loop.md` for outcome and transition rules and
`references/experiment_next_actions.md` for acquisition, readiness, and leases.

## Experiment Portfolio

For each selection revision, generate one broad pool of 8-12 lightweight
hypothesis cards, merge candidates with the same causal signature, then perform
one deterministic batch screen to a 3-5 item shortlist. Require distinct
intervention, mechanism, predicted pattern, or discriminating experiment;
module-name or parameter-only variants share a track. Build deep causal,
literature, and experiment packets only for shortlisted candidates. Heartbeats
consume that committed shortlist and regenerate it only after an explicit
lifecycle decision says it is exhausted, invalid, or strategically superseded.

In `full_auto_bounded` paper-producing workflows, WorkflowGuard may create that
lifecycle decision automatically when `portfolio_admission_deficit > 0`, no
current-revision committed candidate is fillable, at least one named program
claim remains unresolved, and evidence/compute/revision budgets remain. This is
local candidate construction and does not require an idle GPU snapshot. It also
covers zero active tracks: first commit exactly one changed-basis
`replenishment_event` through `research_decision.py --replenishment --write`, then
run one bounded targeted replenishment through the current canonical evidence
source. Preserve any selected primary and its selection fingerprint, and change
only shortlist supply state. Bind both `EXPERIMENT_IDEA_POOL.json` and
`IDEA_NOVELTY_VENUE_SCORECARD.json` to the active program revision and contract
SHA. An unchanged program, selection, evidence, and decision basis must reuse the
prior event or rejection rather than regenerate candidates.

Keep three quantities separate: direct user authorization, the active contract's
`max_targeted_replenishments` allocation, and consumed revision-scoped
`replenishment_event` transactions. The default allocation is one and the hard
maximum is eight; neither idle GPUs nor a model may raise it. If an old route is
terminal for its track but explicitly nonterminal for the project, recovery
requires a matching direct-user intervention, unresolved paper decision,
semantic-hash-bound approving review, CAS-committed replacement contract, and an
atomic program-revision activation. Archive the old terminal route before
resetting only the new revision to `unresolved`. Recovery generates one 8-12-card
pool and one 3-5-item shortlist; it must not select a primary, generate track
seeds, admit tracks, create experiment rows, or launch work. If a current-revision
event already exists, materialize its missing supply without consuming another.

Organize paper experiments around two targets: each core mechanism's best
matched performance across target datasets, then the best supported combination.
Run `single_innovation` rows across datasets before deep tuning; a one-dataset
gain stays dataset-scoped. A `combo` row must cite supported component rows and
must not include negative, mismatched, or unsupported components. Avoid
exhaustive power sets. Low-fidelity HPO ranks candidates only; seed is not a
search axis and the total stability budget remains at most three random seeds.

Use two gates in order. First, scientific admission requires a ready row with a
falsifier, outcome routes, protocol/baseline identity, decision targets,
satisfied dependencies, no duplicate, and remaining evidence/seed/compute
budget. Second, resource placement preserves pools that are the only fit for
constrained rows, then assigns work to the smallest fitting live pool. Idle
capacity never creates an experiment.

Maintain a bounded ready frontier from already justified baseline calibration,
up to four active hypothesis tracks, cross-dataset single-mechanism tests,
discriminators/controls, required ablations, bounded asynchronous DEHB scouts,
and paired confirmation seeds. Priorities order fitting work but are not a global
resource barrier. Baseline calibration may overlap with `pilot_only` innovation
scouts; freeze the matched baseline and rerun survivors before claim promotion.
Final confirmation uses the same declared seed set for matched baseline and
proposed runs, may launch its at-most-three seeds concurrently, and reuses
existing baseline anchors.

Use one validation ladder: Stage 0 static/config checks; Stage 1 active-path
smoke or small-batch overfit; Stage 2 first runs
`stage2_parameter_probe` when value coverage is required, freezes the approved
profile, then runs `stage2_method_screen` as the cheapest low-fidelity
paired-dataset single-seed falsifier; Stage 3 primary-dataset full-budget matched
control; Stage 4 remaining required-dataset full-budget legs, independently
launchable after the Stage-2 pair completes;
Stage 5 DEHB only for a supported/ambiguous mechanism with an explicit
sensitivity question; Stage 6 at most three paired seeds; Stage 7 a small
greedy/beam combination of independently supported components. Baseline
calibration is separate `pilot_only` work, not Stage 5. A valid negative retires,
scopes, or pivots; it does not automatically add seeds or tuning.

After committing scientific evidence, run
`scripts/stage_transition_materialize.py --dry-run`, then apply the same queue
revision. The helper may create Stage 3/4 together, one complete Stage-5
dataset-group trial through `autoreskill-run-experiment/scripts/dataset_group_hpo.py`,
or the complete Stage-6 dataset-by-arm matrix. It never infers support from row
existence: Stage 3/4 require a cross-dataset ledger decision, later stages
require terminal-positive rows plus their applied scientific decisions, and
Stage 6 requires an explicit one-to-three-seed preregistration. Grouped HPO has
no optimizer objective until every required dataset leg is valid; finalize only
full-resource, no-regression-passing groups after the registered search is
exhausted, or record an explicit bounded early-stop reason. Stage 3/4 cost must
come from per-dataset runtime estimates or a finite full-budget compute total;
never inherit a low-fidelity Stage-2 estimate silently.

Keep two frontiers separate. `launch_frontier_*` measures dependency-unlocked
row supply. `portfolio_capacity_target=4`, `portfolio_active_track_count`,
`portfolio_admission_deficit`, and `portfolio_fillable_*` measure hypothesis
supply. `method_portfolio_target=2` is a soft demand signal for real
`method_candidate` tracks; diagnostic, baseline, and protocol work cannot satisfy
it or consume hypothesis slots. Select the exact deterministic feasible subset of causally distinct
shortlist candidates, bounded by aggregate budget and the deficit, then admit
and materialize all of it in one recoverable batch. Zero active tracks cannot be
reported as portfolio-satisfied while a fillable shortlist candidate exists.
Both frontiers are planning signals, not permission to synthesize work; idle
GPUs never increase track, seed, HPO, or claim budgets.

Treat GPUs as independent slots. A running row blocks only its dependencies,
mutex group, exclusive resource, shared scheduler limit, or backend/account
capacity. Reconcile stale/terminal rows, refresh resource pools, then run
`experiment_next_actions.py schedule` and atomically claim only its deterministic
assignments. New queues size the batch automatically within useful fitting rows,
idle slots, in-flight slot/GPU-hour budgets, and an absolute fail-safe cap; they
do not take an insertion-order prefix. A pending pool blocks only itself unless
live evidence identifies a shared limit. Record `resource_request`, assigned
pool, `resource_allocation`, dependencies, and mutexes. Detailed schema and
selection rules live in `references/experiment_next_actions.md`.

Use `policy.admission_scope=project` for a single project controller. Use
`admission_scope=global` when several projects share physical GPUs: schedule all
project queues against one fresh normalized snapshot, acquire global then target
project control leases, claim only the first hashed assignment, perform one
backend submit, refresh live resources, and recompute. Advisory assignments
after the first are visibility only.

After assignment and exact preflight, persist submission in three phases:
`planned -> submitting` with a durable intent and backend-searchable trace,
`submitting -> needs_sync` with the backend receipt, then `needs_sync -> running`
or terminal only after authoritative observation. On recovery, search by the
intent identity before retrying; an ambiguous prepared attempt must never be
blindly resubmitted.

### Heartbeat Experiment Opportunity Scan

After reconciliation and before waiting, every experiment heartbeat must apply
completed scientific outcomes, check both frontiers, compute the portfolio
deficit, batch-admit the exact feasible shortlist subset, and materialize every
dependency-unlocked row. Then refresh fitting resources, claim one assignment,
submit through the durable intent/receipt chain when authorized, refresh, and
repeat until no fitting assignment remains or the bounded wake limit is reached.
If the portfolio has an open slot and the current-revision shortlist has no
fillable candidate, dispatch the bounded shortlist-replenishment route above
before waiting, regardless of current GPU availability. Reuse existing evidence
first, perform only targeted incremental discovery for a named evidence gap, and
batch-screen once. The next bounded tick owns selection, track seeds, admission,
packet materialization, resource fitting, and launch.
`one submit before refresh` is a safety boundary, not a one-submit-per-heartbeat
limit. In global mode the project heartbeat stops before claim/submit and leaves
physical admission to the designated global controller. Scanning is mandatory,
submission is conditional: do not tune terminal-negative mechanisms, use seed
as a search axis, repeat unchanged discovery, or invent idle-GPU work. Record the exact
scientific, dependency, capability, budget, or capacity rejection when nothing
can launch. Read
`references/async_wait_policy.md` for the complete resume and priority contract.

## Experiment Launch Modes

For experiment run, submit, monitor, or result-promotion actions, classify
`launch_mode` after the entry loop routes the work and before applying heavy
gates:

- `first_use`: new code export, dataset profile, runtime environment, remote
  account/host, launcher template, loader/protocol boundary, or resource shape;
  missing validation evidence also counts as `first_use`.
- `repeated_variant`: only seed or method hyperparameters change under the same
  manifest-backed code export, dataset profile, runtime environment, and launcher
  template and resource shape.
- `monitor_only`: status, queue, log, metric, or terminal-result sync with no new
  submit.
- `claim_promotion`: using results to support paper text, abstract/table numbers,
  conclusions, review readiness, or submission readiness.

`repeated_variant` must not trigger unrelated paper-readiness gates, broad
cross-project sync, full dataset/env/code audits, or human wiki/status rewrites
before launch. Its immediate artifact is the machine-readable run/submit
manifest or trace. Batch human summaries to first metric, failure, terminal
state, or explicit user request.

The repeated-variant decision needs explicit identity evidence, not inference
from prose. Accept either a `launch_identity` object or equivalent run/trace
fields covering code export ref/hash, dataset profile and manifest ref/hash,
runtime environment ref/probe, launcher template hash, resource shape, and
method/data-backend profile. Exclude the intentionally varied seed and
hyperparameters from the stable identity hash. If these fields are missing,
treat the launch as `first_use` or append the missing machine-readable identity
fields before reusing prior validation.

This launch-mode scoping does not relax live submit safety. For BJTU HPC and
other remote backends, delegate queue state, resource shape, exact-script
preflight, submission, and post-submit verification to the backend skill. Run
claim/evidence gates only in `claim_promotion` or the relevant analysis/review
stage, not as a prerequisite for every repeated launch.

## Experiment Next Actions

When the user asks what experiment to do next, asks to organize active
experiment threads, or asks for a wiki experiment-status table, read
`references/experiment_next_actions.md`.

Use `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json` as the durable planning
queue. It can point to project-specific plans and monitor artifacts, but it does
not replace stage contracts, launch safety, or claim promotion gates. Render
wiki dashboards from the queue; do not treat wiki prose as the planning
authority when JSON exists.

Default wiki dashboards are configurable through `AUTORESEARCH_WIKI_ROOT` and
otherwise land under `$HOME/Documents/001-WIKI/mypaper/<direction>/...`.
Before creating or moving any human-facing Wiki artifact, read
`references/wiki_projection_and_naming.md`. Use one canonical
`AutoResearch-<project-slug>/` hub per project, keep cross-project material
under `autoresearch/00-实验总控/`, and isolate all test/fixture rendering from the
live Wiki root.
Update the queue only when observations change the next action: terminal
result, first usable metric, failure/blocker, user-goal change, or explicit
queue maintenance. Do not rewrite dashboards on every heartbeat.

## Global Route Audit

When the user explicitly asks for a one-time audit of current research status,
cross-project priorities, or what to do next, dispatch
`$autoreskill-global-route-audit`. It reads project authorities, ranks a global
decision-bearing action portfolio, and can save a dated Wiki report. It is a
read-only cross-stage advisory operation: do not run the entry loop or tick,
mutate queues/lifecycles, launch jobs, or create a heartbeat as part of the
audit. If execution is also requested, finish the audit first and then resume
this workflow from the selected project-local authority.

## Remote Layout

Use stable, neutral project slugs. A `<project_slug>` must not contain account
aliases, usernames, emails, real person names, or credential labels.

Generic SSH/GPU layout:

```text
~/autoresearch_projs/<project_slug>/
  code/
  runs/
  logs/
  outputs/
  checkpoints/
  artifacts/
  manifests/
  datasets/
  tmp/
```

BJTU HPC layout:

```text
/data/home/<account>/projects/<project_slug>/
  code/
  runs/
  logs/
  outputs/
  checkpoints/
  artifacts/
  manifests/
  tmp/

/data/home/<account>/dataset_raw/<dataset_name>/
/data/home/<account>/dataset_archives/<dataset_name>.tar
/data/home/<account>/dataset_archives/<dataset_name>.sha256
/data/home/<account>/dataset_archives/<dataset_name>.manifest.json
/data/home/<account>/dataset_packed/<dataset_name>/<experiment_profile>/
/data/home/<account>/dataset_uploads/<dataset_name>/
/dev/shm/bjtu_dataset_cache/<dataset_name>/
```

Keep code, datasets, run directories, logs, outputs, checkpoints, manifests,
artifacts, and temporary files separate. Store audit-ready summaries and small
metrics under `artifacts/` or `manifests/`; keep datasets, raw logs, secrets,
checkpoints, and model weights out of Git. Start live SSH/HPC/GPU work
read-only unless the user explicitly asks to mutate remote state.

For BJTU live mutation, scheduling, packed datasets, `/dev/shm`, Slurm naming,
resource shapes, pending diagnosis, or submit safety, read `$bjtu-hpc` and the
references listed below before acting.

## Workflow Modes

Default experiment workflow:

```text
init -> topic_search -> graph_build -> frontier_mapping -> literature_review -> ideation -> idea_gate -> experiment_plan -> code -> experiment -> analysis -> review_pressure -> writing -> submission_ready
```

When the user explicitly requests a non-PaperNexus external-material idea
campaign, dispatch `$autoreskill-gpu-idea-validation` to construct and
materialize that evidence route before canonical ideation. Then return to
`$autoreskill-ideation-panel`, `$autoreskill-experiment-plan`,
`$autoreskill-implement-experiment`, and `$autoreskill-run-experiment` for their
normal authorities. A missing `evidence_source_mode` remains the legacy
PaperNexus route; never infer or relabel the external route from absent fields.

Standalone paper-code transfer:

- Read `references/paper_code_innovation_transfer.md`.
- Preserve raw candidates, repository static evidence, mechanism analysis, and
  reviewed migration decisions separately.
- Run `scripts/paper_code_transfer_lint.py --project <project-root> --required`
  when the survey is the requested deliverable.

Standalone CCF-A/top-tier writing-style corpus:

- Read `references/ccfa_writing_style_corpus_audit.md`.
- If producing reusable advice, also read `references/ccfa_writing_principles.md`.
- If revising a concrete manuscript, also read
  `references/ccfa_manuscript_revision_workflow.md`.
- Run `scripts/writing_style_corpus_lint.py --project <project-root> --required`
  when the corpus audit is the requested deliverable.

Manuscript writing or polishing:

- Revise the paper argument before sentence polish.
- Read `references/ccfa_writing_principles.md` and, for concrete manuscripts,
  `references/ccfa_manuscript_revision_workflow.md`.
- Produce `.autoreskill/paper/CCFA_WRITING_AUDIT.md`.

## Reference Routing

Read references only as needed:

- `references/command_surface.md`: deterministic script commands.
- `references/experiment_next_actions.md`: active experiment next-action queue,
  configurable wiki dashboards, and active-thread-to-queue guidance.
- `references/scientific_decision_loop.md`: per-run scientific outcomes, belief
  transitions, separate repair budgets, and terminal non-positive completion.
- `references/goal_state_schema.md`: control-plane fields and scope defaults.
- `references/stage_contracts.md`: stage authorities and completion contracts.
- `references/stage_skill_matrix.md`: child skill routing and write scopes.
- `references/literature_discovery_triggers.md`: PaperNexus discovery triggers.
- `references/async_wait_policy.md`: heartbeat and async wait policy.
- `references/minimal_harness_hardening_contract.md`: cross-stage audit fields
  and pruning rule for new gates.
- `references/paper_integrity_forensics_contract.md`: final manuscript
  numeric/statistical/residue checks and zero-weight AIS policy.
- `references/innovation_story_contract.md`: user-facing innovation storyline.
- `references/paper_code_innovation_transfer.md`: paper-code surveys and transfer.
- `references/ccfa_writing_style_corpus_audit.md`: writing-style corpus audits.
- `references/ccfa_writing_principles.md`: reusable top-tier writing standards.
- `references/ccfa_manuscript_revision_workflow.md`: concrete manuscript audit and
  revision sequence.
- `references/ccfa_writing_polish.md`: backward-compatible router.
- `references/job_execution_packet_schema.md`: dispatch/update and runtime
  observation protocol.
- `references/handoff_packet_schema.md`: role handoff packet shape.
- `references/role_roster.md`: role write ownership.
- `references/source_traceability.md`: multi-experiment audit and
  OpenClaw-to-portable traceability note.
- For DEHB/HPO experiment planning, read
  `$autoreskill-experiment-plan/references/resource_constrained_dehb_policy.md`.
- For BJTU HPC auth, remote paths, datasets, uploads, `/dev/shm` staging,
  Slurm names, running-only scheduling, resource shapes, pending diagnosis, and
  submission safety, use `$bjtu-hpc` plus relevant references:
  `references/anonymization.md`, `references/data_transfer.md`,
  `references/data_backend.md`, `references/gpu_scheduling.md`,
  `references/job_inspection.md`, `references/guardrails.md`, and
  `references/hpc_workflow.md`.

## Tick Protocol

`scripts/goal.py tick` is deterministic and single-action. It does not execute
live PaperNexus calls or experiments; it advances completed stages, dispatches
due repair/async jobs, or writes the next repair/handoff/job packet.

Parent Codex turns may run multiple deterministic ticks inside the bounded loop.
Due repair packets and locally actionable contract blockers take precedence over
due async rows. Dispatch async only when the current contract still classifies
the same allowed external wait as the blocker.

After every Analyzer pass, add `post_analysis_self_audit` to
`analyzer/IDEA_OUTCOME_SUMMARY.json`:

- `least_confident_point`
- `largest_possible_misunderstanding`

This self-audit guards against false closure, missed blockers, stale monitor
cleanup, baseline-source confusion, and over-reading diagnostic evidence. It
does not justify stronger claims.

## Harness Pruning Rule

Before adding or promoting any gate, artifact, heartbeat, queue, or prompt
block, answer:

1. Does it own a state transition no existing authority owns?
2. Does it improve recovery after interruption, failed runs, or role handoff?
3. Does it block a known expensive failure that existing lints miss?

If not, keep it as optional guidance, a rubric row, or a trace note. Do not add a
parallel queue, second contract schema, or duplicate stage authority.

## Stall Diagnostics

When a workflow appears stuck, answer:

- Current stage, owner, next action, and blocker from `goal_state.json`.
- Repair/async job state: pending, running, stale, failed, retry, or waiting.
- Whether `contract_lint.py` says the current stage is complete.
- Where `LOOP_TRACE.jsonl` or evaluator findings show the first route divergence.
- Whether the blocker is completion, owner routing, job delivery, runtime replay,
  projection drift, goal-scope mismatch, repeated stable polling, or context
  decay.
- Whether policy allows repair, downgrade, rollback, or requires hard stop.

Do not convert missing artifacts into completion by projection.
