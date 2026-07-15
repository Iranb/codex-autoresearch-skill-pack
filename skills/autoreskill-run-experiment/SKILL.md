---
name: autoreskill-run-experiment
description: Run and monitor portable AutoResearch experiments. Use to launch local, SSH, AutoDL, BJTU HPC, or other backend runs under autopilot policy, record REMOTE_RUN.json, reconcile ledgers, monitor logs, execute resource-constrained DEHB/HPO trials, and prevent metric/dataset/baseline drift.
metadata:
  short-description: Launch and reconcile experiments
---

# Run Experiment

Use after implementation dry-run passes and policy allows launch.

## Record

Write:

```text
.autoreskill/coder/experiments/<track-id>/<experiment-id>/REMOTE_RUN.json
.autoreskill/coder/experiments/<track-id>/<experiment-id>/SCIENTIFIC_OUTCOME.json
.autoreskill/coder/EXPERIMENT_INDEX.md
.autoreskill/coder/TRACK_RANKING.json
.autoreskill/experiment/EXPERIMENT_MONITOR_PLAN.json
```

## Rules

- Check resource budget before launch.
- Record exact command, environment, commit/diff, remote path, session id.
- Treat running experiments as resource-scoped locks, not a global launch lock.
  Before waiting, read `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json`,
  reconcile terminal/stale rows, refresh live GPU/HPC resource pools, run
  `experiment_next_actions.py schedule`, and launch only its deterministic
  assignments. A missing/stale snapshot requests refresh; it does not authorize
  a claim or launch.
- Every experiment-monitor heartbeat must also run the workflow heartbeat
  opportunity scan before scheduling its next wait: apply completed outcomes,
  run both frontiers, compute `portfolio_admission_deficit`, batch-admit the exact
  feasible causally distinct shortlist subset, materialize all unlocked rows,
  and inspect only eligible baseline-calibration/DEHB contracts. A
  project-specific explicit monitor prompt may add constraints but must not
  remove this scan. Locally actionable planning/implementation continues in the
  current bounded loop instead of being deferred to another heartbeat.
- When a fresh capability-known snapshot has idle slots but the positive
  portfolio deficit has no fillable committed candidate, route WorkflowGuard's
  bounded `replenish_experiment_portfolio` action before waiting. The runtime
  monitor must not generate ideas itself: the workflow preserves the current
  primary identity, performs evidence-backed targeted replenishment once per
  changed fingerprint, returns minimum `pilot_only` packets to the queue, and
  only then resumes normal scheduling. Capacity triggers the scan, not admission.
- Before any backend launch, atomically claim the queue row through
  `autoreskill-workflow/scripts/experiment_next_actions.py claim` or
  `claim-assignment`. Only the live row-lease owner may launch. Lease expiry
  requires backend reconciliation and never proves that a remote run stopped.
- Require the row's current project-passport index and execution-profile hash to
  match a verified, unexpired resource-capability passport entry for the chosen
  pool. Capability proof does not replace a fresh queue/GPU snapshot or the
  route-specific launch preflight; a failed preflight invalidates only the
  implicated capability components and activates their bounded negative cache.
- After exact preflight, call `prepare-backend-submit` before the physical side
  effect so the row durably enters `submitting` with a backend-searchable trace.
  Record the native receipt immediately with `record-backend-submit` to enter
  `needs_sync`, then use only authoritative backend observation to enter
  `running` or terminal. On recovery, search by the prepared trace before retry;
  a missing receipt or expired lease never authorizes resubmission. Use
  `abort-backend-submit` only with explicit evidence that no live run exists.
- Respect queue `admission_scope`. In `project` mode, the project controller may
  claim its deterministic assignment. In `global` mode, only the global
  admission controller may pass the current schedule hash, first assignment
  hash, shared-snapshot hash, and live global/project control leases to
  `claim-assignment`. Advisory assignments after the first are not launchable;
  refresh and reschedule after every physical start or submit.
- The project scientific controller owns packet/matrix/queue mutations, the
  global admission controller owns cross-project physical placement, and the
  project runtime monitor owns observation/reconciliation. A global-mode monitor
  may surface ready rows but must not claim or submit them. Use one monitor per
  project, never one per track or seed.
