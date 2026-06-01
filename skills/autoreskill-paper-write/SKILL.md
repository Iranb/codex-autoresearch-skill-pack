---
name: autoreskill-paper-write
description: Academic writing skill for portable AutoResearch. Use to write evidence-bound manuscripts, story contracts, target-venue summaries, significance statements, cover letters, limitations, related work, and submission notes for top conferences or journals without inventing citations or results.
metadata:
  short-description: Write evidence-bound research papers
---

# Paper Write

Use after analysis has claim-evidence outputs.

Rules:

- Strong claims must link to experiment or citation evidence.
- Unsupported claims are softened, moved to limitations, or deleted.
- Do not invent citations, results, datasets, or baselines.
- If a paragraph needs a citation, closest-prior contrast, related-work bridge, limitation source, or target-venue framing that is missing from the citation queue, trigger targeted literature discovery instead of writing around the gap.
- Venue mode should prepare a venue profile, target-venue summary, required checklist/admin gaps, and venue-specific materials for top conferences or journals. NMI is one supported profile, not the only target.

## Deterministic Helpers

```bash
python scripts/paper_scaffold.py --project <project-root> --venue NeurIPS
python scripts/write_package_lint.py --project <project-root>
```

Read `references/story_contract_schema.md`, `references/venue_template_mapping.md`, and venue-specific notes when available.
