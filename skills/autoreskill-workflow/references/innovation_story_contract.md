# User-Facing Innovation Story Contract

Every AutoResearch project maintains a project-bound user-facing innovation story under:

```text
.autoreskill/user_view/innovation_story/
  00_STORYLINE_DESIGN.md
  01_METHOD_INNOVATION_STORY.md
  02_CLAIM_EVIDENCE_MAP.md
```

This directory is for the user. It is a derived explanation layer, not the source of truth for stage advancement. Machine-readable authorities remain `EXPERIMENT_IDEA_POOL.json`, `IDEA_NOVELTY_VENUE_SCORECARD.json`, `IDEA_DECISION_LEDGER.json`, `INNOVATION_PACKET.json`, `TRACK_PLAN_MATRIX.json`, `EXPERIMENT_REVIEW_PACKET.json`, `EXPERIMENT_LEDGER.json`, `IDEA_OUTCOME_SUMMARY.json`, `CLAIM_EVIDENCE_MATRIX.md`, and the review/package gates.

## 00_STORYLINE_DESIGN.md

Purpose: design the paper narrative, not the method module list.

Required sections:

- `Paper Thesis`: the one-sentence paper claim.
- `Reader Belief Shift`: what the reader believes before and after the paper.
- `Opening Tension`: the real-world need, current assumption, where it breaks, and the consequence.
- `Hidden Cause`: the deeper reason behind the observed failure.
- `Three Innovation Bundle`: at least three paper-level innovation points, each with its role, evidence source, closest-prior delta, and dependency on the other points. The bundle must cover problem/protocol/evaluation, method/mechanism, and training/integration/analysis/validation rather than listing three module names.
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
- `Innovation Bundle And Dependencies`: why the three or more innovation points are mutually necessary, which point is the main method mechanism, which point makes the problem/protocol new, and which point makes the evidence persuasive.
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
- `Three-Innovation Evidence Matrix`: map each innovation point to closest priors, required ablations, expected metrics, failure modes, and current evidence status.
- `Experiment Mapping`: which result or ablation supports which storyline step.
- `Revision Notes`: how later results or review pressure changed the story.

## Stage Expectations

- `ideation`: create or update `00_STORYLINE_DESIGN.md` from the selected story direction and lane evidence.
- `idea_gate`: revise `00_STORYLINE_DESIGN.md` after idea selection, explicitly recording reviewer risks and belief shift.
- `experiment_plan`: produce all three files, aligned to the selected idea and `INNOVATION_PACKET.json`; the selected paper story must retain the three-or-more innovation bundle from ideation and explain why the paper would collapse if any one point were removed.
- `analysis`: update all three files after results, especially proof ladder, claim limits, idea outcome summary, failed/negative ideas, and experiment mapping.
- `review_pressure`, `writing`, and `submission_ready`: keep the story synchronized with reviewer repairs, manuscript claims, citation evidence, and claim downgrades. The story must never be stronger than `IDEA_OUTCOME_SUMMARY.json` and `PAPER_CLAIM_VERIFICATION.json`.

Use `scripts/innovation_story_lint.py --project <project-root> --stage <stage>` before marking a story-bearing stage complete. The linter rejects placeholder text, missing sections, too-short files, and bullet-dominant files.
