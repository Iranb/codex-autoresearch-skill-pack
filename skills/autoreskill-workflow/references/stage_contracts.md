# Stage Contracts

Each stage is complete only when its contract authority passes lint.

Direct completion authority:

```bash
python <skill-root>/scripts/contract_lint.py --project <project-root> --stage <stage>
```

This file owns stage completion criteria. It does not own child-skill routing,
heartbeat cadence, job packet schema, PaperNexus tool configuration, or writing
style details. Those decisions live in their dedicated references.

## Table Of Contents

- Applicability Scope
- Global Completion Gates
- Stage Completion Registry
- Literature Discovery Trigger Rule
- Important Guardrails

## Applicability Scope

Before applying the full registry, read `goal_type` and `claim_mode` from
`goal_state.json` or `autopilot_policy.json`.

- `paper_producing_top_tier` with `strong_paper_claims` uses the full contract.
- `paper_producing_light` may treat review/submission hard gates as warnings only
  when the project records a reduced evidence target.
- `standalone_survey`, `writing_style_corpus`, and `diagnostic_or_resource` keep
  provenance, evidence boundaries, and claim limits, but do not need unrelated
  experiment, writing, or submission artifacts.
- When a strong-paper gate is out of scope, lint details should record
  `out_of_scope_with_claim_limits` and point to the recorded claim boundary.

## Global Completion Gates

- Missing artifacts cannot be converted into completion by projection.
- Empty directories are not evidence.
- WorkflowGuard is the only stage-advancing owner.
- Evaluator packets are recommended before high-risk strong-paper transitions:
  `experiment_plan -> code`, `experiment -> analysis`, `analysis -> writing`, and
  `writing -> submission_ready`. Evaluator findings are repair evidence, not
  stage authority.
- Paper-reported baseline metrics are primary when protocol-aligned. A reproduced
  baseline result does not authorize a paper-report improvement claim unless
  `baseline_report_alignment_lint.py` establishes the comparison.
- Source-code evidence supports feasibility, active-code-path, and
  mechanism-transfer claims only. Effectiveness claims require promoted matched
  experiment evidence.
- Random-seed stability validation is capped at three experiment seeds.
  `IDEA_TRACK_SEEDS` are idea/track candidates and do not authorize extra random
  seeds.
- Launchable `PARAM` mechanisms and target sweeps require
  `hpo_search_policy.search_method="dehb_resource_constrained"` in the planning
  packets. Seed, dataset, split, baseline, and metric are protected axes; linear
  or grid tuning is incomplete.
- Paper-code surveys use `.autoreskill/survey/` as their machine-readable audit
  surface. Obsidian notes and `03_CODE_TRANSFER_STORY.md` are derived views.
- Strong-paper `writing` and `submission_ready` require manuscript forensics with
  no blocking numeric, statistical, or presentation findings. AIS style
  impressions carry zero verdict weight.
- Heartbeats are allowed only for external waits described in
  `async_wait_policy.md`; local repairs, stage transitions, planning, review, and
  writing must not be deferred to heartbeat.

## Stage Completion Registry

`init` is complete when project state, policy, capabilities, memory, queues, and
`goal_state.json` exist and `contract_lint.py --stage init` passes.

`topic_search` is complete when broad topic/query/paper evidence exists, search
scope is recorded, raw candidates are screened, and usable papers have graph or
material next actions.

`graph_build` is complete when `graph/GRAPH_BUILD_DECISION.json` is source-backed
for imported rows, every actionable `GRAPH_IMPORT_PLAN` import/supplement row has
completed PaperNexus import/sync status or an explicit source-limited exception,
and material-view rows have material or split-reading evidence. Source-limited
rows must carry claim limits and are not graph-grounded evidence.

`frontier_mapping` is complete when gap, limitation, transfer, negative-evidence,
and experiment-norm evidence exists, or a discovery blocker and claim limit are
recorded.

`literature_review` is complete when SOTA matrix, gap synthesis, and citation
queue exist. If paper-code survey, repository analysis, innovation extraction, or
migration is in scope, `paper_code_transfer_lint.py --required` must pass before
survey artifacts can support downstream ideas.

`ideation` is complete when the pre-idea evidence gate, lane-aware screening,
paper selection scorecard, graph/material plan and status, split-reading evidence
where required, innovation slot map, evidence projection, idea build brief,
GOE audit, proposal graph session or fallback boundary, idea pool, scorecard, and
storyline design pass their lints. Ideas must be academic-paper-oriented and
evidence-bounded; degraded speculative ideation requires explicit approval and
claim limits.

