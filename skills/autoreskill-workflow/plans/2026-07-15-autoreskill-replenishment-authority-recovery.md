# AutoResearch Replenishment Authority Recovery ExecPlan

Created: 2026-07-15 10:20 CST
Updated: 2026-07-15 11:06 CST
Target repository: `<runtime-skill-root>/autoreskill-workflow`
Target branch / worktree: runtime skill tree, then strict-file sync to `<local-skill-pack-checkout>`
Related docs:
- `<runtime-skill-root>/execplan-builder/SKILL.md`: requires a self-contained living ExecPlan, pre-implementation audit, recovery model, and executable acceptance checks.
- `<runtime-skill-root>/autoreskill-workflow/SKILL.md`: current workflow authority, bounded candidate replenishment, heartbeat, and scientific decision rules.
- `<runtime-skill-root>/autoreskill-workflow/references/program_claim_contract.md`: current program claim contract and bounded search-budget rules.
- `<runtime-skill-root>/autoreskill-workflow/references/scientific_decision_loop.md`: current outcome-to-route and replenishment lifecycle.

This ExecPlan is a living document. Update `Progress`, `Surprises & Discoveries`, `Decision Log`, `Artifacts and Notes`, and `Outcomes & Retrospective` as the work proceeds.

Implementers should proceed milestone by milestone without asking for generic next steps unless blocked by missing authority, unsafe side effects, or a concurrent writer changing the same runtime files.

No repository-level `PLANS.md` governs the runtime skill tree. This plan follows the local `execplan-builder` content contract directly.

## Purpose / Big Picture

After completion, an AutoResearch project whose current scientific track has been validly refuted can automatically recover its candidate supply when all of the following are true: the route is terminal for the old track but not for the project, the user has explicitly authorized a bounded replenishment budget, a reviewed changed-basis replacement contract can be constructed, and the workflow is `full_auto_bounded` for a paper-producing goal.

The observable behavior is:

- `goal_tick.py` no longer converts an already-authorized replacement route into an indefinite `hard_stop`.
- It queues one idempotent local repair packet that constructs or validates the replacement contract, activates a new program revision, authorizes one replenishment transaction, and generates a newly bound candidate supply.
- Old scientific evidence remains in history. The old route's `refuted` status does not leak into the new unresolved program revision.
- `monitor_only` rows and stale project-local GPU snapshots do not block CPU-only candidate construction.
- A missing explicit authorization, exhausted budget, or route marked `terminal_for_project=true` still stops safely.

The proof consists of fixture tests, read-only CLI checks, event/ledger traces, and documentation that distinguishes user authorization from current-contract allocation and transaction consumption.

Current problem:

- The user manually authorized `max_targeted_replenishments=8`. The current code can validate this integer but cannot complete the scientific lifecycle transition that makes it usable after the prior program contract is superseded.
- The workflow currently conflates an old route's terminal scientific status, a current contract's search allocation, and a replenishment transaction. Updating only the integer leaves the old `program_scientific_status=refuted` in force.
- `goal_tick.py` contains a special-case gate that recognizes `budget_authorized_pending_replacement_contract_review` but always returns `hard_stop`; it does not create the reviewed replacement-contract repair packet.
- `research_decision.py` incorrectly counts `launch_mode=monitor_only` queue rows as decision-bearing, requires fresh idle GPU capacity for local idea construction, and rejects legacy projects whose missing goal scope should resolve to the documented paper defaults.

## Progress

- [x] 2026-07-15 10:12 CST Re-read the current GCD project control plane, current runtime workflow scripts, contract validator, goal state defaults, documentation, and existing fixtures.
- [x] 2026-07-15 10:18 CST Reproduced the current failure with a read-only `research_decision.py --replenishment --check`; the active replacement contract still fails on old `refuted` status, stale fillable supply, `monitor_only` rows, missing fresh capacity, and missing goal scope.
- [x] 2026-07-15 10:20 CST Drafted and audited this implementation plan before code changes.
- [x] 2026-07-15 10:50 CST Implemented program-recovery status, replacement authority validation, and program-revision activation.
- [x] 2026-07-15 10:51 CST Integrated the route into `goal_tick.py` with recovery-safe, local-only job packets.
- [x] 2026-07-15 11:01 CST Added nine focused fixture cases; Python compilation and all four named regression suites pass.
- [x] 2026-07-15 11:02 CST Updated the workflow and public reference contracts.
- [x] 2026-07-15 11:04 CST Synced only the 14 changed files to the dirty local GitHub mirror; `git diff --check`, mirror compilation, and the focused fixture pass.
- [x] 2026-07-15 11:05 CST Recorded outcomes, residual project-local work, and final audit evidence in this plan.
- [x] 2026-07-15 11:06 CST Published this plan to the Wiki as `92-autoreskill-replenishment-authority-recovery-execplan.md`.

