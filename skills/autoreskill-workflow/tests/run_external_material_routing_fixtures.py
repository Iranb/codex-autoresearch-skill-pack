#!/usr/bin/env python3
"""Offline routing checks for the non-PaperNexus campaign and GPU handoff."""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import goal_tick  # noqa: E402


IDEA_CAMPAIGN = (
    Path.home()
    / ".codex/skills/autoreskill-gpu-idea-validation/scripts/idea_campaign.py"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def payload_sha(payload: Any) -> str:
    raw = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_committed_gate(base: Path, campaign_path: Path, *, lint_complete: bool = True) -> dict[str, Path]:
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    campaign_sha = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
    campaign_id = campaign["campaign_id"]
    campaign_revision = campaign["campaign_revision"]
    admitted = ["external-candidate-fixture"]
    slot = {
        "schema_version": 1,
        "source_mode": "external_material",
        "campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign_id,
        "campaign_revision": campaign_revision,
        "admitted_candidate_ids": admitted,
    }
    slot_sha = payload_sha(slot)
    slot_ref = f"ideation/committed/INNOVATION_SLOT_MAP.{slot_sha}.json"
    slot_path = base / slot_ref
    write_json(slot_path, slot)
    lint = {
        "schema_version": 1,
        "complete": lint_complete,
        "status": "passed" if lint_complete else "blocked",
        "campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign_id,
        "campaign_revision": campaign_revision,
        "slot_map_ref": slot_ref,
        "slot_map_sha256": slot_sha,
        "admitted_candidate_ids": admitted,
    }
    lint_sha = payload_sha(lint)
    lint_ref = f"ideation/committed/NON_PAPERNEXUS_IDEA_LINT.{lint_sha}.json"
    lint_path = base / lint_ref
    write_json(lint_path, lint)
    gate = {
        "schema_version": 1,
        "status": "passed",
        "evidence_source_mode": "external_material",
        "lane_attempts_satisfied": True,
        "screening_completed": True,
        "allowed_next_action": "generate_experiment_idea_pool",
        "commit_layout": "content_addressed_v1",
        "campaign_ref": "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json",
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign_id,
        "campaign_revision": campaign_revision,
        "lint_ref": lint_ref,
        "lint_sha256": lint_sha,
        "innovation_slot_map_path": slot_ref,
        "slot_map_ref": slot_ref,
        "slot_map_sha256": slot_sha,
        "admitted_candidate_ids": admitted,
    }
    gate_path = base / "ideation/PRE_IDEA_EVIDENCE_GATE.json"
    write_json(gate_path, gate)
    return {"gate": gate_path, "lint": lint_path, "slot": slot_path}


def spec(stage: str, base: Path, action: str = "") -> dict[str, Any]:
    state = {"goal": "fixture external idea validation", "paperNexus": {"corpus": "fixture"}}
    job = {"action": action} if action else {}
    return goal_tick.execution_spec(stage, state, {"missing": []}, job, base)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / ".autoreskill"
        campaign_path = base / "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
        gate_path = base / "ideation/PRE_IDEA_EVIDENCE_GATE.json"
        write_json(
            campaign_path,
            {
                "schema_version": 1,
                "campaign_id": "fixture-external-campaign",
                "campaign_revision": 1,
                "source_mode": "external_material",
                "papernexus_used": False,
            },
        )

        pre_gate = spec("ideation", base)
        require(
            pre_gate["skill"] == "autoreskill-gpu-idea-validation",
            f"uncommitted external campaign must route to the new evidence skill: {pre_gate}",
        )
        require(pre_gate["mcp_calls"] == [], f"external campaign construction must not call PaperNexus: {pre_gate}")
        require(
            any("idea_campaign.py" in command and "materialize" in command for command in pre_gate["capture"]),
            f"pre-gate route must expose campaign materialization: {pre_gate}",
        )
        require(
            ".autoreskill/ideation/committed/NON_PAPERNEXUS_IDEA_LINT.*.json" in pre_gate["outputs"]
            and ".autoreskill/ideation/committed/INNOVATION_SLOT_MAP.*.json" in pre_gate["outputs"],
            f"external materialization must advertise content-addressed derived artifacts: {pre_gate}",
        )
        require(
            ".autoreskill/ideation/NON_PAPERNEXUS_IDEA_LINT.json" not in pre_gate["outputs"]
            and ".autoreskill/ideation/INNOVATION_SLOT_MAP.json" not in pre_gate["outputs"],
            f"external materialization must not advertise legacy fixed derived paths: {pre_gate}",
        )

        write_json(gate_path, {"status": "passed"})
        legacy = spec("ideation", base)
        require(
            legacy["skill"] == "autoreskill-ideation-panel" and legacy["mcp_calls"],
            f"an existing missing-mode gate must retain legacy PaperNexus routing: {legacy}",
        )

        write_json(gate_path, {"status": "passed", "evidence_source_mode": "mystery_source"})
        unknown = spec("experiment", base, "launch_parallel_experiment")
        require(unknown["skill"] == "autoreskill-workflow", f"unknown source mode must stop in WorkflowGuard: {unknown}")
        require(unknown["mcp_calls"] == [] and unknown["capture"] == [], f"unknown route must expose no side effect: {unknown}")
        require("Stop and reconcile" in unknown["goal"], f"unknown route needs an explicit fail-closed goal: {unknown}")
        unknown_packet_path = goal_tick.write_job_packet(
            base,
            {"stage": "experiment", "goal": "fixture", "paperNexus": {"corpus": "fixture"}},
            {"job_id": "unknown-route", "stage": "experiment", "action": "launch_parallel_experiment"},
            {"missing": []},
            None,
            "repair_queue.jsonl",
        )
        unknown_packet = json.loads(unknown_packet_path.read_text(encoding="utf-8"))
        require(unknown_packet["allowed_writes"] == [], f"unknown route must grant no child writes: {unknown_packet}")
        require(
            any("Fail closed" in item for item in unknown_packet["constraints"]),
            f"unknown job packet must carry fail-closed constraints: {unknown_packet}",
        )

        committed_paths = write_committed_gate(base, campaign_path)
        committed = spec("ideation", base)
        committed_commands = "\n".join(committed["capture"])
        require(committed["skill"] == "autoreskill-ideation-panel", f"committed gate returns to stage owner: {committed}")
        require(committed["mcp_calls"] == [], f"committed external ideation must omit PaperNexus calls: {committed}")
        require("external_alignment_lint.py" in committed_commands, f"external ideation must align identities: {committed}")
        require(
            "autoreskill-papernexus-innovation" not in committed_commands,
            f"external ideation capture must omit PaperNexus child commands: {committed}",
        )

        committed_paths["slot"].unlink()
        torn = spec("ideation", base)
        require(
            torn["skill"] == "autoreskill-gpu-idea-validation",
            f"a torn external gate commit must route to evidence-adapter recovery: {torn}",
        )
        committed_paths = write_committed_gate(base, campaign_path)

        for stage in ("idea_gate", "experiment_plan"):
            routed = spec(stage, base)
            commands = "\n".join(routed["capture"])
            require(routed["mcp_calls"] == [], f"{stage} external route must omit PaperNexus calls: {routed}")
            require(
                f"--stage {stage}" in commands and "external_alignment_lint.py" in commands,
                f"{stage} external route must require alignment: {routed}",
            )
            require(
                ".autoreskill/ideation/NON_PAPERNEXUS_IDEA_LINT.json" not in routed["outputs"]
                and ".autoreskill/ideation/INNOVATION_SLOT_MAP.json" not in routed["outputs"],
                f"{stage} external route must not expose legacy fixed derived paths: {routed}",
            )
            if stage == "idea_gate":
                panel_tokens = [
                    "template --kind panel-design-review",
                    "write-panel-design-review",
                    "external_alignment_lint.py",
                ]
                panel_positions = [commands.index(token) for token in panel_tokens]
                require(
                    panel_positions == sorted(panel_positions),
                    f"idea-gate capture must expose panel template, CAS writer, then alignment lint: {routed}",
                )
                rendered = subprocess.run(
                    [
                        sys.executable,
                        str(IDEA_CAMPAIGN),
                        "template",
                        "--kind",
                        "panel-design-review",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                require(
                    rendered.returncode == 0,
                    f"routed panel-template command must be executable: {rendered.stderr}",
                )
                require(
                    isinstance(json.loads(rendered.stdout), dict),
                    "routed panel-template command must print one JSON object",
                )

        write_committed_gate(base, campaign_path, lint_complete=False)
        for stage in ("idea_gate", "experiment_plan", "experiment"):
            routed = spec(stage, base, "launch_parallel_experiment" if stage == "experiment" else "")
            require(
                routed["skill"] == "autoreskill-gpu-idea-validation",
                f"{stage} must fail closed when the hash-bound lint is incomplete: {routed}",
            )
            require(routed["mcp_calls"] == [], f"torn later-stage gate must expose no PaperNexus call: {routed}")
            require(
                not any("claim-assignment" in command or "prepare-launch-intent" in command for command in routed["capture"]),
                f"torn later-stage gate must expose no launch mutation: {routed}",
            )
        committed_paths = write_committed_gate(base, campaign_path)

        launch = spec("experiment", base, "launch_parallel_experiment")
        launch_commands = "\n".join(launch["capture"])
        require("claim-assignment" in launch_commands, f"external GPU pilots need row-plus-pool claim: {launch}")
        require("resource_adapter.py" in launch_commands, f"external launch packet must include bounded adapter checks: {launch}")
        require("first deterministic" in launch["goal"], f"external packet must forbid stale batch preclaim: {launch}")
        ordered_tokens = [
            "normalize-for-row",
            "commit-resource-snapshot",
            "schedule --project",
            "claim-assignment",
            "baseline_clone_lint.py",
            "baseline_protocol_launch_lint.py",
            "launch-spec-digest",
            "record-backend-preflight",
            "budget-check",
            "prepare-launch-intent",
        ]
        positions = [launch_commands.index(token) for token in ordered_tokens]
        require(positions == sorted(positions), f"external capture chain must preserve authority order: {launch}")
        require("normalize-<" not in launch_commands, f"external capture must not expose an unexecutable route placeholder: {launch}")
        require("--launch-spec <absolute-launch-spec.json>" in launch_commands, f"intent must bind exact launch spec: {launch}")
        require(
            "--run-dir <project-root>/.autoreskill/coder/experiments/<track-id>/<experiment-id>" in launch_commands,
            f"intent must use canonical run directory: {launch}",
        )

        packet_path = goal_tick.write_job_packet(
            base,
            {"stage": "experiment", "goal": "fixture", "paperNexus": {"corpus": "fixture"}},
            {"job_id": "external-launch", "stage": "experiment", "action": "launch_parallel_experiment"},
            {"missing": []},
            None,
            "repair_queue.jsonl",
        )
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        require(packet["mcp_calls"] == [], f"external launch job packet must contain no PaperNexus calls: {packet}")
        require(
            any("Do not invoke PaperNexus" in item for item in packet["constraints"]),
            f"external job packet must carry source boundary: {packet}",
        )
        require(
            ".autoreskill/experiment/" in packet["allowed_writes"],
            f"atomic queue assignment must be inside the experiment job write scope: {packet}",
        )
        require(
            ".autoreskill/papernexus/" not in packet["allowed_writes"],
            f"external route must not grant PaperNexus writes: {packet}",
        )

        gate_path.unlink()
        campaign_path.unlink()
        legacy_launch = spec("experiment", base, "launch_parallel_experiment")
        legacy_commands = "\n".join(legacy_launch["capture"])
        require("claim-assignment" not in legacy_commands, f"legacy launch route must remain unchanged: {legacy_launch}")
        require("experiment_next_actions.py claim --project" in legacy_commands, f"legacy plain claim must remain: {legacy_launch}")

    print("PASS external material routing fixtures")


if __name__ == "__main__":
    main()
