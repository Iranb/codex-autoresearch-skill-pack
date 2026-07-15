#!/usr/bin/env python3
"""Ensure project AGENTS.md contains AutoResearch automation rules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BEGIN = "<!-- AUTORESEARCH_AUTOMATION_RULES_BEGIN -->"
END = "<!-- AUTORESEARCH_AUTOMATION_RULES_END -->"

RULE_BLOCK = f"""{BEGIN}

## AutoResearch Automation Rules

When using `autoreskill-workflow` in this project:

- Before creating, updating, or deleting Codex heartbeats, inspect the current workflow state and any existing matching automation; update the existing automation instead of creating duplicates.
- Heartbeats created for `goal.py tick` `wakeup` recommendations are managed workflow state. Use `kind=heartbeat`, `destination=thread`, the returned name/prompt, and the returned interval.
- Do not use in-thread `sleep` loops for PaperNexus discovery/import waits or graph-sync waits. Capture progress, update the async job/status artifact, and schedule the next heartbeat.
- In `full_auto_bounded`, heartbeat resumes and normal workflow turns should run a bounded continuation loop while progress is locally actionable instead of stopping after a single follow-up tick. Continue after `advanced`, `dispatch_repair`, `dispatch_async_poll`, or completed job updates until `hard_stop`, `queued_async_wait`, `repair_already_queued` without a due packet, external live wait with no eligible parallel experiment launch, terminal completion, user/budget/credential gate, or the loop budget. Default loop budget is 5 tick/job actions or about 10 minutes of active work.
- For experiment waits, a running run is not a project-wide barrier. Before keeping or creating `poll_experiment_run`, inspect `.autoreskill/experiment/NEXT_EXPERIMENT_QUEUE.json` and live GPU/HPC capacity; if an independent ready/planned row can fit an idle resource without dependency, mutex, or allocation conflict, dispatch `launch_parallel_experiment` instead of waiting.
- On every experiment heartbeat, refresh capability-known GPU pools before waiting. When idle slots coexist with `portfolio_admission_deficit > 0`, no fillable committed candidate, and an unresolved program claim, dispatch one bounded WorkflowGuard candidate-replenishment action even when zero tracks are active. First commit the changed-basis ledger event with `research_decision.py --replenishment --write`; preserve any selected primary and live selection fingerprint, reuse the canonical evidence source, deduplicate by the program/lifecycle/evidence/decision/resource basis, and return evidence-gated minimum pilots to normal admission. Idle GPUs never waive scientific gates or budgets.
- For an enforced `cross_dataset_method`, resolve the live program claim contract before method planning. Diagnostics cannot satisfy the method portfolio. Before seeds or HPO, batch-run every preregistered 2-3-value-per-dataset load-bearing parameter probe at one fixed scout seed, commit calibration through the idea ledger, freeze one profile, then launch paired dataset screens. Never replace parameter-value coverage with extra seeds.
- Deleting, archiving, or updating a stale heartbeat is cleanup only, not a workflow stop condition. After deleting a managed heartbeat because its external wait is terminal, superseded, or locally actionable, immediately run `goal.py status`, `goal.py reconcile --stale-minutes 60`, and `goal.py tick`; continue one bounded tick/job cycle if local repair, analysis, planning, launch, rollback/degrade, or stage transition work is exposed.
- `next_retry_at` is automatic unattended-retry backoff, not a hard block after the user provides a new endpoint, credential, GPU allocation, dataset path, or other external readiness signal. In that case, allow an immediate matching repair dispatch with `goal.py tick --force-due-repair --force-job-id <job_id>` or `.autoreskill/control/ACTIVE_RETRY_OVERRIDE.json`, then record the override reason and live outcome in the repair/status artifact.
- On every heartbeat resume, recompute the next interval from live progress, ETA, or the returned `wakeup` recommendation. If the interval should change, update the heartbeat before returning.
- For PaperNexus graph import waits, do not use fixed interval buckets. Recompute the next heartbeat from live task state, selected queue position, queued-ahead count, running worker count, overall queue completion delta, selected-position delta, task stage, processed-unit rate, timeout/failure risk, and estimated next meaningful state change. Terminal/risky states, final commit, authoritative sync, or WorkflowGuard transition opportunities should be checked soon; deep queued selected tasks with a long estimated time to start may use longer waits. Record `poll_interval_decision`, `estimated_next_event_at` or `eta_basis`, and the reason in the status artifact. When a heartbeat combines graph import with another active task, compute each wait independently and use the earliest meaningful next-check time.
- Every progress-dependent heartbeat status report must include observed progress, ETA or wait condition, selected poll interval, and the reason for keeping/updating/deleting the heartbeat.
- After every Analyzer pass, `analyzer/IDEA_OUTCOME_SUMMARY.json` must include `post_analysis_self_audit.least_confident_point` and `post_analysis_self_audit.largest_possible_misunderstanding`, answering where the current conclusion is least certain and what global misunderstanding or blind spot may remain. This self-audit is a claim-boundary guard and must not be used to upgrade weak evidence.
- If the user pauses or cancels automation, delete the relevant heartbeat first and do not recreate it until explicitly instructed.
- Remote training shutdown monitors are separate from AutoResearch goal ticks. If such a monitor is created, it must still record progress/ETA and explicitly justify each polling interval decision.
- GitHub private repositories may be used to synchronize experiment code between local and remote machines. Repositories must stay private and code-only: do not commit datasets, dataset archives, model weights, checkpoints, raw outputs, runtime logs, credentials, SSH keys, or machine-specific upload/run state. Record repo URL, privacy, branch, commit SHA, export path, remote checkout path, and excluded artifact classes in `.autoreskill/coder/CODE_SYNC_LEDGER.json` and the relevant `REMOTE_UPLOAD.json`/`REMOTE_RUN.json`.

{END}
"""


def update_agents(text: str) -> tuple[str, bool]:
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        end = text.index(END, start) + len(END)
        new_text = text[:start].rstrip() + "\n\n" + RULE_BLOCK.rstrip() + "\n" + text[end:].lstrip("\n")
        return new_text, new_text != text
    if text.strip():
        return text.rstrip() + "\n\n" + RULE_BLOCK, True
    return RULE_BLOCK, True


def rule_block_hash() -> str:
    return hashlib.sha256(RULE_BLOCK.encode("utf-8")).hexdigest()


def update_goal_state(project: Path, policy_hash: str) -> None:
    state_path = project / ".autoreskill" / "goal_state.json"
    if not state_path.exists():
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(state, dict):
        return
    if state.get("project_agents_policy_hash") == policy_hash:
        return
    state["project_agents_policy_hash"] = policy_hash
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="Project root")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not project.exists():
        raise SystemExit(f"project does not exist: {project}")
    agents = project / "AGENTS.md"
    old = agents.read_text(encoding="utf-8") if agents.exists() else ""
    new, changed = update_agents(old)
    policy_hash = rule_block_hash()
    if changed:
        agents.write_text(new, encoding="utf-8")
        print(f"updated {agents}")
    else:
        print(f"unchanged {agents}")
    update_goal_state(project, policy_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
