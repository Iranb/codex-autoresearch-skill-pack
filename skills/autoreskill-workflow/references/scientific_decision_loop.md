# Scientific Decision Loop

Use this reference after runtime reconciliation produces canonical evidence.
It separates three authorities:

- `REMOTE_RUN.json` and backend state answer whether work ran.
- `RESULT_SUMMARY.json` and metric trajectories answer what was measured.
- `SCIENTIFIC_OUTCOME.json` proposes what that evidence means for one
  predeclared track hypothesis.

`SCIENTIFIC_OUTCOME.json` is evidence, not a stage transition or positive claim.
`research_decision.py` validates and applies it to
`IDEA_DECISION_LEDGER.json`; `contract_lint.py` and `goal_tick.py` alone govern
stage advancement.

## Candidate-To-Evidence Ladder

One selection revision performs one wide, cheap generation pass and one batch
screen: 8-12 lightweight cards, normalized causal-signature deduplication, then
a 3-5 item shortlist. Intervention location, mechanism, predicted dataset/metric
pattern, or discriminating experiment must differ; parameter/module-name
variants become controls, ablations, or `PARAM` work. Only the shortlist receives
full causal, literature, and experiment contracts. Rank hard-gate survivors
deterministically by decisions changed, competing explanations distinguished,
lower falsifier GPU-hours, reusable project components, then lower
novelty/confound risk.

Fill `portfolio_admission_deficit = 4 - active_nonterminal_tracks` with the exact
feasible causally distinct shortlist subset in one batch. Validate each admitted
track through:

| Stage | Evidence and decision |
| ---: | --- |
| 0 | Static path/parser/config checks; diagnostic only |
| 1 | Active-path smoke or small-batch overfit; implementation evidence only |
| 2 | Complete preregistered per-dataset parameter probes at one scout seed, freeze one profile, then paired low-fidelity method screens; pilot evidence |
| 3 | Primary-dataset full-budget matched control; initial support/rejection |
| 4 | Other required-dataset full-budget legs; generalization/scope decision; may run alongside Stage 3 after the Stage-2 pair |
| 5 | DEHB only for supported/ambiguous mechanisms with a sensitivity question |
| 6 | At most three paired baseline/proposed seeds; stability/claim promotion |
| 7 | Small greedy/beam combination of independently supported components |

Baseline calibration is separate `pilot_only` work and may overlap Stage-2
innovation scouts. Before baseline freeze, scouts may rank candidates but cannot
support an improvement claim. After initial support, Stage 4 outranks Stage 5.
A valid negative follows its predeclared route and cannot automatically add
seeds or HPO.

Run `stage_transition_materialize.py` after ledger reconciliation. It is the
only deterministic bridge from a cross-dataset decision to Stage 3/4, from
ledger-backed full-budget support to grouped HPO or Stage 6, and from a finalized
grouped HPO decision to confirmation. `dataset_group_hpo.py` materializes one
row per required dataset and withholds `maximin_signed_delta` until every leg is
terminal-valid and artifact-bound. It may finalize only after registered search
work is exhausted or with an explicit bounded early-stop reason recorded in the
decision.

## Per-Run Contract

Store the sidecar beside the run manifest:

```text
.autoreskill/coder/experiments/<track>/<experiment>/SCIENTIFIC_OUTCOME.json
```

Required identity and evidence:

- `run_id`, `selected_idea_id`, `track_id`, `branch_id`, `queue_row_id`;
- current `selection_fingerprint` or `selected_primary_ref`;
- `launch_identity_hash`;
- `canonical_result_ref` and `raw_evidence_refs`;
- `validity.protocol_valid`, `.spec_valid`, `.evaluator_valid`, and
  `.canonical_result_valid` as explicit booleans;
- `falsifier_evaluation` against the predeclared track contract;
- typed `outcome_class`, `belief_effect`, and `recommended_transition`;
- `evidence_rationale`, `operational_attempt`, `scientific_revision`;
- `claim_effect`, `claim_limits`, adjudicator identity, and timestamp.

The sidecar must use the identity captured before launch. A renamed experiment,
stale selection, changed launch hash, or missing branch/queue lineage is
quarantined rather than guessed.

## Outcome Matrix

| Outcome class | Belief effect | Allowed next step |
| --- | --- | --- |
| `infrastructure_failure` | `none` | `WAIT_OR_RECONCILE_BACKEND` |
| `implementation_failure` | `none` | `REFINE_IMPLEMENTATION` |
| `protocol_invalid` | `none` | `REFINE_PROTOCOL` |
| `budget_stopped_no_scientific_conclusion` | `none` | wait/reconcile or conclude |
| `valid_positive_candidate` | `support_increased` | primary: `PROCEED_TO_ABLATION_OR_CONFIRMATION`; non-primary: `REQUEST_PRIMARY_RESELECTION` |
| `valid_negative` | `support_weakened` or `refuted` | one discriminator, pivot, retire, scope, or conclude |
| `valid_inconclusive` | `still_inconclusive` | one useful discriminator, retire, or conclude |
| `cross_dataset_contradiction` | `scope_narrowed` or `support_weakened` | scope claim, moderator child, or one discriminator |
| `duplicate_or_non_discriminating` | `none` or `still_inconclusive` | retire, conclude, or redesign one discriminator |

Scientific outcome classes require all four validity gates. Operational and
invalid classes cannot weaken a hypothesis. `protocol_invalid` metrics cannot
support a claim. A `valid_negative` cannot be relabeled as implementation repair
unless separate implementation-defect evidence is cited.

## Transition Rules

