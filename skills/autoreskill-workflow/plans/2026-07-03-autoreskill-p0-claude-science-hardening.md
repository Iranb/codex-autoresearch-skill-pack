# ExecPlan: autoreskill-workflow P0 Claude Science Contract Hardening

Created: 2026-07-03 Asia/Shanghai

Updated: 2026-07-05 Asia/Shanghai, after second first-principles overdesign review

Target repository or skill root: `/Users/iranb/.codex/skills/autoreskill-workflow`

Target branch/worktree: local Codex skill directory; no git branch assumption.

Owner: Codex, following `/Users/iranb/.codex/skills/execplan-builder/SKILL.md`.

## Living Document Policy

This ExecPlan is a living document. While implementing it, update `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` in place. Do not treat this file as a static proposal after the first edit. If implementation discovers that an optimization is too broad, record the finding here and narrow the plan before editing runtime code.

No `PLANS.md`, `.agent/PLANS.md`, or existing plan directory was found in `/Users/iranb/.codex/skills/autoreskill-workflow` before this file was created. If a repository-level `PLANS.md` is added later, reconcile this plan with it before continuing.

## Purpose / Big Picture

The current `autoreskill-workflow` already has a strong AutoResearch conductor: stage contracts, `goal_state.json`, `contract_lint.py`, WorkflowGuard-style rules, job execution packets, async wait policy, `LOOP_TRACE.jsonl`, `evidence_cart.jsonl`, `artifacts_index.json`, `EXPERIMENT_MANIFEST.json`, `REMOTE_RUN.json`, `EXPERIMENT_LEDGER.json`, and result-aware experiment gates.

The comparison with Claude Science does not justify a new controller, queue, daemon, database, or role system. The useful P0 gap is narrower:

1. Make runtime environment choices explicit enough that a future paper claim can be audited, using inline fields in existing manifest/run records first and sidecar files only when reuse or size justifies them.
2. Make result-bearing artifacts traceable to source code, runs, environment checks, and evidence.
3. Make `REMOTE_RUN.json` represent minimal run status and harvest evidence instead of being only an upload/run note.

After this plan is complete, a user should be able to run the usual autoreskill workflow and inspect one project to answer:

- Which environment and backend class produced this result?
- Which validation proved that environment could run the experiment?
- Which remote run produced each promoted metric or analysis artifact?
- Which logs and small result artifacts were harvested, and which large or sensitive artifacts were deliberately excluded?
- Whether a manuscript-level claim is backed by the minimum required lineage or must be downgraded.

## Related Docs And Evidence

- `/Users/iranb/.codex/skills/execplan-builder/SKILL.md`: defines when to build an ExecPlan, requires a self-contained living plan, and requires a rubric-based review before finalizing.
- `/Users/iranb/.codex/skills/execplan-builder/references/execplan-content-contract.md`: requires explicit current state, plan of work, concrete validation, recovery, risk, and self-audit sections.
- `/Users/iranb/.codex/skills/autoreskill-workflow/SKILL.md`: current top-level conductor instructions; already defines kernel invariants, loop harness policy, and stage/evidence contracts.
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/stage_contracts.md`: current stage output contracts; `code` and `experiment` already require `EXPERIMENT_MANIFEST`, `REMOTE_RUN`, `EXPERIMENT_LEDGER`, summaries, and metric trajectories.
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/stage_skill_matrix.md`: maps stages to skill owners and write scopes; `code` and `experiment` already write under `.autoreskill/coder/`.
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/job_execution_packet_schema.md`: defines job packets, allowed writes, and experiment repair evidence; already references `REMOTE_RUN`, synced logs, and experiment ledgers.
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/role_roster.md`: current role roster is write-scope oriented; it is not a connector permission system and should not become one in this P0.
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/source_traceability.md`: maps stage artifacts to OpenClaw-style traceability; this plan extends traceability for runtime and artifact lineage without replacing it.
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/command_surface.md`: lists the command surface that must remain stable after changes.
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/contract_lint.py`: current stage gate authority; all new hard checks should live here or be called from here.
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_tick.py`: renders job packets and stage execution specs; this is where new P0 expected outputs and constraints should be introduced.
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_evidence.py`: exports `evidence_cart.jsonl` and `artifacts_index.json`; this is the lowest-risk place to surface lineage summaries.
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_fixture.py`: creates testable fixture projects; it should be extended instead of hand-crafting opaque test projects.
- `/Users/iranb/.codex/skills/autoreskill-workflow/tests/run_minimal_hardening_fixtures.py`: current minimal hardening regression suite.
- `/Users/iranb/.codex/skills/autoreskill-workflow/tests/run_paper_forensics_fixtures.py`: current paper forensics regression suite.

## Progress

