# CCF-A Writing-Style Corpus Audit Contract

Use this reference when a user asks Codex to study how top-tier/CCF-A oral, spotlight, award, or best papers are written, especially from papers.cool, official venue pages, proceedings, OpenReview, arXiv, PaperNexus, or local PDFs. This is the corpus evidence layer: its goal is to produce evidence-bounded findings, not to rank papers, infer scientific effectiveness, or directly rewrite a manuscript.

For reusable writing standards, read `ccfa_writing_principles.md`. For revising a concrete manuscript, read `ccfa_manuscript_revision_workflow.md` and produce `.autoreskill/paper/CCFA_WRITING_AUDIT.md` before rewriting.

## Table Of Contents

- Purpose And Evidence Boundary
- Source Priority
- Required Artifacts
- Workflow
- Rhetorical Move Codebook
- Evidence Synthesis Rules
- Manuscript Application
- Quality Gates
- Red Flags

## Purpose And Evidence Boundary

Separate three evidence tiers in every report:

- `observed_corpus`: supported by harvested metadata, normalized labels, verified award sources, or complete corpus-level counts.
- `sample_fulltext`: supported by downloaded/extracted full text or manually read PDFs for a declared sample.
- `expert_heuristic`: writing advice inferred from top-tier reviewing practice but not measured over the corpus.

Never state "CCF-A papers do X" unless the scope audit supports that level of coverage. Prefer "in the audited sample", "among verified award papers", or "in downloaded full-text examples" when coverage is partial.

## Source Priority

Use this source order when evidence conflicts:

1. Official conference/proceedings/award pages.
2. Publisher proceedings pages, OpenReview records, arXiv records, DOI pages, or accepted-paper lists.
3. papers.cool metadata and presentation groups.
4. Secondary blogs, newsletters, personal pages, or mirrors.

Secondary sources can guide discovery but cannot verify award status by themselves. Mark them as `secondary_only` unless an official source confirms the claim.

## Required Artifacts

Create these files under `.autoreskill/writing_style/` unless the user asks for another project-local output directory. Keep human-facing reports derived from structured artifacts.

### `WRITING_STYLE_CORPUS_PLAN.json`

Required fields:

- `analysis_questions`: what writing-style questions the user wants answered.
- `target_venues`: venue families and years.
- `ccf_source_url`, `ccf_source_checked_at`, and `ccf_a_venue_families` when the user asks for CCF-A.
- `source_priority`: which sources are authoritative.
- `harvest_queries`: venue URLs, papers.cool groups, search terms, or local paths.
- `inclusion_rules` and `exclusion_rules`.
- `sample_strategy`: complete corpus, stratified sample, award-only sample, oral-only sample, or manual subset.
- `intended_outputs`: report, checklist, manuscript audit, or revision plan.

### `RAW_SOURCE_HARVEST.jsonl`

Write one raw row per source hit before filtering or deduplication. Recommended fields:

- `source_name`, `source_url`, `harvested_at`.
- `venue_id`, `venue_family`, `year`, `group`, `raw_label`.
- `paper_id`, `title`, `authors`, `abstract`.
- `paper_url`, `pdf_url`, `openreview_url`, `arxiv_id`, `doi`.
- `badges`, `award_text`, `presentation_text`.
- `row_hash` or another stable raw-record id.

Do not overwrite raw rows after later verification. Add reviewed decisions in later artifacts.

### `STYLE_CANDIDATE_LEDGER.json`

Deduplicate raw hits into reviewed candidate papers. Required row fields:

- `paper_id`, `title`, `venue_family`, `venue_id`, `year`.
- `source_row_refs`: raw rows supporting the candidate.
- `candidate_role`: `award`, `oral`, `spotlight`, `poster`, `control`, or `other`.
- `inclusion_decision`: `include`, `exclude`, `park`, or `source_limited`.
- `decision_reason`.

### `CORPUS_SCOPE_AUDIT.json`

Record:

- `ccf_source_url`, `ccf_source_checked_at`, and `ccf_a_venue_families`.
- `included_venue_families`, `excluded_venue_families`, `missing_venue_families`.
- `year_coverage`, `group_coverage`, and candidate counts by venue/year/label.
- `generalization_limits`: exactly what the report cannot claim.

