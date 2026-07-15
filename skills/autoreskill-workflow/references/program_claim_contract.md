# Program Claim Contract

`orchestrator/PROGRAM_CLAIM_CONTRACT.json` is the project-level authority for
the scientific question that experiment planning must answer. It owns target
datasets, metrics, baseline comparison requirements, method eligibility,
parameter-transfer policy, promotion rules, and bounded search budgets. It does
not own selected ideas, experiment state, result interpretation, belief, or
terminal program status.

Existing projects without this file remain in `legacy` behavior. `shadow` mode
reports blockers and projected routing without mutating packets or queues.
`enforced` mode requires every regenerated packet, queue row, and scientific
outcome to bind the current contract revision and semantic SHA-256.

## Core Rules

- `cross_dataset_method` requires at least two required datasets with `primary`
  and `contrast` roles.
- Paper-report alignment is recorded independently from matched reproduced
  baseline evidence. A matched reproduced gain does not establish a gain over
  the paper report.
- At most four tracks may be active, the method target cannot exceed that
  capacity, and no more than three random seeds may enter confirmation.
- Targeted replenishment remains finite and may be explicitly budgeted from
  zero through eight transactions; each transaction still requires its own
  scientific-authority and deduplication checks.
- The normal default is one transaction. A larger value is valid only when it is
  explicit in the project contract; a replacement contract must also be covered
  by a matching direct-user cap in
  `control/REPLENISHMENT_INTERVENTION_REQUEST.json`. Idle capacity and model
  judgment are never budget authority.
- Parameter calibration changes one load-bearing parameter at a time. Each
  required dataset normally evaluates two or three preregistered values at one
  fixed scout seed. Seed repetition never substitutes for value coverage.
- Every calibration observation references a local immutable result artifact,
  records its SHA-256, and binds `selection_metric`, `train_only|unlabeled_target`
  scope, `target_labels_used=false`, and `test_outcome_used=false`. A metadata
  assertion without matching artifact provenance is not calibration evidence.
- `shared_absolute` freezes one common raw value across datasets.
- `shared_normalized` freezes one common dimensionless setting under one
  label-free formula; formula-derived raw values may differ by dataset.
- Shared-mode formulas may not contain required dataset ids or non-empty
  per-dataset formula-override maps. Such branching is
  `dataset_calibrated`, not a shared method formula.
- Different human-selected settings by dataset require `dataset_calibrated`.
- Every enforced cross-dataset promotion rule declares
  `dataset_aggregation=predeclared`, uses
  `robust_objective=maximin_signed_delta`, and supplies one finite
  `worst_dataset_floor_by_dataset` value for every required dataset. Missing
  floors fail activation instead of letting a favorable dataset hide a
  regression.
- A single value is legal only as `zero_shot_only` and cannot establish a
  calibrated-mechanism negative.
- Before initial mechanism support, one track may consume at most one parameter
  calibration group. A second parameter requires a named sensitivity question,
  prior support, and remaining GPU-hour/revision budget.
- An active/enforced contract records finite positive project and per-track
  parameter-probe GPU-hour caps. Missing or unbounded caps fail activation.

## Commands

Generate a draft to edit:

    python3 scripts/program_claim_contract.py template --project <project-root>

Validate without mutation:

    python3 scripts/program_claim_contract.py check --project <project-root> --input <candidate.json>

Commit with compare-and-swap:

    python3 scripts/program_claim_contract.py commit --project <project-root> \
      --input <candidate.json> \
      --expected-current-sha256 <sha256> \
      --expected-revision <revision>

Use `set-mode` to move through `legacy`, `shadow`, and `enforced`. Use
`supersede` to close an old contract without deleting historical evidence.
Contract events are appended to
`orchestrator/program_claim_contract_events.jsonl`.

For a replacement contract, structural validation additionally requires
`replacement_basis_decision_id`, `unresolved_paper_decision_id`, and source refs
for the intervention, unresolved decision, prior evidence, and independent
review. Commit-time validation requires the old route id and authorized cap to
match, `authorization.source=direct_user_instruction`, and an approving review
whose `reviewed_semantic_sha256` equals the candidate contract SHA. Use
`check --require-replacement-authority` to inspect this gate without mutation.
Committing the contract does not reset scientific state; activate its program
revision separately through `research_decision.py` so the prior route is archived
rather than overwritten.

Result-derived `unresolved`, `screened`, `supported`, `promoted`, `scoped`,
`refuted`, or `budget_exhausted` state belongs only in
`ideation/IDEA_DECISION_LEDGER.json`.