- [x] Compared the P0 candidates against the current `autoreskill-workflow` design.
- [x] Confirmed that current workflow already has stage contracts, allowed writes, job packets, async waits, evidence carts, artifact index, and result summary concepts.
- [x] Removed over-broad ideas from P0: no new queue, no endpoint registry, no role connector allowlist, no daemon, no external remote executor implementation.
- [x] Created this ExecPlan.
- [x] Applied first-principles overdesign review: provider ledger is optional, lifecycle is simplified, artifact lineage is shortened, and lint uses one public entry point.
- [x] Applied second first-principles overdesign review: runtime env/validation is inline-first, sidecar files are optional, `paper_claim_allowed` is no longer run authority, `terminal_status` and ledger refs are optional, and `artifact_id` is no longer required when `path` is already the artifact identity.
- [ ] Implement reference-contract updates.
- [ ] Implement lint and fixture updates.
- [ ] Run regression tests and targeted failure-mode tests.
- [ ] Update this plan's retrospective with the actual implementation outcome.

## Surprises & Discoveries

- The current workflow already has more Claude-Science-like structure than the first comparison implied. `stage_contracts.md` and `goal_tick.py` already require experiment manifests, remote run files, experiment ledgers, trajectory summaries, and selected-idea/track metadata propagation.
- `artifacts_index.json` already exists, but its current role is closer to a catalog than a dependency graph. P0 should extend it as optional typed lineage first, then require lineage only for promoted result-bearing artifacts.
- `REMOTE_RUN.json` already participates in code/experiment readiness. The missing piece is not a second run system; it is a minimal status and harvest schema layered onto the existing file.
- First-principles review showed that `COMPUTE_PROVIDER_LEDGER.json` as a required file is not minimal. A paper-claim audit only needs backend/provider identity attached to the environment or run; a separate ledger is useful only for multi-provider reuse or resource governance.
- Second first-principles review showed that mandatory `ENV_SPEC.json` and `ENV_VALIDATION.json` sidecars are also not minimal. Current autoreskill already has `EXPERIMENT_MANIFEST.json` and `REMOTE_RUN.json`; V0 should accept inline `runtime_env` and `runtime_validation` fields there, with sidecars only when a project shares one environment across many runs or needs a longer validation record.

## Decision Log

- Decision: Keep `contract_lint.py` as the only hard contract authority.
  Rationale: A second gate would split truth between scripts and make debugging harder.

- Decision: Keep compute/provider records as evidence, not as a scheduler.
  Rationale: `autoreskill-workflow` coordinates research state; it should not own real GPU allocation or remote execution in this P0.

- Decision: Make new runtime lineage additive and backwards compatible.
  Rationale: Existing projects and fixtures must not fail merely because they predate the new schema. Strong paper claims and promoted experiment evidence can require stricter lineage.

- Decision: Do not add Claude Science role or connector profiles in P0.
  Rationale: Current `role_roster.md` is based on role/write-scope boundaries. Connector permissions are a larger policy surface and should remain P1 unless concrete misuse appears.

- Decision: Scope artifact lineage to result-bearing and claim-bearing artifacts.
  Rationale: Requiring full lineage for every note, index, or intermediate file would create noise without improving paper safety.

- Decision: Make `COMPUTE_PROVIDER_LEDGER.json` optional in V0.
  Rationale: Provider evidence is needed, but a standalone ledger is not the smallest mechanism. Embed required provider/backend fields in inline `runtime_env` or `REMOTE_RUN.json`; use a ledger only when one project intentionally tracks multiple providers.
  Date/Author: 2026-07-03 / Codex.

- Decision: Simplify run lifecycle to the smallest state needed for claim audit.
  Rationale: `audited` is a lint/review result, not a run state, and `harvested` is better represented as `harvest.status`. The V0 run state should not duplicate async/job state.
  Date/Author: 2026-07-03 / Codex.

- Decision: Make runtime environment and validation inline-first in V0.
  Rationale: The current architecture already centers `EXPERIMENT_MANIFEST.json` and `REMOTE_RUN.json`; requiring two new sidecar files for every project would create migration noise before proving value. Sidecars remain valid when they reduce duplication across runs.
  Date/Author: 2026-07-05 / Codex.

- Decision: Remove `paper_claim_allowed` from required `REMOTE_RUN.json` fields.
  Rationale: A run is evidence, not a claim authority. Claim permission should be derived by `contract_lint.py`, `EXPERIMENT_LEDGER.json`, analysis artifacts, and paper-ready artifact lineage.
  Date/Author: 2026-07-05 / Codex.

## Outcomes & Retrospective

Implementation has not started. Fill this section after the code and docs are changed:

- Files changed:
- Tests run:
- Validation result:
- Contract noise observed:
- Any P0 rules downgraded to warning:
- Remaining follow-up:

## Context and Orientation

The workflow root contains:

- `SKILL.md` for top-level conduct.
- `references/` for stage contracts, command surface, role roster, source traceability, async policy, job packet schema, and related policy.
- `scripts/` for state transition, linting, job dispatch/reconcile, evidence export, package, and repair.
- `tests/` for fixture-based regression.

Current code and experiment stage behavior:

