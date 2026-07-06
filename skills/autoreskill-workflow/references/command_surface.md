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
python <skill-root>/scripts/baseline_report_alignment_lint.py --project <project-root> --stage <stage>
python <skill-root>/scripts/paper_claim_ledger.py --project <project-root>
python <skill-root>/scripts/paper_forensics_lint.py --project <project-root> --stage <stage>
python <skill-root>/scripts/paper_code_transfer_lint.py --project <project-root> --required
python <skill-root>/scripts/writing_style_corpus_lint.py --project <project-root> --required
```

Use `--help` on each helper before adding new automation around it.
