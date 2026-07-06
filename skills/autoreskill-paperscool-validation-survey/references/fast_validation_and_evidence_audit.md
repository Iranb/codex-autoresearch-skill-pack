# Fast Validation and Evidence Audit

Use this reference when turning code mechanisms into target-task innovation candidates.

## Useful Candidate Definition

A useful paper-code candidate is not merely relevant. It must reduce to a mechanism that can be tested in the current project with bounded edits and a clear falsifier.

Prefer candidates with:

- A small number of implementation touchpoints.
- No new large dataset requirement.
- No LLM/VLM/diffusion dependency.
- No huge pretraining step.
- A mechanism that maps to a known target pressure such as pseudo-label noise, old/new drift, domain shortcut, prototype instability, calibration error, or class imbalance.
- A minimal validation protocol that can fail quickly.

## Fast Validation Card

Each idea in `FAST_VALIDATION_QUEUE.json` should answer:

- What mechanism is being transferred?
- Which target-task failure mode does it address?
- Which files or modules likely need edits?
- What dataset/protocol is the smallest honest test?
- What metric should move?
- What result would falsify the idea?
- What evidence boundary must remain in the paper claim?

Suggested fields:

```json
{
  "idea_id": "FV-001",
  "source_paper_id": "paper-123",
  "source_mechanism_id": "MECH-001",
  "target_task": "ContinueGCD",
  "implementation_scope": "prototype memory update gate",
  "expected_files_to_edit": ["models/memory.py", "train.py"],
  "requires_new_dataset": false,
  "requires_large_model": false,
  "requires_diffusion_or_generation": false,
  "estimated_gpu_cost": "low",
  "minimal_validation_dataset": "existing split / small backbone",
  "success_metric": "old/new class clustering accuracy improves without known-class drop",
  "falsifier": "gain disappears in ablation or known-class performance drops beyond tolerance",
  "priority": "P1"
}
```

## Evidence Boundaries

Use these labels consistently:

- `raw_discovery`: papers.cool or search result only.
- `paper_metadata`: title, abstract, venue, authors, paper URL.
- `repo_static`: repository exists and relevant files were inspected.
- `active_code_path`: training/evaluation code path contains the mechanism.
- `mechanism_feasibility`: source code suggests the mechanism can be adapted.
- `target_validation_pending`: not yet run on target protocol.
- `target_validated`: matched target experiment produced evidence.
- `rejected`: falsifier or feasibility check failed.

Do not promote `repo_static` or `active_code_path` evidence into target effectiveness claims.

## Common Failure Modes

- Same-field paper is mistakenly used as a new idea instead of a baseline or novelty-risk item.
- A project page or benchmark wrapper is treated as an implementation repo.
- A heavy foundation-model method is kept because the abstract sounds transferable.
- A mechanism is actually just parameter tuning.
- The source method requires a protocol or metric that the target project cannot support.
- The validation queue lacks falsifiers and therefore becomes a list of hopes rather than testable ideas.