- `goal_tick.py` emits stage job packets with `allowed_writes`, `constraints`, `outputs`, and `acceptance_contract`.
- `code` already expects `.autoreskill/coder/EXPERIMENT_INDEX.md`, `EXPERIMENT_MANIFEST.json`, `BASELINE_DATA_AUDIT.json`, `REMOTE_UPLOAD.json`, `REMOTE_RUN.json`, and real-data smoke logs.
- `experiment` already expects `.autoreskill/coder/EXPERIMENT_LEDGER.json`, `TRACK_RANKING.json`, `EXPERIMENT_INDEX.md`, result summaries, metric trajectories, synced logs, and selected idea/track/branch/search iteration/version metadata.
- `contract_lint.py` already validates stage readiness and has backend-remap closure checks, but it does not currently define an explicit inline-or-sidecar runtime environment contract, validation contract, optional provider ledger, remote run harvest evidence, or typed artifact dependencies.
- `goal_evidence.py` already exports and summarizes `artifacts_index.json`, but does not yet summarize environment or run lineage.

The implementation should fit into that shape. The safest path is to add one reference contract, small references from existing stage docs, narrowly scoped lint helpers, fixture updates, and evidence display improvements.

## Scope

Implement P0 hardening for:

1. Minimal runtime environment evidence, including backend/provider identity, accepted inline in `EXPERIMENT_MANIFEST.json` or `REMOTE_RUN.json`.
2. Short typed artifact lineage for promoted result and claim-bearing artifacts.
3. `REMOTE_RUN.json` run status and harvest evidence, without a second async state machine.
4. Fixture and lint coverage proving the above without breaking existing projects.

The intended changed files are:

- `/Users/iranb/.codex/skills/autoreskill-workflow/SKILL.md`
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/stage_contracts.md`
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/job_execution_packet_schema.md`
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/source_traceability.md`
- `/Users/iranb/.codex/skills/autoreskill-workflow/references/command_surface.md` only if new commands are added; the preferred outcome is no new commands.
- New reference file: `/Users/iranb/.codex/skills/autoreskill-workflow/references/runtime_lineage_contract.md`
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/contract_lint.py`
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_tick.py`
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_evidence.py`
- `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_fixture.py`
- Existing tests under `/Users/iranb/.codex/skills/autoreskill-workflow/tests/`, plus one optional new focused test if needed.

## Non-Goals

Do not implement these in P0:

- No new workflow controller, no new stage, no new daemon, no database, no persistent service.
- No `pending_actions` queue or second async run system.
- No real SSH, AutoDL, Slurm, Modal, cloud, or paid GPU execution.
- No endpoint registry that tries to manage provider credentials or allocation.
- No role-to-connector permission policy.
- No broad rewrite of `goal_state.json`, `evidence_cart.jsonl`, or existing command names.
- No requirement to sync checkpoints, datasets, model weights, raw full logs, secrets, SSH keys, tokens, or private host credentials.
- No hard failure for old projects that lack the new schema unless they are being promoted as current paper-ready evidence.

## Non-Negotiable Rules

- Preserve the existing command surface unless a new command is strictly necessary.
- Treat `contract_lint.py` as the hard gate authority.
- Keep new schemas additive. Existing fields remain valid.
- Keep V0 schemas minimal: require only fields needed to trace `paper_ready` evidence from artifact to run to environment to validation.
- Require runtime lineage only for promoted experiment results, paper-claim evidence, and analysis/writing artifacts that cite experiment metrics.
- If an artifact lacks lineage, the workflow should downgrade or block the claim that depends on it, not delete the artifact.
- Keep sensitive material out of synced artifacts and public examples.
- All fixture data must be synthetic and local.
- Every new hard check must have at least one passing fixture and one failing fixture.

## Authority / Evidence Model

The following authority model prevents overdesign:

- `goal_state.json`: stage state and current workflow status.
- `contract_lint.py`: only hard pass/fail authority for stage readiness.
- `EXPERIMENT_MANIFEST.json`: declares intended experiments, datasets, code refs, and may carry inline `runtime_env` and `runtime_validation` for launch-ready tracks.
- `COMPUTE_PROVIDER_LEDGER.json`: optional evidence about multiple provider identities for this project; not a scheduler and not required for single-provider projects.
- `ENV_SPEC.json`: optional sidecar evidence describing the intended runtime environment when inline fields would duplicate across many runs.
- `ENV_VALIDATION.json`: optional sidecar evidence that the runtime environment passed import, dependency, GPU or CPU, data-path, and dry-run checks.
- `REMOTE_RUN.json`: evidence for one remote or local run status plus inline or referenced runtime/harvest evidence.
- `EXPERIMENT_LEDGER.json`: run/result ledger authority for experiment rows.
- `artifacts_index.json`: searchable artifact and lineage index; not the stage authority.
- `evidence_cart.jsonl`: evidence cart for claims and decisions.

## Plan of Work

### Slice 0: Reconfirm Current State

Read the exact current files before editing:

    cd /Users/iranb/.codex/skills/autoreskill-workflow
    rg -n "ENV_SPEC|ENV_VALIDATION|COMPUTE_PROVIDER|harvest_spec|artifacts_index|REMOTE_RUN|EXPERIMENT_LEDGER|EXPERIMENT_MANIFEST" SKILL.md references scripts tests

