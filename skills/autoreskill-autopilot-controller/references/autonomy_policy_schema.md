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
  "allow_autonomous_candidate_replenishment": true,
  "max_literature_imports_per_round": 24,
  "max_provider_queries_per_round": 24,
  "max_live_discovery_questions": 6,
  "max_experiment_walltime_hours": 12,
  "max_experiment_gpu_hours": 24,
  "max_repair_attempts_per_blocker": 2,
  "max_operational_attempts_per_signature": 2,
  "max_scientific_revisions_per_track": 2,
  "max_stage_iterations": 16
}
```

Use `conservative_auto` to disable remote experiment launch. Use `manual_approval` when the user wants explicit confirmation before imports or experiments.

`max_repair_attempts_per_blocker` is retained as a compatibility fallback.
New routing uses the typed operational and scientific limits. Async polling has
its own cadence/attempt policy and never consumes either scientific revision or
code-repair budget.

`allow_autonomous_candidate_replenishment` enables local changed-basis candidate
construction under an already-authorized program contract. It is not a numeric
budget and cannot raise `max_targeted_replenishments`; replacement programs need
a matching direct-user intervention, while GPU availability grants no authority.
