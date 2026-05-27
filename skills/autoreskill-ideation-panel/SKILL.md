---
name: autoreskill-ideation-panel
description: OpenClaw-aligned multi-persona ideation and experiment-idea construction panel for portable AutoResearch. Use for Professor/Postdoc/PhDStudent/Critic passes, generating the 12-15 experiment optimization idea pool during ideation, novelty tournaments, candidate pool scoring, fallback design review when PaperNexus research_controller is unavailable, selected idea gating, and IDEA_CATALYST_CONTRACT preparation.
metadata:
  short-description: Multi-persona ideation and idea gate
---

# Ideation Panel

Use after PaperNexus materials exist. The panel does not replace PaperNexus evidence; it interprets it.

The 12-15 experiment optimization ideas are created here, during idea construction. Do not defer that generation to `autoreskill-experiment-plan`; experiment planning consumes a selected idea and locks the protocol.

Roles:

- Professor: paradigm value and significance
- Postdoc: feasibility and experiment path
- PhDStudent: prior work and baseline pressure
- Critic: adversarial novelty/reviewer attack

Outputs:

- `IDEA_TREE.md`
- `NOVELTY_TREE.md`
- `CHALLENGE_INSIGHT_TREE.md`
- `WELL_ESTABLISHED_SOLUTION_CHECK.md`
- `CANDIDATE_POOL.json`
- `EXPERIMENT_IDEA_POOL.json`
- `TOURNAMENT_SCOREBOARD.json`
- `TOP3_DIRECTION_SUMMARY.md`
- `RESEARCH_PROPOSAL.md`

`EXPERIMENT_IDEA_POOL.json` must contain 12-15 experiment optimization ideas, not only high-level research directions. Target at least 6 ALGO ideas and at least 6 CODE ideas; keep PARAM ideas to 4 or fewer. Include red-line audit fields for metric/eval/dataset/data-leakage/prediction-cheating/training-budget drift.

During `idea_gate`, select one idea by setting `selected_idea_id` or marking one idea `status=SELECTED`. Do not advance to experiment planning until the selected idea is present in the ideation-stage pool.

## Deterministic Helpers

```bash
python scripts/panel_review.py --project <project-root> --force-ready
python scripts/ideation_lint.py --project <project-root>
python ~/.codex/skills/autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json
python ~/.codex/skills/autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json --require-selected
```

Read references for panel protocol and novelty gate. For the idea pool schema, read `~/.codex/skills/autoreskill-experiment-plan/references/experiment_idea_pool.md`; despite its file location, the canonical owner is this ideation skill.