## Surprises & Discoveries

- Observation: the user's value `8` is now present in an active, enforced replacement contract, but the ledger still describes the old route as `refuted`.
  Evidence: a representative active project had `PROGRAM_CLAIM_CONTRACT.json` revision 4 with `max_targeted_replenishments=8`; `IDEA_DECISION_LEDGER.json` still had `program_scientific_status=refuted` and a prior program-route identifier.
  Action: introduce an explicit program-revision activation transaction instead of interpreting a contract edit as an implicit scientific reset.

- Observation: an existing intervention artifact already preserves direct user authority with `authorization.source=direct_user_instruction` and cap `8`.
  Evidence: GCD `control/REPLENISHMENT_INTERVENTION_REQUEST.json`.
  Action: standardize and validate this artifact; do not create a second budget authority in `autopilot_policy.json`.

- Observation: the replacement contract was manually drafted and role-reviewed by the active project task, proving the scientific review can be represented as local artifacts without launching experiments.
  Evidence: `PROGRAM_CLAIM_CONTRACT_REPLACEMENT_DRAFT_20260715.json`, `UNRESOLVED_PAPER_DECISION_20260715.json`, and `PROGRAM_CLAIM_CONTRACT_REPLACEMENT_REVIEW_20260715.json`.
  Action: make these artifact roles and hash bindings part of the recovery packet and commit gate.

- Observation: GPU availability is relevant to materialized experiment launch, not to changed-basis candidate generation or contract review.
  Evidence: current failure includes `no_fresh_idle_capacity_or_controller_request` even though the blocked work is local planning.
  Action: remove the GPU-capacity prerequisite from replenishment authorization; retain resource fitting at experiment admission/launch.

- Observation: the initial plan required candidate recovery to generate `IDEA_TRACK_SEEDS.json` while also forbidding primary selection.
  Evidence: the track-seed schema requires exactly one primary; the two requirements cannot both hold.
  Action: end recovery at a revision-bound pool and scorecard shortlist. Primary selection, track seeds, admission, and experiments belong to the next lifecycle action.

- Observation: after selection, the canonical scorecard may narrow below the original 3-5 replenishment shortlist even though the replenishment event retains the audited preselection counts.
  Evidence: live GCD records 10 cards and four shortlisted candidates in its first event, then narrows the canonical scorecard to primary plus alternate.
  Action: require canonical pool/scorecard revision bindings, but accept shape evidence from the current-revision event after downstream selection. Never regenerate or charge a second transaction merely because the canonical shortlist was consumed.

## Decision Log

- Decision: keep the default contract allocation at one replenishment; accept values from zero through eight only when explicitly recorded in the project contract.
  Rationale: eight is this project's user-authorized cap, not a safe global default.
  Date/Author: 2026-07-15 / Codex

- Decision: use `REPLENISHMENT_INTERVENTION_REQUEST.json` as the durable exceptional authorization artifact instead of adding a duplicate cap to `autopilot_policy.json`.
  Rationale: the artifact already exists, names the terminal route, records direct user authority, and avoids conflicting authorities.
  Date/Author: 2026-07-15 / Codex

- Decision: add an explicit program-revision activation transaction to `research_decision.py`.
  Rationale: replacing a contract must archive the old route and reset only the current program state; silently overwriting `refuted` would erase evidence, while leaving it unchanged blocks every new candidate.
  Date/Author: 2026-07-15 / Codex

- Decision: use one recovery action, `recover_replenishment_route`, with deterministic phases rather than separate unrelated repair actions.
  Rationale: a single action can resume safely after draft, commit, activation, or candidate-generation interruption and avoids stale repair packets fighting each other.
  Date/Author: 2026-07-15 / Codex

- Decision: exclude `monitor_only`, `monitor_sync`, and `resource_fill_diagnostic` rows from decision-bearing supply checks.
  Rationale: these rows report or preserve backend state; they do not answer the unresolved paper decision.
  Date/Author: 2026-07-15 / Codex

