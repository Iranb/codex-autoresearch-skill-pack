---
name: autoreskill-papernexus-innovation
description: PaperNexus-backed innovation skill for portable AutoResearch. Use for /goal topic_search, graph_build, frontier_mapping, pre-idea evidence expansion, proposal_graph_session full-paper idea generation, negative evidence, source discovery, method transfer, experiment norms, cost norms, novelty risk, and graph-grounded idea evidence through papernexus-remote.
metadata:
  short-description: Build graph-grounded research ideas
---

# PaperNexus Innovation

Use this skill before experiment planning and whenever live PaperNexus evidence is needed. During ideation, PaperNexus owns the pre-idea evidence expansion gate and now provides the preferred idea-generation substrate through `agent_materials(operation="proposal_graph_session")`: target-domain, near-neighbor, and far-neighbor discovery must be attempted, actively screened, converted into split-reading evidence, and then used to run a committed proposal graph session before the ideation panel writes the 12-15 idea pool when the remote MCP exposes that operation.

Also use this skill after ideation whenever a later stage exposes a concrete evidence gap: selected-idea closest-prior closure, baseline/protocol norms, target-domain absence evidence, negative/contradictory evidence, reviewer novelty/citation objections, or manuscript related-work citation gaps. Later-stage discovery should be targeted and source-backed rather than a broad rerun unless the earlier discovery was demonstrably too narrow.

## Hard Policy

- Use `papernexus-remote` MCP for live graph work.
- Do not use local PaperNexus CLI, local graph files, raw PaperNexus HTTP, local MCP, or SSH commands as substitutes.
- Feature-detect `agent_materials` operations at runtime and record results in `.autoreskill/capabilities.json`.
- If `proposal_graph_session` is exposed, use it as the preferred PaperNexus idea-generation call after the pre-idea evidence gate passes. Legacy `idea_catalyst` and `research_controller` are fallback/scoring evidence, not the primary generator, unless `proposal_graph_session` is unavailable or fails into a recorded diagnosis/blocker.
- If remote evidence is sparse, use bounded provider/live/literature discovery according to `.autoreskill/autopilot_policy.json`.
- During ideation, always run broad `literature_discovery` for three lanes: `target_domain`, `near_neighbor`, and `far_neighbor`. The first search pass can be metadata-only, but it must use deep/recall-oriented planning and expansion defaults rather than quick metadata defaults. `pre_idea_discovery_config_lint.py` must pass before idea generation. Idea generation is blocked until high-signal eligible papers have been imported, supplemented, or split-read through PaperNexus, or until an explicit blocker/degraded approval is recorded.
- Metadata-only discovery still needs explicit reading proof. Before `PAPER_SELECTION_SCORECARD.json`, write `.autoreskill/papernexus/ABSTRACT_SCREENING_AUDIT.json` with one row per merged discovery candidate. Each row records lane, title, stable id, abstract-read status or no-abstract metadata fallback, screening decision, and rationale. `abstract_screening_audit_lint.py` must pass before the pre-idea gate can pass.
- The three-lane breadth requirement is venue-agnostic. Do not apply it only to TPAMI, top journals, or manually named venues. Every paper-oriented research workflow must consider the current field, near-neighbor fields, and far-neighbor transfer fields before idea generation.
- For top-tier method novelty, target-domain evidence is the current-field prior and evaluation anchor; it should usually attack, constrain, or falsify an idea rather than serve as the main method source. Prefer near-neighbor, far-neighbor, external-domain transfer, cross-lane recombination, or committed proposal-graph transfer as the primary method mechanism. Treat target-domain-only method variants as baselines or ablations unless a current-field absence audit is recorded.
- Do not mechanically import raw discovery results. Use `PAPER_SELECTION_SCORECARD.json` to reject duplicates, weak relevance, unresolved sources, survey noise, and generic benchmark papers; select roughly 60-80% of the high-signal eligible set, not raw results. Then convert selected usable papers into `GRAPH_IMPORT_PLAN.json` before requesting PaperNexus import/supplement/material views or split-reading evidence.
- Treat PaperNexus import as asynchronous queue work. Use `import_workflow queue_progress/status/wait` for every `GRAPH_IMPORT_PLAN` row with `import_action=import/supplement`, keep progressive batching enabled (`importBatchEnabled=true`, `importBatchInitialTasks=4`, `importBatchMaxTasks=16`, `importBatchProgressive=true`), and capture `IMPORT_WORKFLOW_STATUS.json` with planned/submitted/completed/authoritative-sync counts. A paper is graph-visible only after `status=completed`, `stage=completed`, and authoritative graph sync is complete or superseded; fast commit alone is not enough. Split-reading/material views can satisfy `material_view` rows only, never an `import`/`supplement` graph-import row.

