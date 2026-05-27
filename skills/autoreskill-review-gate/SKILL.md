---
name: autoreskill-review-gate
description: Reviewer and cross-review gate for portable AutoResearch. Use to run isolated novelty/soundness/significance/clarity/reproducibility review, citation integrity checks, issue repair loops, claim downgrade, and submission readiness gate.
metadata:
  short-description: Review and submission gate
---

# Review Gate

Use after manuscript or major section drafts exist.

Modes:

- Reviewer: strict but fair review.
- Cross-Reviewer: isolated external critique, sees only explicit packet.
- Citation gate: check all citations are real and used correctly.
- Submission readiness: verify final package.

If high/medium issues remain, autopilot should create repair packets. After three failed repair rounds, downgrade/delete claims or switch route.

`reviewer/REVIEW_FINDINGS.json` is the machine-readable authority for review pressure. If review comments come from `academic-paper-reviewer`, first convert them with:

```bash
python ~/.codex/skills/academic-paper-reviewer/scripts/review_findings_adapter.py --project <project-root> --input <review-output.md>
```

## Validation

Before packaging or moving past review pressure, run:

```bash
python scripts/review_lint.py --project <project-root>
python scripts/review_scaffold.py --project <project-root>
python scripts/citation_lint.py --project <project-root>
python scripts/submission_lint.py --project <project-root>
```

The linter blocks unresolved high/critical review findings unless they are explicitly closed, fixed, waived, or accepted as risk.

Read references for scorecards and readiness gates.
