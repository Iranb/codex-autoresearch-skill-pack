# Stage Contracts

Each stage is complete only when its contract authority passes lint.

| Stage | Owner | Authority | Complete when |
| --- | --- | --- | --- |
| `init` | WorkflowGuard | `.autoreskill/goal_state.json` | project, policy, capabilities, memory, queues exist |
| `topic_search` | Researcher | literature discovery packet/run state | topic/query/paper evidence exists |
| `graph_build` | Researcher | `graph/GRAPH_BUILD_DECISION.json` | `decision=complete` and `source_backed_graph_claim=true` |
| `frontier_mapping` | Researcher | frontier artifacts | gap/limitation/transfer evidence exists |
| `literature_review` | Researcher | lit review artifacts | SOTA matrix and gap synthesis exist |
| `ideation` | Researcher | `ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json` | `status=ready` |
| `idea_gate` | Reviewer/Critic | review scorecard | chosen idea has baseline, novelty basis, negative evidence |
| `experiment_plan` | Orchestrator | `orchestrator/INNOVATION_PACKET.json` | `innovation_lint.py` passes: selected idea has source-backed PaperNexus support, evidence boundaries, baseline-first one-variable plan, dataset/metric/budget/falsifier, and controller or fallback design review |
| `code` | Coder | experiment manifest/dry-run | dry-run proof and comparable configs |
| `experiment` | Researcher/Coder | run metadata/ledger | execution proof and analysis-ready decision |
| `analysis` | Analyzer | claim matrix/verdicts | results proof plus claim-evidence matrix |
| `review_pressure` | Reviewer | `reviewer/REVIEW_FINDINGS.json` | high/critical issues closed, waived, or claims downgraded |
| `writing` | Academic Writer | paper draft/write package | manuscript exists and strong claims are supported |
| `submission_ready` | WorkflowGuard/Reviewer | `submission_ready.json` | `main.tex`, `main.pdf`, citation/front-matter/package gates ready |

Do not convert missing artifacts into "complete" by projection. Use autopilot repair, degradation, rollback, or hard stop.

Important guardrails:

- Empty directories are never completion evidence.
- `code` needs `EXPERIMENT_INDEX.md`, at least one `EXPERIMENT_MANIFEST.json`, and dry-run log evidence.
- `experiment` needs an experiment ledger plus run metadata or results.
- `analysis` needs claim-evidence and track verdicts tied back to experiment proof.
- `review_pressure` cannot pass with unresolved high/critical findings.
