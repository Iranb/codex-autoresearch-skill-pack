# Resource-Constrained DEHB Policy

Use this policy when an experiment plan contains a `PARAM` mechanism or any
target sweep. It adapts DEHB (Differential Evolution plus Hyperband) for scarce
GPU budgets: explore mixed continuous/discrete spaces with differential
evolution, spend only low fidelity on most candidates, then promote very few
survivors to full-budget confirmation.

## Design Goal

The policy is for efficient parameter search, not paper-level innovation.
`PARAM` work may select a viable configuration or support an ALGO/CODE
mechanism, but it cannot become a core contribution unless `idea_gate`
explicitly reclassifies it as a new source-backed mechanism.

Innovation mechanism tuning is validation-ladder Stage 5, not a default response
to a weak result. Keep it `activation_status=pending_support` until the mechanism
has initial support or explicit parameter ambiguity, a concrete sensitivity
question, a locked protocol/baseline reference, and remaining GPU-hour budget.
Terminal-negative/refuted/retired mechanisms are ineligible. Cross-dataset Stage
4 evidence outranks Stage 5 after initial support.

`tuning_target=baseline_calibration` is separate `pilot_only` claim-closing work,
not innovation Stage 5. It may overlap independent Stage-2 scouts, but survivors
must rerun against the frozen matched baseline before claim promotion.

