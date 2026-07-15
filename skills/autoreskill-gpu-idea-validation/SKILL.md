---
name: autoreskill-gpu-idea-validation
description: Construct, audit, and hand off evidence-backed research ideas from non-PaperNexus material using the ResearchStudio-Idea Phase 0-4 process, then prepare bounded pilot-only validation on available local, SSH, or BJTU HPC GPUs. Use when an AutoResearch project needs additional external-source innovation candidates, mechanism-level novelty checks, falsifiable rapid experiments, or safe spare-GPU scheduling. Do not use for PaperNexus-sourced ideation, unconstrained brainstorming, or as launch authorization.
---

# AutoResearch GPU Idea Validation

Build a non-PaperNexus idea campaign before looking for spare compute. Apply the
ResearchStudio-Idea scientific process in paper Phases 0-4, then use a local
Phase 5 to hand only reviewed, plan-ready pilots to AutoResearch's existing
planning, queue, and runtime authorities.

This skill is an evidence adapter, not a second workflow controller. GPU
availability can schedule an already justified experiment; it cannot create an
idea, promote a claim, enlarge a budget, or authorize a remote side effect.

## Use and routing

Use this skill when all of the following are true:

- the project is an AutoResearch project with a writable `.autoreskill` tree;
- idea evidence comes from user files/PDFs, ordinary academic or Web search, or
  another explicitly non-PaperNexus source;
- the desired result is a falsifiable research mechanism and a small GPU
  discriminator, not free-form brainstorming;
- the downstream scientific and execution lifecycle will remain under
  `$autoreskill-workflow`.

Do not use it to relabel PaperNexus artifacts as external material. If the idea
source is PaperNexus, route to `$autoreskill-papernexus-innovation`. If the user
only wants literature synthesis, use the appropriate literature-review skill.
If the request is only to run an existing experiment, start from
`$autoreskill-run-experiment` and its canonical queue row.

## Non-negotiable boundary

The campaign must declare:

```text
source_mode = external_material
papernexus_used = false
```

Explicit PaperNexus provider/session/MCP provenance, including fabricated
"attempted" metadata, fails this route. A source declaration is auditable
provenance, not proof that every earlier human action avoided PaperNexus.

The campaign and its derived checks are evidence-only:

```text
.autoreskill/ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json
.autoreskill/ideation/committed/NON_PAPERNEXUS_IDEA_LINT_CHECK.<sha256>.json
.autoreskill/ideation/committed/NON_PAPERNEXUS_IDEA_LINT.<sha256>.json
.autoreskill/ideation/committed/INNOVATION_SLOT_MAP.<sha256>.json
```

They do not own selection, belief, planning, scheduling, runs, results, or
claims. Canonical authorities remain:

- `.autoreskill/ideation/IDEA_DECISION_LEDGER.json` for selection/belief;
- `.autoreskill/orchestrator/TRACK_PLAN_MATRIX.json` for scientific tracks;
- `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json` for scheduling;
- each experiment's `REMOTE_RUN.json` for runtime truth;
- `SCIENTIFIC_OUTCOME.json` plus the research-decision workflow for
  interpretation.

Only `idea_campaign.py materialize` may adapt a passing campaign into the
content-addressed lint/slot-map pair and gate-last
`PRE_IDEA_EVIDENCE_GATE.json` commit. Downstream consumers resolve the exact
`lint_ref` and `slot_map_ref` carried by that gate; they must not guess legacy
fixed paths. Materialization must not write the idea pool, scorecard, decision
ledger, track matrix, queue, run record, or scientific outcome.

## Start or resume

Set absolute paths; commands are CWD-independent:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/autoreskill-gpu-idea-validation"
PROJECT_ROOT=/absolute/path/to/project

python3 "$SKILL_DIR/scripts/idea_campaign.py" init \
  --project "$PROJECT_ROOT" --direction "<research direction>"
```

`init` is idempotent and never overwrites an existing campaign. Complete the
scaffold from external evidence, then run:

For a fresh agent, prefer the synthetic authoring-only eight-candidate field
template in
[`NON_PAPERNEXUS_IDEA_CAMPAIGN.template.json`](references/NON_PAPERNEXUS_IDEA_CAMPAIGN.template.json),
or print the same shape with `idea_campaign.py template --kind campaign`.
Replace every placeholder and remove `_template_metadata` before validation;
the template is deliberately not materializable.

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" check --project "$PROJECT_ROOT"
python3 "$SKILL_DIR/scripts/idea_campaign.py" check \
  --project "$PROJECT_ROOT" --write-result
```

Treat `check` output as deterministic contract evidence, not a semantic
reviewer. Never weaken a scientific field merely to make the linter pass.

