---
name: autoreskill-experiment-plan
description: OpenClaw-aligned experiment planning skill for portable AutoResearch. Use to convert PaperNexus-backed ideas and proposal_graph_session full-paper idea bundles into INNOVATION_PACKET.json, EXPERIMENT_REVIEW_PACKET.json, baseline-code-first one-variable experiment plans, resource-constrained DEHB/HPO policies for PARAM mechanisms, local-vs-AutoDL GPU backend decisions, dataset/code path mappings, compute budgets, falsifiers, and prelaunch gates.
metadata:
  short-description: Plan baseline-first experiments
---

# Experiment Plan

This skill turns a selected ideation idea into an executable experiment plan. Ideation may select a promising brainstormed idea with evidence debt; this skill is where novelty, baseline, protocol, PaperNexus support, and falsifier gaps must be closed before launch.

When the selected idea was generated from a committed PaperNexus `proposal_graph_session`, consume that bundle as the strongest upstream idea artifact. It can supply the hypothesis, mechanism, method sketch, novelty contrast, evaluation protocol, risk map, falsification route, must-cite evidence, controller trace, and proposal markdown, but it does not replace baseline-code-first planning or the launch gates below.

## Direct Authority

`orchestrator/INNOVATION_PACKET.json` is the stage authority. `planner/EXPERIMENT_REVIEW_PACKET.json` is the prelaunch gate.
`orchestrator/TRACK_PLAN_MATRIX.json` is the bounded explore/exploit handoff from `idea_gate`; it converts one primary plus alternate `IDEA_TRACK_SEEDS.json` rows into `ready`, `blocked`, `diagnostic_only`, or `parked` experiment tracks. A seed row or matrix row is not launch approval.

This stage must also produce the full user-facing innovation story directory:

```text
.autoreskill/user_view/innovation_story/
  00_STORYLINE_DESIGN.md
  01_METHOD_INNOVATION_STORY.md
  02_CLAIM_EVIDENCE_MAP.md
```

These files are derived explanatory artifacts for the user, not launch authorities. They must translate the selected idea into a coherent paper story and method-formation narrative: the current field supplies the problem, baseline/protocol, and reviewer-risk anchor; the main method mechanism should remain grounded in near-neighbor, far-neighbor, proposal-graph, external-domain, or cross-lane transfer evidence. Do not reduce them to contribution bullets or module inventories.

The selected idea must remain a paper-level bundle, not collapse into one module. `INNOVATION_PACKET.json` must preserve `paper_innovation_bundle` with at least three mutually necessary innovation points: problem/protocol/evaluation, method/mechanism, and training/integration/analysis/validation. It must also preserve `paper_storyline` with the thesis, opening tension, hidden cause, method-as-resolution, proof ladder, reviewer defense, and 5-7 step narrative spine. If planning cannot preserve this bundle, return to `idea_gate` for innovation repair instead of launching a weak single-point experiment.

Required authority fields:

- selected idea fragment id
- selected experiment idea id from `ideation/EXPERIMENT_IDEA_POOL.json`
- pre-idea evidence gate path from `ideation/PRE_IDEA_EVIDENCE_GATE.json`
- innovation slot map path from `ideation/INNOVATION_SLOT_MAP.json`
- consumed innovation slot ids that explain which challenge/insight/transfer evidence drove the selected idea
- proposal graph session path, manifest path, committed subgraph id, proposal artifact paths, and controller trace paths when the selected idea cites `proposal_session_ref`
- innovation search contract: idea-bound mechanism, mechanism type, track id, expected effect, falsifier, ablation/confirmation requirements, and initial promotion stage
- HPO search policy: when `mechanism_type="PARAM"` or a target sweep is planned,
  record `hpo_search_policy` in both packets using the resource-constrained DEHB
  contract from `references/resource_constrained_dehb_policy.md`; linear/grid
  tuning and seed-as-search-axis plans are launch blockers
