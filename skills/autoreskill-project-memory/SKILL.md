---
name: autoreskill-project-memory
description: Project memory and evidence cart for portable AutoResearch. Use when reading or writing .autoreskill memory, decision logs, evidence ids, PaperNexus evidence, experiment evidence, review evidence, or exporting compact packets for child agents.
metadata:
  short-description: Manage AutoResearch memory and evidence
---

# AutoResearch Project Memory

Use this skill to keep role passes independent from the chat transcript. The main agent should pass evidence ids and artifact paths, not hidden reasoning.

## Files

- `.autoreskill/memory.md`: concise durable project memory.
- `.autoreskill/decision_log.jsonl`: control-plane decisions and reasons.
- `.autoreskill/evidence_cart.jsonl`: all PaperNexus, literature, experiment, writing, and review evidence.

## Scripts

```bash
python scripts/memory_read.py --project <project-root>
python scripts/memory_write.py --project <project-root> --section "Decision" --text "..."
python scripts/evidence_cart.py add --project <project-root> --source-type papernexus --item-type snippet --text "..." --tag ideation
python scripts/evidence_cart.py list --project <project-root> --tag ideation
python scripts/evidence_cart.py export --project <project-root> --tag ideation --limit 20
python scripts/evidence_lint.py --project <project-root> --require-reuse
```

## Evidence Rules

- Every strong claim must point to an `evidence_id`.
- Evidence from provider/live discovery is provisional until imported and graph-visible.
- Experiment evidence must include command/path/seed/metric when available.
- Review evidence must include severity and closure status.

Read `references/memory_schema.md`, `references/decision_log_schema.md`, and `references/evidence_cart_schema.md` for schemas.
