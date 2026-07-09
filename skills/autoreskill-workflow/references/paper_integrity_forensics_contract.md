# Paper Integrity Forensics Contract

This contract adds a final manuscript-level integrity gate for paper-producing
AutoResearch workflows. It checks the submitted manuscript surface against
deterministic evidence available in `.autoreskill/`; it is not an AI-authorship
detector, misconduct detector, or replacement for peer review.

## Table Of Contents

- Scope
- Observability Levels
- Required Artifacts
- Check Families
- Blocking Policy
- Repair Guidance

## Scope

Required by default for:

- `goal_type=paper_producing_top_tier`
- `claim_mode=strong_paper_claims`

For `paper_producing_light`, findings are warnings unless the project policy sets
`paper_forensics_minor_blocks=true` or the user explicitly asks for top-tier
readiness. For `standalone_survey`, `writing_style_corpus`, and
`diagnostic_or_resource`, keep provenance and claim limits but do not block on
paper-forensics artifacts.

The only stage authority is `scripts/contract_lint.py`. Raw findings and reports
are evidence consumed by that authority.

## Observability Levels

- `L0`: manuscript source is missing or only a non-structured artifact is
  available. Strong-paper mode fails closed because span-level checks cannot run.
- `L1`: `paper/main.tex` is available. Numeric, statistical, presentation, and
  style-span checks run over deterministic source spans.
- `L2`: result manifests and richer structured evidence are available. Future
  extensions may compare manuscript claims against run manifests, but v1 does not
  require experiment reproduction.

Findings above the current observability level must be downgraded or omitted.

## Required Artifacts

`paper_forensics_lint.py` writes:

- `.autoreskill/paper/PAPER_CLAIM_LEDGER.json`
- `.autoreskill/paper/PAPER_FORENSICS_FINDINGS.json`
- `.autoreskill/paper/PAPER_FORENSICS_REPORT.json`
- `.autoreskill/paper/PAPER_FORENSICS_REPORT.md`
- `.autoreskill/paper/AIS_STYLE_IMPRESSIONS.json`

`PAPER_CLAIM_LEDGER.json` records stable claim ids, source spans, locations,
span hashes, type, confidence, value metadata when parseable, and observability
level.

`PAPER_FORENSICS_REPORT.json` must include `complete`, `status`,
`overall_verdict`, `required`, `scope`, `observability_level`,
`input_hashes`, `finding_counts`, `finding_hashes`, `downgraded_counts`,
`blocking_findings`, `warnings`, `missing`, `ais_count`, and artifact paths.

## Check Families

Numeric self-consistency:

- headline numbers in abstract/introduction/conclusion that do not appear in
  table cells or `SCORE_VERIFICATION`;
- relative or absolute improvement arithmetic that does not match from/to
  values.

Statistical self-consistency:

- GRIM-style impossible percentages over integer `N`;
- impossible standard deviation for bounded percent metrics;
- p-value/test-statistic mismatch when the statistic is parseable.

Presentation residue:

- exact strings such as `as an AI language model`, `[citation needed]`,
  `lorem ipsum`, `[insert `, or similar template/pipeline leftovers;
- duplicate numeric table signatures.

AIS style impressions:

- defensive hedge density and similar writing-style cues are reported only under
  `AIS_STYLE_IMPRESSIONS.json`;
- every AIS impression has `zero_weight=true` and `verdict_weight=0`.

Semantic-review handoff:

- method/experiment scope drift, SOTA-without-baseline, citation context
  errors, proof gaps, evaluation leakage, and LLM-judge validity remain reviewer
  or evaluator findings unless a deterministic helper is added later.

## Blocking Policy

In strong-paper mode, any final `major` or `critical` verdict-bearing finding
blocks `writing` and `submission_ready`. `minor` findings warn by default and can
block only when `autopilot_policy.json` sets
`paper_forensics_minor_blocks=true`.

AIS style impressions never block, never contribute to integrity verdicts, and
must not be described as AI authorship evidence.

Every blocking finding must cite at least one manuscript span or structured
artifact ref. Checks with high false-positive risk must be capped at `minor`
unless a future validated implementation lowers that risk.

## Repair Guidance

Resolve findings by repairing the manuscript, correcting the table/result
artifact, or downgrading the claim. Do not resolve a finding by deleting evidence
boundaries, hiding limitations, or upgrading unsupported claims.
