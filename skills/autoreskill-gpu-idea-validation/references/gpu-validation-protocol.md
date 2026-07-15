# Bounded GPU validation protocol

This document is the normative local Phase 5 contract. It applies only after a
candidate passes paper Phases 0-4, the external campaign is materialized, the
canonical AutoResearch panel/planner reviews it, implementation is ready, and a
`pilot_only` row exists in `NEXT_EXPERIMENT_QUEUE.json`.

GPU availability is a scheduling observation. It is never scientific evidence,
experiment creation authority, claim support, budget authority, or permission
to launch.

Command examples assume:

```bash
SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
SKILL_DIR="$SKILLS_ROOT/autoreskill-gpu-idea-validation"
PROJECT_ROOT=/absolute/path/to/project
```

## 1. Authority chain

| Concern | Canonical authority | Resource artifacts may do |
|---|---|---|
| candidate selection/belief | `IDEA_DECISION_LEDGER.json` | nothing |
| scientific track/readiness | `TRACK_PLAN_MATRIX.json` and reviewed packets | filter resource fit only |
| scheduling | `NEXT_EXPERIMENT_QUEUE.json` | propose normalized pools |
| runtime truth | per-run `REMOTE_RUN.json` | preserve snapshot and backend refs |
| scientific interpretation | `SCIENTIFIC_OUTCOME.json` plus research-decision workflow | supply measured evidence only |

Use `$autoreskill-workflow` as conductor, `$autoreskill-experiment-plan` for the
reviewed protocol, `$autoreskill-implement-experiment` for implementation,
`$gpu-idle-scan` for read-only SSH observations, `$bjtu-hpc` for BJTU
admission/preflight, and `$autoreskill-run-experiment` for launch/monitor/
reconciliation under its own authorization rules.

The skill's build and fixture validation are offline: do not scan, log in,
refresh credentials, reserve/claim remote resources, submit Slurm jobs, launch,
kill, preempt, or terminate processes while installing or testing this skill.

## 2. Admission and quick ceilings

Before resource discovery, require all of:

- passing campaign lint, quality gauntlet, and independent implementability
  audit with no open load-bearing hole;
- passing external alignment lint at the current stage;
- canonical panel selection and reviewed experiment plan;
- a plan-ready queue row with `evidence_tier="pilot_only"` whose external candidate and
  protected commitment hashes match; the row carries the exact current
  `protected_commitment_sha256` copied from the selected campaign candidate;
- locked dataset/split, metric/direction, baseline source/label, command or
  implementation ref, and result routes.

Default quick ceilings are:

- no more than 4 active admitted ideas per campaign;
- one physical GPU and one scout seed per idea;
- a ten-minute smoke included in the per-candidate budget;
- at most 1 GPU-hour/60 minutes per candidate discriminator;
- at most 4 GPU-hours per campaign;
- no more than 3 eventual seeds in an experiment family.

The effective ceiling is the minimum of the explicit user ceiling, remaining
project-policy ceiling, and quick ceiling. Budget accounting includes completed
actual, failed actual, running reserved, planned reserved, smoke, partial runs,
and retries. Unknown consumption fails closed. Deleting local records never
refunds budget; only reconciled backend evidence can replace a reservation with
actual usage.

Conceptually:

```text
remaining = min(user ceiling, project-policy remaining ceiling, 4 GPU-hours)
            - (completed actual + failed actual
               + running reserved + planned reserved)
```

Use the offline checker before claim and again before launch preparation:

```bash
python3 "$SKILL_DIR/scripts/resource_adapter.py" budget-check \
  --project "$PROJECT_ROOT" --candidate-id "<candidate-id>" \
  --reserve-gpu-hours "<hours>"
```

The helper derives a ledger view from canonical campaign/queue/run/experiment
facts; it does not create a new budget authority.

## 3. Captured resource normalization

Normalization consumes captured JSON only and performs no discovery or launch:

```bash
python3 "$SKILL_DIR/scripts/resource_adapter.py" normalize-local-scan \
  --project "$PROJECT_ROOT" --input /absolute/path/to/captured-local-scan.json \
  --output /absolute/path/to/resource-snapshot-proposal.json

python3 "$SKILL_DIR/scripts/resource_adapter.py" normalize-ssh-scan \
  --project "$PROJECT_ROOT" --input /absolute/path/to/captured-ssh-scan.json \
  --output /absolute/path/to/resource-snapshot-proposal.json

python3 "$SKILL_DIR/scripts/resource_adapter.py" normalize-bjtu-plan \
  --project "$PROJECT_ROOT" --input /absolute/path/to/captured-bjtu-plan.json \
  --output /absolute/path/to/resource-snapshot-proposal.json
```

