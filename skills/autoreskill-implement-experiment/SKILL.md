---
name: autoreskill-implement-experiment
description: Research engineering skill for portable AutoResearch. Use to implement experiment bundles from INNOVATION_PACKET and EXPERIMENT_REVIEW_PACKET, consume locked baseline-code decisions, local-vs-AutoDL GPU backend decisions, dataset/code path mappings, create manifests, configs, train/evaluate scripts, dry-run logs, and baseline/proposed comparable code.
metadata:
  short-description: Implement reproducible experiment bundles
---

# Implement Experiment

Use only after `INNOVATION_PACKET.json` and `EXPERIMENT_REVIEW_PACKET.json` pass lint.

The default path is a real baseline/data/GPU-backed experiment bundle. Synthetic or toy fixtures are allowed only when the job packet or user explicitly asks for a fixture; they must be marked `fixture=true` and must not satisfy launch readiness.

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

- Do not change dataset, primary metric, or baseline protocol.
- Do not search for another baseline implementation. Use only `baseline_code` locked by `autoreskill-experiment-plan`; if it is missing, ambiguous, unavailable, or incompatible, stop and return to planning.
- The locked baseline must be a real clone/worktree or verified repository snapshot. Do not recreate baseline logic in new files. Proposed changes must be recorded as a patch/diff against the locked baseline clone through `baseline_patch_proof`.
- Do not choose a new compute backend in implementation. Use `compute_backend.backend` from the review packet: `local_gpu` means use the recorded local/SSH GPU assumptions; `autodl_gpu` means implement against the AutoDL path mapping and pass lifecycle work to `autodl-pro-gpu-api`.
- Do not invent dataset or output paths. Use `path_mapping` from the review packet and expose those paths through configs or environment variables such as `DATA_ROOT`, `OUTPUT_DIR`, and `CKPT_DIR`.
- Do not change the locked evaluation command, data split, or metric parser.
- Implement exactly one selected idea per experiment bundle.
- Keep baseline and proposed paths comparable; proposed code may differ only by the planned logical change.
- Carry the `innovation_search_contract` into `EXPERIMENT_MANIFEST.json`, including `innovation_mechanism`, `mechanism_type`, and `promotion_stage`.
- Do not combine multiple mechanisms. If the run is an ablation, only remove/disable the recorded mechanism and set `ablation_of`; if it is a confirmation, repeat the same mechanism and set `confirmation_of`.
- Before writing train/eval code, write `BASELINE_DATA_AUDIT.json` that records locked baseline source, resolved path, train/eval entrypoint existence, dataset roots/manifests, backend, and whether remote upload/run proof is required.
- Before writing proposed logic, verify the baseline clone/worktree and create `baseline_patch_proof` in `EXPERIMENT_MANIFEST.json` or `BASELINE_DATA_AUDIT.json`. It must record `baseline_code_id`, `base_revision`, `patch_path`, `changed_paths`, and `patch_applies_to_baseline=true`.
- Wrapper files such as experiment-local `train.py`/`evaluate.py` are allowed only as thin adapters. They must be declared in `baseline_adapter` and must call the locked baseline entrypoint; the actual method change still needs patch proof against the cloned baseline.
- If the locked data or GPU backend is remote, upload code with the provided SSH connection, or use `autodl-pro-gpu-api` / `autodl-runner` when `compute_backend.backend=autodl_gpu`. Record upload proof in `REMOTE_UPLOAD.json`.
- Run the first proof against real data or a frozen real-feature manifest on the selected GPU backend. Record command, host/instance, paths, commit, return code, and artifact paths in `REMOTE_RUN.json`.
- Do not let a synthetic-only path, random generated data, or `{"ok": true}` smoke test satisfy the code contract. Synthetic fixtures are for debugging only and must be explicitly marked non-launchable.
- Treat environment/data smoke, feature-pipeline smoke, and baseline-aligned experiment launch as different artifacts. A smoke proof may satisfy code readiness only; it must not be reported as a real experiment result or used to choose target sweeps.
- If using real features, consume `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol`. The feature extractor/backbone, split, metric parser, and sampling cap must match that protocol. If the packet does not register a feature protocol, do not introduce ResNet18/torchvision/sklearn/small-model probes; stop and return to `autoreskill-experiment-plan` or record a diagnostic-only blocker.
- Keep random seeds configurable.
- Assert key input/output shapes.
- Write logs to stdout and file.
- Run a real-data or real-feature smoke run before reporting launch-ready.
- Record source state in `EXPERIMENT_MANIFEST.json`: git commit when available, diff/status summary, selected idea id, locked protocol, and protected eval/test/metric paths.
- Record `baseline_code`, `compute_backend`, `path_mapping`, `baseline_data_audit`, `backend_upload`, `remote_run`, `dry_run_kind`, `innovation_search_contract`, `promotion_stage`, and any `ablation_of`/`confirmation_of` link in `EXPERIMENT_MANIFEST.json`; linters treat drift or fixture-only proof as launch-blocking.
- If implementation discovers a red-line violation, stop and return to `autoreskill-experiment-plan` instead of repairing by changing the metric, data, or eval.

## Execution Order

1. Read `INNOVATION_PACKET.json`, `EXPERIMENT_REVIEW_PACKET.json`, and the current job packet.
2. Audit the locked baseline and data:
   - open the locked baseline entrypoints and relevant config/data loaders;
   - verify the baseline code path and entrypoints exist locally or are staged for upload;
   - identify the exact dataset root, split manifest, feature manifest, or remote path from `path_mapping`;
   - write `BASELINE_DATA_AUDIT.json`.
3. Stage code for the selected GPU backend:
   - for SSH/local GPU, use the provided host/path mapping and upload with `rsync`/`scp` or the existing project transfer script;
   - for AutoDL, invoke the AutoDL skills for instance lifecycle/upload and use `/root/autodl-tmp` live paths plus durable persistent output paths;
   - write `REMOTE_UPLOAD.json`.
4. Implement comparable baseline/proposed entrypoints around the locked baseline. The proposed path may change only the planned one-variable controller.
5. Run a real-data or real-feature smoke/pilot on the selected backend, persist logs/results, and write `REMOTE_RUN.json`.
6. Run `experiment_drift_lint.py` and `experiment_real_readiness_lint.py` before marking the job complete.

## Deterministic Helpers

```bash
python scripts/experiment_scaffold.py --project <project-root> --experiment-id <id>
python scripts/baseline_clone_lint.py --project <project-root>
python scripts/experiment_drift_lint.py --project <project-root>
python scripts/experiment_real_readiness_lint.py --project <project-root>
```

Read `references/experiment_bundle_layout.md` and `references/dry_run_checklist.md`.