- Decision: candidate supply means the pool and scorecard shortlist, both bound to the active program revision; track seeds are downstream selection authority.
  Rationale: an old shortlist can be valid evidence but cannot fill a changed-basis portfolio slot under a new claim contract, while requiring track seeds here would force an unauthorized primary selection.
  Date/Author: 2026-07-15 / Codex

## Outcomes & Retrospective

Actual outcome:

- `program_claim_contract.py` now rejects replacement commits without matching direct authority, basis lineage, unresolved decision, authorized cap, and semantic-hash-bound approval.
- `research_decision.py` now distinguishes authorization, allocation, and per-revision consumption; archives and activates program revisions; excludes monitor-only rows; removes GPU gating from candidate construction; and resumes an existing event without a second charge.
- `goal_tick.py` routes one resumable `recover_replenishment_route` packet instead of an indefinite hard stop. The packet has no resource calls and stops before primary selection, track seeds, admission, or launch.
- The focused suite passes ten positive, negative, authority, idempotence, compatibility, and lifecycle cases. Python compilation plus closed-loop, next-actions, innovation-throughput, and multi-track regression suites all pass.
- Read-only live GCD checks validate the user's cap of eight and report the precise remaining projection repair: its first event already records 10 cards and four shortlisted candidates, while the canonical pool and scorecard still lack the active revision bindings. No second event is proposed.

Remaining gaps:

- The active GCD writer still needs to add `program_revision_id` and `program_claim_contract_sha256` to its canonical pool and scorecard. This is project-state reconciliation, not a workflow-code gap; this task intentionally did not mutate that concurrently written project.
- Older replacement projects without direct intervention/review lineage remain stopped rather than being guessed or migrated automatically.

Lessons for future harness:

- Numeric budget edits are not lifecycle transitions. Every exceptional search route needs explicit authority, allocation, consumption, and revision state.
- Candidate supply and candidate admission are different ownership boundaries. Requiring track seeds during supply construction silently forces primary selection and must be avoided.
- Durable event summaries should preserve preselection pool/shortlist shape so downstream narrowing cannot look like a need for another replenishment.

## Context and Orientation

### User-Visible Outcome

Scenario: an active method is validly negative on the required datasets. Its route says `terminal_for_track=true` and `terminal_for_project=false`. The current contract is superseded, the user authorizes up to eight changed-basis replenishment transactions, and the project remains a bounded paper-producing workflow.

Expected behavior: the next bounded tick creates or resumes one local recovery repair. The repair does not launch GPUs. It verifies the authorization, writes an unresolved paper decision, drafts and role-reviews a changed-basis replacement contract, commits it by compare-and-swap, activates a new program revision while archiving the old route, authorizes one replenishment event, and generates a current-revision-bound pool of 8-12 cards with a 3-5 candidate shortlist. A later tick owns primary selection, track seeds, admission, packet materialization, and experiment launch.

Observed result: `goal_tick.py` emits `queued_repair_handoff` or `dispatch_repair` with action `recover_replenishment_route`; after successful execution, `research_decision.py --replenishment --check` either reports an unchanged-basis idempotent stop or reports the next legitimate transaction state, rather than old-route contamination.

### Current State Snapshot

- `<runtime-skill-root>/autoreskill-workflow/scripts/research_decision.py`: owns scientific decision and replenishment ledger mutations. It currently lacks program-revision activation.
- `<runtime-skill-root>/autoreskill-workflow/scripts/program_claim_contract.py`: owns structural contract validation and CAS updates. It accepts 0-8 replenishments but does not validate replacement authority artifacts.
- `<runtime-skill-root>/autoreskill-workflow/scripts/goal_tick.py`: owns atomic workflow routing and repair packet generation. Its current idea-gate replacement-contract block hard-stops even after budget authorization.
- `<runtime-skill-root>/autoreskill-workflow/scripts/goal_state.py`: owns defaults; it does not currently emit `allow_autonomous_candidate_replenishment` explicitly.
- `<runtime-skill-root>/autoreskill-workflow/tests/run_closed_loop_research_fixtures.py`: covers active-contract one-event replenishment but not superseded-contract recovery.
- GCD read-only check: active replacement contract and budget `8`, but replenishment fails with `program_scientific_status_terminal`, stale/fillable rows, missing resource capacity, and legacy scope errors.