- Positive primary candidate: queue linked ablation or confirmation. Metric
  improvement alone is not promotion.
- Positive alternate/risk-repair candidate: use
  `REQUEST_PRIMARY_RESELECTION`, record lifecycle `reselection_candidate`, and
  keep `claim_effect=none` or another explicitly non-claim-bearing candidate
  value. The idea gate must explicitly select it as primary,
  advance the selection fingerprint, stale unlaunched old-selection rows,
  rematerialize packets/matrix, and rerun against the frozen matched baseline
  before claim-eligible confirmation. A running old-selection row may reconcile
  as historical evidence but cannot spawn follow-up work.
- Valid negative: update belief, then follow the predeclared negative route. Do
  not tune parameters until the negative disappears.
- Inconclusive: run at most one discriminator by default, and only if its
  possible outcomes change a recorded decision.
- Cross-dataset contradiction: narrow the claim or create one moderator child
  that changes a single causal assumption. The child id must appear in the
  parent's preregistered `moderator_candidates`, and the packet must state both
  the moderator prediction and the experiment that distinguishes it from core
  transfer failure. Do not average away the conflict or invent a moderator after
  seeing the result.
- Before a mechanism-level negative, verify per-dataset 2-3-value coverage for
  the load-bearing parameter and comparable effective-strength telemetry. A
  one-value failure scopes that parameterization only. Different human-selected
  settings by dataset require a reviewed `dataset_calibrated` profile.
- Child tracks cite `parent_track_id`, `derived_from_run_id`, and one
  `hypothesis_delta`. Renaming or multi-axis edits are not new hypotheses.
- `PARAM` gains remain parameter evidence and cannot upgrade mechanism novelty.

## Separate Budgets

`operational_attempt` counts retries of the same infrastructure,
implementation, parser, or protocol failure signature. The default maximum is
two. Repeating the same signature after that requires rollback, a different
repair level, or user/resource intervention.

`scientific_revision` counts a changed hypothesis boundary or added
discriminating test. Each track defaults to at most two revisions. It is not
incremented by crashes or environment repairs. An inconclusive track receives
at most one discriminator by default. Further valid negative evidence retires,
scopes, pivots, or concludes the track rather than opening another repair loop.

## Commands

```bash
python <skill-root>/scripts/research_decision.py --project <root> --run-id <run> --check
python <skill-root>/scripts/research_decision.py --project <root> --run-id <run> --write
python <skill-root>/scripts/research_decision.py --project <root> --all-terminal --check
python <skill-root>/scripts/research_decision.py --project <root> --all-terminal --write
python <skill-root>/scripts/research_decision.py --project <root> --program-recovery-status --check
python <skill-root>/scripts/research_decision.py --project <root> --activate-program-revision --check
python <skill-root>/scripts/research_decision.py --project <root> --activate-program-revision --write
python <skill-root>/scripts/research_decision.py --project <root> --replenishment --check
python <skill-root>/scripts/research_decision.py --project <root> --replenishment --write
```

`--check` is read-only. `--write` derives a deterministic decision id from the
run, outcome hash, and prior track revision. Reapplying the same outcome is a
no-op. A successful write updates per-track state in the existing idea ledger
and requests matrix/queue reconciliation; it never launches work.

The replenishment form is a separate bounded ledger transaction. It requires an
active enforced program contract, an unresolved program-scientific status,
positive method deficit, no fillable committed method candidate, no
decision-bearing ready/live row, and remaining contract allocation. Candidate
construction is local and is not GPU-capacity-gated; resource fitting starts only
after later track admission and row materialization. `monitor_only`,
`monitor_sync`, resource diagnostics, and explicitly nonblocking audit rows are
not decision-bearing. Its deterministic basis hash prevents an unchanged
zero-active project from repeatedly regenerating ideas.

When the prior route is terminal for a track but nonterminal for the project,
`--program-recovery-status --check` separates direct authorization, contract
allocation, and event consumption. An authorized route first commits a reviewed
replacement contract, then atomically activates a new program revision. The
activation archives the old status, route, selection, and portfolio; it resets
only the new revision to `unresolved`. One revision-scoped replenishment event
then authorizes an 8-12-card pool and 3-5-item shortlist whose pool and scorecard
carry `program_revision_id` and `program_claim_contract_sha256`. Primary
selection, track seeds, admission, and experiments are later actions. A present
event with missing or stale supply is resumed, not charged again. Missing direct
authority, cap zero/exhaustion, mismatched review hash, or
`terminal_for_project=true` remains a hard stop.

After applying a decision, rerun `run_reconcile.py` so
`EXPERIMENT_LEDGER.json` records the accepted decision id without losing prior
scientific fields.

## Terminal Programs

When all active tracks are terminal, add `terminal_program_context` to the idea
ledger with remaining claim scope, mandatory downgrade, why more work lacks
decision value under the budget, target stage, and independent evaluator refs
for strong-paper workflows. Then run `research_decision.py --all-terminal`.

The resulting `program_decision` is valid only when:

- every active track has a terminal state and evidence refs;
- no `ready`, `planned`, `claimed`, `submitting`, `needs_sync`, or `running`
  queue row remains;
- every terminal run has an applied scientific decision;
- no promised mandatory confirmation remains;
- negative/inconclusive decisions set `improvement_claim_allowed=false`.

Allowed terminal statuses are `supported_result_available`,
`core_hypotheses_refuted`, `no_valid_gain`,
`inconclusive_budget_exhausted`, and `protocol_unresolvable`. A valid negative
program may enter analysis to report limitations and negative evidence, but it
cannot create an abstract/table/conclusion improvement claim.
