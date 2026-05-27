# Fallback Recipes

- `missing_negative_evidence`: queue PaperNexus `negative_evidence_pack`; if unavailable, write `absence_confidence` and downgrade novelty claims.
- `import_wait`: write `async_jobs.jsonl` with `next_poll_at`; continue provisional literature/plan work that does not require graph sync.
- `dry_run_fail`: repair up to policy budget; then shrink experiment to baseline-only smoke or roll back to `experiment_plan`.
- `review_high_issue`: create reviewer repair packet; after max attempts, downgrade or delete the affected claim.
- `budget_exceeded`: hard stop the launch path, shrink compute budget, or switch to a negative-result/plan-only route.
- `research_controller_unavailable`: write degraded controller fallback design review; do not call sketches graph-grounded.