`idea_gate` is complete when the pre-idea gate is still valid or explicitly
degraded, every idea has reviewer score/evidence boundaries, one primary idea is
selected, `IDEA_DECISION_LEDGER.json` owns lifecycle status for every idea, and
`IDEA_TRACK_SEEDS.json` contains only selected, alternate, risk-repair, or
constrained-advance track candidates. Killed or parked ideas cannot launch unless
a later explicit reentry decision changes their lifecycle.

`experiment_plan` is complete when `INNOVATION_PACKET.json`,
`TRACK_PLAN_MATRIX.json`, and `EXPERIMENT_REVIEW_PACKET.json` pass
`innovation_lint.py`, `prelaunch_lint.py`, `track_plan_matrix.py --check`,
selected-projection checks, selected-negative-evidence checks, and required
paper-code, baseline-alignment, and innovation-story lints. The selected idea
and track references must match the current decision ledger and track seeds.
Launch-ready `PARAM` or target-sweep plans must use resource-constrained DEHB,
one scout seed, at most three confirmation seeds, and top 1-2 full-resource
survivor promotion.

`code` is complete when the experiment index, manifests,
`TRACK_IMPLEMENTATION_INDEX.json`, baseline/data audit, clone or worktree proof,
patch proof, selected-projection alignment, and real-data or real-feature smoke
proof are present. Fixture-only proof cannot satisfy launch readiness.

`experiment` is complete when `EXPERIMENT_LEDGER.json` records every attempt,
including failed, regressed, budget-stopped, spec-violating, rollback, and
diagnostic runs, and the ledger contains promoted `best_run` or
`track_best_runs`. Candidate-supported results alone are incomplete. If no active
run remains and no promoted best exists, the latest failed or regressed run must
be analyzed before rerun, rollback, downgrade, or hard stop. At most two same-idea
repair attempts are allowed before changing track, idea, or innovation point.

`analysis` is complete when claim-evidence matrix, track verdicts,
`BEST_RUN_SELECTION.json`, `SCORE_VERIFICATION.json`,
`SPEC_VIOLATION_AUDIT.json`, `IDEA_OUTCOME_SUMMARY.json`, required baseline
alignment, and story updates pass. Candidate-only evidence stays pilot-only.
Strong paper claims require at least three accepted effective innovation points
and `post_analysis_self_audit` with `least_confident_point` and
`largest_possible_misunderstanding`.

`review_pressure` is complete when `REVIEW_FINDINGS.json`,
`REVIEW_REPAIR_LEDGER.json`, and `MULTI_ROUND_REVIEW_GATE.json` record at least
two complete review-repair cycles, cover novelty, soundness, experiment/statistic,
clarity/writing, reproducibility/limitations, claim drift, and scientific
alignment, and no unresolved high or critical issue remains.

`writing` is complete when research representation, grounded write package,
claim verification, manuscript forensics report, top-tier/CCF-A writing audit
when in scope, draft source, required baseline alignment, and innovation-story
sync pass. Strong claims must be citation-backed and cannot rely on
failed/regressed/parked/killed ideas, future work, parameter tuning alone, or
local/reproduced-baseline-only deltas.

`submission_ready` is complete when `main.tex`, `main.pdf`, citation/front-matter
and package gates, `submission_ready.json`, review gate, idea outcome summary,
final manuscript forensics, required baseline alignment, and story synchronization
pass. Strong-paper mode requires no blocking final numeric, statistical, or
presentation findings and at least three accepted effective innovation points.

## Literature Discovery Trigger Rule

Use `literature_discovery_triggers.md` to decide when missing novelty,
closest-prior, baseline/protocol, negative-evidence, transfer-source, cost-norm,
citation, or reviewer-risk evidence requires PaperNexus discovery or material
repair.

Discovery is recall evidence until candidates are screened and graph/material
evidence is captured. Do not trigger fresh discovery during `code` or an active
`experiment` run unless the correct action is rollback to planning or ideation.

## Important Guardrails

- Legacy idea pools without canonical `ideation/PRE_IDEA_EVIDENCE_GATE.json` are
  incomplete until reconciled or rebuilt.
- `IDEA_DECISION_LEDGER.json` owns idea lifecycle decisions.
- `TRACK_PLAN_MATRIX.json` owns bounded B/I/E track search under locked protocol;
  it is not open-ended parameter tuning.
- `EXPERIMENT_LEDGER.json` owns run history and negative evidence.
- Clean restart is allowed only at branch, track, hypothesis, or idea level while
  preserving logs, ledgers, negative evidence, and claim limits.
- Storyline artifacts under `.autoreskill/user_view/innovation_story/` are
  mandatory user-facing views when in scope, but never replace source artifacts.