- primary method source role, neighbor transfer mechanism, target-domain anchor, and target-domain method overlap risk for the selected idea
- paper innovation bundle with at least three mutually necessary innovation points and their source roles, evidence refs, closest-prior deltas, story roles, and validation plans
- paper storyline with thesis, opening tension, hidden cause, method-as-resolution, proof ladder, reviewer risk/defense, and narrative spine
- supporting idea fragment ids
- baseline
- baseline code decision: exact codebase/artifact/revision/path, train/eval entrypoints, and rationale
- compute backend decision: local connectable GPU or AutoDL GPU, with probe/capacity evidence and paid-resource policy
- dataset requirement inventory: all datasets needed for feasibility, ablation, stress, confirmation, and final-scale claims, with baseline support, availability, scale, protocol, and claim role recorded before any first-run selection
- dataset runtime plan: candidate datasets, scale class, estimated runtime per run, feasibility-first dataset order, maximum-dataset deferral policy, and promotion/escalation criteria
- dataset/code path mapping for the selected backend, including data roots, code root, output directory, checkpoint directory, and persistent artifact location
- locked metric suite / `metric_policy`: primary metric, every protocol metric component, predeclared composite or stress metric when applicable, material-regression tolerance, candidate-support rule, and promotion rule. For protocols such as GCD with `All/Old/New`, record all components and matched deltas; `New` alone is not sufficient for candidate or promoted evidence when `All`, `Old`, composite, calibration, tail, unknown-K, or other required metrics regress or are missing.
- stability seed policy: `stability_seed_policy.max_random_seeds <= 3`, planned seed count, planned random seeds when known, and a claim rule explaining that single-seed evidence is pilot-only unless supported by ablation/confirmation. This caps experiment random seeds and does not apply to `IDEA_TRACK_SEEDS` track candidates.
- fixed budget
- one-variable change
- dataset or benchmark
- falsifier or failure condition
- PaperNexus idea evidence export path
- PaperNexus proposal evidence export path when using `proposal_graph_session`
- selected idea evidence import/material gate: status, triage reference, PaperNexus MCP attempts, material refs, evidence ids, launch block, and claim limits
- source-backed evidence boundaries
- controller innovation brief and design review when available

## Innovation Search Contract

Every launchable plan must bind the experiment to one explicit innovation mechanism, not just a metric target. Both packets must contain `innovation_search_contract` with:

- `selected_idea_id`, `track_id`, `innovation_mechanism`, and `mechanism_type` (`ALGO`, `CODE`, or `PARAM`)
- `primary_method_source_role`, `neighbor_transfer_mechanism`, `target_domain_anchor`, and `target_domain_method_overlap_risk`
- `one_variable_change`, `expected_effect`, `falsifier`
- `ablation_required=true`, `confirmation_required=true`
- `promotion_stage="candidate"` for the first run

For top-tier method claims, `primary_method_source_role` should be `near_neighbor`, `far_neighbor`, `cross_lane_recombination`, `proposal_graph_transfer`, or `external_domain_transfer`. A target-domain-only mechanism is launchable as a baseline/ablation or low-claim diagnostic, but it should not be the main method claim unless `current_field_absence_evidence` and closest-prior closure show the mechanism has not appeared in the current field.

`EXPERIMENT_REVIEW_PACKET.json` must also include `promotion_gate`. A single positive run is only candidate evidence; it cannot become a promoted manuscript improvement until a linked ablation or confirmation run supports the same mechanism under the locked protocol. If budget prevents that, downgrade the claim to pilot evidence instead of promoting it.

The `promotion_gate` must evaluate the locked `metric_policy`, not an isolated favorable component. A run is positive only if the predeclared composite/vector rule passes and no material-regression check fails. A single component may be the decision metric only when the benchmark protocol itself declares it as the sole canonical metric and the packet records that fact.

Random-seed stability validation is capped at three experiment seeds. Prefer
one pilot seed followed by ablation/confirmation; use 2-3 seeds only when
stability is the explicit validation question. Do not plan a fourth random seed
for stability validation. `IDEA_TRACK_SEEDS` remain idea/track candidates and
do not increase the random-seed budget.

For `PARAM` mechanisms, also record `hpo_search_policy` at the packet top level
or inside `innovation_search_contract`. Use
`search_method="dehb_resource_constrained"` by default: a small differential
evolution population proposes mixed continuous/discrete candidates, Hyperband
rungs allocate low fidelity to most trials, and only the top 1-2 full-resource
survivors may enter ablation/confirmation. The resource axis must be epochs,
steps, or data fraction, never seed count. Read
`references/resource_constrained_dehb_policy.md` before designing PARAM search.

