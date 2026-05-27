---
title: "Codex AutoResearch Skill Contract Closure ExecPlan"
created: "2026-05-26 11:39 CST"
updated: "2026-05-26 11:39 CST"
type: execplan
scope: autoreskill, openclaw-alignment, papernexus, codex-skill-pack
tags: [execplan, autoreskill, openclaw, papernexus, contract-gate, review-gate, venue-profile]
---

# Codex AutoResearch Skill Contract Closure ExecPlan

Created: 2026-05-26 11:39 CST
Updated: 2026-05-26 11:39 CST
Target skill root: `~/.codex/skills`
Reference repository: `<REFERENCE_OPENCLAW_RESEARCH_REPO>`
Plan output path: `<AUTORESEARCH_EXECPLAN_DIR>/Codex-AutoResearch-Skill-Contract-Closure-ExecPlan-2026-05-26.md`

Related docs:

- `<EXECPLAN_GUIDE_PATH>`
- `<AUTORESEARCH_EXECPLAN_DIR>/Codex-AutoResearch-PaperNexus-Harness-Optimized-Skill-ExecPlan-2026-05-25.md`
- `<AUTORESEARCH_EXECPLAN_DIR>/Codex-AutoResearch-PaperNexus-Skill-Pack-ExecPlan-2026-05-22.md`

This ExecPlan is a living document. Update `Progress`, `Surprises & Discoveries`, `Decision Log`, `Artifacts`, and `Outcomes & Retrospective` as implementation proceeds.

---

## Purpose / Big Picture

完成后，Codex 版 `autoreskill-*` 不只是“语义上接近 OpenClaw”，而是在五个剩余缺口上形成可执行、可验证、可恢复的强 contract：

- `experiment_plan` 阶段不能只因为 `INNOVATION_PACKET.json` 有几个字段就通过，必须证明 selected idea 有 PaperNexus source-backed support、evidence boundary、research-controller 或 fallback design review。
- PaperNexus `idea_catalyst_evidence_export`、research controller artifacts、innovation packet 之间有明确引用链，能区分 `source_backed`、`agent_inferred`、`speculative`。
- `academic-paper-reviewer` 的多 reviewer 输出可以被转换为 `REVIEW_FINDINGS.json`，从而真正进入 `autoreskill-review-gate` 的 blocking issue gate。
- submission package 不再默认假设目标是 NMI；NMI 只是 venue profile 之一，NeurIPS/ICML/ICLR/CVPR/ACL/TPAMI/JMLR/custom 等目标都走同一个 profile contract。
- `goal_validate.py` 的本地验证矩阵能够覆盖新增 gate，而不是只靠 prompt 文案约束。

当前问题是：

- `contract_lint.py` 的 `experiment_plan` gate 仍是轻量字段检查，没有调用独立 idea support gate。
- `innovation_lint.py` 只检查字段存在，尚未检查 source span、provenance、evidence boundary、controller brief。
- `controller_lint.py` 能检查 controller export 和 design review 是否存在，但没有把 research-controller innovation brief 变成 experiment-plan 输入边界。
- `review_lint.py` 已经消费 `REVIEW_FINDINGS.json`，但 `academic-paper-reviewer` 还没有 deterministic adapter 生成该文件。
- `goal_state.py`、`goal_package.py`、`paper_scaffold.py`、`story_contract_schema.md`、`submission_lint.py` 仍有 NMI 默认或 fallback copy。

---

## Current State Snapshot

当前相关文件和职责：

- `~/.codex/skills/autoreskill-workflow-guard/scripts/contract_lint.py`：统一 stage contract linter。`experiment_plan` 目前只检查 `selected_idea_fragment_id`、`baseline`、`primary_metric`、`fixed_budget`、`supporting_idea_fragment_ids`、`evidence_paths/supporting_papers`。
- `~/.codex/skills/autoreskill-experiment-plan/scripts/innovation_lint.py`：独立 innovation packet linter。当前比 `contract_lint.py` 略多一个 `controller_design_review_path` target existence check，但没有检查 evidence boundary。
- `~/.codex/skills/autoreskill-workflow-guard/scripts/goal_validate.py`：本地 Phase-8 验证矩阵。已经包含 `innovation_lint.py`、`controller_lint.py`、`review_lint.py`，但没有 `idea_support_lint.py` 和 review adapter regression。
- `~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py`：已经支持 capture `idea_catalyst_evidence_export`、`research_controller_export`、`research_controller_design_review`、`innovation_packet` 等 artifact，并写 `artifacts_index.json`。
- `~/.codex/skills/autoreskill-papernexus-innovation/scripts/evidence_status_lint.py`：能按 artifact kind 粗分 `graph_grounded`、`discovery_evidence`、`inference_or_local_artifact`，但没有校验 selected idea fragment 和 source span。
- `~/.codex/skills/autoreskill-papernexus-research-controller/scripts/controller_lint.py`：检查 research controller 可用时的 `controller-export.json` 与 `design-review.json`，但没有创新简报 boundary。
- `~/.codex/skills/autoreskill-review-gate/scripts/review_lint.py`：以 `REVIEW_FINDINGS.json` 为 direct gate，阻断 open high/critical findings。
- `~/.codex/skills/academic-paper-reviewer/SKILL.md`：定义 multi-perspective review workflow，但输出是 review reports/editorial decision，不是 AutoResearch machine-readable findings。
- `~/.codex/skills/autoreskill-workflow-guard/scripts/goal_package.py`：已有 venue profiles，但 CLI default 仍是 `NMI`，并保留 `actual_nmi_submission_ready` 和 NMI-specific artifact。
- `~/.codex/skills/autoreskill-workflow-guard/scripts/goal_state.py`：`init --venue` default 仍是 `NMI`。
- `~/.codex/skills/autoreskill-paper-write/scripts/paper_scaffold.py`：`--venue` default 仍是 `NMI`。
- `~/.codex/skills/autoreskill-paper-write/references/story_contract_schema.md`：schema example 仍写 `"target_venue": "NMI"`。
- `~/.codex/skills/autoreskill-review-gate/scripts/submission_lint.py`：如果 `submission_ready.json.required_artifacts` 不存在，会 fallback 到 NMI artifact list。