Existing capabilities:

- Contract CAS writes and semantic hashes.
- A decision ledger lock and atomic JSON writes.
- Bounded, basis-hashed replenishment events.
- Repair queue deduplication, stale repair supersession, and job packet rendering.
- Existing role-separated scientific review artifacts and claim ceilings.

Known gaps:

- No program generation/revision identity in the ledger.
- No transaction to archive an old route and establish a new unresolved program state.
- No validation that a replacement contract's budget is covered by direct authority.
- Candidate supply is not bound to a program revision.
- Local candidate construction is incorrectly resource-gated.
- The goal tick recognizes but cannot execute the recovery route.

Known constraints and dirty-worktree risks:

- The runtime skill tree is not the Git checkout. Changes must be validated there, then copied through an explicit allowlist into the dirty mirror.
- The mirror contains many unrelated user changes and untracked files; no cleanup, reset, or broad sync is allowed.
- The GCD task is an active concurrent writer. This implementation must not mutate its `.autoreskill` state or run `goal_tick.py` against it.
- No remote jobs, GPU reservations, cancellations, or destructive operations are in scope.

### Terms and System Map

- User authorization: direct authority to permit a bounded exceptional search budget. It is recorded in `control/REPLENISHMENT_INTERVENTION_REQUEST.json` and cannot be inferred from idle GPUs.
- Contract allocation: `PROGRAM_CLAIM_CONTRACT.search_budget.max_targeted_replenishments`; the maximum transactions available to one active program contract.
- Replenishment transaction: one basis-hashed event in `IDEA_DECISION_LEDGER.replenishment_events` that authorizes one new changed-basis candidate-generation round.
- Program revision: one active claim contract and unresolved paper decision. A replacement revision may inherit evidence but not the old revision's terminal status or stale shortlist.
- Candidate supply binding: `program_revision_id` and `program_claim_contract_sha256` attached to the generated pool and scorecard. Track seeds are generated only after a later primary-selection decision and retain their existing contract binding.
- Decision-bearing row: a queue row that can resolve the current scientific decision. Monitor-only and resource diagnostics are not decision-bearing.

## Scope

This plan includes:

- Replacement authorization validation and contract commit guards.
- Program-revision identity, activation, archival, and idempotence.
- Correct replenishment basis/counting and stale supply detection.
- Goal-tick routing and recovery job packet behavior.
- Explicit default autonomy policy and docs.
- Focused fixtures plus relevant regression suites.
- Strict-file sync to the local GitHub mirror; no push unless separately requested.

## Non-Goals

This plan does not include:

- Changing the user's GCD project state while its active task is writing.
- Automatically choosing `8` for other projects or increasing any budget without direct authority.
- Launching, cancelling, or rescheduling experiments.
- Replacing the existing queue, ledger, contract, lease, or review artifact systems.
- Proving that any generated candidate is novel or effective; recovery only restores a bounded supply path.
- Rewriting old evidence or deleting old candidate pools.

## Non-Negotiable Rules

1. Old negative evidence and route decisions remain auditable in history; only the active program view is reset.
2. A new program revision is activated only for an active/enforced replacement contract whose basis decision matches a non-project-terminal old route and whose budget is covered by explicit authority.
3. `max_targeted_replenishments=0` is a deliberate stop and must never be silently raised.
4. The global default remains one transaction and the validator hard maximum remains eight.
5. Recovery performs no remote/GPU side effects. Experiment admission and launch retain their existing resource gates.
6. `monitor_only`, `monitor_sync`, and `resource_fill_diagnostic` rows cannot block candidate supply.
7. Legacy missing `goal_type` and `claim_mode` use the documented paper defaults and emit migration warnings; invalid explicit values remain ineligible.
8. Every mutation is locked, atomic, basis-hashed, and idempotent.
9. The GCD live project is used only for read-only diagnosis; all write validation uses temporary fixtures.

## Authority / Evidence Model

Direct authority:

- `autopilot_policy.json`: whether autonomous candidate replenishment is allowed and whether the workflow is `full_auto_bounded`.
- `control/REPLENISHMENT_INTERVENTION_REQUEST.json`: exceptional user-authorized cap and the old route decision it applies to.
- `orchestrator/PROGRAM_CLAIM_CONTRACT.json`: current program allocation, claim scope, datasets, stop rules, and scientific ceilings.
- `ideation/IDEA_DECISION_LEDGER.json`: active program revision, historical route decisions, transaction consumption, and current scientific status.

