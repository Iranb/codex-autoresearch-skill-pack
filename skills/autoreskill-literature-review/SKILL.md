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

## Deterministic Helpers

```bash
python scripts/literature_scaffold.py --project <project-root>
python scripts/literature_lint.py --project <project-root>
```

Read `references/sota_matrix_schema.md` and `references/citation_triage.md`.