已存在能力：

- Codex skill pack 已经不依赖 OpenClaw runtime state；使用 `.autoreskill/goal_state.json` 和 `.autoreskill/*` artifacts。
- PaperNexus remote-only policy 已经写入 skill prompt 和 job packets。
- Direct authorities 已经包括 `GRAPH_BUILD_DECISION.json`、`IDEA_CATALYST_CONTRACT.json`、`INNOVATION_PACKET.json`。
- Review gate 已经有 machine-readable `REVIEW_FINDINGS.json` 消费端。
- Venue profile 概念已经部分进入 `goal_package.py` 与 `venue_template_mapping.md`。

已知缺口：

- 缺少 `idea_support_lint.py`，导致 idea support 不能独立验证。
- `innovation_lint.py` 和 `contract_lint.py` 没有把 PaperNexus evidence boundary 变成硬 gate。
- research controller artifacts 只是存在性检查，没有成为 innovation brief boundary。
- academic multi-review 输出和 AutoResearch review gate 没有 adapter。
- NMI 仍作为默认 target venue 残留在 CLI defaults、schema examples 和 fallback lint 中。

---

## Scope

本计划包括：

- 新增 `idea_support_lint.py`，验证 selected idea fragment 是否有 source-backed evidence export 支撑。
- 强化 `innovation_lint.py`，把 `INNOVATION_PACKET.json` 的 evidence、boundary、controller brief、design review 变成硬约束。
- 强化 `contract_lint.py`，让 `experiment_plan` stage 委托/复用新的 idea support 和 innovation lint 结果。
- 接入 research-controller innovation brief boundary：新增或规范 `.autoreskill/papernexus/research_controller/innovation-brief.json`，并把它纳入 packet 和 lint。
- 新增 `academic-paper-reviewer` 到 `REVIEW_FINDINGS.json` 的 deterministic adapter。
- 清理 NMI 默认假设和文案残留，改成 target venue profile default。
- 更新 `goal_validate.py`，把新增 linter/adapter 纳入 validation matrix。
- 更新相关 `SKILL.md`、reference schema、README-like references 中的 contract 描述。

## Non-Goals

本计划不包括：

- 不重写 OpenClaw repository 的 `research_workflow`、runtime queue、session recovery 或 stage completion resolver。
- 不让 Codex skill pack 依赖 `.openclaw-research`、`PROJECT_MANIFEST.json` 或 OpenClaw runtime state。
- 不做真实 PaperNexus remote import 或付费/长时远程实验；只定义 capture 和 lint contract。
- 不改 academic-paper-reviewer 的 reviewer persona 逻辑；adapter 只转换输出，不替代审稿流程。
- 不直接生成或替换论文正文、实验结果、canonical paper figures。
- 不在本计划中合并 PR 或发布 skill pack；这是 implementation ExecPlan，不是 release note。

---

## Non-Negotiable Rules

1. `INNOVATION_PACKET.json` 仍是 `experiment_plan` 阶段 direct authority，但它必须引用可验证 evidence boundary，不能孤立宣布完成。
2. PaperNexus claims 必须可分为 `source_backed`、`agent_inferred`、`speculative`；只有 `source_backed` 可以支撑 experiment-plan hard gate。
3. `idea_catalyst_evidence_export` 和 research-controller innovation brief 是 evidence/boundary artifacts，不直接推进 stage；stage 通过由 `contract_lint.py` 给出。
4. `academic-paper-reviewer` adapter 必须保留 raw review provenance；不能只输出简化 issue list 后丢失 reviewer/source span。
5. Open high/critical review findings 继续阻断 review pressure 与 submission readiness。
6. Venue handling 必须 profile-driven。NMI 只能在用户显式选择 `NMI` 或 `Nature Machine Intelligence` 时出现。
7. 所有新增 linter 必须可在本地离线 fixture 上运行；不能要求实时 PaperNexus remote call。
8. 新增 scripts 要通过 `python -m py_compile`，并被 `goal_validate.py` 覆盖。
9. 任何向后兼容字段保留都要标记 deprecated，不得继续作为默认控制路径。

