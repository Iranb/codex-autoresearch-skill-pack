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
- When novelty, related-work, missing-baseline, protocol-norm, significance, or citation findings are open, route repair through targeted PaperNexus literature discovery/material evidence before accepting the claim or waiving the issue.
- Submission readiness: verify final package.
- During `review_pressure` and `submission_ready`, keep `.autoreskill/user_view/innovation_story/` synchronized with reviewer outcomes. If a risk is closed, explain where the story or evidence answers it; if a claim is downgraded or waived, update `02_CLAIM_EVIDENCE_MAP.md` and the storyline defense instead of leaving the user-facing narrative stronger than the evidence.

If high/medium issues remain, autopilot should create repair packets. After three failed repair rounds, downgrade/delete claims or switch route.

`reviewer/REVIEW_FINDINGS.json` is the machine-readable authority for review pressure. If review comments come from `academic-paper-reviewer`, first convert them with:

```bash
python <skill-root>/../academic-paper-reviewer/scripts/review_findings_adapter.py --project <project-root> --input <review-output.md>
```

## Validation

Before packaging or moving past review pressure, run:

```bash
python scripts/review_lint.py --project <project-root>
python scripts/review_scaffold.py --project <project-root>
python scripts/citation_lint.py --project <project-root>
python scripts/submission_lint.py --project <project-root>
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage review_pressure
```

The linter blocks unresolved high/critical review findings unless they are explicitly closed, fixed, waived, or accepted as risk.

Read references for scorecards and readiness gates.
