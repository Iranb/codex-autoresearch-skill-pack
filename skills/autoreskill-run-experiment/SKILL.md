---
name: autoreskill-run-experiment
description: Run and monitor portable AutoResearch experiments. Use to launch local, SSH, AutoDL, BJTU HPC, or other backend runs under autopilot policy, record REMOTE_RUN.json, reconcile ledgers, monitor logs, and prevent metric/dataset/baseline drift.
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
.autoreskill/experiment/EXPERIMENT_MONITOR_PLAN.json
```

## Rules

- Check resource budget before launch.
- Record exact command, environment, commit/diff, remote path, session id.
- Do not change metric, dataset, or baseline protocol.
- Reconcile finished runs before starting new ones.
- Snapshot source state before each run and record the snapshot in `REMOTE_RUN.json`.
- Every run writes a ledger entry, including crashes, dry-run failures, budget stops, and regressions.
- Maintain a best-known promoted run. Regressions and failed runs must not replace best.
- Treat the first positive run for an idea as `candidate_supported`, not `promoted`.
- Promote only after a linked `ablation` or `confirmation` run supports the same `selected_idea_id` and `innovation_mechanism` under the locked protocol.
- Maintain per-track best promoted runs as well as the global best; candidate-supported runs stay available as pilot evidence but cannot support strong improvement claims.
- Roll back or mark `not_promoted` after regression; final export/checkpoint must point to the best validated state.
- Hash protected eval/test/metric paths before and after the run when paths are available.
- After launch or reconcile, refresh `REMOTE_RUN.json.monitoring` and `.autoreskill/automation_registry.json` with an adaptive monitor cadence based on status, backend, ETA, progress/log freshness, stale count, and paid-resource risk.
- For stable running experiments with a trustworthy ETA, treat `estimated_remaining_minutes` as the completion wakeup interval. Record `expected_finish_at`, set the heartbeat interval to that remaining time, and let the next reconcile tighten to fast checks only if the run has not finished by the expected time. Do not cap long stable ETA runs to a default 30-minute poll.
- When Codex app automations are available, create or update one heartbeat monitor from `.autoreskill/automation_registry.json`; reuse the stored `automation_id`/`automation_name` and never create a duplicate monitor per run.
- Before calling the Codex app automation tool, run `scripts/experiment_monitor_automation_payload.py --project <project-root> --write` and use the generated `automation_update` payload as the single source of truth for create/update/pause fields. After a successful automation create/update, record the returned id back into `.autoreskill/automation_registry.json` on the next reconcile.
- When a run becomes terminal, reconcile once and then pause the reused monitor.
- Before launching any GPU or target sweep command, run `scripts/baseline_protocol_launch_lint.py --project <project-root>`. If you create a proposed run spec, run the same linter with `--candidate-run <json>`. Do not launch when it reports ambiguous frozen-feature protocol, baseline-code drift, metric/split drift, or off-protocol diagnostic markers.
- Before launching any baseline/proposed command, also run `../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root>`. Do not launch if the baseline is not a clone/worktree or if the proposed implementation lacks patch proof against that clone.
- Off-protocol probes are limited to one diagnostic run and must stop there. Record them as `not_promoted` with a corrective baseline-aligned command. Do not expand an off-protocol probe into target sweeps, ablations, confirmation, or `candidate_supported` evidence.
- A feature pilot can become candidate evidence only when it is pre-registered in `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol` and uses the locked baseline feature path/backbone. Convenience small models such as torchvision ResNet18 ImageNet features are diagnostic-only unless explicitly approved as a degraded plan revision.
- If repeated PARAM tuning stalls, force a structural ALGO/CODE leap idea before spending more budget on parameters.
- If run exceeds budget, shrink experiment or roll back plan.

## Deterministic Helpers

```bash
python ../autoreskill-implement-experiment/scripts/baseline_clone_lint.py --project <project-root>
python scripts/baseline_protocol_launch_lint.py --project <project-root>
python scripts/run_reconcile.py --project <project-root> --backend local
python scripts/experiment_monitor_plan_lint.py --project <project-root>
python scripts/experiment_monitor_automation_payload.py --project <project-root> --write
```

Read `references/launch_metadata_schema.md` and `references/monitor_reconcile_protocol.md`.