## Pre-Idea Evidence Expansion Policy

Before `autoreskill-ideation-panel` may write `ideation/EXPERIMENT_IDEA_POOL.json`, this skill should provide or help capture:

- `.autoreskill/literature/PRE_IDEA_DISCOVERY_PLAN.json`
- `.autoreskill/literature/TARGET_DOMAIN_DISCOVERY_PACKET.json`
- `.autoreskill/literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json`
- `.autoreskill/literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json`
- `.autoreskill/papernexus/ABSTRACT_SCREENING_AUDIT.json`
- `.autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json`
- `.autoreskill/papernexus/GRAPH_IMPORT_PLAN.json`
- `.autoreskill/papernexus/IMPORT_WORKFLOW_STATUS.json` when PaperNexus import/supplement tasks are submitted or already queued
- `.autoreskill/papernexus/GRAPH_IMPORT_STATUS.json` only as a legacy compatibility artifact; prefer `IMPORT_WORKFLOW_STATUS.json`
- `.autoreskill/papernexus/SPLIT_READING_EVIDENCE_PACK.json`
- `.autoreskill/papernexus/proposal_graph_session.json` when `proposal_graph_session` is available
- `.autoreskill/papernexus/proposal_graph_sessions/<run_id>/proposal-session-manifest.json` when an output directory is supplied
- `.autoreskill/ideation/INNOVATION_SLOT_MAP.json`
- `.autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json`

Lane definitions:

- `target_domain`: closest priors, SOTA, baseline/protocol, dataset/metric, limitations/future work, negative evidence.
- `near_neighbor`: related but different directions that share task/evaluation pressure while changing mechanism, assumptions, or optimization route.
- `far_neighbor`: storyline and mechanism-transfer direction, using domain-agnostic challenge reformulation and external source-domain conceptual takeaways.

Method-source priority:

- `target_domain` supplies anchors: problem framing, closest-prior pressure, baseline/protocol norms, data/metric choices, and overlap-risk evidence.
- `near_neighbor` and `far_neighbor` supply candidate mechanisms, transfer bridges, external analogies, and failure-mode repairs for the main method.
- The selected top-tier method idea should record `primary_method_source_role`, `neighbor_transfer_mechanism`, `target_domain_anchor`, and `target_domain_method_overlap_risk` before experiment planning.

General breadth gate:

- The pre-idea gate must not pass only because each lane has one persisted attempt. Each lane needs enough screened candidates to show that Codex considered a small literature map, not only a single close prior.
- Default minimums are enforced by `scripts/pre_idea_breadth_lint.py`: target-domain at least 10 raw / 6 eligible / 4 selected candidates; near-neighbor at least 12 raw / 8 eligible / 5 selected candidates; far-neighbor at least 10 raw / 7 eligible / 4 selected candidates; total eligible at least 21 and total graph-import/split-read selected at least 13. The neighbor lanes are intentionally heavier because top-tier method novelty should normally come from transfer, recombination, or mechanism migration rather than target-domain-only variants.
- These are not venue-specific thresholds. A niche topic may pass with an explicit `breadth_exception_approval` or degraded gate, but the exception must name the sparse lane, the attempted expansion, and the claim limits.
- For manuscript writing, this breadth gate is still a minimum research scaffold, not a complete related-work section. Later writing/review stages may require a broader bibliography.

If keywords are insufficient, trigger another search round. Expansion is required when a lane has too few candidates, eligible ratio is low, source-resolvable count is low, role coverage is missing, near-neighbor results collapse into target duplicates, or far-neighbor results are generic and lack transferable mechanisms.

