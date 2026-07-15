# Retry Budget Protocol

Each operational failure gets a stable signature:

```text
<stage>:<failure-class>:<artifact-or-run>:<normalized-root-cause>
```

For each key, track:

- `failure_signature`
- `repair_kind`
- `operational_attempt`
- `max_operational_attempts` (default 2)
- `scientific_revision`
- `max_scientific_revisions` (default 2 per track)
- `next_retry_at`
- `fallback_action`
- `last_error`
- `status`

Operational and scientific counters never substitute for each other. A crash,
OOM, dependency error, or implementation exception consumes only the operational
counter for that signature and has no belief effect. A valid negative,
inconclusive, or cross-dataset result may consume a scientific revision only when
the next hypothesis changes a recorded causal assumption. Re-running the same
configuration is not a revision.

When the relevant budget is exhausted, do not keep retrying. Choose one of:

- `degrade_claim`
- `rollback_stage`
- `switch_track`
- `negative_result_route`
- `hard_stop`

An inconclusive result receives at most one discriminator by default even though
the track-level scientific ceiling is two. Async heartbeats/polls use their own
attempt state and do not consume either budget.
