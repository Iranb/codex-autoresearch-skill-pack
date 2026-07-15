# Monitor And Reconcile

For each run:

1. Reconcile `submitting`, `needs_sync`, running, terminal, failed, stale, or
   same-resource conflicting runs before launch. Search prepared submit traces
   before any retry. Unrelated running runs on other GPUs/backends do not block
   an independent ready queue row.
2. Record a pre-run source snapshot: commit, status, diff summary, command, backend, budget, and checkpoint tag.
3. Hash protected eval/test/metric paths when listed by the manifest or review packet.
4. Check process/job status.
5. Tail logs for early failures.
6. Verify baseline alignment and protocol lock.
7. Parse metrics.
8. Sync remote training logs and lightweight result metadata to local storage under the experiment directory. Exclude checkpoints/model weights unless the user explicitly requested checkpoint backup.
9. Write `REMOTE_RUN.json`.
   For an external queued intent, first verify its canonical
   `coder/experiments/<track-id>/<experiment-id>` location and immutable digest,
   then preserve the exact campaign/gate/candidate/commitment, resource,
   preflight, launch-spec, budget, authorization, and backend-idempotency
   payload. Runtime reconciliation is a merge, never reconstruction of that
   authority chain.
10. For result-bearing or typed terminal runs, write or consume
    `SCIENTIFIC_OUTCOME.json` against the predeclared hypothesis and falsifier.
11. Refresh `REMOTE_RUN.json.monitoring` and `.autoreskill/automation_registry.json`.
12. Append or refresh `EXPERIMENT_LEDGER.json` and `EXPERIMENT_INDEX.md` without
    erasing an accepted scientific outcome.
13. Run workflow `research_decision.py --check`, then `--write` only after the
    outcome identity, protocol, canonical evidence, and transition all validate.

Adaptive monitor cadence:

- queued BJTU/HPC jobs: around 30 min
- generic queued jobs: around 15 min
- provisioning/startup: around 3 min
- stable training with ETA: schedule the next heartbeat for the estimated completion interval
- at or past expected finish: fast recheck on the next reconcile if the run is still active
- stale/no-progress paid GPU runs: around 3 min
- stale/no-progress non-paid runs: around 5 min
- terminal runs: reconcile once, scan queue and portfolio work, then pause the
  reused monitor only when no claimed/live external wait and no locally
  actionable ready or fillable work remains

`estimated_remaining_minutes` is the completion wakeup interval for stable active runs. Reconcile records `expected_finish_at`, updates the single heartbeat monitor to that interval, and then switches to fast follow-up checks only when the expected finish time has arrived but the run is still active. Startup, queued, stale, hung, and no-ETA states still use health-check intervals.

When Codex app automations are available, use the single monitor described by `.autoreskill/automation_registry.json`. Preserve its `automation_id` and update the same scheduled monitor as status/ETA changes; do not create one monitor per experiment run. The monitor may summarize multiple active runs, but it must not prevent new launches when the next-action queue has independent ready rows and live resources are idle.

The monitor plan carries a monotonically updated plan revision and canonical
semantic hash. Reuse an explicit stored prompt only when its declared revision
and prompt SHA-256 match the current plan; otherwise synthesize the prompt from
current run ids, due time, progress, frontier state, and admission scope. This
prevents an old automation body from polling stale jobs or suppressing new work.
The v2 opportunity contract runs exactly once per prompt: apply outcomes,
compute both launch and portfolio deficits, batch-fill the exact feasible
shortlist subset, materialize all unlocked rows, then enter the repeated
submit-refresh loop. A `delete` action emits only delete; an unknown action fails
closed and never creates a replacement monitor.
Generate migration payloads with `--current-automation <readback.json>` to
preserve the managed task's prompt/name/id while replacing old v1/v2 blocks.
After App mutation, validate the immutable saved payload with
`--expected-payload <payload.json> --readback <after.json>`; any id, status,
cadence, prompt hash, or v2-block-count drift fails closed.

Parallel launch policy:

- Read `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json` before deciding to wait.
- Launch a ready/planned row only when dependencies are satisfied, blocker is
  empty, `parallel_safe` is not false, `mutex_group` does not conflict with a
  running row, and `resource_request` fits a live idle slot.
- The selected pool must also have an unexpired capability proof for the row's
  exact execution profile. Idle memory/utilization is capacity evidence, not
  code/data/checkpoint/runtime compatibility.
- Atomically claim the row with its current `queue_revision` and worker id before
  backend launch. A competing worker must receive a lease conflict without
  mutation. Repeated same-owner claim is idempotent.
- In `admission_scope=global`, the project monitor stops at reconciliation and
  reports `global_admission_required`. Only the global controller, holding the
  global then target-project control leases, may claim the current first hashed
  assignment and enter backend preflight.
