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
  "paper_innovation_bundle": [
    {
      "name": "",
      "role": "problem_definition|protocol|benchmark|evaluation|metric|method_mechanism|algorithm|model|architecture|training_mechanism|training_integration|system_integration|theory_analysis|ablation|validation|analysis",
      "source_role": "target_domain_anchor|near_neighbor|far_neighbor|cross_lane_recombination|proposal_graph_transfer|external_domain_transfer|target_domain_absence_proven",
      "source_evidence_refs": [],
      "closest_prior_delta": "",
      "paper_story_role": "",
      "validation_plan": "",
      "current_field_absence_evidence": ""
    }
  ],
  "paper_storyline": {
    "paper_thesis": "",
    "opening_tension": "",
    "hidden_cause": "",
    "method_as_resolution": "",
    "proof_ladder": [],
    "reviewer_risk_and_defense": "",
    "narrative_spine": []
  },
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
  "hpo_search_policy": {
    "search_method": "dehb_resource_constrained|not_applicable",
    "search_role": "PARAM|supporting_PARAM|not_applicable",
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
    "kill_condition": "",
    "claim_boundary": "Low-fidelity HPO scouts are pilot/search evidence only; final claims require full-resource plus ablation or confirmation."
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
  "dataset_requirement_inventory": {
    "required_datasets": [
      {
        "dataset_id": "",
        "dataset_name": "",
        "claim_role": "method_validation|ablation|stress|confirmation|final_scale|comparison_only",
        "reason_required": "",
        "baseline_supported": true,
        "availability": "available|missing|unknown|invalid_for_claim",
        "scale_class": "small_multiclass|medium_multiclass|large_full_scale",
        "num_classes": 10,
        "train_samples": 50000,
        "eval_samples": 10000,
        "native_protocol_ref": "",
        "native_epochs_or_steps": "200 epochs",
        "native_warmup_or_schedule": "",
        "data_root_or_probe": "",
        "selection_status": "selected_first|deferred|rejected"
      }
    ],
    "selection_rule": "choose_smallest_available_baseline_supported_required_dataset_for_method_validation",
    "method_validation_dataset_id": "",
    "smallest_available_required_dataset_id": "",
    "non_smallest_first_exception_reason": "user_approved_non_smallest|dataset_invalid_for_selected_claim|no_required_small_dataset_available",
    "deferred_dataset_ids": [],
    "rejected_datasets": [
      {"dataset_id": "", "rejection_reason": ""}
    ]
  },
  "dataset_runtime_plan": {
    "candidate_datasets": [
      {
        "dataset_id": "",
        "scale_class": "small_multiclass|medium_multiclass|large_full_scale",
        "num_classes": 10,
        "train_samples": 50000,
        "eval_samples": 10000,
        "epochs_or_steps": "100 epochs",
        "estimated_minutes_per_epoch": 1.5,
        "estimated_walltime_hours": 2.5,
        "estimated_gpu_hours": 2.5,
        "estimation_basis": "prior logs|dry-run throughput|sample count extrapolation|baseline paper norm",
        "purpose": "feasibility_first|ablation|confirmation|final_scale"
      }
    ],
    "feasibility_first_dataset_id": "",
    "first_run_scale_class": "small_multiclass|medium_multiclass",
    "largest_dataset_id": "",
    "largest_dataset_deferred": true,
    "large_first_exception_reason": "no_smaller_multiclass_proxy|user_approved_start_large",
    "escalation_criteria": [],
    "runtime_risk": ""
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
