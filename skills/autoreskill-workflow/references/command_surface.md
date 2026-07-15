# Command Surface

Resolve `<skill-root>` to this skill directory, usually
`<CODEX_HOME>/skills/autoreskill-workflow`.

Prefer the dispatcher:

```bash
python <skill-root>/scripts/goal.py init --project <project-root> --goal "<research problem>"
python <skill-root>/scripts/goal.py status --project <project-root>
python <skill-root>/scripts/goal.py tick --project <project-root>
python <skill-root>/scripts/goal.py repair --project <project-root> --dispatch
python <skill-root>/scripts/goal.py evidence --project <project-root>
python <skill-root>/scripts/goal.py review --project <project-root> --cross --dispatch
python <skill-root>/scripts/goal.py package --project <project-root> --venue <target-venue> --advance
python <skill-root>/scripts/goal.py validate --project <project-root>
python <skill-root>/scripts/goal.py reconcile --project <project-root> --stale-minutes 60
python <skill-root>/scripts/goal.py dispatch --project <project-root> --job-id <job-id> --mode serialized --mark-running
python <skill-root>/scripts/goal.py update-job --project <project-root> --kind repair --job-id <job-id> --status completed --artifact <artifact-path>
python <skill-root>/scripts/goal.py update-job --project <project-root> --kind async --job-id <job-id> --status retry --artifact <status-artifact> --runtime-observation-json @<observation.json>
python <skill-root>/scripts/goal.py subagent-result --project <project-root> --job-id <job-id> --agent-id <agent-id> --status completed --artifact <artifact-path>
python <skill-root>/scripts/goal.py trace --project <project-root> --event evaluator_block --stage <stage> --authority Evaluator --decision queue_repair --reason "<finding>"
```

Direct helpers remain useful for debugging or scripted integration:

