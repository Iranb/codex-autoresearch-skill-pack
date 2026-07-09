# CCF-A Manuscript Revision Workflow

Use this reference when applying CCF-A/top-tier writing standards to a concrete
manuscript. This is the manuscript-application layer: it consumes the user's
draft, project evidence, and optional corpus findings, then produces
`.autoreskill/paper/CCFA_WRITING_AUDIT.md` before rewriting prose.

Read `ccfa_writing_principles.md` before using this workflow. If the revision
cites corpus-derived writing claims, also read
`ccfa_writing_style_corpus_audit.md` and use only evidence-bounded findings from
`.autoreskill/writing_style/EVIDENCE_SYNTHESIS.json` or an equivalent audited
source.

## Table Of Contents

- Non-Negotiable Order
- Required Inputs
- Required Output
- Audit Procedure
- Audit Template
- Completion Gate

## Non-Negotiable Order

Revise in this order:

1. Audit the argument.
2. Repair title, abstract, introduction, and Figure 1 story.
3. Align method and experiments to the repaired story.
4. Calibrate claims against evidence.
5. Run the non-defensive writing pass.
6. Polish paragraph flow and sentence-level English.

Do not begin with grammar, vocabulary, or generic academic tone. A fluent weak
argument is still weak.

## Required Inputs

Collect or infer:

- manuscript source path: `.tex`, `.md`, `.docx`, extracted text, or PDF;
- target venue or style target;
- core method, claimed contributions, and intended novelty;
- evidence package: experiments, ablations, theory, analysis, qualitative
  examples, limitations, and unavailable or missing evidence;
- existing Figure 1 or caption when available;
- corpus-style evidence only when it has an evidence tier and claim limit.

If key evidence is missing, record the gap in the audit and downgrade claims
instead of inventing support.

## Required Output

Create or update:

```text
.autoreskill/paper/CCFA_WRITING_AUDIT.md
```

When editing source files, keep the audit as the authority for why each
story-level change was made.

## Audit Procedure

1. Extract the current thesis.

   Write the current draft's actual thesis in the form used by
   `ccfa_writing_principles.md`. Mark `unclear` if the failure mode, mechanism,
   or enabled capability is missing.

2. Build a gap-diagnosis-method-evidence map.

   For each major claim, record gap, diagnosis, method, evidence, claim strength,
   and required revision. Allowed actions are rewrite, downgrade, move to future
   work, add evidence, or leave unchanged with evidence ref.

3. Audit front matter before method details.

   Check title, abstract, introduction, contribution list, and Figure 1 against
   the principle-layer requirements. Record missing diagnosis, vague contribution
   verbs, unsupported numbers, unclear reader belief shift, and figure-story
   failures.

4. Audit method and experiments.

   Each method component should name the bottleneck it solves, the mechanism it
   changes, and the validation route. Experiments should be organized by claims
   or research questions, not by table order alone.

5. Calibrate claims.

   Choose verbs from the evidence strength rules in `ccfa_writing_principles.md`.
   Downgrade or remove unsupported intensifiers and unsupported causal,
   robustness, generalization, or SOTA claims.

6. Run the non-defensive writing pass.

   Remove unnecessary self-undermining only after claim calibration. Preserve
   real limitations, missing evidence, correlative boundaries, validation-only
   boundaries, and target-domain scope. The pass is invalid if it upgrades weak
   evidence into a stronger claim.

7. Rewrite in dependency order.

   Edit title and abstract first; then introduction and contribution list;
   Figure 1 caption/story; method topic sentences and component motivation;
   experiment organization; related-work group openings; limitations and claim
   boundaries; high-impact non-defensive wording; paragraph transitions and
   sentence-level English last.

## Audit Template

Use this structure for `.autoreskill/paper/CCFA_WRITING_AUDIT.md`:

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

- `CCFA_WRITING_AUDIT.md` exists;
- the one-sentence thesis is explicit or marked unclear with repair route;
- front matter has gap, diagnosis, method, evidence, and boundary;
- each major contribution has evidence or is downgraded;
- strong claims are calibrated;
- the non-defensive writing pass removes unnecessary self-undermining while
  preserving true evidence boundaries;
- unsupported claim upgrades are blocked;
- final polish happened after story-level repair.

If the manuscript cannot satisfy these gates because evidence is missing, report
the blocker and provide a revision plan rather than masking the gap with fluent
prose.
