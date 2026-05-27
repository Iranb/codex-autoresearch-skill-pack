# Experiment Idea Pool

Create `ideation/EXPERIMENT_IDEA_POOL.json` during the ideation/idea construction stage. The 12-15 items are optimization ideas, not high-level research directions. The JSON file is only the container for those ideas.

This is an ideation-stage artifact consumed by experiment planning. Do not refresh the literature review only to populate it. Use existing PaperNexus evidence, code analysis, user priors, and run feedback.

Required shape:

```json
{
  "schema_version": 1,
  "created_at": "",
  "idea_generation_scope": "ideation-stage experiment idea pool; no experiment-plan generation",
  "locked_protocol": {
    "dataset": "",
    "data_split": "",
    "primary_metric": "",
    "metric_direction": "higher|lower",
    "baseline_training_protocol": "",
    "baseline_eval_protocol": "",
    "evaluation_command": "",
    "protected_paths": [
      {"path": "", "purpose": "eval|test_data|metric", "sha256": ""}
    ]
  },
  "selected_idea_id": "IDEA-001",
  "ideas": [
    {
      "id": "IDEA-001",
      "type": "ALGO|CODE|PARAM",
      "priority": "HIGH|MEDIUM|LOW",
      "risk": "LOW|MEDIUM|HIGH",
      "source": "papernexus|code_analysis|run_feedback|user_prior|hybrid",
      "source_paper_or_technique": "",
      "paperNexus_evidence_ids": [],
      "derived_from_idea_fragment_ids": [],
      "description": "",
      "hypothesis": "",
      "one_variable_change": "",
      "expected_metric_impact": "",
      "implementation_scope": "",
      "red_line_audit": {
        "metric_drift": false,
        "eval_drift": false,
        "dataset_drift": false,
        "data_leakage": false,
        "prediction_cheating": false,
        "training_budget_drift": false
      },
      "status": "PENDING|SELECTED|RUNNING|FAILED|NOT_PROMOTED|PROMOTED|REJECTED"
    }
  ]
}
```

Selection rules:

- Generate 12-15 ideas during `ideation`, before `experiment_plan`.
- Target at least 6 Tier 1 ALGO/cross-paper or architecture ideas and at least 6 Tier 2 CODE/algorithm-logic ideas when the codebase permits it.
- Include at least 3 ALGO ideas with an explicit source paper, technique, or PaperNexus evidence id.
- Keep Tier 3 PARAM-only ideas to 4 or fewer; use them only after ALGO/CODE ideas are weak, risky, or exhausted.
- Select one idea during `idea_gate` before entering `experiment_plan`.
- Mark ideas that fail the red-line audit as `REJECTED` or `NOT_PROMOTED` before launch.

Idea status is a ledger pointer, not a claim. An idea becomes evidence only after `REMOTE_RUN.json`, metrics, source snapshot, and `EXPERIMENT_LEDGER.json` record the result.
