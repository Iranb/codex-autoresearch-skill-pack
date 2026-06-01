---
name: autoreskill-ideation-panel
description: OpenClaw-aligned multi-persona ideation and experiment-idea construction panel for portable AutoResearch. Use for Professor/Postdoc/PhDStudent/Critic passes, generating the 12-15 academic-paper-oriented experiment idea pool during ideation from pre-idea evidence and PaperNexus proposal_graph_session bundles, novelty tournaments, candidate pool scoring, fallback design review when PaperNexus research_controller/proposal graph is unavailable, selected idea gating, and IDEA_CATALYST_CONTRACT preparation.
metadata:
  short-description: Multi-persona ideation and idea gate
---

# Ideation Panel

Use after the topic/problem is clear and after the pre-idea evidence expansion gate has passed. PaperNexus materials are no longer only optional seeds before brainstorming: target-domain, near-neighbor, and far-neighbor discovery must each be attempted, actively screened, converted into split-reading evidence and innovation slots, and when available matured through `agent_materials(operation="proposal_graph_session")` before generating the experiment idea pool.

The 12-15 experiment ideas are created here, during idea construction. Immediately after creating the idea pool, score every idea for novelty against existing papers and for top-conference/journal support before selecting one for experiments. Do not defer idea generation or idea-level scoring to `autoreskill-experiment-plan`; experiment planning consumes a selected idea and closes the selected idea's evidence gaps.

Every item in `EXPERIMENT_IDEA_POOL.json` must be a plausible academic paper idea, not a standalone engineering task. Treat a valid idea as a paper thesis with a novelty claim, baseline pressure, minimum experiment table, ablation plan, and falsifier. These fields may be provisional during brainstorming, but they must be specific enough to show how the idea could become a paper. Tooling, metric guards, dashboards, split scripts, and harnesses are supporting artifacts unless they are framed as a benchmark, evaluation, dataset, or systems paper with its own research claim.

## Pre-Idea Evidence Gate

Before writing `ideation/EXPERIMENT_IDEA_POOL.json`, require:

- `.autoreskill/literature/PRE_IDEA_DISCOVERY_PLAN.json`
- `.autoreskill/literature/TARGET_DOMAIN_DISCOVERY_PACKET.json`
- `.autoreskill/literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json`
- `.autoreskill/literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json`
- `.autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json`
- `.autoreskill/papernexus/GRAPH_IMPORT_PLAN.json` or an explicit unresolved blocker
- `.autoreskill/papernexus/GRAPH_IMPORT_STATUS.json` when imports/material jobs were submitted
- `.autoreskill/papernexus/SPLIT_READING_EVIDENCE_PACK.json`
- `.autoreskill/papernexus/proposal_graph_session.json` and/or `.autoreskill/papernexus/proposal_graph_sessions/<run_id>/proposal-session-manifest.json` when PaperNexus exposes `proposal_graph_session`
- `.autoreskill/ideation/INNOVATION_SLOT_MAP.json`
- `.autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json` with `status="passed"`

This gate is venue-agnostic. Do not relax the current-field, near-neighbor, and far-neighbor evidence requirements just because the target venue is broad, unknown, or no longer TPAMI-focused.

The three required discovery lanes are:

- `target_domain`: current field, closest priors, SOTA, baseline, dataset, metric, protocol, limitations, negative evidence.
- `near_neighbor`: related but different direction; shared task, dataset, metric, setting, or failure mode, but different mechanism, assumption, or optimization route.
- `far_neighbor`: storyline construction direction; domain-agnostic challenge abstraction and external source-domain mechanisms inspired by Idea-Catalyst-style cross-domain retrieval.

For top-tier method ideas, target-domain evidence is primarily the anchor and adversary: it defines the task, closest priors, baseline pressure, protocol, and overlap risk. The main method mechanism should primarily come from `near_neighbor`, `far_neighbor`, `cross_lane_recombination`, or `proposal_graph_transfer`. A target-domain-only method variant should be moved to baseline/ablation unless the idea includes source-backed proof that the mechanism is absent from the current field and records `current_field_absence_evidence`.

Do not mechanically import raw discovery results. Raw discovery often contains duplicates, weakly related papers, unresolved full-text sources, survey noise, and generic benchmark papers. Codex must actively screen candidates and select about 60-80% of the high-signal eligible set for graph import, material view, or split-reading, not 60-80% of raw search results.

In addition to one-attempt lane coverage, run the general breadth gate. By default, the screened scorecard must include at least target-domain raw/eligible/selected counts of 10/6/4, near-neighbor counts of 12/8/5, far-neighbor counts of 10/7/4, at least 21 eligible candidates total, and at least 13 graph-import or split-read selections total. The near/far-neighbor evidence budget is intentionally heavier because it is the preferred source of top-tier method mechanisms. A sparse niche topic may pass only with an explicit `breadth_exception_approval` or degraded gate that records attempted expansion and claim limits.

