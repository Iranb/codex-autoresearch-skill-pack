# CCF-A Manuscript Revision Workflow

Use this reference when applying CCF-A/top-tier writing standards to a concrete manuscript. This is the manuscript-application layer: it consumes the user's draft, project evidence, and, when available, writing-style corpus findings. It must produce `.autoreskill/paper/CCFA_WRITING_AUDIT.md` before rewriting or polishing prose.

Read `ccfa_writing_principles.md` before using this workflow. If the revision cites corpus-derived writing claims, also read `ccfa_writing_style_corpus_audit.md` and use only evidence-bounded findings from `.autoreskill/writing_style/EVIDENCE_SYNTHESIS.json` or an equivalent audited source.

## Non-Negotiable Order

Revise in this order:

1. Audit the argument.
2. Repair title, abstract, introduction, and Figure 1 story.
3. Align method and experiments to the repaired story.
4. Calibrate claims against evidence.
5. Run the non-defensive writing pass.
6. Polish paragraph flow and sentence-level English.

Do not begin with grammar, vocabulary, or "academic tone". A fluent weak argument is still weak.

## Required Inputs

Collect or infer:

- Manuscript source path: `.tex`, `.md`, `.docx`, or extracted text/PDF.
- Target venue or style target.
- Core method, claimed contributions, and intended novelty.
- Evidence package: experiments, ablations, theory, analysis, qualitative examples, limitations, and unavailable/missing evidence.
- Existing Figure 1 or figure caption when available.
- Corpus-style evidence only when it has an evidence tier and claim limit.

If key evidence is missing, record the gap in the audit and downgrade claims instead of inventing support.

## Required Output

Create or update:

```text
.autoreskill/paper/CCFA_WRITING_AUDIT.md
```

When editing source files, keep the audit as the authority for why each story-level change was made.

## Audit Procedure

### 1. Extract The Current Thesis

Write the current draft's actual thesis, not the desired thesis:

```text
Existing methods fail because of X. We address this by Y, which enables Z.
```

Mark `unclear` if any part is missing.

### 2. Build The Gap-Diagnosis-Method-Evidence Map

For each major claim, record:

- `gap`: what fails or is missing.
- `diagnosis`: why it fails.
- `method`: what mechanism addresses the diagnosis.
- `evidence`: which experiment, ablation, theorem, analysis, figure, or artifact supports it.
- `claim strength`: strong, moderate, weak, speculative, or unsupported.
- `required revision`: rewrite, downgrade, move to future work, or add evidence.

### 3. Audit Front Matter First

Check title, abstract, introduction, contribution list, and Figure 1 before method details.

Title:

- Shows object, action, and contribution.
- Avoids empty shells such as `A Novel Framework for ...`.
- Contains a memorable mechanism when appropriate.

Abstract:

- Sentence 1 states field pressure, not generic importance.
- Specific limitation/failure appears before the method.
- Diagnosis appears between limitation and proposal.
- Method sentence explains what changes.
- Evidence scope and key numbers appear when available.
- Final sentence states implication with boundaries.

Introduction:

- Paragraph 1 explains why the field pressure matters now.
- Paragraph 2 shows the concrete failure of current methods.
- Paragraph 3 identifies the hidden cause or core observation.
- The core insight appears on page 1.
- The contribution list is evidence-routable.

Figure 1:

- Shows failure mode, diagnosis, and method-as-resolution when possible.
- Does more than list modules.
- Helps a reviewer retell the paper in 30 seconds.

### 4. Audit Method And Experiments

Method:

- Each component begins with the bottleneck it solves.
- The component changes information flow, representation, objective, supervision, or inference in a way tied to the diagnosis.
- Each component has a planned or existing validation route.

Experiments:

- Main results answer the main claim.
- Ablations map to contributions.
- Generalization tests map to scope claims.
- Analysis supports the proposed mechanism.
- Failure cases or limitations calibrate boundaries.

Prefer RQ-based organization:

```text
RQ1: Does the method improve the main task?
RQ2: Which component causes the gain?
RQ3: Does it generalize across datasets/backbones/settings?
RQ4: Does analysis support the proposed mechanism?
RQ5: When does it fail?
```

### 5. Calibrate Claims

Use claim wording according to evidence:

- Strong experimental support: `we show`, `we demonstrate`.
- Empirical observation: `we find`, `we observe`.
- Plausible interpretation: `our results suggest`.
- Method/artifact contribution: `we introduce`, `we propose`.
- Formal proof only: `we prove`.
- Weak support: `is consistent with`, `may indicate`, or downgrade.

Remove or weaken `novel`, `effective`, `robust`, `significant`, and `substantial` unless backed by numbers, tests, or mechanisms.

### 6. Non-Defensive Writing Pass

After claim calibration, remove self-undermining prose that is not required by
the evidence boundary.

Top-tier framing:

