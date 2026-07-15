# Non-PaperNexus idea construction contract

This is the normative scientific contract for
`NON_PAPERNEXUS_IDEA_CAMPAIGN.json`. It adapts ResearchStudio-Idea paper Phases
0-4 to AutoResearch without copying the upstream workflow control plane. Local
GPU validation is Phase 5 and is specified separately in
`gpu-validation-protocol.md`.

## 1. Authority and provenance

The campaign is authoritative only for captured external evidence, an explicit
method lineage, structural gaps, candidate construction/audit records, protected
pilot commitments, and its own revision history. It is evidence for downstream
AutoResearch reviewers; it is not an idea-selection ledger, plan, queue, run
record, result, or claim authority.

Required campaign declarations include:

- `schema_version`, immutable `campaign_id`, monotonic `campaign_revision`, and
  `parent_campaign_sha256` after the first revision;
- research `direction`, constraints, claim limits, and campaign status;
- `source_mode = external_material` and `papernexus_used = false`;
- method/deck version metadata and the pinned deck aggregate;
- quick-pilot ceiling and user/project constraint inputs.

Reject PaperNexus corpus, proposal-session, agent-material, MCP, provider, or
fabricated `mcp_attempted` provenance. Do not map a failed PaperNexus run to this
route.

## 2. Phase 0 — evidence readiness

### Search trace

Preserve enough detail to replay or bound every search:

- query text and intent;
- provider/source collection;
- search time and covered time range;
- returned stable references and selection/exclusion notes;
- per-result full-text acquisition status and source-verification limits.

Use three evidence lanes:

1. `target_domain`: direct methods and current frontier;
2. `near_neighbor`: adjacent tasks or mechanisms that sharpen differentiation;
3. `far_neighbor`: transferable mechanisms or counterexamples from another
   community.

Lane coverage supports breadth; it does not excuse missing direct evidence.

### Evidence record

Every load-bearing record must preserve:

- stable source identifier/URL and bibliographic identity;
- locator or span precise enough to find the statement;
- a short captured excerpt;
- SHA-256 of the exact captured excerpt bytes;
- evidence level, role, full-text status, and `citable` flag;
- a note distinguishing local excerpt integrity from verification against the
  original source.

An excerpt hash detects local drift; it does not prove the source was quoted
faithfully. Preserve verification status honestly.

### Readiness gate

Candidate construction requires `evidence_readiness = ready`, at least two
citable method/full-text records supporting the bottleneck, and a full-text
closest anchor. Abstract-only or degraded records may remain awareness context
but cannot establish the core gap. `degraded` and `not_ready` stop Phase 2.

Do not load the pattern deck in Phase 0.

## 3. Phase 1 — lineage and structural gap

### Explicit graph

Represent methods as named nodes and explicit relations. Every citable edge has
evidence; array position or publication date never implies ancestry.

Permitted evidence classes:

- `external_citable`: stable, verified-enough literature evidence that may
  support lineage, bottleneck, differentiation, and collision claims;
- `parametric_awareness_only`: a non-citable memory cue that may warn against
  regressing to an older family but may not support a gap, novelty,
  differentiation, collision, or acceptance decision.

Do not fabricate ancestors to create depth or age bands. A shallow, supported
lineage is better than a deep speculative one.

### Gap rules

- An additive gap attaches to the unresolved residual of a citable frontier
  leaf and explains what necessary mechanism is missing.
- A subtractive gap identifies a shared assumption across citable methods and
  supplies evidence that the assumption is actually shared.
- Another structural gap must define its shape, supporting frontier nodes, and
  why it is not merely a benchmark wish or vague performance deficit.

Every candidate closure references a declared gap by ID. Do not let a pattern
invent a gap after selection.

Do not load the pattern deck in Phase 1.

## 4. Phase 2 — pattern selection before generation

### Campaign and transaction cardinality

The campaign carries 8-12 independent candidate transactions, then a 3-5 item
shortlist, with no more than four candidates admitted as downstream tracks.
Each candidate is a K=1 construction/audit transaction; campaign breadth does
not turn one generation call into a multi-candidate IdeaSpark transaction.

Each candidate has 1-3 counted `gap_closures`, default 2. A single closure is
allowed only for an explicitly labeled single-gap fast diagnostic. Every
closure contains one `gap_ref`, one primary `main_pattern`, one selected
`subpattern` (`C##`), structural-fit reasoning, recipe application, and concrete
mechanism effect. Reusing a main pattern for two gaps still counts as two
closures. Unique-pattern count is not closure count.

