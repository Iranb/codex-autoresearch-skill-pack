# CCF-A Writing Principles

Use this reference when the user wants to learn, check, or apply CCF-A/top-tier English academic writing style. This is the writing-principle layer: it turns corpus observations and expert top-tier review practice into reusable writing standards. It does not collect evidence and does not directly rewrite a manuscript; use `ccfa_writing_style_corpus_audit.md` for evidence collection and `ccfa_manuscript_revision_workflow.md` for manuscript application.

## Table Of Contents

- Core Rule
- 1. One-Sentence Thesis
- 2. Abstract With Diagnosis
- 3. Introduction As Reviewer Persuasion
- 4. Contributions As Insights
- 5. Method As Resolution
- 6. Experiments As Claim Chain
- 7. Figure 1 As Story
- 8. Related Work As Gap Positioning
- 9. Claim Calibration And English
- 10. Non-Defensive Writing Posture
- 11. Final Self-Check

## Core Rule

Do not learn sentence patterns first. Learn how strong papers build an argument. Good English follows from a clear evidence-bound story in which every paragraph advances the same claim.

Use this revision order:

1. Story spine and claim scope.
2. Title, abstract, introduction, and Figure 1.
3. Method as the resolution to a diagnosis.
4. Experiments as a claim-evidence chain.
5. Related work as gap positioning.
6. Paragraph flow and sentence-level English.

## 1. One-Sentence Thesis

A CCF-A/top-tier manuscript must compress into:

```text
Existing methods fail because of X. We address this by Y, which enables Z.
```

Check:

- `X` is a concrete failure mode, not "limitations".
- `Y` is the core mechanism or design change, not only the method name.
- `Z` is a verifiable capability, result, or boundary.
- The experiments actually support the causal path `Y -> Z`.

If this sentence is unclear, route back to storyline repair before polishing English.

## 2. Abstract With Diagnosis

Weak abstracts jump from limitation to proposal:

```text
Existing methods have limitations. We propose a novel framework...
```

Stronger abstracts insert a diagnosis:

```text
Existing methods fail under X. We identify that this failure stems from Y. Based on this observation, we introduce Z...
```

Use this six-function abstract structure:

1. Field progress with tension.
2. Specific failure setting.
3. Failure cause, diagnosis, or core observation.
4. Method as a response to that cause.
5. Evidence scope and key results.
6. Significance and claim boundary.

The crucial sentence is the diagnosis: why existing methods fail.

## 3. Introduction As Reviewer Persuasion

The first three introduction paragraphs should have different jobs:

1. Establish why the direction matters and why now.
2. Show exactly where current methods fail.
3. Explain the mechanism or observation that makes the failure solvable.

Do not write a literature-review opening. The introduction should make the reviewer accept that the paper addresses a real gap in the current paradigm, not a small engineering tweak.

Required checks:

- The core insight appears on page 1.
- The gap is a mechanism, protocol, data, evaluation, or reasoning gap.
- The paper explains why prior methods fail.
- The reader belief shift is clear: what the reviewer believed before, and what the paper makes them believe after.

## 4. Contributions As Insights

Avoid component-list contributions:

```text
1. We propose a novel framework.
2. We design a new module.
3. Extensive experiments show effectiveness.
```

Prefer insight/evidence-routed contributions:

```text
1. We identify X as the key bottleneck in existing methods.
2. We introduce Y, which addresses X by Z.
3. We validate Y across A/B/C settings and show that the gain comes from Z.
4. We analyze failure cases and clarify the boundary of the method.
```

Every contribution must map to a figure, theorem, experiment, ablation, analysis, dataset, or released artifact.

## 5. Method As Resolution

Each method component must answer a bottleneck before its implementation details appear.

Weak:

```text
We use an attention module to aggregate features.
```

Stronger:

```text
Direct feature aggregation mixes unreliable signals from unseen classes. To reduce this noise, we introduce a confidence-gated attention module that suppresses uncertain regions before fusion.
```

For each component, check:

- Which bottleneck does it solve?
- What changes in information flow, optimization, representation, supervision, or inference?
- Why should that change address the diagnosis?
- Which ablation or analysis validates it?
- What assumption or limitation does it introduce?

Preferred method paragraph order:

1. Bottleneck.
2. Design goal.
3. Mechanism.
4. Formalization.
5. Intuition.
6. Link to evidence.

## 6. Experiments As Claim Chain

Organize experiments by claims, not by table order.