---

## Authority / Evidence Model

Direct authorities:

- `.autoreskill/graph/GRAPH_BUILD_DECISION.json`：决定 graph build 是否完成。
- `.autoreskill/ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json`：决定 ideation 是否 ready。
- `.autoreskill/orchestrator/INNOVATION_PACKET.json`：决定 experiment plan 是否有可执行 baseline-first design。
- `.autoreskill/reviewer/REVIEW_FINDINGS.json`：决定 review pressure 是否仍有 blocking issues。
- `.autoreskill/submission_ready.json`：决定 mechanical submission package 是否 ready。

Evidence and boundary artifacts:

- `.autoreskill/papernexus/idea_catalyst_evidence_export.json`：selected/supporting idea fragments 的 source-backed evidence export。
- `.autoreskill/papernexus/research_controller/controller-export.json`：research controller run export。
- `.autoreskill/papernexus/research_controller/design-review.json`：controller 或 fallback design review verdict。
- `.autoreskill/papernexus/research_controller/innovation-brief.json`：controller-derived innovation boundary，列出哪些 claim/source/fragment 可用于 experiment plan。
- `.autoreskill/artifacts_index.json`：artifact provenance index。
- `.autoreskill/evidence_cart.jsonl`：evidence cart，不直接推进 stage。
- `.autoreskill/reviewer/academic-paper-reviewer/raw/*`：原始多 reviewer 输出，供 adapter provenance 使用。

状态推进规则：

```text
PaperNexus remote result
  -> papernexus_artifact_capture.py
  -> evidence export / controller artifacts / innovation brief
  -> idea_support_lint.py + innovation_lint.py
  -> contract_lint.py stage=experiment_plan
  -> goal_tick.py / goal_validate.py visible workflow state
```

Review gate 规则：

```text
academic-paper-reviewer reports / editorial decision
  -> review_findings_adapter.py
  -> REVIEW_FINDINGS.json
  -> review_lint.py
  -> contract_lint.py stage=review_pressure
```

Venue package 规则：

```text
goal_state target_venue
  -> venue_profile(...)
  -> goal_package.py generated/required artifacts
  -> submission_lint.py
  -> submission_ready.json
```

---

## Plan of Work

### Phase 0: Context Inventory and Fixture Design

目标：

- 冻结当前 file map、现有字段、缺口、验证入口。
- 设计最小离线 fixture，使新增 gate 不依赖实时 PaperNexus。

改动：

- 不改 production scripts，只补充本 ExecPlan 的事实记录。
- 设计 fixture artifact set：
  - `.autoreskill/capabilities.json` with `papernexus_remote_callable=true` and optional `research_controller_available=true/false`。
  - `.autoreskill/papernexus/idea_catalyst_evidence_export.json` with selected idea fragment, source papers, spans, provenance。
  - `.autoreskill/papernexus/research_controller/innovation-brief.json` with source-backed / inferred / speculative sections。
  - `.autoreskill/orchestrator/INNOVATION_PACKET.json` referencing those artifacts。
  - markdown/JSON sample output from `academic-paper-reviewer` for adapter tests。

验收：

- Plan 中能列出每个 gate 的 input/output。
- 每个 planned linter 有至少一个 pass fixture 和一个 fail fixture。

### Phase 1: Add `idea_support_lint.py`

目标：

- 独立验证 selected idea 是否有 PaperNexus source-backed evidence 支撑。
- 让 `experiment_plan` 不再只凭 `supporting_idea_fragment_ids` 字段存在通过。

文件：

- Add `~/.codex/skills/autoreskill-papernexus-innovation/scripts/idea_support_lint.py`
- Update `~/.codex/skills/autoreskill-papernexus-innovation/SKILL.md`
- Update `~/.codex/skills/autoreskill-papernexus-innovation/references/innovation_packet_schema.md`

建议 CLI：

```bash
python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/idea_support_lint.py \
  --project <project-root> \
  --packet .autoreskill/orchestrator/INNOVATION_PACKET.json \
  --evidence-export .autoreskill/papernexus/idea_catalyst_evidence_export.json
```

输入 contract：

- `INNOVATION_PACKET.selected_idea_fragment_id` 必须存在。
- `INNOVATION_PACKET.supporting_idea_fragment_ids` 必须包含 selected fragment 或明确列出 supporting fragments。
- `INNOVATION_PACKET.idea_evidence_export_path` 必须指向 existing artifact，默认 fallback 为 `papernexus/idea_catalyst_evidence_export.json`。
- evidence export 必须包含：
  - fragment id / idea id；
  - source paper id/title/doi/arxiv/url 中至少一种；
  - source span、quote、claim summary 或 section locator 中至少一种；
  - provenance metadata：`source=papernexus-remote` 或 capture metadata；
  - evidence status/category 可以被判为 `source_backed` 或 `graph_grounded`。

输出 schema：