```bash
python <skill-root>/scripts/goal_state.py init --project <project-root> --goal "<research problem>" --corpus <papernexus-corpus> --venue <target-venue>
python <skill-root>/scripts/goal_state.py status --project <project-root>
python <skill-root>/scripts/goal_tick.py --project <project-root>
python <skill-root>/scripts/goal_job_dispatch.py --project <project-root> --job-id <job-id> --mode serialized --mark-running
python <skill-root>/scripts/goal_job_update.py --project <project-root> --kind repair --job-id <job-id> --status completed --artifact <artifact-path>
python <skill-root>/scripts/goal_job_update.py --project <project-root> --kind async --job-id <job-id> --status retry --artifact <status-artifact> --runtime-observation-json @<observation.json>
python <skill-root>/scripts/goal_job_reconcile.py --project <project-root> --stale-minutes 60
python <skill-root>/scripts/loop_trace.py --project <project-root> --event evaluator_block --stage <stage> --authority Evaluator --decision queue_repair --reason "<finding>"
python <skill-root>/scripts/contract_lint.py --project <project-root> --stage <stage>
python <skill-root>/scripts/ensure_project_agents.py --project <project-root>
python <skill-root>/scripts/experiment_result_summary.py --candidate-log <log> --candidate-tag <tag> --baseline-log <baseline-log> --baseline-tag <baseline-tag> --dataset <dataset> --out-json <RESULT_SUMMARY.json> --out-csv <METRIC_TRAJECTORY.csv>
python <skill-root>/scripts/experiment_next_actions.py init --project <project-root> --direction <Direction>
python <skill-root>/scripts/experiment_next_actions.py check --project <project-root>
python <skill-root>/scripts/experiment_next_actions.py frontier --project <project-root>
python <skill-root>/scripts/experiment_next_actions.py schedule --project <project-root>
python <skill-root>/scripts/experiment_next_actions.py schedule-global --project <project-a> --project <project-b> --resource-snapshot <shared-resource-snapshot.json> --out <global-schedule.json>
python <skill-root>/scripts/experiment_next_actions.py set-policy --project <project-root> --expected-revision <queue-revision> --portfolio-capacity-target 4 --reason <reason>
python <skill-root>/scripts/experiment_next_actions.py claim --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision>
python <skill-root>/scripts/experiment_next_actions.py claim-assignment --project <project-root> --row-id <row-id> --pool-id <pool-id> --owner <worker-id> --expected-revision <queue-revision>
python <skill-root>/scripts/experiment_next_actions.py record-backend-preflight --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision> --input <preflight.json>
python <skill-root>/scripts/experiment_next_actions.py prepare-backend-submit --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision> --input <intent.json>
python <skill-root>/scripts/experiment_next_actions.py record-backend-submit --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision> --input <receipt.json>
python <skill-root>/scripts/experiment_next_actions.py record-backend-observation --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision> --input <observation.json>
python <skill-root>/scripts/experiment_next_actions.py renew --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision>
python <skill-root>/scripts/experiment_next_actions.py release --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision> --reason "<unlaunched reason>"
python <skill-root>/scripts/experiment_next_actions.py complete --project <project-root> --row-id <row-id> --owner <worker-id> --expected-revision <queue-revision> --status <terminal-status> --evidence <artifact-path>
python <skill-root>/scripts/experiment_next_actions.py render --project <project-root>
python <skill-root>/scripts/experiment_next_actions.py render-global --project <project-a> --project <project-b> --out <wiki-rollup.md>
python <skill-root>/scripts/portfolio_batch.py --project <project-root> --dry-run
python <skill-root>/scripts/portfolio_batch.py --project <project-root>
python <skill-root>/scripts/portfolio_batch.py --project <project-root> --recover-operation <operation-id>
python <skill-root>/scripts/resource_passport.py build-project --project <project-root>
python <skill-root>/scripts/resource_passport.py lint-project --project <project-root>
python <skill-root>/scripts/resource_passport.py plan-capability --project <project-root> --pool <pool-id> --out <staging-plan.json>
python <skill-root>/scripts/resource_passport.py enrich-snapshot --project <project-root> --input <live-snapshot.json> --out <enriched-snapshot.json>
python <skill-root>/scripts/research_efficiency_report.py observe --project <project-root>
python <skill-root>/scripts/research_efficiency_report.py report --project <project-root> --markdown-out <report.md>
python <skill-root>/scripts/control_plane_lease.py acquire --project <project-root> --owner <worker-id> --operation <operation>
python <skill-root>/scripts/control_plane_lease.py status --project <project-root>
python <skill-root>/scripts/control_plane_lease.py release --project <project-root> --owner <worker-id> --reason <reason>
python <skill-root>/scripts/research_decision.py --project <project-root> --run-id <run-id> --check
python <skill-root>/scripts/research_decision.py --project <project-root> --run-id <run-id> --write
python <skill-root>/scripts/research_decision.py --project <project-root> --all-terminal --check
python <skill-root>/scripts/research_decision.py --project <project-root> --all-terminal --write
python <skill-root>/scripts/research_decision.py --project <project-root> --program-recovery-status --check
python <skill-root>/scripts/research_decision.py --project <project-root> --activate-program-revision --check
python <skill-root>/scripts/research_decision.py --project <project-root> --activate-program-revision --write
python <skill-root>/scripts/research_decision.py --project <project-root> --replenishment --check
python <skill-root>/scripts/research_decision.py --project <project-root> --replenishment --write
python <skill-root>/scripts/baseline_report_alignment_lint.py --project <project-root> --stage <stage>
python <skill-root>/scripts/paper_claim_ledger.py --project <project-root>
python <skill-root>/scripts/paper_forensics_lint.py --project <project-root> --stage <stage>
python <skill-root>/scripts/paper_code_transfer_lint.py --project <project-root> --required
python <skill-root>/scripts/writing_style_corpus_lint.py --project <project-root> --required
```

Use `--help` on each helper before adding new automation around it.

Queue mutation is local coordination, not backend control. Claim before launch;
after exact preflight persist `submitting` intent before the backend side effect,
record the native receipt as `needs_sync`, and accept `running`/terminal only
from authoritative observation. Search a recovered intent before retrying.
Use `abort-backend-submit` only for an evidence-bound definitive failure before
the backend command began; ambiguity after command start must remain
`submitting`/`needs_sync` for trace-based reconciliation.
Renew only as the same owner, release only before launch or after explicit
no-live-backend reconciliation, and complete only with an evidence path. An
expired lease never proves that a remote job stopped. `research_decision.py
--check` is read-only; `--write` applies a deterministic lifecycle decision but
never launches or cancels work.

For `admission_scope=global`, `claim-assignment` additionally requires the
current global plan/schedule hash, first assignment hash, global lease file, and
the same owner on the live global and target-project control leases. Refresh the
shared resource snapshot and reschedule after each physical launch.
