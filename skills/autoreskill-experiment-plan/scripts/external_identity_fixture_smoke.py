#!/usr/bin/env python3
"""Exercise external campaign identity propagation through seeds and matrix."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SKILLS = Path(__file__).resolve().parents[2]
IDEATION_SCRIPT = SKILLS / "autoreskill-ideation-panel/scripts/idea_track_seeds.py"
PRE_IDEA_GATE_SCRIPT = SKILLS / "autoreskill-ideation-panel/scripts/pre_idea_evidence_gate_lint.py"
MATRIX_SCRIPT = SKILLS / "autoreskill-experiment-plan/scripts/track_plan_matrix.py"
MATERIALIZE_SCRIPT = SKILLS / "autoreskill-experiment-plan/scripts/experiment_materialize.py"
PRELAUNCH_LINT_SCRIPT = SKILLS / "autoreskill-experiment-plan/scripts/prelaunch_lint.py"
SCAFFOLD_SCRIPT = SKILLS / "autoreskill-implement-experiment/scripts/experiment_scaffold.py"
DRIFT_SCRIPT = SKILLS / "autoreskill-implement-experiment/scripts/experiment_drift_lint.py"
RUN_RECONCILE_SCRIPT = SKILLS / "autoreskill-run-experiment/scripts/run_reconcile.py"
SUPPORT_SCRIPT = SKILLS / "autoreskill-papernexus-innovation/scripts/idea_support_lint.py"
ALIGNMENT_SCRIPT = SKILLS / "autoreskill-gpu-idea-validation/scripts/external_alignment_lint.py"
GPU_SCRIPT_DIR = SKILLS / "autoreskill-gpu-idea-validation/scripts"
sys.path.insert(0, str(GPU_SCRIPT_DIR))

import idea_campaign  # noqa: E402
import run_fixtures  # noqa: E402


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], expect_success: bool = True) -> dict[str, Any]:
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if expect_success != (proc.returncode == 0):
        raise AssertionError(f"unexpected exit {proc.returncode}: {' '.join(command)}\n{proc.stdout}\n{proc.stderr}")
    if proc.stdout.strip():
        return json.loads(proc.stdout)
    return {"error": proc.stderr.strip(), "returncode": proc.returncode}


def campaign_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_sha(payload: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at", "semantic_sha256"}
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def local_idea(candidate: dict[str, Any], index: int, sha: str) -> dict[str, Any]:
    mechanism = candidate["mechanism"]
    rapid = candidate["rapid_validation"]
    dataset_id = str(rapid["dataset"]["name"])
    seed = int(rapid["seed_policy"]["seed"])
    idea = {
        "id": f"fragment-{index:02d}",
        "external_campaign_ref": str(idea_campaign.CAMPAIGN_REL),
        "external_campaign_sha256": sha,
        "external_candidate_id": candidate["id"],
        "research_question": candidate["research_question"],
        "causal_signature": f"{candidate['id']} conditioned gate intervention",
        "intervention": mechanism["intervention"],
        "one_variable_change": mechanism["one_variable_change"],
        "mechanism": mechanism,
        "predicted_pattern": mechanism["predicted_observation"],
        "falsifier": mechanism["falsifier"],
        "alternative_explanation": mechanism["alternative_explanation"],
        "cheapest_discriminating_experiment": rapid["expected_decision_change"],
        "expected_metric_impact": "positive only when the proposed causal alignment holds",
        "outcome_routes": {
            "positive": rapid["outcome_routes"]["valid_positive_candidate"],
            "negative": rapid["outcome_routes"]["valid_negative"],
            "inconclusive": rapid["outcome_routes"]["valid_inconclusive"],
            "invalid": {
                "infrastructure_failure": rapid["outcome_routes"]["infrastructure_failure"],
                "implementation_failure": rapid["outcome_routes"]["implementation_failure"],
                "protocol_invalid": rapid["outcome_routes"]["protocol_invalid"],
            },
        },
        "track_seed_spec": {
            "baseline_pressure": "matched external baseline must remain locked",
            "red_line_risks": ["parameter-count confound", "protocol drift"],
        },
        "baseline_code": {
            **rapid["baseline_code"],
            "code_id": "fixture-baseline",
            "source_type": "official_repo_snapshot",
            "selection_rationale": "locked offline fixture for protocol-complete launch lint",
        },
        "compute_backend": {
            "backend": "local_gpu",
            "decision_rationale": "bounded offline fixture route",
            "gpu_evidence": "fixture resource observation; no live launch",
            "paid_resource_policy": "no paid resource without separate authorization",
        },
        "path_mapping": {
            "selected_backend": "local_gpu",
            "logical_dataset_id": dataset_id,
            "code_root": "/tmp/fixture-baseline",
            "data_root": "/tmp/fixture-data",
            "output_dir": "/tmp/fixture-output",
            "checkpoint_dir": "/tmp/fixture-output/checkpoints",
            "persistent_output_dir": "/tmp/fixture-output/persistent",
            "env": {
                "DATA_ROOT": "/tmp/fixture-data",
                "OUTPUT_DIR": "/tmp/fixture-output",
                "CKPT_DIR": "/tmp/fixture-output/checkpoints",
            },
        },
        "dataset_requirement_inventory": {
            "required_datasets": [
                {
                    "dataset_id": dataset_id,
                    "dataset_name": dataset_id,
                    "claim_role": "method_validation",
                    "reason_required": "smallest baseline-supported fixture dataset",
                    "baseline_supported": True,
                    "availability": "available",
                    "scale_class": "small_multiclass",
                    "num_classes": 10,
                    "train_samples": 1000,
                    "eval_samples": 200,
                    "native_protocol_ref": "fixture-baseline@0123456789abcdef",
                    "native_epochs_or_steps": 1,
                    "native_warmup_or_schedule": "baseline default",
                    "data_root_or_probe": "/tmp/fixture-data",
                    "selection_status": "selected_first",
                    "estimated_gpu_hours": 0.5,
                }
            ],
            "selection_rule": "choose_smallest_available_baseline_supported_required_dataset_for_method_validation",
            "method_validation_dataset_id": dataset_id,
            "smallest_available_required_dataset_id": dataset_id,
        },
        "dataset_runtime_plan": {
            "candidate_datasets": [
                {
                    "dataset_id": dataset_id,
                    "scale_class": "small_multiclass",
                    "num_classes": 10,
                    "train_samples": 1000,
                    "eval_samples": 200,
                    "epochs_or_steps": 1,
                    "estimated_minutes_per_epoch": 10,
                    "estimated_walltime_hours": 0.5,
                    "estimated_gpu_hours": 0.5,
                    "estimation_basis": "offline fixture dimensions and bounded pilot budget",
                }
            ],
            "feasibility_first_dataset_id": dataset_id,
            "first_run_scale_class": "small_multiclass",
            "largest_dataset_id": dataset_id,
            "largest_dataset_deferred": True,
            "escalation_criteria": ["smoke and metric parsing pass"],
            "runtime_risk": "offline fixture only; no live runtime claim",
        },
        "stability_seed_policy": {
            "max_random_seeds": 3,
            "planned_seed_count": 1,
            "planned_random_seeds": [seed],
            "claim_rule": "A pilot uses one seed; stability confirmation may use at most three unique random seeds.",
            "scope_note": "IDEA_TRACK_SEEDS are hypotheses, not random seeds.",
        },
        "source_evidence_refs": ["ev-target-1", "ev-target-2"],
    }
    if index == 0:
        idea.update(
            {
                "core_scientific_contribution": "A conditioned gate isolates and repairs the matched fixture bottleneck.",
                "paper_storyline": {
                    "paper_thesis": "A conditioned gate repairs a failure caused by a shared fixed-gate assumption.",
                    "opening_tension": "The locked baseline underperforms under the matched bottleneck.",
                    "hidden_cause": "A fixed gate cannot follow the target statistic.",
                    "method_as_resolution": "Condition only the existing scalar gate while freezing all other operations.",
                    "proof_ladder": "Pilot, negative control, ablation, and matched confirmation.",
                    "reviewer_risk_and_defense": "Capacity confounds are tested with a shuffled-gate control.",
                    "narrative_spine": [
                        "establish the matched failure",
                        "isolate the fixed-gate cause",
                        "apply one conditioned intervention",
                        "falsify with the shuffled control",
                        "confirm on the frozen matched protocol",
                    ],
                },
            }
        )
    return idea


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="external-identity-fixture-"))
    try:
        campaign = run_fixtures.valid_campaign()
        admitted_ids = [row["id"] for row in campaign["candidates"][:4]]
        campaign["shortlisted_candidate_ids"] = admitted_ids
        campaign["admitted_candidate_ids"] = admitted_ids
        for row in campaign["candidates"]:
            row["status"] = "admitted" if row["id"] in admitted_ids else "candidate"
        campaign_path = root / ".autoreskill" / idea_campaign.CAMPAIGN_REL
        write(campaign_path, campaign)
        materialized = idea_campaign.materialize(str(root), "absent")
        if not materialized.get("complete"):
            raise AssertionError(materialized)
        pre_idea_gate = run([sys.executable, str(PRE_IDEA_GATE_SCRIPT), "--project", str(root)])
        sha = campaign_sha(campaign_path)
        ideas = [local_idea(candidate, index, sha) for index, candidate in enumerate(campaign["candidates"])]
        admitted = set(campaign["admitted_candidate_ids"])
        admitted_ideas = [idea for idea in ideas if idea["external_candidate_id"] in admitted]
        base = root / ".autoreskill"
        write(
            base / "ideation/EXPERIMENT_IDEA_POOL.json",
            {"selected_idea_id": admitted_ideas[0]["id"], "ideas": ideas},
        )
        write(
            base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            {
                "active_track_limit": 4,
                "selected_primary_idea_id": admitted_ideas[0]["id"],
                "top_track_recommendations": [idea["id"] for idea in admitted_ideas],
                "candidates": [
                    {
                        "id": idea["id"],
                        "rank": index + 1,
                        "promotion_recommendation": "advance" if idea in admitted_ideas else "reject",
                        "external_campaign_ref": idea["external_campaign_ref"],
                        "external_campaign_sha256": sha,
                        "external_candidate_id": idea["external_candidate_id"],
                    }
                    for index, idea in enumerate(ideas)
                ],
            },
        )

        run([sys.executable, str(IDEATION_SCRIPT), "--project", str(root)])
        seed_check = run([sys.executable, str(IDEATION_SCRIPT), "--project", str(root), "--check"])
        seeds = json.loads((base / "ideation/IDEA_TRACK_SEEDS.json").read_text(encoding="utf-8"))
        if {row["external_candidate_id"] for row in seeds["tracks"]} != admitted:
            raise AssertionError("seed identity set drifted from admitted campaign ids")
        if len(seeds["tracks"]) != 4:
            raise AssertionError("fixture must retain exactly one primary and three alternates")

        run(
            [
                sys.executable,
                str(MATERIALIZE_SCRIPT),
                "--project",
                str(root),
                "--track-id",
                str(seeds["tracks"][0]["track_id"]),
            ]
        )
        innovation = json.loads((base / "orchestrator/INNOVATION_PACKET.json").read_text(encoding="utf-8"))
        if innovation.get("external_candidate_id") != seeds["tracks"][0]["external_candidate_id"]:
            raise AssertionError("experiment materializer lost selected external candidate identity")
        if innovation.get("execution_route") != "local" or innovation.get("compute_backend", {}).get("backend") != "local_gpu":
            raise AssertionError("experiment materializer did not preserve external resource route/backend")
        if "paperNexus_corpus" in innovation or "idea_evidence_export_path" in innovation:
            raise AssertionError("external experiment materialization emitted PaperNexus provenance")

        selection = "fixture-external-selection-v1"
        write(
            base / "ideation/IDEA_DECISION_LEDGER.json",
            {
                "selected_primary_idea_id": seeds["tracks"][0]["idea_id"],
                "selected_track_id": seeds["tracks"][0]["track_id"],
                "selection_fingerprint": selection,
                "decisions": [
                    {
                        "idea_id": row["idea_id"],
                        "lifecycle_status": "selected_primary" if index == 0 else "alternate",
                        "selected_primary_ref": selection,
                        "external_campaign_ref": row["external_campaign_ref"],
                        "external_campaign_sha256": row["external_campaign_sha256"],
                        "external_candidate_id": row["external_candidate_id"],
                    }
                    for index, row in enumerate(seeds["tracks"])
                ],
            },
        )
        dry_run = run(
            [
                sys.executable,
                str(MATERIALIZE_SCRIPT),
                "--project",
                str(root),
                "--all-admitted",
                "--dry-run",
            ]
        )
        report = dry_run.get("migration_report") or {}
        if len(report.get("admitted_tracks") or []) != 4:
            raise AssertionError("migration dry run did not list every admitted track")
        if len(report.get("rows_that_would_become_eligible") or []) != 4:
            raise AssertionError("migration dry run did not report eligible track rows")
        if not report.get("files_that_would_be_written"):
            raise AssertionError("migration dry run missed absent alternate packet files")

        run(
            [
                sys.executable,
                str(MATERIALIZE_SCRIPT),
                "--project",
                str(root),
                "--all-admitted",
            ]
        )
        for index, row in enumerate(seeds["tracks"]):
            track_id = row["track_id"]
            packet = json.loads(
                (base / f"orchestrator/tracks/{track_id}/INNOVATION_PACKET.json").read_text(encoding="utf-8")
            )
            review = json.loads(
                (base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json").read_text(encoding="utf-8")
            )
            if packet.get("selected_idea_id") != row["idea_id"] or packet.get("track_id") != track_id:
                raise AssertionError("per-track materialization relabeled an idea/track identity")
            expected_ceiling = "claim_eligible_after_gates" if index == 0 else "pilot_only"
            if packet.get("evidence_tier_ceiling") != expected_ceiling or review.get("evidence_tier_ceiling") != expected_ceiling:
                raise AssertionError("per-track evidence ceiling does not match the track role")
        projected = json.loads((base / "orchestrator/INNOVATION_PACKET.json").read_text(encoding="utf-8"))
        if projected.get("selected_idea_id") != seeds["tracks"][0]["idea_id"]:
            raise AssertionError("top-level compatibility packet is not the current primary")
        idempotent_dry_run = run(
            [
                sys.executable,
                str(MATERIALIZE_SCRIPT),
                "--project",
                str(root),
                "--all-admitted",
                "--dry-run",
            ]
        )
        if (idempotent_dry_run.get("migration_report") or {}).get("files_that_would_be_written"):
            raise AssertionError("repeated per-track materialization is not semantically idempotent")

        tampered = json.loads(json.dumps(seeds))
        tampered["tracks"][1]["idea_id"] = tampered["tracks"][0]["idea_id"]
        tampered["semantic_sha256"] = semantic_sha(tampered)
        write(base / "ideation/IDEA_TRACK_SEEDS.json", tampered)
        mismatch = run(
            [
                sys.executable,
                str(MATERIALIZE_SCRIPT),
                "--project",
                str(root),
                "--track-id",
                str(tampered["tracks"][1]["track_id"]),
            ],
            expect_success=False,
        )
        if "cannot relabel" not in str(mismatch.get("error") or mismatch):
            raise AssertionError("alternate track accepted a relabeled primary idea")
        write(base / "ideation/IDEA_TRACK_SEEDS.json", seeds)

        decision_ledger_path = base / "ideation/IDEA_DECISION_LEDGER.json"
        decision_ledger = json.loads(decision_ledger_path.read_text(encoding="utf-8"))
        killed_ledger = json.loads(json.dumps(decision_ledger))
        killed_ledger["decisions"][1]["lifecycle_status"] = "killed"
        write(decision_ledger_path, killed_ledger)
        killed = run(
            [
                sys.executable,
                str(MATERIALIZE_SCRIPT),
                "--project",
                str(root),
                "--track-id",
                str(seeds["tracks"][1]["track_id"]),
            ],
            expect_success=False,
        )
        if "is not admitted" not in str(killed.get("error") or killed):
            raise AssertionError("killed track remained materializable")
        write(decision_ledger_path, decision_ledger)
        unknown = run(
            [
                sys.executable,
                str(MATERIALIZE_SCRIPT),
                "--project",
                str(root),
                "--track-id",
                "track-not-admitted",
            ],
            expect_success=False,
        )
        if "resolve exactly one" not in str(unknown.get("error") or unknown):
            raise AssertionError("unseeded track selector did not fail closed")
        unsafe_prelaunch = run(
            [
                sys.executable,
                str(PRELAUNCH_LINT_SCRIPT),
                "--project",
                str(root),
                "--track-id",
                "../track-not-safe",
            ],
            expect_success=False,
        )
        if "safe path component" not in str(unsafe_prelaunch.get("error") or unsafe_prelaunch):
            raise AssertionError("prelaunch track selector accepted a path component")

        run([sys.executable, str(MATRIX_SCRIPT), "--project", str(root)])
        matrix_check = run([sys.executable, str(MATRIX_SCRIPT), "--project", str(root), "--check"])
        matrix_path = base / "orchestrator/TRACK_PLAN_MATRIX.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        if {row["external_candidate_id"] for row in matrix["tracks"]} != admitted:
            raise AssertionError("matrix identity set drifted from admitted campaign ids")
        if len([row for row in matrix["tracks"] if row.get("launch_status") == "ready"]) != 4:
            raise AssertionError("all four complete admitted tracks must become planning-ready")
        if any(
            row.get("evidence_tier_ceiling") != "pilot_only"
            for row in matrix["tracks"]
            if row.get("track_role") != "primary"
        ):
            raise AssertionError("matrix lost the non-primary pilot-only ceiling")

        alternate = seeds["tracks"][1]
        alternate_track_id = str(alternate["track_id"])
        run(
            [
                sys.executable,
                str(SCAFFOLD_SCRIPT),
                "--project",
                str(root),
                "--track-id",
                alternate_track_id,
                "--experiment-id",
                "alternate-pilot",
            ]
        )
        alternate_dir = base / f"coder/experiments/{alternate_track_id}/alternate-pilot"
        alternate_manifest = json.loads(
            (alternate_dir / "EXPERIMENT_MANIFEST.json").read_text(encoding="utf-8")
        )
        if alternate_manifest.get("selected_idea_id") != alternate["idea_id"]:
            raise AssertionError("implementation scaffold selected the primary idea for an alternate track")
        if alternate_manifest.get("track_role") != "alternate":
            raise AssertionError("implementation scaffold lost the alternate role")
        if alternate_manifest.get("evidence_tier") != "pilot_only" or alternate_manifest.get(
            "evidence_tier_ceiling"
        ) != "pilot_only":
            raise AssertionError("implementation scaffold elevated alternate evidence above pilot_only")
        if alternate_manifest.get("track_plan_matrix_sha256") != matrix.get("semantic_sha256"):
            raise AssertionError("implementation scaffold lost the current matrix hash")
        if alternate_manifest.get("source_track_seed_sha256") != seeds.get("semantic_sha256"):
            raise AssertionError("implementation scaffold lost the admitted-track seed hash")
        drift_check = run([sys.executable, str(DRIFT_SCRIPT), "--project", str(root)])
        write(
            alternate_dir / "results/metrics.json",
            {"primary_metric": 0.60, "baseline": 0.50, "proposed": 0.60, "fixture": False},
        )
        run(
            [
                sys.executable,
                str(RUN_RECONCILE_SCRIPT),
                "--project",
                str(root),
                "--backend",
                "manual",
                "--status",
                "completed",
                "--command",
                "offline fixture reconcile",
            ]
        )
        experiment_ledger = json.loads((base / "coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        alternate_entry = experiment_ledger["entries"][0]
        if alternate_entry.get("track_id") != alternate_track_id:
            raise AssertionError("run reconciliation replaced alternate identity with the primary track")
        if alternate_entry.get("track_plan_matrix_sha256") != matrix.get("semantic_sha256"):
            raise AssertionError("run reconciliation lost matrix provenance")
        if alternate_entry.get("promotion_decision") != "record_only":
            raise AssertionError("an improved alternate pilot escaped its evidence ceiling")
        if experiment_ledger.get("improvement_claim_allowed") is not False:
            raise AssertionError("alternate-only pilot evidence enabled an improvement claim")

        alternate_review_path = base / f"planner/tracks/{alternate_track_id}/EXPERIMENT_REVIEW_PACKET.json"
        alternate_innovation_path = base / f"orchestrator/tracks/{alternate_track_id}/INNOVATION_PACKET.json"
        current_review = json.loads(alternate_review_path.read_text(encoding="utf-8"))
        current_innovation = json.loads(alternate_innovation_path.read_text(encoding="utf-8"))
        for path, payload in [
            (alternate_review_path, json.loads(json.dumps(current_review))),
            (alternate_innovation_path, json.loads(json.dumps(current_innovation))),
        ]:
            payload["selection_fingerprint"] = "fixture-reselected-primary-v2"
            payload["semantic_sha256"] = semantic_sha(payload)
            write(path, payload)
        run(
            [
                sys.executable,
                str(RUN_RECONCILE_SCRIPT),
                "--project",
                str(root),
                "--backend",
                "manual",
                "--status",
                "completed",
                "--command",
                "offline historical fixture reconcile",
            ]
        )
        historical_ledger = json.loads((base / "coder/EXPERIMENT_LEDGER.json").read_text(encoding="utf-8"))
        historical_entry = historical_ledger["entries"][0]
        if historical_entry.get("historical_plan_stale") is not True:
            raise AssertionError("old-selection run was not marked historical after primary reselection")
        if historical_entry.get("follow_up_allowed") is not False:
            raise AssertionError("old-selection run remained allowed to spawn follow-up work")
        if historical_entry.get("promotion_decision") != "record_only":
            raise AssertionError("old-selection evidence escaped the historical record-only boundary")
        write(alternate_review_path, current_review)
        write(alternate_innovation_path, current_innovation)

        write(
            base / "ideation/PANEL_DESIGN_REVIEW.json",
            {
                "status": "passed",
                "verdict": "advance",
                "reviewer_role": "independent_panel",
                "generation_context_id": "fixture-generation-context",
                "reviewer_context_id": "fixture-independent-review-context",
                "context_separated": True,
                "external_campaign_ref": str(idea_campaign.CAMPAIGN_REL),
                "external_campaign_sha256": sha,
                "reviewed_candidate_ids": sorted(admitted),
            },
        )
        prelaunch_lint_statuses = []
        for row in seeds["tracks"]:
            track_id = str(row["track_id"])
            prelaunch_lint_statuses.append(
                run(
                    [
                        sys.executable,
                        str(PRELAUNCH_LINT_SCRIPT),
                        "--project",
                        str(root),
                        "--track-id",
                        track_id,
                    ]
                )["status"]
            )
        alignment_check = run(
            [sys.executable, str(ALIGNMENT_SCRIPT), "--project", str(root), "--stage", "experiment_plan"]
        )
        support_check = run([sys.executable, str(SUPPORT_SCRIPT), "--project", str(root)])

        matrix["tracks"][0]["external_campaign_sha256"] = "0" * 64
        write(matrix_path, matrix)
        stale = run([sys.executable, str(MATRIX_SCRIPT), "--project", str(root), "--check"], expect_success=False)
        if "current campaign" not in "\n".join(stale.get("missing", [])):
            raise AssertionError("matrix lint accepted stale external campaign identity")

        print(
            json.dumps(
                {
                    "complete": True,
                    "seed_status": seed_check["status"],
                    "pre_idea_gate_status": pre_idea_gate["status"],
                    "matrix_status": matrix_check["status"],
                    "per_track_prelaunch_lint_statuses": prelaunch_lint_statuses,
                    "alignment_status": alignment_check["status"],
                    "support_status": support_check["status"],
                    "admitted_candidate_ids": sorted(admitted),
                    "materialized_track_count": 4,
                    "migration_dry_run_complete": True,
                    "implementation_drift_status": drift_check["status"],
                    "alternate_runtime_decision": alternate_entry["promotion_decision"],
                    "old_selection_reconciled_historical_only": True,
                    "track_relabel_rejected": True,
                    "killed_or_unseeded_track_rejected": True,
                    "unsafe_track_path_rejected": True,
                    "stale_hash_rejected": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
