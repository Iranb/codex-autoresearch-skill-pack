# Paper Forensics Fixtures

These fixtures provide lightweight `paper/main.tex` samples for
`tests/run_paper_forensics_fixtures.py`.

- `pass_clean`: internally consistent numeric claim.
- `fail_delta_error`: relative-improvement arithmetic mismatch.
- `fail_grim`: impossible percentage over integer `N`.
- `fail_pipeline_artifact`: exact template/pipeline residue.
- `warn_ais_only`: zero-weight defensive style impressions only.

The test script creates temporary full `.autoreskill` projects when a complete
`contract_lint.py` stage check is needed.