Idea generation must consume `INNOVATION_SLOT_MAP.json`, not a bare topic. When a committed proposal graph session exists, use its `proposal.md`, `proposal.json`, committed subgraph, role-action trace, and commit decisions as the primary PaperNexus seed for idea construction. Every non-degraded idea should cite challenge/insight/transfer slot ids through `innovation_slot_refs` or an equivalent field, and any idea derived from the proposal bundle should also cite `proposal_session_ref` or `proposal_graph_refs`. If the gate is missing, blocked, or only metadata-backed, return to discovery/material repair instead of generating the idea pool. A degraded metadata-only path requires explicit user approval and must mark claim limits.

Approved degraded ideation is an exception path, not the default. It is valid only when `ideation/PRE_IDEA_EVIDENCE_GATE.json` has `status="degraded_requires_user_approval"`, `allowed_next_action="generate_experiment_idea_pool_degraded"` or equivalent, `claim_limits`, and `degraded_approval` with `approved=true`, `approved_by`, `approved_at`, and `reason`. In that mode, run `pre_idea_evidence_gate_lint.py --allow-degraded`, and every generated `EXPERIMENT_IDEA_POOL.json` plus `IDEA_NOVELTY_VENUE_SCORECARD.json` must carry `claim_limits` and `evidence_boundary`. Degraded ideas are speculative only; `autoreskill-experiment-plan` must close selected-idea PaperNexus evidence before any formal launch or manuscript claim.

## Brainstorming Policy

Ideation remains divergent after the pre-idea evidence gate passes. Do not discard a candidate only because some secondary `agent_materials` fields remain sparse. Instead, keep the candidate when it has paper potential and annotate the evidence gap.

Each idea should include lightweight maturity fields:

- `evidence_maturity`: `blue_sky`, `promising`, `evidence_backed`, or `plan_ready`.
- `primary_method_source_role`: `near_neighbor`, `far_neighbor`, `cross_lane_recombination`, `proposal_graph_transfer`, or `external_domain_transfer` for top-tier main method ideas.
- `target_domain_anchor`: the current-field problem, baseline/protocol, closest-prior pressure, and overlap-risk evidence the idea must beat.
- `neighbor_transfer_mechanism`: the near/far-neighbor mechanism being transferred, not merely a related-paper citation.
- `papernexus_hints`: known related papers, mechanisms, or idea fragment ids when available.
- `missing_materials`: missing novelty, baseline, protocol, cost, or negative-evidence items.
- `followup_evidence_plan`: PaperNexus/literature discovery/import steps needed before experiment planning.

Use PaperNexus as the pre-idea evidence source and as a critic during scoring. Raw `idea_fragments` are not final ideas; rewrite them as academic paper theses. The pre-idea gate does not certify novelty or launch readiness. Strong selected-idea evidence closure still happens after selection, inside `autoreskill-experiment-plan`.

If `proposal_graph_session` is available and committed, treat the proposal bundle as the strongest single PaperNexus idea object, but do not collapse the ideation stage into one option by default. Expand it into a 12-15 idea pool by varying mechanism, intervention boundary, evaluation target, risk repair, and near/far-neighbor transfer route. Directly emitting only the committed proposal is allowed only when the user explicitly asks for a single full-paper idea rather than the AutoResearch experiment idea pool.

## Post-Idea Novelty And Venue Scorecard

After writing `ideation/EXPERIMENT_IDEA_POOL.json`, and before `idea_gate` selection, produce a scorecard that compares every idea against the local literature report, PaperNexus discovery metadata, graph/material hints, and known closest priors. This scorecard is mandatory for screening one idea into experiments.

Required artifacts:

- `ideation/IDEA_NOVELTY_VENUE_SCORECARD.json`: machine-readable scoring authority.
- `ideation/IDEA_NOVELTY_VENUE_SCORECARD.md`: human-readable ranking and selection rationale.

The JSON scorecard must include:

