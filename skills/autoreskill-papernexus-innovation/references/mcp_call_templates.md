# MCP Call Templates

Use these templates through the Codex PaperNexus MCP tools, then persist results with `scripts/papernexus_artifact_capture.py`.

## Capability Probe

1. Call `list_corpora`.
2. Select and persist the active `corpus`. When multiple corpora are indexed, every subsequent PaperNexus call must pass `corpus`; otherwise remote MCP returns `Multiple corpora are indexed`.
3. Probe `agent_materials(operation="research_controller", action="status")`, `agent_materials(operation="proposal_graph_session")` availability from the schema/feature list, `agent_materials(operation="research_material_pack")`, and at least one `agent_materials(operation="paper_material_view")` on a known `paperId` from `corpus_sources`.
4. Record the result:

```bash
python scripts/papernexus_probe_record.py --project <project-root> --callable true --corpus <corpus> --corpora-json <list-corpora-result.json> --operation research_material_pack --operation source_discovery_plan --operation negative_evidence_pack --operation experiment_cost_materials --operation paper_material_view --operation import_requisition_pack --operation proposal_graph_session --research-controller true
```

If the MCP call fails, record the failure instead:

```bash
python scripts/papernexus_probe_record.py --project <project-root> --callable false --error "<transport/auth/session error>"
```

## Topic Search

Call `literature_discovery` with `operation=plan` for query design. For broad or long-running topic discovery, use `operation=submit`, poll `operation=progress`, then capture the terminal `operation=report`. Use synchronous `operation=search` only for small targeted lookups with bounded query/result counts.

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind literature_discovery_run --input <submit-or-progress-result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note "topic search async discovery run" --tag topic_search --tag async_discovery
python scripts/papernexus_artifact_capture.py --project <project-root> --kind literature_discovery_packet --input <report-result.json> --stage topic_search --source papernexus-remote.literature_discovery --evidence-note "topic search evidence report" --tag topic_search
```

## PaperNexus Materials

Call `agent_materials` for `source_discovery_plan`, `research_material_pack`, `paper_material_view`, `negative_evidence_pack`, `import_requisition_pack`, and `experiment_cost_materials`. Always pass the active `corpus` when the server indexes more than one corpus. Capture each result with the matching `--kind`.

## Ideation

First materialize a pre-idea discovery plan:

```bash
python scripts/pre_idea_discovery_plan.py --project <project-root> --topic "<research goal>" --target-domain "<target domain>"
```

Then submit broad `literature_discovery` runs for all three required lanes, even if graph evidence already exists:

- `target_domain`: closest priors, SOTA, baseline, dataset, metric, protocol, limitations/future work, negative evidence.
- `near_neighbor`: related but different directions; same task/evaluation pressure with different mechanism, assumption, or optimization route.
- `far_neighbor`: story-line source domains from domain-agnostic challenge abstraction and transferable mechanisms.

The first search pass may be metadata-only, but it must not be a narrow quick search. Metadata-only means no downloads and no graph import yet; breadth still comes from deep query planning, entity expansion, and citation/related-work expansion:

```json
{
  "operation": "submit",
  "corpus": "<corpus>",
  "topic": "<research goal plus explicit lane focus: target_domain|near_neighbor|far_neighbor>",
  "depth": "deep",
  "searchMode": "deep",
  "planningMode": "llm_augmented",
  "llmQueryPlanner": true,
  "citationExpansion": true,
  "openAlexRelatedExpansion": true,
  "maxCandidates": 10000,
  "maxQueries": 48,
  "maxQueriesPerProvider": 8,
  "maxResultsPerQuery": 150,
  "maxLlmQueries": 16,
  "maxCitationSeeds": 24,
  "maxCitationsPerSeed": 50,
  "maxRelatedPerSeed": 50,
  "maxEntityQueries": 48,
  "maxExtractedEntities": 160,
  "maxSeedEntities": 100,
  "maxSeedPapers": 50,
  "maxSeedQueries": 40,
  "papersCoolMaxQueries": 48,
  "pasaMaxQueries": 20,
  "providerConcurrency": 4,
  "retryCount": 5,
  "timeoutMs": 300000,
  "searchBudgetMs": 300000,
  "preferMarkdown": true,
  "generateArxivMarkdownSources": true,
  "allowDownloads": false,
  "importResolved": false,
  "processImports": false,
  "returnPartial": true,
  "persist": true,
  "asyncLifecycle": "submit_progress_report"
}
```

Poll the submitted run with `operation=progress` until a report is available, then call `operation=report`. Keep `returnPartial=true` for broad submissions so provider rate limits or MCP client interruption do not discard already completed server-side work; treat diagnostics as evidence debt when truncation happens. `lane` is workflow metadata, not a `literature_discovery` MCP argument in the current schema, so encode lane focus in `topic` and capture the report into the lane-specific artifact. Do not set `importResolved=true` or `processImports=true` in the first broad metadata pass. After screening, run `resolve`, `import`, `ingest`, or `import_and_process` only for selected high-signal papers.

Capture and triage:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind literature_discovery_run --input <literature-discovery-submit-or-progress-result.json> --stage ideation --source papernexus-remote.literature_discovery --evidence-note "Ideation broad metadata-only async discovery run" --tag ideation --tag literature_discovery --tag async_discovery
python scripts/papernexus_artifact_capture.py --project <project-root> --kind literature_discovery_packet --input <literature-discovery-report-result.json> --stage ideation --source papernexus-remote.literature_discovery --evidence-note "Ideation broad metadata-only literature discovery report" --tag ideation --tag literature_discovery
python scripts/pre_idea_discovery_config_lint.py --project <project-root>
python scripts/discovery_metadata_triage.py --project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage ideation
python scripts/paper_selection_scorecard_lint.py --project <project-root>
```

