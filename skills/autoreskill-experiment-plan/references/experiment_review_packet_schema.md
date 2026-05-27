# Experiment Review Packet Schema

`planner/EXPERIMENT_REVIEW_PACKET.json`:

```json
{
  "track_id": "track_001",
  "claim_ids": ["claim_001"],
  "hypothesis": "",
  "novelty_basis": "",
  "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
  "selected_idea_id": "IDEA-001",
  "idea_generation_scope": "ideation-stage experiment idea pool; no experiment-plan generation",
  "one_variable_change": "",
  "baseline_reference": "",
  "baseline_training_protocol": "",
  "baseline_eval_protocol": "",
  "evaluation_command": "",
  "dataset": "",
  "data_split": "",
  "primary_metric": "",
  "metric_direction": "higher|lower",
  "secondary_metrics": [],
  "ablation_plan": [],
  "falsifiers": [],
  "stop_rules": [],
  "compute_budget": "",
  "protected_paths": [
    {"path": "", "purpose": "eval|test_data|metric", "sha256": ""}
  ],
  "expected_artifacts": [],
  "paperNexus_norms": {},
  "experiment_cost_norms": {},
  "non_promotion_signals": []
}
```
