---
name: autoreskill-experiment-plan
description: OpenClaw-aligned experiment planning skill for portable AutoResearch. Use to convert PaperNexus-backed or committed external-material ideas into INNOVATION_PACKET.json, EXPERIMENT_REVIEW_PACKET.json, baseline-code-first one-variable experiment plans, resource-constrained DEHB/HPO policies for PARAM mechanisms, compute-backend and execution-route decisions, dataset/code path mappings, compute budgets, falsifiers, and prelaunch gates.
metadata:
  short-description: Plan baseline-first experiments
---

# Experiment Plan

This skill turns the one selected paper primary and any explicitly admitted
alternate/risk-repair tracks into separate executable experiment plans. Exactly
one track remains the paper primary; at most three non-primary tracks may receive
bounded `pilot_only` plans. This stage closes novelty, baseline, protocol, source
support, and falsifier gaps per track before launch. A missing
`evidence_source_mode` remains the legacy PaperNexus route. `external_material`
consumes the committed non-PaperNexus campaign/lint hashes and a passed
`ideation/PANEL_DESIGN_REVIEW.json`; it never fabricates PaperNexus provenance.

When the selected idea was generated from a committed PaperNexus `proposal_graph_session`, consume that bundle as the strongest upstream idea artifact. It can supply the hypothesis, mechanism, method sketch, novelty contrast, evaluation protocol, risk map, falsification route, must-cite evidence, controller trace, and proposal markdown, but it does not replace baseline-code-first planning or the launch gates below.

## Direct Authority

`orchestrator/tracks/<track-id>/INNOVATION_PACKET.json` and
`planner/tracks/<track-id>/EXPERIMENT_REVIEW_PACKET.json` are the per-track plan
and prelaunch authorities. The top-level packet pair remains a primary-only
compatibility projection. `orchestrator/TRACK_PLAN_MATRIX.json` indexes current
track readiness; it does not replace the packets. A seed, packet, or matrix row
is not launch approval: the project queue still owns launch readiness and row
leases.

Shared baseline/code/dataset/metric/runtime/path invariants belong in
`.autoreskill/resources/PROJECT_EXECUTION_PASSPORT.json`, not copied as mutable
track authority. Each packet binds the passport index, one
`execution_profile_sha256`, an `innovation_delta_sha256`, and a resolved
compatibility projection. Changing an unrelated passport component must not
invalidate a track whose profile does not require it.

For an enforced `cross_dataset_method`, each real `method_candidate` also binds
the live `PROGRAM_CLAIM_CONTRACT.json`, one dataset-group plan, and one
load-bearing `parameter_transfer_contract`. Materialization derives one stable
`method_formula`/`method_formula_sha256` and a `parameter_role_inventory` that
marks baseline protocol fields as dataset-adaptable and identifies exactly one
innovation-load-bearing field. The latter must be the parameter named by the
transfer contract. Classify the transfer as
`shared_absolute`, `shared_normalized`, or `dataset_calibrated`; shared modes
freeze one common human-selected setting, while only a declared normalized
formula may realize different raw values. Normally preregister 2-3 values per
required dataset under one fixed scout seed. Materialize those probes first,
commit the deterministic selection through `research_decision.py`, then project
`FROZEN_PARAMETER_PROFILE.json`. That profile owns exact downstream config only;
the idea ledger remains the scientific-decision authority. Stage-2 method
screens and Stages 3-6 must bind the frozen profile hash.

This stage must also produce the full user-facing innovation story directory:

```text
.autoreskill/user_view/innovation_story/
  00_STORYLINE_DESIGN.md
  01_METHOD_INNOVATION_STORY.md
  02_CLAIM_EVIDENCE_MAP.md
```

These files are derived explanatory artifacts for the user, not launch authorities. They must translate the selected idea into a coherent paper story and method-formation narrative: the current field supplies the problem, baseline/protocol, and reviewer-risk anchor; the main method mechanism should remain grounded in near-neighbor, far-neighbor, proposal-graph, external-domain, or cross-lane transfer evidence. Do not reduce them to contribution bullets or module inventories.

