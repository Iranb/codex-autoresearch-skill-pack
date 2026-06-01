# User-Facing Innovation Story Contract

Every AutoResearch project maintains a project-bound user-facing innovation story under:

```text
.autoreskill/user_view/innovation_story/
  00_STORYLINE_DESIGN.md
  01_METHOD_INNOVATION_STORY.md
  02_CLAIM_EVIDENCE_MAP.md
```

This directory is for the user. It is a derived explanation layer, not the source of truth for stage advancement. Machine-readable authorities remain `EXPERIMENT_IDEA_POOL.json`, `IDEA_NOVELTY_VENUE_SCORECARD.json`, `INNOVATION_PACKET.json`, `EXPERIMENT_REVIEW_PACKET.json`, `CLAIM_EVIDENCE_MATRIX.md`, and the review/package gates.

## 00_STORYLINE_DESIGN.md

Purpose: design the paper narrative, not the method module list.

Required sections:

- `Paper Thesis`: the one-sentence paper claim.
- `Reader Belief Shift`: what the reader believes before and after the paper.
- `Opening Tension`: the real-world need, current assumption, where it breaks, and the consequence.
- `Hidden Cause`: the deeper reason behind the observed failure.
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
- `Experiment Mapping`: which result or ablation supports which storyline step.
- `Revision Notes`: how later results or review pressure changed the story.

## Stage Expectations

- `ideation`: create or update `00_STORYLINE_DESIGN.md` from the selected story direction and lane evidence.
- `idea_gate`: revise `00_STORYLINE_DESIGN.md` after idea selection, explicitly recording reviewer risks and belief shift.
- `experiment_plan`: produce all three files, aligned to the selected idea and `INNOVATION_PACKET.json`.
- `analysis`: update all three files after results, especially proof ladder, claim limits, and evidence mapping.
- `review_pressure`, `writing`, and `submission_ready`: keep the story synchronized with reviewer repairs, manuscript claims, and citation evidence.

Use `scripts/innovation_story_lint.py --project <project-root> --stage <stage>` before marking a story-bearing stage complete. The linter rejects placeholder text, missing sections, too-short files, and bullet-dominant files.
