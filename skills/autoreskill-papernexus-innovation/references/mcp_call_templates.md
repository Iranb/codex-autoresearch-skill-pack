# MCP Call Templates

Use these templates through the Codex PaperNexus MCP tools, then persist results with `scripts/papernexus_artifact_capture.py`.

## Capability Probe

1. Call `list_corpora`.
2. Record the result:

```bash
python scripts/papernexus_probe_record.py --project <project-root> --callable true --corpus <corpus> --corpora-json <list-corpora-result.json> --operation research_material_pack --operation source_discovery_plan --operation negative_evidence_pack --operation experiment_cost_materials --research-controller false
```

If the MCP call fails, record the failure instead:

```bash
python scripts/papernexus_probe_record.py --project <project-root> --callable false --error "<transport/auth/session error>"
```

## Topic Search

Call `literature_discovery` with `operation=plan` or `operation=search`, then capture:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind literature_discovery_packet --input <result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note "topic search evidence" --tag topic_search
```

## PaperNexus Materials

Call `agent_materials` for `source_discovery_plan`, `research_material_pack`, `negative_evidence_pack`, and `experiment_cost_materials`. Capture each result with the matching `--kind`.

## Ideation

Call `idea_catalyst(mode=hybrid, outputMode=packet_bundle)` or the graph-only fallback allowed by policy. Capture graph evidence as `graph_ideation_packet`, then capture the returned `evidence_export` as a first-class `idea_catalyst_evidence_export` artifact:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind graph_ideation_packet --input <idea-catalyst-result.json> --stage ideation --source papernexus-remote.idea_catalyst --evidence-note "Idea Catalyst packet evidence" --tag ideation
python scripts/papernexus_artifact_capture.py --project <project-root> --kind idea_catalyst_evidence_export --input <idea-catalyst-result.json> --stage ideation --source papernexus-remote.idea_catalyst --evidence-note "Idea Catalyst evidence export" --tag ideation --tag source_backed
```

`idea_catalyst_evidence_export` accepts either the full `idea_catalyst` result or a standalone `evidence_export` JSON object. Only write `idea_catalyst_contract` when the selected idea is ready and has evidence, novelty risk, baseline norms, and falsifier.

## Research Controller

Only call `agent_materials(operation="research_controller")` when the remote MCP schema exposes it. If unavailable, record `research_controller_available=false` and use material packs plus ideation-panel design review.
