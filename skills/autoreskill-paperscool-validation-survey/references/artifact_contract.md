# Artifact Contract

Use this reference when writing or auditing `.autoreskill/` artifacts for a papers.cool validation survey.

## Required Artifacts

```text
.autoreskill/survey/FIELD_DISTANCE_POLICY.json
.autoreskill/survey/PAPER_CODE_SURVEY_PLAN.json
.autoreskill/survey/RAW_PAPERSCOOL_HARVEST.jsonl
.autoreskill/survey/TOPIC_SCREENING_LEDGER.json
.autoreskill/survey/EXCLUSION_AUDIT.json
.autoreskill/survey/PAPER_CODE_CANDIDATES.json
.autoreskill/survey/REPO_STATIC_EVIDENCE.json
.autoreskill/survey/CODE_MECHANISM_MAP.json
.autoreskill/ideation/INNOVATION_MIGRATION_MATRIX.json
.autoreskill/ideation/FAST_VALIDATION_QUEUE.json
```

Optional but recommended:

```text
.autoreskill/survey/CURRENT_FIELD_BASELINE_LEDGER.json
.autoreskill/survey/NOVELTY_RISK_LEDGER.json
.autoreskill/user_view/innovation_story/03_CODE_TRANSFER_STORY.md
```

## Row Requirements

`PAPER_CODE_SURVEY_PLAN.json`:

- `target_task`
- `venue_scope` or `source_scope`
- `year_range` or `date_scope`
- `source_lanes`
- `field_distance_policy_ref`
- `exclusion_rules`
- `coverage_policy`
- `audit_policy`

`RAW_PAPERSCOOL_HARVEST.jsonl`:

- One JSON object per paper.
- Preserve papers.cool fields such as `paper_id`, `title`, `abstract`, `authors`, `subjects`, `paper_url`, `official_url`, `pdf_url`, `venue_title`, `source_url`, and retrieval metadata.

`TOPIC_SCREENING_LEDGER.json`:

- Use `papers[]`, `screened[]`, or `rows[]`.
- Each row should include `paper_id`, `title`, `target_task`, `field_distance`, `source_lane`, `usage_role`, `decision`, and `reason`.

`EXCLUSION_AUDIT.json`:

- Include `summary` counts by reason.
- Include `examples` or `excluded[]` rows with `paper_id`, `title`, `reason`, and `field_distance`.

`PAPER_CODE_CANDIDATES.json`:

- Use `candidates[]`.
- Each row should include `paper_id`, `title`, `year`, `venue` or `source`, `field_distance`, `source_lane`, `usage_role`, `code_url` or `code_status`, `match_reason`, and `decision`.

`REPO_STATIC_EVIDENCE.json`:

- Use `repositories[]`.
- Each row should include `paper_id`, `repo_url` or `repo_ref`, `repo_status`, `code_available`, `paper_code_match`, `static_evidence`, and `validity_decision`.
- `static_evidence` should record entrypoints, configs, metrics, losses, data requirements, active files, and dependency or checkpoint assumptions when available.

`CODE_MECHANISM_MAP.json`:

- Use `mechanisms[]`.
- Each row should include `mechanism_id`, `source_paper_id`, `source_repo_ref`, `field_distance`, `source_task`, `mechanism_summary`, `active_path_evidence`, `code_evidence_refs`, `target_pressure`, `adaptation_needed`, `known_failure_modes`, and `evidence_boundary`.

`INNOVATION_MIGRATION_MATRIX.json`:

- Use `migrations[]`, `ideas[]`, or `rows[]`.
- Each row should include `migration_id`, `source_mechanism_id`, `source_paper_id`, `field_distance`, `target_task`, `adaptation_plan`, `required_code_changes`, `required_protocol_changes`, `novelty_or_overlap_risk`, `claim_scope`, `validation_route`, `falsifier`, and `lifecycle_status`.

`FAST_VALIDATION_QUEUE.json`:

- Use `ideas[]`, `queue[]`, or `rows[]`.
- Each row should include `idea_id`, `source_paper_id` or `source_mechanism_id`, `target_task`, `implementation_scope`, `expected_files_to_edit`, `requires_new_dataset`, `requires_large_model`, `requires_diffusion_or_generation`, `estimated_gpu_cost`, `minimal_validation_dataset`, `success_metric`, `falsifier`, and `priority`.

## Authority Rules

- JSON artifacts are the authority. Markdown/wiki notes are derived views.
- Same-field rows may appear in screening, baseline, novelty, or related-work ledgers. They must not appear as innovation-source migrations unless `override_reason` is explicit.
- Empty candidate or validation queues are acceptable only when the artifact records a clear `no_viable_candidate_reason` or equivalent project-level decision.
