# Monitor And Reconcile

For each run:

1. Check process/job status.
2. Tail logs for early failures.
3. Verify baseline alignment.
4. Parse metrics.
5. Update experiment index.
6. Write decision: continue, repair, stop, multi-seed, analyze.

Never launch blindly when a previous run is unreconciled.
