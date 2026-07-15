---
name: autoreskill-implement-experiment
description: Research engineering skill for portable AutoResearch. Use to implement one named experiment track from its per-track INNOVATION_PACKET and EXPERIMENT_REVIEW_PACKET, consume locked baseline-code decisions, GPU backend decisions, and path mappings, then create auditable baseline/proposed experiment bundles.
metadata:
  short-description: Implement reproducible experiment bundles
---

# Implement Experiment

Use only after the named track's
`orchestrator/tracks/<track-id>/INNOVATION_PACKET.json` and
`planner/tracks/<track-id>/EXPERIMENT_REVIEW_PACKET.json` pass lint. The
top-level packet pair is a compatibility projection for the current primary
track only; never use it to implement an alternate or risk-repair track.

The default path is a real baseline/data/GPU-backed experiment bundle. Offline contract-test fixtures belong only in dedicated smoke-test helpers and must never be used as the implementation path for an experiment job.

## Output Layout

```text
.autoreskill/coder/experiments/<track-id>/<experiment-id>/
  EXPERIMENT_MANIFEST.json
  train.py
  evaluate.py
  configs/baseline.yaml
  configs/proposed.yaml
  logs/
  results/
  requirements.txt
  README.md
```

## Rules

- Do not change dataset, locked metric suite / `metric_policy`, or baseline protocol.
- Do not search for another baseline implementation. Use only `baseline_code` locked by `autoreskill-experiment-plan`; if it is missing, ambiguous, unavailable, or incompatible, stop and return to planning.
- The locked baseline must be a real clone/worktree or verified repository snapshot. Do not recreate baseline logic in new files. Proposed changes must be recorded as a patch/diff against the locked baseline clone through `baseline_patch_proof`.
- Do not choose a new compute backend or execution route in implementation. Use the reviewed pair: `local_gpu` with `execution_route=local|ssh|bjtu_hpc`, or `autodl_gpu` with `execution_route=autodl`. Generic SSH remains project-specific; BJTU work must use `$bjtu-hpc` preflight/planning; AutoDL lifecycle work passes to `autodl-pro-gpu-api`. Route metadata is not launch authorization.
- For `external_material`, preserve `external_campaign_ref`, `external_campaign_sha256`, `external_candidate_id`, and `protected_commitment_sha256` from the reviewed packets, keep candidate/fragment/track IDs distinct, and copy the same protected commitment hash into every canonical queue row.
- Do not invent dataset or output paths. Use `path_mapping` from the review packet and expose those paths through configs or environment variables such as `DATA_ROOT`, `OUTPUT_DIR`, and `CKPT_DIR`.
- Do not change the locked evaluation command, data split, metric parser, or metric policy.
- Implement exactly one named track and its selected idea per experiment bundle. Do not mix mechanisms or packet pairs across tracks.
- Preserve `track_id`, `track_role`, `idea_lifecycle_status`, `selection_fingerprint`, both packet refs and semantic hashes, and `evidence_tier_ceiling` in `EXPERIMENT_MANIFEST.json`. An `alternate` or `risk_repair` bundle must remain `evidence_tier=pilot_only`; only an explicit primary reselection followed by a frozen matched-baseline rerun can make it claim-eligible.
- Resolve the packet's `project_execution_passport_ref` and verify its index
  hash plus the named `execution_profile_id`/`execution_profile_sha256`. Carry
  those identities, `innovation_delta_sha256`, and
  `resolved_execution_contract_projection_sha256` into
  `EXPERIMENT_MANIFEST.json`. Shared baseline/data/runtime fields come from that
  profile; the packet may change only its innovation delta. Fail closed on a
  missing, stale, or mismatched profile rather than reconstructing it from prose.
