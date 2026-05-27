---
name: autoreskill-ideation-panel
description: OpenClaw-aligned multi-persona ideation panel for portable AutoResearch. Use for Professor/Postdoc/PhDStudent/Critic passes, novelty tournaments, candidate pool scoring, fallback design review when PaperNexus research_controller is unavailable, and IDEA_CATALYST_CONTRACT preparation.
metadata:
  short-description: Multi-persona ideation and idea gate
---

# Ideation Panel

Use after PaperNexus materials exist. The panel does not replace PaperNexus evidence; it interprets it.

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
- `TOURNAMENT_SCOREBOARD.json`
- `TOP3_DIRECTION_SUMMARY.md`
- `RESEARCH_PROPOSAL.md`

## Deterministic Helpers

```bash
python scripts/panel_review.py --project <project-root> --force-ready
python scripts/ideation_lint.py --project <project-root>
```

Read references for panel protocol and novelty gate.
