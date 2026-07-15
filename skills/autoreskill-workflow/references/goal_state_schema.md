# Goal State Schema

`goal_state.json` is the control plane, not proof of semantic completion.

Required fields:

```json
{
  "schema_version": 1,
  "project_root": "/absolute/project",
  "goal": "research problem",
  "target_venue": "unspecified_top_tier",
  "paperNexus": {
    "mode": "remote_mcp",
    "corpus": "default-papernexus-corpus"
  },
  "stage": "init",
  "owner": "WorkflowGuard",
  "next_action": "resolve_corpus_and_project_memory",
  "blocking_reason": null,
  "autonomy_level": "full_auto_bounded",
  "goal_type": "paper_producing_top_tier",
  "claim_mode": "strong_paper_claims",
  "claim_limits": null,
  "project_agents_policy_hash": null,
  "iteration": 0,
  "updated_at": "ISO-8601"
}
```

`blocking_reason` should be machine-readable. Human-facing explanation belongs in `decision_log.jsonl`.
Loop-level recovery evidence belongs in `.autoreskill/LOOP_TRACE.jsonl`, not in
`goal_state.json`. The trace may record tick decisions, lint failures, evaluator
findings, repair routes, and clean-restart decisions, but it never owns the
current stage or completion status.
Core workflow scripts append trace entries for state saves, job dispatches, job
updates, actual stale-job reconcile changes, and sub-agent results; manual entries are only
needed for out-of-band evaluator findings or restart decisions.

`goal_type` and `claim_mode` scope the contracts so survey, writing-corpus, and
diagnostic workflows are not blocked by unrelated paper-submission gates.
When a workflow is outside `paper_producing_top_tier` + `strong_paper_claims`,
record `claim_limits`, `out_of_scope_claim_limits`, `evidence_boundaries`, or
equivalent scope boundaries so skipped strong-paper gates remain auditable.

Default classifications:

| Situation | `goal_type` | `claim_mode` |
| --- | --- | --- |
| Top-tier or CCF-A research paper goal | `paper_producing_top_tier` | `strong_paper_claims` |
| Pilot paper draft or reduced evidence manuscript | `paper_producing_light` | `pilot_evidence` |
| Paper-code or literature survey only | `standalone_survey` | `survey_only` |
| CCF-A writing-style corpus audit only | `writing_style_corpus` | `writing_guidance_only` |
| Environment, GPU, dataset, or workflow diagnosis | `diagnostic_or_resource` | `diagnostic_only` |

`project_agents_policy_hash` records the current project-local automation-policy
surface written by `scripts/ensure_project_agents.py`. When the hash already
matches, the entry/resume loop should avoid rewriting `AGENTS.md`.

`autopilot_policy.json` also controls async wait cadence. Defaults:

```json
{
  "async_poll_interval_minutes": 5,
  "experiment_monitor_default_interval_minutes": 30,
  "repair_retry_interval_minutes": 5,
  "max_operational_attempts_per_signature": 2,
  "max_scientific_revisions_per_track": 2,
  "allow_autonomous_candidate_replenishment": true
}
```

Operational attempts are keyed by a stable failure signature and do not change
hypothesis belief. Scientific revisions are keyed by track and consume a separate
budget only after valid evidence changes the hypothesis. A valid negative result
is never counted as an operational repair.

`allow_autonomous_candidate_replenishment` permits the bounded local recovery
route; it does not choose or increase a transaction cap. The active program
contract owns the allocation, and exceptional replacement allocations require a
matching direct-user intervention. Legacy projects missing `goal_type` or
`claim_mode` use the documented paper-producing defaults with a migration
warning; an explicit invalid value still fails closed.

For PaperNexus discovery waits, `async_poll_interval_minutes` is the default heartbeat interval the parent Codex agent should use after `goal_tick.py` returns a `wakeup` recommendation. Experiment runtime waits use `experiment_monitor_default_interval_minutes` only as a fallback when no stage-aware ETA artifact exists; live experiment monitor artifacts should still set the heartbeat from progress, ETA, or the next stage boundary and are not capped by this fallback. For PaperNexus graph import waits, `goal_tick.py` may override this default from `papernexus/IMPORT_WORKFLOW_STATUS.json` using queue depth, active fast-commit progress, authoritative-sync state, and terminal completion.
