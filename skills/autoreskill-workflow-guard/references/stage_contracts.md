# Stage Contracts

Each stage is complete only when its contract authority passes lint.

| Stage | Owner | Authority | Complete when |
| --- | --- | --- | --- |
| `init` | WorkflowGuard | `.autoreskill/goal_state.json` | project, policy, capabilities, memory, queues exist |
| `topic_search` | Researcher | literature discovery packet/run state | topic/query/paper evidence exists |
| `graph_build` | Researcher | `graph/GRAPH_BUILD_DECISION.json` | `decision=complete` and `source_backed_graph_claim=true` |
| `frontier_mapping` | Researcher | frontier artifacts | gap/limitation/transfer evidence exists |
| `literature_review` | Researcher | lit review artifacts | SOTA matrix and gap synthesis exist |
| `ideation` | Researcher | `ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json` + `ideation/EXPERIMENT_IDEA_POOL.json` | `status=ready` and `idea_pool_lint.py` passes with 12-15 experiment optimization ideas |
| `idea_gate` | Reviewer/Critic | review scorecard + `ideation/EXPERIMENT_IDEA_POOL.json` | chosen idea has baseline, novelty basis, negative evidence, and the pool has `selected_idea_id` or one `status=SELECTED` idea |
| `experiment_plan` | Orchestrator | `orchestrator/INNOVATION_PACKET.json` + `planner/EXPERIMENT_REVIEW_PACKET.json` | `innovation_lint.py` and `prelaunch_lint.py` pass: selected ideation idea is consumed, evidence boundaries, locked baseline/eval/metric/data, one-variable plan, budget/falsifier, and controller or fallback design review are present |
| `code` | Coder | experiment manifest/dry-run | dry-run proof, comparable configs, selected idea id, locked protocol, and source snapshot |
| `experiment` | Researcher/Coder | run metadata/ledger | execution proof, full ledger trajectory, best-run decision, and no unreconciled run |
| `analysis` | Analyzer | claim matrix/verdicts | results proof plus claim-evidence matrix tied to ledger trajectory and best validated run |
| `review_pressure` | Reviewer | `reviewer/REVIEW_FINDINGS.json` | high/critical issues closed, waived, or claims downgraded |
| `writing` | Academic Writer | paper draft/write package | manuscript exists and strong claims are supported |
| `submission_ready` | WorkflowGuard/Reviewer | `submission_ready.json` | `main.tex`, `main.pdf`, citation/front-matter/package gates ready |

Do not convert missing artifacts into "complete" by projection. Use autopilot repair, degradation, rollback, or hard stop.

Important guardrails:

- Empty directories are never completion evidence.
- `code` needs `EXPERIMENT_INDEX.md`, at least one `EXPERIMENT_MANIFEST.json`, and dry-run log evidence.
- `experiment` needs an experiment ledger plus run metadata/results for every attempt, including failed and regressed attempts.
- `analysis` needs claim-evidence and track verdicts tied back to the ledger, not only the best metric.
- `review_pressure` cannot pass with unresolved high/critical findings.
