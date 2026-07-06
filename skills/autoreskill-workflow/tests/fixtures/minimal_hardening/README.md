# Minimal Hardening Fixtures

These fixtures target only the small hardening checks added to
`scripts/contract_lint.py`. They are not full AutoResearch projects.

Run:

```bash
python tests/run_minimal_hardening_fixtures.py
```

The fixtures cover:

- top-tier non-defensive writing posture;
- aggregate-score wins with critical slice regressions;
- mechanism claims without mechanism evidence;
- selected-primary fingerprint propagation;
- out-of-scope strong-paper gates with explicit claim limits.
