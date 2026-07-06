# Blocker Repair Matrix

| Reason pattern | Class | Action |
| --- | --- | --- |
| `negative_evidence_missing` | `auto_repairable` | run `negative_evidence_pack`; if empty, write `absence_confidence` |
| `research_controller_unavailable` | `degradable` | use `research_material_pack + idea_catalyst + ideation-panel` |
| `import_wait` | `async_wait` | poll `import_workflow status` until timeout, then use discovery evidence as provisional |
| `dry_run_failed` | `auto_repairable` | repair up to 3 times, then shrink experiment or rollback plan |
| `single_seed_only` | `degradable` | run up to three total random seeds if budget allows, else downgrade claim |
| `review_high_issue_open` | `auto_repairable` | create repair packet; after 3 rounds downgrade/delete claim |
| `budget_exceeded` | `hard_stop` | shrink task or stop current route |
| `data_license_blocked` | `hard_stop` | switch dataset or stop route |