Fresh agents should normally use the queue-row dispatcher so the protected
route selects the normalizer and no shell placeholder is needed:

```bash
python3 "$SKILL_DIR/scripts/resource_adapter.py" normalize-for-row \
  --project "$PROJECT_ROOT" --row-id "<row-id>" \
  --input /absolute/path/to/route-matched-captured-observation.json \
  --output /absolute/path/to/resource-snapshot-proposal.json
```

The local capture declares `schema="local-gpu-scan/v1"`, a fresh
timezone-aware `checked_at`, and a `gpus` array. A local GPU is assignable only
when its row has a non-empty physical `uuid`, `idle=true`, and
`full_process_visibility=true`. Capturing that JSON is read-only observation;
normalization never probes the machine.

Each normalized pool records canonical identity, backend, execution route,
status, `fresh`, `checked_at`, source ref/SHA-256, GPU model/VRAM/capabilities,
one launch slot per physical GPU, and shared-limit scope if known. Unknown or
stale input produces zero assignable slots.

Preserve `compute_backend.backend=local_gpu` and use an orthogonal
`execution_route = local | ssh | bjtu_hpc`. Paid `autodl_gpu/autodl` is outside
this skill unless separately and explicitly authorized.

## 4. Read-only SSH discovery and exact recheck

Use the curated/current endpoint scan first:

```bash
python3 "$SKILLS_ROOT/gpu-idle-scan/scripts/gpu_idle_scan.py" \
  --project "$PROJECT_ROOT" --current-ssh-hosts --no-ssh-config \
  --timeout 3 --command-timeout 30 \
  --write-artifact "$PROJECT_ROOT/.autoreskill/experiment/GPU_IDLE_SCAN.json"
```

Search the full SSH config only if curated/project endpoints are insufficient
and the current user asks for it. Timeout, authentication failure, malformed
output, unreachable host, missing UUID, or stale observation is `unknown`, not
idle. Do not put credentials or private SSH material in artifacts.

Normalize physical identity by canonical endpoint plus GPU UUID and expose one
launch slot per physical GPU. Raw `nvidia-smi` visibility does not prove the GPU
is reserved, allocatable, safe to use, or compatible with the planned code.

Immediately before a future launch, verify the exact code revision, dataset,
environment, remote paths, pre-generated run/session ID, and assigned GPU UUID;
then recheck only the assigned host with bounded timeouts and full process
visibility. Renew the local lease before a long preflight. Busy, unknown, or
failed preflight means release the unlaunched allocation, stale the observation,
refresh, and reschedule. Never kill or preempt another process.

## 5. BJTU HPC planning and preflight

Raw GPU visibility does not establish Slurm allocatability. Use `$bjtu-hpc` and
its live queue/account/QOS snapshot plus `hpc_resource_planner.py`/
`hpc_plan_from_snapshot.py`. Resolve `$HPC_PYTHON`; otherwise use an available
Python >=3.10 environment with `requests` and `paramiko`.

Use this planning shape unless a stricter live policy says otherwise:

```text
hpc_plan_from_snapshot.py
  --admission-mode direct-start
  --max-admissions-per-cycle 8
  --cap 2
  --run-slots 2
  --workload single
  --no-queued
  --planner-json
  --summary-jobs 4
```

Default to `1GPU/6CPU`; use `1GPU/4CPU` only when exact test-only evidence shows
it resolves reservation/same-node CPU pressure. Use anonymous Slurm-visible
names and keep private account mapping in a mode-0600 ledger.

Before a real submit, run exact-script local/remote syntax checks where
applicable, `sbatch --test-only`, and shape verification. `hpc_native_submit.py`
runs without `--submit` first. Add `--submit` only after all launch authorities
pass, then submit one job, verify exact shape with `scontrol`, refresh, and
replan. QOS/account caps are scheduling limits, not code or hypothesis failure.
Do not build a queued backlog.

## 6. Deterministic schedule and atomic assignment

The queue order is:

```text
reconcile
→ queue check
→ capture/normalize resource facts
→ revision-checked resource-snapshot commit
→ read-only schedule
→ first deterministic assignment only
→ atomic claim-assignment
→ baseline clone lint and protocol lint
→ route-specific preflight
→ launch-authority and budget checks
→ persist queued launch intent / REMOTE_RUN.json
→ remote side effect
→ reconcile exact backend ID
→ queue running
→ reconcile
```

Never preclaim a batch or claim a second row from a stale schedule. Use only the
first assignment returned for the current queue revision:

