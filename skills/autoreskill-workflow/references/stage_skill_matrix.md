# Stage Skill Matrix

Use this file to route a `.autoreskill` stage to the child skill that should
execute the current job packet.

This file is not a completion authority. Stage completion is owned by
`stage_contracts.md` and `scripts/contract_lint.py`.

| Stage | Owner | Child skill | Primary writes |
| --- | --- | --- | --- |
| `init` | WorkflowGuard | `autoreskill-workflow` | `.autoreskill/goal_state.json`, `.autoreskill/autopilot_policy.json`, queues, memory |
| `topic_search` | Researcher | `autoreskill-papernexus-innovation` | `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/evidence_cart.jsonl` |
| `graph_build` | Researcher | `autoreskill-papernexus-innovation` | `.autoreskill/graph/`, `.autoreskill/papernexus/`, `.autoreskill/evidence_cart.jsonl` |
| `frontier_mapping` | Researcher | `autoreskill-papernexus-innovation` | `.autoreskill/papernexus/`, `.autoreskill/ideation/`, `.autoreskill/evidence_cart.jsonl` |
| `literature_review` | Researcher | `autoreskill-literature-review`; use `autoreskill-papernexus-innovation` for missing source coverage | `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/survey/`, `.autoreskill/evidence_cart.jsonl` |
| `ideation` | Researcher | `autoreskill-ideation-panel`; use `autoreskill-papernexus-innovation` for discovery/material closure | `.autoreskill/ideation/`, `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/survey/`, `.autoreskill/user_view/`, `.autoreskill/evidence_cart.jsonl` |
| `idea_gate` | Reviewer | `autoreskill-ideation-panel` or `autoreskill-review-gate`; use `autoreskill-papernexus-innovation` for selected-idea evidence debt | `.autoreskill/ideation/`, `.autoreskill/reviewer/`, `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/survey/`, `.autoreskill/user_view/` |
| `experiment_plan` | Orchestrator | `autoreskill-experiment-plan`; use `autoreskill-papernexus-innovation` for evidence import/material closure | `.autoreskill/orchestrator/`, `.autoreskill/planner/`, `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/survey/`, `.autoreskill/user_view/` |
| `code` | Coder | `autoreskill-implement-experiment` | `.autoreskill/coder/` |
| `experiment` | Coder | `autoreskill-run-experiment` | `.autoreskill/coder/` |
| `analysis` | Analyzer | `autoreskill-analyze-results`; use `autoreskill-papernexus-innovation` for claim or negative-evidence repair | `.autoreskill/analyzer/`, `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/user_view/` |
| `review_pressure` | Reviewer | `autoreskill-review-gate`; use `autoreskill-papernexus-innovation` for novelty, citation, or baseline objections | `.autoreskill/reviewer/`, `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/user_view/` |
| `writing` | Academic Writer | `autoreskill-paper-write`; use `autoreskill-literature-review` and `autoreskill-papernexus-innovation` for related-work/citation gaps | `.autoreskill/paper/`, `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/user_view/` |
| `submission_ready` | WorkflowGuard/Reviewer | `autoreskill-review-gate`; use `autoreskill-papernexus-innovation` only for final citation/source blockers | `.autoreskill/paper/`, `.autoreskill/reviewer/`, `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/submission_ready.json`, `.autoreskill/user_view/` |

## Routing Rules

- Execute the child skill named in the job packet first. Use this matrix only to
  resolve ambiguity or repair a bad packet.
- WorkflowGuard remains the only owner that may advance `goal_state.json`. Child
  skills write artifacts, then the parent updates the job and runs another tick.
- Keep `code` and `experiment` under `Coder`. Ask Researcher to reconcile
  scientific intent only when a job packet explicitly requests that.
- If a linter fails, mark the job failed or retry with the exact blocker instead
  of manually advancing the stage.
- Use `paper_code_innovation_transfer.md` for paper-code survey and migration
  routing. Repository evidence supports mechanism feasibility, not performance
  claims.
- Use `innovation_story_contract.md` when a stage writes
  `.autoreskill/user_view/innovation_story/`. User-facing story files are derived
  views and do not replace machine-readable authorities.
- Use `async_wait_policy.md` for heartbeat decisions. Local stage advancement,
  ready repairs, lint failures, planning, review, writing, and generic queues are
  not heartbeat scopes.
