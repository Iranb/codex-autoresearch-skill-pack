---
name: autoreskill-literature-review
description: Literature review skill for portable AutoResearch. Use to produce SOTA matrix, gap synthesis, citation queue, baseline/dataset/metric anchors, and target-venue-ready related-work evidence from PaperNexus and literature discovery outputs.
metadata:
  short-description: Build SOTA matrix and gap synthesis
---

# Literature Review

Use after topic search and graph build. Consume PaperNexus discovery/material packs and write:

- `.autoreskill/literature/LITERATURE_REVIEW.md`
- `.autoreskill/literature/SOTA_MATRIX.md`
- `.autoreskill/literature/GAP_SYNTHESIS.md`
- `.autoreskill/literature/CITATION_QUEUE.json`

Every claim should cite an evidence id or a paper id. Keep unresolved citations in the queue.

If the existing discovery packets do not cover SOTA, closest priors, baseline candidates, datasets, metrics, protocols, limitations, negative evidence, or target-venue related-work expectations, trigger targeted PaperNexus literature discovery before finalizing the review. Do not treat a first-pass topic search as sufficient coverage when the SOTA matrix or citation queue exposes gaps. After discovery, screen usable papers, record the paper-selection scorecard and graph-import/material plan, and rely on PaperNexus material or split-reading evidence rather than raw search rows for claims.

## Deterministic Helpers

```bash
python scripts/literature_scaffold.py --project <project-root>
python scripts/literature_lint.py --project <project-root>
```

Read `references/sota_matrix_schema.md` and `references/citation_triage.md`.