```json
{
  "schema_version": 1,
  "complete": true,
  "status": "complete",
  "selected_idea_fragment_id": "...",
  "source_backed_fragment_count": 1,
  "missing": [],
  "warnings": [],
  "evidence_export_path": "papernexus/idea_catalyst_evidence_export.json",
  "supported_fragments": [
    {
      "fragment_id": "...",
      "evidence_status": "source_backed",
      "source_count": 2,
      "span_count": 2
    }
  ]
}
```

Fail cases：

- Missing evidence export。
- selected fragment 不在 evidence export。
- 只有 local/prompt inference，没有 PaperNexus provenance。
- 有 source paper 但没有 source span / claim locator。
- evidence status 是 `agent_inferred` 或 `speculative`。

### Phase 2: Strengthen `innovation_lint.py`

目标：

- 把 `INNOVATION_PACKET.json` 从字段存在检查升级为 experiment-plan authority check。

文件：

- Update `~/.codex/skills/autoreskill-experiment-plan/scripts/innovation_lint.py`
- Update `~/.codex/skills/autoreskill-experiment-plan/SKILL.md`
- Update `~/.codex/skills/autoreskill-experiment-plan/references/experiment_review_packet_schema.md`

新增 hard requirements：

- Required baseline-first experiment fields：
  - `selected_idea_fragment_id`
  - `baseline`
  - `primary_metric`
  - `fixed_budget`
  - `one_variable_change` or equivalent explicit intervention statement
  - `falsifier` or `failure_condition`
  - `dataset_or_benchmark`
- Required evidence fields：
  - `idea_evidence_export_path`
  - `evidence_status` in `source_backed`, or per-claim boundary marking enough to identify source-backed support
  - `evidence_boundaries` with `source_backed`, `agent_inferred`, `speculative`, `unsupported`
  - `supporting_idea_fragment_ids`
- Required controller/design fields when available：
  - `controller_innovation_brief_path`
  - `controller_design_review_path`
  - design review status/verdict in ready/pass/approved/complete
- Compatibility:
  - Keep legacy `evidence_paths` and `supporting_papers` accepted as evidence locations only when they resolve to structured artifacts or source-backed source records.
  - Emit warnings for legacy-only packet shape; fail only when source-backed support cannot be established.

输出变化：

- Include nested `idea_support` result when `idea_support_lint.py` is available.
- Include `evidence_boundary_summary` counts.
- Return non-zero if selected idea is unsupported, design review is missing, or experiment design lacks baseline-first falsifier.

### Phase 3: Strengthen `contract_lint.py` and `goal_validate.py`

目标：

- 让 stage gate 使用同一套 canonical linter，避免 `contract_lint.py` 和 specialized linter 语义漂移。

文件：

- Update `~/.codex/skills/autoreskill-workflow-guard/scripts/contract_lint.py`
- Update `~/.codex/skills/autoreskill-workflow-guard/scripts/goal_validate.py`
- Update `~/.codex/skills/autoreskill-workflow-guard/references/stage_contracts.md`

实现规则：

- `contract_lint.py stage=experiment_plan` 应调用或复用 `innovation_lint.lint(...)` 的 logic，而不是复制字段检查。
- 如果 import path 不稳定，使用 local helper subprocess wrapper 也可以，但输出必须嵌入 `details`。
- `goal_validate.py` 的 `specialized_linters` 新增：
  - `idea_support`
  - `review_adapter_fixture` 或 adapter dry-run validation
- `validation_summary(...)` 要把新增 linter failure 纳入 `specialized_failures`。

验收：

- 缺少 evidence export 时：
  - `idea_support_lint.py` fail
  - `innovation_lint.py` fail
  - `contract_lint.py --stage experiment_plan` fail
  - `goal_validate.py` summary fail
- pass fixture 时四者同时 pass。

### Phase 4: Research-Controller Innovation Brief Boundary

目标：

- 把 PaperNexus `research_controller` 的 export/design review 转换为 downstream experiment plan 可引用的 boundary artifact。

文件：

- Update `~/.codex/skills/autoreskill-papernexus-research-controller/scripts/controller_lint.py`
- Add or update `~/.codex/skills/autoreskill-papernexus-research-controller/scripts/controller_brief.py`
- Update `~/.codex/skills/autoreskill-papernexus-research-controller/references/controller_artifact_schema.md`
- Update `~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py`
- Update `~/.codex/skills/autoreskill-papernexus-research-controller/SKILL.md`

New artifact:

```text
.autoreskill/papernexus/research_controller/innovation-brief.json
```

Suggested schema:

```json
{
  "schema_version": 1,
  "status": "ready",
  "selected_idea_fragment_id": "",
  "selected_subgraph_ids": [],
  "controller_export_path": "papernexus/research_controller/controller-export.json",
  "design_review_path": "papernexus/research_controller/design-review.json",
  "what_is_evidence_supported": [],
  "what_is_agent_inferred": [],
  "what_is_speculative": [],
  "unsupported_or_open_gaps": [],
  "evidence_boundaries": {
    "source_backed": [],
    "agent_inferred": [],
    "speculative": [],
    "unsupported": []
  }
}
```