## Default Planning Order

Run these steps before continuing the remaining experiment-plan workflow:

1. Resolve the selected idea evidence import/material gate.
   - First confirm `ideation/PRE_IDEA_EVIDENCE_GATE.json` exists with `status="passed"` and that `ideation/INNOVATION_SLOT_MAP.json` contains the slots consumed by the selected idea.
   - If the gate is `status="degraded_requires_user_approval"` with valid user approval, treat the selected idea as speculative. Copy `claim_limits` and `evidence_boundary` into both planning packets, set selected-idea evidence closure as a launch blocker, and do not make novelty, SOTA, closest-prior, or formal performance claims until PaperNexus material closure succeeds.
   - If the idea pool was generated without the pre-idea gate, return to pre-idea evidence expansion or mark the project `legacy_requires_evidence_reconciliation`; do not silently accept metadata-only idea provenance.
   - If the selected idea has `evidence_maturity` below `plan_ready`, or `papernexus/LITERATURE_DISCOVERY_TRIAGE.json` marks selected-idea papers as `import_recommended`, use the screened `PAPER_SELECTION_SCORECARD.json` and `GRAPH_IMPORT_PLAN.json` first, then use `papernexus-remote` to import/supplement closest priors and request material or split-reading packs.
   - If the selected idea has `proposal_session_ref`, run `proposal_graph_session_lint.py`. A committed proposal graph can satisfy selected-idea source support and controller-trace evidence, but any unresolved proposal risk, missing baseline/protocol detail, or launch-blocking evidence boundary must remain in `evidence_import_gate` or prelaunch blockers.
   - Do not choose claim downgrade, dry-run-only constraints, or launch-precondition wording until the PaperNexus MCP attempt has been made or feature detection shows it is unavailable.
   - If the import/material work is queued, record `evidence_import_gate.status="async_wait"` with job/status refs and keep `launch_blocked=true` until polling completes.
   - If MCP is unavailable, import fails, full text is unavailable, license/budget blocks import, or retries are exhausted, record `status="blocked"`, the exact fallback reason, `launch_blocked=true`, and claim limits. Code dry-run handoff may continue only under this blocked gate; novelty/SOTA/closest-prior claims and formal training launch remain blocked.
   - If no import is required or the closure succeeds, record `status="not_required"` or `status="passed"` with material refs and evidence ids in both packets.
2. Determine the exact baseline code for the selected idea.
   - Prefer a baseline codebase already present in the project workspace or explicitly referenced by the idea/literature evidence.
   - If using an upstream or official repo, pin the URL/artifact and revision before launch.
   - Record `baseline_code` in both packets with `code_id`, `source_type`, `source_ref`, `revision`, `resolved_path`, `train_entrypoint`, `eval_entrypoint`, `selection_rationale`, and `locked: true`.
   - Do not let later agents search for or substitute a different baseline after this field is locked. If the baseline code cannot be determined, stop and return to evidence/ideation/user input rather than filling in a convenient baseline.
3. Decide whether the experiment should use AutoDL GPU or a locally connectable GPU.
   - Check whether the current machine or a user-provided SSH target has a usable GPU with the required CUDA/framework stack.
   - If local/connectable GPU is adequate, set `compute_backend.backend` to `local_gpu` and record the probe evidence.
   - If AutoDL is required, use `autodl-pro-gpu-api` for the lifecycle plan: check reusable instances first, default to Beijing, respect paid `--execute --allow-paid` guards, and do not fallback outside Beijing when `/root/autodl-fs` is required.
   - Planning may create a dry-run/provision handoff, but paid AutoDL creation must stay gated by the AutoDL skill and automation budget policy.