Capture lane-specific packets when available:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind target_domain_discovery_packet --input <target-domain-search-result.json> --stage pre_idea --source papernexus-remote.literature_discovery
python scripts/papernexus_artifact_capture.py --project <project-root> --kind near_neighbor_discovery_packet --input <near-neighbor-search-result.json> --stage pre_idea --source papernexus-remote.literature_discovery
python scripts/papernexus_artifact_capture.py --project <project-root> --kind far_neighbor_discovery_packet --input <far-neighbor-search-result.json> --stage pre_idea --source papernexus-remote.literature_discovery
```

Use `papernexus/PAPER_SELECTION_SCORECARD.json` to decide which papers should be imported, supplemented, split-read, watched, or rejected before idea generation. Do not import raw discovery mechanically; select roughly 60-80% of the high-signal eligible set and reject duplicates, weak relevance, no-source papers, surveys, and generic benchmarks.

For selected import/supplement papers, prefer the fast Markdown/background semantic import profile when the remote feature matrix supports it:

```json
{
  "operation": "submit",
  "corpus": "<corpus>",
  "taskIds": ["<optional-existing-task-id>"],
  "papers": ["<selected paper refs or source paths>"],
  "processingProfile": "fast-md-background-semantic",
  "completionPolicy": "graph-visible",
  "importExecutionMode": "dag",
  "preferMarkdown": true,
  "generateArxivMarkdownSources": true,
  "llmContextWindowTokens": 1000000,
  "llmExtractionStrategy": "long-context-first",
  "llmLongContextMaxPapersPerCall": 10,
  "llmBatchConcurrency": 2,
  "importBatchEnabled": true,
  "importBatchInitialTasks": 4,
  "importBatchMaxTasks": 16,
  "importBatchProgressive": true
}
```

Capture import/material status and split-reading evidence:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind graph_import_plan --input <graph-import-plan.json> --stage pre_idea --source papernexus-remote.agent_materials
python scripts/papernexus_artifact_capture.py --project <project-root> --kind import_workflow_status --input <import-workflow-submit-status-or-wait-result.json> --stage pre_idea --source papernexus-remote.import_workflow --tag pre_idea --tag import_workflow
python scripts/papernexus_artifact_capture.py --project <project-root> --kind split_reading_evidence_pack --input <split-reading-material-pack.json> --stage pre_idea --source papernexus-remote.agent_materials --evidence-note "Pre-idea split-reading evidence pack" --tag pre_idea --tag source_backed
python scripts/split_reading_evidence_pack_lint.py --project <project-root>
```

For status checks, use batch task lookup with explicit selected `taskIds` and wait targets. Record `graph-visible`, `semantic-complete`, and `authoritative-sync` separately in `IMPORT_WORKFLOW_STATUS.json`. `GRAPH_IMPORT_STATUS.json` is legacy compatibility only.

Build and capture the innovation slot map, then gate idea generation:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind innovation_slot_map --input <innovation-slot-map.json> --stage ideation --source papernexus-remote.agent_materials
python "${CODEX_HOME:-$HOME/.codex}/skills/autoreskill-ideation-panel/scripts/pre_idea_evidence_gate_lint.py" --project <project-root> --write-gate
```

When `proposal_graph_session` is available, call it after the pre-idea gate passes and before writing `EXPERIMENT_IDEA_POOL.json`. Always supply an `outputDir` under the AutoResearch project so the proposal bundle is replayable:

```json
{
  "operation": "proposal_graph_session",
  "corpus": "<corpus>",
  "project": "<project-id>",
  "problem": "<research goal>",
  "targetDomain": "<target domain>",
  "runId": "<stable-run-id>",
  "maxRounds": 5,
  "outputDir": "<project-root>/.autoreskill/papernexus/proposal_graph_sessions/<stable-run-id>",
  "evidenceRefs": ["<split-reading evidence ids>"],
  "evidenceExport": {"source": "pre_idea_split_reading_and_slot_map"}
}
```

Capture and lint:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind proposal_graph_session --input <proposal-graph-session-result.json> --stage ideation --source papernexus-remote.agent_materials --evidence-note "Committed PaperNexus proposal graph full-paper idea bundle" --tag ideation --tag proposal_graph --tag source_backed
python scripts/proposal_graph_session_lint.py --project <project-root>
```

If the result has `final_status="diagnosis"`, record the commit blockers and repair evidence/actions before idea generation. Use `idea_catalyst(mode=hybrid, outputMode=packet_bundle)` or `research_controller` only as fallback/scoring evidence when `proposal_graph_session` is unavailable, blocked, or explicitly recorded as diagnosis. Capture graph evidence as `graph_ideation_packet`, then capture the returned `evidence_export` as a first-class `idea_catalyst_evidence_export` artifact:

```bash
python scripts/papernexus_artifact_capture.py --project <project-root> --kind graph_ideation_packet --input <idea-catalyst-result.json> --stage ideation --source papernexus-remote.idea_catalyst --evidence-note "Idea Catalyst packet evidence" --tag ideation
python scripts/papernexus_artifact_capture.py --project <project-root> --kind idea_catalyst_evidence_export --input <idea-catalyst-result.json> --stage ideation --source papernexus-remote.idea_catalyst --evidence-note "Idea Catalyst evidence export" --tag ideation --tag source_backed
```

`idea_catalyst_evidence_export` accepts either the full `idea_catalyst` result or a standalone `evidence_export` JSON object. Only write `idea_catalyst_contract` when the selected idea is ready and has evidence, novelty risk, baseline norms, and falsifier.

## Research Controller

Only call `agent_materials(operation="research_controller")` when the remote MCP schema exposes it. If unavailable, record `research_controller_available=false` and use material packs plus ideation-panel design review.
