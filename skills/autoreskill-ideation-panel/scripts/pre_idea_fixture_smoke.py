#!/usr/bin/env python3
"""Run offline fixture smoke tests for the pre-idea evidence gate."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PAPER_SCRIPTS = ROOT / "autoreskill-papernexus-innovation/scripts"
IDEATION_SCRIPTS = ROOT / "autoreskill-ideation-panel/scripts"
EXPERIMENT_SCRIPTS = ROOT / "autoreskill-experiment-plan/scripts"


def run(cmd: list[str], *, expect: int = 0) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    parsed: dict[str, Any]
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"stdout": proc.stdout}
    parsed["returncode"] = proc.returncode
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    if proc.returncode != expect:
        raise AssertionError(f"{cmd} returned {proc.returncode}, expected {expect}: {parsed}")
    return parsed


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def base_project() -> Path:
    root = Path(tempfile.mkdtemp(prefix="autoreskill-pre-idea-"))
    (root / ".autoreskill/literature").mkdir(parents=True)
    (root / ".autoreskill/papernexus").mkdir(parents=True)
    (root / ".autoreskill/ideation").mkdir(parents=True)
    run(
        [
            sys.executable,
            str(PAPER_SCRIPTS / "pre_idea_discovery_plan.py"),
            "--project",
            str(root),
            "--topic",
            "generalized category discovery under domain shift",
            "--target-domain",
            "computer vision",
        ]
    )
    return root


def add_lane_packets(root: Path, rows: list[dict[str, Any]]) -> None:
    base = root / ".autoreskill"
    names = {
        "target_domain": "TARGET_DOMAIN_DISCOVERY_PACKET.json",
        "near_neighbor": "NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
        "far_neighbor": "FAR_NEIGHBOR_DISCOVERY_PACKET.json",
    }
    for lane, name in names.items():
        lane_rows = [row for row in rows if row["lane"] == lane]
        write(
            base / "literature" / name,
            {
                "lane": lane,
                "attempts": [{"attempt_id": f"{lane}-1", "query": lane, "raw_results": lane_rows}],
                "candidates": lane_rows,
            },
        )
    write(base / "literature/LITERATURE_DISCOVERY_PACKET.json", {"candidates": rows})


def add_split_pack_and_slots(root: Path) -> None:
    base = root / ".autoreskill"
    write(
        base / "papernexus/SPLIT_READING_EVIDENCE_PACK.json",
        {
            "packet_id": "pack1",
            "source": "papernexus-remote",
            "paper_material_views": [
                {
                    "paper_id": "p1",
                    "roles": [
                        "closest_prior",
                        "baseline_protocol",
                        "dataset_metric",
                        "mechanism",
                        "limitation_future",
                        "negative_evidence",
                        "transfer_bridge",
                    ],
                }
            ],
            "source_spans": ["span1"],
            "provenance_refs": ["mcp1"],
            "evidence_boundaries": {"source_backed": ["span1"]},
            "closest_prior_anchors": [{}],
            "baseline_protocol_anchors": [{}],
            "dataset_metric_anchors": [{}],
            "mechanism_layers": [{}],
            "limitation_layers": [{}],
            "negative_evidence_layers": [{}],
            "transfer_takeaways": [{}],
        },
    )
    write(
        base / "ideation/INNOVATION_SLOT_MAP.json",
        {
            "challenge_clusters": [{"slot_id": "c1"}],
            "insight_clusters": [{"slot_id": "i1"}],
            "transfer_bridges": [{"slot_id": "t1"}],
            "anchor_nodes": [{"slot_id": "a1"}],
            "relation_patterns": [{"slot_id": "r1"}],
            "evidence_boundary": {"source_backed": ["span1"]},
        },
    )


def add_abstract_screening_audit(root: Path) -> None:
    scorecard = json.loads(
        (root / ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json").read_text(encoding="utf-8")
    )
    discovery = json.loads(
        (root / ".autoreskill/literature/LITERATURE_DISCOVERY_PACKET.json").read_text(encoding="utf-8")
    )
    abstracts_by_title = {
        str(row.get("title") or ""): str(row.get("abstract") or "")
        for row in discovery.get("candidates", [])
        if isinstance(row, dict)
    }
    rows = []
    for index, candidate in enumerate(scorecard.get("candidates", [])):
        identifiers = candidate.get("identifiers") if isinstance(candidate.get("identifiers"), dict) else {}
        identifier = next((str(value) for value in identifiers.values() if value), f"fixture-{index}")
        rows.append(
            {
                "candidate_id": identifier,
                "lane": candidate.get("lane"),
                "title": candidate.get("title"),
                "abstract": abstracts_by_title.get(str(candidate.get("title") or "")),
                "abstract_read": True,
                "decision": candidate.get("decision"),
                "reason": "; ".join(candidate.get("score_reasons") or ["fixture screening decision"]),
                "source": "offline_fixture",
            }
        )
    write(
        root / ".autoreskill/papernexus/ABSTRACT_SCREENING_AUDIT.json",
        {
            "screening_completed": True,
            "screening_basis": "abstract_or_metadata_when_abstract_missing",
            "expected_candidate_count": len(rows),
            "rows": rows,
        },
    )


def high_signal_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(10):
        rows.append(
            {
                "lane": "target_domain",
                "title": f"Target GCD closest prior {index + 1}",
                "abstract": "SimGCD baseline protocol dataset metric prototype limitation negative evidence source resolvable mechanism",
                "identifiers": {"doi": f"10.0000/target{index + 1}"},
            }
        )
    for index in range(12):
        rows.append(
            {
                "lane": "near_neighbor",
                "title": f"Near-neighbor transfer mechanism {index + 1}",
                "abstract": "related task different mechanism prototype alignment failure case dataset metric source resolvable",
                "identifiers": {"doi": f"10.0000/near{index + 1}"},
            }
        )
    for index in range(12):
        rows.append(
            {
                "lane": "far_neighbor",
                "title": f"Far-neighbor adaptive control bridge {index + 1}",
                "abstract": "representation learning external domain control feedback adaptation mechanism transfer analogy challenge limitation negative evidence source resolvable",
                "identifiers": {"doi": f"10.0000/far{index + 1}"},
            }
        )
    return rows


def sparse_rows() -> list[dict[str, Any]]:
    return [
        {"lane": "target_domain", "title": "SimGCD: A Simple Baseline for Generalized Category Discovery", "abstract": "prototype mechanism baseline dataset metric limitation future work", "identifiers": {"arxiv": "2201.001"}},
        {"lane": "near_neighbor", "title": "Open-set domain adaptation with prototype alignment", "abstract": "related task different mechanism objective failure case", "identifiers": {"doi": "10.0000/a"}},
        {"lane": "far_neighbor", "title": "Cognitive control and adaptive feedback for goal switching", "abstract": "psychology control feedback adaptation mechanism transfer analogy", "identifiers": {"doi": "10.0000/b"}},
    ]


def case_pass() -> dict[str, Any]:
    root = base_project()
    try:
        add_lane_packets(root, high_signal_rows())
        run(
            [
                sys.executable,
                str(PAPER_SCRIPTS / "discovery_metadata_triage.py"),
                "--project",
                str(root),
                "--input",
                "literature/LITERATURE_DISCOVERY_PACKET.json",
                "--stage",
                "pre_idea",
            ]
        )
        scorecard_path = root / ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json"
        scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
        write(scorecard_path, scorecard)
        add_abstract_screening_audit(root)
        add_split_pack_and_slots(root)
        gate = run([sys.executable, str(IDEATION_SCRIPTS / "pre_idea_evidence_gate_lint.py"), "--project", str(root), "--write-gate"])
        run([sys.executable, str(IDEATION_SCRIPTS / "pre_idea_evidence_gate_lint.py"), "--project", str(root)])
        return {"case": "pass", "root": str(root), "scorecard_ratio": scorecard.get("eligible_graph_or_material_ratio"), "gate_status": gate.get("status")}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_ratio_fails() -> dict[str, Any]:
    root = base_project()
    try:
        add_lane_packets(root, sparse_rows())
        run([sys.executable, str(PAPER_SCRIPTS / "discovery_metadata_triage.py"), "--project", str(root), "--input", "literature/LITERATURE_DISCOVERY_PACKET.json", "--stage", "pre_idea"])
        lint = run([sys.executable, str(PAPER_SCRIPTS / "paper_selection_scorecard_lint.py"), "--project", str(root)], expect=1)
        return {"case": "ratio_fails", "missing": lint.get("missing", [])}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_expansion_and_noise_filtering() -> dict[str, Any]:
    root = base_project()
    try:
        rows = [
            {
                "lane": "target_domain",
                "title": "SimGCD Prototype Baseline for Generalized Category Discovery",
                "abstract": "baseline dataset metric protocol prototype limitation negative evidence",
                "identifiers": {"arxiv": "2201.001"},
            },
            {
                "lane": "target_domain",
                "title": "A Survey of Generalized Category Discovery",
                "abstract": "survey overview taxonomy",
                "identifiers": {"doi": "10.0000/survey"},
            },
            {
                "lane": "near_neighbor",
                "title": "Open-set domain adaptation prototype mechanism",
                "abstract": "related task different mechanism prototype failure case",
                "identifiers": {},
            },
            {
                "lane": "far_neighbor",
                "title": "Benchmarking suite for domain agnostic challenge datasets",
                "abstract": "benchmark suite leaderboard dataset benchmark",
                "identifiers": {"doi": "10.0000/bench"},
            },
        ]
        add_lane_packets(root, rows)
        run(
            [
                sys.executable,
                str(PAPER_SCRIPTS / "discovery_metadata_triage.py"),
                "--project",
                str(root),
                "--input",
                "literature/LITERATURE_DISCOVERY_PACKET.json",
                "--stage",
                "pre_idea",
            ]
        )
        scorecard = json.loads((root / ".autoreskill/papernexus/PAPER_SELECTION_SCORECARD.json").read_text(encoding="utf-8"))
        lint = run([sys.executable, str(PAPER_SCRIPTS / "paper_selection_scorecard_lint.py"), "--project", str(root)], expect=1)
        return {
            "case": "expansion_and_noise_filtering",
            "search_expansion_recommended": scorecard.get("search_expansion_recommended"),
            "decision_counts": scorecard.get("decision_counts"),
            "missing": lint.get("missing", [])[:4],
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_legacy_reconcile() -> dict[str, Any]:
    root = base_project()
    try:
        write(root / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json", {"ideas": [{"id": "legacy"}]})
        result = run([sys.executable, str(IDEATION_SCRIPTS / "legacy_pre_idea_reconcile.py"), "--project", str(root), "--write-blocked-gate"], expect=1)
        gate = json.loads((root / ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json").read_text(encoding="utf-8"))
        return {"case": "legacy_reconcile", "status": result.get("status"), "gate_status": gate.get("status")}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_legacy_dry_run_no_write() -> dict[str, Any]:
    root = base_project()
    try:
        write(root / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json", {"ideas": [{"id": "legacy"}]})
        result = run([sys.executable, str(IDEATION_SCRIPTS / "legacy_pre_idea_reconcile.py"), "--project", str(root), "--dry-run", "--write-blocked-gate"], expect=1)
        report_path = root / ".autoreskill/ideation/LEGACY_PRE_IDEA_RECONCILIATION.json"
        gate_path = root / ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json"
        return {
            "case": "legacy_dry_run_no_write",
            "status": result.get("status"),
            "report_written": report_path.exists(),
            "gate_written": gate_path.exists(),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_misplaced_gate_dry_run() -> dict[str, Any]:
    root = base_project()
    try:
        write(root / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json", {"ideas": [{"id": "legacy"}]})
        write(root / ".autoreskill/orchestrator/PRE_IDEA_EVIDENCE_GATE.json", {"schema_version": 1, "status": "passed"})
        result = run([sys.executable, str(IDEATION_SCRIPTS / "legacy_pre_idea_reconcile.py"), "--project", str(root), "--dry-run"], expect=1)
        return {
            "case": "misplaced_gate_dry_run",
            "status": result.get("status"),
            "found_gate_paths": result.get("report", {}).get("found_gate_paths", []),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def degraded_idea(index: int) -> dict[str, Any]:
    idea_type = "ALGO" if index < 6 else "CODE"
    idea_id = f"DEGRADED-{index + 1:03d}"
    deep = index < 3
    payload = {
        "id": idea_id,
        "type": idea_type,
        "priority": "HIGH" if index == 0 else "MEDIUM",
        "risk": "MEDIUM",
        "source": "degraded_pre_idea",
        "source_paper_or_technique": "",
        "paperNexus_evidence_ids": [],
        "description": f"Approved degraded fixture idea {index + 1}.",
        "hypothesis": "Degraded fixture hypothesis with claim limits.",
        "research_question": f"Does degraded intervention {index + 1} restore the target signal?",
        "core_scientific_contribution": f"A bounded causal test of degraded mechanism {index + 1}.",
        "target_domain_anchor": "approved degraded target-domain anchor pending closure",
        "closest_prior_delta": f"Speculative mechanism delta {index + 1} pending evidence closure.",
        "intervention": f"degraded intervention {index + 1}",
        "mechanism": f"restore degraded latent signal {index + 1}",
        "predicted_pattern": f"metric component {index + 1} changes only under the intervention",
        "falsifier": f"matched ablation shows no component-{index + 1} change",
        "alternative_explanation": "capacity or optimization rather than the proposed mechanism",
        "cheapest_discriminating_experiment": "one-seed matched pilot under the locked evaluator",
        "causal_signature": f"degraded-{index + 1}|signal-{index + 1}|pattern-{index + 1}",
        "one_variable_change": f"degraded fixture one-variable change {index + 1}",
        "expected_metric_impact": "speculative improvement pending evidence closure",
        "implementation_scope": "fixture implementation scope",
        "evidence_maturity": "promising",
        "primary_method_source_role": "near_neighbor",
        "innovation_slot_refs": ["approved-degraded-slot"],
        "missing_materials": ["pre-idea evidence was user-approved degraded"],
        "followup_evidence_plan": ["close PaperNexus evidence before experiment launch"],
        "red_line_audit": {
            "metric_drift": False,
            "eval_drift": False,
            "dataset_drift": False,
            "data_leakage": False,
            "prediction_cheating": False,
            "training_budget_drift": False,
        },
        "paper_contribution": {
            "paper_thesis": f"Degraded fixture thesis for {idea_id}.",
            "contribution_type": "method" if idea_type == "ALGO" else "engineering_method",
            "target_venue_fit": "fixture venue only after evidence closure",
            "novelty_claim": "Speculative until selected evidence closure.",
            "baseline_pressure": "Must compare against locked baseline later.",
            "minimum_experiment_table": ["baseline", "proposed", "ablation"],
            "ablation_plan": ["remove degraded fixture mechanism"],
            "falsifier": "no improvement under locked protocol",
            "performance_claim": "speculative performance claim pending closure" if idea_type == "CODE" else "",
            "standalone_engineering": False,
        },
        "paper_potential": {
            "target_claim": f"degraded mechanism claim {index + 1}",
            "minimum_experiment_table": "baseline, intervention, matched ablation",
            "reviewer_risk": "degraded source evidence",
        },
        "status": "SELECTED" if index == 0 else "SHORTLISTED" if deep else "PENDING",
    }
    if deep:
        payload.update(
            {
                "closest_prior_comparison": "Speculative until approved evidence closure.",
                "claim_boundary": "Pilot-only; no paper claim before evidence closure.",
                "outcome_routes": {
                    "positive": "ablation_or_confirmation",
                    "negative": "weaken_or_retire",
                    "inconclusive": "one_disambiguator",
                    "invalid": "repair_protocol",
                },
                "goe_path_refs": ["approved-degraded-gate"],
                "mechanism_source_path": "approved degraded near-neighbor hypothesis",
                "negative_evidence_refs": ["approved-degraded-gate"],
                "reviewer_attack_surface": ["missing source-backed novelty closure"],
                "falsifier_probe": "matched one-seed pilot",
                "track_seed_spec": {
                    "track_id": f"degraded-track-{index + 1}",
                    "one_variable_change": f"degraded fixture one-variable change {index + 1}",
                    "expected_metric_effect": "pilot-only positive delta",
                    "baseline_pressure": "locked baseline required",
                    "locked_or_missing_protocol_fields": ["source evidence"],
                    "minimum_pilot": ["baseline", "proposed", "ablation"],
                    "kill_condition": "no matched effect or evidence closure failure",
                },
            }
        )
    if index == 0:
        payload["paper_contribution"]["storyline"] = {
            "opening_tension": "The degraded gate leaves the mechanism uncertain.",
            "hidden_cause": "A latent signal may be suppressed.",
            "method_as_resolution": "Test one bounded restoration intervention.",
            "proof_ladder": ["pilot", "ablation", "evidence closure"],
            "reviewer_risk_and_defense": "Keep every claim speculative until closure.",
            "narrative_spine": ["problem", "cause", "method", "pilot", "closure"],
        }
    return payload


def degraded_score_row(idea: dict[str, Any], index: int) -> dict[str, Any]:
    row = {
        "id": idea["id"],
        "rank": index + 1,
        "scientistone_fast_rank": index + 1,
        "paper_potential_rank": index + 1,
        "graph_path_status": "degraded",
        "evidence_closure_level": "degraded",
        "recommended_track_action": "primary" if index == 0 else "park",
        "scores": {
            "significance": 3,
            "novelty_separation": 3,
            "experiment_defensibility": 2,
            "feasibility": 4,
            "evidence_maturity": 2,
            "risk_control": 3,
        },
        "weighted_total": 3,
        "causal_signature": idea["causal_signature"],
        "pairwise_comparison": {
            "closest_competing_idea_id": f"DEGRADED-{(index + 1) % 8 + 1:03d}",
            "mechanism_difference": "different degraded latent signal",
            "predicted_pattern_difference": "different metric component",
            "cheapest_discriminator": "matched one-seed pilot",
            "verdict": "distinct",
        },
        "paper_comparison": {
            "closest_prior_papers": ["degraded approval has no source-backed closest prior yet"],
            "innovation_comparison": "speculative comparison pending evidence closure",
            "overlap_risk": "unknown until PaperNexus repair",
            "differentiation_claim": "not claimable before evidence closure",
        },
        "closest_prior_pressure": "unresolved under approved degraded gate",
        "novelty_separation_needed": "must be closed before experiment launch",
        "near_neighbor_pressure": "unresolved under approved degraded gate",
        "far_neighbor_transfer_rationale": "unresolved under approved degraded gate",
        "primary_method_source_role": "near_neighbor",
        "target_domain_anchor": "approved degraded target-domain anchor pending closure",
        "neighbor_transfer_mechanism": "approved degraded transfer mechanism pending closure",
        "target_domain_method_overlap_risk": "unknown until PaperNexus repair",
        "reviewer_attack_surface": ["degraded evidence boundary"],
        "top_tier_support_judgment": "not supported until selected evidence closure",
        "venue_support_verdict": "degraded_hold",
        "evidence_debt": ["approved degraded pre-idea evidence"],
        "next_evidence_closure": "run pre-idea evidence expansion repair",
        "promotion_recommendation": "advance_with_constraints" if index == 0 else "park",
    }
    if index < 3:
        row["paper_story_assessment"] = {
            "core_contribution_verdict": "speculative_but_falsifiable",
            "storyline_readiness": "ready" if index == 0 else "defer until selected",
            "weakest_causal_link": "source evidence closure",
            "required_story_repair": "close PaperNexus evidence before launch",
        }
    return row


def case_degraded_approval() -> dict[str, Any]:
    root = base_project()
    try:
        write(
            root / ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
            {
                "schema_version": 1,
                "status": "degraded_requires_user_approval",
                "lane_attempts_satisfied": False,
                "screening_completed": False,
                "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
                "claim_limits": ["idea pool may be generated only as speculative; experiment_plan must close selected evidence"],
                "blocking_reasons": ["fixture missing PaperNexus split-reading evidence"],
                "allowed_next_action": "generate_experiment_idea_pool_degraded",
                "degraded_approval": {
                    "approved": True,
                    "approved_by": "fixture_user",
                    "approved_at": "2026-05-30T00:00:00+00:00",
                    "reason": "fixture explicitly approves degraded pre-idea ideation",
                },
            },
        )
        gate = run([sys.executable, str(IDEATION_SCRIPTS / "pre_idea_evidence_gate_lint.py"), "--project", str(root), "--allow-degraded"])
        ideas = [degraded_idea(index) for index in range(8)]
        write(
            root / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
            {
                "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
                "selected_idea_id": "DEGRADED-001",
                "shortlisted_idea_ids": ["DEGRADED-001", "DEGRADED-002", "DEGRADED-003"],
                "claim_limits": ["all ideas are speculative until selected evidence closure"],
                "evidence_boundary": {"speculative": ["approved degraded fixture"], "unsupported": ["paper claims"]},
                "ideas": ideas,
            },
        )
        write(
            root / ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            {
                "stage": "post_idea_generation_pre_idea_gate",
                "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
                "claim_limits": ["all ideas are speculative until selected evidence closure"],
                "evidence_boundary": {"speculative": ["approved degraded fixture"], "unsupported": ["paper claims"]},
                "scoring_rubric": "Fixture degraded scorecard rubric.",
                "weights": {"significance": 1, "novelty_separation": 1, "experiment_defensibility": 1, "feasibility": 1, "evidence_maturity": 1, "risk_control": 1},
                "top_recommendations": ["DEGRADED-001", "DEGRADED-002", "DEGRADED-003"],
                "top_track_recommendations": ["DEGRADED-001", "DEGRADED-002", "DEGRADED-003"],
                "shortlisted_idea_ids": ["DEGRADED-001", "DEGRADED-002", "DEGRADED-003"],
                "selected_primary_idea_id": "DEGRADED-001",
                "rows": [degraded_score_row(idea, index) for index, idea in enumerate(ideas)],
            },
        )
        write(
            root / ".autoreskill/ideation/CANDIDATE_POOL.json",
            {
                "candidates": [
                    {
                        "id": idea["id"],
                        "status": "advance_with_constraints" if index == 0 else "park",
                        "evidence_ids": ["approved_degraded_gate"],
                        "weakest_assumption": "PaperNexus evidence closure is still pending.",
                        "falsifier": "evidence closure fails or locked protocol shows no gain",
                    }
                    for index, idea in enumerate(ideas[:4])
                ]
            },
        )
        write(root / ".autoreskill/ideation/TOURNAMENT_SCOREBOARD.json", {"rows": [{"id": "DEGRADED-001", "rank": 1, "verdict": "advance_with_constraints"}]})
        pool = run(
            [
                sys.executable,
                str(ROOT / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
                "--project",
                str(root),
                "--pool",
                "ideation/EXPERIMENT_IDEA_POOL.json",
                "--require-selected",
            ]
        )
        ideation = run([sys.executable, str(IDEATION_SCRIPTS / "ideation_lint.py"), "--project", str(root), "--require-selected"])
        return {"case": "degraded_approval", "gate_status": gate.get("status"), "pool_status": pool.get("status"), "ideation_status": ideation.get("status")}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def case_degraded_missing_approval_fails() -> dict[str, Any]:
    root = base_project()
    try:
        write(
            root / ".autoreskill/ideation/PRE_IDEA_EVIDENCE_GATE.json",
            {
                "schema_version": 1,
                "status": "degraded_requires_user_approval",
                "lane_attempts_satisfied": False,
                "screening_completed": False,
                "allowed_next_action": "generate_experiment_idea_pool_degraded",
                "blocking_reasons": ["fixture missing approval"],
            },
        )
        lint = run([sys.executable, str(IDEATION_SCRIPTS / "pre_idea_evidence_gate_lint.py"), "--project", str(root), "--allow-degraded"], expect=1)
        return {"case": "degraded_missing_approval_fails", "missing": lint.get("missing", [])[:3]}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def goe_idea(index: int) -> dict[str, Any]:
    idea_type = "ALGO" if index < 9 else "CODE" if index < 12 else "PARAM"
    idea_id = f"GOE-{index + 1:03d}"
    return {
        "id": idea_id,
        "type": idea_type,
        "priority": "HIGH" if index < 4 else "MEDIUM",
        "risk": "MEDIUM",
        "source": "graph_of_evidence_fixture",
        "source_paper_or_technique": f"near/far transfer source {index + 1}",
        "paperNexus_evidence_ids": [f"ev-{index + 1}", "span1"],
        "description": f"Graph-backed fixture idea {index + 1}.",
        "hypothesis": "A transferred mechanism improves under the locked GCD protocol.",
        "research_question": f"Does transferred mechanism {index + 1} repair the target failure?",
        "core_scientific_contribution": f"Causal test of transferred mechanism {index + 1} under a locked protocol.",
        "intervention": f"activate transferred state update {index + 1}",
        "mechanism": f"restore category-state signal {index + 1}",
        "predicted_pattern": f"accuracy component {index + 1} rises and disappears under ablation",
        "falsifier": f"matched ablation preserves the gain for mechanism {index + 1}",
        "alternative_explanation": "capacity or optimization rather than category-state restoration",
        "cheapest_discriminating_experiment": "one-seed matched baseline/proposed/ablation pilot",
        "causal_signature": f"state-update-{index + 1}|category-signal-{index + 1}|ablation-pattern-{index + 1}",
        "outcome_routes": {
            "positive": "ablation_or_confirmation",
            "negative": "weaken_or_retire",
            "inconclusive": "one_disambiguator",
            "invalid": "repair_protocol",
        },
        "one_variable_change": f"replace confidence update with evidence-aware mechanism {index + 1}",
        "expected_metric_impact": "improve clustering accuracy under fixed split",
        "implementation_scope": "single module patch under fixed evaluator",
        "evidence_maturity": "evidence_backed",
        "closest_prior_comparison": "The closest prior lacks the transferred state-update mechanism.",
        "claim_boundary": "No generalization or SOTA claim before matched confirmation.",
        "paper_potential": {
            "target_claim": f"transferred mechanism claim {index + 1}",
            "minimum_experiment_table": "baseline, proposed, matched ablation",
            "reviewer_risk": "closest-prior overlap and causal isolation",
        },
        "primary_method_source_role": "near_neighbor" if index % 2 == 0 else "far_neighbor",
        "target_domain_anchor": "target-domain closest prior and baseline protocol",
        "neighbor_transfer_mechanism": "prototype/control feedback transfer mechanism",
        "target_domain_method_overlap_risk": "requires closest-prior delta table",
        "goe_path_refs": ["paper:target", "method:near", "negative:failure"],
        "closest_prior_delta": "adds certified category-state update absent from closest prior",
        "mechanism_source_path": "near_neighbor -> transfer_bridge -> target_domain_anchor",
        "negative_evidence_refs": ["negative:failure"],
        "reviewer_attack_surface": ["closest-prior overlap", "ablation isolation", "protocol drift"],
        "falsifier_probe": "No improvement after removing the transferred update under the locked evaluator.",
        "track_seed_spec": {
            "track_id": f"track-{index + 1:02d}",
            "one_variable_change": f"evidence-aware mechanism {index + 1}",
            "expected_metric_effect": "positive accuracy delta",
            "kill_condition": "no positive delta or failed ablation",
            "baseline_pressure": "SimGCD-style prior",
            "locked_or_missing_protocol_fields": ["metric", "split", "eval_command"],
            "minimum_pilot": ["baseline", "proposed", "ablation"],
        },
        "innovation_slot_refs": ["c1", "i1", "t1"],
        "missing_materials": ["closest-prior closure table"],
        "followup_evidence_plan": ["targeted PaperNexus import for closest prior"],
        "red_line_audit": {
            "metric_drift": False,
            "eval_drift": False,
            "dataset_drift": False,
            "data_leakage": False,
            "prediction_cheating": False,
            "training_budget_drift": False,
        },
        "paper_contribution": {
            "paper_thesis": f"GOE fixture thesis {index + 1}.",
            "contribution_type": "method" if idea_type == "ALGO" else "engineering_method",
            "target_venue_fit": "top-tier method paper after evidence closure",
            "novelty_claim": "Transferred mechanism separates from closest prior.",
            "baseline_pressure": "Must beat source-free GCD closest prior.",
            "minimum_experiment_table": ["baseline", "proposed", "ablation"],
            "ablation_plan": ["remove evidence-aware update"],
            "falsifier": "ablation removes the gain or protocol drift appears",
            "performance_claim": "performance-bearing method claim" if idea_type == "CODE" else "",
            "standalone_engineering": False,
            "storyline": {
                "opening_tension": "Current GCD methods do not explain category-state failure.",
                "hidden_cause": "The target category-state signal is suppressed.",
                "method_as_resolution": "Transfer one evidence-aware state update.",
                "proof_ladder": ["pilot", "ablation", "cross-dataset confirmation"],
                "reviewer_risk_and_defense": "Use locked protocol and closest-prior delta evidence.",
                "narrative_spine": ["problem", "cause", "transfer", "pilot", "confirmation"],
            },
        },
        "status": "SELECTED" if index == 0 else "PENDING",
    }


def goe_score_row(idea: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "id": idea["id"],
        "rank": index + 1,
        "scientistone_fast_rank": index + 1,
        "paper_potential_rank": index + 1,
        "graph_path_status": "closed",
        "evidence_closure_level": "source_backed",
        "recommended_track_action": "primary" if index == 0 else "alternate" if index < 4 else "park",
        "scores": {
            "significance": 4,
            "novelty_separation": 4,
            "experiment_defensibility": 4,
            "feasibility": 4,
            "evidence_maturity": 4,
            "risk_control": 4,
        },
        "weighted_total": 4,
        "paper_comparison": {
            "closest_prior_papers": ["Target GCD closest prior 1"],
            "innovation_comparison": "uses near/far transfer rather than target-only mechanism",
            "overlap_risk": "moderate; closure table required",
            "differentiation_claim": "certified state update and non-identifiable buffer differ from prior",
        },
        "closest_prior_pressure": "closest prior lacks transferred mechanism",
        "novelty_separation_needed": "delta table plus ablation",
        "near_neighbor_pressure": "near-neighbor mechanism supplies update logic",
        "far_neighbor_transfer_rationale": "far-neighbor feedback control supplies verifier story",
        "primary_method_source_role": idea["primary_method_source_role"],
        "target_domain_anchor": idea["target_domain_anchor"],
        "neighbor_transfer_mechanism": idea["neighbor_transfer_mechanism"],
        "target_domain_method_overlap_risk": idea["target_domain_method_overlap_risk"],
        "reviewer_attack_surface": idea["reviewer_attack_surface"],
        "top_tier_support_judgment": "promising after closest-prior closure",
        "venue_support_verdict": "advance_with_constraints",
        "evidence_debt": ["closest-prior closure table"],
        "next_evidence_closure": "import closest prior and run ablation plan",
        "promotion_recommendation": "advance_with_constraints" if index < 4 else "park",
        "innovation_slot_refs": ["c1", "i1", "t1"],
    }


def case_goe_package() -> dict[str, Any]:
    root = base_project()
    try:
        add_lane_packets(root, high_signal_rows())
        run([sys.executable, str(PAPER_SCRIPTS / "discovery_metadata_triage.py"), "--project", str(root), "--input", "literature/LITERATURE_DISCOVERY_PACKET.json", "--stage", "pre_idea"])
        add_abstract_screening_audit(root)
        add_split_pack_and_slots(root)
        gate = run([sys.executable, str(IDEATION_SCRIPTS / "pre_idea_evidence_gate_lint.py"), "--project", str(root), "--write-gate"])
        ideas = [goe_idea(index) for index in range(12)]
        write(
            root / ".autoreskill/ideation/EXPERIMENT_IDEA_POOL.json",
            {
                "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
                "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
                "selected_idea_id": "GOE-001",
                "ideas": ideas,
            },
        )
        write(
            root / ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            {
                "stage": "post_idea_generation_pre_idea_gate",
                "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
                "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
                "evidence_boundary": "source_backed fixture",
                "source_evidence_roles": ["target_domain", "near_neighbor", "far_neighbor"],
                "scoring_rubric": "Fixture GOE scorecard rubric.",
                "weights": {"significance": 1, "novelty_separation": 1, "experiment_defensibility": 1, "feasibility": 1, "evidence_maturity": 1, "risk_control": 1},
                "top_recommendations": ["GOE-001", "GOE-002", "GOE-003", "GOE-004"],
                "top_track_recommendations": ["GOE-001", "GOE-002", "GOE-003", "GOE-004"],
                "selected_primary_idea_id": "GOE-001",
                "alternate_track_idea_ids": ["GOE-002", "GOE-003", "GOE-004"],
                "rows": [goe_score_row(idea, index) for index, idea in enumerate(ideas)],
            },
        )
        write(
            root / ".autoreskill/ideation/CANDIDATE_POOL.json",
            {
                "candidates": [
                    {
                        "id": idea["id"],
                        "status": "advance_with_constraints" if index == 0 else "park",
                        "evidence_ids": idea["paperNexus_evidence_ids"],
                        "weakest_assumption": "closest-prior delta and ablation isolation must close",
                        "falsifier": idea["falsifier_probe"],
                    }
                    for index, idea in enumerate(ideas[:4])
                ]
            },
        )
        write(root / ".autoreskill/ideation/TOURNAMENT_SCOREBOARD.json", {"rows": [{"id": "GOE-001", "rank": 1, "verdict": "advance_with_constraints"}]})
        (root / ".autoreskill/ideation/IDEA_NOVELTY_VENUE_SCORECARD.md").write_text("# Fixture scorecard\n", encoding="utf-8")
        projection = run([sys.executable, str(IDEATION_SCRIPTS / "idea_graph_projection.py"), "--project", str(root)])
        graph = run([sys.executable, str(IDEATION_SCRIPTS / "idea_graph_lint.py"), "--project", str(root), "--write-audit"])
        brief = run([sys.executable, str(IDEATION_SCRIPTS / "idea_build_brief.py"), "--project", str(root)])
        seeds = run([sys.executable, str(IDEATION_SCRIPTS / "idea_track_seeds.py"), "--project", str(root)])
        seed_check = run([sys.executable, str(IDEATION_SCRIPTS / "idea_track_seeds.py"), "--project", str(root), "--check"])
        seed_payload = json.loads(
            (root / ".autoreskill/ideation/IDEA_TRACK_SEEDS.json").read_text(encoding="utf-8")
        )
        write(
            root / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json",
            {
                "selected_primary_idea_id": "GOE-001",
                "selected_track_id": seed_payload["tracks"][0]["track_id"],
                "selection_fingerprint": "GOE-001/fixture-selection-v1",
                "decisions": [
                    {
                        "idea_id": row["idea_id"],
                        "lifecycle_status": "selected_primary" if index == 0 else "alternate",
                        "selected_primary_ref": "GOE-001/fixture-selection-v1",
                    }
                    for index, row in enumerate(seed_payload["tracks"])
                ],
            },
        )
        matrix = run([sys.executable, str(EXPERIMENT_SCRIPTS / "track_plan_matrix.py"), "--project", str(root)])
        matrix_check = run([sys.executable, str(EXPERIMENT_SCRIPTS / "track_plan_matrix.py"), "--project", str(root), "--check"])
        ideation = run([sys.executable, str(IDEATION_SCRIPTS / "ideation_lint.py"), "--project", str(root), "--require-selected"])
        return {
            "case": "goe_package",
            "gate_status": gate.get("status"),
            "projection_nodes": projection.get("nodes"),
            "graph_status": graph.get("status"),
            "brief_boundary": brief.get("evidence_boundary"),
            "track_count": seeds.get("track_count"),
            "seed_status": seed_check.get("status"),
            "matrix_track_count": matrix.get("track_count"),
            "matrix_status": matrix_check.get("status"),
            "ideation_status": ideation.get("status"),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    results = [
        case_pass(),
        case_ratio_fails(),
        case_expansion_and_noise_filtering(),
        case_legacy_reconcile(),
        case_legacy_dry_run_no_write(),
        case_misplaced_gate_dry_run(),
        case_degraded_approval(),
        case_degraded_missing_approval_fails(),
        case_goe_package(),
    ]
    print(json.dumps({"ok": True, "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
