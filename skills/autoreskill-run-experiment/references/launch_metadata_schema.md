# Launch Metadata Schema

```json
{
  "experiment_id": "",
  "track_id": "",
  "track_role": "primary|alternate|risk_repair",
  "evidence_tier_ceiling": "claim_eligible_after_gates|pilot_only",
  "idea_lifecycle_status": "selected_primary|alternate_track|risk_repair_track",
  "idea_decision_ref": "",
  "source_track_seed_ref": "ideation/IDEA_TRACK_SEEDS.json",
  "source_track_seed_sha256": "",
  "selection_fingerprint": "",
  "innovation_packet_ref": "",
  "innovation_packet_sha256": "",
  "review_packet_ref": "",
  "review_packet_sha256": "",
  "project_execution_passport_ref": "resources/PROJECT_EXECUTION_PASSPORT.json",
  "project_execution_passport_index_sha256": "",
  "execution_profile_id": "",
  "execution_profile_sha256": "",
  "innovation_delta_sha256": "",
  "resolved_execution_contract_projection_sha256": "",
  "track_plan_ref": "orchestrator/TRACK_PLAN_MATRIX.json:<track-id>",
  "track_plan_matrix_sha256": "",
  "historical_plan_stale": false,
  "historical_identity_conflicts": [],
  "follow_up_allowed": true,
  "backend": "local|ssh|autodl|bjtu_hpc|other",
  "command": "",
  "environment": {},
  "working_dir": "",
  "session_id": "",
  "started_at": "",
  "status": "queued|submitting|needs_sync|running|completed|failed|budget_stopped",
  "queue_row_id": "",
  "resource_pool_id": "",
  "execution_route": "local|ssh|bjtu_hpc",
  "external_campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
  "external_campaign_sha256": "",
  "external_candidate_id": "",
  "protected_commitment_sha256": "",
  "external_gate": {
    "gate_ref": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
    "gate_sha256": "",
    "lint_ref": "ideation/committed/NON_PAPERNEXUS_IDEA_LINT.<sha256>.json",
    "lint_sha256": "",
    "slot_map_ref": "ideation/committed/INNOVATION_SLOT_MAP.<sha256>.json",
    "slot_map_sha256": ""
  },
  "selected_idea_id": "",
  "innovation_mechanism": "",
  "mechanism_type": "ALGO|CODE|PARAM",
  "promotion_stage": "candidate|ablation|confirmation",
  "evidence_tier": "pilot_only|claim_eligible",
  "experiment_family_id": "",
  "replication_group_id": "",
  "baseline_freeze_ref": "",
  "ablation_of": "",
  "confirmation_of": "",
  "source_snapshot": {
    "git_commit": "",
    "git_status_porcelain": "",
    "git_diff_stat": ""
  },
  "locked_protocol": {
    "dataset": "",
    "data_split": "",
    "primary_metric": "",
    "metric_direction": "higher|lower",
    "evaluation_command": ""
  },
  "resource_request": {
    "backend": "local|ssh|autodl|bjtu_hpc|other",
    "host": "",
    "account": "",
    "gpu_count": 1,
    "min_free_mib": null,
    "exclusive_resource_id": ""
  },
  "resource_allocation": {
    "backend": "local|ssh|autodl|bjtu_hpc|other",
    "host": "",
    "account": "",
    "gpu_id": "",
    "gpu_uuid": "",
    "job_id": "",
    "allocated_at": ""
  },
  "planned_resource_allocation": {},
  "backend_preflight": {},
  "backend_submit_intent": {},
  "backend_submit_intent_sha256": "",
  "backend_submit_receipt": {},
  "backend_submit_receipt_sha256": "",
  "backend_observation": {},
  "backend_observation_sha256": "",
  "resource_snapshot_ref": "",
  "resource_snapshot_sha256": "",
  "resource_snapshot_source_sha256": "",
  "resource_snapshot_checked_at": "",
  "resource_capability_passport_ref": "resources/RESOURCE_CAPABILITY_PASSPORT.json",
  "resource_capability_passport_sha256": "",
  "global_schedule_sha256": "",
  "assignment_sha256": "",
  "launch_spec": {},
  "authorization": {},
  "backend_idempotency_key": "",
  "immutable_launch_intent_sha256": "",
  "mutex_group": "",
  "parallel_safe": true,
  "validation_stage": 0,
  "validation_prerequisites": [],
  "claim_ceiling": "diagnostic|pilot_only|claim_eligible_after_gates",
  "protected_path_hashes": [],
  "metrics": {
    "baseline": null,
    "proposed": null,
    "primary_metric": null,
    "score_delta": null
  },
  "promotion_decision": "candidate_supported|promoted|not_promoted|record_only|rollback_to_best|repair",
  "promotion_reason": "",
  "next_action": "",
  "result_paths": [],
  "log_paths": [],
  "local_log_paths": [],
  "log_sync": {
    "status": "not_required|synced|partial|failed|skipped",
    "synced_at": "",
    "policy": "sync logs and lightweight text/metadata only; checkpoints excluded by default",
    "included_suffixes": [".log", ".txt", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".out", ".err"],
    "excluded_patterns": ["checkpoint/", "checkpoints/", "*.pt", "*.pth", "*.ckpt", "*.safetensors", "*.bin", "*.onnx"],
    "items": [
      {"remote": "", "local": "", "status": "synced|failed|skipped", "reason": ""}
    ]
  },
  "budget": {},
  "monitoring": {
    "schema_version": 1,
    "status": "active|paused",
    "last_checked_at": "",
    "next_check_at": "",
    "interval_minutes": 15,
    "desired_rrule": "",
    "cadence_reason": "",
    "estimated_remaining_minutes": null,
    "expected_finish_at": null,
    "stale_count": 0,
    "last_progress_at": null,
    "automation": {
      "key": "autoreskill-experiment-monitor:<project>",
      "name": "autoreskill-experiment-monitor:<project>",
      "kind": "heartbeat",
      "destination": "thread",
      "action": "create|update|pause|none",
      "automation_id": null,
      "desired_rrule": ""
    }
  }
}
```