```bash
python3 "$SKILLS_ROOT/autoreskill-workflow/scripts/experiment_next_actions.py" \
  check --project "$PROJECT_ROOT"

python3 "$SKILL_DIR/scripts/resource_adapter.py" normalize-for-row \
  --project "$PROJECT_ROOT" --row-id "<row-id>" \
  --input /absolute/path/to/route-matched-captured-observation.json \
  --output /absolute/path/to/resource-snapshot-proposal.json

python3 "$SKILLS_ROOT/autoreskill-workflow/scripts/experiment_next_actions.py" \
  commit-resource-snapshot --project "$PROJECT_ROOT" \
  --input /absolute/path/to/resource-snapshot-proposal.json \
  --owner "<worker>" --expected-revision "<queue-revision-before-commit>"

python3 "$SKILLS_ROOT/autoreskill-workflow/scripts/experiment_next_actions.py" \
  schedule --project "$PROJECT_ROOT"

python3 "$SKILLS_ROOT/autoreskill-workflow/scripts/experiment_next_actions.py" \
  claim-assignment --project "$PROJECT_ROOT" --row-id "<row-id>" \
  --pool-id "<pool-id>" --owner "<worker>" \
  --expected-revision "<queue-revision>"
```

`claim-assignment` recomputes schedule under the canonical queue lock and binds
one row plus one pool. The planned allocation records the pool/backend/route,
account/host refs, GPU count, estimated GPU-hours, fit confidence, claim time,
and resource snapshot. It consumes/stales the observed slot and advances one
queue revision atomically.

This claim is a local lease, not launch permission. Do not use plain `claim` for
these pilots. On unlaunched busy/unknown/preflight/authority/budget failure, use
the core revision-checked `release`, stale capacity, refresh, and reschedule.

## 7. Launch authorization and intent

A future remote side effect requires all three independent authorities:

1. the current invocation explicitly requests the actual run/submit, or carries
   an unambiguous current-action `approval_ref`;
2. `.autoreskill/autopilot_policy.json` has
   `allow_remote_experiment_launch=true`;
3. the selected backend/route policy permits launch.

A passing skill, plan, gate, schedule, scan, local lease, or previously granted
approval is insufficient. Any missing authority stops and releases an unlaunched
allocation.

Persist the third authority before intent preparation as one of these explicit,
auditable forms (normally after route-specific preflight):

```json
{"backend_policy": {"allow_launch": true, "policy_ref": "<current-policy-evidence>"}}
```

on the queue row/resource request, or a matching campaign
`execution_policy.routes.<route>` entry. The compatible row shorthand is
`backend_launch_allowed=true` plus non-empty `backend_policy_ref`. An idle pool,
backend name, or successful preflight without a policy ref does not satisfy this
authority. The intent helper validates recorded evidence; it does not execute
the backend preflight itself.

After the atomic claim, record a fresh `backend_preflight` on the queue row. It
must bind `pool_id`, `execution_route`, the claimed
`resource_snapshot_sha256`, and the exact `launch_spec_sha256`, with
`status="passed"` and a timezone-aware `checked_at` no more than ten minutes
old. The immutable launch spec uses a string-array command, exact 64-hex hashes
for code, dataset, environment, and launcher template, and
`resource_shape.gpus=1`; its explicit `seed` must equal the protected campaign
scout seed. The claimed lease must still have a non-empty owner and future
expiry, and the row's route and GPU-hour reservation must equal the protected
candidate commitments.

Run the baseline clone lint and baseline protocol launch lint before computing
the final digest. Then validate that exact digest without contacting a backend:

```bash
python3 "$SKILLS_ROOT/autoreskill-implement-experiment/scripts/baseline_clone_lint.py" \
  --project "$PROJECT_ROOT"
python3 "$SKILLS_ROOT/autoreskill-run-experiment/scripts/baseline_protocol_launch_lint.py" \
  --project "$PROJECT_ROOT"

python3 "$SKILL_DIR/scripts/resource_adapter.py" launch-spec-digest \
  --input /absolute/path/to/launch-spec.json
```

After route-specific preflight has produced captured JSON bound to that digest,
commit it with the current claimed-row revision:

```bash
python3 "$SKILLS_ROOT/autoreskill-workflow/scripts/experiment_next_actions.py" \
  record-backend-preflight --project "$PROJECT_ROOT" --row-id "<row-id>" \
  --owner "<worker>" --expected-revision "<queue-revision-after-claim>" \
  --input /absolute/path/to/route-specific-backend-preflight.json
```