To resume, inspect the campaign, the current gate and its hash-verified
content-addressed lint/slot refs, the canonical idea pool/ledger/matrix/queue,
and unfinished per-run records before choosing the next phase. Do not rerun
completed generation from chat memory.

## Paper Phase 0-4 plus local Phase 5

Read [idea-construction-contract.md](references/idea-construction-contract.md)
before authoring or auditing a campaign. It is the normative scientific
contract.

### Phase 0 — establish evidence readiness

Record the external search trace and target-domain, near-neighbor, and
far-neighbor evidence lanes. Load-bearing evidence needs a stable source ref,
locator/span, short excerpt, excerpt SHA-256, full-text status, and verification
limit. The core gap cannot rest on an abstract. Require
`evidence_readiness = ready`, at least two citable method/full-text supports for the bottleneck, and a
full-text closest anchor before candidate generation.

Load no pattern deck in Phase 0.

### Phase 1 — reconstruct lineage and structural bottleneck

Create explicit method nodes and evidence-backed edges. `external_citable`
nodes can support claims. `parametric_awareness_only` nodes are non-citable
regression warnings and cannot support a gap, differentiation, novelty, or
collision result. Shallow lineages are valid; never invent ancestors to fill a
timeline.

Locate either an additive residual at a citable frontier leaf, a subtractive
shared assumption supported across citable methods, or another explicitly
justified structural gap. List order never implies ancestry.

Load no pattern deck in Phase 1.

### Phase 2 — select patterns, then construct candidates

The campaign contains 8-12 independent candidate transactions. Each transaction
is K=1: select a structural recipe first, then construct one mechanism. Produce
a 3-5 candidate shortlist and admit no more than four candidates for downstream
tracks.

For each candidate:

- use 1-3 counted `gap_closures`, default 2;
- map each closure to exactly one gap, one main pattern, and one selected `C##`
  subpattern;
- count repeated use of the same main pattern as separate closures;
- disable companion roles and do not use `companion-combos.md`;
- name ordered mechanism steps, exactly one load-bearing variable, an outcome
  metric and direction, a non-tautological negative control targeting the
  downstream outcome, an alternative explanation, and positive/negative/
  inconclusive/invalid routes.

Use the vendored deck progressively:

1. Main-pattern selection: read only
   `references/researchstudio-idea/ideation-patterns/overview.md`.
2. Subpattern selection: additionally read only
   `references/researchstudio-idea/ideation-sub-patterns/overview.md`.
3. Candidate generation: read only the selected 1-3 `C##.md` files' `Tactical
   pattern` and `Step-by-Step` sections.
4. Do not read `anti-patterns.md`, tactical failures, Reject lessons, frequency,
   or acceptance signals during generation.

Select by structural fit, never by pattern frequency or historical acceptance.
Never load all 31 subpattern cards into one context.

### Phase 3 — collide, audit, and route

Run mechanism-targeted collision search in two auditable channels:

- `signature_terms`: recent, candidate-native vocabulary over 10 months;
- `alias_terms`: cross-community mechanism aliases over 48 months.

Tag every hit with its channel. Name the worst concrete prior paper, its exact
result, and whether that result subsumes the proposed mechanism. Do not
age-discount an alias ancestor. Exact-mechanism overlap is a hard abandon.
`no_threat_found` must retain queries, limits, and claim boundaries and is never
a novelty certificate. Four Scoop-Check axes may annotate the audit but cannot
replace the concrete `paper_pointed_threat`.

Run audit in a fresh context after generation. Only now load selected cards'
`Tactical failure mode` and `Reject lessons` plus
`references/researchstudio-idea/anti-patterns.md`. Require exactly these checks:

1. `gap_closure_reject_check`
2. `recipe_application_check`
3. `anti_pattern_check`
4. `paper_pointed_threat`
5. `falsification_structure_check` (pinned-repository hardening)

Route `advance | revise | abandon`. A triggered Reject lesson, unmitigated
anti-pattern, or exact collision is a hard-floor `abandon`. Recipe bypass
requires revision or reconstruction. Audit never edits. Repair runs separately;
only a structurally deficient falsifier may be repaired once while preserving
the experiment, metric, claim, and compute commitment. Compute has no silent
repair route. Record a repaired proposal as an explicit candidate revision, not
a hidden retry.

### Phase 4 — expand and independently audit implementability

Expand the survivor into the AutoResearch campaign/slot-map shape. In a fresh
skeptical-engineer context, enrich every mechanism step one-to-one, preserving
IDs and order, with `what_changes`, build procedure, inputs, and outputs. Record
every hole as `filled` or `open`; an open load-bearing hole blocks admission.
The implementability reviewer cannot add/delete/rename steps or change protected
commitments. Passing this audit does not authorize a launch.

Hash canonical JSON containing the falsifier, negative control, metric/split,
resource ceiling, seed policy, and all outcome routes. A material change needs
an incremented campaign revision and `parent_campaign_sha256`.

### Local Phase 5 — canonical handoff and bounded GPU pilot

Phase 5 is an AutoResearch extension, not a contribution claimed by the paper.
Read [gpu-validation-protocol.md](references/gpu-validation-protocol.md) before
resource discovery, normalization, claim, preflight, or launch preparation.

First materialize the external evidence gate with compare-and-swap:

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" materialize \
  --project "$PROJECT_ROOT" \
  --expected-current-gate-sha256 "<sha256-or-absent>"
python3 "$SKILL_DIR/scripts/idea_campaign.py" verify-gate \
  --project "$PROJECT_ROOT"
```

