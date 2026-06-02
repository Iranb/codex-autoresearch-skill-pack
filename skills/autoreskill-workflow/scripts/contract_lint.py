#!/usr/bin/env python3
"""Lint .autoreskill stage contracts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


READY = {"ready", "complete", "completed", "pass", "passed", "verified"}
IDEA_LIFECYCLE_STATUSES = {
    "selected_primary",
    "alternate_track",
    "risk_repair_track",
    "advance_with_constraints",
    "repair_needed",
    "parked",
    "killed",
    "degraded_speculative",
}
IDEA_FAILURE_CLASSES = {
    "none",
    "novelty_collision",
    "closest_prior_overlap",
    "story_collapse",
    "three_innovation_bundle_incomplete",
    "evidence_gap",
    "proposal_graph_uncommitted",
    "target_domain_only_method",
    "baseline_unavailable",
    "protocol_unsafe",
    "metric_or_dataset_drift_risk",
    "feasibility_fail",
    "risk_uncontrolled",
    "low_expected_value",
}
BIE_REQUIRED_FIELDS = [
    "branch_budget_B",
    "search_iterations_I",
    "versions_per_branch_E",
    "retain_top_K",
    "stop_on_spec_violation",
    "promotion_required",
]


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def has_any(base: Path, rels: list[str]) -> bool:
    return any(nonempty(base / rel) or (base / rel).exists() for rel in rels)


def has_glob(base: Path, pattern: str) -> bool:
    return any(path.is_file() and nonempty(path) for path in base.glob(pattern))


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def degraded_gate_approved(gate: Any) -> bool:
    if not isinstance(gate, dict):
        return False
    if str(gate.get("status") or "").strip().lower() != "degraded_requires_user_approval":
        return False
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return False
    if not present(approval.get("approved_by")) or not present(approval.get("approved_at")) or not present(approval.get("reason")):
        return False
    return present(gate.get("claim_limits") or approval.get("claim_limits"))


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["tracks", "rows", "track_plans", "ideas", "decisions", "outcomes", "idea_outcomes"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def idea_ids_from_pool(pool: Any) -> set[str]:
    ids: set[str] = set()
    if not isinstance(pool, dict):
        return ids
    for key in ["ideas", "candidates"]:
        rows = pool.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    idea_id = row.get("id") or row.get("idea_id")
                    if present(idea_id):
                        ids.add(str(idea_id))
    return ids


def track_seed_idea_ids(seeds: Any) -> set[str]:
    ids: set[str] = set()
    for row in rows_from_payload(seeds):
        idea_id = row.get("idea_id")
        if present(idea_id):
            ids.add(str(idea_id))
    return ids


def validate_idea_decision_ledger(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    ledger_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    ledger = read_json(ledger_path)
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json")
    seeds = read_json(base / "ideation/IDEA_TRACK_SEEDS.json")
    if not ledger:
        return ["ideation/IDEA_DECISION_LEDGER.json"], warnings, {}
    decisions = ledger.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        missing.append("ideation/IDEA_DECISION_LEDGER.json decisions[]")
        decisions = []
    decision_ids: set[str] = set()
    lifecycle_by_id: dict[str, str] = {}
    for index, decision in enumerate(row for row in decisions if isinstance(row, dict)):
        prefix = f"ideation/IDEA_DECISION_LEDGER.json decisions[{index}]"
        for field in ["idea_id", "scorecard_rank", "lifecycle_status", "decision_reason", "failure_class", "evidence_refs", "claim_scope", "next_action"]:
            if not present(decision.get(field)):
                missing.append(f"{prefix}.{field}")
        idea_id = decision.get("idea_id")
        if present(idea_id):
            decision_ids.add(str(idea_id))
        status = str(decision.get("lifecycle_status") or "").strip()
        failure_class = str(decision.get("failure_class") or "").strip()
        if status and status not in IDEA_LIFECYCLE_STATUSES:
            missing.append(f"{prefix}.lifecycle_status must be one of {sorted(IDEA_LIFECYCLE_STATUSES)}")
        if failure_class and failure_class not in IDEA_FAILURE_CLASSES:
            missing.append(f"{prefix}.failure_class must be one of {sorted(IDEA_FAILURE_CLASSES)}")
        if status in {"parked", "killed", "repair_needed", "advance_with_constraints", "degraded_speculative"}:
            if "can_reenter" not in decision:
                missing.append(f"{prefix}.can_reenter")
            if not present(decision.get("reentry_conditions")) and decision.get("can_reenter") is True:
                missing.append(f"{prefix}.reentry_conditions")
        if present(idea_id):
            lifecycle_by_id[str(idea_id)] = status
    pool_ids = idea_ids_from_pool(pool)
    if pool_ids:
        missing_ids = sorted(pool_ids - decision_ids)
        if missing_ids:
            missing.append("IDEA_DECISION_LEDGER missing pool ideas: " + ", ".join(missing_ids))
        extra_ids = sorted(decision_ids - pool_ids)
        if extra_ids:
            warnings.append("IDEA_DECISION_LEDGER has decisions for ids not found in pool: " + ", ".join(extra_ids))
    seed_ids = track_seed_idea_ids(seeds)
    for seed_id in sorted(seed_ids):
        status = lifecycle_by_id.get(seed_id)
        if not status:
            missing.append(f"IDEA_TRACK_SEEDS idea {seed_id} lacks IDEA_DECISION_LEDGER row")
        elif status == "killed":
            missing.append(f"IDEA_TRACK_SEEDS idea {seed_id} is killed in IDEA_DECISION_LEDGER")
        elif status == "parked":
            missing.append(f"IDEA_TRACK_SEEDS idea {seed_id} is parked in IDEA_DECISION_LEDGER")
        elif status not in {"selected_primary", "alternate_track", "risk_repair_track", "advance_with_constraints"}:
            warnings.append(f"IDEA_TRACK_SEEDS idea {seed_id} has lifecycle_status={status}; verify this is intentional")
    return missing, warnings, {"decision_count": len(decisions), "pool_idea_count": len(pool_ids), "track_seed_count": len(seed_ids)}


def validate_track_plan_lifecycle(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json")
    if not matrix:
        return ["orchestrator/TRACK_PLAN_MATRIX.json"], warnings, {}
    bie_config = matrix.get("bie_config") if isinstance(matrix.get("bie_config"), dict) else {}
    if not bie_config:
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json bie_config")
    else:
        for field in BIE_REQUIRED_FIELDS:
            if not present(bie_config.get(field)):
                missing.append(f"orchestrator/TRACK_PLAN_MATRIX.json bie_config.{field}")
    if not present(matrix.get("source_idea_decision_ledger_path")) and not present(matrix.get("idea_decision_ledger_path")):
        missing.append("orchestrator/TRACK_PLAN_MATRIX.json source_idea_decision_ledger_path")
    rows = rows_from_payload(matrix)
    for index, row in enumerate(rows):
        prefix = f"orchestrator/TRACK_PLAN_MATRIX.json tracks[{index}]"
        if not present(row.get("idea_decision_ref")):
            missing.append(f"{prefix}.idea_decision_ref")
        if not present(row.get("branch_id")):
            warnings.append(f"{prefix}.branch_id recommended for B/I/E search tracing")
    return missing, warnings, {"bie_config_present": bool(bie_config), "track_count": len(rows)}


def validate_experiment_failure_lineage(base: Path, ledger: dict[str, Any] | None) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    entries = rows_from_payload((ledger or {}).get("entries") if isinstance(ledger, dict) else None)
    failure_like = {
        "failed",
        "failure",
        "budget_stopped",
        "not_promoted",
        "rollback_to_best",
        "repair",
    }
    for index, entry in enumerate(entries):
        prefix = f"coder/EXPERIMENT_LEDGER.json entries[{index}]"
        decision = str(entry.get("promotion_decision") or entry.get("promotion_status") or entry.get("verdict") or "").strip().lower()
        status = str(entry.get("status") or "").strip().lower()
        spec = str(entry.get("spec_violation_status") or "").strip().lower()
        is_failure = decision in failure_like or status in {"failed", "failure", "budget_stopped"} or spec in {"flagged", "violation", "failed"}
        if is_failure:
            if not present(entry.get("failure_class")):
                missing.append(f"{prefix}.failure_class")
            if not present(entry.get("next_action")):
                missing.append(f"{prefix}.next_action")
            if not present(entry.get("selected_idea_id")):
                missing.append(f"{prefix}.selected_idea_id")
            if not present(entry.get("track_id")):
                missing.append(f"{prefix}.track_id")
        if decision == "candidate_supported":
            warnings.append(f"{prefix} candidate_supported is pilot evidence and cannot support stable improvement claims")
    return missing, warnings, {"entry_count": len(entries)}


def validate_idea_outcome_summary(base: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    missing: list[str] = []
    warnings: list[str] = []
    summary = read_json(base / "analyzer/IDEA_OUTCOME_SUMMARY.json")
    if not summary:
        return ["analyzer/IDEA_OUTCOME_SUMMARY.json"], warnings, {}
    outcomes = summary.get("idea_outcomes") or summary.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json idea_outcomes[]")
        outcomes = []
    if not present(summary.get("source_idea_decision_ledger_path")):
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json source_idea_decision_ledger_path")
    if not present(summary.get("source_experiment_ledger_path")):
        missing.append("analyzer/IDEA_OUTCOME_SUMMARY.json source_experiment_ledger_path")
    for index, outcome in enumerate(row for row in outcomes if isinstance(row, dict)):
        prefix = f"analyzer/IDEA_OUTCOME_SUMMARY.json idea_outcomes[{index}]"
        for field in ["idea_id", "lifecycle_status", "claim_scope", "outcome_status", "next_action"]:
            if not present(outcome.get(field)):
                missing.append(f"{prefix}.{field}")
        claim_scope = str(outcome.get("claim_scope") or "").strip().lower()
        if claim_scope in {"strong_improvement", "stable_improvement", "promoted"} and not present(outcome.get("promoted_run_ref")):
            missing.append(f"{prefix}.promoted_run_ref for strong/promoted claim scope")
        if str(outcome.get("outcome_status") or "").strip().lower() in {"failed", "regressed", "killed", "parked"}:
            if claim_scope not in {"negative_evidence", "limitation", "future_work", "pilot_only", "no_claim", "downgraded"}:
                missing.append(f"{prefix}.claim_scope must not be strong for failed/regressed/parked/killed ideas")
    return missing, warnings, {"outcome_count": len(outcomes)}


def result(
    stage: str,
    complete: bool,
    missing: list[str],
    source: str,
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "missing": missing,
        "warnings": warnings or [],
        "contract_source": source,
        "details": details or {},
    }


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"stdout": proc.stdout}
    parsed.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    return parsed


def run_innovation_story_lint(skill_root: Path, project: str, stage: str) -> dict[str, Any]:
    return run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-workflow/scripts/innovation_story_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
            "--stage",
            stage,
        ]
    )


def lint(project: str, stage: str) -> dict[str, Any]:
    base = ar(project)
    if stage == "init":
        missing = [
            rel
            for rel in [
                "goal_state.json",
                "autopilot_policy.json",
                "capabilities.json",
                "memory.md",
                "decision_log.jsonl",
                "blocker_ledger.jsonl",
                "repair_queue.jsonl",
                "async_jobs.jsonl",
            ]
            if not (base / rel).exists()
        ]
        return result(stage, not missing, missing, "init_contract")

    if stage == "topic_search":
        missing = []
        if not has_any(base, ["literature/LITERATURE_DISCOVERY_PACKET.json", "literature/LITERATURE_DISCOVERY_RUN.json"]):
            missing.append("literature discovery evidence")
        for rel in [
            "papernexus/LITERATURE_DISCOVERY_TRIAGE.json",
            "papernexus/PAPER_SELECTION_SCORECARD.json",
            "papernexus/GRAPH_IMPORT_PLAN.json",
        ]:
            if not nonempty(base / rel):
                missing.append(rel)
        return result(stage, not missing, missing, "topic_search_contract")

    if stage == "graph_build":
        skill_root = Path(__file__).resolve().parents[2]
        decision = read_json(base / "graph/GRAPH_BUILD_DECISION.json")
        graph_plan = read_json(base / "papernexus/GRAPH_IMPORT_PLAN.json")
        import_workflow_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/import_workflow_status_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        missing = []
        warnings = []
        if not bool(decision and decision.get("decision") == "complete" and decision.get("source_backed_graph_claim") is True):
            missing.append("graph/GRAPH_BUILD_DECISION.json decision=complete source_backed_graph_claim=true")
        if not isinstance(graph_plan, dict):
            missing.append("papernexus/GRAPH_IMPORT_PLAN.json")
        elif graph_plan.get("selected_papers") and not (
            import_workflow_lint.get("complete") or nonempty(base / "papernexus/SPLIT_READING_EVIDENCE_PACK.json")
        ):
            items = import_workflow_lint.get("missing") if isinstance(import_workflow_lint.get("missing"), list) else []
            if items:
                missing.extend(f"import_workflow_status_lint: {item}" for item in items)
            else:
                missing.append("papernexus/IMPORT_WORKFLOW_STATUS.json or papernexus/SPLIT_READING_EVIDENCE_PACK.json for selected usable papers")
        items = import_workflow_lint.get("warnings") if isinstance(import_workflow_lint.get("warnings"), list) else []
        warnings.extend(f"import_workflow_status_lint: {item}" for item in items)
        return result(stage, not missing, missing, "graph_build_contract", warnings, {"import_workflow_status_lint": import_workflow_lint})

    if stage == "frontier_mapping":
        ok = has_any(base, ["papernexus/research_material_pack.json", "papernexus/source_discovery_plan.json", "ideation/CHALLENGE_INSIGHT_TREE.md"])
        return result(stage, ok, [] if ok else ["frontier mapping material pack or challenge insight tree"], "frontier_mapping_contract")

    if stage == "literature_review":
        missing = [
            rel
            for rel in ["literature/SOTA_MATRIX.md", "literature/GAP_SYNTHESIS.md", "literature/CITATION_QUEUE.json"]
            if not nonempty(base / rel)
        ]
        return result(stage, not missing, missing, "literature_review_contract")

    if stage == "ideation":
        skill_root = Path(__file__).resolve().parents[2]
        contract = read_json(base / "ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json")
        discovery_packet = read_json(base / "literature/LITERATURE_DISCOVERY_PACKET.json")
        discovery_triage = read_json(base / "papernexus/LITERATURE_DISCOVERY_TRIAGE.json")
        gate_payload = read_json(base / "ideation/PRE_IDEA_EVIDENCE_GATE.json")
        caps = read_json(base / "capabilities.json") or {}
        agent_ops = set(caps.get("agent_materials_operations") or [])
        proposal_graph_available = caps.get("proposal_graph_session_available") is True or "proposal_graph_session" in agent_ops
        approved_degraded = degraded_gate_approved(gate_payload)
        pool_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--pool",
                "ideation/EXPERIMENT_IDEA_POOL.json",
            ]
        )
        scorecard_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_scorecard_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        idea_graph_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_graph_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        pre_idea_gate_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/pre_idea_evidence_gate_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--allow-degraded",
            ]
        )
        proposal_graph_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/proposal_graph_session_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        discovery_config_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/pre_idea_discovery_config_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        paper_selection_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/paper_selection_scorecard_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        breadth_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/pre_idea_breadth_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        graph_import_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/graph_import_plan_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        import_workflow_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/import_workflow_status_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        split_reading_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-papernexus-innovation/scripts/split_reading_evidence_pack_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        idea_decision_missing, idea_decision_warnings, idea_decision_details = validate_idea_decision_ledger(base)
        missing = []
        warnings = []
        if approved_degraded:
            warnings.append("pre-idea gate is approved degraded; discovery/triage gaps are tracked as claim limits")
        elif not discovery_packet:
            missing.append("literature/LITERATURE_DISCOVERY_PACKET.json from pre-idea literature discovery")
        if approved_degraded:
            pass
        elif not discovery_triage:
            missing.append("papernexus/LITERATURE_DISCOVERY_TRIAGE.json from pre-idea candidate screening")
        elif discovery_triage.get("discovery_attempted") is not True:
            missing.append("papernexus/LITERATURE_DISCOVERY_TRIAGE.json discovery_attempted=true")
        elif discovery_triage.get("policy", {}).get("import_resolved") is not False or discovery_triage.get("policy", {}).get("process_imports") is not False:
            missing.append("first-pass ideation literature discovery must be metadata-only and non-importing")
        if not approved_degraded:
            for name, out in {
                "pre_idea_discovery_config_lint": discovery_config_lint,
                "paper_selection_scorecard_lint": paper_selection_lint,
                "pre_idea_breadth_lint": breadth_lint,
                "graph_import_plan_lint": graph_import_lint,
                "import_workflow_status_lint": import_workflow_lint,
                "split_reading_evidence_pack_lint": split_reading_lint,
            }.items():
                if not out.get("complete"):
                    items = out.get("missing") if isinstance(out.get("missing"), list) else []
                    missing.extend(f"{name}: {item}" for item in items)
                    if out.get("returncode", 1) != 0 and not items:
                        missing.append(f"{name} failed without structured missing output")
                items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
                warnings.extend(f"{name}: {item}" for item in items)
        if not pre_idea_gate_lint.get("complete"):
            items = pre_idea_gate_lint.get("missing") if isinstance(pre_idea_gate_lint.get("missing"), list) else []
            missing.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
            if pre_idea_gate_lint.get("returncode", 1) != 0 and not items:
                missing.append("pre_idea_evidence_gate_lint failed without structured missing output")
        items = pre_idea_gate_lint.get("warnings") if isinstance(pre_idea_gate_lint.get("warnings"), list) else []
        warnings.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
        if not contract:
            warnings.append("ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json missing; allowed when pre-idea evidence gate and slot map pass")
        elif contract.get("status") not in {"ready", "brainstorm_ready"}:
            warnings.append("ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json not ready; treating as PaperNexus evidence debt")
        if proposal_graph_available and not approved_degraded:
            if not proposal_graph_lint.get("complete"):
                items = proposal_graph_lint.get("missing") if isinstance(proposal_graph_lint.get("missing"), list) else []
                missing.extend(f"proposal_graph_session_lint: {item}" for item in items)
                if proposal_graph_lint.get("returncode", 1) != 0 and not items:
                    missing.append("proposal_graph_session_lint failed without structured missing output")
        elif not proposal_graph_available:
            warnings.append("proposal_graph_session unavailable or unrecorded; falling back to split-reading slots plus idea_catalyst/research_controller")
        if not pool_lint.get("complete"):
            items = pool_lint.get("missing") if isinstance(pool_lint.get("missing"), list) else []
            missing.extend(f"idea_pool_lint: {item}" for item in items)
            if pool_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_pool_lint failed without structured missing output")
        items = pool_lint.get("warnings") if isinstance(pool_lint.get("warnings"), list) else []
        warnings.extend(f"idea_pool_lint: {item}" for item in items)
        if not scorecard_lint.get("complete"):
            items = scorecard_lint.get("missing") if isinstance(scorecard_lint.get("missing"), list) else []
            missing.extend(f"idea_scorecard_lint: {item}" for item in items)
            if scorecard_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_scorecard_lint failed without structured missing output")
        items = scorecard_lint.get("warnings") if isinstance(scorecard_lint.get("warnings"), list) else []
        warnings.extend(f"idea_scorecard_lint: {item}" for item in items)
        if not idea_graph_lint.get("complete"):
            items = idea_graph_lint.get("missing") if isinstance(idea_graph_lint.get("missing"), list) else []
            missing.extend(f"idea_graph_lint: {item}" for item in items)
            if idea_graph_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_graph_lint failed without structured missing output")
        items = idea_graph_lint.get("warnings") if isinstance(idea_graph_lint.get("warnings"), list) else []
        warnings.extend(f"idea_graph_lint: {item}" for item in items)
        if not approved_degraded:
            for rel in ["ideation/IDEA_BUILD_BRIEF.json", "ideation/IDEA_BUILD_BRIEF.md", "ideation/GOE_IDEA_AUDIT.json"]:
                if not nonempty(base / rel):
                    missing.append(rel)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        return result(
            stage,
            not missing,
            missing,
            "ideation_contract",
            warnings,
            {
                "pre_idea_evidence_gate_lint": pre_idea_gate_lint,
                "pre_idea_discovery_config_lint": discovery_config_lint,
                "paper_selection_scorecard_lint": paper_selection_lint,
                "pre_idea_breadth_lint": breadth_lint,
                "graph_import_plan_lint": graph_import_lint,
                "import_workflow_status_lint": import_workflow_lint,
                "split_reading_evidence_pack_lint": split_reading_lint,
                "innovation_story_lint": innovation_story_lint,
                "proposal_graph_session_lint": proposal_graph_lint,
                "idea_pool_lint": pool_lint,
                "idea_scorecard_lint": scorecard_lint,
                "idea_graph_lint": idea_graph_lint,
                "discovery_triage": discovery_triage or {},
                "proposal_graph_session_available": proposal_graph_available,
            },
        )

    if stage == "idea_gate":
        skill_root = Path(__file__).resolve().parents[2]
        pool_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--pool",
                "ideation/EXPERIMENT_IDEA_POOL.json",
                "--require-selected",
            ]
        )
        scorecard_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_scorecard_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        track_seed_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/idea_track_seeds.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--check",
            ]
        )
        pre_idea_gate_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-ideation-panel/scripts/pre_idea_evidence_gate_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--allow-degraded",
            ]
        )
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        idea_decision_missing, idea_decision_warnings, idea_decision_details = validate_idea_decision_ledger(base)
        missing = []
        warnings = []
        if not has_any(base, ["ideation/TOURNAMENT_SCOREBOARD.json", "ideation/TOP3_DIRECTION_SUMMARY.md", "reviewer/IDEA_GATE_REVIEW.json"]):
            missing.append("idea gate review or tournament scoreboard")
        if not pool_lint.get("complete"):
            items = pool_lint.get("missing") if isinstance(pool_lint.get("missing"), list) else []
            missing.extend(f"idea_pool_lint: {item}" for item in items)
            if pool_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_pool_lint failed without structured missing output")
        items = pool_lint.get("warnings") if isinstance(pool_lint.get("warnings"), list) else []
        warnings.extend(f"idea_pool_lint: {item}" for item in items)
        if not pre_idea_gate_lint.get("complete"):
            items = pre_idea_gate_lint.get("missing") if isinstance(pre_idea_gate_lint.get("missing"), list) else []
            missing.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
            if pre_idea_gate_lint.get("returncode", 1) != 0 and not items:
                missing.append("pre_idea_evidence_gate_lint failed without structured missing output")
        items = pre_idea_gate_lint.get("warnings") if isinstance(pre_idea_gate_lint.get("warnings"), list) else []
        warnings.extend(f"pre_idea_evidence_gate_lint: {item}" for item in items)
        if not scorecard_lint.get("complete"):
            items = scorecard_lint.get("missing") if isinstance(scorecard_lint.get("missing"), list) else []
            missing.extend(f"idea_scorecard_lint: {item}" for item in items)
            if scorecard_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_scorecard_lint failed without structured missing output")
        items = scorecard_lint.get("warnings") if isinstance(scorecard_lint.get("warnings"), list) else []
        warnings.extend(f"idea_scorecard_lint: {item}" for item in items)
        if not track_seed_lint.get("complete"):
            items = track_seed_lint.get("missing") if isinstance(track_seed_lint.get("missing"), list) else []
            missing.extend(f"idea_track_seeds: {item}" for item in items)
            if track_seed_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_track_seeds failed without structured missing output")
        items = track_seed_lint.get("warnings") if isinstance(track_seed_lint.get("warnings"), list) else []
        warnings.extend(f"idea_track_seeds: {item}" for item in items)
        missing.extend(f"idea_decision_ledger: {item}" for item in idea_decision_missing)
        warnings.extend(f"idea_decision_ledger: {item}" for item in idea_decision_warnings)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        return result(
            stage,
            not missing,
            missing,
            "idea_gate_contract",
            warnings,
            {
                "pre_idea_evidence_gate_lint": pre_idea_gate_lint,
                "idea_pool_lint": pool_lint,
                "idea_scorecard_lint": scorecard_lint,
                "idea_track_seeds": track_seed_lint,
                "idea_decision_ledger": idea_decision_details,
                "innovation_story_lint": innovation_story_lint,
            },
        )

    if stage == "experiment_plan":
        skill_root = Path(__file__).resolve().parents[2]
        scripts = {
            "track_plan_matrix": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/track_plan_matrix.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--check",
            ],
            "prelaunch_lint": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/prelaunch_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ],
            "innovation_lint": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/innovation_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ],
            "innovation_story_lint": [
                sys.executable,
                str(skill_root / "autoreskill-workflow/scripts/innovation_story_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--stage",
                stage,
            ],
        }
        details = {name: run_json(cmd) for name, cmd in scripts.items()}
        missing: list[str] = []
        warnings: list[str] = []
        complete = True
        for name, out in details.items():
            if not out.get("complete"):
                complete = False
                items = out.get("missing") if isinstance(out.get("missing"), list) else []
                missing.extend(f"{name}: {item}" for item in items)
                if out.get("returncode", 1) != 0 and not items:
                    missing.append(f"{name} failed without structured missing output")
            items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
            warnings.extend(f"{name}: {item}" for item in items)
        track_lifecycle_missing, track_lifecycle_warnings, track_lifecycle_details = validate_track_plan_lifecycle(base)
        if track_lifecycle_missing:
            complete = False
            missing.extend(f"track_plan_lifecycle: {item}" for item in track_lifecycle_missing)
        warnings.extend(f"track_plan_lifecycle: {item}" for item in track_lifecycle_warnings)
        details["track_plan_lifecycle"] = track_lifecycle_details
        return result(stage, complete, missing, "experiment_plan_contract", warnings, details)

    if stage == "code":
        skill_root = Path(__file__).resolve().parents[2]
        missing = []
        if not nonempty(base / "coder/EXPERIMENT_INDEX.md"):
            missing.append("coder/EXPERIMENT_INDEX.md")
        if not has_glob(base, "coder/experiments/**/EXPERIMENT_MANIFEST.json"):
            missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
        if not (has_glob(base, "coder/experiments/**/logs/dry_run*") or has_glob(base, "coder/experiments/**/logs/real_*")):
            missing.append("coder/experiments/**/logs/dry_run* or coder/experiments/**/logs/real_*")
        details: dict[str, Any] = {}
        warnings: list[str] = []
        if has_glob(base, "coder/experiments/**/EXPERIMENT_MANIFEST.json"):
            scripts = {
                "baseline_clone_lint": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/baseline_clone_lint.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                ],
                "experiment_drift_lint": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/experiment_drift_lint.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                ],
                "track_implementation_index": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/track_implementation_index.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                    "--check",
                ],
                "experiment_real_readiness_lint": [
                    sys.executable,
                    str(skill_root / "autoreskill-implement-experiment/scripts/experiment_real_readiness_lint.py"),
                    "--project",
                    str(Path(project).expanduser().resolve()),
                ],
            }
            details = {name: run_json(cmd) for name, cmd in scripts.items()}
            for name, out in details.items():
                if not out.get("complete"):
                    items = out.get("missing") if isinstance(out.get("missing"), list) else []
                    missing.extend(f"{name}: {item}" for item in items)
                    if out.get("returncode", 1) != 0 and not items:
                        missing.append(f"{name} failed without structured missing output")
                items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
                warnings.extend(f"{name}: {item}" for item in items)
        return result(stage, not missing, missing, "code_contract", warnings, details)

    if stage == "experiment":
        missing = []
        warnings = []
        details: dict[str, Any] = {}
        ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json")
        if not nonempty(base / "coder/EXPERIMENT_LEDGER.json"):
            missing.append("coder/EXPERIMENT_LEDGER.json")
        if not (has_glob(base, "coder/experiments/**/REMOTE_RUN.json") or has_glob(base, "coder/experiments/**/results/*")):
            missing.append("REMOTE_RUN.json or experiment results")
        skill_root = Path(__file__).resolve().parents[2]
        protocol_out = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-run-experiment/scripts/baseline_protocol_launch_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        details["baseline_protocol_launch_lint"] = protocol_out
        clone_out = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-implement-experiment/scripts/baseline_clone_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        details["baseline_clone_lint"] = clone_out
        if not clone_out.get("complete"):
            items = clone_out.get("missing") if isinstance(clone_out.get("missing"), list) else []
            missing.extend(f"baseline_clone_lint: {item}" for item in items)
            if clone_out.get("returncode", 1) != 0 and not items:
                missing.append("baseline_clone_lint failed without structured missing output")
        items = clone_out.get("warnings") if isinstance(clone_out.get("warnings"), list) else []
        warnings.extend(f"baseline_clone_lint: {item}" for item in items)
        if not protocol_out.get("complete"):
            items = protocol_out.get("missing") if isinstance(protocol_out.get("missing"), list) else []
            missing.extend(f"baseline_protocol_launch_lint: {item}" for item in items)
            if protocol_out.get("returncode", 1) != 0 and not items:
                missing.append("baseline_protocol_launch_lint failed without structured missing output")
        items = protocol_out.get("warnings") if isinstance(protocol_out.get("warnings"), list) else []
        warnings.extend(f"baseline_protocol_launch_lint: {item}" for item in items)
        if ledger:
            if ledger.get("ready_for_analysis") is not True:
                missing.append("coder/EXPERIMENT_LEDGER.json ready_for_analysis=true from promoted evidence")
            if not ledger.get("best_run") and not ledger.get("track_best_runs"):
                missing.append("promoted best_run or track_best_runs")
            if ledger.get("candidate_runs"):
                warnings.append("candidate_supported runs are pilot evidence; run linked ablation/confirmation before analysis")
            failure_missing, failure_warnings, failure_details = validate_experiment_failure_lineage(base, ledger)
            missing.extend(f"experiment_failure_lineage: {item}" for item in failure_missing)
            warnings.extend(f"experiment_failure_lineage: {item}" for item in failure_warnings)
            details["experiment_failure_lineage"] = failure_details
        return result(stage, not missing, missing, "experiment_contract", warnings, details)

    if stage == "analysis":
        skill_root = Path(__file__).resolve().parents[2]
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        analysis_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-analyze-results/scripts/analysis_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        missing = []
        warnings = []
        if not analysis_lint.get("complete"):
            items = analysis_lint.get("missing") if isinstance(analysis_lint.get("missing"), list) else []
            missing.extend(f"analysis_lint: {item}" for item in items)
            if analysis_lint.get("returncode", 1) != 0 and not items:
                missing.append("analysis_lint failed without structured missing output")
        items = analysis_lint.get("warnings") if isinstance(analysis_lint.get("warnings"), list) else []
        warnings.extend(f"analysis_lint: {item}" for item in items)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        outcome_missing, outcome_warnings, outcome_details = validate_idea_outcome_summary(base)
        missing.extend(f"idea_outcome_summary: {item}" for item in outcome_missing)
        warnings.extend(f"idea_outcome_summary: {item}" for item in outcome_warnings)
        return result(stage, not missing, missing, "analysis_contract", warnings, {"innovation_story_lint": innovation_story_lint, "analysis_lint": analysis_lint, "idea_outcome_summary": outcome_details})

    if stage == "review_pressure":
        skill_root = Path(__file__).resolve().parents[2]
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        findings = read_json(base / "reviewer/REVIEW_FINDINGS.json")
        status = str((findings or {}).get("status", "")).lower()
        issues = []
        if isinstance(findings, dict):
            for key in ["issues", "findings", "review_findings", "items"]:
                if isinstance(findings.get(key), list):
                    issues = findings[key]
                    break
        blocking = [
            issue
            for issue in issues
            if isinstance(issue, dict)
            and str(issue.get("severity") or issue.get("priority") or "").lower() in {"critical", "high"}
            and str(issue.get("status") or issue.get("state") or "open").lower() not in {"closed", "resolved", "waived", "accepted_risk", "fixed"}
        ]
        ok = bool(findings and status in READY and not blocking)
        missing = []
        if not findings:
            missing.append("reviewer/REVIEW_FINDINGS.json")
        if findings and status not in READY:
            missing.append("reviewer/REVIEW_FINDINGS.json status ready")
        if blocking:
            missing.append("open high/critical review findings")
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        warnings = []
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        return result(stage, ok and not missing, missing, "review_pressure_contract", warnings, {"innovation_story_lint": innovation_story_lint})

    if stage == "writing":
        skill_root = Path(__file__).resolve().parents[2]
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        write_package_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-paper-write/scripts/write_package_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        missing = []
        warnings = []
        if not write_package_lint.get("complete"):
            items = write_package_lint.get("missing") if isinstance(write_package_lint.get("missing"), list) else []
            missing.extend(f"write_package_lint: {item}" for item in items)
            if write_package_lint.get("returncode", 1) != 0 and not items:
                missing.append("write_package_lint failed without structured missing output")
        items = write_package_lint.get("warnings") if isinstance(write_package_lint.get("warnings"), list) else []
        warnings.extend(f"write_package_lint: {item}" for item in items)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        return result(stage, not missing, missing, "writing_contract", warnings, {"innovation_story_lint": innovation_story_lint, "write_package_lint": write_package_lint})

    if stage == "submission_ready":
        skill_root = Path(__file__).resolve().parents[2]
        package = read_json(base / "submission_ready.json")
        status = str((package or {}).get("status", "")).lower()
        citation_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-review-gate/scripts/citation_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        write_package_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-paper-write/scripts/write_package_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ]
        )
        ok = nonempty(base / "paper/main.tex") and (base / "paper/main.pdf").exists() and status in READY and citation_lint.get("complete") is True
        missing = []
        if not nonempty(base / "paper/main.tex"):
            missing.append("paper/main.tex")
        if not (base / "paper/main.pdf").exists():
            missing.append("paper/main.pdf")
        if status not in READY:
            missing.append("submission_ready.json status ready")
        if not citation_lint.get("complete"):
            items = citation_lint.get("missing") if isinstance(citation_lint.get("missing"), list) else []
            missing.extend(f"citation_lint: {item}" for item in items)
            if citation_lint.get("returncode", 1) != 0 and not items:
                missing.append("citation_lint failed without structured missing output")
        if not write_package_lint.get("complete"):
            items = write_package_lint.get("missing") if isinstance(write_package_lint.get("missing"), list) else []
            missing.extend(f"write_package_lint: {item}" for item in items)
            if write_package_lint.get("returncode", 1) != 0 and not items:
                missing.append("write_package_lint failed without structured missing output")
        innovation_story_lint = run_innovation_story_lint(skill_root, project, stage)
        if not innovation_story_lint.get("complete"):
            items = innovation_story_lint.get("missing") if isinstance(innovation_story_lint.get("missing"), list) else []
            missing.extend(f"innovation_story_lint: {item}" for item in items)
            if innovation_story_lint.get("returncode", 1) != 0 and not items:
                missing.append("innovation_story_lint failed without structured missing output")
        warnings = []
        items = innovation_story_lint.get("warnings") if isinstance(innovation_story_lint.get("warnings"), list) else []
        warnings.extend(f"innovation_story_lint: {item}" for item in items)
        return result(stage, ok and not missing, missing, "submission_ready_contract", warnings, {"citation_lint": citation_lint, "innovation_story_lint": innovation_story_lint, "write_package_lint": write_package_lint})

    return result(stage, False, [f"unknown stage {stage}"], "unknown_contract")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.stage)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
