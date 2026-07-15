#!/usr/bin/env python3
"""Focused offline adversarial fixtures for external-gate consumers."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_ROOT = SCRIPT_DIR.parents[1]
PROJECTION = SKILLS_ROOT / "autoreskill-ideation-panel/scripts/idea_graph_projection.py"
MATERIALIZER = SKILLS_ROOT / "autoreskill-experiment-plan/scripts/experiment_materialize.py"
PRE_GATE_LINT = SKILLS_ROOT / "autoreskill-ideation-panel/scripts/pre_idea_evidence_gate_lint.py"
IDEA_POOL_LINT = SKILLS_ROOT / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"
IDEA_SCORECARD_LINT = SKILLS_ROOT / "autoreskill-ideation-panel/scripts/idea_scorecard_lint.py"
sys.path.insert(0, str(SCRIPT_DIR))

import idea_campaign  # noqa: E402
import run_fixtures  # noqa: E402


PLAN_OUTPUTS = (
    "orchestrator/INNOVATION_PACKET.json",
    "planner/EXPERIMENT_REVIEW_PACKET.json",
    "planner/EXPERIMENT_PLAN.md",
    "decision_log.jsonl",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(command: list[str], *, success: bool) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(
        (proc.returncode == 0) is success,
        f"unexpected exit {proc.returncode}: {' '.join(command)}\nstdout={proc.stdout}\nstderr={proc.stderr}",
    )
    return proc


def project_base(root: Path) -> Path:
    return root / ".autoreskill"


def seed_external_project(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign = run_fixtures.valid_campaign()
    run_fixtures.write_campaign(root, campaign)
    result = idea_campaign.materialize(str(root), "absent")
    require(result.get("complete") is True, f"fixture campaign did not materialize: {result}")
    gate = idea_campaign.read_json(project_base(root) / idea_campaign.GATE_REL)
    require(isinstance(gate, dict), "materialized fixture gate is missing")
    return campaign, gate


def write_selected_pool(root: Path, campaign: dict[str, Any]) -> None:
    selected = campaign["admitted_candidate_ids"][0]
    idea_campaign.atomic_write_json(
        project_base(root) / "ideation/EXPERIMENT_IDEA_POOL.json",
        {
            "selected_idea_id": "fixture-fragment",
            "ideas": [
                {
                    "id": "fixture-fragment",
                    "status": "selected",
                    "external_candidate_id": selected,
                    "selected_idea_fragment_id": "fixture-fragment",
                    "track_id": "fixture-track",
                    "evidence_ids": ["ev-target-1"],
                    "one_variable_change": "fixture one-variable change",
                    "falsifier": "fixture falsifier",
                }
            ],
        },
    )


def committed_json(base: Path, stem: str, payload: dict[str, Any], *, allow_nan: bool = False) -> tuple[str, str]:
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=allow_nan) + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    ref = f"ideation/committed/{stem}.{digest}.json"
    path = base / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return ref, digest


def replace_slot_commit(
    root: Path,
    gate: dict[str, Any],
    mutate: Any,
    *,
    allow_nan: bool = False,
) -> None:
    base = project_base(root)
    slot = copy.deepcopy(idea_campaign.read_json(base / gate["innovation_slot_map_path"]))
    mutate(slot)
    slot_ref, slot_sha = committed_json(base, "INNOVATION_SLOT_MAP", slot, allow_nan=allow_nan)
    lint = copy.deepcopy(idea_campaign.read_json(base / gate["lint_ref"]))
    lint["slot_map_ref"] = slot_ref
    lint["slot_map_sha256"] = slot_sha
    lint_ref, lint_sha = committed_json(base, "NON_PAPERNEXUS_IDEA_LINT", lint)
    revised_gate = copy.deepcopy(gate)
    revised_gate.update(
        {
            "innovation_slot_map_path": slot_ref,
            "slot_map_ref": slot_ref,
            "slot_map_sha256": slot_sha,
            "lint_ref": lint_ref,
            "lint_sha256": lint_sha,
        }
    )
    idea_campaign.atomic_write_json(base / idea_campaign.GATE_REL, revised_gate)


def replace_lint_commit(root: Path, gate: dict[str, Any], mutate: Any) -> None:
    base = project_base(root)
    lint = copy.deepcopy(idea_campaign.read_json(base / gate["lint_ref"]))
    mutate(lint)
    lint_ref, lint_sha = committed_json(base, "NON_PAPERNEXUS_IDEA_LINT", lint)
    revised_gate = copy.deepcopy(gate)
    revised_gate.update({"lint_ref": lint_ref, "lint_sha256": lint_sha})
    idea_campaign.atomic_write_json(base / idea_campaign.GATE_REL, revised_gate)


def assert_plan_outputs_absent(root: Path) -> None:
    base = project_base(root)
    present = [rel for rel in PLAN_OUTPUTS if (base / rel).exists()]
    require(not present, f"failed external materialization wrote outputs: {present}")


def projection_command(root: Path) -> list[str]:
    return [sys.executable, str(PROJECTION), "--project", str(root)]


def materializer_command(root: Path) -> list[str]:
    return [sys.executable, str(MATERIALIZER), "--project", str(root)]


def pre_gate_lint_command(root: Path) -> list[str]:
    return [sys.executable, str(PRE_GATE_LINT), "--project", str(root)]


def test_pre_gate_requires_content_addressed_refs() -> None:
    with tempfile.TemporaryDirectory(prefix="external-pre-gate-content-ref-") as raw:
        root = Path(raw)
        _, gate = seed_external_project(root)
        base = project_base(root)
        run(pre_gate_lint_command(root), success=True)

        fixed_lint_ref = "ideation/NON_PAPERNEXUS_IDEA_LINT.json"
        fixed_slot_ref = "ideation/INNOVATION_SLOT_MAP.json"
        (base / fixed_lint_ref).write_bytes((base / gate["lint_ref"]).read_bytes())
        (base / fixed_slot_ref).write_bytes((base / gate["innovation_slot_map_path"]).read_bytes())
        gate.update(
            {
                "lint_ref": fixed_lint_ref,
                "innovation_slot_map_path": fixed_slot_ref,
                "slot_map_ref": fixed_slot_ref,
            }
        )
        idea_campaign.atomic_write_json(base / idea_campaign.GATE_REL, gate)
        run(pre_gate_lint_command(root), success=False)


def test_pool_and_scorecard_bind_committed_slot_ref() -> None:
    with tempfile.TemporaryDirectory(prefix="external-pool-slot-ref-") as raw:
        root = Path(raw)
        _, gate = seed_external_project(root)
        base = project_base(root)
        fixed_slot_ref = "ideation/INNOVATION_SLOT_MAP.json"
        idea_campaign.atomic_write_json(
            base / "ideation/EXPERIMENT_IDEA_POOL.json",
            {
                "pre_idea_evidence_gate_path": str(idea_campaign.GATE_REL),
                "innovation_slot_map_path": fixed_slot_ref,
                "ideas": [],
            },
        )
        pool_proc = run(
            [sys.executable, str(IDEA_POOL_LINT), "--project", str(root)],
            success=False,
        )
        pool_result = json.loads(pool_proc.stdout)
        require(
            "innovation_slot_map_path must match the external PRE_IDEA_EVIDENCE_GATE"
            in pool_result.get("missing", []),
            f"external pool linter did not bind the committed slot ref: {pool_result}",
        )

        idea_campaign.atomic_write_json(
            base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            {
                "stage": "post_idea_generation_pre_idea_gate",
                "pre_idea_evidence_gate_path": str(idea_campaign.GATE_REL),
                "innovation_slot_map_path": fixed_slot_ref,
                "external_campaign_ref": gate["campaign_ref"],
                "external_campaign_sha256": gate["campaign_sha256"],
            },
        )
        score_proc = run(
            [sys.executable, str(IDEA_SCORECARD_LINT), "--project", str(root)],
            success=False,
        )
        score_result = json.loads(score_proc.stdout)
        require(
            "innovation_slot_map_path must match PRE_IDEA_EVIDENCE_GATE.innovation_slot_map_path"
            in score_result.get("missing", []),
            f"external scorecard linter did not bind the committed slot ref: {score_result}",
        )


def test_projection_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="external-projection-blocked-") as raw:
        root = Path(raw)
        _, gate = seed_external_project(root)
        gate["status"] = "blocked"
        idea_campaign.atomic_write_json(project_base(root) / idea_campaign.GATE_REL, gate)
        run(projection_command(root), success=False)
        require(
            not (project_base(root) / "ideation/EVIDENCE_GRAPH_PROJECTION.json").exists(),
            "blocked external gate wrote a graph projection",
        )

    with tempfile.TemporaryDirectory(prefix="external-projection-tampered-") as raw:
        root = Path(raw)
        _, gate = seed_external_project(root)
        slot_path = project_base(root) / gate["innovation_slot_map_path"]
        slot = idea_campaign.read_json(slot_path)
        slot["insight_clusters"][0]["label"] = "ATTACKER SENTINEL"
        idea_campaign.atomic_write_json(slot_path, slot)
        run(projection_command(root), success=False)
        require(
            not (project_base(root) / "ideation/EVIDENCE_GRAPH_PROJECTION.json").exists(),
            "hash-tampered external slot map wrote a graph projection",
        )

    with tempfile.TemporaryDirectory(prefix="external-projection-nonfinite-") as raw:
        root = Path(raw)
        _, gate = seed_external_project(root)
        replace_slot_commit(
            root,
            gate,
            lambda slot: slot["insight_clusters"][0].__setitem__("nonfinite", float("nan")),
            allow_nan=True,
        )
        run(projection_command(root), success=False)
        require(
            not (project_base(root) / "ideation/EVIDENCE_GRAPH_PROJECTION.json").exists(),
            "non-finite external slot map wrote a graph projection",
        )

    with tempfile.TemporaryDirectory(prefix="external-projection-rehashed-drift-") as raw:
        root = Path(raw)
        _, gate = seed_external_project(root)
        replace_slot_commit(
            root,
            gate,
            lambda slot: slot["insight_clusters"][0].__setitem__("title", "ATTACKER SENTINEL"),
        )
        run(projection_command(root), success=False)
        require(
            not (project_base(root) / "ideation/EVIDENCE_GRAPH_PROJECTION.json").exists(),
            "rehashed external slot-map drift wrote a graph projection",
        )

    with tempfile.TemporaryDirectory(prefix="external-projection-misnamed-") as raw:
        root = Path(raw)
        _, gate = seed_external_project(root)
        base = project_base(root)
        wrong_ref = f"ideation/committed/NON_PAPERNEXUS_IDEA_LINT.{'0' * 64}.json"
        (base / wrong_ref).write_bytes((base / gate["lint_ref"]).read_bytes())
        gate["lint_ref"] = wrong_ref
        idea_campaign.atomic_write_json(base / idea_campaign.GATE_REL, gate)
        run(projection_command(root), success=False)
        require(
            not (base / "ideation/EVIDENCE_GRAPH_PROJECTION.json").exists(),
            "misnamed content-addressed lint wrote a graph projection",
        )


def test_materializer_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="external-plan-blocked-") as raw:
        root = Path(raw)
        campaign, gate = seed_external_project(root)
        write_selected_pool(root, campaign)
        gate["status"] = "blocked"
        idea_campaign.atomic_write_json(project_base(root) / idea_campaign.GATE_REL, gate)
        run(materializer_command(root), success=False)
        assert_plan_outputs_absent(root)

    with tempfile.TemporaryDirectory(prefix="external-plan-tampered-") as raw:
        root = Path(raw)
        campaign, gate = seed_external_project(root)
        write_selected_pool(root, campaign)
        slot_path = project_base(root) / gate["innovation_slot_map_path"]
        slot = idea_campaign.read_json(slot_path)
        slot["campaign_revision"] = 999
        idea_campaign.atomic_write_json(slot_path, slot)
        run(materializer_command(root), success=False)
        assert_plan_outputs_absent(root)

    with tempfile.TemporaryDirectory(prefix="external-plan-lineage-") as raw:
        root = Path(raw)
        campaign, gate = seed_external_project(root)
        write_selected_pool(root, campaign)
        replace_slot_commit(root, gate, lambda slot: slot.__setitem__("campaign_revision", 999))
        run(materializer_command(root), success=False)
        assert_plan_outputs_absent(root)

    with tempfile.TemporaryDirectory(prefix="external-plan-lint-blocked-") as raw:
        root = Path(raw)
        campaign, gate = seed_external_project(root)
        write_selected_pool(root, campaign)
        replace_lint_commit(root, gate, lambda lint: lint.__setitem__("status", "blocked"))
        run(materializer_command(root), success=False)
        assert_plan_outputs_absent(root)

    with tempfile.TemporaryDirectory(prefix="external-plan-duplicate-json-") as raw:
        root = Path(raw)
        campaign, gate = seed_external_project(root)
        write_selected_pool(root, campaign)
        gate_path = project_base(root) / idea_campaign.GATE_REL
        raw_gate = json.dumps(gate, ensure_ascii=False, sort_keys=True)
        raw_gate = raw_gate.replace(
            '"evidence_source_mode": "external_material"',
            '"evidence_source_mode": "external_material", "evidence_source_mode": "papernexus"',
            1,
        )
        gate_path.write_text(raw_gate + "\n", encoding="utf-8")
        run(materializer_command(root), success=False)
        assert_plan_outputs_absent(root)


def test_valid_and_legacy_routes() -> None:
    with tempfile.TemporaryDirectory(prefix="external-consumer-valid-") as raw:
        root = Path(raw)
        campaign, _ = seed_external_project(root)
        write_selected_pool(root, campaign)
        run(projection_command(root), success=True)
        run(materializer_command(root), success=True)
        require(
            (project_base(root) / "ideation/EVIDENCE_GRAPH_PROJECTION.json").is_file(),
            "valid external projection was not written",
        )
        require(
            (project_base(root) / "orchestrator/INNOVATION_PACKET.json").is_file(),
            "valid external experiment packet was not written",
        )

    with tempfile.TemporaryDirectory(prefix="papernexus-consumer-legacy-") as raw:
        root = Path(raw)
        base = project_base(root)
        idea_campaign.atomic_write_json(
            base / "ideation/PRE_IDEA_EVIDENCE_GATE.json",
            {"schema_version": 1, "status": "passed", "evidence_source_mode": "papernexus"},
        )
        idea_campaign.atomic_write_json(
            base / "ideation/EXPERIMENT_IDEA_POOL.json",
            {
                "selected_idea_id": "legacy-idea",
                "ideas": [
                    {
                        "id": "legacy-idea",
                        "status": "selected",
                        "track_id": "legacy-track",
                        "evidence_ids": ["legacy-evidence"],
                    }
                ],
            },
        )
        run(projection_command(root), success=True)
        run(materializer_command(root), success=True)
        require(
            (base / "ideation/EVIDENCE_GRAPH_PROJECTION.json").is_file()
            and (base / "orchestrator/INNOVATION_PACKET.json").is_file(),
            "legacy PaperNexus consumers changed behavior",
        )


def main() -> int:
    test_pre_gate_requires_content_addressed_refs()
    test_pool_and_scorecard_bind_committed_slot_ref()
    test_projection_fail_closed()
    test_materializer_fail_closed()
    test_valid_and_legacy_routes()
    print("PASS external content-addressed consumer fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
