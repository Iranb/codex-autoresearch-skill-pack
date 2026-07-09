---
name: autoreskill-workflow
description: Main $autoreskill and /goal workflow conductor for portable AutoResearch + PaperNexus. Use when initializing, resuming, advancing, debugging, or fully driving a .autoreskill workflow; dispatching role/job packets; checking stage completion; recovering stalled state; running bounded full-auto research; or routing paper-code survey, DEHB/HPO planning, writing audit/polish, manuscript integrity, and remote/HPC experiment workflows.
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
- Handoffs: `.autoreskill/handoffs/` and
  `references/handoff_packet_schema.md`.
- Recovery trace: `.autoreskill/LOOP_TRACE.jsonl`; trace entries explain route
  decisions but never complete a stage.
- PaperNexus graph work: configured `papernexus-remote` MCP plus captured
  artifacts. Do not replace live graph work with local PaperNexus CLI, raw HTTP,
  local graph files, local MCP, or SSH graph commands.
- Remote/HPC work: this skill owns portable project layout; `$bjtu-hpc` owns
  BJTU auth, live queue state, helper defaults, resource scheduling, dataset
  packing, and submit safety.

## Entry Loop

On every `$autoreskill`, `autoreskill`, or `/goal` entry:

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
external async wait.

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
