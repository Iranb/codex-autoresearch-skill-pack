# Stage Contracts

Each stage is complete only when its contract authority passes lint.

| Stage | Owner | Authority | Complete when |
| --- | --- | --- | --- |
| `init` | WorkflowGuard | `.autoreskill/goal_state.json` | project, policy, capabilities, memory, queues exist |
| `topic_search` | Researcher | literature discovery packet/run state | broad topic/query/paper evidence exists and the search scope is recorded |
| `graph_build` | Researcher | `graph/GRAPH_BUILD_DECISION.json` | `decision=complete` and `source_backed_graph_claim=true` |
| `frontier_mapping` | Researcher | frontier artifacts | gap/limitation/transfer/negative-evidence and experiment-norm evidence exists, or a discovery blocker/claim limit is recorded |
| `literature_review` | Researcher | lit review artifacts | SOTA matrix, gap synthesis, and citation queue exist |
| `ideation` | Researcher | `ideation/PRE_IDEA_EVIDENCE_GATE.json` + `ideation/INNOVATION_SLOT_MAP.json` + `papernexus/proposal_graph_session.json` when available + `ideation/EXPERIMENT_IDEA_POOL.json` | target-domain, near-neighbor, and far-neighbor discovery all have persisted broad attempts; `pre_idea_discovery_config_lint.py`, lane-aware screening, PaperNexus split-reading evidence, and innovation slot map pass lint; if `proposal_graph_session` is available, a committed proposal graph session passes lint or a diagnosis/fallback boundary is explicit; then `idea_pool_lint.py` passes with 12-15 academic-paper-oriented ideas tied to innovation slots and proposal graph provenance where used. For method ideas, target-domain evidence anchors problem/baseline/protocol/overlap risk, while the primary method mechanism is near-neighbor, far-neighbor, or cross-lane transfer unless a source-backed audit proves no current-field occurrence. An approved degraded gate may pass only when claim limits and evidence boundaries are recorded in both the pool and scorecard |
| `idea_gate` | Reviewer/Critic | pre-idea gate + review scorecard + `ideation/EXPERIMENT_IDEA_POOL.json` | pre-idea gate still passes or has explicit approved degraded status, scorecard compares every idea against target/near/far evidence or records the missing evidence boundary, one idea is selected, weakest assumptions and evidence debt are explicit, selected method source is not target-domain-only for the main method claim, and remaining selected-idea novelty/baseline/protocol evidence is routed to `experiment_plan` |
| `experiment_plan` | Orchestrator | `orchestrator/INNOVATION_PACKET.json` + `planner/EXPERIMENT_REVIEW_PACKET.json` | `innovation_lint.py` and `prelaunch_lint.py` pass: selected ideation idea is consumed, proposal graph provenance is retained when present, an innovation search contract is bound, primary method source role and neighbor transfer mechanism are preserved, target-domain overlap risk is closed, and evidence boundaries, locked baseline/eval/metric/data, one-variable plan, budget/falsifier, promotion gate, and controller/proposal-graph/fallback design review are present |
| `code` | Coder | experiment manifest/dry-run | dry-run proof, comparable configs, selected idea id, locked protocol, and source snapshot |
| `experiment` | Researcher/Coder | run metadata/ledger | execution proof, full ledger trajectory, promoted `best_run` or `track_best_runs`, and no unreconciled run; `candidate_supported` alone is incomplete |
| `analysis` | Analyzer | claim matrix/verdicts | results proof plus claim-evidence matrix tied to ledger trajectory and promoted track best; candidate-supported evidence is marked pilot-only |
| `review_pressure` | Reviewer | `reviewer/REVIEW_FINDINGS.json` | high/critical issues closed, waived, or claims downgraded |
| `writing` | Academic Writer | paper draft/write package | manuscript exists and strong claims are supported |
| `submission_ready` | WorkflowGuard/Reviewer | `submission_ready.json` | `main.tex`, `main.pdf`, citation/front-matter/package gates ready |

Do not convert missing artifacts into "complete" by projection. Use autopilot repair, degradation, rollback, or hard stop.

Literature discovery trigger rule:

- Treat literature discovery as reusable evidence repair across `topic_search`, `graph_build`, `frontier_mapping`, `literature_review`, `ideation`, `idea_gate`, `experiment_plan`, `analysis`, `review_pressure`, `writing`, and `submission_ready`.
- Queue another PaperNexus discovery/material job whenever required novelty, closest-prior, baseline/protocol, negative-evidence, transfer-source, cost-norm, citation, or reviewer-risk evidence is missing, stale, or too generic.
- Do not trigger fresh discovery during `code` or an active `experiment` run unless the correct action is to roll back to planning/ideation; implementation and training should not silently change the literature basis.
- Use `references/literature_discovery_triggers.md` as the detailed trigger map.

Important guardrails:

- Empty directories are never completion evidence.
- Existing legacy idea pools without `ideation/PRE_IDEA_EVIDENCE_GATE.json` are incomplete until `legacy_pre_idea_reconcile.py` records repair state or the missing pre-idea evidence artifacts are built. A gate under `orchestrator/` or another non-canonical path is a misplaced gate, not completion evidence.
- `code` needs `EXPERIMENT_INDEX.md`, at least one `EXPERIMENT_MANIFEST.json`, baseline/data audit, clone/worktree proof plus patch proof from `baseline_clone_lint.py`, non-fixture real-data or real-feature smoke proof, and `experiment_real_readiness_lint.py` completion.
- `experiment` needs an experiment ledger plus run metadata/results for every attempt, including failed and regressed attempts, and a promoted ablation/confirmation-backed best run before automatic analysis.
- `experiment` also needs baseline clone/patch proof and baseline-protocol launch preflight before spending GPU time; off-protocol probes must remain diagnostic and cannot be expanded into sweeps.
- `analysis` needs claim-evidence and track verdicts tied back to the ledger, not only the best metric; candidate-supported results cannot support stable improvement claims.
- `review_pressure` cannot pass with unresolved high/critical findings.