Companion roles are disabled in v1. `companion-combos.md` is not vendored and
must not be reconstructed from model memory.

### Progressive deck disclosure

| Decision | Files/sections allowed | Forbidden influence |
|---|---|---|
| Select main pattern | `ideation-patterns/overview.md` only | full cards, failure lessons, frequency or acceptance as rankers |
| Select subpattern | add `ideation-sub-patterns/overview.md` only | loading all C## cards or selecting by `n_papers` |
| Generate mechanism | selected 1-3 C## cards: `Tactical pattern` and `Step-by-Step` only | `Tactical failure mode`, Reject lessons, anti-patterns |
| Audit | selected cards' failure/Reject sections plus `anti-patterns.md`; selected full main card only if needed | unselected subcards; generation-time negative priors |

Never load all 31 subpattern cards into one context. Pattern frequency and
acceptance history are descriptive/audit priors only, never generation ranking
or novelty evidence.

### Candidate mechanism and falsifier

The candidate must contain ordered mechanism steps and specify:

- the concrete intervention and why it closes each selected gap;
- exactly one named load-bearing variable;
- a minimal experiment and outcome metric with expected direction;
- a non-tautological negative control on the load-bearing variable that predicts
  the downstream outcome returns toward the locked baseline;
- the strongest alternative explanation and how the discriminator separates it;
- positive, negative, inconclusive, and invalid outcome routes;
- a pilot-only resource ceiling and one-seed default.

Ablating the output itself, removing the entire method, or checking an internal
quantity that mechanically follows from the intervention is not a valid
negative control. The control must threaten the mechanism while preserving the
rest of the protocol enough to interpret the downstream metric.

## 5. Phase 3 — collision and quality gauntlet

### Mechanism-targeted collision

Run two channels and record every query execution and hit channel:

- `signature_terms`, candidate-native terms, recent 10-month window;
- `alias_terms`, cross-community names for the same mechanism, 48-month window.

The audit names the worst concrete prior paper, the exact result it establishes,
and a result-level subsumption argument. Do not dismiss an alias ancestor for
age. A `parametric_family_concern` is a soft search cue only.

An exact-mechanism collision is a hard abandon. If no concrete threat is found,
record `no_threat_found`, the full query trace, coverage limits, and narrowed
claim language. No-hit is never a novelty certificate.

Optional `scoop_axes` may annotate problem framing, core mechanism, key insight,
and application domain. They neither satisfy nor replace the concrete
`paper_pointed_threat`.

### Generation/audit isolation

Generation must not read negative priors. Audit runs in a separate context and
may then load:

- only selected C## cards' tactical failure and Reject-lesson sections;
- `anti-patterns.md`;
- collision results and the candidate's generation trace.

Require exactly five named checks:

1. `gap_closure_reject_check`: does every closure avoid the selected card's
   known Reject lessons and genuinely close its referenced gap?
2. `recipe_application_check`: does the mechanism execute the selected tactical
   recipe rather than cite its label decoratively?
3. `anti_pattern_check`: is the composition free of unmitigated generic or
   reject-enriched anti-patterns?
4. `paper_pointed_threat`: does the worst concrete prior subsume the proposed
   result or mechanism?
5. `falsification_structure_check`: does the falsifier include the minimal
   experiment, metric/direction, one load-bearing variable, meaningful control,
   alternative explanation, and routes? This fifth check is pinned-repository
   hardening, not attributed to paper v1.

The audit returns `advance | revise | abandon`, a hard/soft layer, rationale,
and explicit revision targets. It judges only and never mutates the candidate.

Hard-floor `abandon` applies to a triggered Reject lesson, unmitigated
anti-pattern, or exact-mechanism collision. Recipe bypass returns to revision or
candidate reconstruction. A separate repair context may fix falsification
structure at most once while preserving the experiment, metric, claim, and
compute. Compute has no repair route. Any material repair is an explicit
candidate/campaign revision followed by re-audit; do not hide an internal retry.

## 6. Phase 4 — expansion and implementability

Run implementability review in a fresh skeptical-engineer context, separate
from the generation author and quality auditor. It produces one `enriched_step`
for every mechanism step with the same ID and order and adds:

