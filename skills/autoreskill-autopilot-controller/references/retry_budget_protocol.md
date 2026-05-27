# Retry Budget Protocol

Each blocker gets a stable key:

```text
<stage>:<reason>:<artifact-or-track>
```

For each key, track:

- `attempts`
- `max_attempts`
- `next_retry_at`
- `fallback_action`
- `last_error`
- `status`

When attempts exceed the budget, do not keep retrying. Choose one of:

- `degrade_claim`
- `rollback_stage`
- `switch_track`
- `negative_result_route`
- `hard_stop`