- A reviewer should see the paper's strongest supported contribution in the
  title, abstract, introduction, and contribution list before seeing apologies or
  caveats.
- The manuscript should make a direct scoped claim, then show the evidence and
  boundary. It should not lead with "we do not claim" unless that sentence
  prevents a likely reviewer misread.
- Real limitations are not defensive writing. They are part of the evidence
  boundary and must remain visible in the right location.
- The pass is invalid if it upgrades weak, pilot, correlative, or
  validation-only evidence into strong causal, robust, or general claims.

Check for:

- unnecessary disclaimers before supported claims;
- repeated "we do not claim" or "not intended to" statements;
- limitation-first paragraphs that bury the contribution;
- vague hedging where the correct fix is precise evidence wording;
- negative framing of a valid scope choice;
- hypothetical objections introduced without reviewer or evidence pressure;
- contribution statements that apologize for being incremental when the evidence
  supports a clearer claim.

Repair pattern:

1. State the supported claim directly.
2. Attach the exact evidence or scope boundary.
3. Move true limitations to a limitation or discussion position.
4. Delete caveats that repeat already-stated scope.
5. Block unsupported claim upgrades introduced during polish.
6. Preserve necessary uncertainty when evidence is weak, incomplete, or
   correlative.

This pass must not create overclaiming. It turns defensive wording into precise
claim scope; it does not remove real limitations.

### 7. Rewrite Sequence

When editing files, use this order:

1. Rewrite title and abstract.
2. Rewrite introduction paragraphs 1-3 and contribution list.
3. Rewrite or propose Figure 1 caption/story.
4. Rewrite method section topic sentences and component motivation.
5. Reorder experiments into claim-answering RQs where appropriate.
6. Rewrite related work group openings and gap-positioning sentences.
7. Add limitations or claim-boundary text.
8. Run the non-defensive writing pass on high-impact positions: title, abstract,
   introduction opening/closing, contribution list, method motivation,
   limitations, and conclusion.
9. Polish paragraph transitions and sentence-level English.

## `CCFA_WRITING_AUDIT.md` Template

```markdown
# CCF-A Writing Audit

## One-Sentence Thesis
Existing methods fail because of X. We address this by Y, which enables Z.

## Evidence Boundary
- Target venue/style:
- Manuscript source:
- Evidence package read:
- Corpus-style evidence used:
- Unsupported or missing evidence:

## Gap -> Diagnosis -> Method -> Evidence
| Element | Current Draft | Required Revision | Evidence Ref | Claim Strength |
|---|---|---|---|---|

## Section Audit
| Section | Status | Main Issue | Required Fix |
|---|---|---|---|
| Title |  |  |  |
| Abstract |  |  |  |
| Introduction |  |  |  |
| Contributions |  |  |  |
| Figure 1 |  |  |  |
| Method |  |  |  |
| Experiments |  |  |  |
| Related Work |  |  |  |
| Limitations |  |  |  |

## Claim Calibration
| Claim | Evidence | Allowed Wording | Overclaim Risk | Action |
|---|---|---|---|---|

## Non-Defensive Writing Pass
| Location | Defensive Pattern | Necessary Boundary? | Revision |
|---|---|---|---|

## Top-Tier Claim Posture
| Location | Supported Direct Claim | Evidence/Scope Boundary | Necessary Limitations Preserved | Claim Upgrades Blocked | Top-Tier Reviewer Risk |
|---|---|---|---|---|---|
| Title |  |  |  |  |  |
| Abstract |  |  |  |  |  |
| Introduction |  |  |  |  |  |
| Contributions |  |  |  |  |  |

## Figure 1 Story Check
- Failure mode:
- Diagnosis:
- Method-as-resolution:
- Evidence signal:
- Required caption/story revision:

## Experiment Story Check
| RQ | Claim | Evidence/Table/Figure | Missing Repair |
|---|---|---|---|

## Revision Plan
1. Story-level edits:
2. Claim downgrades:
3. Section rewrites:
4. Sentence-level polish after story lock:

## Revision Log
- Files edited:
- Story-level changes:
- Claim/evidence changes:
- Sentence-level changes:
```

## Completion Gate

Do not report CCF-A writing polish as complete unless:

- `CCFA_WRITING_AUDIT.md` exists.
- The one-sentence thesis is explicit.
- Abstract and introduction include gap, diagnosis, method, evidence, and boundary.
- Each major contribution has evidence.
- Strong claims are calibrated.
- The non-defensive writing pass removes unnecessary self-undermining while
  preserving true evidence boundaries.
- Necessary limitations are preserved, unsupported claim upgrades are blocked,
  and front-matter claim posture is checked from a top-tier reviewer viewpoint.
- The final polish happened after story-level repair.

If the manuscript cannot satisfy these gates because evidence is missing, report the blocker and provide a revision plan rather than masking the gap with fluent prose.
