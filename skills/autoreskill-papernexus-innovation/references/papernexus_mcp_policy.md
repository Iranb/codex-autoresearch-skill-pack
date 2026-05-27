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
literature_discovery plan/search/run
optional open-access import
import_workflow status/wait
repeat graph-grounded lookup
```

Label evidence as `graph_grounded`, `discovery`, `provider_snippet`, `live_discovery`, `agent_inferred`, or `open_risk`.
