---
name: autoreskill-papernexus-research-controller
description: Use PaperNexus agent_materials operation=research_controller for problem decomposition, candidate graph generation, judge/select batch, evidence expansion, solution sketches, design review, and export in portable AutoResearch workflows.
metadata:
  short-description: Run PaperNexus research controller
---

# PaperNexus Research Controller

Use when the remote MCP supports `agent_materials(operation="research_controller")`. If it is unavailable, record `research_controller_available=false` and fall back to PaperNexus material packs plus ideation-panel review.

## Required Sequence

```text
status
init_task
generate_decomposition
review_decomposition
generate_candidates
propose_edges
judge_batch
select_batch
expand_evidence
compose_solutions
design_review
export
```

Do not treat `solution-sketches` as recommendations until `design_review` exists.

Mirror controller artifacts to `.autoreskill/papernexus/research_controller/`.
Before experiment planning, materialize `innovation-brief.json`; downstream `INNOVATION_PACKET.json` should cite this brief plus the design review path.

## Deterministic Helpers

```bash
python scripts/controller_brief.py --project <project-root>
python scripts/controller_lint.py --project <project-root>
python scripts/controller_fallback.py --project <project-root> --reason "research_controller unavailable"
```

Read `references/controller_sequence.md`, `references/controller_artifact_schema.md`, and `references/design_review_gate.md`.