The selected idea must retain one defensible `core_scientific_contribution`, not
collapse into a metric target or module rename. `supporting_contributions` are
optional and count only when each records the counterfactual central claim that
fails without it; validation, analysis, and engineering remain evidence roles.
The selected primary must also preserve a complete `paper_storyline`. If the
core contribution, causal hypothesis, or story cannot survive planning scrutiny,
return to `idea_gate` instead of inflating the contribution count.

An alternate pilot does not need a second full manuscript storyline. It still
needs evidence ids, causal mechanism, prediction, falsifier, locked baseline and
protocol, dataset/split/metric/evaluator, budget, seed policy, stop rules, and all
outcome routes. Its packet must set `track_role`, current lifecycle and selection
refs, `source_track_seed_sha256`, and `evidence_tier_ceiling=pilot_only`.

Required authority fields:

- selected idea fragment id
- selected experiment idea id from `ideation/EXPERIMENT_IDEA_POOL.json`
- pre-idea evidence gate path from `ideation/PRE_IDEA_EVIDENCE_GATE.json`
- innovation slot map: for legacy PaperNexus mode use
  `ideation/INNOVATION_SLOT_MAP.json`; for `external_material`, resolve the
  content-addressed `innovation_slot_map_path`/`slot_map_ref` from the passed
  pre-idea gate and verify its filename/hash/campaign binding
- consumed innovation slot ids that explain which challenge/insight/transfer evidence drove the selected idea
- proposal graph session path, manifest path, committed subgraph id, proposal artifact paths, and controller trace paths when the selected idea cites `proposal_session_ref`
- innovation search contract: idea-bound mechanism, mechanism type, track id, expected effect, falsifier, ablation/confirmation requirements, and initial promotion stage
- HPO search policy: when `mechanism_type="PARAM"` or a target sweep is planned,
  record `hpo_search_policy` in both packets using the resource-constrained DEHB
  contract from `references/resource_constrained_dehb_policy.md`; name
  `tuning_target=baseline_calibration|mechanism_parameterization`, use bounded
  `elastic_async` execution, and treat linear/grid tuning or seed-as-search-axis
  plans as launch blockers
- validation contract: `validation_stage` 0-7, prerequisite evidence refs,
  `claim_ceiling`, project passport/index hash, execution profile id/hash,
  innovation-delta hash, and resolved execution projection hash
- primary method source role, neighbor transfer mechanism, target-domain anchor, and target-domain method overlap risk for the selected idea
- core scientific contribution, optional supporting contributions with
  counterfactual necessity, and explicit validation/analysis/engineering roles
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
- cross-dataset parameter policy for real method candidates: `claim_role`, live
  program-contract ref/hash/revision, required dataset ids/roles,
  immutable method formula/hash, parameter-role inventory,
  `parameter_transfer_contract`, `parameter_profile_status`, and, after
  calibration, frozen-profile ref/hash. Varying seeds at one parameter value
  never closes parameter coverage.
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

For eligible `PARAM` mechanisms, also record `hpo_search_policy` at the packet
top level or inside `innovation_search_contract`. Use
`search_method="dehb_resource_constrained"` by default: a small differential
evolution population proposes mixed continuous/discrete candidates, Hyperband
rungs allocate low fidelity to most trials, and only the top 1-2 full-resource
survivors may enter ablation/confirmation. The resource axis must be epochs,
steps, or data fraction, never seed count. Read
`references/resource_constrained_dehb_policy.md` before designing PARAM search.
Innovation DEHB is Stage 5 and requires initial support or explicit ambiguity,
a named sensitivity question, locked protocol, and remaining budget. A valid
negative is ineligible. `baseline_calibration` is separate `pilot_only` work,
may overlap Stage-2 innovation scouts, and never uses innovation Stage 5.

## Track Hypothesis And Acquisition

`experiment_materialize.py --track-id <id>` is an identity selector, not a label
override: it must resolve exactly one current seed, idea, and lifecycle decision.
Use `--all-admitted` only to materialize the current bounded portfolio. Missing,
duplicate, parked, killed, role/lifecycle-mismatched, or relabeled identities fail
closed. Every active `TRACK_PLAN_MATRIX.tracks[]` row must carry one falsifiable
`hypothesis_contract`: causal signature, causal question, intervention,
one-variable delta, mechanism, predicted pattern, falsifier, alternative
explanation, minimum discriminating experiment, dataset-transfer assumption,
positive/negative/inconclusive/invalid routes, belief state, and bounded scientific
revision index. An evolved child also records `parent_track_id`,
`derived_from_run_id`, and one `hypothesis_delta`; renaming or parameter-only
variation does not create a new causal track.

