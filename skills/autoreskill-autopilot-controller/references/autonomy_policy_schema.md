# Autonomy Policy Schema

Default policy is `full_auto_bounded`.

```json
{
  "schema_version": 1,
  "autonomy_level": "full_auto_bounded",
  "allow_provider_evidence": true,
  "allow_live_discovery": true,
  "allow_literature_discovery": true,
  "allow_open_access_imports": true,
  "allow_remote_experiment_launch": true,
  "allow_claim_downgrade": true,
  "allow_negative_result_route": true,
  "max_literature_imports_per_round": 8,
  "max_provider_queries_per_round": 8,
  "max_experiment_walltime_hours": 12,
  "max_experiment_gpu_hours": 24,
  "max_repair_attempts_per_blocker": 3,
  "max_stage_iterations": 8
}
```

Use `conservative_auto` to disable remote experiment launch. Use `manual_approval` when the user wants explicit confirmation before imports or experiments.
