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
  "dataset_or_benchmark": "locked dataset or benchmark",
  "evidence_paths": [".autoreskill/papernexus/research_material_pack.json"],
  "idea_evidence_export_path": ".autoreskill/papernexus/idea_catalyst_evidence_export.json",
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

If `research_controller` is unavailable, use an ideation-panel design review path and set `degraded_controller=true`.

`idea_support_lint.py` verifies that `selected_idea_fragment_id` is present in `idea_evidence_export_path` with PaperNexus provenance, source records, and source spans. Legacy `evidence_paths` or `supporting_papers` are not enough unless they resolve to source-backed evidence.
