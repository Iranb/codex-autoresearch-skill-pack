---
name: autoreskill-workflow
description: Main $autoreskill and /goal workflow conductor for the portable AutoResearch + PaperNexus skill pack. Use when the user invokes $autoreskill, autoreskill, /goal, asks Codex to initialize, resume, advance, debug, or fully drive a .autoreskill research workflow, dispatch role/job packets, check stage completion, recover stalled workflow state, run bounded full-auto research without OpenClaw, run resource-constrained DEHB/HPO experiment planning, run paper/code survey workflows, run CCF-A/top-tier writing-style audits, explain CCF-A writing principles, apply those principles to manuscript writing/polishing through a required writing audit, or run manuscript paper-integrity forensics before writing/submission readiness.
---

# AutoResearch Workflow

This is the portable AutoResearch + PaperNexus conductor. It must run without
`openclaw-research`, `.openclaw-research/`, `PROJECT_MANIFEST.json`, or
`research_workflow` tools.

## Kernel Invariants

- Treat `.autoreskill/goal_state.json` as the stage, owner, action, and scope
  control plane. It is not semantic proof.
- Treat stage completion as contract-driven. Run `scripts/contract_lint.py`
  before advancing a stage.
- WorkflowGuard is the only component that advances stages. Child skills satisfy
  job packets and write authority artifacts only.
- Read `.autoreskill/autopilot_policy.json` before deciding whether to repair,
  degrade, wait, rollback, or hard-stop.
- Keep child roles isolated through `.autoreskill/job_packets/` and, when useful,
  `.autoreskill/handoffs/`.
- Keep repair, async, and pending execution state in the existing job system:
  `.autoreskill/repair_queue.jsonl`, `.autoreskill/async_jobs.jsonl`, and
  `.autoreskill/job_packets/` snapshots/prompts. Do not add
  `.autoreskill/pending_actions/` or another parallel queue.
- New `goal_tick.py` job packets carry a local `acceptance_contract` so "done"
  is testable before the role starts. Keep legacy or external packets that only
  use `acceptance_criteria` valid.
- Use isolated Evaluator packets before in-scope high-risk transitions when the
  producing role should not grade its own work.
- Treat `.autoreskill/LOOP_TRACE.jsonl` as append-only recovery evidence for
  loop decisions, lint failures, evaluator blocks, repairs, and restarts. It is
  not a stage authority.
- For async polls or repeated tool actions, record compact action/result
  signatures and progress markers in the job packet or loop trace. A repeated
  poll with changing observed progress is not a stall; unchanged
  action/result/progress is stale evidence.
- PaperNexus live graph work must use the configured `papernexus-remote` MCP. Do
  not replace it with local PaperNexus CLI, raw HTTP, local graph files, local
  MCP, or SSH graph commands.
- Source-code evidence is not effectiveness evidence. Repository analysis can
  support feasibility, active-code-path, implementation affordance, and
  mechanism-transfer claims; performance claims require matched experiment
  artifacts under the normal `code`/`experiment`/`analysis` contracts.
- Paper-reported baseline metrics are the primary numerical authority whenever a
  paper-backed baseline exists or the project enables
  `analysis_requires_paper_report_baseline_lint`.
- Always distinguish paper-reported baseline numbers from local, remote, or HPC
  reproduced baseline numbers. Do not describe a method as improving over "the
  baseline" unless the comparison source is explicit: use "vs paper report" only
  for exact paper-reported values; use "vs reproduced baseline" for local/remote
  reproduction; and use "vs matched reproduced baseline" only when host,
  dataset/protocol, split, backbone/checkpoint, seed, metric definition, and
  stage are matched.
- A positive delta against a reproduced baseline is not paper-report alignment.
  Treat baseline reproduction versus the paper report as a separate evidence
  lane from method improvement versus the reproduced baseline. If paper-report
  values are unavailable or not protocol-aligned, write "paper-report comparison
  not established" instead of implying it. Strong manuscript claims require both
  clear method-vs-reproduced-baseline evidence and clear baseline-vs-paper-report
  alignment evidence, unless claim limits explicitly downgrade the scope.
- Experiment selection for paper-producing workflows must be driven by current
  manuscript progress rather than GPU utilization, candidate-list breadth, or raw
  positive-count maximization. Before preparing, dispatching, or submitting an
  experiment, identify the exact manuscript gap it can close: paper-report
  baseline alignment, method-vs-matched-reproduced-baseline evidence,
  ablation/mechanism attribution, cross-dataset or multi-seed robustness,
  negative-boundary/limitation evidence, or instrumentation/data-loader/protocol
  correctness.
