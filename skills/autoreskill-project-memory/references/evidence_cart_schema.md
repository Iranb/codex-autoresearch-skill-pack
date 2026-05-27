# Evidence Cart Schema

Each `.autoreskill/evidence_cart.jsonl` row must be one JSON object:

```json
{
  "schema_version": 1,
  "evidence_id": "ev_unique_id",
  "created_at": "ISO-8601",
  "stage": "ideation",
  "source_type": "papernexus | literature | experiment | review | inference",
  "source_id": "artifact path, paper id, DOI, run id, or review id",
  "item_type": "graph_fact | discovery_span | experiment_result | review_issue | inference",
  "paper_id": "optional",
  "text": "short evidence statement",
  "tags": ["topic_search", "novelty"],
  "confidence": "low | medium | high",
  "provenance": {
    "artifact_path": ".autoreskill/...",
    "mcp_source": "papernexus-remote.agent_materials"
  }
}
```

Do not promote strong claims from `source_type=inference` or discovery-only evidence unless a later graph/experiment/review artifact validates it.