All complete admitted tracks may be planning-ready concurrently. Primary rows
may use `claim_eligible_after_gates`; alternate and risk-repair rows are capped at
`pilot_only`. Positive non-primary evidence routes to explicit reselection and a
frozen matched-baseline rerun, never directly to claim promotion.

Build queue proposals in this order: restore invalid evidence, resolve competing
hypotheses, falsify the core mechanism, close a required claim, confirm
generalization, optimize an already supported mechanism, then optional
resource-fill diagnostics. Within one class prefer the experiment that changes
the most current decisions, then lower cost, then an otherwise idle independent
resource. HPO and combinations cannot outrank missing mechanism or cross-dataset
evidence. Detailed readiness and lease fields are owned by
`autoreskill-workflow/references/experiment_next_actions.md`.

## Validation Ladder

Plan the cheapest decision-changing row first and encode its stage in both
packet and queue proposal:

| Stage | Required experiment | Evidence ceiling |
| ---: | --- | --- |
| 0 | Static path/parser/config validation | diagnostic |
| 1 | Active-path smoke or small-batch overfit | implementation only |
| 2 | Minimum-dataset, one-seed, low-fidelity falsifier | `pilot_only` |
| 3 | One-seed full-budget matched control | initial support/rejection |
| 4 | Second target dataset | generalization/scope |
| 5 | Sensitivity-justified DEHB | search/full-resource candidate |
| 6 | At most three paired baseline/proposed seeds | stability/promotion |
| 7 | Small greedy/beam combo of independently supported components | combination |

Baseline calibration can run beside Stage 2, but innovation evidence remains
screening-only until the baseline is frozen and the survivor is rerun matched.
After initial support, Stage 4 outranks Stage 5. A valid negative follows its
predeclared lifecycle route instead of adding seeds or parameter trials.

## Default Planning Order

Run these steps for each named admitted track before continuing the remaining
experiment-plan workflow. Do not copy a primary packet into an alternate; shared
baseline/protocol fields may be reused only when the alternate is genuinely
protocol-aligned.

1. Resolve the selected idea evidence import/material gate.
   - First confirm `ideation/PRE_IDEA_EVIDENCE_GATE.json` exists with `status="passed"`. In legacy PaperNexus mode, verify `ideation/INNOVATION_SLOT_MAP.json`; in `external_material` mode, resolve and hash-check the gate's content-addressed `innovation_slot_map_path`/`slot_map_ref` before consuming the selected idea's slots.
   - If the gate is `status="degraded_requires_user_approval"` with valid user approval, treat the selected idea as speculative. Copy `claim_limits` and `evidence_boundary` into both planning packets, set selected-idea evidence closure as a launch blocker, and do not make novelty, SOTA, closest-prior, or formal performance claims until PaperNexus material closure succeeds.
   - If `evidence_source_mode="external_material"`, require `external_campaign_ref`, `external_campaign_sha256`, and `external_candidate_id` throughout pool/scorecard/ledger/seeds/track/packets, and copy the selected campaign candidate's exact `protected_commitment_sha256` into both planning packets. Keep `selected_idea_fragment_id`, `track_id`, and `external_candidate_id` separate. Use `evidence_import_gate.status="not_required"`, `source_mode="external_material"`, the campaign/lint refs, an explicit reason, and `launch_blocked=false`; require `external_evidence_norms` (or `evidence_norms`) instead of `paperNexus_norms`.
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
   - If local/connectable GPU is adequate, set `compute_backend.backend` to `local_gpu` and record the probe evidence. Record the orthogonal `execution_route` in both packets and `path_mapping`: `local_gpu` permits `local`, `ssh`, or `bjtu_hpc`; `autodl_gpu` requires `autodl`. An execution route observes where a reviewed plan may run; it does not authorize launch.
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
  default, and treat scout results as non-promotable pilot evidence. Materialize
  independent scouts into the bounded next-action frontier so fitting trials can
  execute asynchronously; concurrency reduces wall-clock time and never enlarges
  `max_scout_trials`, `max_full_budget_trials`, or total GPU-hours.
