---
name: autoreskill-autopilot-controller
description: Bounded full-auto controller for portable AutoResearch. Use when /goal needs to classify blockers, avoid workflow stalls, schedule repairs or async jobs, enforce budgets, downgrade claims, rollback tracks, or decide hard stops in .autoreskill workflows.
metadata:
  short-description: Classify blockers and keep /goal moving
---

# AutoResearch Autopilot Controller

This skill turns hard gates into bounded automatic actions. It does not weaken evidence standards; it prevents silent stalls.

## Blocker Classes

- `auto_repairable`: missing fields, stale projection, malformed JSON, missing artifact index.
- `degradable`: missing optional PaperNexus feature, sparse cost evidence, single-seed result, stale cached graph evidence.
- `async_wait`: only live external waits: PaperNexus literature discovery,
  PaperNexus graph import or authoritative sync, and experiment runtime/resource
  waits. Long review repair, queued sub-agent work, planning, writing, lint, and
  ready local repair are `auto_repairable` or dispatch states, not heartbeat
  waits.
- `hard_stop`: no PaperNexus and no cached evidence, budget exceeded, license blocked, unsafe experiment, no viable claim.

## Scripts

```bash
python scripts/blocker_triage.py --project <project-root> --stage ideation --reason negative_evidence_missing
python scripts/retry_scheduler.py add --project <project-root> --kind repair --stage ideation --action run_negative_evidence_pack
python scripts/retry_scheduler.py list --project <project-root>
python scripts/policy_lint.py --project <project-root> --request remote_experiment --gpu-hours 4 --walltime-hours 2
python scripts/blocker_simulation.py --project <project-root>
```

## Autopilot Rules

- Every `/goal tick` must end with an artifact, repair job, async poll, stage transition, claim downgrade, rollback, track switch, negative-result route, or hard-stop report.
- `full_auto_bounded` may run bounded read-only provider/live/literature discovery, open-access imports, and budgeted experiments.
- It may not fabricate citations, invent results, bypass paywalls, ignore licenses, or exceed budget.
- After `max_repair_attempts_per_blocker`, choose downgrade, rollback, switch track, negative-result route, or hard stop.

Read the references for policy, repair matrix, fallback recipes, and retry budget details.
