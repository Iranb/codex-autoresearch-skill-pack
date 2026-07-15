# User-Facing Innovation Story Contract

Every AutoResearch project maintains a project-bound user-facing innovation story under:

```text
.autoreskill/user_view/innovation_story/
  00_STORYLINE_DESIGN.md
  01_METHOD_INNOVATION_STORY.md
  02_CLAIM_EVIDENCE_MAP.md
  03_CODE_TRANSFER_STORY.md      # optional, only when paper-code migration is in scope
```

This directory is for the user. It is a derived explanation layer, not the source of truth for stage advancement. Machine-readable authorities remain `EXPERIMENT_IDEA_POOL.json`, `IDEA_NOVELTY_VENUE_SCORECARD.json`, `IDEA_DECISION_LEDGER.json`, `INNOVATION_PACKET.json`, `TRACK_PLAN_MATRIX.json`, `EXPERIMENT_REVIEW_PACKET.json`, `EXPERIMENT_LEDGER.json`, `IDEA_OUTCOME_SUMMARY.json`, `CLAIM_EVIDENCE_MATRIX.md`, paper-code transfer JSON artifacts when in scope, and the review/package gates.

## 00_STORYLINE_DESIGN.md

Purpose: design the paper narrative, not the method module list.

Required sections:

- `Paper Thesis`: the one-sentence paper claim.
- `Reader Belief Shift`: what the reader believes before and after the paper.
- `Opening Tension`: the real-world need, current assumption, where it breaks, and the consequence.
- `Hidden Cause`: the deeper reason behind the observed failure.
- `Core Scientific Contribution`: the one causal or scientific contribution the paper must defend, its evidence source, closest-prior delta, falsifier, and claim boundary. Contribution count is not a novelty criterion.
- `Method As Resolution`: how each method move answers the opening tension.
- `Novelty Positioning`: what is new relative to closest priors and what is not new.
- `Proof Ladder`: how main result, ablation, mechanism analysis, robustness, and failure cases support the thesis.
- `Figure Story`: what each major figure should make the reader believe.
- `Reviewer Risk And Defense`: likely objections and where the paper will answer them.
- `Final Narrative Spine`: 5-7 sequential sentences compressing the paper story.

## 01_METHOD_INNOVATION_STORY.md

Purpose: explain how the method idea forms.

Required sections:

- `Core Problem Tension`: why the current field needs a different mechanism.
- `Where The Method Comes From`: current-field anchor, near-neighbor mechanism, far-neighbor abstraction, and why the transfer is legitimate.
- `Method Idea In One Sentence`: the compact method claim.
- `Mechanism Construction`: the causal path from problem pressure to method components.
- `Contribution Roles And Dependencies`: distinguish the core scientific contribution from optional supporting contributions, validation, analysis, and engineering support. A supporting contribution counts only when its `counterfactual_necessity` states what central claim fails without it.
- `What Is Actually New`: novelty boundaries, not module names.
- `Evidence Chain`: PaperNexus, literature, and experiment evidence refs.
- `Experiment Implications`: what the method story requires experiments to prove.
- `Current User-Facing Summary`: concise status for the user.

## 02_CLAIM_EVIDENCE_MAP.md

Purpose: connect the paper story to evidence.

Required sections:

- `Main Claims`: claims the paper can currently make.
- `Evidence Support`: artifact, paper, run, and analysis evidence backing each claim.
- `Claim Limits`: unsupported, downgraded, or speculative claims.
- `Promoted Idea Claims`: claims supported by promoted best runs, score verification, spec audit, and required ablation/confirmation.
- `Candidate-Only Claims`: pilot or candidate-supported findings that require more evidence before strong wording.
- `Failed Or Negative Ideas`: failed, regressed, parked, killed, or diagnostic-only ideas from `IDEA_DECISION_LEDGER.json`, `EXPERIMENT_LEDGER.json`, and `IDEA_OUTCOME_SUMMARY.json`; these can support pruning, limitations, future work, or downgrade, but not stable performance improvement.
- `Downgraded Or Deleted Claims`: claims removed or softened because the idea lifecycle, run ledger, score verification, spec audit, or reviewer gate did not support them.
- `Core Contribution Evidence`: map the core contribution and any necessary supporting contributions to closest priors, falsifiers, required ablations, expected metrics, failure modes, and current evidence status. Keep validation and engineering rows labeled as evidence roles rather than innovations.
- `Experiment Mapping`: which result or ablation supports which storyline step.
- `Revision Notes`: how later results or review pressure changed the story.

## 03_CODE_TRANSFER_STORY.md

Purpose: explain paper/code survey, source-code reading, innovation extraction, and target-task migration in user-facing prose when that workflow is in scope.

Required sections:

- `Survey Scope`: target task, source lanes, year/venue/search scope, and exclusions.
- `Candidate Funnel`: raw paper-code candidates, no-code/source-limited cases, valid repositories, mismatches, thin repos, benchmark-only repos, and project pages.
- `Source Mechanisms`: source paper, repository evidence ref, active code path, mechanism summary, and what static source evidence can and cannot prove.
- `Transfer Decisions`: direct-transfer, needs-adaptation, diagnostic-only, parked, killed, and source-limited decisions from `INNOVATION_MIGRATION_MATRIX.json`.
- `Target Adaptation`: required code/protocol changes, baseline/metric/dataset deltas, and implementation route.
- `Evidence Boundaries`: novelty risk, overlap risk, claim limits, and why repository validity is not effectiveness evidence.
- `Validation Route`: falsifier, ablation or confirmation plan, and the promotion gate needed before writing strong claims.

## Stage Expectations

- `ideation`: create or update `00_STORYLINE_DESIGN.md` from the selected story direction and lane evidence.
- `idea_gate`: revise `00_STORYLINE_DESIGN.md` after idea selection, explicitly recording reviewer risks and belief shift.
- `experiment_plan`: produce all three core files, aligned to the selected idea and `INNOVATION_PACKET.json`. The story must defend one explicit core scientific contribution; optional supporting contributions need a counterfactual necessity test. If paper-code migration is in scope, also create or update `03_CODE_TRANSFER_STORY.md` from `PAPER_CODE_CANDIDATES.json`, `REPO_STATIC_EVIDENCE.json`, `CODE_MECHANISM_MAP.json`, and `INNOVATION_MIGRATION_MATRIX.json`.
- `analysis`: update all three files after results, especially proof ladder, claim limits, idea outcome summary, failed/negative ideas, and experiment mapping.
- `review_pressure`, `writing`, and `submission_ready`: keep the story synchronized with reviewer repairs, manuscript claims, citation evidence, paper-forensics findings, and claim downgrades. The story must never be stronger than `IDEA_OUTCOME_SUMMARY.json`, `PAPER_CLAIM_VERIFICATION.json`, and `PAPER_FORENSICS_REPORT.json`.

Use `scripts/innovation_story_lint.py --project <project-root> --stage <stage>` before marking a story-bearing stage complete. The linter rejects placeholder text, missing sections, too-short files, and bullet-dominant files.