- When experiment code is managed through a GitHub private repository, launch only from the recorded branch/commit or an explicitly recorded dirty patch. Before launch, record repo URL, privacy, branch, commit SHA, remote checkout path, and local export path in `REMOTE_RUN.json.source_state` and `.autoreskill/coder/CODE_SYNC_LEDGER.json`. Do not use that repository for datasets, checkpoints, model weights, raw outputs, runtime logs, credentials, or machine-specific state.
- For SSH/AutoDL/BJTU remote runs, sync training logs and lightweight result text back to the local project after every launch/reconcile. Do not sync checkpoints by default. Record local copies in `REMOTE_RUN.json.local_log_paths` and the sync status in `REMOTE_RUN.json.log_sync`.
- Do not change the locked metric suite / `metric_policy`, dataset, or baseline protocol.
- For PARAM/HPO launches, preserve `hpo_search_policy` from the planning packet
  and record per-trial `hpo_trial` metadata: method, branch/trial id, rung,
  resource axis, resource fraction, config, seed, and whether the trial is
  scout, full_resource, ablation, or confirmation. Execute independent scouts
  asynchronously within the declared trial/GPU-hour budget and queue in-flight
  limits; completion order never changes same-rung comparability or promotion.
  Do not launch seed sweeps as search trials.
- Treat parameter debugging as a scientific action, not generic resource fill.
  It is admissible only for protocol-locked baseline calibration or a
  supported/explicitly ambiguous method with a concrete sensitivity question,
  matched comparison, valid DEHB policy, and remaining trial/GPU-hour budget.
  Never tune a terminal-negative mechanism or extend an exhausted search merely
  because a GPU is idle.
- For `tuning_target=baseline_calibration`, use validation evidence only and
  freeze the selected matched baseline configuration before claim promotion.
  Independent innovation scouts may overlap as `evidence_tier=pilot_only`, but
  they cannot establish paper-report comparison or a publishable gain. Rerun a
  survivor against `baseline_freeze_ref` before `candidate_supported`.
- Preserve the full planning `metric_policy` in `REMOTE_RUN.json`, `EXPERIMENT_LEDGER.json`, and `TRACK_RANKING.json`. Parse and report every locked metric component, matched baseline/proposed deltas, and the predeclared composite or stress metric; do not rank or close evidence from a single favorable component when the protocol is multi-metric.
- Metric parsing must be reusable and auditable. Prefer the workflow `scripts/experiment_result_summary.py` or a project-committed parser over one-off prompt parsing. The parser must emit `RESULT_SUMMARY.json` and `METRIC_TRAJECTORY.csv` or an equivalent manifest-linked pair, preserve raw numeric units, and record whether values are fractions (`0..1`) or percentages (`0..100`). If parsing detects impossible ranges, double scaling, mixed units, missing locked components, or count/epoch mismatches, quarantine the derived artifact, mark the run `parser_gap` or `not_promoted`, and keep the raw synced log path for repair.
- Reconcile finished, failed, stale, or same-resource conflicting runs before
  starting new ones. Do not wait for unrelated running runs on other GPUs or
  backends when an independent queue row can fit available resources.
- Snapshot source state before each run and record the snapshot in `REMOTE_RUN.json`.
- Record `resource_request`, `resource_allocation`, `mutex_group`, and queue row
  id for every launch, including assigned `resource_pool_id`, so later turns can
  distinguish true resource/shared-limit contention from safe parallelism.
- Every launch manifest and `REMOTE_RUN.json` also records `track_role`,
  `evidence_tier`, `evidence_tier_ceiling`, packet/matrix refs and hashes, and the
  launch-time selection fingerprint, project-passport index, execution profile,
  innovation-delta hash, resolved projection hash, submit-intent hash, receipt
  hash, and observation hash. Global-mode launches additionally record
  `global_schedule_sha256`, `assignment_sha256`, and the shared resource snapshot
  ref/hash.
- Every run writes a ledger entry, including crashes, dry-run failures, budget stops, and regressions.
- Keep runtime truth separate from scientific interpretation. `REMOTE_RUN.json`
  records backend state; canonical metrics record numeric evidence;
  `SCIENTIFIC_OUTCOME.json` proposes the outcome relative to the predeclared
  falsifier. The workflow `research_decision.py` validates and applies lifecycle
  changes after reconciliation.