Materialization commits the gate last and refuses to overwrite a PaperNexus or
unknown-mode gate. Then use `$autoreskill-ideation-panel` for debate/selection,
`$autoreskill-experiment-plan` for reviewed plans, and
`$autoreskill-implement-experiment` for implementation. `$autoreskill-workflow`
and WorkflowGuard remain stage owners. External planning also requires a
separate passed `.autoreskill/ideation/PANEL_DESIGN_REVIEW.json`; deterministic
lint does not replace semantic review.

Create that independent review from the strict template and commit it with CAS;
do not write the canonical panel file directly:

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" template --kind panel-design-review
python3 "$SKILL_DIR/scripts/idea_campaign.py" write-panel-design-review \
  --project "$PROJECT_ROOT" \
  --input /absolute/path/to/independent-panel-review.json \
  --expected-current-panel-sha256 "<current-sha256-or-absent>"
```

The workflow job-packet router recognizes only an explicit external campaign or
committed external gate. Before the gate is complete it dispatches this skill;
after the gate/hash chain is complete it returns to the canonical stage owner.
Unknown/conflicting source modes expose no PaperNexus calls, resource claims, or
child write scope. For an external pilot, the experiment packet uses only the
first deterministic assignment and `claim-assignment`, never plain `claim` or a
stale batch schedule.

At each boundary run:

```bash
python3 "$SKILL_DIR/scripts/external_alignment_lint.py" \
  --project "$PROJECT_ROOT" --stage ideation
python3 "$SKILL_DIR/scripts/external_alignment_lint.py" \
  --project "$PROJECT_ROOT" --stage idea_gate
python3 "$SKILL_DIR/scripts/external_alignment_lint.py" \
  --project "$PROJECT_ROOT" --stage experiment_plan
```

The linter reports `complete`, `missing`, and `warnings` and verifies the
campaign/candidate identity chain. Canonical handoffs carry
`campaign_ref`, `campaign_sha256`, `lint_ref`, `lint_sha256`, and
`slot_map_sha256`; selected records also preserve `external_candidate_id`.
`selected_idea_fragment_id`, `track_id`, and `external_candidate_id` are
distinct identities.

When a validated external campaign must replace a legacy PaperNexus/unknown
live evidence gate, do not call normal `materialize` and do not overwrite the
gate by hand. First CAS-write the independent passed panel against the current
campaign, then dry-run and apply the single-authority migration:

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" migrate-evidence-authority \
  --project "$PROJECT_ROOT" \
  --expected-current-gate-sha256 "<legacy-gate-sha256>" \
  --expected-selection-fingerprint "<current-selection-fingerprint>" \
  --input-campaign-sha256 "<current-campaign-sha256>"
python3 "$SKILL_DIR/scripts/idea_campaign.py" migrate-evidence-authority \
  --project "$PROJECT_ROOT" \
  --expected-current-gate-sha256 "<legacy-gate-sha256>" \
  --expected-selection-fingerprint "<current-selection-fingerprint>" \
  --input-campaign-sha256 "<current-campaign-sha256>" --apply
```

The transaction archives and hash-verifies the old gate and its referenced
artifacts, binds the panel ref/hash into the new gate, replaces the fixed live
path by CAS, and journals recovery. Use `recover-authority-migration
--operation-id <id>` after interruption. Use `rollback-authority-migration
--operation-id <id>` only before downstream selection consumes the new gate.

Only after a reviewed plan becomes a plan-ready canonical queue row may spare
capacity be considered. Use `$gpu-idle-scan` for read-only SSH discovery,
`$bjtu-hpc` for BJTU planning and exact-script preflight, and
`$autoreskill-run-experiment` for queue/runtime operations. Do not launch merely
because this skill, a scan, a schedule, or `claim-assignment` succeeded.
The queue row must preserve the selected candidate's
`protected_commitment_sha256`; launch-intent preparation also requires a fresh,
route-specific preflight bound to the exact one-GPU launch-spec hash and claimed
resource identity.

