# Citation Quality Profile

`literature/CITATION_QUALITY_PROFILE.json` is an optional writing-quality
dashboard derived from `literature/CITATION_QUEUE.json`. It adapts the
paper-writing skill group's LQS and A/B/C/D citation-depth ideas, but it is not
a PaperNexus evidence authority and must not replace citation integrity lint.

Run:

    python scripts/citation_quality_profile.py --project <project-root>
    python scripts/citation_quality_profile.py --project <project-root> --check

The profile scores recency, citation impact, venue, institution, and acceptance
status when those fields are available. Missing optional metadata produces
warnings rather than hard failures because citation queue schemas vary across
projects.

Interpretation:

- `must_cite`: usually A/B-level discussion candidates.
- `conditional`: usually C-level support candidates.
- `drop_or_watchlist`: weak or under-specified candidates until stronger
  evidence or venue status is available.

Survey-mode thresholds such as within-one-year ratio, accepted ratio, and
arXiv-only ratio are dashboard warnings. Method papers may use the warnings to
guide related-work repair, but WorkflowGuard should still rely on existing
PaperNexus evidence closure, citation queue, and citation lint authorities.