- Infrastructure/implementation failures and protocol-invalid runs do not weaken
  the hypothesis. A valid negative updates belief, scope, pivot, retirement, or
  program conclusion; it is not a code-repair request. A valid inconclusive result
  gets at most one decision-changing discriminator by default.
- Maintain a best-known promoted run. Regressions and failed runs must not replace best.
- Treat the first positive run for an idea as `candidate_supported`, not `promoted`.
- "Positive" means policy-positive under the full locked metric suite. A `New`-only gain, isolated metric win, or missing component with `All`, `Old`, composite, calibration, tail, unknown-K, or other required metric regression must be recorded as `not_promoted`, `metric_tradeoff`, or repair/track-switch evidence rather than `candidate_supported`.
- Promote only after a linked `ablation` or `confirmation` run supports the same `selected_idea_id` and `innovation_mechanism` under the locked protocol.
- Low-fidelity HPO scout trials are `record_only` or `not_promoted` even when
  their metric improves. Only full-resource survivors selected by the declared
  DEHB promotion rule may become `candidate_supported`, and they still need
  linked ablation or confirmation before promoted claims.
- Multi-seed stability validation is capped at three experiment random seeds.
  Use one scout/pilot seed before expensive confirmation. Once 2-3 final seeds
  are justified, materialize them as one `replication_group_id` and launch them
  concurrently when fitting resources exist rather than waiting seed by seed.
  Matched baseline and proposed rows use the same declared seed set and reuse
  valid baseline anchors across innovations. Retries retain the original seed;
  do not launch a fourth unique random seed or treat seed as a tuning axis.
- Maintain per-track best promoted runs as well as the global best; candidate-supported runs stay available as pilot evidence but cannot support strong improvement claims.
- Maintain `TRACK_RANKING.json` from the canonical `metric_policy`, promotion status, retire reasons, and spec-violation status. Do not rank tracks from model-written summaries or a single metric component unless the locked protocol declares that component as the sole canonical metric.
- Roll back or mark `not_promoted` after regression; final export/checkpoint must point to the best validated state.
- Hash protected eval/test/metric paths before and after the run when paths are available.
- After launch or reconcile, refresh `REMOTE_RUN.json.monitoring` and `.autoreskill/automation_registry.json` with an adaptive monitor cadence based on status, backend, ETA, progress/log freshness, stale count, and paid-resource risk.
- Reconcile must keep remote `log_paths` plus local synced copies. Sync only logs/metadata/metrics such as `.log`, `.txt`, `.json`, `.jsonl`, `.csv`, `.tsv`, `.yaml`, `.yml`, `.out`, and `.err`; exclude checkpoint/model artifacts such as `.pt`, `.pth`, `.ckpt`, `.safetensors`, `.bin`, `.onnx`, `checkpoint/`, and `checkpoints/` unless the user explicitly asks for checkpoint backup.
- For stable running experiments with a trustworthy ETA, treat `estimated_remaining_minutes` as the completion wakeup interval. Record `expected_finish_at`, set the heartbeat interval to that remaining time, and let the next reconcile tighten to fast checks only if the run has not finished by the expected time. Do not cap long stable ETA runs to a default 30-minute poll.
- For multi-stage experiment scripts, compute ETA from the full remaining protocol, not only the currently visible training stage. A progress marker such as `offline epoch 8/100` is stage-local; if the launch script will later run online sessions, adapter training, evaluation, or analysis, record those remaining stages explicitly in the monitor artifact and choose the heartbeat from the nearest meaningful stage boundary or full-protocol ETA. Do not replace unobserved later stages with an arbitrary small overhead such as 15% unless the artifact clearly marks it as a lower-bound diagnostic and does not use it to schedule the heartbeat.
- When Codex app automations are available, create or update one heartbeat monitor from `.autoreskill/automation_registry.json`; reuse the stored `automation_id`/`automation_name` and never create a duplicate monitor per run.
- Before calling the Codex app automation tool, run `scripts/experiment_monitor_automation_payload.py --project <project-root> --write` and use the generated `automation_update` payload as the single source of truth for create/update/pause fields. After a successful automation create/update, record the returned id back into `.autoreskill/automation_registry.json` on the next reconcile.
- When a run becomes terminal, reconcile once, scan queue and portfolio work,
  and pause the reused monitor only when no claimed/live external wait and no
  locally actionable ready or fillable work remains.
