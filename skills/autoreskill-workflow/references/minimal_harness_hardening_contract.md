# Minimal Harness Hardening Contract

This reference captures the small set of audit objects added from the 2026
AutoResearch method review. It is intentionally narrower than the full stage
contract. Apply it only where the current `goal_type` and `claim_mode` require
paper-claim evidence.

## Scope

Required by default for:

- `goal_type=paper_producing_top_tier`
- `claim_mode=strong_paper_claims`

For `paper_producing_light`, use the same fields as warnings unless the user
asks for top-tier readiness. For `standalone_survey`, `writing_style_corpus`, and
`diagnostic_or_resource`, keep provenance and claim limits but do not require
experiment, review, or submission fields that are irrelevant to the goal.

When a strong-paper gate is skipped because the goal is out of scope,
`contract_lint.py` should report the skipped gate under
`details.out_of_scope_with_claim_limits[]`. The entry must identify the skipped
items and show where `claim_limits`, `out_of_scope_claim_limits`, or equivalent
scope boundaries are recorded. A skipped gate without claim limits is still a
warning because the workflow otherwise cannot distinguish "not applicable" from
"missing evidence".

## Experiment Planning

Each `TRACK_PLAN_MATRIX` row that can launch or support a claim should include:

- `certification_policy`: what must be true before this row can support a claim.
- `intervention_axis`: the scientific variable changed by the track.
- `critical_evidence_requirements`: minimum evidence needed for promotion.
- `negative_knowledge_consultation`: negative evidence or failure patterns
  consulted before launching.

The matrix or top-level plan should also keep `selected_idea_id`, B/I/E budget,
idea-decision refs, selected-projection alignment, and a stable
`selection_fingerprint` or `selected_primary_ref`. Downstream packets and active
track rows must carry the same reference so stale projections cannot silently
continue after idea_gate selects, parks, or kills a different idea/track.

## Experiment Ledger

Every failed, regressed, budget-stopped, spec-violating, diagnostic, or
not-promoted row in `EXPERIMENT_LEDGER` should keep:

- `failure_class`
- `failure_diagnosis` with `primary_cause`, `evidence_sufficiency`,
  `intervention_level`, `repair_route`, and `repeated_failure_key` when the
  route repeats the same idea
- `next_action`
- selected idea/track lineage
- result summary path when metrics exist

Negative evidence is useful only when it remains tied to the selected idea,
track, branch/iteration/version lineage, and reentry policy.

## Score Verification

`SCORE_VERIFICATION.json` should include:

- `disaggregated_effects`: all locked metric components, not only a favorable
  scalar. Critical slices that regress must downgrade or block the affected
  claim even if an aggregate score improves.
- `mechanism_support`: whether the observed gains support the proposed
  mechanism. Outcome-only evidence cannot authorize strong mechanism wording.
- `validation_to_test_transfer`: whether validation choices transfer to the test
  or target protocol. Unknown or failed transfer cannot support a strong test
  claim.
- `numeric_measurement_registry`: metric units, parser source, baseline source,
  and measurement provenance.

## Idea Outcome Summary

`IDEA_OUTCOME_SUMMARY.json` should include:

- evidence refs for every effective innovation point;
- `mechanism_status` for each point;
- `claim_permission` for each point or idea outcome;
- `negative_knowledge_summary` describing failures consulted and how claims were
  bounded.
- `post_analysis_self_audit` with `least_confident_point` and
  `largest_possible_misunderstanding`, explicitly naming the weakest part of the
  current conclusion and the largest possible blind spot or mistaken framing.

Parameter tuning, diagnostics, and resource-fill runs do not count as effective
innovation points unless idea_gate explicitly reclassifies them as a new
mechanism with evidence boundaries.

## Review Findings

`REVIEW_FINDINGS.json` should include the usual reviewer axes plus:

- `claim_drift`: claims that moved beyond the evidence or selected idea.
- `scientific_alignment`: mismatch among problem, mechanism, protocol, metrics,
  and evidence.
- `defensive_underclaim`: unnecessary caveats or apology framing that weakens a
  supported contribution.

These axes repair different failure modes and should not be collapsed into a
generic clarity issue.

