# Monitor And Reconcile

For each run:

1. Reconcile any previous unfinished run before launch.
2. Record a pre-run source snapshot: commit, status, diff summary, command, backend, budget, and checkpoint tag.
3. Hash protected eval/test/metric paths when listed by the manifest or review packet.
4. Check process/job status.
5. Tail logs for early failures.
6. Verify baseline alignment and protocol lock.
7. Parse metrics.
8. Sync remote training logs and lightweight result metadata to local storage under the experiment directory. Exclude checkpoints/model weights unless the user explicitly requested checkpoint backup.
9. Write `REMOTE_RUN.json`.
10. Refresh `REMOTE_RUN.json.monitoring` and `.autoreskill/automation_registry.json`.
11. Append or refresh `EXPERIMENT_LEDGER.json` and `EXPERIMENT_INDEX.md`.
12. Write decision: promoted, not_promoted, rollback_to_best, repair, stop, multi-seed, leap_idea, analyze. Multi-seed means at most three experiment random seeds for stability validation.

Adaptive monitor cadence:

- queued BJTU/HPC jobs: around 30 min
- generic queued jobs: around 15 min
- provisioning/startup: around 3 min
- stable training with ETA: schedule the next heartbeat for the estimated completion interval
- at or past expected finish: fast recheck on the next reconcile if the run is still active
- stale/no-progress paid GPU runs: around 3 min
- stale/no-progress non-paid runs: around 5 min
- terminal runs: reconcile once, then pause the reused monitor

`estimated_remaining_minutes` is the completion wakeup interval for stable active runs. Reconcile records `expected_finish_at`, updates the single heartbeat monitor to that interval, and then switches to fast follow-up checks only when the expected finish time has arrived but the run is still active. Startup, queued, stale, hung, and no-ETA states still use health-check intervals.

When Codex app automations are available, use the single monitor described by `.autoreskill/automation_registry.json`. Preserve its `automation_id` and update the same scheduled monitor as status/ETA changes; do not create one monitor per experiment run.

Never launch blindly when a previous run is unreconciled.

Log sync policy:

- Sync remote logs after launch and on every reconcile for SSH, AutoDL, BJTU, and other remote backends.
- Keep synced files under `.autoreskill/coder/experiments/<track-id>/<experiment-id>/logs/synced/`.
- Record every sync attempt in `REMOTE_RUN.json.log_sync.items` and record local files in `REMOTE_RUN.json.local_log_paths`.
- Include lightweight files such as `.log`, `.txt`, `.json`, `.jsonl`, `.csv`, `.tsv`, `.yaml`, `.yml`, `.out`, and `.err`.
- Exclude checkpoint/model artifacts by default: `.pt`, `.pth`, `.ckpt`, `.safetensors`, `.bin`, `.onnx`, and any `checkpoint/` or `checkpoints/` path.
- If checkpoint backup is needed, route it through an explicit backup/persistent-storage step and do not mix it with log sync.

Baseline/protocol preflight:

- Run `../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root>` before launch. The baseline must be a git clone/worktree or verified repository snapshot, and proposed changes must have patch proof against that baseline.
- Run `scripts/baseline_protocol_launch_lint.py --project <project-root>` before spending GPU time.
- If the next command is represented as JSON, run `scripts/baseline_protocol_launch_lint.py --project <project-root> --candidate-run <json>`.
- A candidate run must identify the locked baseline code id, command/entrypoint, dataset, split, metric, and protocol status.
- `protocol_status` must be `baseline_aligned` or `pre_registered_feature_protocol` before target sweeps, ablations, confirmation, or promotion. `off_protocol_probe` can be recorded once as diagnostic evidence only.
- Frozen-feature pilots require `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol`; otherwise they are launch blockers, not a reason to substitute a smaller model.

Promotion rules:

- Completed positive candidate runs become `candidate_supported` only.
- Promote only completed linked `ablation` or `confirmation` runs with locked protocol and non-fixture metrics.
- Compare proposed against matched baseline using `metric_direction`.
- Do not promote if metrics are missing, protected hashes changed unexpectedly, or source state is unknown.
- Preserve the current best if the new run regresses.
- Record every ledger row with `selected_idea_id`, `innovation_mechanism`, `mechanism_type`, `promotion_stage`, `verdict`, and `next_action`.
- Keep `best_run` and `track_best_runs` limited to promoted entries. `candidate_runs` are pilot evidence for ablation/confirmation scheduling, not manuscript support.
- Record negative results as evidence for pruning candidates, not as manuscript support.

Leap rule:

- If recent ledger entries are dominated by PARAM ideas or small tuning changes without improvement, select or generate an ALGO/CODE structural idea and mark the transition as `leap_idea`.