Evidence only:

- `SCIENTIFIC_OUTCOME.json`, cross-dataset decisions, queue/backend observations, and review reports support a decision but do not independently change current authority.
- Idle GPU observations may fit an experiment row but cannot authorize candidate search or contract replacement.

State transition:

    terminal scientific evidence
      -> program route decision (track terminal, project nonterminal)
      -> explicit user replenishment authorization
      -> unresolved paper decision + reviewed replacement contract
      -> CAS contract commit
      -> locked program-revision activation and old-route archival
      -> one basis-hashed replenishment transaction
      -> current-revision-bound candidate supply
      -> later admission/materialization/launch

## Plan of Work

### Phase 0: Context and Contract Inventory

Goal:
- Freeze the observed failure and authority boundaries before editing.

Edits:
- This ExecPlan only.

Validation:
- Re-run read-only GCD contract, intervention, ledger, queue, and replenishment checks.
- Confirm no project file changes were made.

Risks:
- A concurrent task can advance GCD state while the plan is implemented.

Artifacts:
- This plan records timestamps and evidence instead of relying on the conversation.

### Phase 1: Replacement Authority and Program Revision

Goal:
- Add the smallest complete scientific lifecycle transaction that separates old terminal evidence from a new unresolved program.

Edits:
- `scripts/program_claim_contract.py`: validate replacement-contract lineage and direct authorization at commit time; preserve structural-only draft checks.
- `scripts/research_decision.py`: add recovery status, decision-bearing row filtering, program-revision activation, per-revision event counting, current-revision candidate supply binding, default paper scope fallback, and removal of the idea-generation GPU gate.
- `scripts/goal_state.py`: make autonomous candidate replenishment explicit in new project defaults.

Validation:
- A fixture with an authorized cap of eight and a project-nonterminal old route can activate a replacement revision.
- A missing authorization, cap zero, mismatched basis, unapproved review, or project-terminal old route cannot activate.
- Repeating activation is idempotent and does not duplicate history.

Risks:
- Resetting too much could erase scientific history; resetting too little could preserve stale authority.

Artifacts:
- Ledger `program_revision_history`, `active_program_revision`, and revision-tagged replenishment events.

### Phase 2: Goal-Tick Recovery Harness

Goal:
- Convert the recognized but inert idea-gate block into one resumable local repair route.

Edits:
- `scripts/goal_tick.py`: replace the hard-coded hard stop with recovery status classification, stale-repair supersession, and a `recover_replenishment_route` packet.
- The packet performs at most three dependency-ordered phases: reviewed contract construction/commit; program-revision activation; one replenishment authorization plus candidate supply generation.
- Candidate generation must bind the pool and scorecard to the active revision. It must not select a primary, generate track seeds, admit tracks, or launch jobs.

Validation:
- First tick queues the recovery repair.
- A repeated tick reuses the same failure signature or dispatches the existing due repair, rather than creating duplicates.
- After a partially completed contract commit, the next packet resumes at activation instead of rebuilding authority.
- Without authority, the result remains a clear hard stop.

### Phase 3: Regression and Documentation

Goal:
- Prove compatibility and make the authority model discoverable.

Edits:
- Add `tests/run_replenishment_recovery_fixtures.py` with focused positive, negative, idempotence, stale-supply, and monitor-only cases.
- Update `SKILL.md`, `references/program_claim_contract.md`, `references/scientific_decision_loop.md`, `references/experiment_next_actions.md`, `references/async_wait_policy.md`, `references/goal_state_schema.md`, `references/command_surface.md`, and the autonomy policy schema only where the behavior is public.
- Sync only changed files to the dirty local Git mirror.

Validation:
- Python compilation.
- Focused fixture.
- Existing closed-loop, next-actions, innovation-throughput, and multi-track fixture suites.
- Documentation searches show no remaining claim that fresh idle GPU slots are required for candidate replenishment.
- `git diff --check` passes in the mirror.

## Implementation Slices

- Slice: replacement authority guard
  Files: `scripts/program_claim_contract.py`
  Acceptance: unauthorized or over-cap replacement commit fails; reviewed authorized commit succeeds.

- Slice: program revision transaction
  Files: `scripts/research_decision.py`
  Acceptance: old route is archived exactly once, current status becomes unresolved, and event consumption is per revision.