## Subjective Top-Tier Rubrics

Some high-impact decisions include subjective quality: idea taste, story
coherence, Figure 1 clarity, reviewer excitement, and writing posture. Score
these only when they affect a top-tier paper-producing stage. Do not use them as
generic style decoration.

A rubric row should contain:

- `axis`: what is being judged, such as novelty tension, mechanism elegance,
  story coherence, reviewer risk, or front-matter claim posture.
- `weight`: why this axis matters for the target venue or stage.
- `score`: bounded local score, preferably with a short scale definition.
- `evidence_ref`: paper, experiment, figure, draft, or reviewer finding that
  justifies the score.
- `reviewer_gap`: what a strong reviewer would still object to.
- `required_repair`: concrete revision, downgrade, evidence repair, or no-op.

Rubrics are evidence and repair guidance. They are not independent stage
authorities unless a stage contract explicitly names them.

## Writing Claim Verification

`PAPER_CLAIM_VERIFICATION.json` should include:

- `claim_drift_status`
- `scientific_alignment_status`
- `numeric_grounding_status`
- `non_defensive_writing_status`

`CCFA_WRITING_AUDIT.md` should include a `Non-Defensive Writing Pass` section for
manuscript work. The pass removes unnecessary disclaimers, converts defensive
limitations into positive scope statements, replaces vague hedging with evidence
precision, and preserves necessary uncertainty. For top-tier targets, the pass
must explicitly record:

- `Necessary Limitations Preserved`: real limits, missing evidence, correlation
  limits, and target-domain boundaries remain visible.
- `Claim Upgrades Blocked`: polishing did not convert weak, pilot, or
  correlative evidence into strong claims.
- `Top-Tier Reviewer Risk` or `Front Matter Claim Posture`: title, abstract,
  introduction, and contribution wording state the supported contribution
  directly while keeping evidence boundaries auditable.

## Paper Integrity Forensics

`PAPER_FORENSICS_REPORT.json` should be produced by
`scripts/paper_forensics_lint.py` before strong-paper `writing` or
`submission_ready` passes. It is a manuscript-level self-consistency and residue
gate, not an AI-authorship detector.

The report should summarize:

- `PAPER_CLAIM_LEDGER.json`: deterministic source spans and hashes from
  `paper/main.tex`.
- Audit fields: `input_hashes`, deterministic `finding_hashes`,
  `finding_counts`, and `downgraded_counts`.
- Numeric self-consistency: headline numbers, table cells, and relative
  improvement arithmetic.
- Statistical self-consistency: GRIM-style impossible percentages, impossible
  bounded variance, and p-value/statistic mismatches when parseable.
- Presentation residue: exact template or pipeline strings and duplicate table
  signatures.
- `AIS_STYLE_IMPRESSIONS.json`: defensive/style cues with `zero_weight=true` and
  `verdict_weight=0`.

For `paper_producing_top_tier` plus `strong_paper_claims`, major or critical
verdict-bearing forensic findings block the stage. Minor findings warn unless
`paper_forensics_minor_blocks=true`. AIS style impressions never block and must
not be presented as evidence of AI authorship.

## Control Plane

`goal_state.json` or `autopilot_policy.json` should record:

- `goal_type`
- `claim_mode`
- `claim_limits` or `out_of_scope_claim_limits` when the goal is not strong
  paper production but strong-paper gates are skipped
- `project_agents_policy_hash`

The hash prevents repeated project `AGENTS.md` rewrites when the required policy
surface is already current.

## Harness Pruning

New harness rules should not grow monotonically. Before adding a required gate or
artifact, apply the minimal artifact test:

1. Does it own a state transition that no existing authority owns?
2. Does it improve recovery across interruptions, failed runs, or role handoffs?
3. Does it block a known expensive failure that existing lints miss?

If the answer is no, keep the idea as guidance, a rubric item, or an optional
trace entry instead of a mandatory artifact.

Remove or downgrade a gate when it duplicates another authority, does not change
stage decisions, mostly emits noisy findings, or a better model/tool/script now
handles the failure mode reliably. Do not delete hard gates that protect
scientific claims without regression evidence or explicit user approval.
