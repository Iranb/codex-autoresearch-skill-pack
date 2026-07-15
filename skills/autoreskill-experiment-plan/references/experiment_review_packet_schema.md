# Experiment Review Packet Schema

`planner/EXPERIMENT_REVIEW_PACKET.json`:

```json
{
  "track_id": "track_001",
  "track_role": "primary|alternate|risk_repair",
  "evidence_tier_ceiling": "claim_eligible_after_gates|pilot_only",
  "source_track_seed_ref": "ideation/IDEA_TRACK_SEEDS.json",
  "source_track_seed_sha256": "",
  "source_track_seed_item_sha256": "",
  "project_execution_passport_ref": "resources/PROJECT_EXECUTION_PASSPORT.json",
  "project_execution_passport_index_sha256": "",
  "execution_profile_id": "",
  "execution_profile_sha256": "",
  "claim_role": "method_candidate|method_control|diagnostic_only|baseline_support|protocol_support",
  "program_claim_contract_ref": "orchestrator/PROGRAM_CLAIM_CONTRACT.json",
  "program_claim_contract_sha256": "",
  "program_claim_contract_revision": 0,
  "claim_scope": "dataset_specific|cross_dataset_method",
  "method_formula": "one immutable algorithm/formula used on every required dataset",
  "method_formula_sha256": "",
  "parameter_role_inventory": [
    {"parameter_name": "epochs", "parameter_role": "baseline_protocol_dataset_adaptable"},
    {"parameter_name": "association_margin_threshold", "parameter_role": "innovation_load_bearing"}
  ],
  "dataset_group_plan": {
    "required_dataset_ids": ["dataset-a", "dataset-b"],
    "dataset_roles": {"dataset-a": "primary", "dataset-b": "contrast"},
    "baseline_ref_by_dataset": {"dataset-a": "", "dataset-b": ""}
  },
  "parameter_transfer_contract": {
    "parameter_role": "innovation_load_bearing",
    "parameter_name": "",
    "parameter_calibration_group_id": "parameter-track_001-r1",
    "parameter_probe_kind": "scale_audit|bounded_calibration|portability_probe",
    "transfer_mode": "shared_absolute|shared_normalized|dataset_calibrated",
    "shared_formula": "",
    "normalization_or_calibration_statistic": "",
    "calibration_data_scope": "train_only|unlabeled_target",
    "candidate_values_by_dataset": {"dataset-a": [0.05, 0.1], "dataset-b": [0.05, 0.1]},
    "selection_seed_by_dataset": {"dataset-a": 0, "dataset-b": 0},
    "selection_rule": "",
    "selection_rule_spec": {"direction": "max|min", "tie_break": "smaller_setting"},
    "test_outcome_forbidden": true,
    "claim_ceiling": "",
    "parameter_transfer_contract_sha256": ""
  },
  "parameter_profile_status": "not_required|audit_pending|calibrating|frozen|invalidated",
  "stage2_role": "stage2_parameter_probe|stage2_method_screen",
  "frozen_parameter_profile_ref": "planner/tracks/track_001/FROZEN_PARAMETER_PROFILE.json",
  "frozen_parameter_profile_sha256": "",
  "innovation_delta": {
    "mechanism": "",
    "one_variable_change": "",
    "predicted_pattern": "",
    "falsifier": "",
    "alternative_explanations": [],
    "stop_rules": [],
    "budget": {"gpu_hours": 0.0, "walltime_hours": 0.0}
  },
  "innovation_delta_sha256": "",
  "claim_ids": ["claim_001"],
  "hypothesis": "",
  "novelty_basis": "",
  "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
  "selected_idea_id": "IDEA-001",
  "selected_idea_fragment_id": "fragment-001 (required for external_material)",
  "external_campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json (external_material only)",
  "external_campaign_sha256": "<sha256> (external_material only)",
  "external_candidate_id": "candidate-001 (external_material only; distinct from fragment and track)",
  "protected_commitment_sha256": "<selected campaign candidate commitment sha256; external_material only>",
  "idea_generation_scope": "consume the ideation-stage pool; targeted literature/material closure is required when selected-idea evidence debt exists",
  "core_scientific_contribution": "one causal/scientific claim that the paper must defend",
  "supporting_contributions": [
    {
      "name": "",
      "contribution_class": "supporting_scientific_contribution|validation_role|analysis_role|engineering_support",
      "counterfactual_necessity": "required only for supporting_scientific_contribution: what central claim fails without it",
      "evidence_refs": [],
      "validation_plan": "",
      "claim_boundary": ""
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
  "hypothesis_contract": {
    "causal_signature": "normalized intervention | mechanism | predicted pattern",
    "causal_question": "",
    "intervention": "",
    "one_variable_delta": "",
    "mechanism": "",
    "predicted_pattern": "",
    "falsifier": "",
    "alternative_explanation": "",
    "minimum_discriminating_experiment": "",
    "dataset_transfer_assumption": "",
    "positive_route": "PROCEED_TO_ABLATION_OR_CONFIRMATION",
    "negative_route": "PIVOT_TO_CHILD_TRACK|RETIRE_TRACK|SCOPE_CLAIM|CONCLUDE_PROGRAM",
    "inconclusive_route": "RUN_ONE_DISAMBIGUATOR|RETIRE_TRACK|CONCLUDE_PROGRAM",
    "invalid_route": "REFINE_IMPLEMENTATION|REFINE_PROTOCOL|WAIT_OR_RECONCILE_BACKEND",
    "belief_state": "untested",
    "scientific_revision_index": 0,
    "max_scientific_revisions": 2
  },
  "promotion_gate": {
    "stage": "candidate",
    "promotion_requires": [],
    "claim_policy": "candidate_supported is pilot evidence; promoted track best is required for improvement claims"
  },
  "hpo_search_policy": {
    "search_method": "dehb_resource_constrained|not_applicable",
    "search_role": "PARAM|supporting_PARAM|not_applicable",
    "tuning_target": "baseline_calibration|mechanism_parameterization",
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
  "execution_route": "local|ssh|bjtu_hpc|autodl",
  "path_mapping": {
    "selected_backend": "local_gpu|autodl_gpu",
    "execution_route": "local|ssh|bjtu_hpc|autodl",
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
  "compute_budget": {
    "gpu_hours": 0.0,
    "full_budget_gpu_hours_by_dataset": {}
  },
  "validation_ladder_schema_version": 1,
  "validation_ladder": [
    {
      "stage": 0,
      "name": "static_identity_and_path_checks",
      "prerequisites": [],
      "decision_targets": [],
      "claim_ceiling": "diagnostic_only",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    },
    {
      "stage": 1,
      "name": "smoke_or_tiny_batch_overfit",
      "prerequisites": ["stage_0_pass"],
      "decision_targets": [],
      "claim_ceiling": "readiness_only",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    },
    {
      "stage": 2,
      "name": "smallest_valid_dataset_single_seed",
      "prerequisites": ["stage_1_pass"],
      "decision_targets": [],
      "claim_ceiling": "pilot_only",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    },
    {
      "stage": 3,
      "name": "full_budget_single_seed_matched_control",
      "prerequisites": ["stage_2_support_or_ambiguity"],
      "decision_targets": [],
      "claim_ceiling": "initial_mechanism_support",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    },
    {
      "stage": 4,
      "name": "second_target_dataset",
      "prerequisites": ["stage_3_initial_support"],
      "decision_targets": [],
      "claim_ceiling": "dataset_scoped_support",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    },
    {
      "stage": 5,
      "name": "bounded_dehb_and_required_ablation",
      "prerequisites": ["stage_3_support_or_ambiguity", "stage_4_or_equivalent_cross_dataset_evidence"],
      "decision_targets": [],
      "claim_ceiling": "search_evidence_only",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    },
    {
      "stage": 6,
      "name": "paired_seed_stability",
      "prerequisites": ["frozen_matched_baseline", "promotion_candidate"],
      "decision_targets": [],
      "claim_ceiling": "claim_promotion_candidate",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    },
    {
      "stage": 7,
      "name": "bounded_supported_component_combination",
      "prerequisites": ["independently_supported_components"],
      "decision_targets": [],
      "claim_ceiling": "bounded_combination_evidence",
      "estimated_gpu_hours": 0.0,
      "outcome_routes": ["positive", "negative", "inconclusive", "invalid"],
      "stop_condition": ""
    }
  ],
  "protected_paths": [
    {"path": "", "purpose": "eval|test_data|metric", "sha256": ""}
  ],
  "expected_artifacts": [],
  "paperNexus_norms": {},
  "external_evidence_norms": {
    "campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
    "campaign_sha256": "<sha256>",
    "source_integrity": {},
    "source_verification_limits": [],
    "claim_limits": []
  },
  "experiment_cost_norms": {},
  "non_promotion_signals": []
}
```

