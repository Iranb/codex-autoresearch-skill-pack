---
name: autoreskill-workflow-guard
description: Main /goal workflow guard for the portable AutoResearch + PaperNexus skill pack. Use when the user invokes /goal, asks to run an automated research workflow, initialize or resume .autoreskill state, dispatch role packets, check stage completion, or drive full_auto_bounded multi-agent research without the OpenClaw runtime.
metadata:
  short-description: Drive /goal AutoResearch workflow
---

# AutoResearch Workflow Guard

This is the entry skill for the portable AutoResearch + PaperNexus workflow. It must run without `openclaw-research`, `.openclaw-research/`, `PROJECT_MANIFEST.json`, or `research_workflow` tools.

## Operating Rules

- Treat `.autoreskill/goal_state.json` as the current stage/owner/action control plane.
- Treat semantic completion as contract-driven, not chat-driven. Use `scripts/contract_lint.py`.
- Read `.autoreskill/autopilot_policy.json` before deciding whether to repair, degrade, wait, rollback, or hard-stop.
- Keep every child role isolated through handoff packets under `.autoreskill/handoffs/`.
- PaperNexus live graph work must use the configured `papernexus-remote` MCP. Do not use local PaperNexus CLI, raw HTTP, local graph files, or SSH graph commands as substitutes.
- In `full_auto_bounded`, every `/goal tick` must produce at least one concrete artifact, repair job, async poll, stage transition, downgrade, rollback, track switch, negative-result route, or hard-stop report.

## Commands

Use the scripts as deterministic helpers:

```bash
python scripts/goal_state.py init --project <project-root> --goal "<research problem>" --corpus PN-ICML-Ideation-Shared-240-v1 --venue <target-venue>
python scripts/goal_state.py status --project <project-root>
python scripts/goal_tick.py --project <project-root>
python scripts/goal_repair.py --project <project-root> --dispatch --mode serialized
python scripts/goal_evidence.py --project <project-root> --markdown evidence/EVIDENCE_PACKET.md
python scripts/goal_review.py --project <project-root> --cross --dispatch
python scripts/goal_package.py --project <project-root> --venue <target-venue> --advance
python scripts/goal_validate.py --project <project-root>
python scripts/goal_job_dispatch.py --project <project-root> --job-id <job-id> --mode serialized --mark-running
python scripts/goal_subagent_result.py --project <project-root> --job-id <job-id> --agent-id <agent-id> --status completed --artifact <artifact-path>
python scripts/goal_job_update.py --project <project-root> --kind repair --job-id <job-id> --status completed --artifact <artifact-path>
python scripts/goal_job_reconcile.py --project <project-root> --stale-minutes 60
python scripts/contract_lint.py --project <project-root> --stage <stage>
python scripts/handoff_append.py --project <project-root> --from WorkflowGuard --to Researcher --stage ideation --goal "<bounded task>"
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
```

## Stage Order

Default experiment workflow:

```text
init -> topic_search -> graph_build -> frontier_mapping -> literature_review -> ideation -> idea_gate -> experiment_plan -> code -> experiment -> analysis -> review_pressure -> writing -> submission_ready
```

The direct authorities are:

- `graph_build`: `.autoreskill/graph/GRAPH_BUILD_DECISION.json`
- `ideation`: `.autoreskill/ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json`
- `experiment_plan`: `.autoreskill/orchestrator/INNOVATION_PACKET.json`
- prelaunch gate: `.autoreskill/planner/EXPERIMENT_REVIEW_PACKET.json`

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

Read `references/stage_contracts.md`, `references/goal_state_schema.md`, `references/handoff_packet_schema.md`, and `references/job_execution_packet_schema.md` when implementing or debugging the workflow.