Use PaperNexus split-reading/material views rather than human-style full-paper reading. The evidence pack must cover closest prior, baseline/protocol, mechanism, limitation/future, and negative evidence before the pre-idea gate can pass. Sparse graph layers such as low `EvidenceLayer`, `FutureLayer`, or `MechanismLayer` counts are not a natural stopping point; actively request the missing roles when MCP capabilities support it. If import tasks are queued or authoritative sync is pending, record an async wait instead of downgrading to raw discovery evidence.

## Proposal Graph Idea Generation Policy

After `ideation/PRE_IDEA_EVIDENCE_GATE.json` passes, feature-detect and prefer:

```json
{
  "operation": "proposal_graph_session",
  "corpus": "<active corpus>",
  "project": "<autoreskill project id>",
  "problem": "<research problem>",
  "targetDomain": "<target domain>",
  "runId": "<stable run id>",
  "maxRounds": 5,
  "outputDir": "<project-root>/.autoreskill/papernexus/proposal_graph_sessions/<run_id>",
  "evidenceRefs": ["<evidence ids from split-reading pack and evidence cart>"],
  "evidenceExport": {"source": "pre_idea_split_reading_and_slot_map"}
}
```

The proposal graph session is episode-local and must not mutate the raw corpus graph. A usable result has `final_status="committed"`, a `committed_subgraph_id`, `proposal.md`, `proposal.json`, `proposal-graph.json`, `role-action-trace.jsonl`, `edit-decisions.jsonl`, `commit-decisions.jsonl`, `validation-report.json`, `evidence-export.json`, and `proposal-session-manifest.json`. Capture the MCP result as `papernexus/proposal_graph_session.json` and keep the run artifacts under `papernexus/proposal_graph_sessions/<run_id>/`.

If the session returns `diagnosis` instead of `committed`, do not silently fall back to raw brainstorming. Record the commit blockers, repair missing evidence/actions when policy permits, and only use legacy `idea_catalyst` or `research_controller` as a fallback with an explicit evidence boundary.

## Evidence Maturity Policy

Do not treat the pre-idea gate as a novelty certificate or launch approval. After the pre-idea gate passes, individual ideas may still have maturity labels and evidence debt. The selected idea still needs hard source-backed closure in `autoreskill-experiment-plan`.

Use these maturity labels during ideation:

- `blue_sky`: plausible paper hypothesis, mostly brainstormed, evidence weak.
- `promising`: clear mechanism and experiment path, but novelty/baseline evidence still incomplete.
- `evidence_backed`: backed by PaperNexus or literature evidence ids, but not yet launch-ready.
- `plan_ready`: selected idea has enough source-backed novelty, baseline, protocol, and falsifier evidence for experiment planning.

For each ideation candidate, attach lightweight evidence notes when available:

- `evidence_maturity`
- `papernexus_hints`
- `missing_materials`
- `followup_evidence_plan`

At ideation time, produce `papernexus/LITERATURE_DISCOVERY_TRIAGE.json`, `papernexus/ABSTRACT_SCREENING_AUDIT.json`, `papernexus/PAPER_SELECTION_SCORECARD.json`, `papernexus/GRAPH_IMPORT_PLAN.json`, and `papernexus/IMPORT_WORKFLOW_STATUS.json` from discovery and import-workflow packets. The abstract audit proves that each merged discovery candidate was considered at abstract level, or explicitly marked as no-abstract metadata fallback. The scorecard must identify which discovered papers should be imported, supplemented, split-read, watched, or rejected before idea generation for novelty risk, baseline candidates, negative evidence, dataset/benchmark anchors, method lineage, limitations/future work, and transfer bridges. The graph import plan is the handoff into PaperNexus import/material work and must include a hard `required_graph_import_keys` list for `import`/`supplement` rows; raw discovery candidates must not be used directly as graph evidence.

Before a selected idea can enter `experiment_plan`, collect:

- target prior
- near-source method
- far-source story and domain distance
- bridge mechanism
- primary method source role, preferably near/far-neighbor or cross-lane transfer rather than target-domain-only
- target-domain method overlap risk and current-field absence evidence when needed
- negative evidence or absence confidence
- novelty risk
- baseline norms
- experiment cost norms
- falsifier pilot

