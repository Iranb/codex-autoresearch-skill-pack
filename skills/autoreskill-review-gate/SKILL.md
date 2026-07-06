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
- Treat metric cherry-picking as a soundness issue. Reviewer findings should block or downgrade claims that rely on a single favorable metric component when the experiment's locked `metric_policy` requires a full vector, composite/stress metric, or material-regression checks; for GCD-style protocols, `New`-only improvement cannot justify a broad performance claim if `All`, `Old`, or other required metrics regress or are missing.
- Submission readiness: verify final package.
- During `review_pressure` and `submission_ready`, keep `.autoreskill/user_view/innovation_story/` synchronized with reviewer outcomes. If a risk is closed, explain where the story or evidence answers it; if a claim is downgraded or waived, update `02_CLAIM_EVIDENCE_MAP.md` and the storyline defense instead of leaving the user-facing narrative stronger than the evidence.
- After review findings exist, generate `reviewer/WEAKNESS_ROUTING_PLAN.json` to map weaknesses to the responsible child skill. This plan is routing evidence only; `REVIEW_FINDINGS.json` remains the issue authority.

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
python scripts/weakness_router.py --project <project-root>
python scripts/weakness_router.py --project <project-root> --check
python scripts/citation_lint.py --project <project-root>
python scripts/submission_lint.py --project <project-root>
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage review_pressure
```

The linter blocks unresolved high/critical review findings unless they are explicitly closed, fixed, waived, or accepted as risk.

Read `references/weakness_routing.md` plus references for scorecards and readiness gates.