- `stage="post_idea_generation_pre_idea_gate"`.
- `evidence_boundary`: say whether the score uses metadata-only discovery, graph material, full-text imports, or manual report evidence.
- `pre_idea_evidence_gate_path` and `innovation_slot_map_path`.
- `proposal_graph_session_path` or `proposal_graph_session_manifest_path` when available; if unavailable or diagnosis-only, record the fallback reason.
- `source_evidence_roles`: target-domain, near-neighbor, and far-neighbor evidence roles used by the scorecard.
- `scoring_rubric` and `weights`.
- One row for every idea in `EXPERIMENT_IDEA_POOL.json`.
- Per-idea 1-5 scores for `significance`, `novelty_separation`, `experiment_defensibility`, `feasibility`, `evidence_maturity`, and `risk_control`.
- `weighted_total`, rank, `closest_prior_pressure`, `novelty_separation_needed`, `venue_support_verdict`, `top_tier_support_judgment`, `evidence_debt`, `next_evidence_closure`, and `promotion_recommendation` (`advance`, `advance_with_constraints`, `park`, or `kill`).
- Per-idea `paper_comparison` with `closest_prior_papers`, `innovation_comparison`, `overlap_risk`, and `differentiation_claim`; this is the front-loaded comparison against the local survey, PaperNexus discovery metadata, graph/material hints, and known closest priors.
- Per-idea `innovation_slot_refs`, `near_neighbor_pressure`, and `far_neighbor_transfer_rationale`.
- Per-idea `primary_method_source_role`, `target_domain_anchor`, `neighbor_transfer_mechanism`, and `target_domain_method_overlap_risk`; top-ranked method ideas should not be target-domain-only unless they carry explicit current-field absence evidence.
- Per-idea `proposal_graph_basis` when the idea uses the committed proposal graph, including `run_id`, `committed_subgraph_id`, `proposal_artifact_path`, and which claim/method/risk/eval nodes were reused or changed.
- `top_recommendations`: usually 3-4 ideas that are worth closest-prior closure before experiment planning.

The scorecard is the screening authority for choosing which idea enters experiment planning. It must rank the full 12-15 idea pool before any `idea_gate` selection, surface top-tier-paper support and reviewer risk, and identify the 3-4 candidates worth closest-prior closure. Scorecards are still ideation-stage judgments, not novelty certificates. Do not claim an idea can support a top-tier paper solely because it scores highly here. `autoreskill-experiment-plan` must still supplement/import relevant papers, build the closest-prior difference table, lock baselines/protocols, and upgrade the selected idea to `plan_ready` before launch.

## Mandatory Pre-Idea Discovery And Screening

Every ideation run must trigger broad PaperNexus literature discovery in all three lanes, regardless of whether the graph already has data. The first pass may be metadata-only, but it must use the widest recall-oriented search profile available rather than quick defaults. The pre-idea gate is not metadata-only: high-signal eligible papers must be imported, supplemented, or split-read through PaperNexus unless explicitly blocked.

The first successful discovery pass is not automatically sufficient. If the scorecard has only token coverage, such as one or two papers per lane without enough eligible/selected candidates, continue PaperNexus discovery, manual source expansion, or split-reading repair before idea generation.

Required MCP call when `papernexus-remote` is callable:

- `literature_discovery(operation="search", depth="deep", searchMode="deep", planningMode="llm_augmented", llmQueryPlanner=true, citationExpansion=true, openAlexRelatedExpansion=true, maxCandidates>=10000, maxQueries>=48, maxQueriesPerProvider>=8, maxResultsPerQuery>=150, maxLlmQueries>=16, maxCitationSeeds>=24, maxCitationsPerSeed>=50, maxRelatedPerSeed>=50, maxEntityQueries>=48, maxExtractedEntities>=160, maxSeedEntities>=100, maxSeedPapers>=50, maxSeedQueries>=40, papersCoolMaxQueries>=48, pasaMaxQueries>=20, providerConcurrency>=4, timeoutMs>=300000, searchBudgetMs>=300000, retryCount>=5, importResolved=false, processImports=false, allowDownloads=false, returnPartial=true, persist=true)`

Required artifacts:

- `literature/LITERATURE_DISCOVERY_PACKET.json`: raw metadata-only discovery packet.
- `papernexus/LITERATURE_DISCOVERY_TRIAGE.json`: candidate triage with `import_recommended`, `watchlist`, and `reject_irrelevant` decisions.
- `papernexus/PAPER_SELECTION_SCORECARD.json`: lane-aware active screening with `graph_import`, `split_read_only`, `watchlist`, and explicit `reject_*` decisions.
- `ideation/PRE_IDEA_EVIDENCE_GATE.json`: hard authority for whether idea generation can start.
- `papernexus/proposal_graph_session.json`: preferred PaperNexus idea-generation result when supported.
- `pre_idea_discovery_config_lint.py`: must pass before idea generation; it rejects narrow quick/balanced discovery plans and enforces broad metadata discovery config.

The triage must identify papers that should be supplemented/imported into the graph or split-read before idea generation, especially closest priors, baseline candidates, negative-evidence sources, datasets/benchmarks, mechanisms, limitations/future work, and transfer bridges that shape novelty.

