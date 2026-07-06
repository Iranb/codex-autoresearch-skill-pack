# Experiment Idea Pool

Create `ideation/EXPERIMENT_IDEA_POOL.json` during the ideation/idea construction stage. The 12-15 items are academic-paper-oriented experiment ideas, not high-level research directions and not engineering backlog tasks. The JSON file is only the container for those ideas.

This is an ideation-stage artifact consumed by experiment planning. Do not refresh the full literature review only to populate it, but do run broad metadata-only, non-importing PaperNexus `literature_discovery search` with `depth="deep"`, `searchMode="deep"`, LLM-augmented query planning, citation/related-work expansion, and high query/candidate caps, then triage the discovered papers before finalizing the pool. Use existing PaperNexus evidence, discovery metadata, committed `proposal_graph_session` bundles when available, code analysis, user priors, and run feedback. PaperNexus proposal graph evidence is the preferred idea-generation substrate; missing `novelty_risk`, `baseline_candidate`, negative evidence, or cost norms must be recorded as evidence debt rather than used to suppress broad brainstorming. Engineering necessities such as evaluators, dashboards, split scripts, metric guards, and launch harnesses belong in `ideation/SUPPORTING_ARTIFACTS.json` unless they are explicitly framed as performance-bearing engineering-method ideas or benchmark/evaluation/dataset/system paper contributions.

Immediately after the pool is generated, create `ideation/IDEA_NOVELTY_VENUE_SCORECARD.json` and `ideation/IDEA_NOVELTY_VENUE_SCORECARD.md`. The scorecard compares every idea against existing papers and the discovery/report evidence, scores top-tier support across multiple dimensions, and recommends which 3-4 ideas should be promoted to closest-prior closure. This scoring happens before `idea_gate` selection so the user can choose one idea for `experiment_plan` with explicit novelty and venue-risk context. Each score row must include `paper_comparison.closest_prior_papers`, `paper_comparison.innovation_comparison`, `paper_comparison.overlap_risk`, `paper_comparison.differentiation_claim`, plus `evidence_debt` and `next_evidence_closure`.

The idea pool must also preserve Graph-of-Evidence handoff fields for ranked or selected ideas: `goe_path_refs`, `closest_prior_delta`, `mechanism_source_path`, `negative_evidence_refs`, `reviewer_attack_surface`, `falsifier_probe`, and `track_seed_spec`. Low-maturity ideas may carry these as evidence debt, but selected or evidence-backed ideas cannot pass `idea_gate` without them.

Required shape:

```json
{
  "schema_version": 1,
  "created_at": "",
  "idea_generation_scope": "experiment idea generation; broad pre-idea discovery plus targeted follow-up evidence closure",
  "locked_protocol": {
    "dataset": "",
    "data_split": "",
    "primary_metric": "",
    "metric_direction": "higher|lower",
    "baseline_training_protocol": "",
    "baseline_eval_protocol": "",
    "evaluation_command": "",
    "protected_paths": [
      {"path": "", "purpose": "eval|test_data|metric", "sha256": ""}
    ]
  },
  "selected_idea_id": "IDEA-001",
  "ideas": [
    {
      "id": "IDEA-001",
      "type": "ALGO|CODE|PARAM",
      "priority": "HIGH|MEDIUM|LOW",
      "risk": "LOW|MEDIUM|HIGH",
      "source": "papernexus|code_analysis|run_feedback|user_prior|hybrid",
      "source_paper_or_technique": "",
      "paperNexus_evidence_ids": [],
      "derived_from_idea_fragment_ids": [],
      "proposal_session_ref": {
        "run_id": "",
        "manifest_path": "papernexus/proposal_graph_sessions/<run_id>/proposal-session-manifest.json",
        "committed_subgraph_id": "",
        "proposal_md_path": "",
        "proposal_json_path": ""
      },
      "proposal_graph_refs": {
        "role_action_trace_path": "",
        "commit_decisions_path": "",
        "evidence_export_path": ""
      },
      "proposal_reuse_or_delta": "reused|mechanism_variant|risk_repair|eval_variant|transfer_variant|none",
      "evidence_maturity": "blue_sky|promising|evidence_backed|plan_ready",
      "papernexus_hints": [],
      "missing_materials": [
        {
          "type": "novelty_risk|baseline_candidate|negative_evidence|protocol|cost_norms|citation",
          "why_it_matters": "",
          "followup_path": []
        }
      ],
      "followup_evidence_plan": [],
      "goe_path_refs": [],
      "closest_prior_delta": "",
      "mechanism_source_path": "",
      "negative_evidence_refs": [],
      "reviewer_attack_surface": [],
      "falsifier_probe": "",
      "track_seed_spec": {
        "track_id": "",
        "one_variable_change": "",
        "expected_metric_effect": "",
        "baseline_pressure": "",
        "locked_or_missing_protocol_fields": [],
        "minimum_pilot": [],
        "kill_condition": ""
      },
      "description": "",
      "hypothesis": "",
      "one_variable_change": "",
      "expected_metric_impact": "",
      "implementation_scope": "",
      "paper_contribution": {
        "paper_thesis": "",
        "contribution_type": "method|benchmark|dataset|evaluation|analysis|theory|system",
        "target_venue_fit": "",
        "novelty_claim": "",
        "baseline_pressure": "",
        "minimum_experiment_table": "",
        "ablation_plan": "",
        "falsifier": "",
        "innovation_bundle": [
          {
            "name": "",
            "role": "problem_definition|protocol|benchmark|evaluation|metric|method_mechanism|algorithm|model|architecture|training_mechanism|training_integration|system_integration|theory_analysis|ablation|validation|analysis",
            "source_role": "target_domain_anchor|near_neighbor|far_neighbor|cross_lane_recombination|proposal_graph_transfer|external_domain_transfer|target_domain_absence_proven",
            "source_evidence_refs": [],
            "closest_prior_delta": "",
            "paper_story_role": "",
            "validation_plan": ""
          }
        ],
        "storyline": {
          "opening_tension": "",
          "hidden_cause": "",
          "method_as_resolution": "",
          "proof_ladder": [],
          "reviewer_risk_and_defense": "",
          "narrative_spine": []
        },
        "performance_claim": "",
        "standalone_engineering": false
      },
      "red_line_audit": {
        "metric_drift": false,
        "eval_drift": false,
        "dataset_drift": false,
        "data_leakage": false,
        "prediction_cheating": false,
        "training_budget_drift": false
      },
      "status": "PENDING|SELECTED|RUNNING|FAILED|NOT_PROMOTED|PROMOTED|REJECTED"
    }
  ]
}
```