### `PRESENTATION_TYPE_NORMALIZATION.json`

Normalize source labels without erasing source-specific meaning. Required row fields:

- `source_name`, `source_url`, `venue_id`, `raw_label`.
- `normalized_label`: `award`, `oral`, `spotlight`, `poster`, `honorable_mention`, `accepted`, `unknown`, or a documented extension.
- `normalization_basis`: official definition, venue policy, papers.cool group, manual inspection, or secondary source.
- `confidence`: `high`, `medium`, or `low`.
- `claim_limit`.

### `AWARD_SOURCE_AUDIT.json`

Required for any best-paper, award, honorable-mention, or similar claim. Required row fields:

- `award_name`, `award_year`, `official_source_url` when available.
- `candidate_paper_id`, `candidate_title`.
- `matched_title`, `match_method`, `match_score`.
- `verification_status`: `official_verified`, `near_exact_verified`, `secondary_only`, `ambiguous`, `unmatched`, or `not_checked`.
- `claim_limit`.

Rows with `secondary_only`, `ambiguous`, `unmatched`, or `not_checked` must not be treated as verified award exemplars.

### `FULLTEXT_COVERAGE_AUDIT.json`

Required before section-level style claims. Required row fields:

- `paper_id`, `title`, `pdf_url` or `fulltext_url`.
- `download_status`: `downloaded`, `cached`, `rate_limited`, `not_found`, `access_blocked`, or `not_attempted`.
- `extraction_status`: `parsed`, `partial`, `failed`, or `not_attempted`.
- `detected_sections`: abstract, introduction, method, experiments, related work, limitations, appendix, or figure captions when available.
- `coverage_basis`: full text, abstract only, metadata only, manual read, or source-limited.
- `claim_limit`.

Do not make introduction, Figure 1, method, experiment-organization, or related-work style claims from rows that only have abstracts or metadata.

### `RHETORICAL_MOVE_ANNOTATION.json`

Required before claiming a writing pattern from full text. Required top-level fields:

- `annotation_codebook_version`.
- `sample_strategy`.
- `annotator` or `annotation_method`.
- `rows`.

Required row fields:

- `paper_id`, `title`, `section`.
- `move`: one item from the codebook or a documented extension.
- `evidence_basis`: sentence id, span text, paragraph id, figure/table id, or manual note.
- `confidence`: `high`, `medium`, or `low`.
- `evidence_tier`: `observed_corpus`, `sample_fulltext`, or `expert_heuristic`.

Use short excerpts only when needed. Prefer paraphrased move labels and sentence/paragraph references over copying long passages.

### `EVIDENCE_SYNTHESIS.json`

Required row fields:

- `finding_id`.
- `finding`: the writing-style pattern or recommendation.
- `evidence_tier`.
- `supporting_artifact_refs`: rows from the above artifacts.
- `counterevidence_or_gaps`.
- `claim_limit`.
- `manuscript_check`: what a user's paper should check or revise.

Every report paragraph that says "good papers tend to..." should trace to at least one synthesis row.

### `WRITING_STYLE_REPORT.md`

The report must include:

- Corpus scope and exclusions.
- Verification status for awards and presentation labels.
- Full-text coverage and sampling limits.
- Rhetorical-move findings grouped by section.
- Writing strengths of the audited papers.
- Manuscript-facing checklist.
- Claim limits and unresolved evidence gaps.

## Workflow

1. Define the scope before downloading. Pin the target CCF source, venue families, years, label groups, and intended claims.
2. Harvest raw rows from each source. Preserve raw metadata in `RAW_SOURCE_HARVEST.jsonl`.
3. Deduplicate into `STYLE_CANDIDATE_LEDGER.json`, but keep raw source refs for every decision.
4. Complete `CORPUS_SCOPE_AUDIT.json` before any cross-venue statement.
5. Normalize labels in `PRESENTATION_TYPE_NORMALIZATION.json`; keep `oral`, `spotlight`, and `award` distinct unless the venue defines them as equivalent.
6. Verify award claims in `AWARD_SOURCE_AUDIT.json`; official sources outrank papers.cool and secondary pages.
7. Resolve full text and extraction status in `FULLTEXT_COVERAGE_AUDIT.json`.
8. Annotate rhetorical moves in `RHETORICAL_MOVE_ANNOTATION.json`. Use complete annotation for small corpora or a declared sample strategy for large corpora.
9. Write `EVIDENCE_SYNTHESIS.json` with evidence tiers and claim limits.
10. Write `WRITING_STYLE_REPORT.md` from the structured artifacts.
11. Run `scripts/writing_style_corpus_lint.py --project <project-root> --required`.
12. If revising a manuscript, read `ccfa_writing_principles.md` and `ccfa_manuscript_revision_workflow.md`, then produce `.autoreskill/paper/CCFA_WRITING_AUDIT.md`.

