# Async Wait Policy Fixtures

`tests/run_async_wait_policy_fixtures.py` generates minimal project fixtures in
temporary directories from these scenario names. The generated fixtures exercise
real `goal.py tick` and `blocker_triage.py --dry-run` behavior without live
PaperNexus, SSH, GPU, Slurm, or Codex heartbeat side effects.
