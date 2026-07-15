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
- `analyzer/BEST_RUN_SELECTION.json`
- `analyzer/SCORE_VERIFICATION.json`
- `analyzer/SPEC_VIOLATION_AUDIT.json`
- `analyzer/UNSUPPORTED_CLAIMS.md`
- `analyzer/NARRATIVE_REPORT.md`
- `analyzer/tables/`
- `analyzer/figures/`
- `user_view/innovation_story/00_STORYLINE_DESIGN.md`
- `user_view/innovation_story/01_METHOD_INNOVATION_STORY.md`
- `user_view/innovation_story/02_CLAIM_EVIDENCE_MAP.md`

Rules:

- Compare baseline and proposed side by side.
- Verify the full locked `metric_policy`: every required metric component, matched baseline/proposed delta, composite or stress metric, and material-regression check. `SCORE_VERIFICATION.json` must record missing components, parser gaps, material regressions, and whether the policy-positive rule passed.
- Validate metric scale before any claim. Check each `RESULT_SUMMARY.json`, `METRIC_TRAJECTORY.csv`, ledger row, and table input for fraction/percentage consistency, impossible ranges, duplicated scaling, and mixed-unit baseline/proposed comparisons. If scale sanity fails, quarantine the affected artifact, record the parser issue in `SCORE_VERIFICATION.json`, and downgrade or remove the claim until a corrected parser reruns from the raw logs.
- Prefer bounded multi-seed only when it answers a stability question. Stability
  validation is capped at three experiment random seeds; if budget prevents
  2-3 seeds, downgrade claim strength instead of over-reading a single seed.
- Do not report only best result or only the best metric component. For multi-metric protocols, tables and verdicts must show the full metric vector plus the predeclared composite/stress metrics.
- Use `coder/EXPERIMENT_LEDGER.json` as the run trajectory authority. Report
  promoted, not_promoted, failed, rollback, valid negative, refuted,
  inconclusive, invalid, and terminal-program decisions.
- Treat `best_run` and `track_best_runs` promoted entries as the only sources for improvement claims unless a later confirmation run supersedes them, and only when those entries pass the locked `metric_policy`.
- Run `best_run_selector.py` before writing. It is the deterministic selector for promoted evidence and emits the score/spec audit artifacts consumed by paper writing.
- Treat `candidate_supported` as pilot evidence only. It may justify ablation/confirmation scheduling, but it must not be phrased as a stable improvement.
- Report each innovation track with selected idea, mechanism, mechanism type, promotion stage, ablation/confirmation links, verdict, and next action.
- Downgrade or remove claims when improvement comes from a fixture, single seed, more-than-three-seed fishing, missing matched baseline, protected-path hash change, protocol drift, unreconciled run, cherry-picked single metric component, or `New`-only gain with material `All`, `Old`, composite, calibration, tail, unknown-K, or other required metric regression.
- Negative/refuted/inconclusive tracks remain analyzable. They may support
  pruning, scope limits, failure analysis, or a bounded negative finding, but
  cannot count as an effective innovation or positive improvement.
- When a valid terminal non-positive `program_decision` reaches analysis,
  `BEST_RUN_SELECTION.json` must explicitly record
  `terminal_program_no_promoted_run`, `SCORE_VERIFICATION.json` must record
  `not_applicable_no_positive_claim`, and the narrative must preserve
  `improvement_claim_allowed=false`. Do not fabricate a best run to satisfy the
  positive path.
- Positive writing needs one accepted core scientific contribution. Optional
  supporting contributions count only with counterfactual necessity; validation,
  analysis, engineering support, parameter tuning, and negative tracks do not
  increase the contribution count.
- If results contradict the proposed mechanism or need source-backed limitation/negative-evidence framing, trigger targeted PaperNexus literature discovery and record the evidence boundary before writing.
- Unsupported claims must be removed or softened before writing.
- Figures/tables must be reproducible from scripts or data.
- Tables and figures should carry a non-trivial paper insight, not only raw output. Record enough caption/key-finding material for `autoreskill-paper-write` to build `paper/WRITING_QUALITY_PROFILE.json`; experimental tables should expose mean/std or the explicit reason that variance is unavailable.
- After analysis, update the user-facing story docs so the storyline follows the evidence instead of the original hope. Revise the proof ladder, claim limits, experiment mapping, and current user-facing summary. Candidate-supported evidence remains pilot-only in both the analysis files and `02_CLAIM_EVIDENCE_MAP.md`.

Validation:

```bash
python scripts/analysis_lint.py --project <project-root>
python scripts/best_run_selector.py --project <project-root>
python scripts/best_run_selector.py --project <project-root> --check
python scripts/analysis_scaffold.py --project <project-root>
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage analysis
```

Use `--strict` before final packaging if unsupported claims and narrative report must be mandatory.

Read references for schemas and statistics.