Selection rules:

- Generate 12-15 ideas during `ideation`, before `experiment_plan`.
- When `proposal_graph_session` is available and committed, use it as the primary PaperNexus seed, then expand it into a diverse pool by changing mechanism, evaluation protocol, risk repair, near-neighbor pressure, or far-neighbor transfer. Do not reduce the default AutoResearch pool to one idea unless the user explicitly requests a single full-paper proposal.
- Score all generated ideas in `IDEA_NOVELTY_VENUE_SCORECARD.json` before `idea_gate`; the scorecard is the screening authority for choosing which idea enters experiment planning.
- Generate `EVIDENCE_GRAPH_PROJECTION.json`, `IDEA_BUILD_BRIEF.json/md`, and `GOE_IDEA_AUDIT.json` before final ranking. Generate `IDEA_TRACK_SEEDS.json` during `idea_gate` for the primary plus 2-3 alternate tracks.
- Use the scorecard to front-load novelty comparison and top-tier-paper support analysis. Do not select an idea for experiment planning until every idea has been ranked, compared with closest priors, and assigned an `advance`, `advance_with_constraints`, `park`, or `kill` recommendation.
- Each item must be writable as a paper thesis. If an item would appear only in an implementation checklist, move it to `SUPPORTING_ARTIFACTS.json`.
- Each item must contain `paper_contribution.innovation_bundle` with at least three mutually necessary paper-level innovation points. The bundle must cover at least one problem/protocol/evaluation role, one method/mechanism role, and one training/integration/analysis/validation role, with at least one point sourced from near-neighbor, far-neighbor, cross-lane, proposal-graph, or external-domain transfer evidence. Three module names are not enough.
- Each item must contain `paper_contribution.storyline` with opening tension, hidden cause, method-as-resolution, proof ladder, reviewer risk/defense, and a 5-7 step narrative spine. The storyline must explain why the three-or-more innovation points form one paper rather than a loose checklist.
- Prefer Tier 1 `ALGO` method/cross-paper/architecture ideas. Require at least 8 `ALGO` ideas by default.
- `CODE` ideas are allowed only as performance-bearing engineering-method contributions or benchmark/evaluation/dataset/system paper contributions, not as tooling chores. Keep `CODE` ideas to 4 or fewer. A performance-bearing `CODE` idea must include `paper_contribution.performance_claim`, expected metric impact, a baseline comparison, and an ablation plan.
- Keep Tier 3 `PARAM`-only ideas to 2 or fewer; use them only when they define a paper-level hypothesis rather than a tuning sweep.
- Prefer at least 6 ALGO ideas with an explicit source paper, technique, PaperNexus evidence id, or committed proposal graph reference when available. Do not block ideation if fewer are available; mark unsupported ideas as `blue_sky` or `promising` and add `missing_materials`.
- `locked_protocol` is a planning hint during ideation. It may be incomplete, but unresolved dataset/metric/baseline/eval entries must be closed by `experiment_plan` before launch.
- Select one idea during `idea_gate` before entering `experiment_plan`.
- A selected idea may still be `promising`, but it cannot become a launchable plan until experiment planning upgrades it to `plan_ready` by closing novelty, baseline, protocol, PaperNexus support, and falsifier gaps.
- Mark ideas that fail the red-line audit as `REJECTED` or `NOT_PROMOTED` before launch.
- Track seeds are not launch approval. `experiment_plan` must convert them into `TRACK_PLAN_MATRIX.json` rows and mark each row `ready`, `blocked`, `diagnostic_only`, or `parked` after baseline/protocol/evidence closure.

Idea status is a ledger pointer, not a claim. An idea becomes evidence only after `REMOTE_RUN.json`, metrics, source snapshot, and `EXPERIMENT_LEDGER.json` record the result.