- For baseline calibration, search validation evidence only, record an equal or
  shared tuning budget, and freeze the matched reproduced baseline before claim
  promotion. Innovation scouts may overlap only as `pilot_only`; rerun any
  survivor against the frozen baseline and matched seed set. Keep
  `paper-report comparison not established` when reproduction remains below or
  mismatched with the paper report.
- Before handing off to execution, materialize a bounded ready frontier of
  already justified baseline trials, active-track discriminators, cross-dataset
  single-mechanism rows, controls, ablations, HPO scouts, and confirmations.
  Do not size the scientific plan from the number of idle GPUs, exceed four
  active track seeds, or exceed three unique random seeds per experiment family.
- Consume the selected optimization idea from `autoreskill-ideation-panel` at `ideation/EXPERIMENT_IDEA_POOL.json`. Do not generate the pool in experiment planning.
- Consume the selected idea's `pre_idea_evidence_gate_path`, `innovation_slot_map_path`, and `innovation_slot_refs` into both `INNOVATION_PACKET.json` and `EXPERIMENT_REVIEW_PACKET.json`.
- Preserve the selected idea's `primary_method_source_role`, `neighbor_transfer_mechanism`, `target_domain_anchor`, and `target_domain_method_overlap_risk`. Do not rewrite a near/far-neighbor transfer idea into a target-domain-only tweak during planning.
- Preserve `core_scientific_contribution`, optional
  `supporting_contributions`, and the selected primary's `paper_storyline`. Do not
  turn a causal thesis into a metric, module, or heuristic, and do not relabel
  validation or engineering as extra innovation.
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
- Update all three `user_view/innovation_story/` files after the packets are internally consistent. They should explain the belief shift, core contribution, method origin, optional necessary supports, proof ladder, planned evidence, falsifiers, and claim limits.
- Convert `ideation/IDEA_TRACK_SEEDS.json` into matrix schema v3 before prelaunch
  lint. Keep an alternate parked until it is explicitly materialized; after its
  own baseline/protocol/evidence closure passes, allow it to become
  planning-ready without inheriting any primary field. Legacy schema-v2 projects
  remain primary-only until explicit materialization.

## Validation

Before `autoreskill-run-experiment`, run:

```bash
python scripts/experiment_materialize.py --project <project-root> --all-admitted --dry-run
python scripts/experiment_materialize.py --project <project-root> --all-admitted
python scripts/track_plan_matrix.py --project <project-root>
python scripts/track_plan_matrix.py --project <project-root> --check
python ../autoreskill-workflow/scripts/resource_passport.py lint-project --project <project-root>
# When the selected idea cites proposal_session_ref:
python ../autoreskill-papernexus-innovation/scripts/proposal_graph_session_lint.py --project <project-root>
python scripts/prelaunch_lint.py --project <project-root> --track-id <track-id>
python scripts/innovation_lint.py --project <project-root>
python ../autoreskill-workflow/scripts/innovation_story_lint.py --project <project-root> --stage experiment_plan
```

Materialization uses canonical semantic hashes, does not rewrite unchanged
packets, and writes top-level compatibility artifacts only for the current
primary. A dry run reports admitted tracks, missing packet refs, rows that would
become eligible, stale rows, and files that would be written. It never activates
queue rows or launches work. Explicitly materializing a legacy alternate is the
migration action; migration never changes primary selection, seeds, budgets, or
existing queue status.

The linters block launch when the reviewed packet lacks a defensible core
contribution, causal identity/outcome routes, passed/not-required evidence import
gate, source-backed selected idea support, one-variable change, locked baseline
code/protocol/dataset/eval/metric, backend/path/runtime plan, falsifiers, stop
rules, compute budget, or expected artifacts. They also block a large first
dataset without an explicit exception and a `PARAM` mechanism without a
resource-constrained DEHB policy.

Read `references/experiment_review_packet_schema.md`,
`references/resource_constrained_dehb_policy.md`, and
`references/baseline_fairness_checklist.md`. Read
`references/experiment_idea_pool.md` only when diagnosing the upstream ideation
pool; do not create that pool in this skill.