Recommended RQ structure:

- `RQ1`: Does the method improve the main task?
- `RQ2`: Which component causes the gain?
- `RQ3`: Does it generalize across datasets, backbones, domains, or settings?
- `RQ4`: Does analysis support the proposed mechanism?
- `RQ5`: When does it fail?

Every table or figure should answer a claim. If a result does not support a contribution, boundary, or reviewer risk, move it to appendix or remove it.

## 7. Figure 1 As Story

Figure 1 should help the reviewer retell the paper in 30 seconds. It should show at least three of:

- Existing method failure mode.
- Central diagnosis or hidden cause.
- Method-as-resolution.
- Changed information flow, objective, or representation.
- Evidence ladder or expected behavior.
- Visual or quantitative contrast supporting the story.

If Figure 1 only shows module blocks, it is probably too implementation-centered.

## 8. Related Work As Gap Positioning

Organize related work by argument role, not chronology.

Each group should answer:

- What has this line of work solved?
- What pressure remains unresolved?
- How does the current paper differ in problem framing, mechanism, or evidence?

Use precise boundaries:

```text
These methods improve X under Y, but they do not explicitly model Z, which is central to our target setting.
```

Do not use related work as a list of citations. Use it to clarify the gap.

## 9. Claim Calibration And English

Choose verbs by evidence strength:

- `we introduce/propose`: method or artifact contribution.
- `we identify/find/observe`: empirical observation.
- `we show/demonstrate`: supported by experiments or analysis.
- `we prove`: formal proof only.
- `our results suggest/indicate`: plausible interpretation without causal isolation.
- `is consistent with`: evidence aligns with a hypothesis but does not prove it.

Prefer analytical verbs:

```text
identify, reveal, formalize, quantify, decompose, align, constrain, calibrate, disentangle, isolate, suppress, regularize, diagnose, validate
```

Avoid unsupported intensifiers unless immediately backed by numbers, tests, or mechanisms:

```text
novel, effective, robust, significant, substantial, remarkable, highly
```

Use old-to-new flow: start from known context, add one new idea, then use that idea as the next sentence's context.

## 10. Non-Defensive Writing Posture

Strong academic writing states the supported contribution directly and then
places the boundary where it belongs. It does not apologize before the reader has
seen the claim.

From a top-tier reviewer viewpoint, non-defensive writing is not a softer tone.
It is a stricter claim contract:

- The front matter states the strongest claim that the evidence can withstand.
- The boundary is attached to the evidence, not used as an opening apology.
- Necessary limitations remain explicit because they prevent reviewer
  misinterpretation.
- Polishing never upgrades weak, pilot, correlative, validation-only, or
  aggregate-only evidence into a stronger claim.

Keep necessary precision:

- real limitations;
- missing experiments;
- correlative rather than causal evidence;
- target-domain or dataset boundaries;
- assumptions needed for a theorem, protocol, or measurement.

Remove unnecessary defense:

- repeated "we do not claim" language;
- caveats in the first sentence of an abstract, introduction paragraph, or
  contribution bullet when the claim is already scoped;
- limitation-first paragraphs that hide the main contribution;
- vague hedging such as "may possibly" when the evidence supports a precise
  empirical statement;
- negative framing of a deliberate design scope;
- hypothetical objections without evidence or reviewer pressure.

Revision pattern:

```text
Claim -> evidence/scope -> implication.
```

Do not use:

```text
Apology -> caveat -> maybe-claim -> repeated boundary.
```

This posture is not overclaiming. If evidence is weak, downgrade the claim. If
evidence is strong within a scope, state that scoped claim plainly. A sentence is
ready for a top-tier submission only if a reviewer can point to the exact
evidence and scope boundary that authorize its verb.

## 11. Final Self-Check

Before sentence polishing, confirm:

- The one-sentence thesis is clear.
- The abstract contains gap, diagnosis, method, evidence, and boundary.
- The introduction explains why existing methods fail.
- Each contribution has evidence.
- Each method component maps to a bottleneck.
- Experiments are organized by claims/RQs.
- Figure 1 tells the core story.
- Related work positions the gap.
- Claims are not overstated.
- Necessary limitations are preserved, but unsupported disclaimers and repeated
  self-undermining caveats are removed.
- Sentences present logic before technical detail.

The practical editing order is: rewrite title, abstract, introduction, and Figure 1 first; then revise method and experiments to support that story; polish sentence-level English last.