Reference: [DEHB, IJCAI 2021](https://www.ijcai.org/proceedings/2021/296).

## Required `hpo_search_policy`

Record this object in both `orchestrator/INNOVATION_PACKET.json` and
`planner/EXPERIMENT_REVIEW_PACKET.json` whenever `mechanism_type="PARAM"`.
For ALGO/CODE plans without tuning, record `{"search_method":
"not_applicable"}` or omit the object.

```json
{
  "search_method": "dehb_resource_constrained",
  "search_role": "PARAM",
  "tuning_target": "baseline_calibration|mechanism_parameterization",
  "activation_status": "pending_support|eligible",
  "sensitivity_question": "required when mechanism_parameterization is eligible",
  "eligible_belief_states": ["initial_support", "explicitly_ambiguous"],
  "current_belief_state": "",
  "baseline_freeze_or_calibration_ref": "",
  "remaining_gpu_hours": 0,
  "budget_tier": "micro|small|standard",
  "resource_axis": "epochs|steps|data_fraction",
  "trial_budget": {
    "max_scout_trials": 12,
    "max_full_budget_trials": 2,
    "max_total_gpu_hours": 0,
    "user_approved_higher_budget": false
  },
  "rungs": [
    {"name": "r0", "resource_fraction": 0.1, "promotion": "top_fraction_or_top_k"},
    {"name": "r1", "resource_fraction": 0.3, "promotion": "top_fraction_or_top_k"},
    {"name": "r2", "resource_fraction": 1.0, "promotion": "top_k"}
  ],
  "search_space_audit": {
    "max_search_dimensions": 6,
    "protected_axes": ["random_seed", "dataset", "split", "baseline", "metric"],
    "dimensions": [
      {
        "name": "",
        "type": "categorical|ordinal|integer|float|log_float|boolean",
        "bounds_or_choices": [],
        "default_or_prior": "",
        "rationale": "",
        "conditional_on": ""
      }
    ]
  },
  "dehb_config": {
    "population_size": 8,
    "eta": 3,
    "initial_design": "baseline_default_plus_small_random",
    "mutation_strategy": "differential_evolution_survivors",
    "categorical_strategy": "mutate_among_declared_choices",
    "conditional_dimension_strategy": "inactive_dimensions_are_not_sampled"
  },
  "execution_policy": {
    "mode": "elastic_async",
    "max_concurrent_scouts": "auto",
    "max_concurrent_full_budget_trials": 2,
    "promotions_require_comparable_rung_metrics": true,
    "scheduler_ref": "experiment/NEXT_EXPERIMENT_QUEUE.json"
  },
  "baseline_calibration_policy": {
    "validation_only_search": true,
    "freeze_before_claim_promotion": true,
    "equal_or_shared_tuning_budget": true,
    "provisional_overlap_evidence_tier": "pilot_only"
  },
  "seed_policy": {
    "seed_is_search_axis": false,
    "scout_random_seed_count": 1,
    "matched_seed_protocol": true,
    "max_total_random_seeds": 3
  },
  "dataset_group_hpo": {
    "required_dataset_ids": ["dataset-a", "dataset-b"],
    "frozen_parameter_profile_sha256": "",
    "parameter_transfer_contract_sha256": "",
    "stage2_support_ref_by_dataset": {"dataset-a": "", "dataset-b": ""},
    "full_budget_support_ref_by_dataset": {"dataset-a": "", "dataset-b": ""},
    "fixed_scout_seed": 0,
    "robust_objective": "maximin_signed_delta",
    "no_regression_constraints_by_dataset": {"dataset-a": 0, "dataset-b": 0},
    "incomplete_trial_is_infeasible": true
  },
  "promotion_rule": {
    "promote_top_k": 1,
    "max_promote_top_k": 2,
    "full_resource_before_candidate": true,
    "metric_policy_ref": "planner/EXPERIMENT_REVIEW_PACKET.json:metric_policy"
  },
  "kill_condition": "Stop a trial on NaN/OOM/parser failure/material regression; stop PARAM branch after the declared DEHB budget without promoted improvement.",
  "claim_boundary": "Low-fidelity HPO scouts are pilot/search evidence only; final claims require full-resource plus ablation or confirmation under the locked metric policy."
}
```

For an enforced `cross_dataset_method`, this block is mandatory once Stage 5 is
eligible. One DEHB configuration creates one leg per required dataset at the
same fidelity; it cannot rank until all legs are valid. Dataset-specific scalar
dimensions are forbidden. Both support maps must cover every required dataset,
and their refs plus the frozen-profile and transfer-contract hashes must resolve
before a trial is eligible. A calibrated-method claim may tune shared parameters
of the common calibration algorithm, but DEHB cannot convert that evidence into
zero-shot portability.
Use `autoreskill-run-experiment/scripts/dataset_group_hpo.py materialize` for
the queue transaction and `reconcile --write` for artifact-bound aggregation.
The helper performs deterministic default/DE mutation and Hyperband promotion;
`reconcile --write --finalize` selects only complete full-resource groups that
pass every dataset floor. An eligible policy must replace
`trial_budget.max_total_gpu_hours=0` with a finite positive cap and keep
`remaining_gpu_hours` at or below that cap. The total cap covers all materialized
Stage-5 rows; the remaining value bounds the next grouped trial and may decrease
as evidence is reconciled. Finalization is legal only after no
registered trial can still be materialized; an intentional early stop must use
`--stop-reason <recorded-reason>` so the ledger decision preserves why search
ended before budget exhaustion.

## Budget Tiers

Use the smallest tier that can distinguish non-degenerate behavior.

| Tier | Scout trials | Full-budget survivors | Use when |
| --- | ---: | ---: | --- |
| `micro` | 8-12 | 1 | one GPU, expensive run, uncertain mechanism |
| `small` | 12-24 | 1-2 | normal limited research budget |
| `standard` | 24-48 | 2 | cheap proxy dataset or fast model |

Do not exceed 48 scout trials or 3 full-budget survivors unless the user records
`user_approved_higher_budget=true`. If even `micro` is too expensive, run a
single fixed candidate as diagnostic-only and return to ALGO/CODE ideation
instead of pretending tuning evidence is stable.

## Protocol Rules

- Search dimensions must be the few important knobs. Cap at 6 dimensions by
  default; prefer 3-5.
- Use log-scale dimensions for learning rates, regularizers, loss weights,
  temperatures, thresholds, and other multiplicative scales.
- Never include random seed, dataset, split, baseline, backbone/checkpoint,
  metric, or evaluation command as a search dimension.
- Use exactly one matched scout seed. The confirmation set may reuse that seed and
  add at most two others; stability is capped at three unique random seeds total.
- Execute independent scouts asynchronously. `max_concurrent_scouts=auto` means
  the minimum of remaining scout budget, scientifically ready queue rows, fitting
  idle slots, and queue in-flight budgets; it does not expand `max_scout_trials`.
  Full-budget concurrency cannot exceed `max_full_budget_trials`.
- Promote only from canonical metrics at the same rung/protocol fingerprint.
  Completion order and partially observed higher-fidelity trials must not change
  comparison eligibility.
- The resource axis is epochs, steps, or data fraction. It is never seed count.
- Low-fidelity rungs may rank/prune candidates, but only a full-resource survivor
  can become `candidate_supported`.
- Promotion uses the locked metric policy and material-regression checks, not a
  single favorable metric component.
- If PARAM search stalls or consumes its declared budget, preserve the negative
  evidence and force a structural ALGO/CODE leap or return to idea_gate.
- Materialize trials only when `activation_status=eligible`. Pending policies are
  planning records, not launchable work. Eligible mechanism search must name its
  sensitivity question and belief state; eligible baseline calibration instead
  records `work_kind=baseline_calibration`, `evidence_tier=pilot_only`, and no
  innovation `validation_stage=5`.

## Baseline Calibration

Use `tuning_target=baseline_calibration` only to obtain a fair matched reproduced
baseline under the locked code, dataset, split, evaluator, and validation metric.
Search uses validation evidence, never protected test feedback. Record an equal
or shared tuning budget for baseline and proposed method, then freeze the chosen
baseline configuration before any claim-closing row.

Innovation scouts need not wait for every calibration trial. They may overlap as
`pilot_only` code/mechanism tests against the current declared baseline, but they
cannot establish a paper-report comparison or publishable gain. Any survivor is
rerun against the frozen matched baseline, using the same seed set, before
`candidate_supported` or claim promotion. Failure to reproduce the paper report
remains separate evidence and must be labeled `paper-report comparison not
established`; DEHB may not tune until a favorable seed or test result appears.