For an enforced cross-dataset method candidate, `method_formula_sha256` must
match in both packet authorities and the track matrix. The role inventory must
contain exactly one `innovation_load_bearing` row, and its name/hash must bind
the `parameter_transfer_contract`. Dataset-native epochs, schedules, batch size,
and other baseline protocol fields remain
`baseline_protocol_dataset_adaptable`; changing them does not create a method
variant. A shared-mode `shared_formula` may not branch on a required dataset id
or carry per-dataset formula overrides; use a reviewed `dataset_calibrated`
profile when selected settings genuinely differ. This separation prevents
baseline adaptation from being mistaken for innovation-parameter transfer.

Source-conditional fields: legacy/missing-mode packets require
`paperNexus_norms`. `evidence_source_mode="external_material"` packets require
`external_evidence_norms` (or canonical `evidence_norms`) and the exact external
identity triple, and must omit fabricated PaperNexus/MCP provenance. Backend and
route are orthogonal: `local_gpu` maps to `local`, `ssh`, or `bjtu_hpc`, while
`autodl_gpu` maps only to `autodl`.

The project passport is a component-addressed invariant index. A row binds the
named execution profile, while `innovation_delta` records only the track's
scientific change; both hashes are direct authority and repeated embedded
baseline/path fields are compatibility projections. Unrelated passport
components must not invalidate this packet.

