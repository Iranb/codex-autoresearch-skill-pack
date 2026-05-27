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
```

## Rules

- Check resource budget before launch.
- Record exact command, environment, commit/diff, remote path, session id.
- Do not change metric, dataset, or baseline protocol.
- Reconcile finished runs before starting new ones.
- If run exceeds budget, shrink experiment or roll back plan.

## Deterministic Helpers

```bash
python scripts/run_reconcile.py --project <project-root> --backend local
```

Read `references/launch_metadata_schema.md` and `references/monitor_reconcile_protocol.md`.
