# Writing Review Enhancement

`paper/WRITING_QUALITY_PROFILE.json` is an optional drafting dashboard. It
imports the useful writing heuristics from the paper-writing skill group while
preserving the AutoResearch evidence contract.

Run:

    python scripts/writing_quality_profile.py --project <project-root>
    python scripts/writing_quality_profile.py --project <project-root> --check

The profile records:

- inferred or declared `paper_type`;
- paragraph-logic pattern coverage;
- claim counts from `RESEARCH_REPRESENTATION.json`;
- figure/table counts from analyzer artifacts;
- citation-quality profile availability;
- warnings about blocked claims, unpassed grounded writing, unpassed claim
  verification, and survey-mode quantity targets.

Survey thresholds are dashboard warnings. They are useful for surveys and
position papers, but they must not override `GROUNDED_WRITE_PACKAGE.json`,
`PAPER_CLAIM_VERIFICATION.json`, promoted experiment evidence, or PaperNexus
citation/evidence closure.