Rules:

- `controller_brief.py` may derive the brief from controller export + design review + selected subgraphs.
- If research controller is unavailable, `ideation/PANEL_DESIGN_REVIEW.json` may be accepted as fallback, but the brief must mark `source="fallback_panel"` and cannot mark speculative content as source-backed.
- `innovation_lint.py` should require `controller_innovation_brief_path` when `capabilities.research_controller_available=true`.
- `controller_lint.py` should check innovation brief if any innovation packet references it.

### Phase 5: Academic Reviewer Adapter to `REVIEW_FINDINGS.json`

目标：

- 把 `academic-paper-reviewer` 的 human-readable multi-review output 变成 AutoResearch review gate 可以消费的 canonical JSON。

文件：

- Add `~/.codex/skills/academic-paper-reviewer/scripts/review_findings_adapter.py`
- Update `~/.codex/skills/academic-paper-reviewer/SKILL.md`
- Update `~/.codex/skills/autoreskill-review-gate/SKILL.md`
- Update `~/.codex/skills/autoreskill-review-gate/scripts/review_lint.py` only if needed for schema compatibility.

CLI:

```bash
python ~/.codex/skills/academic-paper-reviewer/scripts/review_findings_adapter.py \
  --project <project-root> \
  --input <academic-review-output.md-or-json> \
  --output .autoreskill/reviewer/REVIEW_FINDINGS.json \
  --mode full
```

Adapter behavior:

- Accept Markdown or JSON output.
- Preserve raw input under `.autoreskill/reviewer/academic-paper-reviewer/raw/`.
- Extract issues from weaknesses, editorial decision, revision roadmap, questions for authors, and Devil's Advocate critical items.
- Normalize severity:
  - `Critical` -> `critical`
  - `Major` -> `high`
  - `Minor` -> `medium`
  - editorial/admin/style-only -> `low`
- Normalize status:
  - default extracted issue status is `open`
  - explicit repaired/resolved/waived text may become `resolved` or `waived`, but only in re-review mode with source evidence.
- Emit:
  - `status=needs_repair` if any open high/critical issue exists
  - `status=ready` only if no open high/critical issues
  - `source_adapter="academic-paper-reviewer"`
  - `reviewer_count`
  - `decision`
  - `issues[]` with `id`, `severity`, `status`, `source_reviewer`, `message`, `evidence`, `recommendation`, `source_span`, `blocks_submission`

Review gate behavior:

- `review_lint.py` should continue to pass/fail based on open high/critical findings.
- `contract_lint.py stage=review_pressure` should not need to know the original academic-review format; it only consumes `REVIEW_FINDINGS.json`.

### Phase 6: Remove NMI Defaults and Copy

目标：

- NMI 不再是 implicit default。所有 package logic 使用 target venue profile。

文件：

- Update `~/.codex/skills/autoreskill-workflow-guard/scripts/goal_state.py`
- Update `~/.codex/skills/autoreskill-workflow-guard/scripts/goal_package.py`
- Update `~/.codex/skills/autoreskill-paper-write/scripts/paper_scaffold.py`
- Update `~/.codex/skills/autoreskill-paper-write/references/story_contract_schema.md`
- Update `~/.codex/skills/autoreskill-review-gate/scripts/submission_lint.py`
- Update `~/.codex/skills/autoreskill-paper-write/references/nmi_submission_notes.md` only to clarify it is profile-specific.

Rules:

- Introduce `DEFAULT_TARGET_VENUE = "unspecified_top_tier"` or equivalent.
- `venue_profile("unspecified_top_tier")` should generate generic top-tier required artifacts:
  - `paper/TARGET_VENUE_SUMMARY.md`
  - `paper/REPRODUCIBILITY_CHECKLIST.md`
  - `paper/VENUE_CHECKLIST_GAPS.md`
  - `reviewer/CITATION_INTEGRITY_REPORT.md`
- `submission_lint.py` fallback must use generic target-venue artifacts, not `paper/NMI_SUMMARY_PARAGRAPH.md`.
- `goal_package.py` should write `actual_target_submission_ready`; keep `actual_nmi_submission_ready` only if required for backward compatibility and mark deprecated.
- `paper/NMI_SUMMARY_PARAGRAPH.md` should only be generated when profile key is explicitly `nmi`.
- `story_contract_schema.md` should use `"target_venue": "unspecified_top_tier"` or `"target_venue": "<venue_profile_key>"`.
- Job packet goal text should say target-venue readiness, not NMI readiness.

### Phase 7: Regression Fixtures and Documentation Sync

目标：

- 让另一个 agent 不需要聊天记录也能验证这些 changes。

文件：

- Update relevant `SKILL.md` files with concise instructions.
- Add reference snippets or schemas where needed, keeping SKILL.md lean.
- Add fixture docs or scripts only if they reduce repeated manual setup.

Recommended permanent fixtures:

