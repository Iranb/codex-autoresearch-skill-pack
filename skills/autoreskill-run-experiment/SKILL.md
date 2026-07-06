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
.autoreskill/coder/EXPERIMENT_INDEX.md
.autoreskill/coder/TRACK_RANKING.json
.autoreskill/experiment/EXPERIMENT_MONITOR_PLAN.json
```

## Rules

- Check resource budget before launch.
- Record exact command, environment, commit/diff, remote path, session id.
- When experiment code is managed through a GitHub private repository, launch only from the recorded branch/commit or an explicitly recorded dirty patch. Before launch, record repo URL, privacy, branch, commit SHA, remote checkout path, and local export path in `REMOTE_RUN.json.source_state` and `.autoreskill/coder/CODE_SYNC_LEDGER.json`. Do not use that repository for datasets, checkpoints, model weights, raw outputs, runtime logs, credentials, or machine-specific state.
- For SSH/AutoDL/BJTU remote runs, sync training logs and lightweight result text back to the local project after every launch/reconcile. Do not sync checkpoints by default. Record local copies in `REMOTE_RUN.json.local_log_paths` and the sync status in `REMOTE_RUN.json.log_sync`.
- Do not change the locked metric suite / `metric_policy`, dataset, or baseline protocol.
- For PARAM/HPO launches, preserve `hpo_search_policy` from the planning packet
  and record per-trial `hpo_trial` metadata: method, branch/trial id, rung,
  resource axis, resource fraction, config, seed, and whether the trial is
  scout, full_resource, ablation, or confirmation. Do not launch seed sweeps as
  search trials.
- Preserve the full planning `metric_policy` in `REMOTE_RUN.json`, `EXPERIMENT_LEDGER.json`, and `TRACK_RANKING.json`. Parse and report every locked metric component, matched baseline/proposed deltas, and the predeclared composite or stress metric; do not rank or close evidence from a single favorable component when the protocol is multi-metric.
- Metric parsing must be reusable and auditable. Prefer the workflow `scripts/experiment_result_summary.py` or a project-committed parser over one-off prompt parsing. The parser must emit `RESULT_SUMMARY.json` and `METRIC_TRAJECTORY.csv` or an equivalent manifest-linked pair, preserve raw numeric units, and record whether values are fractions (`0..1`) or percentages (`0..100`). If parsing detects impossible ranges, double scaling, mixed units, missing locked components, or count/epoch mismatches, quarantine the derived artifact, mark the run `parser_gap` or `not_promoted`, and keep the raw synced log path for repair.
- Reconcile finished runs before starting new ones.
- Snapshot source state before each run and record the snapshot in `REMOTE_RUN.json`.
- Every run writes a ledger entry, including crashes, dry-run failures, budget stops, and regressions.
- Maintain a best-known promoted run. Regressions and failed runs must not replace best.
- Treat the first positive run for an idea as `candidate_supported`, not `promoted`.
- "Positive" means policy-positive under the full locked metric suite. A `New`-only gain, isolated metric win, or missing component with `All`, `Old`, composite, calibration, tail, unknown-K, or other required metric regression must be recorded as `not_promoted`, `metric_tradeoff`, or repair/track-switch evidence rather than `candidate_supported`.
- Promote only after a linked `ablation` or `confirmation` run supports the same `selected_idea_id` and `innovation_mechanism` under the locked protocol.
- Low-fidelity HPO scout trials are `record_only` or `not_promoted` even when
  their metric improves. Only full-resource survivors selected by the declared
  DEHB promotion rule may become `candidate_supported`, and they still need
  linked ablation or confirmation before promoted claims.
- Multi-seed stability validation is capped at three experiment random seeds.
  Use one pilot seed plus ablation/confirmation by default; run 2-3 random
seeds only when stability is the explicit validation question. Do not launch a
  fourth random seed for stability validation.
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
- When a run becomes terminal, reconcile once and then pause the reused monitor.
- Before launching any GPU or target sweep command, run `scripts/baseline_protocol_launch_lint.py --project <project-root>`. If you create a proposed run spec, run the same linter with `--candidate-run <json>`. Do not launch when it reports ambiguous frozen-feature protocol, baseline-code drift, metric/split drift, or off-protocol diagnostic markers.
- Before launching any baseline/proposed command, also run `../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root>`. Do not launch if the baseline is not a clone/worktree or if the proposed implementation lacks patch proof against that clone.
- Off-protocol probes are limited to one diagnostic run and must stop there. Record them as `not_promoted` with a corrective baseline-aligned command. Do not expand an off-protocol probe into target sweeps, ablations, confirmation, or `candidate_supported` evidence.
- A feature pilot can become candidate evidence only when it is pre-registered in `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol` and uses the locked baseline feature path/backbone. Convenience small models such as torchvision ResNet18 ImageNet features are diagnostic-only unless explicitly approved as a degraded plan revision.
- If repeated PARAM tuning stalls, force a structural ALGO/CODE leap idea before spending more budget on parameters.
- If the declared DEHB trial budget is exhausted without a full-resource
  candidate, stop PARAM search, preserve all pruned/failed trials as negative
  evidence, and route back to experiment_plan or idea_gate instead of extending
  the sweep.
- If run exceeds budget, shrink experiment or roll back plan.

## Deterministic Helpers

```bash
python ../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root>
python scripts/baseline_protocol_launch_lint.py --project <project-root>
python scripts/run_reconcile.py --project <project-root> --backend local
python scripts/run_reconcile.py --project <project-root> --backend ssh --sync-logs
python scripts/experiment_monitor_plan_lint.py --project <project-root>
python scripts/experiment_monitor_automation_payload.py --project <project-root> --write
```

Read `references/launch_metadata_schema.md` and `references/monitor_reconcile_protocol.md`.
