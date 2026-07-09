# Paper-Code Innovation Transfer Contract

Use this reference when a job asks for paper survey, code survey, repository validation, source-code analysis, innovation extraction, or migration of ideas into a target research task.

This contract exists because recent AutoResearch threads repeatedly needed the same loop:

```text
paper discovery -> code availability check -> repository static evidence -> source mechanism map -> transferable innovation extraction -> target-task migration matrix -> selected validation plan
```

Do not treat this as a replacement for PaperNexus evidence, experiment planning, or run validation. It is an evidence bridge from external papers and repositories into the normal AutoResearch ideation and experiment workflow.

## Table Of Contents

- Required Layers
- Canonical Artifacts
- Artifact Expectations
- Validity Rules
- Stage Integration
- Standalone Invocation

## Required Layers

Keep three layers separate.

1. Raw candidates:
   - Search/discovery results, venue/year filters, paper ids, code URLs, project pages, and initial inclusion/exclusion reasons.
   - Raw hits do not support innovation claims.

2. Repository static evidence:
   - Repository exists, license/visibility if known, code depth, training/evaluation entrypoints, configs, data assumptions, metric implementation, checkpoint/model dependency, paper-code match, and active path evidence.
   - Static evidence supports feasibility and mechanism-source claims only.

3. Reviewed transfer decisions:
   - Source mechanism, target pressure, adaptation needed, protocol changes, novelty risk, claim boundary, implementation route, validation/falsification plan, and lifecycle decision.
   - Only reviewed transfer rows may feed ideation, idea_gate, experiment_plan, or user-facing innovation stories.

## Canonical Artifacts

Write structured artifacts under `.autoreskill/` even when the user also asks for Obsidian/wiki notes:

```text
.autoreskill/survey/PAPER_CODE_SURVEY_PLAN.json
.autoreskill/survey/PAPER_CODE_CANDIDATES.json
.autoreskill/survey/REPO_STATIC_EVIDENCE.json
.autoreskill/survey/CODE_MECHANISM_MAP.json
.autoreskill/ideation/INNOVATION_MIGRATION_MATRIX.json
.autoreskill/user_view/innovation_story/03_CODE_TRANSFER_STORY.md
```

`03_CODE_TRANSFER_STORY.md` is optional and user-facing. It must not replace the JSON authorities.

## Artifact Expectations

`PAPER_CODE_SURVEY_PLAN.json` should record:

- `target_task`
- `source_lanes`
- `year_range` or explicit date scope
- `venue_scope`
- `paper_count_goal` or coverage policy
- `exclusion_rules`
- `output_targets` when writing wiki notes
- `audit_policy`

`PAPER_CODE_CANDIDATES.json` should contain `papers[]` or `candidates[]` rows with:

- stable `paper_id`
- `title`
- `year`
- `venue`
- `lane`
- paper URL or identifier
- code URL or explicit no-code status
- raw source
- inclusion decision and reason

`REPO_STATIC_EVIDENCE.json` should contain `repositories[]` rows with:

- `paper_id`
- `repo_url`
- `repo_status`: `valid`, `thin`, `project_page`, `benchmark_only`, `mismatch`, `dead_link`, `needs_review`, or equivalent
- `code_available`
- `paper_code_match`
- `static_evidence`: files, entrypoints, configs, metrics, losses, data requirements, active flags, and smoke/readability notes
- `validity_decision`
- `failure_reason` when invalid or parked

`CODE_MECHANISM_MAP.json` should contain `mechanisms[]` rows with:

- `mechanism_id`
- `source_paper_id`
- `source_repo_ref`
- `code_evidence_refs`
- `mechanism_summary`
- `active_path_evidence`
- `source_task`
- `transfer_axis`
- `target_pressure`
- `known_failure_modes`
- `evidence_boundary`

`INNOVATION_MIGRATION_MATRIX.json` should contain `migrations[]`, `ideas[]`, or `rows[]` with:

- `migration_id`
- `source_mechanism_id`
- `target_task`
- `adaptation_plan`
- `required_code_changes`
- `required_protocol_changes`
- `novelty_or_overlap_risk`
- `claim_scope`
- `validation_route`
- `falsifier`
- `lifecycle_status`: direct_transfer, needs_adaptation, diagnostic_only, selected_candidate, parked, killed, source_limited, or equivalent
- `objective_class`: normally `innovation_validation`, `structural_repair`, or `diagnostic`; avoid `parameter_tuning` unless the mechanism is already defined and only a scalar axis is being chosen.

## Validity Rules

- A paper without code can still be literature evidence, but not code-transfer evidence.
- A project page, benchmark wrapper, leaderboard repo, or README-only repo must be marked separately from a valid implementation repo.
- A valid repo is not a valid innovation point. It becomes a transfer candidate only after mechanism mapping and target adaptation are recorded.
- Code availability is not effectiveness evidence. Performance claims require matched run artifacts and metric trajectories.
- Synthetic smoke tests prove interface readiness only. They do not validate paper effectiveness.
- If source code reveals that the apparent idea is just parameter tuning, record it as tuning or diagnostic. Do not relabel it as a paper-level innovation.
- If the source mechanism needs a different dataset/protocol/metric than the target task, record the protocol delta before experiment planning.
- For GCD/DomainGCD/ContinueGCD surveys, exclude or separately mark medical/biomedical/clinical, 3D, and open-vocabulary scene-understanding items unless the user explicitly overrides.

## Stage Integration

- `literature_review`: use the candidate ledger to improve SOTA/source coverage. Do not let repository validity substitute for citation closure.
- `ideation`: use `CODE_MECHANISM_MAP.json` and `INNOVATION_MIGRATION_MATRIX.json` as mechanism-transfer inputs. Ideas still need a three-or-more innovation bundle and PaperNexus/literature grounding.
- `idea_gate`: select only migration rows with explicit target adaptation, novelty risk, evidence boundary, and validation route.
- `experiment_plan`: carry source repo refs, active-code-path evidence, protocol deltas, and falsifiers into `INNOVATION_PACKET.json` and `TRACK_PLAN_MATRIX.json`.
- `code`: implement the selected plan under the normal real-code readiness contract. The source repository does not satisfy target implementation readiness by itself.
- `analysis`: separate promoted evidence from candidate-only, static-code feasibility, failed migrations, and parked ideas.

## Standalone Invocation

When called outside a full `.autoreskill` stage:

1. Create or reuse `.autoreskill/survey/`.
2. Write the canonical artifacts above.
3. Write requested wiki notes from the structured artifacts.
4. Run:

```bash
python <skill-root>/scripts/paper_code_transfer_lint.py --project <project-root> --required
```

5. If the lint fails, repair missing audit layers. Do not summarize around a missing layer as if it were complete.