- `.codex` skill scripts do not currently have a formal tests directory. If adding tests, prefer a small `scripts/selftest_*.py` or documented temp fixture commands over creating a large custom framework.
- If a formal tests directory is added, keep it scoped:
  - `~/.codex/skills/autoreskill-papernexus-innovation/tests/idea_support_fixture.py`
  - `~/.codex/skills/academic-paper-reviewer/tests/review_findings_adapter_fixture.py`

验收：

- A fresh temp project can run the validation commands below.
- Failure fixtures demonstrate each new hard gate fails for the intended reason.

---

## Validation Commands

Run local compile from any directory:

```bash
python -m py_compile \
  ~/.codex/skills/autoreskill-papernexus-innovation/scripts/*.py \
  ~/.codex/skills/autoreskill-papernexus-research-controller/scripts/*.py \
  ~/.codex/skills/autoreskill-experiment-plan/scripts/*.py \
  ~/.codex/skills/autoreskill-workflow-guard/scripts/*.py \
  ~/.codex/skills/autoreskill-review-gate/scripts/*.py \
  ~/.codex/skills/academic-paper-reviewer/scripts/*.py
```

Run stage-specific pass fixture:

```bash
PROJECT="$(mktemp -d)"
python ~/.codex/skills/autoreskill-workflow-guard/scripts/goal_state.py init \
  --project "$PROJECT" \
  --goal "fixture: source-backed idea support" \
  --venue NeurIPS

# Create or capture fixture artifacts:
# - .autoreskill/capabilities.json
# - .autoreskill/papernexus/idea_catalyst_evidence_export.json
# - .autoreskill/papernexus/research_controller/innovation-brief.json
# - .autoreskill/papernexus/research_controller/design-review.json
# - .autoreskill/orchestrator/INNOVATION_PACKET.json

python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/idea_support_lint.py \
  --project "$PROJECT"
python ~/.codex/skills/autoreskill-experiment-plan/scripts/innovation_lint.py \
  --project "$PROJECT"
python ~/.codex/skills/autoreskill-workflow-guard/scripts/contract_lint.py \
  --project "$PROJECT" \
  --stage experiment_plan
```

Run negative fixture:

```bash
PROJECT="$(mktemp -d)"
python ~/.codex/skills/autoreskill-workflow-guard/scripts/goal_state.py init \
  --project "$PROJECT" \
  --goal "fixture: unsupported idea should fail" \
  --venue ICLR

# Create INNOVATION_PACKET.json without source-backed evidence export.
python ~/.codex/skills/autoreskill-papernexus-innovation/scripts/idea_support_lint.py \
  --project "$PROJECT"
# Expected: non-zero exit, missing includes idea evidence export or selected source-backed fragment.
```

Run review adapter fixture:

```bash
PROJECT="$(mktemp -d)"
python ~/.codex/skills/autoreskill-workflow-guard/scripts/goal_state.py init \
  --project "$PROJECT" \
  --goal "fixture: review adapter" \
  --venue custom

python ~/.codex/skills/academic-paper-reviewer/scripts/review_findings_adapter.py \
  --project "$PROJECT" \
  --input /path/to/fixture-academic-review.md \
  --mode full

python ~/.codex/skills/autoreskill-review-gate/scripts/review_lint.py \
  --project "$PROJECT"
```

Run full local validation matrix:

```bash
python ~/.codex/skills/autoreskill-workflow-guard/scripts/goal_validate.py \
  --project "$PROJECT" \
  --output validation/PHASE8_VALIDATION.json
```

Expected:

- `py_compile` passes.
- Positive fixture passes `idea_support_lint.py`, `innovation_lint.py`, `contract_lint.py --stage experiment_plan`.
- Negative fixture fails with specific `missing` fields, not generic parse errors.
- Review adapter writes `REVIEW_FINDINGS.json`; `review_lint.py` blocks open high/critical findings.
- `goal_validate.py` includes `idea_support` and adapter checks in `specialized_linters`.
- `goal_state.py init` without `--venue` no longer creates an implicit NMI package path.

---

## Acceptance Criteria

This ExecPlan is complete when:

- [ ] `idea_support_lint.py` exists and rejects unsupported selected idea fragments.
- [ ] `innovation_lint.py` checks baseline-first experiment fields, source-backed evidence, evidence boundaries, and controller/design review references.
- [ ] `contract_lint.py stage=experiment_plan` uses the strengthened innovation/idea-support logic.
- [ ] `goal_validate.py` reports `idea_support` and adapter-related failures in `specialized_failures`.
- [ ] research-controller innovation brief has a documented schema and is checked by controller/innovation gates.
- [ ] `academic-paper-reviewer/scripts/review_findings_adapter.py` converts Markdown/JSON review outputs into `REVIEW_FINDINGS.json` with provenance.
- [ ] `review_lint.py` blocks open high/critical issues produced by the adapter.
- [ ] NMI is no longer an implicit default in `goal_state.py`, `goal_package.py`, `paper_scaffold.py`, story contract examples, or submission fallback lint.
- [ ] All touched Python scripts pass `python -m py_compile`.
- [ ] A temp pass fixture and temp fail fixture demonstrate the new gates.
- [ ] Documentation explains direct authority vs evidence artifacts without relying on chat history.