`coder/EXPERIMENT_LEDGER.json` also records `best_run`, `track_best_runs`, `candidate_runs`, all entries, and whether promoted results are ready for analysis.
`.autoreskill/automation_registry.json` records the single reusable experiment monitor for the project. Keep the registry stable across runs so Codex can update the existing monitor instead of creating duplicate scheduled checks.
For stable active runs with `estimated_remaining_minutes`, `monitoring.interval_minutes` should match the remaining time to `expected_finish_at`; it is a completion wakeup, not a fixed 30-minute poll. Short health-check intervals are reserved for queued, startup, stale, hung, no-progress, or no-ETA states.
Remote runs must preserve both remote `log_paths` and local `local_log_paths`. Local sync is for logs, text metrics, run metadata, command files, and small result tables only; checkpoint/model files remain remote or in persistent storage unless the user explicitly requests checkpoint backup.
Resource fields are required for parallel scheduling. A running run blocks only
matching `mutex_group`, matching exclusive resource allocation, backend/account
caps, or declared dependencies; it is not a global project lock.
Project-passport/profile/delta identities must match the planning packet and
implementation manifest. The capability passport proves stable pool fit, while
the resource snapshot and backend preflight prove volatile launch readiness;
neither substitutes for the other. Persist submit intent before the physical
side effect, receipt immediately after backend acceptance, and running/terminal
state only after authoritative observation. A prepared attempt with unknown
backend outcome is reconciled by trace, never blindly retried.
`resource_pool_id` must match the scheduler assignment and is still subject to
fresh backend preflight. `pilot_only` runs may guide repair or selection but
cannot set `candidate_supported`, become `promoted`, or close claims. External
queued intents live only at
`.autoreskill/coder/experiments/<track_id>/<experiment_id>/REMOTE_RUN.json`.
Their campaign/candidate/commitment, content-addressed gate, resource snapshot,
preflight, launch spec, budget, authorization, backend idempotency key, and
pilot promotion boundary form one immutable digest. Reconciliation may update
runtime status, logs, metrics, and monitoring state, but must verify and
preserve that digest-bound payload byte-for-byte at the JSON-value level.
Global schedule and assignment fields are required only for
`admission_scope=global`; they record launch-time admission identity and do not
replace backend state. Non-primary roles must use `pilot_only` for both the
ceiling and actual evidence tier.
After primary reselection, an already launched old-selection run may reconcile
with `historical_plan_stale=true` and `follow_up_allowed=false`. It remains
launch-time evidence only, is `record_only`, and cannot create a child,
ablation, confirmation, or claim-bearing row under the superseded selection.
Rows in one replication group share a declared seed set;
the experiment family may contain at most three unique random seeds, including
HPO scouts and retries (which reuse their original seed).
