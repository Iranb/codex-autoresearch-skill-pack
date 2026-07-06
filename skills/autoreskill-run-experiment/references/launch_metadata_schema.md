# Launch Metadata Schema

```json
{
  "experiment_id": "",
  "track_id": "",
  "backend": "local|ssh|autodl|bjtu_hpc|other",
  "command": "",
  "environment": {},
  "working_dir": "",
  "session_id": "",
  "started_at": "",
  "status": "queued|running|completed|failed|budget_stopped",
  "track_id": "",
  "selected_idea_id": "",
  "innovation_mechanism": "",
  "mechanism_type": "ALGO|CODE|PARAM",
  "promotion_stage": "candidate|ablation|confirmation",
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