Do not continue to idea generation when discovery/material work fails. Record attempted-discovery and pre-idea gate blocker artifacts with the provider/transport failure and repair the evidence gap first. If `proposal_graph_session` is available but does not commit, repair its commit blockers before idea generation unless policy or user approval allows explicit fallback. Continue only with explicit degraded user approval and claim limits. Legacy projects that already have `EXPERIMENT_IDEA_POOL.json` but no canonical `ideation/PRE_IDEA_EVIDENCE_GATE.json` must first run `scripts/legacy_pre_idea_reconcile.py`; if a gate exists under `orchestrator/` or another non-canonical path, treat it as `pre_idea_gate_misplaced` and repair or rebuild the canonical ideation gate before marking ideation complete.

Roles:

- Professor: paradigm value and significance
- Postdoc: feasibility and experiment path
- PhDStudent: prior work and baseline pressure
- Critic: adversarial novelty/reviewer attack

Outputs:

- `IDEA_TREE.md`
- `NOVELTY_TREE.md`
- `CHALLENGE_INSIGHT_TREE.md`
- `WELL_ESTABLISHED_SOLUTION_CHECK.md`
- `CANDIDATE_POOL.json`
- `EXPERIMENT_IDEA_POOL.json`
- `IDEA_NOVELTY_VENUE_SCORECARD.json`
- `IDEA_NOVELTY_VENUE_SCORECARD.md`
- `TOURNAMENT_SCOREBOARD.json`
- `TOP3_DIRECTION_SUMMARY.md`
- `RESEARCH_PROPOSAL.md`

`EXPERIMENT_IDEA_POOL.json` must contain 12-15 paper-oriented experiment ideas, not only high-level research directions and not engineering backlog items. Prefer method-paper `ALGO` ideas. `CODE` ideas are allowed when they are performance-bearing algorithmic/engineering-method contributions, or benchmark/evaluation/dataset/system paper contributions. Pure infrastructure chores with no measurable research claim go to `SUPPORTING_ARTIFACTS.json`. Target at least 8 `ALGO` ideas, keep `CODE` ideas to 4 or fewer, and keep `PARAM` ideas to 2 or fewer. At least some ideas should cite source papers, techniques, or PaperNexus evidence when available, but absence of complete PaperNexus evidence should become `missing_materials`, not a reason to shrink the pool. Include:

- `paper_contribution.paper_thesis`
- `paper_contribution.contribution_type`
- `paper_contribution.target_venue_fit`
- `paper_contribution.novelty_claim`
- `paper_contribution.baseline_pressure`
- `paper_contribution.minimum_experiment_table`
- `paper_contribution.ablation_plan`
- `paper_contribution.falsifier`
- `paper_contribution.performance_claim` for every `CODE` idea that claims a performance-bearing engineering contribution
- red-line audit fields for metric/eval/dataset/data-leakage/prediction-cheating/training-budget drift
- evidence maturity and follow-up evidence fields listed above
- proposal graph provenance fields when applicable: `proposal_session_ref`, `proposal_graph_refs`, `proposal_manifest_path`, `proposal_committed_subgraph_id`, and `proposal_reuse_or_delta`

Write operational engineering necessities that do not satisfy these fields to `SUPPORTING_ARTIFACTS.json`, not to the idea pool.

During `idea_gate`, select one idea by setting `selected_idea_id` or marking one idea `status=SELECTED`. Selection may choose a `promising` idea with evidence debt, but `experiment_plan` must close the novelty, baseline, protocol, and PaperNexus support gaps before launch.

## Deterministic Helpers

```bash
python scripts/panel_review.py --project <project-root> --force-ready
python scripts/ideation_lint.py --project <project-root>
python scripts/pre_idea_evidence_gate_lint.py --project <project-root>
python scripts/idea_scorecard_lint.py --project <project-root>
python ../autoreskill-papernexus-innovation/scripts/pre_idea_discovery_plan.py --project <project-root> --topic "<topic>" --target-domain "<domain>"
python ../autoreskill-papernexus-innovation/scripts/discovery_metadata_triage.py --project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage ideation
python ../autoreskill-papernexus-innovation/scripts/paper_selection_scorecard_lint.py --project <project-root>
python ../autoreskill-papernexus-innovation/scripts/pre_idea_breadth_lint.py --project <project-root>
python ../autoreskill-papernexus-innovation/scripts/split_reading_evidence_pack_lint.py --project <project-root>
# When proposal_graph_session is available:
python ../autoreskill-papernexus-innovation/scripts/proposal_graph_session_lint.py --project <project-root>
python ../autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json
python ../autoreskill-experiment-plan/scripts/idea_pool_lint.py --project <project-root> --pool ideation/EXPERIMENT_IDEA_POOL.json --require-selected
```

Read references for panel protocol and novelty gate. For the idea pool schema, read `../autoreskill-experiment-plan/references/experiment_idea_pool.md`; despite its file location, the canonical owner is this ideation skill.
