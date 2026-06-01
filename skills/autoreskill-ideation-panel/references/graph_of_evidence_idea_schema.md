# Graph-of-Evidence Idea Schema

`EVIDENCE_GRAPH_PROJECTION.json` is an ideation-stage evidence view. It is not a stage authority by itself; WorkflowGuard still advances stages only through the existing contract lints.

Required node types:

- `paper`
- `claim`
- `method_mechanism`
- `limitation`
- `negative_evidence`
- `baseline`
- `dataset`
- `metric`
- `protocol`
- `transfer_bridge`
- `proposal_node`
- `reviewer_risk`

Required edge types:

- `supports`
- `contradicts`
- `extends`
- `transfers_to`
- `anchors`
- `compares_against`
- `evaluates_on`
- `risks_overlap_with`
- `needs_closure`

The projection should contain target-domain anchors, near/far-neighbor mechanisms, negative evidence, baseline/protocol norms, and reviewer risks when available. Sparse or approved degraded projects must keep explicit `claim_limits` and cannot use the projection to promote novelty or launch approval.

`IDEA_BUILD_BRIEF.json` and `IDEA_BUILD_BRIEF.md` compress the projection into a ScientistOne-style PI brief:

- current-field anchor and closest-prior pressure
- candidate mechanisms from near/far-neighbor, cross-lane transfer, or proposal graph nodes
- negative evidence and falsifiers
- baseline, dataset, metric, and protocol norms
- reviewer risks and claim limits

`IDEA_TRACK_SEEDS.json` preserves top-3/top-4 candidate tracks for later bounded exploration. It is evidence-only and must keep `launch_approval=false`; `TRACK_PLAN_MATRIX.json` and prelaunch lint decide whether a track can launch.
