---
name: autoreskill-analyze-results
description: Analyze portable AutoResearch experiment results. Use to produce claim-evidence matrix, track verdicts, unsupported claims, narrative report, tables, figures, statistics, and claim downgrades under autopilot policy.
metadata:
  short-description: Analyze experiment results and claims
---

# Analyze Results

Use after experiment proof exists.

Outputs:

- `analyzer/CLAIM_EVIDENCE_MATRIX.md`
- `analyzer/TRACK_VERDICTS.md`
- `analyzer/UNSUPPORTED_CLAIMS.md`
- `analyzer/NARRATIVE_REPORT.md`
- `analyzer/tables/`
- `analyzer/figures/`
- `user_view/innovation_story/00_STORYLINE_DESIGN.md`
- `user_view/innovation_story/01_METHOD_INNOVATION_STORY.md`
- `user_view/innovation_story/02_CLAIM_EVIDENCE_MAP.md`

Rules:

- Compare baseline and proposed side by side.
- Prefer multi-seed. If budget prevents it, downgrade claim strength.
- Do not report only best result.
- Use `coder/EXPERIMENT_LEDGER.json` as the run trajectory authority. Report promoted, not_promoted, failed, and rollback decisions.
- Treat `best_run` and `track_best_runs` promoted entries as the only sources for improvement claims unless a later confirmation run supersedes them.
- Treat `candidate_supported` as pilot evidence only. It may justify ablation/confirmation scheduling, but it must not be phrased as a stable improvement.
- Report each innovation track with selected idea, mechanism, mechanism type, promotion stage, ablation/confirmation links, verdict, and next action.
- Downgrade or remove claims when improvement comes from a fixture, single seed, missing matched baseline, protected-path hash change, protocol drift, or unreconciled run.
- Negative and regressed runs are useful evidence for pruning candidates, not support for stronger manuscript claims.
- If results contradict the proposed mechanism or need source-backed limitation/negative-evidence framing, trigger targeted PaperNexus literature discovery and record the evidence boundary before writing.
- Unsupported claims must be removed or softened before writing.
- Figures/tables must be reproducible from scripts or data.
- After analysis, update the user-facing story docs so the storyline follows the evidence instead of the original hope. Revise the proof ladder, claim limits, experiment mapping, and current user-facing summary. Candidate-supported evidence remains pilot-only in both the analysis files and `02_CLAIM_EVIDENCE_MAP.md`.

Validation:

```bash
python scripts/analysis_lint.py --project <project-root>
python scripts/analysis_scaffold.py --project <project-root>
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage analysis
```

Use `--strict` before final packaging if unsupported claims and narrative report must be mandatory.

Read references for schemas and statistics.