---

## Idempotence and Recovery

可重复运行：

- `python -m py_compile ...`：只检查 syntax，不写 project state。
- `idea_support_lint.py --project <project>`：read-only linter，重复运行应输出相同 result。
- `innovation_lint.py --project <project>`：read-only linter，重复运行应输出相同 result。
- `contract_lint.py --stage experiment_plan`：read-only linter。
- `review_findings_adapter.py --project <project> --input <file>`：可重复，但应把 raw input 用 content hash 或 timestamp 保存，避免覆盖 provenance；`REVIEW_FINDINGS.json` 可以 deterministic overwrite。
- `goal_validate.py --output validation/PHASE8_VALIDATION.json`：可重复，会覆盖 validation output。

恢复方式：

- 中断后先检查：
  - `git diff -- ~/.codex/skills`
  - `python -m py_compile <touched scripts>`
  - `python .../goal_validate.py --project <fixture>`
- 如果 adapter 已生成 raw review artifacts，检查 `.autoreskill/reviewer/academic-paper-reviewer/raw/` 和 `REVIEW_FINDINGS.json` 的 `source_input_hash`。
- 如果 fixture project 状态混乱，丢弃 temp directory 重新生成；不要把 failed fixture 当成 canonical project state。

不可自动重试：

- 实时 PaperNexus remote imports。
- 真实实验运行、付费 GPU job、提交/发布/PR merge。
- 覆盖用户已有论文主文件或 canonical figures。

---

## Risks and Rollback

| Risk | Signal | Mitigation | Rollback |
|---|---|---|---|
| Gate 过强导致已有 portable projects 全部卡住 | `goal_validate.py` 大量 fail 且 missing 指向 legacy packet shape | 先支持 legacy fields with warning，但 source-backed support 仍为 hard requirement | 暂时在 `innovation_lint.py` 加 compatibility mode，默认仍严格 |
| evidence export schema 不统一 | `idea_support_lint.py` 无法找到 fragment/source/span | 实现 schema-normalization helpers，接受 snake/camel case 和 nested result/data/payload | 保留原始 payload path，输出具体 missing path 供 capture 修复 |
| adapter 误判 review severity | Minor issue 被升为 high 或 critical | Severity mapping 保守且可配置；保留 raw source span | 在 adapter output 中标记 `adapter_confidence`，人工修正 `REVIEW_FINDINGS.json` 后由 `review_lint.py` gate |
| NMI 兼容字段移除破坏旧项目 | 旧 project 依赖 `actual_nmi_submission_ready` | 保留 deprecated field only when profile is NMI；新增 `actual_target_submission_ready` | 恢复 deprecated field，但不恢复 NMI default |
| controller unavailable 时无法推进 | `research_controller_available=false` 且没有 fallback design review | 允许 `ideation/PANEL_DESIGN_REVIEW.json` fallback，但降低 evidence status | 明确 blocker，不自动伪造 controller evidence |
| `contract_lint.py` import specialized linter 失败 | PYTHONPATH/path problem | 使用 small shared helper or subprocess with explicit script path | 回退为 local copy of minimal check only temporarily，并记录 duplication debt |

---

## Progress

- [x] 2026-05-26 11:39 CST Current state scanned across contract, innovation, validation, PaperNexus capture, controller lint, review lint, venue package, and NMI defaults.
- [x] 2026-05-26 11:39 CST ExecPlan drafted with direct authority, evidence model, phases, validation commands, and acceptance criteria.
- [x] 2026-05-26 12:18 CST Implement Phase 1 `idea_support_lint.py`.
- [x] 2026-05-26 12:18 CST Implement Phase 2 strengthened `innovation_lint.py`.
- [x] 2026-05-26 12:18 CST Implement Phase 3 contract/validation integration.
- [x] 2026-05-26 12:18 CST Implement Phase 4 research-controller innovation brief boundary.
- [x] 2026-05-26 12:18 CST Implement Phase 5 academic reviewer adapter.
- [x] 2026-05-26 12:18 CST Implement Phase 6 venue-default cleanup.
- [x] 2026-05-26 12:18 CST Run validation commands and record results in this document.

---

## Surprises & Discoveries

- Observation: `goal_validate.py` already has a specialized linter matrix, so the right extension point is additive rather than a new validator.
  Evidence: `specialized_linters(project)` includes `controller`, `innovation`, `review`, `citation`, `submission`, etc.
  Action: Add `idea_support` and adapter validation to that matrix.

- Observation: `goal_package.py` already has multi-venue profiles, but defaults and fallback paths still encode NMI.
  Evidence: `--venue default="NMI"`, `actual_nmi_submission_ready`, and `submission_lint.py` fallback requiring `paper/NMI_SUMMARY_PARAGRAPH.md`.
  Action: Keep venue profile design and remove implicit NMI defaults.

- Observation: `review_lint.py` is already structurally compatible with an adapter.
  Evidence: It accepts `issues`, `findings`, `review_findings`, or `items`.
  Action: Adapter can target existing schema without rewriting review gate.

