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
- selected experiment idea id from `ideation/EXPERIMENT_IDEA_POOL.json`
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
- Consume the selected optimization idea from `autoreskill-ideation-panel` at `ideation/EXPERIMENT_IDEA_POOL.json`. Do not generate the pool in experiment planning.
- If the pool is missing, malformed, or has no selected idea, return to `ideation` or `idea_gate`; do not patch around it by inventing a planning-stage pool.
- One variable per main experiment and one logical change per iteration.
- Dataset, metric, evaluation command, data split, and baseline protocol are locked before Coder starts.
- Reuse the red-line audit from the selected idea, then run a plan-level check for no metric drift, evaluation drift, dataset drift, data leakage, prediction cheating, or training-budget drift.
- Include falsifier and stop rules.
- Use `experiment_cost_materials` when available; otherwise record `cost_evidence_gap`.
- Record `idea_pool_path` as `ideation/EXPERIMENT_IDEA_POOL.json` and record the selected `selected_idea_id` in `EXPERIMENT_REVIEW_PACKET.json`.

## Validation

Before `autoreskill-run-experiment`, run:

```bash
python scripts/experiment_materialize.py --project <project-root>
python scripts/prelaunch_lint.py --project <project-root>
python scripts/innovation_lint.py --project <project-root>
```

The linters block launch when the reviewed packet lacks source-backed selected idea support, evidence boundaries, one-variable change, baseline protocol, locked dataset/eval/metric, falsifiers, stop rules, compute budget, PaperNexus norms, controller/fallback design review, or expected artifacts.

Read `references/experiment_review_packet_schema.md` and `references/baseline_fairness_checklist.md`. Read `references/experiment_idea_pool.md` only when diagnosing the upstream ideation pool; do not create that pool in this skill.
