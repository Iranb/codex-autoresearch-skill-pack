# Experiment Idea Pool

## Contents

- Purpose and ownership
- Pool tiers
- Lightweight card schema
- Shortlist and selected depth
- Scorecard contract
- Selection rules

## Purpose And Ownership

`ideation/EXPERIMENT_IDEA_POOL.json` is created by `autoreskill-ideation-panel` and consumed by experiment planning. It contains falsifiable paper hypotheses, not engineering backlog items or launch approval.

Build it from the passed pre-idea evidence gate, `INNOVATION_SLOT_MAP.json`, screened PaperNexus evidence, negative evidence, proposal-graph artifacts when available, code analysis, user priors, and run feedback. Missing support becomes explicit evidence debt; it does not become invented evidence.

## Pool Tiers

Default pool size is 8-12 lightweight cards. Counts 6-7 require `pool_size_exception.kind="niche_topic"`; counts 13-15 require `kind="breadth_extension"`. Every exception records `reason`, `approved_by`, and `approved_at`.

After scoring:

- all cards remain lightweight and comparable;
- 3-5 shortlisted cards receive deep scientific and paper fields;
- one selected primary receives the complete paper storyline;
- one primary plus two alternates enter `IDEA_TRACK_SEEDS.json` by default, with four as the hard explicit maximum.

This tiering prevents speculative paper prose from consuming context before a mechanism survives screening.

## Lightweight Card Schema

```json
{
  "schema_version": 2,
  "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
  "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
  "pool_size_exception": {
    "kind": "niche_topic|breadth_extension",
    "reason": "",
    "approved_by": "",
    "approved_at": ""
  },
  "shortlisted_idea_ids": ["IDEA-001", "IDEA-002", "IDEA-003"],
  "selected_idea_id": "IDEA-001",
  "ideas": [
    {
      "id": "IDEA-001",
      "type": "ALGO|CODE|PARAM",
      "priority": "HIGH|MEDIUM|LOW",
      "risk": "LOW|MEDIUM|HIGH",
      "status": "PENDING|SHORTLISTED|SELECTED|PARKED|REJECTED",
      "research_question": "",
      "core_scientific_contribution": "",
      "target_domain_anchor": "",
      "closest_prior_delta": "",
      "intervention": "",
      "mechanism": "",
      "predicted_pattern": "",
      "falsifier": "",
      "alternative_explanation": "",
      "cheapest_discriminating_experiment": "",
      "causal_signature": "normalized intervention | mechanism | predicted pattern",
      "source_evidence_refs": [],
      "evidence_debt": [],
      "evidence_maturity": "blue_sky|promising|evidence_backed|plan_ready",
      "paper_potential": {
        "target_claim": "",
        "minimum_experiment_table": "",
        "reviewer_risk": ""
      },
      "supporting_contributions": [
        {
          "name": "",
          "counterfactual_necessity": "central claim that fails if removed",
          "evidence_refs": [],
          "validation_plan": ""
        }
      ],
      "primary_method_source_role": "near_neighbor|far_neighbor|cross_lane_recombination|proposal_graph_transfer|external_domain_transfer|target_domain_absence_proven",
      "innovation_slot_refs": [],
      "red_line_audit": {
        "metric_drift": false,
        "eval_drift": false,
        "dataset_drift": false,
        "data_leakage": false,
        "prediction_cheating": false,
        "training_budget_drift": false
      }
    }
  ]
}
```

The linter derives a causal signature when the explicit field is absent. Two cards sharing the same intervention, mechanism, and predicted pattern are scientifically duplicate even if their titles or module names differ. Merge them, reject one, or record `causal_relation.type=duplicate|merged|ablation` and `related_idea_id`.

Every card needs source evidence or explicit evidence debt. Parameter-only changes remain `PARAM`. Pure infrastructure, parsers, dashboards, split scripts, and harness work belong in `SUPPORTING_ARTIFACTS.json` unless they have an independent benchmark, evaluation, dataset, or systems research claim.

## Shortlist And Selected Depth

Each shortlisted card adds:

- `paper_contribution`: thesis, contribution type, venue fit, novelty claim, baseline pressure, minimum table, ablation plan, and falsifier;
- `closest_prior_comparison`;
- `claim_boundary`;
- `outcome_routes.positive|negative|inconclusive|invalid`;
- Graph-of-Evidence refs, negative evidence, reviewer attack surface, falsifier probe, and `track_seed_spec`.

`supporting_contributions` is optional. One core scientific contribution is enough. A supporting item counts as innovation only when its `counterfactual_necessity` identifies a central claim that fails without it.

Only the selected primary adds `paper_contribution.storyline` with:

- opening tension;
- hidden cause;
- method as resolution;
- proof ladder;
- reviewer risk and defense;
- a 5-7 step narrative spine.

The selected story is a planning contract, not evidence that the story is true.

## Scorecard Contract

`ideation/IDEA_NOVELTY_VENUE_SCORECARD.json` scores every pool row before selection. It records:

- standard 1-5 significance, novelty separation, experiment defensibility, feasibility, evidence maturity, and risk control scores;
- closest-prior paper comparison and evidence boundary;
- the card's exact causal signature;
- `pairwise_comparison` against the closest competing idea: competing id, mechanism difference, predicted-pattern difference, cheapest discriminator, and `distinct|redundant|ablation|uncertain` verdict;
- evidence closure level, evidence debt, and next closure action;
- promotion recommendation and track action;
- `shortlisted_idea_ids` or `top_track_recommendations` containing 3-5 ids;
- optional `selected_primary_idea_id` that must belong to the shortlist.

Only shortlist rows need full venue support, Graph-of-Evidence, source-role, transfer, and paper-story readiness assessments. A redundant pairwise verdict cannot advance. Scores and tournaments are screening evidence, never novelty or launch authority.

## Selection Rules

- Keep `PARAM` at two or fewer and `CODE` at four or fewer.
- Do not force a fixed number of `ALGO` labels; reject semantic duplicates and engineering chores instead.
- Prefer the cheapest experiment that changes a scientific decision, not the idea with the most elaborate prose.
- Do not select a card with unresolved metric/eval/dataset/budget drift, leakage, or prediction cheating.
- A target-domain-only mechanism requires current-field absence evidence for a main novelty claim; otherwise treat it as a baseline, ablation, or diagnostic.
- The selected idea may still have evidence debt, but experiment planning must close novelty, baseline, protocol, and source support before launch.
- `IDEA_TRACK_SEEDS.json` is a bounded hypothesis handoff with `launch_approval=false`, not an experiment command.

Run `idea_pool_lint.py` before and after selection, `idea_scorecard_lint.py` after scoring, and `idea_track_seeds.py --check` after materializing track seeds.
