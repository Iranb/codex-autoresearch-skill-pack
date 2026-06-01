#!/usr/bin/env python3
"""Lint the pre-idea evidence gate before experiment idea generation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


LANE_PACKETS = {
    "target_domain": "literature/TARGET_DOMAIN_DISCOVERY_PACKET.json",
    "near_neighbor": "literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
    "far_neighbor": "literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json",
}
REQUIRED_SLOT_FIELDS = ["challenge_clusters", "insight_clusters", "transfer_bridges", "anchor_nodes", "relation_patterns"]


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


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


def attempts_count(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    attempts = payload.get("attempts")
    if isinstance(attempts, list):
        return len([row for row in attempts if isinstance(row, dict)])
    if payload.get("discovery_attempted") is True:
        return 1
    return 0


def degraded_approval(gate: dict[str, Any]) -> tuple[bool, list[str]]:
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    missing: list[str] = []
    if not isinstance(approval, dict):
        return False, ["degraded_approval"]
    if approval.get("approved") is not True:
        missing.append("degraded_approval.approved=true")
    for key in ["approved_by", "approved_at", "reason"]:
        if not present(approval.get(key)):
            missing.append(f"degraded_approval.{key}")
    claim_limits = gate.get("claim_limits") or approval.get("claim_limits")
    if not present(claim_limits):
        missing.append("claim_limits")
    allowed = gate.get("allowed_next_action")
    if present(allowed) and str(allowed) not in {"generate_experiment_idea_pool_degraded", "generate_experiment_idea_pool"}:
        missing.append("allowed_next_action must permit degraded idea generation")
    return not missing, missing


def lint(project: str, allow_degraded: bool = False, write_gate: bool = False) -> dict[str, Any]:
    base = ar(project)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    gate_path = base / "ideation/PRE_IDEA_EVIDENCE_GATE.json"
    gate = read_json(gate_path)
    if not isinstance(gate, dict):
        if not write_gate:
            missing.append("ideation/PRE_IDEA_EVIDENCE_GATE.json")
        gate = {}

    status = str(gate.get("status") or "").strip().lower()
    approved_degraded = False
    degraded_missing: list[str] = []
    if status != "passed" and not write_gate:
        if allow_degraded and status == "degraded_requires_user_approval":
            approved_degraded, degraded_missing = degraded_approval(gate)
            if approved_degraded:
                warnings.append("pre-idea gate is degraded with explicit user approval; generated ideas must keep claim limits")
            else:
                missing.extend(degraded_missing)
        else:
            missing.append("PRE_IDEA_EVIDENCE_GATE.status=passed")

    if gate and gate.get("lane_attempts_satisfied") is not True:
        missing.append("PRE_IDEA_EVIDENCE_GATE.lane_attempts_satisfied=true")
    if gate and gate.get("screening_completed") is not True:
        missing.append("PRE_IDEA_EVIDENCE_GATE.screening_completed=true")
    if gate and not present(gate.get("innovation_slot_map_path")):
        missing.append("PRE_IDEA_EVIDENCE_GATE.innovation_slot_map_path")

    lane_details: dict[str, int] = {}
    for lane, rel in LANE_PACKETS.items():
        packet = read_json(base / rel)
        count = attempts_count(packet)
        lane_details[lane] = count
        if count < 1:
            missing.append(f"{rel} with at least one persisted attempt")
    details["lane_attempts"] = lane_details

    skill_root = Path(__file__).resolve().parents[2]
    paper_lint = run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-papernexus-innovation/scripts/paper_selection_scorecard_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
        ]
    )
    details["paper_selection_scorecard_lint"] = paper_lint
    if not paper_lint.get("complete"):
        for item in paper_lint.get("missing", []) if isinstance(paper_lint.get("missing"), list) else []:
            missing.append(f"paper_selection_scorecard_lint: {item}")
    for item in paper_lint.get("warnings", []) if isinstance(paper_lint.get("warnings"), list) else []:
        warnings.append(f"paper_selection_scorecard_lint: {item}")

    split_lint = run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-papernexus-innovation/scripts/split_reading_evidence_pack_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
        ]
    )
    details["split_reading_evidence_pack_lint"] = split_lint
    if not split_lint.get("complete"):
        for item in split_lint.get("missing", []) if isinstance(split_lint.get("missing"), list) else []:
            missing.append(f"split_reading_evidence_pack_lint: {item}")
    for item in split_lint.get("warnings", []) if isinstance(split_lint.get("warnings"), list) else []:
        warnings.append(f"split_reading_evidence_pack_lint: {item}")

    breadth_lint = run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-papernexus-innovation/scripts/pre_idea_breadth_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
        ]
    )
    details["pre_idea_breadth_lint"] = breadth_lint
    if not breadth_lint.get("complete"):
        for item in breadth_lint.get("missing", []) if isinstance(breadth_lint.get("missing"), list) else []:
            missing.append(f"pre_idea_breadth_lint: {item}")
    for item in breadth_lint.get("warnings", []) if isinstance(breadth_lint.get("warnings"), list) else []:
        warnings.append(f"pre_idea_breadth_lint: {item}")

    discovery_config_lint = run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-papernexus-innovation/scripts/pre_idea_discovery_config_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
        ]
    )
    details["pre_idea_discovery_config_lint"] = discovery_config_lint
    if not discovery_config_lint.get("complete"):
        for item in discovery_config_lint.get("missing", []) if isinstance(discovery_config_lint.get("missing"), list) else []:
            missing.append(f"pre_idea_discovery_config_lint: {item}")
    for item in discovery_config_lint.get("warnings", []) if isinstance(discovery_config_lint.get("warnings"), list) else []:
        warnings.append(f"pre_idea_discovery_config_lint: {item}")

    slot_path_raw = gate.get("innovation_slot_map_path") or "ideation/INNOVATION_SLOT_MAP.json"
    slot_path = Path(str(slot_path_raw)).expanduser()
    if not slot_path.is_absolute():
        if str(slot_path_raw).startswith(".autoreskill/"):
            slot_path = base.parent / slot_path
        else:
            slot_path = base / slot_path
    slot_map = read_json(slot_path)
    if not isinstance(slot_map, dict):
        missing.append("ideation/INNOVATION_SLOT_MAP.json")
    else:
        for field in REQUIRED_SLOT_FIELDS:
            if not present(slot_map.get(field)):
                missing.append(f"INNOVATION_SLOT_MAP.{field}")
        boundary = slot_map.get("evidence_boundary") or slot_map.get("evidence_boundaries")
        if not present(boundary):
            missing.append("INNOVATION_SLOT_MAP.evidence_boundary")
    details["innovation_slot_map_path"] = str(slot_path)

    degraded_reasons: list[str] = []
    if approved_degraded and missing:
        degraded_reasons = list(missing)
        warnings.extend(f"degraded pre-idea evidence: {item}" for item in degraded_reasons)
        missing = []

    complete = not missing
    if write_gate:
        synthesized = dict(gate)
        synthesized.update(
            {
                "schema_version": 1,
                "status": "passed" if complete else "blocked",
                "lane_attempts_satisfied": all(count >= 1 for count in lane_details.values()),
                "screening_completed": bool(paper_lint.get("complete")),
                "eligible_import_ratio": paper_lint.get("eligible_graph_or_material_ratio"),
                "lane_coverage": lane_details,
                "role_coverage": split_lint.get("role_counts"),
                "split_reading_status": split_lint.get("status"),
                "breadth_status": breadth_lint.get("status"),
                "breadth_summary": (breadth_lint.get("details") or {}).get("lane_counts"),
                "discovery_config_status": discovery_config_lint.get("status"),
                "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
                "blocking_reasons": missing,
                "allowed_next_action": "generate_experiment_idea_pool" if complete else "repair_pre_idea_evidence",
            }
        )
        write_json(gate_path, synthesized)

    return {
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(gate_path),
        "details": {**details, "degraded_approved": approved_degraded, "degraded_reasons": degraded_reasons},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--allow-degraded", action="store_true")
    parser.add_argument("--write-gate", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.allow_degraded, args.write_gate)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