4. Map dataset and code paths for the selected backend.
   - Record `path_mapping` with `selected_backend`, `logical_dataset_id`, `code_root`, `data_root`, `output_dir`, `checkpoint_dir`, `persistent_output_dir`, and the environment variables the implementation must use.
   - For AutoDL, prefer `/root/autodl-fs/datasets/<dataset>` as the persistent source, `/root/autodl-tmp/datasets/<dataset>` as the training data root, `/root/autodl-tmp/code/<project>` as the code root, `/root/autodl-tmp/outputs/<run>` for live outputs, and `/root/autodl-fs/outputs/<run>` for retained artifacts.
   - For local GPU, map to concrete local or SSH-mounted paths and keep them configurable; do not hardcode AutoDL paths.
5. Build the dataset requirement inventory before selecting the launch dataset.
   - First list every dataset required by the paper claim, selected idea, closest priors, baseline scripts, benchmark norms, stress tests, ablations, and confirmation route. Record this as `dataset_requirement_inventory.required_datasets[]` before writing `dataset_runtime_plan`.
   - Each required dataset row must include `dataset_id`, `dataset_name`, `claim_role` (`method_validation`, `ablation`, `stress`, `confirmation`, `final_scale`, or `comparison_only`), `reason_required`, `baseline_supported`, `availability`, `scale_class`, `num_classes`, `train_samples`, `eval_samples`, `native_protocol_ref`, `native_epochs_or_steps`, `native_warmup_or_schedule`, `data_root_or_probe`, and `selection_status`.
   - Exclude a dataset from first-run selection only with explicit `selection_status="rejected"` and a concrete `rejection_reason`, such as not baseline-supported, missing data, incompatible with the method's target claim, or explicit user approval to defer it. Do not reject a smaller dataset merely because a larger dataset path is already documented.
   - Set `dataset_requirement_inventory.method_validation_dataset_id` to the smallest available baseline-supported dataset whose `claim_role` is `method_validation`, `ablation`, or `stress`. Size is ordered first by `scale_class` (`small_multiclass` before `medium_multiclass` before `large_full_scale`), then by `train_samples`, then by estimated GPU hours.
   - If the smallest available required dataset is not selected first, record `dataset_requirement_inventory.non_smallest_first_exception_reason` as `user_approved_non_smallest`, `dataset_invalid_for_selected_claim`, or `no_required_small_dataset_available`; otherwise launch is blocked.
   - After the inventory is complete, build the dataset runtime and feasibility plan from the inventory. Estimate per-run wall time and GPU hours for every required candidate dataset. Use prior local logs when available; otherwise estimate from sample count, classes, epochs, batch size, evaluation frequency, and backend GPU evidence.
   - Before accepting a `medium_multiclass` or `large_full_scale` first run, actively probe the locked baseline's supported small multi-class datasets through its scripts/configs/data modules and the selected backend's dataset roots. For CV/GCD projects this normally includes CUB, CIFAR-10/100, Stanford Cars, Aircraft, or other baseline-supported small/fine-grained datasets when relevant. Do not omit a baseline-supported small dataset merely because the project `AGENTS.md` only documents a larger verified dataset path.
   - Record the probe as `dataset_runtime_plan.small_dataset_probe` with datasets checked, script/config evidence, remote/local dataset paths, availability, and rejection rationale. If a baseline-supported small dataset such as CUB is available, it must be the first feasibility dataset unless the packet records explicit user approval or a source-backed reason that it is invalid for the selected idea.
   - Classify each dataset as `small_multiclass`, `medium_multiclass`, or `large_full_scale`; record class count, train/eval sample counts, intended epochs/steps, expected minutes per epoch, expected total wall time, expected GPU hours, and estimation basis.
   - For innovation feasibility, set `dataset_runtime_plan.feasibility_first_dataset_id` to `dataset_requirement_inventory.method_validation_dataset_id`. Prefer the locked baseline's native protocol for that smallest selected dataset, including epochs and warmup, unless a shorter run is explicitly marked `diagnostic_only`. Do not start with a larger dataset unless the inventory records the non-smallest exception and the runtime plan records the corresponding exception.
   - Record `dataset_runtime_plan` in both `INNOVATION_PACKET.json` and `EXPERIMENT_REVIEW_PACKET.json` with `candidate_datasets`, `feasibility_first_dataset_id`, `first_run_scale_class`, `largest_dataset_id`, `largest_dataset_deferred`, `escalation_criteria`, and `runtime_risk`.
   - Treat the largest dataset as confirmation/final-scale evidence after the feasibility run passes smoke, metric parser, and mechanism sanity checks. A failed small-scale feasibility run should route to repair/track switch rather than spending the full-scale budget by default.
