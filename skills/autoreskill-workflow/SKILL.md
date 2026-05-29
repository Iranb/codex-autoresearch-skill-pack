---
name: autoreskill-workflow
description: Main $autoreskill and /goal workflow conductor for the portable AutoResearch + PaperNexus skill pack. Use when the user invokes $autoreskill, autoreskill, /goal, asks Codex to initialize, resume, advance, debug, or fully drive a .autoreskill research workflow, dispatch role/job packets, check stage completion, recover stalled workflow state, or run full_auto_bounded multi-step research without the OpenClaw runtime.
---

# AutoResearch Workflow

This is the conductor for the portable AutoResearch + PaperNexus workflow. It must run without `openclaw-research`, `.openclaw-research/`, `PROJECT_MANIFEST.json`, or `research_workflow` tools.

## Non-Negotiables

- Treat `.autoreskill/goal_state.json` as the current stage/owner/action control plane.
- Treat semantic completion as contract-driven, not chat-driven. Use `scripts/contract_lint.py`.
- WorkflowGuard is the only component that advances stages. Child skills only satisfy the current job packet and write their authority artifacts.
- Read `.autoreskill/autopilot_policy.json` before deciding whether to repair, degrade, wait, rollback, or hard-stop.
- Keep every child role isolated through job packets under `.autoreskill/job_packets/` and, when useful, handoff packets under `.autoreskill/handoffs/`.
- PaperNexus live graph work must use the configured `papernexus-remote` MCP. Do not use local PaperNexus CLI, raw HTTP, local graph files, local MCP, or SSH graph commands as substitutes.
- In `full_auto_bounded`, every tick must produce at least one concrete artifact, repair job, async poll, stage transition, downgrade, rollback, track switch, negative-result route, or hard-stop report.
- The parent Codex agent executes ready job packets itself through the named child skill. Do not hand the packet back to the user as manual work unless credentials, budget, or a human gate blocks execution.

## Entry Run Loop

Use this loop whenever the user invokes `$autoreskill`, `/goal`, or asks to continue an existing portable workflow:

1. Resolve the project root. Prefer the user-specified path; otherwise use the current workspace. If `.autoreskill/goal_state.json` exists, resume it.
2. If state is missing and the user supplied a research goal, initialize with `goal.py init`. If no goal is available, ask one concise question for the goal.
3. Run `goal.py status` and summarize `stage`, `owner`, `next_action`, and `blocking_reason`.
4. Run `goal.py reconcile --stale-minutes 60` before long resumes or after interrupted runs.
5. Run `goal.py tick`. Treat the JSON action as authoritative:
   - `advanced` or `terminal_complete`: report the transition; continue only when the user asked for ongoing auto progress.
   - `queued_repair_handoff`, `dispatch_repair`, or `dispatch_async_poll`: dispatch and execute the job packet.
   - `repair_already_queued` or `queued_async_wait` without a due packet: report the wait condition and next retry/poll time.
   - `hard_stop`: report the exact blocker, policy reason, and required external input or downgrade route.
6. For every ready job packet, run `goal.py dispatch --mode serialized --mark-running`, read the generated prompt, use the named child skill, create the required artifacts, run the relevant linter, then run `goal.py update-job`.
7. Run one follow-up `goal.py tick` after a completed job to verify whether the stage advances or a new blocker is queued.

Do not skip status, reconcile, tick, or update-job when executing a role pass. These files are the resume surface after context loss.

## Commands

Use the scripts as deterministic helpers. Resolve `<skill-root>` to this skill directory, usually `~/.codex/skills/autoreskill-workflow`.

```bash
python <skill-root>/scripts/goal_state.py init --project <project-root> --goal "<research problem>" --corpus PN-ICML-Ideation-Shared-240-v1 --venue <target-venue>
python <skill-root>/scripts/goal_state.py status --project <project-root>
python <skill-root>/scripts/goal_tick.py --project <project-root>
python <skill-root>/scripts/goal_job_dispatch.py --project <project-root> --job-id <job-id> --mode serialized --mark-running
python <skill-root>/scripts/goal_job_update.py --project <project-root> --kind repair --job-id <job-id> --status completed --artifact <artifact-path>
python <skill-root>/scripts/goal_job_reconcile.py --project <project-root> --stale-minutes 60
python <skill-root>/scripts/contract_lint.py --project <project-root> --stage <stage>
```

