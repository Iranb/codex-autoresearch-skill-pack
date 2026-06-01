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
- Use `.autoreskill/user_view/innovation_story/` as the current user-facing narrative contract. The manuscript should follow the belief shift, opening tension, method-as-resolution, proof ladder, and claim limits recorded there, while still treating experiment and citation artifacts as the evidence authorities.
- If writing changes the story, update the story docs too. Do not strengthen claims in prose unless `02_CLAIM_EVIDENCE_MAP.md`, the analysis files, and the citation queue support them.

## Deterministic Helpers

```bash
python scripts/paper_scaffold.py --project <project-root> --venue NeurIPS
python scripts/write_package_lint.py --project <project-root>
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage writing
```

Read `references/story_contract_schema.md`, `references/venue_template_mapping.md`, and venue-specific notes when available.
