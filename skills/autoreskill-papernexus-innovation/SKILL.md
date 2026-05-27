---
name: autoreskill-papernexus-innovation
description: PaperNexus-backed innovation skill for portable AutoResearch. Use for /goal topic_search, graph_build, frontier_mapping, negative evidence, source discovery, method transfer, experiment norms, cost norms, novelty risk, and graph-grounded idea evidence through papernexus-remote.
metadata:
  short-description: Build graph-grounded research ideas
---

# PaperNexus Innovation

Use this skill before any ideation or experiment planning. Innovation must be evidence-backed by PaperNexus, not free brainstorming.

## Hard Policy

- Use `papernexus-remote` MCP for live graph work.
- Do not use local PaperNexus CLI, local graph files, raw PaperNexus HTTP, local MCP, or SSH commands as substitutes.
- Feature-detect `agent_materials` operations at runtime and record results in `.autoreskill/capabilities.json`.
- If remote evidence is sparse, use bounded provider/live/literature discovery according to `.autoreskill/autopilot_policy.json`.

## Required Materials

Before an idea can enter `idea_gate` or `experiment_plan`, collect:

- target prior
- near-source method
- far-source story and domain distance
- bridge mechanism
- negative evidence or absence confidence
- novelty risk
- baseline norms
- experiment cost norms
- falsifier pilot

Write materials under `.autoreskill/papernexus/` and evidence ids to `.autoreskill/evidence_cart.jsonl`.

This skill supplies source-backed evidence and PaperNexus material packs. It must not substitute a small set of high-level directions for the experiment idea pool. The 12-15 optimization ideas are produced during ideation by `autoreskill-ideation-panel` as `.autoreskill/ideation/EXPERIMENT_IDEA_POOL.json`, using these PaperNexus materials as inputs.

## Deterministic Helpers

After Codex calls PaperNexus MCP tools, persist the observations:

```bash
python scripts/papernexus_probe_record.py --project <project-root> --callable true --corpus <corpus> --operation research_material_pack --operation source_discovery_plan
python scripts/papernexus_feature_matrix.py --project <project-root> --callable unknown --operation research_material_pack --operation research_controller
python scripts/papernexus_artifact_capture.py --project <project-root> --kind research_material_pack --input <mcp-result.json> --stage frontier_mapping --evidence-note "PaperNexus material pack evidence" --tag papernexus
python scripts/papernexus_artifact_capture.py --project <project-root> --kind idea_catalyst_evidence_export --input <idea-catalyst-result.json> --stage ideation --source papernexus-remote.idea_catalyst --evidence-note "Idea Catalyst evidence export" --tag ideation
python scripts/idea_support_lint.py --project <project-root>
python scripts/evidence_status_lint.py --project <project-root>
```

`idea_support_lint.py` is the hard gate for source-backed selected idea fragments. It must pass before `autoreskill-experiment-plan` treats `INNOVATION_PACKET.json` as stage-complete.

If the MCP call fails, record the transport/auth/session failure with `papernexus_probe_record.py --callable false --error "<reason>"` and do not continue with local PaperNexus substitutes.

Read `references/papernexus_mcp_policy.md`, `references/mcp_call_templates.md`, `references/innovation_packet_schema.md`, and `references/negative_evidence_protocol.md`.