- Keep baseline and proposed paths comparable; proposed code may differ only by the planned logical change.
- Carry the `innovation_search_contract` into `EXPERIMENT_MANIFEST.json`, including `innovation_mechanism`, `mechanism_type`, and `promotion_stage`.
- Carry the planning `metric_policy` into `EXPERIMENT_MANIFEST.json`, configs, run manifests, and result parsers. For multi-metric protocols, extract every locked component and the predeclared composite/stress metric; do not hardcode a single-component summary such as `New` as the launch or ranking result.
- Do not combine multiple mechanisms. If the run is an ablation, only remove/disable the recorded mechanism and set `ablation_of`; if it is a confirmation, repeat the same mechanism and set `confirmation_of`.
- Before writing train/eval code, write `BASELINE_DATA_AUDIT.json` that records locked baseline source, resolved path, train/eval entrypoint existence, dataset roots/manifests, backend, and whether remote upload/run proof is required.
- Before writing proposed logic, verify the baseline clone/worktree and create `baseline_patch_proof` in `EXPERIMENT_MANIFEST.json` or `BASELINE_DATA_AUDIT.json`. It must record `baseline_code_id`, `base_revision`, `patch_path`, `changed_paths`, and `patch_applies_to_baseline=true`.
- Wrapper files such as experiment-local `train.py`/`evaluate.py` are allowed only as thin adapters. They must be declared in `baseline_adapter` and must call the locked baseline entrypoint; the actual method change still needs patch proof against the cloned baseline.
- If the locked data or GPU backend is remote, upload code with the provided SSH connection, synchronize through an approved GitHub private repository, or use `autodl-pro-gpu-api` / `autodl-runner` when `compute_backend.backend=autodl_gpu`. Record upload/sync proof in `REMOTE_UPLOAD.json`.
- GitHub private repository sync is allowed for code/config/patch/script management between local and remote machines. The repository must be private, contain code-only material, and exclude datasets, dataset archives, model weights, checkpoints, raw outputs, runtime logs, credentials, SSH keys, and machine-specific upload/run state by `.gitignore` plus an explicit pre-push/export audit. Record repo URL, privacy, branch, commit SHA, export path, excluded artifact classes, remote checkout path, and sync command in `.autoreskill/coder/CODE_SYNC_LEDGER.json`, `REMOTE_UPLOAD.json`, and `EXPERIMENT_MANIFEST.json.source_state`.
- Run the first proof against real data or a frozen real-feature manifest on the selected GPU backend. Record command, host/instance, paths, commit, return code, and artifact paths in `REMOTE_RUN.json`.
- Do not let a synthetic-only path, random generated data, or `{"ok": true}` smoke test satisfy the code contract. If a historical/debug fixture exists, mark it non-launchable and route back to baseline/data audit.
- Treat environment/data smoke, feature-pipeline smoke, and baseline-aligned experiment launch as different artifacts. A smoke proof may satisfy code readiness only; it must not be reported as a real experiment result or used to choose target sweeps.
- If using real features, consume `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol`. The feature extractor/backbone, split, metric parser, and sampling cap must match that protocol. If the packet does not register a feature protocol, do not introduce ResNet18/torchvision/sklearn/small-model probes; stop and return to `autoreskill-experiment-plan` or record a diagnostic-only blocker.
- Keep random seeds configurable, but cap stability-validation random seeds at
  three. Do not turn `IDEA_TRACK_SEEDS` track candidates into extra experiment
  random seeds.
- Assert key input/output shapes.
- Write logs to stdout and file.
- Run a real-data or real-feature smoke run before reporting launch-ready.
- Record source state in `EXPERIMENT_MANIFEST.json`: git commit when available, diff/status summary, selected idea id, locked protocol, and protected eval/test/metric paths.
- Record `baseline_code`, `compute_backend`, `execution_route`, `path_mapping`, `baseline_data_audit`, `backend_upload`, `remote_run`, `dry_run_kind`, `innovation_search_contract`, `promotion_stage`, and any `ablation_of`/`confirmation_of` link in `EXPERIMENT_MANIFEST.json`; linters treat drift or fixture-only proof as launch-blocking.
- After manifests are written, run `track_implementation_index.py` to create `coder/TRACK_IMPLEMENTATION_INDEX.json`. This index must map every ready or selected `TRACK_PLAN_MATRIX.json` row to manifest paths, baseline audit paths, patch proof status, remote-run proof, and fixture status.
- The implementation index also projects each matrix/manifest passport index,
  execution profile, innovation-delta, and resolved-projection hash so later
  audits can identify drift without treating the index as a new authority.
- If implementation discovers a red-line violation, stop and return to `autoreskill-experiment-plan` instead of repairing by changing the metric policy, data, or eval.

## Execution Order

1. Read the named track's per-track innovation/review packet pair and the current
   job packet. Verify their `track_id`, selected idea, role, lifecycle, selection
   fingerprint, semantic hashes, project-passport index, execution profile,
   innovation delta, and resolved projection agree before touching code.
2. Audit the locked baseline and data:
   - open the locked baseline entrypoints and relevant config/data loaders;
   - verify the baseline code path and entrypoints exist locally or are staged for upload;
   - identify the exact dataset root, split manifest, feature manifest, or remote path from `path_mapping`;
   - write `BASELINE_DATA_AUDIT.json`.
3. Stage code for the selected GPU backend:
   - for SSH/local GPU, use the provided host/path mapping and upload with `rsync`/`scp`, the existing project transfer script, or a GitHub private repo checkout/pull when that repo has passed the code-only audit;
   - for AutoDL, invoke the AutoDL skills for instance lifecycle/upload and use `/root/autodl-tmp` live paths plus durable persistent output paths;
   - write `REMOTE_UPLOAD.json`.
4. Implement comparable baseline/proposed entrypoints around the locked baseline. The proposed path may change only the planned one-variable controller.
5. Run a real-data or real-feature smoke/pilot on the selected backend, persist logs/results, and write `REMOTE_RUN.json`.
6. Run `track_implementation_index.py`, `experiment_drift_lint.py`, and `experiment_real_readiness_lint.py` before marking the job complete.

## Deterministic Helpers

```bash
python scripts/experiment_scaffold.py --project <project-root> --track-id <track-id> --experiment-id <id>
python scripts/track_implementation_index.py --project <project-root>
python scripts/track_implementation_index.py --project <project-root> --check
python scripts/baseline_clone_lint.py --project <project-root> --track-id <track-id>
python scripts/experiment_drift_lint.py --project <project-root>
python scripts/experiment_real_readiness_lint.py --project <project-root>
```

Read `references/experiment_bundle_layout.md` and `references/dry_run_checklist.md`.