The fresh-agent Phase-5 command order is fixed: queue check; capture the chosen
route's read-only observation; `resource_adapter.py normalize-for-row` to a
proposal file; revision-checked `commit-resource-snapshot`; read-only
`schedule`; first-assignment-only `claim-assignment`; baseline clone and
protocol launch lints; `launch-spec-digest`; revision-checked
`record-backend-preflight`; final `budget-check`; and only then
`prepare-launch-intent` with the canonical run directory and exact
`--launch-spec`. The intent is queued local state, not a launch. See the
normative Phase-5 protocol for complete commands, authority checks, release,
remote-side-effect, and reconciliation rules.

## Pilot limits and interpretation

Unless the user and stricter project policy impose a lower ceiling:

- at most 4 admitted active ideas per campaign;
- `evidence_tier="pilot_only"`, one physical GPU, one scout seed per idea;
- ten-minute smoke included in the candidate budget;
- at most 1 GPU-hour/60 minutes for one baseline-aligned discriminator per idea;
- at most 4 GPU-hours total for the campaign;
- any eventual experiment family remains at no more than 3 seeds.

The effective ceiling is the minimum of the explicit user budget, remaining
project-policy budget, and these quick-pilot limits. Completed and failed actual
usage, running and planned reservations, smoke tests, and retries all count.
Unknown usage fails closed.

A positive scout means only `valid_positive_candidate`: the idea survives for
matched reproduction, confirmation, and ablation. A valid negative may lower
belief. A valid inconclusive result allows at most one additional
decision-changing discriminator by default. Infrastructure, implementation, or
protocol failure does not count against the hypothesis.

Label every comparison exactly as one of:

- `vs paper-reported baseline`
- `vs reproduced baseline`
- `vs matched reproduced baseline`
- `paper-report comparison not established`

Never use a pilot to set `candidate_supported`, `promoted`,
`close_required_claim`, or `claim_promotion`.

## Deck integrity and maintenance

The vendored deck is pinned to
`microsoft/ResearchStudio@868f0e9c30685b72ebd475f0dada1492a1982168`.
Before relying on it after installation or suspected drift, run:

```bash
python3 "$SKILL_DIR/scripts/idea_campaign.py" verify-deck
```

The manifest covers exactly 50 upstream files: root MIT `LICENSE`, two
overviews, 15 main cards, 31 subpattern cards, and `anti-patterns.md`.
`companion-combos.md` and the upstream control plane are intentionally absent.
The MIT license applies to the vendored repository files; the arXiv paper's
separate CC BY 4.0 status is not the license for this deck copy. Do not accept a
new upstream revision implicitly.

## Resource map

- [Eight-candidate campaign authoring template](references/NON_PAPERNEXUS_IDEA_CAMPAIGN.template.json):
  synthetic, authoring-only complete field shape for exactly eight candidate
  transactions; it defaults to `draft`/`not_ready` and cannot materialize while
  `_template_metadata` remains.
- [Panel design review template](references/PANEL_DESIGN_REVIEW.template.json):
  strict independent generation/reviewer context and campaign-binding shape.
- [External authoring and commit protocol](references/external-authoring-and-commit-protocol.md):
  seed/template commands, CAS panel writer, and content-addressed gate-last
  commit layout.
- [Idea construction contract](references/idea-construction-contract.md):
  normative Phase 0-4 evidence, lineage, pattern, collision, gauntlet,
  implementability, and identity rules.
- [GPU validation protocol](references/gpu-validation-protocol.md): normative
  local Phase 5 budget, queue, SSH/BJTU, launch-authority, recovery, and outcome
  rules.
- `references/researchstudio-idea/UPSTREAM_MANIFEST.json`: pinned file and
  license integrity record.
- `scripts/idea_campaign.py`: initialize, print templates, CAS-seed, check,
  materialize, read-only verify the committed gate, CAS-write
  `PANEL_DESIGN_REVIEW.json`, and verify the deck.
- `scripts/external_alignment_lint.py`: validate external identity/hash
  propagation without rejudging scientific prose.
- `scripts/external_gate_commit.py`: shared strict, semantic verifier for the
  gate-bound content-addressed campaign/lint/slot snapshot used by downstream
  graph and packet consumers.
- `scripts/resource_adapter.py`: normalize captured resource facts, check
  derived budget, validate/hash an immutable launch spec, and prepare a launch
  intent without launching.
- `scripts/run_fixtures.py`: run the offline scientific, materialization,
  identity, queue, resource, concurrency, and workflow-routing proof suite.