Expected result:

- No existing runtime contract names except current manifest, remote run, ledger, and artifact index.
- Any discovered overlapping fields are reused rather than duplicated.

### Slice 1: Add Runtime Lineage Reference Contract

Create `/Users/iranb/.codex/skills/autoreskill-workflow/references/runtime_lineage_contract.md`.

It should define an inline-first contract:

1. `runtime_env`: a compact object embedded in `EXPERIMENT_MANIFEST.json` or `REMOTE_RUN.json`.
2. `runtime_validation`: a compact object embedded in `EXPERIMENT_MANIFEST.json` or `REMOTE_RUN.json`.
3. Optional `ENV_SPEC.json` and `ENV_VALIDATION.json` sidecars when one environment is reused across many runs or the validation evidence is too large to keep inline.
4. Optional `COMPUTE_PROVIDER_LEDGER.json` for projects that intentionally track more than one provider.

It should also define minimal extensions for:

1. `REMOTE_RUN.json.status`
2. `REMOTE_RUN.json.harvest`
3. `artifacts_index.json` lineage fields

Optional provider ledger fields:

- `schema_version`
- `providers[]`
- `providers[].provider_id`
- `providers[].backend_kind`: one of `local_cpu`, `local_gpu`, `ssh`, `slurm`, `autodl`, `cloud`, `other`
- `providers[].display_name`
- `providers[].resource_summary`
- `providers[].credential_policy`: `not_recorded`, `external_profile`, or `local_private_config`
- `providers[].notes`

Do not require this file for a single-provider experiment. If it exists, lint it for obvious safety issues such as secret-like fields, but do not make it a stage gate by itself.

Required `runtime_env` fields:

- `schema_version`
- `env_id`
- `backend`: object with `backend_kind` and optional `provider_id` or `display_name`
- `created_at`
- `code_ref`: commit, archive hash, or code sync ledger reference
- `dependency_fingerprint`: lockfile hash, container digest, or explicit package summary
- `data_manifest_refs`
- `secret_policy`

Optional `runtime_env` fields:

- `python`
- `cuda`
- `driver`
- `torch`
- `package_lock_refs`
- `container_ref`
- `install_steps_ref`
- `dataset_mounts`
- `weight_mounts`
- `expected_commands`
- `validation_ref`: useful when validation is sidecar-only, but not required when `runtime_validation` is inline.

Do not require local absolute dataset or weight mount paths unless the project is private and the path is needed for reproducibility. Prefer manifest IDs, hashes, and redacted mount labels. `ENV_SPEC.json` is only a sidecar representation of this same object; it is not required when `runtime_env` is already inline.

Required `runtime_validation` fields:

- `schema_version`
- `env_id`
- `validated_at`
- `validation_status`: `pass`, `warn`, or `fail`
- `evidence_refs`

Conditionally required `runtime_validation` fields:

- `claim_limit`: required when `validation_status` is `warn` or `fail`, when validation is CPU-only for a GPU claim, or when validation is diagnostic-only.

Optional `runtime_validation` fields:

- `validation_id`
- `import_checks`
- `gpu_witness`
- `data_path_checks`
- `dry_run_command`
- `dry_run_log_ref`
- `failure_class`

Required `REMOTE_RUN.json` fields for any run row:

- `schema_version`
- `run_id`
- `status`: `planned`, `running`, `finished`, or `failed`

Required `REMOTE_RUN.json` fields once the run is `running`, `finished`, promoted, ready for analysis, or cited by a paper-ready artifact:

- `runtime_env` or `runtime_env_ref`
- `runtime_validation` or `runtime_validation_ref`

Required `REMOTE_RUN.json` fields for a finished run that is promoted, ready for analysis, or cited by a paper-ready artifact:

- `result_summary_ref`
- `harvest`: object with `status`, `result_refs`, and `excluded_classes`

Optional `REMOTE_RUN.json` fields:

- `provider_id`
- `submit_plan`
- `remote_workdir`
- `remote_job_id`
- `started_at`
- `ended_at`
- `terminal_status`
- `local_log_paths`
- `log_sync`
- `metric_trajectory_ref`
- `experiment_ledger_ref`
- `paper_claim_allowed`: allowed only as a diagnostic hint; it is not a claim authority.

Required `harvest` fields for promoted finished runs:

- `status`: `complete`, `partial`, `skipped`, or `failed`
- `result_refs`
- `excluded_classes`

Optional `harvest` fields:

- `required_artifacts`
- `include_patterns`
- `exclude_patterns`
- `forbidden_classes`
- `max_total_bytes`
- `sync_policy`
- `harvested_at`
- `local_refs`

Required artifact lineage fields for `paper_ready` or promoted result artifacts:

- `path`
- `kind`
- `stage`
- `claim_permission`: `none`, `exploratory`, `internal`, `paper_candidate`, or `paper_ready`
- `produced_by_run`
- `evidence_refs`

Optional observed artifact lineage fields:

- `artifact_id`
- `source_refs`
- `code_refs`
- `run_refs`
- `env_refs`
- `dependency_refs`
- `verification_refs`
- `produced_at`

This reference should explicitly say that older artifact rows without these fields remain valid catalog rows, but cannot alone support `paper_ready` claims. In V0, `path` can serve as the artifact identity. `produced_by_run` is enough to connect artifact lineage to `REMOTE_RUN.json`, which then connects to inline or sidecar runtime environment and validation evidence; duplicate `run_refs`, `env_refs`, and `dependency_refs` are optional denormalized convenience fields.

### Slice 2: Wire Docs Into Existing Contracts

Update `SKILL.md` minimally:

- Add one short pointer under stage/evidence policy saying P0 runtime-lineage evidence is required when code or experiment evidence is used for paper-facing claims.
- Avoid restating the entire schema in `SKILL.md`; link to `references/runtime_lineage_contract.md`.

Update `references/stage_contracts.md`:

- In `code`, require minimal `runtime_env` and `runtime_validation` evidence for launch-ready experiments, either inline in `EXPERIMENT_MANIFEST.json` or by optional sidecar reference.
- In `experiment`, require `REMOTE_RUN.status`, `harvest.status`, result refs, and minimal artifact lineage for promoted results.
- Preserve the current rule that historical failed or non-promoted `REMOTE_RUN` files cannot satisfy new active readiness.

Update `references/job_execution_packet_schema.md`:

- Add runtime-lineage expected outputs to code and experiment execution packets.
- State that inline `runtime_env` and `runtime_validation` are preferred. Optional sidecar files may be written only under `.autoreskill/coder/`, and artifact lineage remains under `.autoreskill/artifacts_index.json`.

Update `references/source_traceability.md`:

- Extend traceability from source-to-implementation to source-code-run-environment-artifact lineage.
- Keep the OpenClaw-style traceability language intact.

Avoid updating `references/command_surface.md` unless a new command is unavoidable. The expected implementation uses existing `goal.py evidence`, `goal.py validate`, and `contract_lint.py`.

### Slice 3: Extend Job Packet Output Specs

Modify `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_tick.py`.

For the `code` stage execution spec, add expected output language:

- `.autoreskill/coder/experiments/**/EXPERIMENT_MANIFEST.json` should carry inline `runtime_env` and `runtime_validation` for launch-ready tracks, or references to optional `.autoreskill/coder/ENV_SPEC.json` and `.autoreskill/coder/ENV_VALIDATION.json` sidecars.
- `.autoreskill/coder/COMPUTE_PROVIDER_LEDGER.json` is only an optional output when a project needs to compare or reuse multiple compute providers.

For the `experiment` stage execution spec, add constraints:

- `REMOTE_RUN.json` must include inline or referenced runtime env and validation evidence; provider identity may be embedded in either place.
- `REMOTE_RUN.json` must include minimal run `status` and `harvest` fields for promoted finished runs.
- promoted experiment rows must have minimal artifact lineage in `.autoreskill/artifacts_index.json`.

Do not change job packet routing or introduce a new queue.

### Slice 4: Add Focused Contract Lint

Modify `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/contract_lint.py`.

Add one public helper with a name close to:

- `validate_runtime_lineage_contract(project_root, stage, data)`

Inside it, use private local helpers only where they simplify parsing. Do not expose several new public lint entry points until implementation proves they are needed.

The helpers should:

- Load JSON defensively.
- Report paths and missing fields clearly.
- Reuse existing lint result structures and severity conventions.
- Treat missing runtime lineage as a warning for old or exploratory projects.
- Treat missing `runtime_env` or `runtime_validation` evidence as an error only when the code stage marks experiments as launch-ready or when current outputs promote experiment metrics into analysis/writing.
- Treat missing run or artifact lineage as an error only for promoted experiment rows, `paper_candidate`, or `paper_ready` evidence.
- Treat `runtime_validation.validation_status=fail` as an error for launch-ready or promoted experiments.
- Treat absent `gpu_witness` as acceptable only if `runtime_env.backend.backend_kind` is `local_cpu` or if `runtime_validation.claim_limit` explains CPU-only validation.
- Treat `REMOTE_RUN.status` before `finished` as an async wait case, not a failed experiment, unless the stage claims terminal metrics.
- Treat `REMOTE_RUN.harvest.status != complete` as an error only when the run is promoted for analysis/writing.
- Treat artifact rows with `claim_permission=paper_ready` as requiring `produced_by_run` and `evidence_refs`; `run_refs`, `env_refs`, and `verification_refs` are optional denormalized fields.

Do not make every artifact row lineage-complete. That would overfit the schema and create noise.

### Slice 5: Surface Lineage In Evidence Export

Modify `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_evidence.py`.

Expected behavior:

- Old `artifacts_index.json` rows still display.
- Rows with lineage show compact fields: claim permission, produced-by run, and evidence refs.
- If lineage is missing for a paper-ready row, show a clear warning in the evidence export.
- Do not mutate artifacts from `goal_evidence.py`; it should remain a reporter/exporter.