Write materials under `.autoreskill/papernexus/` and evidence ids to `.autoreskill/evidence_cart.jsonl`.

This skill supplies source-backed evidence and PaperNexus material packs. It must not substitute a small set of high-level directions for the experiment idea pool, and it must not force every brainstormed idea to be launch-ready. The 12-15 optimization ideas are produced during ideation by `autoreskill-ideation-panel` as `.autoreskill/ideation/EXPERIMENT_IDEA_POOL.json`, using `INNOVATION_SLOT_MAP.json` as the direct input. Hard selected-idea evidence closure still moves to `autoreskill-experiment-plan`.

When a committed proposal graph session exists, `INNOVATION_SLOT_MAP.json` remains the evidence-slot input, while the proposal bundle becomes the primary PaperNexus idea seed and critique trace. Ideation should expand, vary, and score around the committed proposal instead of treating `idea_fragments` as the highest-authority idea source.

## Deterministic Helpers

After Codex calls PaperNexus MCP tools, persist the observations:

```bash
python scripts/papernexus_probe_record.py --project <project-root> --callable true --corpus <corpus> --operation research_material_pack --operation source_discovery_plan --operation proposal_graph_session
python scripts/papernexus_feature_matrix.py --project <project-root> --callable unknown --operation research_material_pack --operation research_controller --operation proposal_graph_session
python scripts/pre_idea_discovery_plan.py --project <project-root> --topic "<topic>" --target-domain "<domain>"
python scripts/papernexus_artifact_capture.py --project <project-root> --kind research_material_pack --input <mcp-result.json> --stage frontier_mapping --evidence-note "PaperNexus material pack evidence" --tag papernexus
python scripts/papernexus_artifact_capture.py --project <project-root> --kind literature_discovery_packet --input <literature-discovery-search-result.json> --stage ideation --source papernexus-remote.literature_discovery --evidence-note "Ideation broad metadata-only literature discovery" --tag ideation --tag literature_discovery
python scripts/discovery_metadata_triage.py --project <project-root> --input literature/LITERATURE_DISCOVERY_PACKET.json --stage ideation
python scripts/abstract_screening_audit_lint.py --project <project-root>
python scripts/paper_selection_scorecard_lint.py --project <project-root>
python scripts/pre_idea_breadth_lint.py --project <project-root>
python scripts/graph_import_plan_lint.py --project <project-root>
python scripts/papernexus_artifact_capture.py --project <project-root> --kind import_workflow_status --input <import-workflow-queue-or-wait-result.json> --stage ideation --source papernexus-remote.import_workflow --tag ideation --tag import_workflow
python scripts/import_workflow_status_lint.py --project <project-root>
python scripts/split_reading_evidence_pack_lint.py --project <project-root>
python scripts/papernexus_artifact_capture.py --project <project-root> --kind proposal_graph_session --input <proposal-graph-session-result.json> --stage ideation --source papernexus-remote.agent_materials --evidence-note "Committed PaperNexus proposal graph full-paper idea bundle" --tag ideation --tag proposal_graph --tag source_backed
python scripts/proposal_graph_session_lint.py --project <project-root>
python scripts/papernexus_artifact_capture.py --project <project-root> --kind idea_catalyst_evidence_export --input <idea-catalyst-result.json> --stage ideation --source papernexus-remote.idea_catalyst --evidence-note "Idea Catalyst evidence export" --tag ideation
python scripts/idea_support_lint.py --project <project-root>
python scripts/evidence_status_lint.py --project <project-root>
```

`idea_support_lint.py` is the hard gate for source-backed selected idea fragments at experiment planning time. It must pass before `autoreskill-experiment-plan` treats `INNOVATION_PACKET.json` as stage-complete, but it must not be used to suppress broad ideation candidates.

If the MCP call fails, record the transport/auth/session failure with `papernexus_probe_record.py --callable false --error "<reason>"` and do not continue with local PaperNexus substitutes.

Read `references/papernexus_mcp_policy.md`, `references/mcp_call_templates.md`, `references/innovation_packet_schema.md`, and `references/negative_evidence_protocol.md`.