Every ladder stage records all fields shown for stage 0. Stages 0-1 cannot
support effectiveness; stage 2 is one-seed `pilot_only`; stage 4 precedes stage
5 after initial support; innovation stage 5 requires an explicit sensitivity
question and must not represent baseline calibration; stage 6 uses at most
three paired seeds; stage 7 accepts only independently supported components.
Baseline calibration is separate `pilot_only` claim-closing work. A valid
terminal negative cannot enter stages 5 or 6.

`trial_budget.max_total_gpu_hours=0` is a pending-policy placeholder only. Set a
finite positive value before `activation_status=eligible`, with
`remaining_gpu_hours <= max_total_gpu_hours`. The total cap bounds cumulative
Stage-5 rows; the remaining field bounds the next grouped trial. Before Stage 3/4 materialization,
record either `compute_budget.full_budget_gpu_hours_by_dataset`, complete
per-dataset `dataset_runtime_plan` estimates, or a finite positive aggregate
`compute_budget.gpu_hours`; the workflow must not reuse Stage-2 scout cost as a
full-budget estimate.

Only `track_role=primary` requires the complete paper storyline. Alternates and
risk repairs remain `pilot_only`, but still require the causal contract,
closest-prior distinction, baseline/protocol identity, four outcome routes,
falsifier, cost, stop rules, and claim boundary.