- Slice: bounded recovery routing
  Files: `scripts/goal_tick.py`, `scripts/goal_state.py`
  Acceptance: authorized idea-gate recovery queues one local packet; unauthorized recovery hard-stops.

- Slice: regression harness and public contract
  Files: focused fixture and listed Markdown references
  Acceptance: all relevant tests pass and docs match the tested behavior.

## Agent Contract: WorkflowGuard Recovery Packet

Purpose:
- Restore a bounded changed-basis candidate supply after an old scientific program is terminal for its track but not for the project.

Owns:
- Local authority validation, replacement-contract artifacts, program-revision activation, one replenishment transaction, and candidate supply generation.

Does not own:
- GPU scheduling, experiment launch, candidate admission, claim promotion, paper writing, or user-budget expansion.

Inputs:
- Current goal state and autonomy policy.
- Old route decision and negative evidence references.
- Replenishment intervention authorization.
- Current/superseded contract and replacement review artifacts.

Outputs:
- Reviewed active replacement contract, active program revision, archived old route, one ledger event, and revision-bound pool/scorecard shortlist.

Tools:
- `program_claim_contract.py`, `research_decision.py`, existing ideation panel linters/generators, and local file/hash tools.

Guardrails:
- No remote jobs; no inferred cap; no restoration of refuted causal signatures; no admission or launch; no claim effect.

Eval cases:
- Authorized recovery, unauthorized recovery, project-terminal route, over-cap contract, partial recovery resume, duplicate tick, stale old shortlist, and monitor-only queue rows.

## Tool Contract: program_claim_contract.py replacement commit

Capability:
- CAS-commit a replacement claim contract only when its lineage and exceptional budget are authorized and role-reviewed.

Input schema:
- Active/enforced contract with `replacement_basis_decision_id`, source references to an unresolved paper decision, intervention authorization, and replacement review.

Side effects:
- Atomic contract replacement and append-only contract event.

Idempotency:
- Existing semantic SHA returns unchanged; stale expected SHA/revision fails.

Error model:
- Structured CLI error for missing authority, basis mismatch, cap mismatch, missing/incorrect review hash, or invalid contract.

Audit:
- Contract event stores prior/current hashes and revision.

Mock / eval:
- Temporary-project fixture; never commit against the live GCD project during this task.

## Tool Contract: research_decision.py program revision activation

Capability:
- Archive an old project-nonterminal route and bind the ledger to a reviewed replacement contract.

Input schema:
- Active replacement contract, matching old route, direct authorization, existing old-revision selection if any, and approved replacement evidence.

Side effects:
- Atomic ledger update, append-only decision log, and reconciliation marker.

Idempotency:
- Current matching `active_program_revision` returns success without duplicate history.

Error model:
- Refuses project-terminal route, mismatched basis, invalid authority/review, decision-bearing live work, or non-active contract. Any old-revision selection is archived and quarantined.

Audit:
- `program_revision_history`, `active_program_revision`, and decision log action.

Mock / eval:
- Temporary-project positive and negative fixtures.

## Concrete Steps

Run from `<runtime-skill-root>/autoreskill-workflow`:

    python3 -m py_compile scripts/program_claim_contract.py scripts/research_decision.py scripts/goal_tick.py scripts/goal_state.py
    python3 tests/run_replenishment_recovery_fixtures.py
    python3 tests/run_closed_loop_research_fixtures.py
    python3 tests/run_experiment_next_actions_fixtures.py
    python3 tests/run_innovation_throughput_fixtures.py
    python3 tests/run_multi_track_parallelism_fixtures.py

Then run read-only checks against GCD only after confirming no project-control lease/write action is invoked:

    python3 scripts/research_decision.py --project '<GCD-root>' --replenishment --check
    python3 scripts/research_decision.py --project '<GCD-root>' --program-recovery-status --check

Sync the strict allowlist into the mirror and validate:

    git -C '<mirror-root>' diff --check -- <changed allowlist>
    git -C '<mirror-root>' status --short -- <changed allowlist>

Expected:

- Focused fixtures report every case `ok`.
- Existing suites remain green.
- The GCD read-only status explains the current recovery phase without mutating it.
- No remote command or experiment submission occurs.

## Validation and Acceptance

This ExecPlan is complete when:

- [x] An explicitly authorized superseded-contract route produces `recover_replenishment_route`, not an indefinite hard stop.
- [x] The replacement contract commit is rejected when direct authorization or review hash binding is absent.
- [x] Program activation archives the old route exactly once and creates a new unresolved active revision.
- [x] Old `refuted` status cannot block the new revision and cannot be erased from history.
- [x] `monitor_only` and resource diagnostics do not count as decision-bearing rows.
- [x] Local candidate replenishment does not require a fresh GPU snapshot.
- [x] Legacy missing goal scope uses documented defaults with a warning.
- [x] A stale old shortlist cannot fill the new program revision.
- [x] Event budget consumption is revision-scoped and duplicate basis is rejected.
- [x] Missing authority, zero/exhausted cap, or project-terminal route remains a hard stop.
- [x] Focused and regression fixture suites pass.
- [x] Public docs and local mirror match the runtime implementation.
- [x] `Outcomes & Retrospective` records actual results.

## Idempotence and Recovery

Repeatable commands:

- `program_claim_contract.py check`: read-only and repeatable.
- `program_claim_contract.py commit` with expected SHA/revision: CAS-protected and idempotent for identical semantic content.
- `research_decision.py --activate-program-revision --check`: read-only proposal.
- `research_decision.py --activate-program-revision --write`: locked; repeated matching activation does not duplicate history.
- `research_decision.py --replenishment --write`: basis-hashed; unchanged basis cannot consume a second transaction.
- `goal_tick.py`: lease-protected; repair signatures and obsolete-job checks prevent duplicate recovery packets.

Checkpoint / ledger / manifest:

- `orchestrator/program_claim_contract_events.jsonl`: contract mutation history.
- `ideation/IDEA_DECISION_LEDGER.json`: active/history program revisions and replenishment events.
- `decision_log.jsonl`: activation and authorization actions.
- `repair_queue.jsonl` and `job_packets/`: recovery packet status and rendered contract.

Resume:

- Check the current phase with `research_decision.py --program-recovery-status --check`.
- If the contract is still superseded, resume reviewed contract construction.
- If the contract is active but the ledger is unbound, resume program activation.
- If activation is complete but supply is stale, authorize one event and regenerate supply.
- Skip completed phases by semantic hash, revision identity, event basis, and supply binding.

Must not retry automatically:

- Any budget increase without direct user authority.
- Any route marked terminal for the project.
- Any remote experiment launch or paid resource action.
- Any contract commit whose reviewer hash does not match.
- Any replenishment with unchanged basis or exhausted allocation.

## Risks and Rollback

| Risk | Signal | Mitigation | Rollback |
|---|---|---|---|
| Old negative evidence is lost | Route absent from current and history views | Archive complete route/status/portfolio snapshot before resetting current fields | Restore fixture snapshot; do not deploy failing transaction |
| A model self-expands budget | Replacement cap exceeds direct authorization or no authorization artifact | Commit-time cap and source validation; default remains one | Reject commit and retain superseded contract |
| Stale shortlist is admitted | Pool/scorecard lacks active revision binding | Treat unbound/different supply as stale; if the current event already exists, repair projection without another charge | Keep old files as evidence; clear only active portfolio projection |
| Duplicate recovery consumes budget | Repeated heartbeat creates multiple events | Stable program revision, failure signature, and basis hash | Idempotent no-op; fixture asserts one event/history row |
| Legacy projects regress | Initial active contracts have no replacement lineage | Apply activation guard only when `replacement_basis_decision_id` is present | Legacy fallback remains contract-scoped |
| Resource safety weakens | Candidate recovery triggers launch | Recovery packet excludes launch/admission and resource APIs | No remote side effects exist to undo |
| Concurrent runtime edits are overwritten | Runtime file mtimes/diffs change during implementation | Re-read before each patch and keep edits surgical | Stop and reconcile; never reset others' changes |
| Dirty mirror loses user changes | Broad copy or reset changes unrelated paths | Strict-file allowlist and `git diff --check` | Restore only our allowlisted patch from runtime copy |

## Artifacts and Notes

- GCD read-only failure at 2026-07-15 10:12 CST proves the integer alone is insufficient.
- This ExecPlan is the recovery and implementation record.
- A focused fixture will become the canonical regression artifact for this lifecycle.
- Private Wiki projection: `<wiki-root>/synthesis/AI-Agents-Course/02-agent-system-design/92-autoreskill-replenishment-authority-recovery-execplan.md`.