### Slice 6: Extend Fixtures

Modify `/Users/iranb/.codex/skills/autoreskill-workflow/scripts/goal_fixture.py`.

When creating a force-ready or experiment-ready fixture, write synthetic examples:

- `.autoreskill/coder/experiments/**/EXPERIMENT_MANIFEST.json` with inline `runtime_env` and `runtime_validation`
- `.autoreskill/coder/REMOTE_RUN.json` or `.autoreskill/coder/experiments/**/REMOTE_RUN.json` with inline or referenced runtime evidence plus minimal run status and harvest fields
- `.autoreskill/coder/EXPERIMENT_LEDGER.json` referencing the run
- `.autoreskill/artifacts_index.json` with at least one paper-candidate or paper-ready result artifact lineage row

Optionally write `.autoreskill/coder/ENV_SPEC.json`, `.autoreskill/coder/ENV_VALIDATION.json`, and `.autoreskill/coder/COMPUTE_PROVIDER_LEDGER.json` only in dedicated sidecar or multi-provider fixtures. Do not make sidecars part of the default force-ready fixture.

Add a negative fixture path inside the tests rather than as a permanent project directory:

- Missing `runtime_validation` inline object and no sidecar reference
- Failed `runtime_validation.validation_status`
- Promoted result with incomplete `REMOTE_RUN.harvest`
- Paper-ready artifact with no `produced_by_run` or no `evidence_refs`

### Slice 7: Regression Tests

Prefer extending existing test scripts before adding a new one. Add a new focused test only if the existing files become confusing.

Required checks:

- Existing minimal hardening fixture still passes.
- Existing paper forensics fixture still passes.
- New inline runtime-lineage fixture passes code and experiment lint.
- New incomplete runtime-lineage fixture fails with specific missing-field messages.
- Old-style fixture without P0 files is not broken for non-promoted exploratory state.
- `goal.py evidence` displays minimal lineage fields without crashing old artifact rows.

