# Innovation Packet Schema

`orchestrator/INNOVATION_PACKET.json` is the experiment-plan authority.

Required:

```json
{
  "schema_version": 1,
  "status": "ready",
  "selected_idea_fragment_id": "idea_001",
  "supporting_idea_fragment_ids": ["idea_001"],
  "baseline": "method or paper",
  "primary_metric": "metric",
  "fixed_budget": "bounded compute/time/data budget",
  "one_variable_change": "the only intended method/protocol delta",
  "innovation_search_contract": {
    "primary_method_source_role": "near_neighbor|far_neighbor|cross_lane_recombination|proposal_graph_transfer|external_domain_transfer|target_domain_absence_proven",
    "neighbor_transfer_mechanism": "mechanism transferred from near/far neighbor evidence",
    "target_domain_anchor": "current-field problem, baseline/protocol, closest-prior pressure",
    "target_domain_method_overlap_risk": "why this is not already a target-domain method",
    "current_field_absence_evidence": "required only for target_domain_absence_proven"
  },
  "dataset_or_benchmark": "locked dataset or benchmark",
  "evidence_paths": [".autoreskill/papernexus/research_material_pack.json"],
  "idea_evidence_export_path": ".autoreskill/papernexus/idea_catalyst_evidence_export.json",
  "proposal_graph_session_path": ".autoreskill/papernexus/proposal_graph_session.json",
  "proposal_graph_session_manifest_path": ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/proposal-session-manifest.json",
  "proposal_committed_subgraph_id": "proposal-subgraph id",
  "proposal_artifact_paths": {
    "proposal_md": ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/proposal.md",
    "proposal_json": ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/proposal.json",
    "proposal_graph_json": ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/proposal-graph.json"
  },
  "proposal_controller_trace_paths": [
    ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/role-action-trace.jsonl",
    ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/edit-decisions.jsonl",
    ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/commit-decisions.jsonl"
  ],
  "proposal_evidence_export_path": ".autoreskill/papernexus/proposal_graph_sessions/<run_id>/evidence-export.json",
  "supporting_papers": ["paper ids or titles"],
  "evidence_status": "source_backed",
  "evidence_boundaries": {
    "source_backed": ["claims supported by PaperNexus source spans"],
    "agent_inferred": ["agent synthesis from source-backed material"],
    "speculative": ["ideas not yet source-backed"],
    "unsupported": ["known gaps and non-claims"]
  },
  "paperNexus_corpus": "corpus",
  "source_backing_summary": "what is evidence-backed",
  "novelty_basis": "why not already solved",
  "falsifier": "pilot that can kill the idea",
  "controller_innovation_brief_path": ".autoreskill/papernexus/research_controller/innovation-brief.json",
  "controller_design_review_path": ".autoreskill/papernexus/research_controller/design-review.json"
}
```

If `research_controller` is unavailable, a committed `proposal_graph_session` can serve as the controller trace/design authority when its manifest has `final_status="committed"`, a `committed_subgraph_id`, controller trace paths, validation report paths, and proposal evidence export. Otherwise use an ideation-panel design review path and set `degraded_controller=true`.

`idea_support_lint.py` verifies that `selected_idea_fragment_id` is present in `idea_evidence_export_path` with PaperNexus provenance, source records, and source spans, or that a committed proposal graph session manifest is attached for the selected idea. Legacy `evidence_paths` or `supporting_papers` are not enough unless they resolve to source-backed evidence.