- `what_changes` relative to the baseline;
- concrete build procedure;
- inputs and outputs;
- implementation assumptions and dependencies.

Record `underspecified_points` with step ID, hole, proposed fill, and either
`filled` or `open`. The reviewer cannot add, delete, rename, or reorder mechanism steps, and
cannot carry or alter protected commitment fields. An open load-bearing hole
blocks admission. Implementability pass is evidence for planning, never launch
authorization.

### Protected commitments

Canonicalize and hash exactly the candidate's:

- falsifier and observable prediction;
- negative control and load-bearing variable;
- metric, direction, dataset/split, and baseline label;
- resource ceiling and seed policy;
- positive, negative, inconclusive, and invalid routes.

Use deterministic JSON ordering/encoding; omit timestamps and environment-local
ordering. Verify the digest through materialization and downstream alignment.
Any material change requires an incremented campaign revision and prior hash.

## 7. Identity and materialization boundary

The immutable identity chain is:

```text
external_campaign_ref + external_campaign_sha256 + external_candidate_id
```

Propagate it through the idea pool, scorecard, decision ledger, track seeds,
track-plan matrix, innovation packet, and experiment-review packet.
`selected_idea_fragment_id`, `track_id`, and `external_candidate_id` are
different identifiers and cannot substitute for one another.

`idea_campaign.py materialize` may write only the content-addressed external
slot map and derived lint plus the external pre-idea gate. The committed gate
carries `campaign_ref`, `campaign_sha256`, `lint_ref`, `lint_sha256`,
`slot_map_ref`, and `slot_map_sha256`; it is written last under lock/CAS.
Consumers resolve and verify those refs rather than reading a legacy fixed
slot/lint path. The adapter never writes the pool, decision ledger, matrix,
queue, `REMOTE_RUN.json`, or `SCIENTIFIC_OUTCOME.json`.

The committed gate has this minimum semantic shape:

```json
{
  "status": "passed",
  "evidence_source_mode": "external_material",
  "lane_attempts_satisfied": true,
  "screening_completed": true,
  "commit_layout": "content_addressed_v1",
  "innovation_slot_map_path": "ideation/committed/INNOVATION_SLOT_MAP.<slot-map-sha256>.json",
  "slot_map_ref": "ideation/committed/INNOVATION_SLOT_MAP.<slot-map-sha256>.json",
  "campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
  "campaign_sha256": "<sha256>",
  "lint_ref": "ideation/committed/NON_PAPERNEXUS_IDEA_LINT.<lint-sha256>.json",
  "lint_sha256": "<lint-sha256>",
  "slot_map_sha256": "<slot-map-sha256>",
  "allowed_next_action": "generate_experiment_idea_pool"
}
```

The slot map deterministically populates the existing non-empty arrays
`challenge_clusters`, `insight_clusters`, `transfer_bridges`, `anchor_nodes`,
and `relation_patterns`, plus `evidence_boundary`. It preserves explicit
lineage/gap relations; array order creates no edge.

The lint records campaign and deck SHA-256 values, completeness/errors/warnings,
source-lane counts, supported/admitted candidate IDs, and validation time. The
gate hashes this derived lint and the slot map so a later campaign edit cannot
inherit stale approval. Same campaign plus same current gate is idempotent. A
changed campaign requires an incremented revision, `parent_campaign_sha256`,
and the caller's current-gate SHA-256; `absent` is valid only when no gate exists.

Downstream external-mode packets use an `evidence_import_gate` with
`status=not_required`, `source_mode=external_material`, campaign and lint refs,
an explicit reason, and `launch_blocked=false`. They must carry external
evidence norms/source-verification limits rather than PaperNexus paths or fake
provenance. A separate, passed `PANEL_DESIGN_REVIEW.json` supplies semantic
reviewer judgment; deterministic lint cannot replace it.

Run `external_alignment_lint.py` at `ideation`, `idea_gate`, and
`experiment_plan`. Its `complete/missing/warnings` result validates identity and
hash continuity; it does not replace semantic panel review.

## 8. Claim limits

ResearchStudio-Idea supplies an idea-construction and audit process, not
experimental proof. A passing campaign may claim only that the candidate is
evidence-grounded, collision-audited within recorded limits, falsifiable, and
implementable enough to plan. It may not claim novelty certification,
superiority, reproducibility, or support from an unrun pilot.

Phase 5 and result interpretation follow `gpu-validation-protocol.md`.