Candidate commands:

    cd /Users/iranb/.codex/skills/autoreskill-workflow
    python -m py_compile scripts/*.py tests/*.py
    python tests/run_minimal_hardening_fixtures.py
    python tests/run_paper_forensics_fixtures.py

For focused manual validation:

    cd /Users/iranb/.codex/skills/autoreskill-workflow
    tmpdir=$(mktemp -d)
    python scripts/goal_fixture.py --project "$tmpdir/project" --force-ready
    python scripts/contract_lint.py --project "$tmpdir/project" --stage code --json
    python scripts/contract_lint.py --project "$tmpdir/project" --stage experiment --json
    python scripts/goal.py evidence --project "$tmpdir/project"

If `goal_fixture.py` uses a different CLI shape, inspect `python scripts/goal_fixture.py --help` and update this plan before continuing.

## Validation and Acceptance

This plan is accepted only when all conditions hold:

- The new `runtime_lineage_contract.md` exists and is linked from the existing docs.
- `goal_tick.py` asks code and experiment jobs for runtime lineage without changing stage routing.
- `contract_lint.py` validates environment, run status, harvest, and paper-ready artifact lineage through one public runtime-lineage lint entry.
- Existing tests still pass.
- At least one new passing fixture proves inline minimal runtime lineage.
- At least one optional sidecar fixture proves `ENV_SPEC.json` and `ENV_VALIDATION.json` remain accepted without becoming mandatory.
- At least one new failing fixture proves missing runtime lineage is caught.
- Old exploratory projects without the new files are not hard-blocked unless they claim promoted paper-ready results.
- No new queue, daemon, database, real remote execution, required env sidecars, required provider ledger, or provider credential storage is introduced.
- No test fixture contains real hostnames, tokens, SSH keys, private account IDs, absolute dataset paths, model weights, checkpoints, raw full logs, or secrets.

## Idempotence and Recovery

All edits are local text/script edits. The implementation is idempotent because:

- Re-running tests creates fresh temporary projects.
- New fixture output overwrites only synthetic fixture project files.
- Required runtime-lineage evidence is inline in existing manifest/run files or under `.autoreskill/artifacts_index.json`; optional sidecars stay under `.autoreskill/coder/`, matching existing allowed-write patterns.
- No real jobs are submitted.
- No remote files are deleted or modified.

Recovery steps:

1. If docs are too broad, revert only the new or changed reference sections and keep the plan.
2. If lint becomes noisy, narrow the hard-error conditions to `paper_ready` and promoted experiment results; leave exploratory cases as warnings.
3. If existing tests fail because old fixtures lack runtime lineage, confirm the fixture's claim level before deciding. Old exploratory fixtures should pass or warn; old paper-ready fixtures should be upgraded.
4. If `goal_evidence.py` output becomes cluttered, keep only claim permission, produced-by run, and evidence refs in the summary.
5. If any command surface change was introduced, remove it unless it is demonstrably necessary.

## Risks And Rollback

Risk: Provider ledger becomes a second scheduler.

Mitigation: The provider ledger is optional evidence only. It cannot allocate resources, queue jobs, or authorize execution.

Rollback: Remove provider scheduling-like fields and keep only provider identity, backend kind, artifact policy, and resource summary.

Risk: Artifact lineage becomes mandatory for every artifact.

Mitigation: Hard requirements apply only to `claim_permission=paper_ready`, promoted result artifacts, or analysis/writing artifacts that cite experiment metrics.

Rollback: Convert broad artifact errors into warnings and enforce only paper-ready rows.

Risk: `REMOTE_RUN` run state duplicates async job state.

Mitigation: Do not introduce a separate lifecycle field in V0. Use `REMOTE_RUN.status` only for `planned`, `running`, `finished`, or `failed`; keep async waiting governed by existing async/job policy.

Rollback: Keep run status display-only except for promoted terminal metrics.

Risk: Existing projects fail unexpectedly.

Mitigation: Additive schema and severity gating. Old exploratory projects warn instead of fail.

Rollback: Add compatibility guard in `contract_lint.py` that detects missing P0 files and downgrades to warning unless claim promotion is detected.

Risk: The P0 contract captures private infrastructure details.

Mitigation: Use display names, provider IDs, and credential policy fields; never store tokens, SSH keys, or secrets.

Rollback: Redact provider ledger fields and keep only backend kind plus local private config reference.

Risk: Runtime environment sidecars become mandatory boilerplate.

Mitigation: V0 accepts inline `runtime_env` and `runtime_validation` in existing manifest/run files. Sidecars are optional only for shared environments or long validation records.

Rollback: Remove sidecar fixture expectations and keep only inline runtime evidence in lint.

## Concrete Steps

1. Re-read target files and confirm no overlapping schema names exist.
2. Add `references/runtime_lineage_contract.md` with compact schemas and compatibility rules.
3. Patch `SKILL.md`, `stage_contracts.md`, `job_execution_packet_schema.md`, and `source_traceability.md` with links and minimal new rules.
4. Patch `goal_tick.py` so code and experiment job packets request inline runtime evidence first, with sidecars only as optional references.
5. Patch `contract_lint.py` with one runtime-lineage validation entry and severity gating.
6. Patch `goal_evidence.py` to display lineage fields when present.
7. Patch `goal_fixture.py` to emit minimal synthetic inline runtime-lineage evidence for ready fixtures.
8. Extend fixture tests with passing and failing runtime-lineage cases.
9. Run syntax checks and both existing fixture suites.
10. Run a focused manual fixture through `contract_lint.py` and `goal.py evidence`.
11. Update `Progress`, `Surprises & Discoveries`, and `Outcomes & Retrospective`.
12. Re-run the overdesign review below and remove any added mechanism that is not necessary for the three P0 outcomes.

## Artifacts and Notes

- `/Users/iranb/.codex/skills/autoreskill-workflow/plans/2026-07-03-autoreskill-p0-claude-science-hardening.md`: this living plan; it records P0 scope, overdesign review, implementation slices, validation, and rollback.
- Planned `/Users/iranb/.codex/skills/autoreskill-workflow/references/runtime_lineage_contract.md`: compact runtime-lineage contract. It should prove schema shape and compatibility rules, not become a second workflow manual.
- Planned inline `runtime_env`: per-track or per-run runtime environment evidence, usually embedded in `EXPERIMENT_MANIFEST.json` or `REMOTE_RUN.json`.
- Planned inline `runtime_validation`: validation evidence proving the environment is usable for launch-ready or promoted experiment claims.
- Optional planned `.autoreskill/coder/ENV_SPEC.json` and `.autoreskill/coder/ENV_VALIDATION.json`: sidecar representations for shared or long runtime evidence.
- Planned `.autoreskill/coder/REMOTE_RUN.json` or `.autoreskill/coder/experiments/**/REMOTE_RUN.json`: per-run status and harvest evidence.
- Planned `.autoreskill/artifacts_index.json` lineage fields: artifact-to-run evidence for paper-ready or promoted result artifacts.

## Interfaces and Dependencies

The implementation must preserve these interfaces:

- `python scripts/contract_lint.py --project <path> --stage <stage> --json`: remains the hard gate entry point; runtime lineage is validated through this path.
- `python scripts/goal.py evidence --project <path>`: continues to export evidence and artifact summaries; lineage display is additive.
- `goal_tick.py` job packets: still use existing job packet schema, `allowed_writes`, `outputs`, and `acceptance_contract`; runtime-lineage requests are output hints, not a new dispatcher.
- `artifacts_index.json`: remains a JSON artifact catalog; new lineage fields are additive and required only for paper-ready or promoted result artifacts.
- `REMOTE_RUN.json`: remains the run evidence file; V0 adds minimal `status`, inline-or-referenced runtime evidence, and harvest fields without becoming an async queue.
- `ENV_SPEC.json` and `ENV_VALIDATION.json`: optional local project evidence files under `.autoreskill/coder/`, not required when inline `runtime_env` and `runtime_validation` are present.
- Optional `COMPUTE_PROVIDER_LEDGER.json`: only for multi-provider projects; no code path may require it for single-provider claim audit.

## Optimization Review After Drafting

The first P0 draft was intentionally reviewed for overdesign before implementation. A second first-principles pass tightened the plan around the minimum paper-claim audit chain: artifact -> run -> environment -> validation -> harvested result. A third pass made the plan inline-first so it extends the current autoreskill artifacts instead of forcing new sidecar files.

- Overdesign risk: adding an endpoint registry would duplicate provider management.
  Optimization: removed from P0. Provider/backend identity is embedded in inline `runtime_env` or `REMOTE_RUN.json`; `COMPUTE_PROVIDER_LEDGER.json` is optional.

- Overdesign risk: requiring `ENV_SPEC.json` and `ENV_VALIDATION.json` for every project would duplicate existing `EXPERIMENT_MANIFEST.json` and `REMOTE_RUN.json`.
  Optimization: V0 is inline-first. Sidecars are accepted but optional.

- Overdesign risk: adding a pending-action queue would duplicate existing async/job policy.
  Optimization: removed from P0. Keep `REMOTE_RUN.status` as run evidence only, with four states: `planned`, `running`, `finished`, and `failed`.

- Overdesign risk: enforcing fully denormalized lineage on every artifact would make normal workflow noisy.
  Optimization: enforce minimal lineage only for promoted result artifacts and paper-ready claims.

- Overdesign risk: adding connector permissions to roles would expand `role_roster.md` beyond current write-scope design.
  Optimization: defer role/connector permissions to P1 unless a concrete failure motivates it.

- Overdesign risk: introducing new commands would increase command-surface maintenance.
  Optimization: use existing `goal.py evidence`, `goal.py validate`, and `contract_lint.py`; update `command_surface.md` only if implementation proves a new command is unavoidable.

- Overdesign risk: exposing several new contract-lint helper APIs would create maintenance surface before the structure is proven.
  Optimization: add one public runtime-lineage validation entry and keep internal parsing helpers private.

Final optimized P0 shape:

- One compact inline-first reference contract.
- Small doc links in existing contracts.
- One narrow lint entry under existing `contract_lint.py`.
- Job packet output hints under existing `goal_tick.py`, preferring inline fields in existing manifests and run files.
- Evidence display under existing `goal_evidence.py`.
- Synthetic fixture coverage under existing test harness.

This is the minimum implementation that absorbs the useful Claude Science design without replacing the current autoreskill architecture.

## ExecPlan Self-Audit

Rubric score after second first-principles optimization: 19 / 20.

- User result: 2 / 2. The observable outcome is a project whose paper-ready experiment artifacts can be traced to run, runtime environment, validation, and harvest evidence.
- Self-contained: 2 / 2. The plan names relevant files, current architecture, expected artifacts, and implementation commands.
- Current state: 2 / 2. The plan records existing stage contracts, job packets, evidence files, and lint entry points.
- Scope boundary: 2 / 2. Non-goals rule out new queues, daemons, provider management, connector permissions, and remote execution.
- Work slices: 2 / 2. Each slice is independently editable and testable.
- Acceptance: 2 / 2. Acceptance requires existing regression tests, positive fixture, negative fixture, and evidence export.
- Recovery: 2 / 2. The plan names idempotent local edits, temp fixtures, rollback, and compatibility gates.
- Risk control: 2 / 2. Risks have signals, mitigations, and rollback paths, including privacy and schema-noise risks.
- Progress log: 2 / 2. The living progress section records completed analysis and pending implementation.
- Decisions/discoveries: 1 / 2. Decisions are auditable, but the exact inline-versus-sidecar lint severity thresholds may still need one implementation pass before they are fully proven.

No key dimension has a zero score. Risk control is full-score because this P0 touches stage gating and paper-claim evidence; the plan explicitly protects old exploratory projects, avoids private infrastructure leakage, and keeps all hard authority in `contract_lint.py`.

## Revision Notes

- 2026-07-03 Asia/Shanghai: Applied first-principles overdesign review. `COMPUTE_PROVIDER_LEDGER.json` became optional, `ENV_SPEC.json` was split into required and optional fields, the earlier run lifecycle concept was replaced with minimal `REMOTE_RUN.status`, artifact lineage was shortened to `produced_by_run` plus `evidence_refs`, and lint was reduced to one public runtime-lineage entry.
- 2026-07-05 Asia/Shanghai: Applied second first-principles overdesign review. Runtime environment and validation evidence became inline-first in `EXPERIMENT_MANIFEST.json` or `REMOTE_RUN.json`; `ENV_SPEC.json` and `ENV_VALIDATION.json` became optional sidecars; `paper_claim_allowed`, `terminal_status`, `experiment_ledger_ref`, and `artifact_id` were removed from required V0 fields where they duplicated existing authority or identity.
- 2026-07-05 Asia/Shanghai: Removed another schema-level duplication: `runtime_env.validation_ref` and `runtime_validation.validation_id` are optional because inline validation evidence is already directly attached to the manifest or run record.