6. Continue the baseline-first one-variable experiment plan, cost budget, falsifiers, and prelaunch gates.

## Planning Rules

- Evidence import/material gate first; after that gate is passed, not required, or explicitly marked launch-blocked for dry-run-only work, lock baseline code before baseline protocol.
- Record `stability_seed_policy` in both planning packets with `max_random_seeds=3`. If the plan only has one random seed, mark stronger claims as pending ablation/confirmation or pilot-only; if it needs more than three seeds, downgrade or switch track instead of expanding stability validation.
- For `PARAM` or target-sweep plans, record `hpo_search_policy` in both planning
  packets and use the resource-constrained DEHB policy. Search over at most 3-6
  important dimensions, protect seed/dataset/split/baseline/metric from search,
  set rungs such as 10% -> 30% -> 100%, cap full-resource survivors at 1-2 by
  default, and treat scout results as non-promotable pilot evidence.
- Consume the selected optimization idea from `autoreskill-ideation-panel` at `ideation/EXPERIMENT_IDEA_POOL.json`. Do not generate the pool in experiment planning.
- Consume the selected idea's `pre_idea_evidence_gate_path`, `innovation_slot_map_path`, and `innovation_slot_refs` into both `INNOVATION_PACKET.json` and `EXPERIMENT_REVIEW_PACKET.json`.
- Preserve the selected idea's `primary_method_source_role`, `neighbor_transfer_mechanism`, `target_domain_anchor`, and `target_domain_method_overlap_risk`. Do not rewrite a near/far-neighbor transfer idea into a target-domain-only tweak during planning.
- Preserve the selected idea's `paper_contribution.innovation_bundle` as `paper_innovation_bundle` and its `paper_contribution.storyline` as `paper_storyline`. Do not simplify a three-innovation paper thesis into a single metric, module, or heuristic.
- Consume the selected idea's proposal graph provenance into both packets when present: `proposal_graph_session_path`, `proposal_graph_session_manifest_path`, `proposal_committed_subgraph_id`, `proposal_artifact_paths`, `proposal_controller_trace_paths`, and `proposal_evidence_export_path`.
- If the pool is missing, malformed, or has no selected idea, return to `ideation` or `idea_gate`; do not patch around it by inventing a planning-stage pool.
- If selected-idea evidence debt exists, PaperNexus import/material work is a hard gate, not a default downgrade path. Use `papernexus-remote` first; downgrade or launch-precondition constraints are allowed only after an MCP attempt, async queue handoff, feature-detection failure, import failure, full-text/license/budget block, or exhausted bounded retry is recorded in `evidence_import_gate`.
- One variable per main experiment and one logical change per iteration.
- Baseline code, compute backend, path mapping, dataset, locked metric suite / `metric_policy`, evaluation command, data split, and baseline protocol are locked before Coder starts.
- Do not collapse multi-metric protocols into one primary component during planning. Materialize `metric_policy` in `INNOVATION_PACKET.json`, `TRACK_PLAN_MATRIX.json`, and `EXPERIMENT_REVIEW_PACKET.json`, including required metric components, parser fields, composite/stress rule, and material-regression thresholds.
- Dataset requirement inventory and runtime planning are mandatory before Coder starts. `dataset_requirement_inventory` must first summarize all datasets needed for method validation, ablation, stress, confirmation, and final-scale claims. `dataset_runtime_plan` must then estimate runtime for those candidates and set `feasibility_first_dataset_id` to the smallest available baseline-supported required dataset. The first feasibility run is for innovation viability and implementation validation; the largest dataset is reserved for confirmation/final-scale evidence unless no smaller required proxy exists or the user explicitly approves starting larger.
- If a medium/full-scale experiment was launched before a required small-dataset probe, mark that run `off_order_diagnostic` or `candidate_only_no_promotion`, queue an experiment-plan repair, and run the baseline-supported small-dataset feasibility track before promoting any claim from the larger run. The larger run may remain as background diagnostic evidence only if it preserves metric, dataset, evaluation, and one-variable constraints.
- If a frozen-backbone or frozen-feature pilot is allowed, register it explicitly in `EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol` with `protocol_id`, `baseline_code_id`, exact `feature_extractor`/backbone, extraction entrypoint, dataset domains/splits, sampling cap, metric parser, and whether it can support only code readiness or candidate evidence. Do not write broad phrases such as "frozen features/backbone pilot" without this object.
- A frozen-feature pilot must use the locked baseline's feature path or a declared adapter of that baseline. Convenience substitutes such as torchvision ResNet18/ImageNet, sklearn prototype probes, tiny sampled feature caches, or hand-rolled loaders are off-protocol unless the packet explicitly marks them as diagnostic-only and user-approved.
- Reuse the red-line audit from the selected idea, then run a plan-level check for no metric drift, evaluation drift, dataset drift, data leakage, prediction cheating, or training-budget drift.
- Include falsifier and stop rules.
- Use `experiment_cost_materials` when available; otherwise record `cost_evidence_gap`. Include AutoDL paid GPU cost/capacity assumptions when `compute_backend.backend` is `autodl_gpu`.
- Record `idea_pool_path` as `ideation/EXPERIMENT_IDEA_POOL.json` and record the selected `selected_idea_id` in `EXPERIMENT_REVIEW_PACKET.json`.
- Record `proposal_session_ref` from the idea pool in the innovation packet when present; do not flatten the proposal bundle into unsupported prose without artifact paths and committed subgraph id.
- Record the innovation mechanism and promotion gate before implementation starts; no experiment may launch from a metric-only or parameter-only search unless it is tied to an idea-bound mechanism and explicitly marked `PARAM`.
- Update all three `user_view/innovation_story/` files after the packets are internally consistent. `00_STORYLINE_DESIGN.md` should state the belief shift, three-innovation bundle, and proof ladder; `01_METHOD_INNOVATION_STORY.md` should explain where the method came from, why the transfer is legitimate, and how the innovation points depend on each other; `02_CLAIM_EVIDENCE_MAP.md` should map each innovation point to planned evidence, ablations, failure modes, and current claim limits.
- Convert `ideation/IDEA_TRACK_SEEDS.json` into `orchestrator/TRACK_PLAN_MATRIX.json` before prelaunch lint. Keep alternates parked or blocked until their own baseline/protocol/evidence closure is explicit; do not inherit readiness from the primary track.

