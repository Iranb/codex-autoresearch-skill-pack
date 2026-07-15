---
name: autoreskill-ideation-panel
description: Evidence-backed multi-persona ideation and idea-gate skill for portable AutoResearch. Use to build a compact pool of falsifiable causal hypotheses from PaperNexus or committed external-material pre-idea evidence, detect semantic duplicates, run adversarial pairwise comparison, deepen a 3-5 idea shortlist, select one primary idea, and emit bounded IDEA_TRACK_SEEDS without granting launch approval.
metadata:
  short-description: Causal ideation and idea gate
---

# Ideation Panel

Use after the research problem is clear and `ideation/PRE_IDEA_EVIDENCE_GATE.json` has passed, or has an explicitly approved degraded path with claim limits. This skill owns idea construction and selection. It does not certify novelty, approve launches, or promote claims.

## Inputs And Authority

Consume:

- target-domain, near-neighbor, and far-neighbor discovery evidence;
- `papernexus/ABSTRACT_SCREENING_AUDIT.json` and `PAPER_SELECTION_SCORECARD.json`;
- split-reading/material evidence and negative evidence;
- the slot map committed by the pre-idea gate: for legacy PaperNexus this may be
  `ideation/INNOVATION_SLOT_MAP.json`; for `external_material`, resolve only
  `PRE_IDEA_EVIDENCE_GATE.innovation_slot_map_path`/`slot_map_ref` and verify
  the content-addressed filename, SHA-256, and campaign lineage before use;
- committed `proposal_graph_session` artifacts when available;
- the existing Graph-of-Evidence projection and build brief.

PaperNexus artifacts, a committed `$autoreskill-gpu-idea-validation` external campaign, and model critiques are evidence. `EXPERIMENT_IDEA_POOL.json`, the scorecard, and the downstream `IDEA_DECISION_LEDGER.json` remain the project authorities. A model ranking cannot establish novelty or scientific truth.

If the canonical pre-idea gate is missing or blocked, return to evidence repair. Missing `evidence_source_mode` means legacy `papernexus`; `external_material` requires exact `campaign_ref`/hash, lint, slot-map, and protected candidate refs and is never treated as approved degraded evidence. An approved legacy degraded path must preserve `claim_limits` and `evidence_boundary` in the pool and scorecard. Read the source skill for its evidence policy; do not duplicate remote call configuration here.

For an external-material idea gate, create the independent semantic review from
the source skill's `PANEL_DESIGN_REVIEW.template.json`, in a reviewer context
different from candidate generation, then install it only through:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/autoreskill-gpu-idea-validation/scripts/idea_campaign.py" \
  write-panel-design-review --project <project-root> \
  --input <absolute-independent-panel-review.json> \
  --expected-current-panel-sha256 <sha256-or-absent>
