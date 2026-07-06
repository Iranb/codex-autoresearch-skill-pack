# Weakness Routing

`reviewer/WEAKNESS_ROUTING_PLAN.json` maps reviewer findings to the child skill
most likely to repair them. It is a routing helper, not issue closure.
`reviewer/REVIEW_FINDINGS.json` remains the review authority, and high/critical
findings remain blocking until they are fixed, closed, waived, or accepted as
risk through the existing review gate.

Run:

    python scripts/weakness_router.py --project <project-root>
    python scripts/weakness_router.py --project <project-root> --check

Common routes:

- citation, recency, arXiv-only, and related-work coverage -> literature review
- novelty, closest-prior, protocol norm, and source-backed objection ->
  PaperNexus innovation
- hypothesis, control, falsifier, and metric/dataset drift -> experiment plan
- missing trials, std, ablation, and replication -> experiment run
- statistics, unsupported claims, and best-result-only reporting -> analysis
- structure, claim strength, taxonomy, clarity, captions, figures, and tables ->
  paper writing

Ambiguous findings are routed back to `autoreskill-review-gate` with low
confidence so a repair packet can be written explicitly.
