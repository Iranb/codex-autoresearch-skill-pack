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
  "seed_policy": {
    "seed_is_search_axis": false,
    "scout_random_seed_count": 1,
    "matched_seed_protocol": true,
    "max_confirmation_random_seeds": 3
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
- Use exactly one matched scout seed. Seed stability is a confirmation question,
  capped at three random seeds total.
- The resource axis is epochs, steps, or data fraction. It is never seed count.
- Low-fidelity rungs may rank/prune candidates, but only a full-resource survivor
  can become `candidate_supported`.
- Promotion uses the locked metric policy and material-regression checks, not a
  single favorable metric component.
- If PARAM search stalls or consumes its declared budget, preserve the negative
  evidence and force a structural ALGO/CODE leap or return to idea_gate.
