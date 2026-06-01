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
  "idea_generation_scope": "experiment idea generation; targeted literature/material closure required when selected-idea evidence debt exists",
  "innovation_search_contract": {
    "selected_idea_id": "IDEA-001",
    "track_id": "track_001",
    "innovation_mechanism": "",
    "mechanism_type": "ALGO|CODE|PARAM",
    "primary_method_source_role": "near_neighbor|far_neighbor|cross_lane_recombination|proposal_graph_transfer|external_domain_transfer|target_domain_absence_proven",
    "neighbor_transfer_mechanism": "",
    "target_domain_anchor": "",
    "target_domain_method_overlap_risk": "",
    "current_field_absence_evidence": "",
    "one_variable_change": "",
    "expected_effect": "",
    "falsifier": "",
    "ablation_required": true,
    "confirmation_required": true,
    "promotion_stage": "candidate"
  },
  "promotion_gate": {
    "stage": "candidate",
    "promotion_requires": [],
    "claim_policy": "candidate_supported is pilot evidence; promoted track best is required for improvement claims"
  },
  "one_variable_change": true,
  "one_variable_change_description": "",
  "baseline_reference": "",
  "baseline_code": {
    "code_id": "",
    "source_type": "workspace|official_repo|artifact|user_provided",
    "source_ref": "",
    "revision": "",
    "resolved_path": "",
    "train_entrypoint": "",
    "eval_entrypoint": "",
    "selection_rationale": "",
    "locked": true
  },
  "baseline_training_protocol": "",
  "baseline_eval_protocol": "",
  "evidence_import_gate": {
    "status": "passed|not_required|async_wait|blocked",
    "reason": "",
    "triage_ref": "papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
    "mcp_attempted": true,
    "attempts": [
      {"operation": "literature_discovery_import|research_material_pack|closest_prior_materials", "status": "", "artifact_ref": ""}
    ],
    "material_refs": [],
    "evidence_ids": [],
    "launch_blocked": false,
    "claim_limits": []
  },
  "compute_backend": {
    "backend": "local_gpu|autodl_gpu",
    "decision_rationale": "",
    "gpu_evidence": "",
    "autodl_plan_ref": "",
    "paid_resource_policy": ""
  },
  "path_mapping": {
    "selected_backend": "local_gpu|autodl_gpu",
    "logical_dataset_id": "",
    "code_root": "",
    "data_root": "",
    "output_dir": "",
    "checkpoint_dir": "",
    "persistent_output_dir": "",
    "env": {
      "DATA_ROOT": "",
      "OUTPUT_DIR": "",
      "CKPT_DIR": ""
    }
  },
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
