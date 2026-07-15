# Blocker Repair Matrix

| Evidence / reason | Workflow class | Belief effect | Action |
| --- | --- | --- | --- |
| `negative_evidence_missing` | `auto_repairable` | none | run `negative_evidence_pack`; if empty, write `absence_confidence` |
| `research_controller_unavailable` | `degradable` | none | use the documented fallback and preserve claim limits |
| live import/runtime/resource wait | `async_wait` | none | poll authoritative state; continue independent local/experiment work |
| `infrastructure_failure` | `auto_repairable` or `async_wait` | none | reconcile or retry the same signature at most twice |
| `implementation_failure` | `auto_repairable` | none | make one bounded implementation repair; stop at signature budget |
| `protocol_invalid` | `auto_repairable` | none | quarantine evidence and repair the plan/protocol |
| `valid_negative` | scientific transition | weaken/refute/scope | pivot, retire, scope, or conclude; do not code-repair by default |
| `valid_inconclusive` | scientific transition | inconclusive | run one decision-changing discriminator or retire/conclude |
| `valid_positive_candidate` | scientific transition | support increased | queue linked ablation/confirmation; do not promote directly |
| `single_seed_only` | `degradable` | none | use up to three total random seeds only for a stability question; otherwise downgrade |
| `budget_exceeded` | `hard_stop` | none | shrink task, conclude with claim limits, or stop current route |
| `data_license_blocked` | `hard_stop` | none | switch dataset or stop route |
