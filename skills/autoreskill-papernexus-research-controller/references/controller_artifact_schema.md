# Controller Artifacts

Mirror these files when available:

```text
.autoreskill/papernexus/research_controller/
  controller-state.json
  controller-export.json
  controller-export.md
  selected-subgraphs.json
  solution-sketches.jsonl
  solution-sketches.md
  innovation-brief.json
  design-review.json
  design-review.md
  method-card-pack.md
```

Downstream innovation packets should cite selected subgraphs, evidence boundaries, innovation brief boundaries, and design review verdicts.

`innovation-brief.json` is the boundary artifact consumed by experiment planning. It should include:

```json
{
  "schema_version": 1,
  "status": "ready",
  "source": "research_controller",
  "selected_idea_fragment_id": "",
  "selected_subgraph_ids": [],
  "controller_export_path": "papernexus/research_controller/controller-export.json",
  "design_review_path": "papernexus/research_controller/design-review.json",
  "what_is_evidence_supported": [],
  "what_is_agent_inferred": [],
  "what_is_speculative": [],
  "unsupported_or_open_gaps": [],
  "evidence_boundaries": {
    "source_backed": [],
    "agent_inferred": [],
    "speculative": [],
    "unsupported": []
  }
}
```

If `research_controller_available=false`, a fallback panel review may be used, but the brief must use `"source": "fallback_panel"` and must not mark speculative content as source-backed.