- Prioritize paper-producing experiments in manuscript order: first paper-report
  baseline reproduction/audit; second the current strongest paper-route method
  against matched reproduced baselines; third minimal ablations needed for the
  paper story; fourth targeted cross-dataset or multi-seed validation that tests
  the current claim boundary; and only then new innovation-point candidates that
  answer a manuscript-critical weakness. Do not expand parked ideas, CUB
  combination search, or broad validation queues merely because they are
  available.
- Every experiment plan or job packet for a paper-producing workflow must state
  the expected paper table, figure, claim, ablation, or limitation section it
  could affect. If an experiment cannot change a manuscript claim, table,
  ablation, or limitation, do not run it as an effectiveness-evidence job.
- Final manuscript integrity forensics are required for strong top-tier paper
  claims before `writing` or `submission_ready` can pass. The gate checks
  manuscript-level numeric/statistical self-consistency, exact presentation
  residue, and zero-weight AIS style impressions; it is not an AI-authorship or
  misconduct detector.
- Random-seed stability validation is capped at three experiment seeds. This is
  separate from `IDEA_TRACK_SEEDS`, which are idea/track candidates rather than
  random seeds.
- Parameter search must use the resource-constrained DEHB policy when it is a
  launchable `PARAM` mechanism: seed is never a search axis, low-fidelity scouts
  are pilot/search evidence only, and at most the top 1-2 full-resource survivors
  may enter ablation or confirmation. Linear/grid tuning is not a launch plan.
- Remote, SSH, GPU, and HPC work must follow the Remote And HPC Layout Policy
  below. Keep project code, datasets, runs, logs, outputs, checkpoints,
  manifests, artifacts, and temporary files in separate stable directories.

## Applicability Scope

Every new or resumed workflow must classify the goal before applying heavy gates.
Record the classification in `goal_state.json` or `autopilot_policy.json`.

`goal_type`:

- `paper_producing_top_tier`: default for research-paper goals that target a top
  conference or journal.
- `paper_producing_light`: paper draft or pilot manuscript work with explicit
  reduced evidence expectations.
- `standalone_survey`: paper-code survey, literature survey, or writing-style
  corpus audit without manuscript claims.
- `writing_style_corpus`: CCF-A/top-tier writing evidence collection only.
- `diagnostic_or_resource`: environment diagnosis, data/GPU/resource checks, or
  non-paper operations.

`claim_mode`:

- `strong_paper_claims`: default for `paper_producing_top_tier`.
- `pilot_evidence`: useful evidence, but no stable paper claim unless upgraded.
- `survey_only`: survey findings only.
- `writing_guidance_only`: style and revision guidance only.
- `diagnostic_only`: operational diagnosis only.

Only `paper_producing_top_tier` with `strong_paper_claims` should receive the full
paper-readiness contract. Other modes must keep provenance and claim limits, but
must not be blocked by unrelated paper-submission gates. When a strong-paper gate
is skipped as out of scope, record explicit `claim_limits` or
`out_of_scope_claim_limits` so the lint result can distinguish "not applicable"
from "missing evidence".

## Remote And HPC Layout Policy

Use stable, neutral project slugs and keep remote project work separate from
dataset source-of-truth roots. A `<project_slug>` must not contain saved account
aliases, cluster usernames, portal usernames, emails, real person names, or
credential labels. Prefer lower-ASCII slugs with letters, digits, `-`, `_`, or
`.`. Preserve legacy project roots when resuming existing work, but do not create
new legacy or framework-specific remote roots.

Generic SSH/GPU servers:

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

- Put repository checkouts, editable experiment code, and launch scripts under
  `code/`.
- Put per-run working directories under `runs/<run_or_trace_id>/`; use
  `logs/`, `outputs/`, and `checkpoints/` for the corresponding streams and
  artifacts rather than writing them under `code/`.
- Put audit-ready summaries, small metrics, claim/evidence exports, and reports
  under `artifacts/` or `manifests/`; keep large checkpoints, datasets, raw logs,
  secrets, and model weights out of Git.
- Use `datasets/` for symlinks, dataset manifests, or small local debug data.
  Do not copy large datasets there when a stable shared dataset root or packed
  dataset can be referenced safely.
- Use `tmp/` only for bounded scratch files. Do not create new AutoResearch
  workspaces under `/tmp`, dataset roots, old ad hoc experiment folders, or
  unrelated project directories.

BJTU HPC accounts use the `$bjtu-hpc` layout as the stricter authority:

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