`scripts/goal.py` is a thin dispatcher for the command surface:

```bash
python scripts/goal.py init --project <project-root> --goal "<research problem>"
python scripts/goal.py status --project <project-root>
python scripts/goal.py tick --project <project-root>
python scripts/goal.py repair --project <project-root> --dispatch
python scripts/goal.py evidence --project <project-root>
python scripts/goal.py review --project <project-root> --cross --dispatch
python scripts/goal.py package --project <project-root> --venue <target-venue> --advance
python scripts/goal.py validate --project <project-root>
python scripts/goal.py reconcile --project <project-root> --stale-minutes 60
python scripts/goal.py dispatch --project <project-root> --job-id <job-id> --mode serialized --mark-running
python scripts/goal.py update-job --project <project-root> --kind repair --job-id <job-id> --status completed --artifact <artifact-path>
python scripts/goal.py subagent-result --project <project-root> --job-id <job-id> --agent-id <agent-id> --status completed --artifact <artifact-path>
```

## Stage Order

Default experiment workflow:

```text
init -> topic_search -> graph_build -> frontier_mapping -> literature_review -> ideation -> idea_gate -> experiment_plan -> code -> experiment -> analysis -> review_pressure -> writing -> submission_ready
```

The direct authorities are:

- `graph_build`: `.autoreskill/graph/GRAPH_BUILD_DECISION.json`
- `ideation`: `.autoreskill/ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json`
- `ideation` experiment idea pool: `.autoreskill/ideation/EXPERIMENT_IDEA_POOL.json`
- `idea_gate` selected experiment idea: `.autoreskill/ideation/EXPERIMENT_IDEA_POOL.json`
- `experiment_plan`: `.autoreskill/orchestrator/INNOVATION_PACKET.json`
- prelaunch gate: `.autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json`

Read `references/stage_skill_matrix.md` when deciding which child skill owns a stage, allowed write scope, or linter.

## Tick Protocol

1. Read goal state, policy, capabilities, memory, decision log, repair queue, and async jobs.
2. Reconcile completed/expired jobs.
3. Run contract lint for the current stage.
4. If complete, advance to the next stage.
5. If incomplete, classify with `autoreskill-autopilot-controller` semantics.
6. Queue a repair or async poll, and create a bounded handoff packet when a role pass is needed.
7. Append a decision log entry for the action taken.

Use `scripts/goal_tick.py` for a deterministic single-action tick. It never executes live PaperNexus calls or experiments by itself; it advances completed stages, dispatches due repair/async jobs, or writes the next repair/handoff/job packet for Codex to execute through the relevant child skill.

Use `scripts/goal_job_dispatch.py` to render a job packet into a prompt for either a real sub-agent or a serialized role pass. After the role pass finishes, update the queue with `scripts/goal_job_update.py`.

When `goal_job_dispatch.py --mode subagent` is used, it also writes `.autoreskill/job_packets/<job_id>.subagent_request.json`. The parent Codex agent must call `multi_agent_v1.spawn_agent` with that prompt and then record the result with `goal_subagent_result.py`. Python helpers deliberately do not call Codex MCP tools directly.

Use `scripts/goal_job_reconcile.py` before long-running resumes to requeue stale running jobs or fail them into their fallback action.

## Stall Diagnostics

When a workflow appears stuck, explicitly answer:

- Current stage, owner, next action, and blocking reason from `goal_state.json`.
- Whether a repair or async job is pending, running, stale, failed, or waiting for retry.
- Whether `contract_lint.py` says the current stage is complete.
- Whether the blocker is canonical completion, owner routing, handoff/job delivery, runtime replay, or projection drift.
- Whether policy allows repair/degrade/rollback, or requires a hard stop.

Read these references only as needed:

- `references/stage_contracts.md`: stage authorities and completion contracts.
- `references/stage_skill_matrix.md`: child skill routing and allowed write scopes.
- `references/goal_state_schema.md`: control-plane fields.
- `references/job_execution_packet_schema.md`: dispatch/update protocol.
- `references/handoff_packet_schema.md`: role handoff packet shape.
- `references/role_roster.md`: role write ownership.
