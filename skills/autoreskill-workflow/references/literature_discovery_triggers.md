# Literature Discovery Triggers

PaperNexus literature discovery is a recurring evidence repair action across the
workflow. Use this file to decide when discovery or material repair is needed.
Use `stage_contracts.md` for completion, `async_wait_policy.md` for heartbeat
cadence, and PaperNexus child skills for concrete tool configuration.

Discovery is a recall step only. Raw discovery results may prove that a search
was attempted; they do not support novelty, baseline, mechanism, limitation, or
citation claims until usable papers are screened and graph/material evidence is
captured.

Paper-code surveys can extend discovery when the task asks for repository
analysis, source-code mechanisms, or innovation migration. They do not replace
PaperNexus/literature evidence. Use `paper_code_innovation_transfer.md` for that
audit chain.

For broad or long-running discovery/import work, prefer server-side submit plus
progress/report polling so state survives MCP client timeouts. If a submitted run
or graph import is still active, persist the progress snapshot, queue async wait,
and let `goal_tick.py` return a heartbeat recommendation. Graph import waits use
the adaptive policy in `async_wait_policy.md`, not a universal fixed cadence.

| Stage | Trigger discovery when | Preferred output |
| --- | --- | --- |
| `topic_search` | no broad discovery packet, topic is underspecified, corpus scope is unclear, keywords are too narrow, or raw results have not been screened | discovery packet, triage, paper selection scorecard, graph/material plan |
| `graph_build` | graph decision is not source-backed, required imports are unsubmitted/incomplete/unsynced, source-limited rows lack exhaustion records, or material-view rows lack material routing | source discovery plan, graph import plan, import workflow status, graph build decision |
| `frontier_mapping` | gap, limitation, failure mode, transfer source, negative evidence, or experiment/cost norm is missing | research material pack or challenge/transfer materials |
| `literature_review` | SOTA matrix, gap synthesis, citation queue, baseline/dataset/metric anchors, target-venue coverage, or requested paper-code survey coverage is incomplete | SOTA matrix, gap synthesis, citation queue, and survey artifacts when in scope |
| `ideation` | target-domain, near-neighbor, or far-neighbor lanes miss breadth, screening, source resolvability, import/material closure, transferable mechanisms, or code-migration evidence | lane discovery packets, screening, graph/material artifacts, split-reading pack, and migration matrix when in scope |
| `idea_gate` | selected ideas have unresolved closest-prior comparison, overlap risk, negative evidence, weak transfer bridge, or unsupported novelty score | selected-idea follow-up evidence and updated decision ledger refs |
| `experiment_plan` | selected idea is below `plan_ready`, evidence import/material gate is blocked, protocol norms are not source-backed, or track planning exposes lifecycle/evidence mismatch | evidence refs in planning packets and track plan matrix |
| `code` | implementation reveals the locked baseline/protocol/dataset choice was unsupported by literature evidence | planning repair packet, not ad hoc code-stage search |
| `experiment` | terminal negative/regressed/budget-stopped/spec-violating results need literature-backed mechanism diagnosis, negative evidence, or structural replacement ideas | failure-mode evidence routed to decision ledger or planning repair |
| `analysis` | claims are unsupported, results contradict the expected mechanism, ablations expose confounds, or failed ideas need source-backed limitation framing | claim-evidence repair and updated outcome summary |
| `review_pressure` | reviewer findings mention novelty, related work, baselines, citations, threat models, protocol norms, or unsupported significance | targeted discovery and updated findings |
| `writing` | related work has placeholders, claims lack citation ids, closest-prior contrast is weak, or citation queue is unresolved | citation queue updates, related-work evidence, and bibliography entries |
| `submission_ready` | citation lint, bibliography, venue claims, or front-matter evidence checks fail | final citation/corpus verification before readiness |

Default policy:

- Start broad and metadata-only for ideation lanes; import, supplement, and
  split-read only after candidate triage.
- Account for every merged discovery candidate in `ABSTRACT_SCREENING_AUDIT.json`
  or an equivalent screening artifact.
- Reject duplicates, weak relevance, unresolved sources, survey noise, and
  generic benchmark-only papers before graph/material work.
- Prefer targeted follow-up discovery after idea selection, analysis, review, and
  writing.
- Record each submit/report/search attempt, failed attempt, import/material
  queue, and degraded boundary.
- Failed, parked, killed, or candidate-only ideas must remain visible in
  `IDEA_DECISION_LEDGER.json` and `IDEA_OUTCOME_SUMMARY.json`. They may support
  pruning, limitations, future work, or claim downgrade, but not stable
  improvement claims.