- After exact preflight, durably record `submitting` intent before the backend
  side effect, immediately bind the native receipt as `needs_sync`, then set
  `running` or terminal only from authoritative backend observation. Preserve
  intent, receipt, and observation hashes in queue/run artifacts. Release or
  abort is permitted only before launch or after explicit backend no-live proof.
- Lease expiry means reconcile; it is not permission to assume the backend stopped
  or to launch a duplicate.
- If no row fits, record the exact dependency/resource blocker and then allow
  the project monitor heartbeat to wait.
- After each physical submit, invalidate the consumed snapshot, refresh, and
  repeat one assignment at a time until no fitting row or wake budget remains.
  Refresh-after-one is a safety boundary, not a heartbeat throughput cap.

Never launch blindly when a conflicting previous run is unreconciled. Empty logs
or missing progress text do not establish failure while the backend remains live.

Log sync policy:

- Sync remote logs after launch and on every reconcile for SSH, AutoDL, BJTU, and other remote backends.
- Keep synced files under `.autoreskill/coder/experiments/<track-id>/<experiment-id>/logs/synced/`.
- Record every sync attempt in `REMOTE_RUN.json.log_sync.items` and record local files in `REMOTE_RUN.json.local_log_paths`.
- Include lightweight files such as `.log`, `.txt`, `.json`, `.jsonl`, `.csv`, `.tsv`, `.yaml`, `.yml`, `.out`, and `.err`.
- Exclude checkpoint/model artifacts by default: `.pt`, `.pth`, `.ckpt`, `.safetensors`, `.bin`, `.onnx`, and any `checkpoint/` or `checkpoints/` path.
- If checkpoint backup is needed, route it through an explicit backup/persistent-storage step and do not mix it with log sync.

Baseline/protocol preflight:

- Run `../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root> --track-id <track-id>` before launch. The selected per-track packet must match the manifest, the baseline must be a git clone/worktree or verified repository snapshot, and proposed changes must have patch proof against that baseline.
- Run `scripts/baseline_protocol_launch_lint.py --project <project-root> --track-id <track-id>` before spending GPU time.
- If the next command is represented as JSON, run `scripts/baseline_protocol_launch_lint.py --project <project-root> --track-id <track-id> --candidate-run <json>`.
- A candidate run must identify the locked baseline code id, command/entrypoint, dataset, split, metric, and protocol status.
- `protocol_status` must be `baseline_aligned` or `pre_registered_feature_protocol` before target sweeps, ablations, confirmation, or promotion. `off_protocol_probe` can be recorded once as diagnostic evidence only.
- Frozen-feature pilots require `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol`; otherwise they are launch blockers, not a reason to substitute a smaller model.

Promotion rules:

- Completed positive candidate runs become `candidate_supported` only.
- Exception: `evidence_tier=pilot_only` rapid-validation runs remain
  `record_only` even when their pilot metric improves; they may guide the next
  decision but never enter `candidate_runs` or directly support promotion.
- Promote only completed linked `ablation` or `confirmation` runs with locked protocol and non-fixture metrics.
- Compare proposed against matched baseline using `metric_direction`.
- Do not promote if metrics are missing, protected hashes changed unexpectedly, or source state is unknown.
- Preserve the current best if the new run regresses.
- Record every ledger row with `selected_idea_id`, `innovation_mechanism`, `mechanism_type`, `promotion_stage`, `verdict`, and `next_action`.
- Keep `best_run` and `track_best_runs` limited to promoted entries. `candidate_runs` are pilot evidence for ablation/confirmation scheduling, not manuscript support.
- Record valid negative/refuted/inconclusive results as scientific evidence for
  pruning, scope, limitations, or a bounded negative finding. They cannot support
  a positive improvement claim or trigger implementation repair without separate
  defect evidence.

Scientific outcome routing:

- `infrastructure_failure` and `implementation_failure`: operational repair or
  backend reconciliation, `belief_effect=none`.
- `protocol_invalid`: quarantine the result and repair the protocol; no claim.
- `valid_positive_candidate`: a primary may queue linked ablation or
  confirmation; a non-primary must request primary reselection and a frozen
  matched-baseline rerun. Neither path directly promotes the pilot.
- `valid_negative`: weaken/refute, pivot, scope, retire, or conclude.
- `valid_inconclusive`: run one useful discriminator or retire/conclude.
- `cross_dataset_contradiction`: narrow scope or create one moderator child track.

Detailed classes, required identity, counters, and allowed transitions are owned
by `autoreskill-workflow/references/scientific_decision_loop.md`.

Leap rule:

- If recent ledger entries are dominated by PARAM ideas or small tuning changes without improvement, select or generate an ALGO/CODE structural idea and mark the transition as `leap_idea`.
