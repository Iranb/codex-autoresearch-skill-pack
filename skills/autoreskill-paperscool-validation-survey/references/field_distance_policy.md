# Field-Distance Source Selection

Use this reference when defining `FIELD_DISTANCE_POLICY.json` or screening papers into direct, near-neighbor, far-neighbor, and blocked lanes.

## Core Principle

The survey should not simply find the most related papers. It should use same-field papers to set boundaries and reviewer risk, and use neighbor fields to find transferable mechanisms that can be implemented and validated quickly.

## Lane Definitions

- `direct_field`: Same task family as the target. Use for `baseline_anchor`, `novelty_risk`, or `related_work`. Do not use as `innovation_source`.
- `near_neighbor`: Adjacent task family with reusable mechanisms and low adaptation cost. Prefer these for innovation transfer.
- `far_neighbor`: Different task family but shares a technical pressure such as noisy pseudo-labels, domain shift, prototype drift, calibration, memory update, or open-set uncertainty. Use only when the mechanism is lightweight and testable.
- `blocked`: Outside the survey scope or too expensive to validate quickly.

## Target Examples

For `GCD`:

- `direct_field`: generalized category discovery, novel category discovery, NCD, CGCD, open-world GCD, category discovery benchmarks.
- `near_neighbor`: semi-supervised learning, unsupervised clustering, deep clustering, open-set recognition, pseudo-label learning, uncertainty calibration.
- `far_neighbor`: domain adaptation, long-tail recognition, metric learning, noisy-label learning, prototype memory, representation disentanglement.
- `blocked`: medical/clinical, 3D, open-vocabulary scene understanding, VLM/LLM-heavy methods, diffusion/generation.

For `ContinueGCD`:

- `direct_field`: continual generalized category discovery, continual category discovery, ContinueGCD, continual GCD, open-world continual category discovery.
- `near_neighbor`: continual learning, class-incremental learning, task-free CL, exemplar-free CL, online CL, concept drift, replay-free adaptation, old/new class separation.
- `far_neighbor`: domain adaptation, streaming clustering, test-time adaptation, pseudo-label denoising, memory consolidation, prototype calibration.
- `blocked`: LLM/VLM/diffusion-heavy methods, huge pretraining, medical/3D/open-vocabulary scene methods unless explicitly allowed.

For `DomainGCD`:

- `direct_field`: DomainGCD, domain-shift GCD, GCD with explicit domain generalization/adaptation as the main task.
- `near_neighbor`: unsupervised domain adaptation, domain generalization, test-time adaptation, style/shortcut bias learning, domain calibration.
- `far_neighbor`: robust learning, long-tail learning, multi-source balancing, ReID metric learning, remote-sensing domain adaptation if not medical/3D/heavy-model.
- `blocked`: open-vocabulary scene understanding, 3D, medical, LLM/VLM-heavy, diffusion/generation.

## Required Policy Fields

`FIELD_DISTANCE_POLICY.json` should contain:

```json
{
  "target_task": "ContinueGCD",
  "direct_field": ["continual generalized category discovery"],
  "near_neighbor": ["continual learning", "class-incremental learning"],
  "far_neighbor": ["domain adaptation", "prototype calibration"],
  "blocked": ["large language model", "diffusion model", "medical imaging"],
  "usage_rules": {
    "direct_field": ["baseline_anchor", "novelty_risk", "related_work", "excluded"],
    "near_neighbor": ["innovation_source", "related_work"],
    "far_neighbor": ["innovation_source", "diagnostic_source"],
    "blocked": ["excluded"]
  },
  "override_policy": "Direct-field or blocked papers require override_reason before entering innovation artifacts."
}
```

## Screening Decisions

Each screened paper should record:

- `paper_id`
- `title`
- `target_task`
- `field_distance`: `direct_field`, `near_neighbor`, `far_neighbor`, `blocked`, or `out_of_scope`
- `source_lane`
- `usage_role`: `innovation_source`, `baseline_anchor`, `novelty_risk`, `related_work`, `diagnostic_source`, or `excluded`
- `decision`: `keep_for_code_check`, `route_to_baseline`, `route_to_novelty_risk`, `route_to_related_work`, `exclude`, or `needs_review`
- `reason`

Direct-field rows may be important; they should not be silently deleted. Route them to baseline and novelty-risk ledgers so they can protect the final paper from overlap.
