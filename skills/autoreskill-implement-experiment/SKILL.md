---
name: autoreskill-implement-experiment
description: Research engineering skill for portable AutoResearch. Use to implement experiment bundles from INNOVATION_PACKET and EXPERIMENT_REVIEW_PACKET, create manifests, configs, train/evaluate scripts, dry-run logs, and baseline/proposed comparable code.
metadata:
  short-description: Implement reproducible experiment bundles
---

# Implement Experiment

Use only after `INNOVATION_PACKET.json` and `EXPERIMENT_REVIEW_PACKET.json` pass lint.

## Output Layout

```text
.autoreskill/coder/experiments/<track-id>/<experiment-id>/
  EXPERIMENT_MANIFEST.json
  train.py
  evaluate.py
  configs/baseline.yaml
  configs/proposed.yaml
  logs/
  results/
  requirements.txt
  README.md
```

## Rules

- Do not change dataset, primary metric, or baseline protocol.
- Keep random seeds configurable.
- Assert key input/output shapes.
- Write logs to stdout and file.
- Run dry-run before reporting launch-ready.

## Deterministic Helpers

```bash
python scripts/experiment_scaffold.py --project <project-root> --write-dry-run
python scripts/experiment_drift_lint.py --project <project-root>
```

Read `references/experiment_bundle_layout.md` and `references/dry_run_checklist.md`.