/data/home/<account>/dataset_raw/<dataset_name>/                    # conversion source
/data/home/<account>/dataset_archives/<dataset_name>.tar
/data/home/<account>/dataset_archives/<dataset_name>.sha256
/data/home/<account>/dataset_archives/<dataset_name>.manifest.json
/data/home/<account>/dataset_packed/<dataset_name>/<experiment_profile>/
/data/home/<account>/dataset_uploads/<dataset_name>/                # resumable upload scratch
/dev/shm/bjtu_dataset_cache/<dataset_name>/                         # node-local disposable cache
```

- For evidence-producing training, prefer account-local archives and reusable
  packed datasets with `DATA_BACKEND=lmdb`, `DATA_BACKEND=hdf5`, or
  `DATA_BACKEND=tfrecord`. A packed dataset is usable only after it has a
  manifest, split separation, validation report, and smoke-test evidence
  required by `$bjtu-hpc`.
- Keep persistent dataset roots named by stable dataset/profile identifiers such
  as `<dataset_family>_<split_or_source>_<version>` and
  `<experiment_profile>`. Never name source-of-truth datasets after a Slurm job
  id, trace hash, user-task token, account alias, or one-off run.
- Use `/dev/shm/bjtu_dataset_cache/<dataset_name>/` only as a reusable
  node-local cache for validated packed inputs. Never place checkpoints, model
  weights, final outputs, raw logs, secrets, private ledgers, or source-of-truth
  datasets in `/dev/shm`.
- Slurm-visible job names, queue keywords, run/log/output basenames, and
  Git-safe evidence filenames for BJTU evidence runs must use an anonymous trace
  id such as `hpc_<12-16hex>`. Keep the reversible account-to-trace mapping only
  in a private ledger with restrictive permissions.
- Remote launch packets or manifests must record the remote project root, code
  root, run/log/output/checkpoint roots, dataset root, dataset backend, and
  whether the dataset is raw debug, packed persistent data, or node-local cache.
- Start live SSH/HPC/GPU work read-only unless the user explicitly asks to
  submit, cancel, delete, reserve, chmod/setfacl, or otherwise mutate remote
  state. Do not migrate or delete legacy remote files without explicit approval
  when data loss or queue disruption is possible.

## Entry And Resume Loop

On every `$autoreskill`, `autoreskill`, or `/goal` entry:

1. Resolve `<project-root>` and `<skill-root>`.
2. Run `scripts/ensure_project_agents.py --project <project-root>`.
3. Run `scripts/goal.py status --project <project-root>`.
4. Reconcile stale jobs with `scripts/goal.py reconcile --project <project-root>
   --stale-minutes 60`.
5. Run `scripts/goal.py tick --project <project-root>`.
6. If the tick output is `dispatch_repair` or `dispatch_async_poll`, execute the
   rendered packet through the routed child skill. Do not infer async dispatch
   from a due async row alone; async packets are executable only when `tick`
   returns `dispatch_async_poll`.
7. Write/update artifacts, run relevant lint, update the job packet, rely on the
   workflow scripts to append concise loop-trace entries for state/job decisions,
   and add manual trace entries for external evaluator blocks or restarts when
   needed. Tick again while local work remains actionable and budget allows.

Use a bounded continuation loop for `full_auto_bounded`: default to 5 tick/job
actions or about 10 minutes of active work. Stop on terminal completion,
`hard_stop`, user/budget/credential gate, loop budget exhaustion, or one of the
allowed external async waits.

Deleting, archiving, or updating a stale heartbeat is cleanup, not a workflow
stop condition. After any managed heartbeat is deleted because its external wait
is terminal, superseded, or locally actionable, immediately run the normal
successor check (`status`, `reconcile`, then `tick`) and continue the bounded
loop while a local repair, analysis, planning, launch, rollback, or stage
transition remains actionable. Only stop after recording an explicit terminal
completion, allowed external wait, safety/user/budget/credential gate, or loop
budget exhaustion.

## Loop Harness Policy

Apply LOOP.md-style harness ideas through the existing AutoResearch loop rather
than by adding a second controller.

- Contract first: for substantial repair, planning, experiment, analysis, review,
  or writing jobs, use the generated `acceptance_contract` in the job packet as
  the executable done-definition: required outputs, commands to pass, forbidden
  violations, claim boundaries, and optional evaluator commands. Map functional,
  counterexample, scope, evidence, and subjective assertions onto these existing
  fields instead of creating a second contract schema.
- Role separation: keep Producer and Evaluator outputs separate. Evaluator
  packets may write findings under `.autoreskill/evaluator/` or reviewer-owned
  locations, but they do not advance stages by themselves.
- Critical transitions: for top-tier paper-producing workflows, use an isolated
  Evaluator packet before
  `experiment_plan -> code`, `experiment -> analysis`, `analysis -> writing`, and
  `writing -> submission_ready` unless out-of-scope claim limits explicitly
  downgrade the gate.
- Disk state over context: state saves, job dispatch, job update, actual
  stale-job reconcile changes, and sub-agent result recording append compact facts to
  `.autoreskill/LOOP_TRACE.jsonl`; use manual trace entries for external
  evaluator findings or restart decisions that occur outside those scripts.
- Single job-state surface: use `.autoreskill/repair_queue.jsonl` and
  `.autoreskill/async_jobs.jsonl` as the authoritative queues, with
  `.autoreskill/job_packets/` as executable packet/snapshot storage. Extend the
  existing schema when a new pending state is needed; do not create parallel
  pending-action directories.
- Result-aware waits: for repeated async polls, compare action signature, result
  signature, and progress marker before declaring a stall or scheduling another
  heartbeat.
- Clean restart: after repeated same-cause failures, retire or rebuild the
  branch, track, or idea and preserve negative evidence. Do not keep patching the
  same failed route, and never delete project evidence to "restart".
- Subjective quality: when ideation, story, review, Figure 1, or writing quality
  affects acceptance, use a small evidence-routed rubric with axis, weight,
  score, evidence ref, reviewer gap, and required repair.
- Harness pruning: do not add permanent gates unless they own a transition,
  improve recovery, or block a known expensive failure. Remove or downgrade gates
  that duplicate another authority or mainly create noise.

## Async Waits

Codex thread heartbeats are allowed only for:

- PaperNexus literature discovery waits.
- PaperNexus graph import or authoritative-sync waits.
- Experiment runtime or resource waits.

Do not create heartbeats for stage transitions, ready repair jobs, local lint,
planning, writing, review, or any state where the parent agent can keep moving
locally. Do not use shell sleep loops for long external waits. Read
`references/async_wait_policy.md` for adaptive heartbeat, result-aware
polling, and stale-poll rules.

`scripts/goal.py tick` must revalidate every due async row against the current
stage and the live artifact state before dispatch. A due async row is not enough
to prove the workflow is externally blocked. If a local repair, contract
transition, capture step, stale-job reconciliation, or rollback/degrade route is
actionable, local routing wins and no heartbeat is created or continued. Stale
literature-discovery, graph/import-sync, and experiment-runtime async rows must
be marked `superseded` with a decision-log reason before local routing resumes.

## Workflow Modes

Default experiment workflow:

```text
init -> topic_search -> graph_build -> frontier_mapping -> literature_review -> ideation -> idea_gate -> experiment_plan -> code -> experiment -> analysis -> review_pressure -> writing -> submission_ready
```

Standalone paper-code transfer mode:

- Read `references/paper_code_innovation_transfer.md`.
- Preserve raw candidates, repository static evidence, source-code mechanism
  analysis, and reviewed migration decisions separately.
- Run `scripts/paper_code_transfer_lint.py --project <project-root> --required`
  when the standalone survey is the requested deliverable.

Standalone CCF-A/top-tier writing-style corpus mode:

- Read `references/ccfa_writing_style_corpus_audit.md`.
- If producing reusable advice, also read `references/ccfa_writing_principles.md`.
- If revising a concrete manuscript, also read
  `references/ccfa_manuscript_revision_workflow.md`.
- Run `scripts/writing_style_corpus_lint.py --project <project-root> --required`
  when the corpus audit is the requested deliverable.

Manuscript writing or polishing mode:

- Revise the paper argument before sentence polish.
- Read `references/ccfa_writing_principles.md` and
  `references/ccfa_manuscript_revision_workflow.md`.
- Produce `.autoreskill/paper/CCFA_WRITING_AUDIT.md`.
- Apply the non-defensive writing pass described in the manuscript and principles
  references before final English polish.

## Stage And Evidence Contracts

Use `references/stage_contracts.md` as the detailed authority for stage
completion. Use `references/minimal_harness_hardening_contract.md` for the
small set of cross-stage fields added from the 2026 AutoResearch audit:

- bounded search and negative-knowledge consultation in `TRACK_PLAN_MATRIX`;
- `selection_fingerprint` or `selected_primary_ref` from idea_gate through
  downstream packets and active track rows;
- failure diagnosis in negative experiment ledger rows;
- disaggregated/mechanism/transfer/numeric checks in `SCORE_VERIFICATION`;
- evidence refs, mechanism status, claim permission, and negative-knowledge
  summary in `IDEA_OUTCOME_SUMMARY`;
- review axes for claim drift, scientific alignment, and defensive underclaim;
- writing verification for claim drift, scientific alignment, numeric grounding,
  and non-defensive wording, including preserved necessary limitations, blocked
  unsupported claim upgrades, and top-tier reviewer claim posture in front matter.
- manuscript forensics for final-paper numeric/statistical consistency, exact
  residue checks, duplicate-table warnings, and zero-weight AIS style impressions
  before `writing` and `submission_ready`.
- resource-constrained DEHB/HPO planning for `PARAM` mechanisms through
  `hpo_search_policy`, with seed excluded from search and low-fidelity scouts
  excluded from promotion.

Run baseline-report alignment before `experiment_plan`, `code`, `experiment`,
`analysis`, `review_pressure`, `writing`, or `submission_ready` can support
paper claims when the project policy enables it:

```bash
python <skill-root>/scripts/baseline_report_alignment_lint.py --project <project-root> --stage <stage>
```

Run final manuscript forensics before strong-paper `writing` or
`submission_ready` can pass. This is a numeric/statistical/residue integrity
gate, not AI-authorship detection:

```bash
python <skill-root>/scripts/paper_forensics_lint.py --project <project-root> --stage <stage>
```

## Reference Routing

Read references only as needed:

- `references/command_surface.md`: deterministic script commands.
- `references/goal_state_schema.md`: control-plane fields and scope defaults.
- `references/stage_contracts.md`: stage authorities and completion contracts.
- `references/stage_skill_matrix.md`: child skill routing and write scopes.
- `references/literature_discovery_triggers.md`: PaperNexus discovery triggers.
- `references/async_wait_policy.md`: heartbeat and async wait policy.
- `references/minimal_harness_hardening_contract.md`: added minimal audit fields.
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
- For BJTU HPC remote paths, datasets, uploads, `/dev/shm` staging, Slurm
  names, and submission safety, use `$bjtu-hpc` plus its
  `references/data_transfer.md`, `references/data_backend.md`, and
  `references/guardrails.md`.

## Tick Protocol

`scripts/goal.py tick` is deterministic and single-action. It does not execute
live PaperNexus calls or experiments by itself; it advances completed stages,
dispatches due repair/async jobs, or writes the next repair/handoff/job packet.

Parent Codex turns may run multiple deterministic ticks inside the bounded
continuation loop. After `advanced`, continue immediately while budget remains.
After `dispatch_repair` or `dispatch_async_poll`, execute the rendered packet
through the routed child skill, update the job, and tick again. Stop only when
the next action is not locally actionable or an allowed external wait is reached.
Due repair packets and locally actionable contract blockers take precedence over
due async rows. Dispatch async only when the current contract still classifies
the same allowed external wait as the blocker.

Before sending a final response, apply a pre-stop guard: if the current contract
is incomplete and `goal.py status`, `goal.py tick`, a due job packet, or
`contract_lint.py` exposes a concrete local next action, continue one bounded
tick/job cycle or record the explicit external wait, budget/user gate, or
hard-stop. Do not end with a prose summary just because the model has no tool
call to make.

After every Analyzer pass, add a short post-analysis self-audit to
`analyzer/IDEA_OUTCOME_SUMMARY.json` under `post_analysis_self_audit`:

- `least_confident_point`: answer "For the current conclusion, where am I least
  confident, and what evidence would change it?"
- `largest_possible_misunderstanding`: answer "What is the biggest possible
  misunderstanding of the overall situation, and what have I not noticed?"

This self-audit does not justify stronger claims. It is a guard against false
closure, missed blockers, stale monitor cleanup, baseline-source confusion, and
over-reading diagnostic evidence.

## Stall Diagnostics

When a workflow appears stuck, explicitly answer:

- Current stage, owner, next action, and blocking reason from `goal_state.json`.
- Whether a repair or async job is pending, running, stale, failed, or waiting
  for retry.
- Whether `contract_lint.py` says the current stage is complete.
- Whether `.autoreskill/LOOP_TRACE.jsonl` or evaluator findings show the first
  decision point where the loop diverged from the intended route.
- Whether the blocker is canonical completion, owner routing, handoff/job
  delivery, runtime replay, projection drift, or goal-scope mismatch.
- Whether the trace disease is goal drift, self-evaluation inflation, tool-error
  blindness, context decay, over-patching, weak stop condition, or result-stable
  repeated polling.
- Whether policy allows repair/degrade/rollback, or requires a hard stop.

Do not convert missing artifacts into "complete" by projection. Use repair,
degradation, rollback, or hard stop.
