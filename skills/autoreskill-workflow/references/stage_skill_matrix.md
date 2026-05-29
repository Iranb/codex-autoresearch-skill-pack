# Stage Skill Matrix

Use this table to route a `.autoreskill` stage to the child skill that should satisfy its current job packet. WorkflowGuard remains the only authority for stage advancement.

| Stage | Owner | Child skill | Primary writes | Completion check |
| --- | --- | --- | --- | --- |
| `init` | WorkflowGuard | `autoreskill-workflow` | `.autoreskill/goal_state.json`, policy, queues, memory | `contract_lint.py --stage init` |
| `topic_search` | Researcher | `autoreskill-papernexus-innovation` | `.autoreskill/literature/`, `.autoreskill/papernexus/`, `.autoreskill/evidence_cart.jsonl` | topic search contract |
| `graph_build` | Researcher | `autoreskill-papernexus-innovation` | `.autoreskill/graph/`, `.autoreskill/papernexus/`, `.autoreskill/evidence_cart.jsonl` | `GRAPH_BUILD_DECISION.json` has `decision=complete` and `source_backed_graph_claim=true` |
| `frontier_mapping` | Researcher | `autoreskill-papernexus-innovation` | `.autoreskill/papernexus/`, `.autoreskill/ideation/`, `.autoreskill/evidence_cart.jsonl` | frontier material pack or challenge insight tree exists |
| `literature_review` | Researcher | `autoreskill-literature-review` | `.autoreskill/literature/`, `.autoreskill/evidence_cart.jsonl` | SOTA matrix and gap synthesis exist |
| `ideation` | Researcher | `autoreskill-papernexus-innovation`, then `autoreskill-ideation-panel` when panel synthesis is needed | `.autoreskill/ideation/`, `.autoreskill/papernexus/`, `.autoreskill/evidence_cart.jsonl` | `IDEA_CATALYST_CONTRACT.json` has `status=ready` and `ideation/EXPERIMENT_IDEA_POOL.json` has 12-15 experiment optimization ideas |
| `idea_gate` | Reviewer | `autoreskill-ideation-panel` or `autoreskill-review-gate` | `.autoreskill/ideation/`, `.autoreskill/reviewer/` | tournament scoreboard, top-3 summary, or idea gate review exists, and the idea pool has a selected idea |
| `experiment_plan` | Orchestrator | `autoreskill-experiment-plan` | `.autoreskill/orchestrator/`, `.autoreskill/planner/` | `innovation_lint.py` and `prelaunch_lint.py` pass |
| `code` | Coder | `autoreskill-implement-experiment` | `.autoreskill/coder/` | experiment index, manifest, and dry-run log exist |
| `experiment` | Coder | `autoreskill-run-experiment` | `.autoreskill/coder/` | experiment ledger plus run metadata or results exist |
| `analysis` | Analyzer | `autoreskill-analyze-results` | `.autoreskill/analyzer/` | claim-evidence matrix and track verdicts exist |
| `review_pressure` | Reviewer | `autoreskill-review-gate` | `.autoreskill/reviewer/` | `REVIEW_FINDINGS.json` is ready and has no unresolved high/critical issues |
| `writing` | Academic Writer | `autoreskill-paper-write` | `.autoreskill/paper/` | `paper/main.tex` exists |
| `submission_ready` | WorkflowGuard/Reviewer | `autoreskill-review-gate` | `.autoreskill/paper/`, `.autoreskill/submission_ready.json` | `main.tex`, `main.pdf`, and ready submission package exist |

Routing rules:

- Execute the child skill named in the job packet first. Use this matrix only to resolve ambiguity or repair a bad packet.
- Prefer PaperNexus-backed material production before panel ideation. The panel interprets evidence; it does not replace source-backed graph evidence.
- Keep `code` and `experiment` under `Coder` unless a job packet explicitly asks Researcher to reconcile scientific intent.
- Do not let a child skill advance `goal_state.json`. After artifacts are written, mark the job complete and run another tick.
- If a linter fails, update the job as failed or retry with the exact blocker instead of manually advancing the stage.
