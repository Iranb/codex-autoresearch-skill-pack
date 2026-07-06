---
name: autoreskill-paperscool-validation-survey
description: Build audited papers.cool topic surveys for AutoResearch paper-code innovation transfer. Use when Codex needs to harvest papers.cool conference or topic pages, avoid same-field papers as innovation sources, skip heavy LLM/diffusion or impractical papers, verify paper-code repositories, extract transferable mechanisms, and produce fast-validation queues for GCD, ContinueGCD, DomainGCD, or related CS research projects.
---

# Autoreskill Papers.cool Validation Survey

## Purpose

Use this skill to turn papers.cool topic or venue pages into an audited innovation-source survey for an AutoResearch project. The output is not a generic literature review. It separates same-field papers for baselines and novelty risk, near/far-neighbor papers for transferable mechanisms, and infeasible papers for exclusion.

This skill complements:

- `papers-cool-harvest`: use its harvester for raw papers.cool page extraction when available.
- `autoreskill-workflow`: consume the generated `.autoreskill/survey/` and `.autoreskill/ideation/` artifacts in the normal AutoResearch workflow.

## Non-Negotiable Rules

1. Do not use same-field papers as innovation sources. Route them to baseline, novelty-risk, or related-work ledgers.
2. Do not let LLM, VLM, diffusion, text-to-image generation, huge pretraining, medical, 3D, or open-vocabulary scene-understanding papers enter the fast-validation queue unless the user explicitly overrides the scope.
3. Keep raw papers, screening decisions, repository static evidence, mechanism extraction, migration decisions, and validation plans as separate evidence layers.
4. Treat static code evidence as feasibility evidence only. It is not effectiveness evidence.
5. Keep every exclusion and downgrade auditable so the same papers are not repeatedly reprocessed.

## Required Inputs

Before harvesting or screening, establish:

- `target_task`: for example `GCD`, `ContinueGCD`, `DomainGCD`, `OWR-GCD`.
- `project_root`: the directory that will contain `.autoreskill/`.
- `venue_scope`: papers.cool venue/group URLs, year range, topic pages, or a raw export path.
- `source_lane_policy`: which fields are direct, near-neighbor, far-neighbor, or blocked.
- `fast_validation_constraints`: maximum implementation size, dataset constraints, GPU budget, skipped model families, and required falsifier style.

If the user only gives a broad topic, first write a conservative `FIELD_DISTANCE_POLICY.json` and ask only if the direct/near/far boundary is ambiguous enough to affect results.

## Workflow

1. **Lock target field**
   - Write `.autoreskill/survey/FIELD_DISTANCE_POLICY.json`.
   - Define `direct_field`, `near_neighbor`, `far_neighbor`, and `blocked` terms.
   - For GCD, direct field includes GCD/NCD/CGCD-style category discovery. For ContinueGCD, direct field is continual category discovery; broader Continual Learning can be near-neighbor.

2. **Plan harvest**
   - Write `.autoreskill/survey/PAPER_CODE_SURVEY_PLAN.json`.
   - Record target task, papers.cool URLs, venue/year/topic scope, source lanes, hard exclusions, coverage target, and audit policy.

3. **Harvest papers.cool**
   - Prefer the `papers-cool-harvest` script for deterministic extraction.
   - Preserve raw results as `.autoreskill/survey/RAW_PAPERSCOOL_HARVEST.jsonl`.
   - Do not collapse raw results directly into candidates.

4. **Run field-distance triage**
   - Write `.autoreskill/survey/TOPIC_SCREENING_LEDGER.json`.
   - For each paper record `field_distance`, `source_lane`, `usage_role`, `decision`, and reasons.
   - Direct-field papers must use `baseline_anchor`, `novelty_risk`, `related_work`, or `excluded`, never `innovation_source`.

5. **Audit exclusions**
   - Write `.autoreskill/survey/EXCLUSION_AUDIT.json`.
   - Count and sample every exclusion class: same-field, LLM/VLM, diffusion/generation, medical, 3D, open-vocabulary scene, no abstract, no code, heavy dependency, dataset unavailable, or out-of-topic.

6. **Discover and verify code**
   - Write `.autoreskill/survey/PAPER_CODE_CANDIDATES.json`.
   - Keep paper id, title, venue/year, field distance, source lane, code URL/status, match reason, and inclusion decision.
   - Mark project pages, README-only repos, benchmark-only repos, mismatches, and no-code papers separately.

7. **Record repository static evidence**
   - Write `.autoreskill/survey/REPO_STATIC_EVIDENCE.json`.
   - Record inspected files, entrypoints, configs, losses, metrics, data assumptions, checkpoints, active code paths, and paper-code match.

8. **Extract transferable mechanisms**
   - Write `.autoreskill/survey/CODE_MECHANISM_MAP.json`.
   - Mechanisms must come from near-neighbor or far-neighbor sources unless an explicit override exists.
   - Explain the source mechanism, target pressure, active code evidence, adaptation needs, known failure modes, and evidence boundary.

9. **Build migration matrix and validation queue**
   - Write `.autoreskill/ideation/INNOVATION_MIGRATION_MATRIX.json`.
   - Write `.autoreskill/ideation/FAST_VALIDATION_QUEUE.json`.
   - Each selected idea must name the source mechanism, target adaptation, expected files to edit, minimal dataset/protocol, metric, falsifier, and expected GPU cost.

10. **Write optional user-facing notes**
    - Optional wiki or Obsidian notes must be generated from the structured JSON authorities, not the other way around.
    - Same-field papers should appear in baseline/novelty sections, not in innovation-source sections.

11. **Run lint**
    - Run:

```bash
python scripts/paperscool_validation_survey_lint.py --project <project-root> --required
```

Repair missing layers or policy violations before summarizing the survey as complete.

## References

Read only the reference needed for the current step:

- `references/field_distance_policy.md`: direct/near/far field rules and task-specific examples.
- `references/artifact_contract.md`: JSON artifact expectations and row-level fields.
- `references/fast_validation_and_evidence_audit.md`: fast-validation scoring, evidence boundaries, and common failure modes.

## Completion Standard

A survey is complete only when:

- Raw harvest, screening, exclusion audit, code candidates, repo evidence, mechanism map, migration matrix, and fast-validation queue all exist.
- Same-field papers are routed away from innovation-source artifacts.
- Heavy or slow-validation papers are excluded or explicitly overridden.
- Every selected idea has a falsifier and minimal validation route.
- The lint script passes, or every remaining warning is explained in the final report.
