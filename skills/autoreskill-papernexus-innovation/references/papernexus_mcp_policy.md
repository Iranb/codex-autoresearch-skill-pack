# PaperNexus MCP Policy

Preferred MCP calls:

```text
list_corpora
agent_materials(source_discovery_plan)
agent_materials(research_material_pack)
agent_materials(negative_evidence_pack)
agent_materials(experiment_cost_materials)
research_lookup(domain_distance / interdisciplinary_potential / method_registry / method_lineage / method_evidence / research_answer)
idea_catalyst(mode=hybrid, outputMode=packet_bundle)
research_briefing(evidence_chain / storyline_brief)
```

If graph evidence is sparse, use policy-bounded:

```text
literature_discovery plan
literature_discovery submit/progress/report for broad or long-running discovery
literature_discovery search only for small targeted lookups
optional open-access import
import_workflow queue_progress/status/wait with waitForAuthoritativeSync=true
repeat graph-grounded lookup
```

Selected papers are graph-grounded only after `import_workflow` reports the relevant task `status=completed` and `stage=completed`, with authoritative graph sync complete, superseded, or explicitly `not-required`. Progressive import batching is the default path (`importBatchEnabled=true`, initial 4, max 16); queued/running tasks are async wait, not failure.

When supported by the remote, graph imports should request the fast Markdown/background semantic profile: `processingProfile=fast-md-background-semantic`, `completionPolicy=graph-visible`, `importExecutionMode=dag`, `llmContextWindowTokens=1000000`, `llmExtractionStrategy=long-context-first`, `llmLongContextMaxPapersPerCall=10`, and bounded `llmBatchConcurrency`. `graph-visible` is structural progress; writing and review evidence closure still needs semantic readiness and authoritative sync whenever semantic graph relations are used.

Label evidence as `graph_grounded`, `discovery`, `provider_snippet`, `live_discovery`, `agent_inferred`, or `open_risk`.