## Validation

Before `autoreskill-run-experiment`, run:

```bash
python scripts/experiment_materialize.py --project <project-root>
python scripts/track_plan_matrix.py --project <project-root>
python scripts/track_plan_matrix.py --project <project-root> --check
# When the selected idea cites proposal_session_ref:
python ../autoreskill-papernexus-innovation/scripts/proposal_graph_session_lint.py --project <project-root>
python scripts/prelaunch_lint.py --project <project-root>
python scripts/innovation_lint.py --project <project-root>
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage experiment_plan
```

`experiment_materialize.py` refuses to overwrite existing `INNOVATION_PACKET.json` or `EXPERIMENT_REVIEW_PACKET.json` unless `--force` is passed. Use `--force` only when intentionally regenerating after backing up or replacing stale plan authority; do not use it to simplify a detailed packet into a generic scaffold.

The linters block launch when the reviewed packet lacks a passed/not-required evidence import gate, source-backed selected idea support, evidence boundaries, one-variable change, baseline code decision, compute backend decision, path mapping, dataset runtime plan, baseline protocol, locked dataset/eval/metric, falsifiers, stop rules, compute budget, PaperNexus norms, controller/fallback design review, or expected artifacts. They also block when the first feasibility dataset is the largest/full-scale dataset without an explicit smaller-proxy-unavailable or user-approved exception, or when a `PARAM` mechanism lacks a resource-constrained DEHB `hpo_search_policy`.

Read `references/experiment_review_packet_schema.md`,
`references/resource_constrained_dehb_policy.md`, and
`references/baseline_fairness_checklist.md`. Read
`references/experiment_idea_pool.md` only when diagnosing the upstream ideation
pool; do not create that pool in this skill.
