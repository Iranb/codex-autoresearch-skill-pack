# Minimal Harness Hardening Contract

This reference indexes the cross-stage audit fields added by the 2026
AutoResearch method review. It is not a second stage contract. Stage completion
still belongs to `stage_contracts.md` plus `contract_lint.py`.

## Table Of Contents

- Scope
- Field Index
- Pruning Rule
- Removal Or Downgrade Rule

## Scope

Required by default for:

- `goal_type=paper_producing_top_tier`
- `claim_mode=strong_paper_claims`

For `paper_producing_light`, use these fields as warnings unless the user asks
for top-tier readiness. For `standalone_survey`, `writing_style_corpus`, and
`diagnostic_or_resource`, keep provenance and claim limits but do not require
irrelevant experiment, review, or submission fields.

When a strong-paper gate is skipped because the goal is out of scope,
`contract_lint.py` should report the skipped gate under
`details.out_of_scope_with_claim_limits[]` and identify the recorded claim
boundary.

## Field Index

`goal_state.json` or `autopilot_policy.json`:

- `goal_type`
- `claim_mode`
- `claim_limits` or `out_of_scope_claim_limits`
- `project_agents_policy_hash`

`TRACK_PLAN_MATRIX.json` launchable or claim-supporting rows:

- `selected_idea_id`
- `selection_fingerprint` or `selected_primary_ref`
- `bie_config`
- `certification_policy`
- `intervention_axis`
- `critical_evidence_requirements`
- `negative_knowledge_consultation`

`INNOVATION_PACKET.json` and `EXPERIMENT_REVIEW_PACKET.json`:

- selected idea and track refs matching `IDEA_DECISION_LEDGER.json`
- locked baseline, dataset, split, metric, and protocol
- `stability_seed_policy` with at most three experiment seeds
- `hpo_search_policy` for `PARAM` mechanisms or target sweeps
- claim limits and evidence boundaries

`EXPERIMENT_LEDGER.json` failed, regressed, budget-stopped, spec-violating,
diagnostic, or not-promoted rows:

- `failure_class`
- `failure_diagnosis`
- `next_action`
- selected idea/track lineage
- branch, iteration, or version lineage when available
- result summary path when metrics exist
- retire reason when applicable

`SCORE_VERIFICATION.json`:

- `disaggregated_effects`
- `mechanism_support`
- `validation_to_test_transfer`
- `numeric_measurement_registry`
- paper-reported baseline authority when strong improvement claims are made

`IDEA_OUTCOME_SUMMARY.json`:

- evidence refs for every effective innovation point
- `mechanism_status`
- `claim_permission`
- `negative_knowledge_summary`
- `post_analysis_self_audit.least_confident_point`
- `post_analysis_self_audit.largest_possible_misunderstanding`

`REVIEW_FINDINGS.json`:

- `claim_drift`
- `scientific_alignment`
- `defensive_underclaim`

`PAPER_CLAIM_VERIFICATION.json`:

- `claim_drift_status`
- `scientific_alignment_status`
- `numeric_grounding_status`
- `non_defensive_writing_status`

`CCFA_WRITING_AUDIT.md` for concrete top-tier/CCF-A manuscript work:

- `Non-Defensive Writing Pass`
- `Necessary Limitations Preserved`
- `Claim Upgrades Blocked`
- `Top-Tier Reviewer Risk` or `Front Matter Claim Posture`

`PAPER_FORENSICS_REPORT.json`:

- produce it through `scripts/paper_forensics_lint.py`;
- use `paper_integrity_forensics_contract.md` for check families and blocking
  policy.

## Pruning Rule

Before adding or promoting any required gate, artifact, heartbeat, queue, or
prompt block, answer:

1. Does it own a state transition no existing authority owns?
2. Does it improve recovery after interruption, failed runs, or role handoff?
3. Does it block a known expensive failure that existing lints miss?

If not, keep it as optional guidance, a rubric row, or a trace note.

## Removal Or Downgrade Rule

Remove or downgrade a gate when it duplicates another authority, does not change
stage decisions, mostly emits noisy findings, or a better model/tool/script now
handles the failure mode reliably. Do not delete hard gates that protect
scientific claims without regression evidence or explicit user approval.