## Interfaces and Dependencies

Required final interfaces:

- `program_claim_contract.validate_replacement_authority(project, payload) -> dict`: returns complete/errors/warnings and never mutates.
- `research_decision.program_recovery_status(base, frontier=None) -> dict`: returns phase, class, action, reason, authority, and diagnostics.
- `research_decision.program_revision_activation_proposal(base) -> dict`: returns an idempotent mutation proposal or typed errors.
- CLI target `research_decision.py --program-recovery-status --check`: read-only route explanation.
- CLI target `research_decision.py --activate-program-revision --check|--write`: locked activation transaction.
- Candidate pool and scorecard expose `program_revision_id` and `program_claim_contract_sha256` when generated after replacement activation.
- `goal_tick.py` action `recover_replenishment_route`: one deterministic local recovery packet.

External dependencies:

- Python standard library only for new helper logic.
- Existing `contract_lint`, `experiment_next_actions`, queue/lease helpers, and ideation panel commands.
- No network, backend, database, or GPU dependency in focused tests.

## Plan Audit

Initial audit performed before implementation:

- User result: 2/2. The success scenario and observable tick/ledger behavior are explicit.
- Self-contained: 2/2. Paths, current failure, terms, authorities, phases, and commands are recorded.
- Current state: 2/2. Runtime modules, GCD evidence, failure codes, concurrency, and dirty mirror are named.
- Scope boundary: 2/2. Scope, non-goals, and nine invariants prevent budget or remote-action expansion.
- Work slices: 2/2. Four independently acceptable slices and three phases have proofs.
- Acceptance: 2/2. Positive, negative, idempotence, regression, docs, and mirror checks are concrete.
- Recovery: 2/2. CAS, locks, hashes, revision history, resume phases, and no-retry cases are explicit.
- Risk control: 2/2. Every high-risk authority/state issue has a signal, mitigation, and rollback; remote actions are excluded.
- Progress log: 2/2. Timestamped evidence and next milestones are recorded.
- Decisions/discoveries: 2/2. The authority choice, program revision, GPU separation, and stale supply are auditable.

Audit score: 20/20. Hard gates pass; risk control is 2/2.

Audit-driven refinement:

- Removed the preliminary idea of adding `max_autonomous_replenishment_transactions` to `autopilot_policy.json`. It would duplicate the intervention and contract authorities and create ambiguity.
- Reduced three phase-specific goal-tick actions to one resumable `recover_replenishment_route` action. Recovery phase remains machine-readable in status output and packet inputs.
- Kept replacement authority validation commit-only so a draft can be hashed before its reviewer artifact exists; structural `check` remains usable during drafting.
- Kept resource checks at experiment admission/launch and removed them only from CPU/local candidate replenishment.
- Post-implementation audit removed `IDEA_TRACK_SEEDS.json` from recovery outputs because its schema requires a primary, which recovery is forbidden to select.
- Post-implementation audit made original 8-12/3-5 shape evidence durable in the revision-scoped event so normal post-selection shortlist narrowing cannot trigger duplicate replenishment.
- Final safety audit treats every revoked, cancelled, rejected, or blocked intervention status as inactive instead of depending on one exact blocked-status spelling.

Final audit after implementation:

- The initial audit's 20/20 score was provisional and missed the track-seed/primary-selection contradiction. The implementation audit exposed and removed it before deployment.
- Every final acceptance item is backed by a focused fixture, named regression suite, read-only live check, documentation search, or mirror verification.
- Authority remains fail-closed: no implicit cap change, no project-terminal reopen, no reviewer-hash bypass, and no GPU/resource side effect.
- Recovery remains minimal: one action with three resumable phases, one new program-revision transaction, no new schema service, and no automatic migration writer.
- Final assessment: design intent is fully covered without the over-designed track-seed requirement.

## Revision Notes

- 2026-07-15 10:20 CST: Initial self-contained plan created from current runtime and live-project read-only evidence; completed 20-point pre-implementation audit and incorporated simplifications before coding.
- 2026-07-15 11:03 CST: Implementation audit corrected the track-seed boundary and post-selection shortlist compatibility; focused and named regression suites pass.
- 2026-07-15 11:05 CST: Strict mirror sync, final acceptance audit, outcomes, and residual live-project reconciliation note completed.
- 2026-07-15 11:06 CST: Final living plan projected to the Wiki and re-synced to the local mirror.