## Rhetorical Move Codebook

Use these move labels unless the project needs a documented extension:

- `field_pressure`: why the problem matters now.
- `specific_gap`: the precise failure mode, setting, or missing capability.
- `diagnosis`: the hidden cause or mechanism behind the gap.
- `method_as_resolution`: how the method directly addresses the diagnosis.
- `contribution_as_insight`: contribution phrased as a finding, formalization, mechanism, or validated capability.
- `evidence_scope`: datasets, protocols, baselines, backbones, tasks, theory, user studies, or analysis promised early.
- `claim_boundary`: where the claim does not apply or what evidence would be needed for a stronger claim.
- `related_work_positioning`: how prior work is grouped by solved pressure and remaining gap.
- `figure_story`: whether Figure 1 shows failure, diagnosis, resolution, or evidence rather than only a pipeline.
- `experiment_as_rq`: experiment organized as a claim-answering research question.
- `ablation_causal_link`: ablation tied to a contribution or mechanism.
- `limitation_calibration`: limitation used to calibrate claims.
- `sentence_flow`: old-to-new information flow or concrete analytical subjects.

## Evidence Synthesis Rules

- Count first, interpret second. Report candidate counts, verified award counts, full-text counts, and annotated-paper counts.
- Separate metadata findings from full-text findings.
- Separate official verification from secondary discovery.
- Mark label-normalization uncertainty; presentation categories are not globally comparable across venues.
- Treat keyword frequencies as heuristics unless manually validated.
- Do not turn writing patterns into scientific evidence. A style corpus can guide abstract framing and claim calibration, but it cannot support novelty, soundness, or effectiveness claims.
- Record counterexamples when available; strong writing patterns often have venue- or subfield-specific exceptions.

## Manuscript Application

When using the corpus audit to improve a user's paper:

1. Extract the user's current thesis and claim-evidence map.
2. Select only corpus findings whose `manuscript_check` applies to the user's target venue and paper type.
3. Read `ccfa_writing_principles.md` to convert applicable corpus findings into reusable checks.
4. Read `ccfa_manuscript_revision_workflow.md` and rewrite the paper's argument before sentence polishing.
5. Use `CCFA_WRITING_AUDIT.md` to record gap, diagnosis, method-as-resolution, evidence scope, claim calibration, Figure 1 story, experiment RQs, and revision decisions.
6. Do not import stylistic features that conflict with the user's evidence. If a top-tier pattern expects analysis, ablations, or limitations the paper lacks, record it as a missing evidence/revision item rather than writing around it.

## Quality Gates

The audit is incomplete if any of these are missing:

- CCF source/version and venue coverage.
- Raw source harvest.
- Deduplicated candidate ledger.
- Presentation-label normalization.
- Award verification for award claims.
- Full-text coverage for section-level claims.
- Rhetorical move annotations for writing-style findings.
- Evidence synthesis with tiers, supporting refs, and claim limits.
- Lint run output or documented reason the linter could not run.

## Red Flags

Repair the audit before summarizing if:

- The report treats papers.cool labels as official awards.
- CCF-A scope omits venues without saying so.
- A fuzzy title match is treated as exact.
- Abstract-only rows support introduction, method, Figure 1, or experiment-organization claims.
- Keyword counts are presented as rhetorical-move analysis.
- The report says "best papers write like..." without verified award rows.
- The advice copies phrases from papers instead of extracting transferable checks.
- The manuscript revision adopts corpus style without checking the user's own evidence strength.
