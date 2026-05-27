---
name: autoreskill-analyze-results
description: Analyze portable AutoResearch experiment results. Use to produce claim-evidence matrix, track verdicts, unsupported claims, narrative report, tables, figures, statistics, and claim downgrades under autopilot policy.
metadata:
  short-description: Analyze experiment results and claims
---

# Analyze Results

Use after experiment proof exists.

Outputs:

- `analyzer/CLAIM_EVIDENCE_MATRIX.md`
- `analyzer/TRACK_VERDICTS.md`
- `analyzer/UNSUPPORTED_CLAIMS.md`
- `analyzer/NARRATIVE_REPORT.md`
- `analyzer/tables/`
- `analyzer/figures/`

Rules:

- Compare baseline and proposed side by side.
- Prefer multi-seed. If budget prevents it, downgrade claim strength.
- Do not report only best result.
- Unsupported claims must be removed or softened before writing.
- Figures/tables must be reproducible from scripts or data.

Validation:

```bash
python scripts/analysis_lint.py --project <project-root>
python scripts/analysis_scaffold.py --project <project-root>
```

Use `--strict` before final packaging if unsupported claims and narrative report must be mandatory.

Read references for schemas and statistics.
