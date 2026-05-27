# Controller Sequence

Run actions in order:

1. `status`
2. `init_task`
3. `generate_decomposition`
4. `review_decomposition`
5. `generate_candidates`
6. `propose_edges`
7. `judge_batch`
8. `select_batch`
9. `expand_evidence`
10. `compose_solutions`
11. `design_review`
12. `export`

Provider evidence, literature discovery, imports, and experiment launch are controlled by `autopilot_policy.json`.