- Observation: The academic-paper-reviewer Markdown template writes severity as bold Markdown, e.g. `**Severity**: Major`.
  Evidence: Initial adapter fixture produced zero issues until the parser stripped Markdown emphasis before severity matching.
  Action: Normalize Markdown emphasis before parsing role and severity lines.

---

## Decision Log

- Decision: Keep `INNOVATION_PACKET.json` as the direct authority for `experiment_plan`.
  Context: OpenClaw alignment favors one canonical machine-readable completion source per stage.
  Consequence: Evidence export and controller brief are required support artifacts, not independent stage authorities.

- Decision: Implement `idea_support_lint.py` under `autoreskill-papernexus-innovation`, not under workflow guard.
  Context: The check is PaperNexus evidence-specific and should be reusable by innovation and validation flows.
  Consequence: `contract_lint.py` should import/call it rather than own PaperNexus schema logic.

- Decision: Place review adapter under `academic-paper-reviewer/scripts`.
  Context: The adapter understands academic-reviewer output formats and should travel with that producer skill.
  Consequence: `autoreskill-review-gate` remains the consumer of normalized `REVIEW_FINDINGS.json`.

- Decision: Replace implicit NMI default with `unspecified_top_tier` or equivalent generic profile.
  Context: The skill pack should support top-tier conferences/journals without biasing every run to NMI.
  Consequence: Existing explicit NMI runs remain supported; implicit default output becomes venue-neutral.

---

## Artifacts

- `<AUTORESEARCH_EXECPLAN_DIR>/Codex-AutoResearch-Skill-Contract-Closure-ExecPlan-2026-05-26.md`：本 ExecPlan。
- `~/.codex/skills/autoreskill-workflow-guard/scripts/goal_validate.py`：planned validation integration point。
- `~/.codex/skills/autoreskill-papernexus-innovation/scripts/idea_support_lint.py`：source-backed selected idea support gate。
- `~/.codex/skills/autoreskill-experiment-plan/scripts/innovation_lint.py`：strengthened experiment-plan authority linter。
- `~/.codex/skills/autoreskill-papernexus-research-controller/scripts/controller_brief.py`：research-controller innovation brief materializer。
- `~/.codex/skills/autoreskill-papernexus-innovation/scripts/papernexus_artifact_capture.py`：artifact capture extension point with `research_controller_innovation_brief` support。
- `~/.codex/skills/academic-paper-reviewer/scripts/review_findings_adapter.py`：academic reviewer output adapter to `REVIEW_FINDINGS.json`。
- `~/.codex/skills/autoreskill-review-gate/scripts/review_lint.py`：existing canonical review findings consumer。
- Validation summary from final fixture:
  - positive project `/var/folders/ld/gwn4r9d963s5m3dbbjllj2l80000gn/T/autoreskill-final-pass-89x1ujjd`: `idea_support`, `innovation`, `contract_experiment_plan`, and `controller` all returned complete.
  - negative project `/var/folders/ld/gwn4r9d963s5m3dbbjllj2l80000gn/T/autoreskill-final-fail-s7uy1uyw`: missing `papernexus/idea_catalyst_evidence_export.json` blocked `idea_support`, `innovation`, and `contract_experiment_plan`.
  - review adapter fixture produced `status=needs_repair`; `review_lint.py` failed with `open high/critical review findings`.
  - JSON review fixture `/var/folders/ld/gwn4r9d963s5m3dbbjllj2l80000gn/T/autoreskill-json-review-ktpfa68b`: adapter mapped a JSON `Critical` issue to `critical`, wrote `status=needs_repair`, and `review_lint.py` blocked.
  - default venue fixture produced `target_venue=unspecified_top_tier`, package profile `unspecified_top_tier`, and no `paper/NMI_SUMMARY_PARAGRAPH.md`.
  - full offline validation fixture `/var/folders/ld/gwn4r9d963s5m3dbbjllj2l80000gn/T/autoreskill-full-pass-eqjjwbmg`: `goal_validate.py` returned `ok=true`, `stage_contract_failures=[]`, and `specialized_failures=[]`.

---

## Outcomes & Retrospective

Actual outcome:

- Implemented the five contract-closure gaps from this ExecPlan:
  - source-backed idea support linter;
  - strengthened innovation and experiment-plan contract gate;
  - research-controller innovation brief boundary;
  - academic-paper-reviewer to `REVIEW_FINDINGS.json` adapter;
  - venue-neutral default package flow.

Remaining gaps:

- Need decide exact normalized schema helpers after inspecting real PaperNexus `idea_catalyst_evidence_export` examples.
- Need run against a real academic-paper-reviewer output sample beyond template-style Markdown.
- Need run the full AutoResearch validation matrix on a real non-fixture project before using these gates as release evidence.

Lessons for future harness:

- Keep direct authority small and canonical, but make the authority cite machine-verifiable evidence boundaries.
- Avoid using venue-specific journal artifacts as fallback defaults; venue-specific files should only appear through explicit profile selection.
- Review outputs are only useful to workflow control once converted into stable machine-readable findings.