```

Do not write `PANEL_DESIGN_REVIEW.json` directly. The CAS writer binds the
review to the current passed content-addressed campaign commit and admitted
candidate IDs; run external alignment lint after the write.

## Build Causal Hypotheses

Generate 8-12 lightweight hypothesis cards by default. A 6-7 item niche pool or 13-15 item breadth extension requires `pool_size_exception` with `kind`, `reason`, `approved_by`, and `approved_at`. More names are not scientific diversity.

Every card must state:

- `research_question` and one `core_scientific_contribution`;
- target-domain anchor and closest-prior delta;
- intervention, mechanism, and predicted metric/dataset pattern;
- falsifier and strongest alternative explanation;
- cheapest experiment that distinguishes the mechanism;
- `causal_signature`, normalized from intervention + mechanism + predicted pattern;
- source evidence or explicit evidence debt;
- paper potential: target claim, minimum table, and reviewer risk;
- red-line audit for metric/eval/dataset/budget drift, leakage, and prediction cheating.

When the live program contract declares `cross_dataset_method`, a shortlisted
method card must also set `claim_role=method_candidate`, use an `ALGO|CODE`
learner mechanism, predict the outcome pattern on every required dataset, name
its load-bearing parameter and scale type, choose a provisional transfer mode,
and give one paired falsifier that distinguishes mechanism failure from
parameter-scale failure. Ideation names the transfer assumption and sensitivity;
the Experiment Planner owns concrete 2-3-value ranges, calibration, and freeze.
Evaluator-only, protocol-only, and baseline-calibration ideas use their explicit
non-method claim roles and cannot satisfy the method portfolio target.

Different names with the same causal signature are duplicates. Merge them, reject one, or mark an explicit duplicate/ablation relation. Parameter-only variants remain `PARAM`; engineering chores go to `SUPPORTING_ARTIFACTS.json`. Keep `PARAM` ideas at two or fewer and `CODE` ideas at four or fewer.

One defensible core contribution is sufficient. `supporting_contributions` are optional and count only when each states what central claim fails without it through `counterfactual_necessity`. Validation, analysis, tooling, and presentation are evidence roles, not invented innovations.

Roles run isolated passes:

- Professor: significance and paradigm value.
- Postdoc: feasibility and discriminating experiment.
- PhDStudent: closest-prior and baseline pressure.
- Critic: semantic duplication, alternative explanation, and reviewer attack.

## Score And Shortlist

Score every card before selection. Each score row must retain the standard 1-5 dimensions, closest-prior comparison, evidence closure/debt, and a pairwise comparison against the closest competing idea:

- whether mechanisms differ;
- whether predicted patterns differ;
- the cheapest discriminator;
- verdict: `distinct`, `redundant`, `ablation`, or `uncertain`.

A `redundant` row cannot advance. Pairwise scores and tournament rankings are
screening evidence only. After the hard gates, use a deterministic lexicographic
order: more unique claim/decision targets, more competing explanations
distinguished, lower cheapest-falsifier GPU-hours, more reuse of locked
baseline/code/data/runtime components, then lower reviewer novelty/confound
risk. `validation_density = unique_decision_targets / estimated_gpu_hours` may
explain the order; do not invent a success probability.

Choose a 3-5 idea shortlist in one batch for the current selection revision.
Only shortlisted ideas require the expensive deep contract: full closest-prior
comparison, baseline pressure, positive/negative/inconclusive/invalid routes,
ablation path, claim boundary, and paper-contribution fields. Only the selected
primary must have the complete 5-7 step paper storyline before experiment
planning. Downstream heartbeats consume this committed shortlist; rerun broad
generation only after an explicit lifecycle decision records exhaustion,
invalidation, or strategic supersession.

A WorkflowGuard `replenish_experiment_portfolio` decision is such a trigger only
when it records a positive portfolio deficit, no fillable committed candidate,
fresh capability-known idle capacity, an unresolved program claim, remaining
budgets, and a changed program/lifecycle/evidence/decision/resource fingerprint.
Zero active tracks are eligible after the idempotent replenishment ledger event
is committed. Reuse the current canonical evidence source, perform only targeted
incremental discovery for missing roles, preserve the selected primary and its
selection fingerprint, and advance only the shortlist supply revision. Raw idle
GPU count alone is not a trigger.

The scorecard must name the shortlist through `shortlisted_idea_ids` or `top_track_recommendations`. Select one primary with `selected_primary_idea_id` and mirror it to the pool's `selected_idea_id` or `status=SELECTED`.

## Emit Track Seeds

Generate `IDEA_TRACK_SEEDS.json` after selection:

- default portfolio: one primary plus two alternates;
- hard maximum: exactly one primary plus at most three alternate/risk-repair
  seeds when `active_track_limit=4` is explicitly recorded;
- track candidates are not random seeds and do not change the three-random-seed stability cap;
- every seed carries one stable `hypothesis_contract`, four outcome routes, belief state `untested`, and `max_scientific_revisions=2`;
- child hypotheses must state parent, source run, and one causal delta;
- `launch_approval=false` for every seed.
- bind membership, roles, and causal contracts with canonical
  `semantic_sha256`; changing any of them invalidates downstream per-track
  packets and matrix rows.
- keep `admitted_at` outside the per-track semantic hash so audit timestamps do
  not invalidate unchanged science; preserve the prior timestamp/hash for an
  unchanged admitted track.
- when the portfolio has open slots, admit the exact causally distinct feasible
  shortlist subset up to the deficit in one batch; do not serialize it to one
  new track per heartbeat.

Experiment planning closes baseline, protocol, dataset, compute, and selected-evidence gaps. It may not rewrite the selected mechanism into a convenient target-domain tweak.

## Outputs

Required idea-stage outputs:

- `EXPERIMENT_IDEA_POOL.json`
- `IDEA_NOVELTY_VENUE_SCORECARD.json` and `.md`
- `EVIDENCE_GRAPH_PROJECTION.json`
- `IDEA_BUILD_BRIEF.json` and `.md`
- `GOE_IDEA_AUDIT.json`
- `IDEA_TRACK_SEEDS.json`
- `TOURNAMENT_SCOREBOARD.json`
- `RESEARCH_PROPOSAL.md`
- `.autoreskill/user_view/innovation_story/00_STORYLINE_DESIGN.md` for the selected primary only

Trees and direction summaries are optional projections. They never replace the JSON authorities.

## Deterministic Checks

```bash
python scripts/pre_idea_evidence_gate_lint.py --project <project-root>
python scripts/idea_graph_projection.py --project <project-root>
python scripts/idea_graph_lint.py --project <project-root> --write-audit
python scripts/idea_build_brief.py --project <project-root>
python ../autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root>
python scripts/idea_scorecard_lint.py --project <project-root>
python scripts/idea_track_seeds.py --project <project-root>
python scripts/idea_track_seeds.py --project <project-root> --capacity-target 4 --admit-idea-id <idea-a> --admit-idea-id <idea-b> --dry-run
python scripts/idea_track_seeds.py --project <project-root> --check
python ../autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root> --require-selected
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage ideation
```

Read `references/professor_postdoc_phd_critic_panel.md`, `references/tournament_schema.md`, and `references/novelty_gate.md`. Read `../autoreskill-experiment-plan/references/experiment_idea_pool.md` for the canonical tiered schema.
