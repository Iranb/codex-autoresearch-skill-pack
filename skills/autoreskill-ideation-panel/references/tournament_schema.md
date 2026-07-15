# Tournament Schema

Candidate fields:

```json
{
  "track_id": "track_001",
  "title": "Idea title",
  "status": "advance|park|kill",
  "evidence_ids": [],
  "novelty_basis": "",
  "baseline": "",
  "primary_metric": "",
  "weakest_assumption": "",
  "falsifier": "",
  "causal_signature": "normalized intervention | mechanism | predicted pattern",
  "intervention": "",
  "mechanism": "",
  "predicted_pattern": "",
  "unique_decision_targets": [],
  "competing_hypotheses_resolved": [],
  "estimated_falsifier_gpu_hours": 0.0,
  "estimated_cost_basis": "prior log|throughput probe|matched run",
  "reusable_invariant_refs": [],
  "reviewer_risks": [],
  "changes_core_claim": false,
  "validation_density": 0.0,
  "deterministic_rank_tuple": [],
  "pairwise_comparison": {
    "closest_competing_idea_id": "",
    "mechanism_difference": "",
    "predicted_pattern_difference": "",
    "cheapest_discriminator": "",
    "verdict": "distinct|redundant|ablation|uncertain"
  },
  "scores": {
    "novelty": 0,
    "feasibility": 0,
    "significance": 0,
    "risk": 0
  }
}
```

Generate 8-12 lightweight cards once per `selection_revision`, then screen one
3-5 item shortlist in a batch. Only shortlisted candidates require the complete
causal, closest-prior, outcome-route, baseline-pressure, and experiment
contract. Ordinary heartbeats consume this committed shortlist and cannot
regenerate or rescore it.

For `cross_dataset_method`, shortlisted method rows additionally carry
`claim_role=method_candidate`, `mechanism_type=ALGO|CODE`,
`parameter_transfer_mode`, expected load-bearing parameter/scale, predictions
for every required dataset, and a paired falsifier. These are screening
assumptions, not concrete calibration values or launch approval.

A `redundant` candidate cannot advance. Merge identical causal signatures;
route parameter-only differences as `PARAM`, ablations, or controls instead of
independent tracks. After hard gates, sort lexicographically by core-claim
impact, competing-hypothesis coverage, validation density, falsifier cost,
invariant reuse, reviewer risk, then stable idea id. Do not add a model-invented
success probability. Pairwise preference is screening evidence only and cannot
establish novelty or scientific truth.
