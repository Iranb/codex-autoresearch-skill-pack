---
name: autoreskill-experiment-plan
description: OpenClaw-aligned experiment planning skill for portable AutoResearch. Use to convert PaperNexus-backed ideas into INNOVATION_PACKET.json, EXPERIMENT_REVIEW_PACKET.json, baseline-first one-variable experiment plans, compute budgets, falsifiers, and prelaunch gates.
metadata:
  short-description: Plan baseline-first experiments
---

# Experiment Plan

This skill turns an evidence-backed idea into an executable experiment plan.

## Direct Authority

`orchestrator/INNOVATION_PACKET.json` is the stage authority. `planner/EXPERIMENT_REVIEW_PACKET.json` is the prelaunch gate.

Required authority fields:

- selected idea fragment id
- supporting idea fragment ids
- baseline
- primary metric
- fixed budget
- one-variable change
- dataset or benchmark
- falsifier or failure condition
- PaperNexus idea evidence export path
- source-backed evidence boundaries
- controller innovation brief and design review when available

## Planning Rules

- Baseline first.
- One variable per main experiment.
- Dataset, metric, and baseline protocol are locked before Coder starts.
- Include falsifier and stop rules.
- Use `experiment_cost_materials` when available; otherwise record `cost_evidence_gap`.

## Validation

Before `autoreskill-run-experiment`, run:

```bash
python scripts/prelaunch_lint.py --project <project-root>
python scripts/innovation_lint.py --project <project-root>
python scripts/experiment_materialize.py --project <project-root>
```

The linter blocks launch when the reviewed packet lacks source-backed selected idea support, evidence boundaries, one-variable change, baseline protocol, dataset, metrics, falsifiers, stop rules, compute budget, PaperNexus norms, controller/fallback design review, or expected artifacts.

Read `references/experiment_review_packet_schema.md` and `references/baseline_fairness_checklist.md`.
