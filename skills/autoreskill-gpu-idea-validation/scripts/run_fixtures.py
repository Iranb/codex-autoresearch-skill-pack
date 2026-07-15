#!/usr/bin/env python3
"""Offline deterministic fixtures for the GPU idea-validation skill."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = SCRIPT_DIR.parents[1]
IDEA_GRAPH_PROJECTION = SKILLS_ROOT / "autoreskill-ideation-panel/scripts/idea_graph_projection.py"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import external_alignment_lint as alignment  # noqa: E402
import idea_campaign as campaign_tool  # noqa: E402


CAMPAIGN_REL = Path(".autoreskill") / campaign_tool.CAMPAIGN_REL


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def base_evidence() -> List[Dict[str, Any]]:
    rows = [
        ("ev-target-1", "target_domain", "Target method A changes the representation but retains a shared fixed gate.", ["bottleneck_support", "closest_anchor", "baseline_protocol"]),
        ("ev-target-2", "target_domain", "Target method B also retains the same fixed gate under the matched protocol.", ["bottleneck_support", "negative_evidence"]),
        ("ev-near-1", "near_neighbor", "A neighboring field reframes fixed gates as measurable optimization objects.", ["mechanism", "transfer_bridge"]),
        ("ev-far-1", "far_neighbor", "A distant field audits shared assumptions with controlled counterfactuals.", ["mechanism", "transfer_bridge"]),
    ]
    return [
        {
            "id": evidence_id,
            "lane": lane,
            "source_type": "paper",
            "provider": "arXiv",
            "source_ref": f"https://arxiv.org/abs/fixture-{index}",
            "title": f"Fixture paper {index}",
            "locator": "Methods, paragraph 2",
            "excerpt": excerpt,
            "excerpt_sha256": digest(excerpt),
            "evidence_level": "method_section",
            "full_text_status": "method_section_acquired",
            "source_verification_status": "verified_against_source",
            "source_verification_limit": "Fixture verifies the captured method span only, not the paper's broader claims.",
            "citable": True,
            "roles": roles,
        }
        for index, (evidence_id, lane, excerpt, roles) in enumerate(rows, 1)
    ]


def quality_gauntlet() -> Dict[str, Any]:
    checks = {
        name: {"verdict": "pass", "rationale": f"fixture {name} passed", "hard_floor_triggered": False}
        for name in campaign_tool.CHECK_NAMES
    }
    return {
        "checks": checks,
        "verdict": "advance",
        "verdict_layer": "soft_judgment",
        "revision_targets": [],
        "repair": {"count": 0},
    }


def one_candidate(index: int, status: str) -> Dict[str, Any]:
    candidate_id = f"ext-cand-{index:02d}"
    candidate: Dict[str, Any] = {
        "id": candidate_id,
        "status": status,
        "title": f"Controlled gate intervention {index}",
        "research_question": "Does making the fixed gate adaptive remove the matched bottleneck?",
        "contribution_type": "ALGO",
        "gap_closures": [
            {
                "gap_ref": "gap-additive",
                "role": "primary",
                "main_pattern": "reframe_as_solvable_object",
                "subpattern": "C00",
                "structural_fit": "The missing leaf is recast as a measurable constrained object.",
                "recipe_application": "Define the gate statistic, optimize it, and test fidelity.",
                "expected_artifact": "adaptive gate module",
            },
            {
                "gap_ref": "gap-subtractive",
                "role": "secondary",
                "main_pattern": "assumption_audit_and_pivot",
                "subpattern": "C01",
                "structural_fit": "The shared fixed-gate assumption is explicitly relaxed.",
                "recipe_application": "Name, relax, and isolate the fixed-gate assumption.",
                "expected_artifact": "assumption-isolating ablation",
            },
        ],
        "mechanism": {
            "intervention": "Replace the fixed gate with one input-conditioned scalar while keeping all other operations frozen.",
            "one_variable_change": "fixed gate -> input-conditioned scalar gate",
            "load_bearing_variable": "conditioned gate value",
            "predicted_observation": "Matched primary metric improves only when the gate follows the target statistic.",
            "falsifier": "No matched gain, or a shuffled gate matches the proposed gate.",
            "alternative_explanation": "The change only adds regularization or parameter count.",
            "method_steps": [
                {"id": "step-1", "action": "Compute one input statistic from frozen features."},
                {"id": "step-2", "action": "Map that statistic to the existing gate location."},
            ],
        },
        "negative_control": {
            "intervention": "Shuffle the conditioned gate across examples while preserving its marginal distribution.",
            "expected_if_mechanism_true": "The shuffled gate loses the downstream gain.",
            "downstream_metric": "matched_primary_metric",
            "non_tautology_rationale": "The control changes the proposed causal alignment while preserving capacity and marginals.",
        },
        "collision_audit": {
            "signature_terms": ["input-conditioned scalar gate", "matched gate intervention"],
            "signature_window_months": 10,
            "alias_terms": ["adaptive modulation", "conditional control coefficient"],
            "alias_window_months": 48,
            "query_trace": [
                {"channel": "signature", "query": "input-conditioned scalar gate", "searched_at": "2026-07-10T00:00:00Z", "provider": "arXiv", "result_refs": ["ev-target-1"]},
                {"channel": "alias", "query": "adaptive modulation conditional control", "searched_at": "2026-07-10T00:01:00Z", "provider": "Semantic Scholar", "result_refs": ["ev-near-1", "ev-far-1"]},
            ],
            "status": "no_threat_found",
            "search_limitations": "Fixture corpus is intentionally bounded and cannot certify novelty.",
            "claim_limit": "No novelty certificate; repeat live targeted retrieval before paper claims.",
            "scoop_axes": {
                "problem_framing": "matched bottleneck",
                "core_mechanism": "conditioned gate",
                "key_insight": "remove a shared fixed assumption",
                "application_domain": "fixture task",
            },
        },
        "quality_gauntlet": quality_gauntlet(),
        "implementability_audit": {
            "generation_context_id": f"gen-{index}",
            "reviewer_context_id": f"review-{index}",
            "reviewer_role": "skeptical_engineer",
            "status": "passed",
            "enriched_steps": [
                {"id": "step-1", "what_changes": "one statistic", "build_procedure": "reuse frozen feature output", "inputs": ["features"], "outputs": ["statistic"]},
                {"id": "step-2", "what_changes": "one gate value", "build_procedure": "bounded scalar mapping", "inputs": ["statistic"], "outputs": ["gate"]},
            ],
            "underspecified_points": [
                {"step_id": "step-2", "hole": "mapping range", "fill": "clip to baseline gate range", "severity": "filled", "load_bearing": True}
            ],
            "protected_commitments_present": False,
        },
        "rapid_validation": {
            "evidence_tier": "pilot_only",
            "claim_intent": "candidate_screening",
            "baseline_code": {
                "source_ref": "https://github.com/example/baseline",
                "revision": "0123456789abcdef",
                "resolved_path": "/tmp/fixture-baseline",
                "train_entrypoint": "train.py",
                "eval_entrypoint": "evaluate.py",
                "comparison_label": "paper-report comparison not established",
                "locked": True,
            },
            "dataset": {"name": "fixture-proxy", "proxy_rationale": "smallest baseline-supported split", "split": "official-validation"},
            "metric_policy": {"primary_metric": "matched_primary_metric", "direction": "higher", "locked": True},
            "evaluation_command": "python evaluate.py --split official-validation",
            "decision_class": "falsify_core_mechanism",
            "expected_decision_change": "Retire if shuffled and proposed gates are indistinguishable.",
            "resource_request": {
                "compute_backend": "local_gpu",
                "execution_route": ["local", "ssh", "bjtu_hpc"][index % 3],
                "gpu_count": 1,
                "estimated_gpu_hours": 0.5,
                "walltime_minutes": 30,
                "smoke_minutes": 5,
            },
            "seed_policy": {"planned_seed_count": 1, "max_random_seeds": 3, "seed": 1000 + index, "retry_reuses_seed": True},
            "outcome_routes": {
                "valid_positive_candidate": "survivor only; matched confirmation and ablation required",
                "valid_negative": "lower belief or retire",
                "valid_inconclusive": "allow at most one decision-changing discriminator",
                "infrastructure_failure": "no hypothesis belief change",
                "implementation_failure": "no hypothesis belief change",
                "protocol_invalid": "no hypothesis belief change",
            },
        },
    }
    payload = campaign_tool.protected_payload(candidate)
    candidate["protected_commitments"] = {"payload": payload, "sha256": campaign_tool.protected_digest(candidate)}
    return candidate


def valid_campaign() -> Dict[str, Any]:
    candidates = []
    for index in range(8):
        status = "admitted" if index < 2 else "shortlisted" if index == 2 else "candidate"
        candidates.append(one_candidate(index, status))
    return {
        "schema_version": 1,
        "campaign_id": "fixture-campaign-001",
        "campaign_revision": 1,
        "parent_campaign_sha256": None,
        "direction": "fixture external idea validation",
        "status": "ready",
        "source_mode": "external_material",
        "papernexus_used": False,
        "method_reference": {
            "paper": "arXiv:2607.04439",
            "paper_version": "v1",
            "official_repo": "https://github.com/microsoft/ResearchStudio",
            "repo_commit": "868f0e9c30685b72ebd475f0dada1492a1982168",
            "workflow": "ResearchStudio-Idea Phase 0-4 plus local bounded GPU handoff",
        },
        "deck_aggregate_sha256": campaign_tool.PINNED_DECK_AGGREGATE_SHA256,
        "constraints": {
            "candidate_count_min": 8,
            "candidate_count_max": 12,
            "shortlist_min": 3,
            "shortlist_max": 5,
            "max_admitted_tracks": 4,
            "quick_campaign_gpu_hours": 4,
            "max_candidate_gpu_hours": 1,
            "max_random_seeds": 3,
        },
        "claim_limits": ["All quick results remain pilot_only.", "paper-report comparison not established"],
        "evidence_readiness": "ready",
        "literature_search_trace": [
            {
                "query": "fixture fixed gate method lineage",
                "provider": "arXiv",
                "searched_at": "2026-07-10T00:00:00Z",
                "covered_time_range": "2022-01-01/2026-07-10",
                "result_refs": ["ev-target-1", "ev-target-2", "ev-near-1", "ev-far-1"],
                "full_text_status": "method_sections_cached",
                "source_verification_limit": "Fixture search trace covers only the captured method spans.",
            }
        ],
        "evidence_records": base_evidence(),
        "method_lineage": {
            "nodes": [
                {"id": "method-a", "label": "Target method A", "provenance": "external_citable", "citable": True, "evidence_refs": ["ev-target-1"]},
                {"id": "method-b", "label": "Target method B", "provenance": "external_citable", "citable": True, "evidence_refs": ["ev-target-2"]},
                {"id": "old-warning", "label": "Older awareness ancestor", "provenance": "parametric_awareness_only", "citable": False, "evidence_refs": []},
            ],
            "edges": [
                {"source": "old-warning", "target": "method-a", "relation": "regression_warning", "evidence_refs": []},
                {"source": "method-a", "target": "method-b", "relation": "extends", "evidence_refs": ["ev-target-1", "ev-target-2"]},
            ],
        },
        "anchor_gap_id": "gap-additive",
        "structural_gaps": [
            {
                "id": "gap-additive",
                "type": "additive_leaf",
                "description": "No citable frontier leaf conditions the fixed gate on the target statistic.",
                "lineage_node_refs": ["method-b"],
                "evidence_refs": ["ev-target-1", "ev-target-2"],
                "missing_leaf": "input-conditioned gate under the matched protocol",
            },
            {
                "id": "gap-subtractive",
                "type": "subtractive_shared_assumption",
                "description": "Both frontier methods retain a fixed, input-independent gate.",
                "lineage_node_refs": ["method-a", "method-b"],
                "evidence_refs": ["ev-target-1", "ev-target-2"],
                "shared_assumption": "the gate should remain input independent",
            },
        ],
        "candidates": candidates,
        "shortlisted_candidate_ids": ["ext-cand-00", "ext-cand-01", "ext-cand-02"],
        "admitted_candidate_ids": ["ext-cand-00", "ext-cand-01"],
    }


def write_campaign(root: Path, payload: Dict[str, Any]) -> None:
    campaign_tool.atomic_write_json(root / CAMPAIGN_REL, payload)


def lint_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="gpu-idea-fixture-") as raw:
        root = Path(raw)
        write_campaign(root, payload)
        return campaign_tool.lint_campaign(str(root))


def expect_failure(name: str, mutate: Callable[[Dict[str, Any]], None], needle: str) -> None:
    payload = copy.deepcopy(valid_campaign())
    mutate(payload)
    result = lint_payload(payload)
    joined = "\n".join(result.get("missing", []))
    if result.get("complete") or needle not in joined:
        raise AssertionError(f"{name}: expected failure containing {needle!r}, got {json.dumps(result, ensure_ascii=False)}")


def external_ref(candidate_id: str, campaign_sha: str, **extra: Any) -> Dict[str, Any]:
    row = {
        "external_campaign_ref": str(campaign_tool.CAMPAIGN_REL),
        "external_campaign_sha256": campaign_sha,
        "external_candidate_id": candidate_id,
    }
    row.update(extra)
    return row


def write_alignment_artifacts(root: Path, payload: Dict[str, Any], campaign_sha: str) -> None:
    base = root / ".autoreskill"
    gate = campaign_tool.read_json(base / campaign_tool.GATE_REL) or {}
    candidate_ids = [row["id"] for row in payload["candidates"]]
    shortlist = payload["shortlisted_candidate_ids"]
    admitted = payload["admitted_candidate_ids"]
    campaign_tool.atomic_write_json(base / alignment.POOL_REL, {"ideas": [external_ref(cid, campaign_sha, id=f"pool-{cid}") for cid in candidate_ids]})
    campaign_tool.atomic_write_json(base / alignment.SCORECARD_REL, {"candidates": [external_ref(cid, campaign_sha, id=f"score-{cid}") for cid in shortlist]})
    campaign_tool.atomic_write_json(base / alignment.SEEDS_REL, {"tracks": [external_ref(cid, campaign_sha, track_id=f"track-{cid}") for cid in admitted]})
    campaign_tool.atomic_write_json(base / alignment.LEDGER_REL, {"decisions": [external_ref(cid, campaign_sha, decision="admit") for cid in admitted]})
    campaign_tool.atomic_write_json(base / alignment.MATRIX_REL, {"tracks": [external_ref(cid, campaign_sha, track_id=f"track-{cid}") for cid in admitted]})
    selected = admitted[0]
    selected_candidate = next(row for row in payload["candidates"] if row["id"] == selected)
    selected_commitment = selected_candidate["protected_commitments"]["sha256"]
    packet_chain = {
        "protected_commitment_sha256": selected_commitment,
        "pre_idea_evidence_gate_path": str(campaign_tool.GATE_REL),
        "innovation_slot_map_path": str(gate.get("innovation_slot_map_path") or ""),
        "evidence_import_gate": {
            "status": "not_required",
            "source_mode": "external_material",
            "material_refs": [str(campaign_tool.CAMPAIGN_REL)],
            "validation_ref": str(gate.get("lint_ref") or ""),
        },
        "external_evidence_norms": {
            "campaign_ref": str(campaign_tool.CAMPAIGN_REL),
            "campaign_sha256": campaign_sha,
            "source_integrity": {
                "lint_ref": str(gate.get("lint_ref") or ""),
                "lint_sha256": gate.get("lint_sha256"),
                "slot_map_ref": str(gate.get("innovation_slot_map_path") or ""),
                "slot_map_sha256": gate.get("slot_map_sha256"),
            },
        },
    }
    campaign_tool.atomic_write_json(
        base / alignment.INNOVATION_REL,
        external_ref(
            selected,
            campaign_sha,
            track_id=f"track-{selected}",
            selected_idea_fragment_id=f"fragment-{selected}",
            **copy.deepcopy(packet_chain),
        ),
    )
    campaign_tool.atomic_write_json(
        base / alignment.REVIEW_REL,
        external_ref(
            selected,
            campaign_sha,
            track_id=f"track-{selected}",
            selected_idea_fragment_id=f"fragment-{selected}",
            **copy.deepcopy(packet_chain),
        ),
    )
    campaign_tool.atomic_write_json(
        base / alignment.PANEL_REL,
        {
            "status": "passed",
            "verdict": "advance",
            "generation_context_id": "generation-context",
            "reviewer_context_id": "independent-panel-context",
            "reviewer_role": "independent_panel",
            "external_campaign_ref": str(campaign_tool.CAMPAIGN_REL),
            "external_campaign_sha256": campaign_sha,
            "reviewed_candidate_ids": [selected],
        },
    )


def test_valid_and_fail_closed() -> None:
    campaign_template = campaign_tool.read_json(
        campaign_tool.SKILL_ROOT / "references/NON_PAPERNEXUS_IDEA_CAMPAIGN.template.json"
    )
    expected_template = campaign_tool.campaign_authoring_template("replace-with-research-direction")
    if campaign_template != expected_template or len((campaign_template or {}).get("candidates", [])) != 8:
        raise AssertionError("static campaign authoring template drifted from the eight-row CLI template")
    template_result = lint_payload(campaign_template or {})
    if template_result.get("complete") or "synthetic authoring-only template" not in "\n".join(template_result.get("missing", [])):
        raise AssertionError("synthetic authoring template became materializable")

    valid = lint_payload(valid_campaign())
    if not valid.get("complete"):
        raise AssertionError(f"valid campaign failed: {json.dumps(valid, ensure_ascii=False)}")

    single_gap = valid_campaign()
    single_gap["candidates"][7]["gap_closures"] = single_gap["candidates"][7]["gap_closures"][:1]
    single_gap["candidates"][7]["single_gap_fast_diagnostic"] = True
    single_gap_result = lint_payload(single_gap)
    if not single_gap_result.get("complete"):
        raise AssertionError(f"labeled single-gap diagnostic failed: {json.dumps(single_gap_result, ensure_ascii=False)}")

    expect_failure("papernexus declaration", lambda p: p.__setitem__("papernexus_used", True), "papernexus_used")
    expect_failure("papernexus provider", lambda p: p["evidence_records"][0].__setitem__("provider", "PaperNexus"), "provider must be explicit and non-PaperNexus")
    expect_failure("deck drift", lambda p: p.__setitem__("deck_aggregate_sha256", "0" * 64), "deck_aggregate_sha256")
    expect_failure("excerpt drift", lambda p: p["evidence_records"][0].__setitem__("excerpt", "tampered"), "excerpt_sha256 mismatch")
    expect_failure("abstract-only load-bearing evidence", lambda p: p["evidence_records"][0].__setitem__("full_text_status", "abstract_only"), "requires acquired full text")
    expect_failure("unverified load-bearing evidence", lambda p: p["evidence_records"][0].__setitem__("source_verification_status", "unverified"), "checked source verification")
    expect_failure("not ready", lambda p: p.__setitem__("evidence_readiness", "not_ready"), "evidence_readiness must be ready")
    expect_failure("awareness gap support", lambda p: p["structural_gaps"][0].__setitem__("lineage_node_refs", ["old-warning"]), "may not use awareness-only")
    expect_failure("subtractive support", lambda p: p["structural_gaps"][1].__setitem__("lineage_node_refs", ["method-b"]), "requires at least two")
    expect_failure("closure overflow", lambda p: p["candidates"][0].__setitem__("gap_closures", p["candidates"][0]["gap_closures"] * 2), "1..3 counted entries")
    expect_failure("unlabeled single closure", lambda p: p["candidates"][7].__setitem__("gap_closures", p["candidates"][7]["gap_closures"][:1]), "single_gap_fast_diagnostic")
    expect_failure("wrong subparent", lambda p: p["candidates"][0]["gap_closures"][0].__setitem__("subpattern", "C01"), "subpattern parent")
    expect_failure("missing variable", lambda p: p["candidates"][0]["mechanism"].__setitem__("load_bearing_variable", ""), "load_bearing_variable")
    expect_failure("missing control", lambda p: p["candidates"][0]["negative_control"].__setitem__("non_tautology_rationale", ""), "non_tautology_rationale")
    expect_failure("review context", lambda p: p["candidates"][0]["implementability_audit"].__setitem__("reviewer_context_id", "gen-0"), "reviewer context must be separate")
    expect_failure("recipe revise ignored", lambda p: p["candidates"][0]["quality_gauntlet"]["checks"]["recipe_application_check"].__setitem__("verdict", "revise"), "verdict must be revise")
    expect_failure("anti-pattern abandon ignored", lambda p: p["candidates"][0]["quality_gauntlet"]["checks"]["anti_pattern_check"].__setitem__("verdict", "abandon"), "verdict must be abandon")
    expect_failure("non-pilot", lambda p: p["candidates"][0]["rapid_validation"].__setitem__("evidence_tier", "claim_support"), "evidence_tier must be pilot_only")
    expect_failure("bad route", lambda p: p["candidates"][0]["rapid_validation"]["resource_request"].__setitem__("execution_route", "autodl"), "execution_route must be")
    expect_failure("bad baseline label", lambda p: p["candidates"][0]["rapid_validation"]["baseline_code"].__setitem__("comparison_label", "baseline"), "exact baseline-comparison label")
    expect_failure("seed overflow", lambda p: p["candidates"][0]["rapid_validation"]["seed_policy"].__setitem__("max_random_seeds", 4), "max_random_seeds must be 1..3")
    expect_failure("commitment drift", lambda p: p["candidates"][0]["protected_commitments"].__setitem__("sha256", "0" * 64), "protected_commitments.sha256 mismatch")

    def five_admitted(payload: Dict[str, Any]) -> None:
        payload["shortlisted_candidate_ids"] = [f"ext-cand-{i:02d}" for i in range(5)]
        payload["admitted_candidate_ids"] = list(payload["shortlisted_candidate_ids"])
        for index in range(5):
            payload["candidates"][index]["status"] = "admitted"

    expect_failure("admitted overflow", five_admitted, "1..4 unique ids")

    def hard_collision(payload: Dict[str, Any]) -> None:
        candidate = payload["candidates"][0]
        candidate["collision_audit"].update(
            {
                "status": "threat_found",
                "worst_case_prior": {
                    "evidence_ref": "ev-target-1",
                    "exact_result": "The prior already implements the same conditioned gate.",
                    "subsumption_argument": "The candidate mechanism and intervention are fully subsumed.",
                    "overlap": "exact_mechanism",
                    "collision_channel": "alias",
                },
            }
        )

    expect_failure("hard collision", hard_collision, "exact-mechanism collision cannot be")


def test_materialization_and_alignment() -> None:
    payload = valid_campaign()
    with tempfile.TemporaryDirectory(prefix="gpu-idea-materialize-") as raw:
        root = Path(raw)
        write_campaign(root, payload)
        first = campaign_tool.materialize(str(root), "absent")
        if not first.get("complete") or first.get("idempotent"):
            raise AssertionError(f"first materialization failed: {first}")
        gate_path = root / ".autoreskill" / campaign_tool.GATE_REL
        second = campaign_tool.materialize(str(root), campaign_tool.sha256_file(gate_path))
        if not second.get("complete") or not second.get("idempotent"):
            raise AssertionError(f"idempotent materialization failed: {second}")
        mismatch = campaign_tool.materialize(str(root), "0" * 64)
        if mismatch.get("complete") or "CAS mismatch" not in mismatch.get("error", ""):
            raise AssertionError(f"materialization CAS did not fail: {mismatch}")

        campaign_sha = campaign_tool.sha256_file(root / CAMPAIGN_REL)
        gate = campaign_tool.read_json(root / ".autoreskill" / campaign_tool.GATE_REL) or {}
        projection_proc = subprocess.run(
            [sys.executable, str(IDEA_GRAPH_PROJECTION), "--project", str(root)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if projection_proc.returncode != 0:
            raise AssertionError(f"external graph projection failed: {projection_proc.stderr}")
        projection = campaign_tool.read_json(root / ".autoreskill/ideation/EVIDENCE_GRAPH_PROJECTION.json") or {}
        committed_refs = {str(gate.get("lint_ref") or ""), str(gate.get("innovation_slot_map_path") or "")}
        if not committed_refs <= set(projection.get("source_paths") or []):
            raise AssertionError(f"projection did not consume committed lint/slot refs: {projection.get('source_paths')}")
        if not any(
            str(gate.get("innovation_slot_map_path") or "") in set(node.get("source_paths") or [])
            for node in projection.get("nodes") or []
            if isinstance(node, dict)
        ):
            raise AssertionError("external slot nodes retained a fixed canonical source path")
        projection_path = root / ".autoreskill/ideation/EVIDENCE_GRAPH_PROJECTION.json"
        projection_before = projection_path.read_bytes()
        unsafe_gate = copy.deepcopy(gate)
        unsafe_gate["innovation_slot_map_path"] = "../outside-slot.json"
        unsafe_gate["slot_map_ref"] = "../outside-slot.json"
        campaign_tool.atomic_write_json(root / ".autoreskill" / campaign_tool.GATE_REL, unsafe_gate)
        unsafe_proc = subprocess.run(
            [sys.executable, str(IDEA_GRAPH_PROJECTION), "--project", str(root)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if unsafe_proc.returncode == 0 or projection_path.read_bytes() != projection_before:
            raise AssertionError("external graph projection did not fail closed on an escaping gate ref")
        campaign_tool.atomic_write_json(root / ".autoreskill" / campaign_tool.GATE_REL, gate)
        write_alignment_artifacts(root, payload, campaign_sha)
        for stage in ("ideation", "idea_gate", "experiment_plan"):
            result = alignment.lint(str(root), stage)
            if not result.get("complete"):
                raise AssertionError(f"alignment {stage} failed: {json.dumps(result, ensure_ascii=False)}")

        packet_path = root / ".autoreskill" / alignment.INNOVATION_REL
        packet = campaign_tool.read_json(packet_path) or {}
        original_packet = copy.deepcopy(packet)
        packet.pop("external_evidence_norms", None)
        campaign_tool.atomic_write_json(packet_path, packet)
        broken_chain = alignment.lint(str(root), "experiment_plan")
        if broken_chain.get("complete") or "external_evidence_norms" not in "\n".join(broken_chain.get("missing", [])):
            raise AssertionError("alignment accepted a packet without committed lint/slot integrity refs")

        campaign_tool.atomic_write_json(packet_path, original_packet)
        review_path = root / ".autoreskill" / alignment.REVIEW_REL
        review_packet = campaign_tool.read_json(review_path) or {}
        review_packet["external_candidate_id"] = payload["admitted_candidate_ids"][1]
        campaign_tool.atomic_write_json(review_path, review_packet)
        selection_drift = alignment.lint(str(root), "experiment_plan")
        if selection_drift.get("complete") or "must select the same external candidate" not in "\n".join(selection_drift.get("missing", [])):
            raise AssertionError("alignment accepted different selected candidates in the innovation and review packets")
        write_alignment_artifacts(root, payload, campaign_sha)

        packet = campaign_tool.read_json(packet_path) or {}
        packet["track_id"] = packet["external_candidate_id"]
        campaign_tool.atomic_write_json(packet_path, packet)
        stale = alignment.lint(str(root), "experiment_plan")
        if stale.get("complete") or "may not impersonate" not in "\n".join(stale.get("missing", [])):
            raise AssertionError("alignment accepted track-id/candidate-id impersonation")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-pn-gate-") as raw:
        root = Path(raw)
        write_campaign(root, payload)
        gate = root / ".autoreskill" / campaign_tool.GATE_REL
        campaign_tool.atomic_write_json(gate, {"schema_version": 1, "status": "passed", "evidence_source_mode": "papernexus"})
        result = campaign_tool.materialize(str(root), campaign_tool.sha256_file(gate))
        if result.get("complete") or "refusing to overwrite" not in result.get("error", ""):
            raise AssertionError(f"materializer overwrote PaperNexus gate: {result}")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-invalid-gate-") as raw:
        root = Path(raw)
        write_campaign(root, payload)
        gate = root / ".autoreskill" / campaign_tool.GATE_REL
        gate.parent.mkdir(parents=True, exist_ok=True)
        gate.write_text("{invalid-json\n", encoding="utf-8")
        result = campaign_tool.materialize(str(root), campaign_tool.sha256_file(gate))
        if result.get("complete") or "invalid or unknown" not in result.get("error", ""):
            raise AssertionError(f"materializer overwrote invalid/unknown gate: {result}")


def test_crash_recovery_and_concurrency() -> None:
    payload = valid_campaign()
    with tempfile.TemporaryDirectory(prefix="gpu-idea-crash-") as raw:
        root = Path(raw)
        write_campaign(root, payload)
        original = campaign_tool.atomic_write_json
        calls = {"count": 0}

        def flaky(path: Path, value: Any) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("injected crash before lint/gate commit")
            original(path, value)

        campaign_tool.atomic_write_json = flaky
        try:
            try:
                campaign_tool.materialize(str(root), "absent")
            except RuntimeError:
                pass
        finally:
            campaign_tool.atomic_write_json = original
        gate = root / ".autoreskill" / campaign_tool.GATE_REL
        if gate.exists():
            raise AssertionError("gate commit marker exists after injected pre-commit crash")
        recovered = campaign_tool.materialize(str(root), "absent")
        if not recovered.get("complete"):
            raise AssertionError(f"crash recovery failed: {recovered}")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-concurrent-") as raw:
        root = Path(raw)
        write_campaign(root, payload)
        script = SCRIPT_DIR / "idea_campaign.py"

        def launch() -> Tuple[int, Dict[str, Any]]:
            proc = subprocess.run(
                [sys.executable, str(script), "materialize", "--project", str(root), "--expected-current-gate-sha256", "absent"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            return proc.returncode, json.loads(proc.stdout)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: launch(), range(2)))
        successes = [result for code, result in results if code == 0 and result.get("complete")]
        failures = [result for code, result in results if code != 0 and not result.get("complete")]
        if len(successes) != 1 or len(failures) != 1:
            raise AssertionError(f"concurrent materialization was not single-winner: {results}")


def test_adversarial_commit_and_identity_invariants() -> None:
    expect_failure(
        "papernexus source ref",
        lambda p: p["evidence_records"][0].__setitem__("source_ref", "papernexus://paper/fixture"),
        "may not reference PaperNexus",
    )
    expect_failure(
        "fabricated mcp provenance",
        lambda p: p.__setitem__("mcp_attempted", False),
        "forbidden PaperNexus/session provenance",
    )
    expect_failure(
        "non-citable lineage support",
        lambda p: p["evidence_records"][0].__setitem__("citable", False),
        "citable verified method evidence",
    )

    with tempfile.TemporaryDirectory(prefix="gpu-idea-nonfinite-") as raw:
        root = Path(raw)
        path = root / CAMPAIGN_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = valid_campaign()
        payload["candidates"][0]["rapid_validation"]["resource_request"]["estimated_gpu_hours"] = float("nan")
        path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
        result = campaign_tool.lint_campaign(str(root))
        if result.get("complete") or "strict finite JSON" not in "\n".join(result.get("missing", [])):
            raise AssertionError(f"campaign validator accepted NaN: {result}")
        try:
            campaign_tool.atomic_write_json(path, payload)
        except ValueError:
            pass
        else:
            raise AssertionError("atomic JSON writer emitted a non-finite JSON number")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-blocked-gate-") as raw:
        root = Path(raw)
        payload = valid_campaign()
        write_campaign(root, payload)
        first = campaign_tool.materialize(str(root), "absent")
        if not first.get("complete"):
            raise AssertionError(first)
        base = root / ".autoreskill"
        gate_path = base / campaign_tool.GATE_REL
        gate = campaign_tool.read_json(gate_path) or {}
        gate["status"] = "blocked"
        campaign_tool.atomic_write_json(gate_path, gate)
        repaired = campaign_tool.materialize(str(root), campaign_tool.sha256_file(gate_path))
        repaired_gate = campaign_tool.read_json(gate_path) or {}
        if not repaired.get("complete") or repaired.get("idempotent") or repaired_gate.get("status") != "passed":
            raise AssertionError(f"blocked gate was trusted or not repaired: {repaired}")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-immutable-id-") as raw:
        root = Path(raw)
        payload = valid_campaign()
        write_campaign(root, payload)
        first = campaign_tool.materialize(str(root), "absent")
        gate_path = root / ".autoreskill" / campaign_tool.GATE_REL
        old_campaign_sha = str(first.get("campaign_sha256"))
        revised = copy.deepcopy(payload)
        revised["campaign_id"] = "different-campaign-id"
        revised["campaign_revision"] = 2
        revised["parent_campaign_sha256"] = old_campaign_sha
        revised["direction"] = "changed direction"
        write_campaign(root, revised)
        result = campaign_tool.materialize(str(root), campaign_tool.sha256_file(gate_path))
        if result.get("complete") or "campaign_id is immutable" not in result.get("error", ""):
            raise AssertionError(f"materializer accepted campaign_id mutation: {result}")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-reread-race-") as raw:
        root = Path(raw)
        payload = valid_campaign()
        write_campaign(root, payload)
        original = campaign_tool.write_content_addressed
        injected = {"done": False}

        def mutate_before_commit(base: Path, stem: str, value: Dict[str, Any]) -> Tuple[str, str]:
            if not injected["done"]:
                injected["done"] = True
                changed = copy.deepcopy(payload)
                changed["direction"] = "concurrent mutation after validation"
                write_campaign(root, changed)
            return original(base, stem, value)

        campaign_tool.write_content_addressed = mutate_before_commit
        try:
            result = campaign_tool.materialize(str(root), "absent")
        finally:
            campaign_tool.write_content_addressed = original
        if result.get("complete") or "campaign changed during locked materialization" not in result.get("error", ""):
            raise AssertionError(f"materializer committed across a campaign reread race: {result}")
        if (root / ".autoreskill" / campaign_tool.GATE_REL).exists():
            raise AssertionError("gate was written after a concurrent campaign mutation")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-decoy-row-") as raw:
        root = Path(raw)
        payload = valid_campaign()
        write_campaign(root, payload)
        first = campaign_tool.materialize(str(root), "absent")
        campaign_sha = str(first.get("campaign_sha256"))
        write_alignment_artifacts(root, payload, campaign_sha)
        pool_path = root / ".autoreskill" / alignment.POOL_REL
        pool = campaign_tool.read_json(pool_path) or {}
        for row in pool.get("ideas", []):
            row.pop("external_campaign_ref", None)
            row.pop("external_campaign_sha256", None)
            row.pop("external_candidate_id", None)
        pool["decoy_metadata"] = external_ref(payload["candidates"][0]["id"], campaign_sha)
        campaign_tool.atomic_write_json(pool_path, pool)
        result = alignment.lint(str(root), "ideation")
        if result.get("complete") or "canonical_row" not in "\n".join(result.get("missing", [])):
            raise AssertionError("alignment accepted identities from a nested decoy instead of canonical rows")

        write_alignment_artifacts(root, payload, campaign_sha)
        panel_path = root / ".autoreskill" / alignment.PANEL_REL
        panel = campaign_tool.read_json(panel_path) or {}
        panel.pop("generation_context_id", None)
        campaign_tool.atomic_write_json(panel_path, panel)
        result = alignment.lint(str(root), "experiment_plan")
        if result.get("complete") or "non-empty and separate" not in "\n".join(result.get("missing", [])):
            raise AssertionError("alignment accepted a panel without a generation context")


def test_revision_crash_safety_and_writers() -> None:
    with tempfile.TemporaryDirectory(prefix="gpu-idea-revision-crash-") as raw:
        root = Path(raw)
        payload = valid_campaign()
        write_campaign(root, payload)
        first = campaign_tool.materialize(str(root), "absent")
        base = root / ".autoreskill"
        gate_path = base / campaign_tool.GATE_REL
        old_gate_sha = campaign_tool.sha256_file(gate_path)
        old_gate = campaign_tool.read_json(gate_path) or {}
        old_lint = base / str(old_gate.get("lint_ref"))
        old_slot = base / str(old_gate.get("innovation_slot_map_path"))
        old_lint_sha = campaign_tool.sha256_file(old_lint)
        old_slot_sha = campaign_tool.sha256_file(old_slot)

        revised = copy.deepcopy(payload)
        revised["campaign_revision"] = 2
        revised["parent_campaign_sha256"] = first.get("campaign_sha256")
        revised["direction"] = "fixture revision after committed gate"
        write_campaign(root, revised)
        original = campaign_tool.atomic_write_json
        calls = {"count": 0}

        def flaky(path: Path, value: Any) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("injected crash between immutable artifacts and gate")
            original(path, value)

        campaign_tool.atomic_write_json = flaky
        try:
            try:
                campaign_tool.materialize(str(root), old_gate_sha)
            except RuntimeError:
                pass
        finally:
            campaign_tool.atomic_write_json = original
        if campaign_tool.sha256_file(gate_path) != old_gate_sha:
            raise AssertionError("gate changed before the final commit write")
        if campaign_tool.sha256_file(old_lint) != old_lint_sha or campaign_tool.sha256_file(old_slot) != old_slot_sha:
            raise AssertionError("a failed revision damaged artifacts referenced by the previous gate")
        recovered = campaign_tool.materialize(str(root), old_gate_sha)
        if not recovered.get("complete") or recovered.get("idempotent"):
            raise AssertionError(f"revision recovery failed: {recovered}")

    with tempfile.TemporaryDirectory(prefix="gpu-idea-writers-") as raw:
        root = Path(raw)
        campaign_input = root / "campaign-input.json"
        campaign_tool.atomic_write_json(campaign_input, valid_campaign())
        seeded = campaign_tool.seed_campaign(str(root), str(campaign_input), "absent")
        if not seeded.get("complete"):
            raise AssertionError(f"campaign seed writer failed: {seeded}")
        committed = campaign_tool.materialize(str(root), "absent")
        if not committed.get("complete"):
            raise AssertionError(f"seeded campaign did not materialize: {committed}")
        panel_input = root / "panel-input.json"
        panel = {
            "schema_version": 1,
            "status": "passed",
            "verdict": "advance",
            "generation_context_id": "writer-generation",
            "reviewer_context_id": "writer-independent-review",
            "reviewer_role": "independent_panel",
            "external_campaign_ref": str(campaign_tool.CAMPAIGN_REL),
            "external_campaign_sha256": committed.get("campaign_sha256"),
            "reviewed_candidate_ids": ["ext-cand-00"],
            "rationale": "Independent fixture panel advances one admitted candidate.",
            "created_at": "2026-07-10T00:00:00Z",
        }
        campaign_tool.atomic_write_json(panel_input, panel)
        written = campaign_tool.write_panel_design_review(str(root), str(panel_input), "absent")
        if not written.get("complete"):
            raise AssertionError(f"panel writer failed: {written}")


def test_evidence_authority_migration_recovery() -> None:
    script = SCRIPT_DIR / "idea_campaign.py"
    for fail_after, expected_state in [
        ("archive_copied", "RETRY_COMMITTED"),
        ("archive_verified", "ROLLED_BACK"),
        ("gate_replaced", "COMMITTED"),
    ]:
        with tempfile.TemporaryDirectory(prefix=f"gpu-idea-migrate-{fail_after}-") as raw:
            root = Path(raw)
            payload = valid_campaign()
            write_campaign(root, payload)
            base = root / ".autoreskill"
            gate_path = base / campaign_tool.GATE_REL
            campaign_tool.atomic_write_json(
                gate_path,
                {
                    "schema_version": 1,
                    "status": "passed",
                    "evidence_source_mode": "papernexus",
                    "source_ref": "ideation/legacy-source.json",
                },
            )
            campaign_tool.atomic_write_json(base / "ideation/legacy-source.json", {"legacy": True})
            selection = f"selection-{fail_after}"
            campaign_tool.atomic_write_json(
                base / "ideation/IDEA_DECISION_LEDGER.json",
                {"schema_version": 2, "selection_fingerprint": selection, "decisions": []},
            )
            gate_sha = campaign_tool.sha256_file(gate_path)
            campaign_sha = campaign_tool.sha256_file(root / CAMPAIGN_REL)
            campaign_tool.atomic_write_json(
                base / campaign_tool.PANEL_REL,
                {
                    "schema_version": 1,
                    "status": "passed",
                    "verdict": "advance",
                    "generation_context_id": "migration-generation",
                    "reviewer_context_id": "migration-independent-review",
                    "reviewer_role": "independent_panel",
                    "external_campaign_ref": str(campaign_tool.CAMPAIGN_REL),
                    "external_campaign_sha256": campaign_sha,
                    "reviewed_candidate_ids": [payload["admitted_candidate_ids"][0]],
                    "rationale": "Independent migration fixture review advances one admitted candidate.",
                    "created_at": "2026-07-13T00:00:00Z",
                },
            )
            preview = campaign_tool.migrate_evidence_authority(
                str(root), gate_sha, selection, campaign_sha, apply=False
            )
            if not preview.get("complete") or not preview.get("dry_run"):
                raise AssertionError(f"migration dry-run failed: {preview}")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "migrate-evidence-authority",
                    "--project",
                    str(root),
                    "--expected-current-gate-sha256",
                    gate_sha,
                    "--expected-selection-fingerprint",
                    selection,
                    "--input-campaign-sha256",
                    campaign_sha,
                    "--apply",
                    "--fail-after",
                    fail_after,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if proc.returncode != 86:
                raise AssertionError(f"migration failpoint did not terminate at {fail_after}: {proc.returncode}")
            if expected_state == "RETRY_COMMITTED":
                if campaign_tool.sha256_file(gate_path) != gate_sha:
                    raise AssertionError("pre-verification migration crash changed the live gate")
                retried = campaign_tool.migrate_evidence_authority(
                    str(root), gate_sha, selection, campaign_sha, apply=True
                )
                if not retried.get("complete"):
                    raise AssertionError(f"pre-verification migration retry failed: {retried}")
                continue
            recovered = campaign_tool.recover_authority_migration(str(root), str(preview["operation_id"]))
            if not recovered.get("complete") or recovered.get("state") != expected_state:
                raise AssertionError(f"migration recovery chose the wrong boundary: {recovered}")
            journal = campaign_tool.read_json(Path(str(preview["journal"]))) or {}
            archive = Path(str(journal.get("old_gate_archive_path") or ""))
            if not archive.is_file() or campaign_tool.sha256_file(archive) != gate_sha:
                raise AssertionError("migration did not preserve the exact old live gate")
            if expected_state == "COMMITTED":
                live_gate = campaign_tool.read_json(gate_path) or {}
                if live_gate.get("evidence_source_mode") != "external_material":
                    raise AssertionError("post-replacement recovery did not retain the new live authority")
                rolled_back = campaign_tool.rollback_authority_migration(str(root), str(preview["operation_id"]))
                if not rolled_back.get("complete") or campaign_tool.sha256_file(gate_path) != gate_sha:
                    raise AssertionError(f"migration rollback failed: {rolled_back}")


def test_cli_has_no_external_side_effects() -> None:
    with tempfile.TemporaryDirectory(prefix="gpu-idea-offline-") as raw:
        root = Path(raw)
        write_campaign(root, valid_campaign())
        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        audit = root / "command-audit.txt"
        for name in ["ssh", "scp", "rsync", "sbatch", "scontrol", "curl", "wget"]:
            shim = fake_bin / name
            shim.write_text(f"#!/bin/sh\necho {name} >> '{audit}'\nexit 97\n", encoding="utf-8")
            shim.chmod(0o755)
        guard = root / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(
            "import socket\n"
            "class ForbiddenSocket:\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        raise RuntimeError('network disabled by fixture')\n"
            "socket.socket = ForbiddenSocket\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["PYTHONPATH"] = f"{guard}:{env.get('PYTHONPATH', '')}"
        for command in [
            [sys.executable, str(SCRIPT_DIR / "idea_campaign.py"), "verify-deck"],
            [sys.executable, str(SCRIPT_DIR / "idea_campaign.py"), "check", "--project", str(root)],
        ]:
            proc = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if proc.returncode != 0:
                raise AssertionError(f"offline CLI failed: {command}\n{proc.stdout}\n{proc.stderr}")
        if audit.exists() and audit.read_text(encoding="utf-8").strip():
            raise AssertionError(f"offline CLI invoked external commands: {audit.read_text(encoding='utf-8')}")


def test_gpu_resource_and_atomic_queue_suites() -> None:
    suites = [
        SCRIPT_DIR / "run_external_consumer_gate_fixtures.py",
        SKILLS_ROOT / "autoreskill-ideation-panel/scripts/pre_idea_fixture_smoke.py",
        SKILLS_ROOT / "autoreskill-experiment-plan/scripts/external_identity_fixture_smoke.py",
        SKILLS_ROOT / "autoreskill-workflow/tests/run_gpu_resource_adapter_fixtures.py",
        SKILLS_ROOT / "autoreskill-workflow/tests/run_experiment_next_actions_fixtures.py",
        SKILLS_ROOT / "autoreskill-workflow/tests/run_external_material_routing_fixtures.py",
        SKILLS_ROOT / "autoreskill-run-experiment/scripts/run_reconcile_external_intent_fixture.py",
    ]
    for suite in suites:
        proc = subprocess.run(
            [sys.executable, str(suite)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(f"focused suite failed: {suite}\n{proc.stdout}\n{proc.stderr}")


def main() -> int:
    tests = [
        ("valid_and_fail_closed", test_valid_and_fail_closed),
        ("materialization_and_alignment", test_materialization_and_alignment),
        ("crash_recovery_and_concurrency", test_crash_recovery_and_concurrency),
        ("adversarial_commit_and_identity_invariants", test_adversarial_commit_and_identity_invariants),
        ("revision_crash_safety_and_writers", test_revision_crash_safety_and_writers),
        ("evidence_authority_migration_recovery", test_evidence_authority_migration_recovery),
        ("cli_has_no_external_side_effects", test_cli_has_no_external_side_effects),
        ("gpu_resource_and_atomic_queue_suites", test_gpu_resource_and_atomic_queue_suites),
    ]
    results = []
    for name, test in tests:
        test()
        results.append({"name": name, "status": "passed"})
    print(json.dumps({"complete": True, "tests": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