- Empty or stale logs alone are not terminal evidence. Preserve `running` or
  `unknown` until the backend reports a terminal state or an explicit timeout or
  budget condition is evidenced.
- Before launching any GPU or target sweep command, run `scripts/baseline_protocol_launch_lint.py --project <project-root> --track-id <track-id>`. If you create a proposed run spec, run the same linter with `--candidate-run <json>`. Do not launch when it reports packet identity drift, a non-primary evidence-tier leak, ambiguous frozen-feature protocol, baseline-code drift, metric/split drift, or off-protocol diagnostic markers.
- Before launching any baseline/proposed command, also run `../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root> --track-id <track-id>`. Do not launch if the baseline is not a clone/worktree, if the selected per-track packet does not match the manifest, or if the proposed implementation lacks patch proof against that clone.
- Off-protocol probes are limited to one diagnostic run and must stop there. Record them as `not_promoted` with a corrective baseline-aligned command. Do not expand an off-protocol probe into target sweeps, ablations, confirmation, or `candidate_supported` evidence.
- A feature pilot can become candidate evidence only when it is pre-registered in `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol` and uses the locked baseline feature path/backbone. Convenience small models such as torchvision ResNet18 ImageNet features are diagnostic-only unless explicitly approved as a degraded plan revision.
- If repeated PARAM tuning stalls, force a structural ALGO/CODE leap idea before spending more budget on parameters.
- If the declared DEHB trial budget is exhausted without a full-resource
  candidate, stop PARAM search, preserve all pruned/failed trials as negative
  evidence, and route back to experiment_plan or idea_gate instead of extending
  the sweep.
- If run exceeds budget, shrink experiment or roll back plan.

## Deterministic Helpers

For an enforced cross-dataset Stage-5 search, use
`scripts/dataset_group_hpo.py materialize` to create one queue leg per required
dataset for the same configuration and fidelity. Use `reconcile --write` after
terminal evidence arrives. Only `reconcile --write --finalize` may commit the
best full-resource, no-regression-passing grouped configuration; incomplete
groups remain infeasible and have no optimizer score. The helper rejects
finalization while registered work remains. Use `--stop-reason <reason>` only
for a deliberate bounded early stop; it is stored in the HPO decision.

```bash
python ../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root> --track-id <track-id>
python scripts/baseline_protocol_launch_lint.py --project <project-root> --track-id <track-id>
python scripts/run_reconcile.py --project <project-root> --backend local
python scripts/run_reconcile.py --project <project-root> --backend ssh --sync-logs
python scripts/dataset_group_hpo.py reconcile --project <project-root> --write
python scripts/dataset_group_hpo.py reconcile --project <project-root> --write --finalize [--stop-reason <reason>]
python scripts/experiment_monitor_plan_lint.py --project <project-root>
python scripts/experiment_monitor_automation_payload.py --project <project-root> --write
python scripts/global_admission_automation_payload.py --config <private-global-config.json> --out <payload.json>
python ../autoreskill-workflow/scripts/experiment_next_actions.py check --project <project-root>
python ../autoreskill-workflow/scripts/experiment_next_actions.py frontier --project <project-root>
python ../autoreskill-workflow/scripts/experiment_next_actions.py schedule --project <project-root>
python ../autoreskill-workflow/scripts/portfolio_batch.py --project <project-root> --dry-run
python ../autoreskill-workflow/scripts/resource_passport.py enrich-snapshot --project <project-root> --input <live-snapshot.json> --out <enriched-snapshot.json>
python ../autoreskill-workflow/scripts/research_decision.py --project <project-root> --run-id <run-id> --check
```

Read `references/launch_metadata_schema.md`,
`references/monitor_reconcile_protocol.md`, and
`../autoreskill-workflow/references/scientific_decision_loop.md`.