For SSH, the allocation must contain exactly one physical `gpu_uuids` entry and
the preflight additionally records the matching `assigned_gpu_uuid`,
`assigned_gpu_idle=true`, and `full_process_visibility=true`. For BJTU, it
records `exact_script_checks_passed=true`, `sbatch_test_only_passed=true`,
`no_queued=true`, and `requested_gpus=1`. Missing, stale, or mismatched
preflight evidence blocks intent preparation; the caller releases the
unlaunched claim and refreshes resource state.

After a final budget check and before the side effect, persist the queued intent:

```bash
python3 "$SKILL_DIR/scripts/resource_adapter.py" budget-check \
  --project "$PROJECT_ROOT" --candidate-id "<external-candidate-id>" \
  --reserve-gpu-hours "<hours>"

python3 "$SKILL_DIR/scripts/resource_adapter.py" prepare-launch-intent \
  --project "$PROJECT_ROOT" --row-id "<row-id>" --pool-id "<pool-id>" \
  --run-dir "$PROJECT_ROOT/.autoreskill/coder/experiments/<track-id>/<experiment-id>" \
  --launch-spec /absolute/path/to/launch-spec.json \
  --approval-ref "<current-action-approval-ref>"
```

The intent/`REMOTE_RUN.json` records `status=queued`, run ID, row/pool IDs,
exact-command digest, code/data/environment refs, resource snapshot/hash,
protected commitment and locked budget, route, and backend idempotency key. The
helper prepares local state only and must report `side_effects_performed=false`.

After an ambiguous SSH/submit response, reconcile that exact session/job/trace
ID and never automatically resend. No automatic retry is allowed when the
submit/SSH result is unknown, the run record is missing, the command changed,
the resource observation expired, or budget/commitment hashes changed.

## 8. Outcome taxonomy and claim boundary

The protected campaign has six leaf outcomes. At queue handoff they project to
the canonical four-key `outcome_routes` contract without losing the invalid
reason:

| Protected leaf | Queue route | Belief effect |
|---|---|---|
| `valid_positive_candidate` | `positive` | candidate-only increase; confirmation still required |
| `valid_negative` | `negative` | weaken, scope, pivot, or retire |
| `valid_inconclusive` | `inconclusive` | at most one useful discriminator |
| `infrastructure_failure` | `invalid.infrastructure_failure` | none; runtime/resource repair |
| `implementation_failure` | `invalid.implementation_failure` | none; implementation repair |
| `protocol_invalid` | `invalid.protocol_invalid` | none; quarantine and protocol repair |

Thus queue keys are exactly `positive`, `negative`, `inconclusive`, and
`invalid`; the invalid value retains all three subroutes. After execution,
persist the exact six-leaf `outcome_class` expected by AutoResearch. The
four-key projection must not erase which invalid class occurred.

- A feasibility smoke is `record_only` implementation evidence, not a
  `SCIENTIFIC_OUTCOME` class.
- `valid_positive_candidate` means the idea survives. It requires a matched
  baseline plus matched reproduction, confirmation, and ablation before claim
  support.
- `valid_negative` may lower belief, narrow scope, or retire the candidate.
- `valid_inconclusive` permits at most one additional decision-changing
  discriminator by default.
- Infrastructure, implementation, or protocol failure carries no hypothesis
  belief penalty. Fix or stop according to budget; do not label it scientific
  negative evidence.

All fast runs remain `pilot_only` and may not directly set
`candidate_supported`, `promoted`, `close_required_claim`, or
`claim_promotion`.

Every baseline statement must use one exact label:

- `vs paper-reported baseline`
- `vs reproduced baseline`
- `vs matched reproduced baseline`
- `paper-report comparison not established`

A gain over a reproduced baseline is not automatically a gain over the paper
report. If protocol alignment is absent or the reproduction underperforms the
paper report, use `paper-report comparison not established` and downgrade the
claim.

## 9. Recovery rules

- Same owner/row/pool claim is idempotent; a competing owner/pool fails.
- Release any unlaunched allocation before refreshing or changing route.
- Never reuse a schedule revision after claim/release/launch reconciliation.
- Preserve failed/smoke/partial consumption in budget accounting.
- Reuse the same scout seed for a retry; a retry is not permission to sample a
  favorable seed.
- Missing log/result synchronization is `needs_sync`, not success or failure.
- Reconcile exact backend IDs after launch; do not infer state from silence.
- Refresh BJTU state after every submission before deciding the next action.
- Never delete remote data, cancel jobs, kill processes, or preempt GPUs unless
  the user explicitly asks for that concrete action and the backend policy
  permits it.
