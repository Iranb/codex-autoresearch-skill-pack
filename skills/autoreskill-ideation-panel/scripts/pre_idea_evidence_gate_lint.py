#!/usr/bin/env python3
"""Lint the pre-idea evidence gate before experiment idea generation."""

from __future__ import annotations

import argparse
import hashlib
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
EVIDENCE_SOURCE_MODES = {"papernexus", "external_material"}


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


def evidence_source_mode(gate: dict[str, Any]) -> str:
    """Return the explicit source mode; old gates remain PaperNexus gates."""
    return str(gate.get("evidence_source_mode") or "papernexus").strip().lower()


def resolve_ref(base: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return base.parent / path
    return base / path


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_candidate_ids(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in {
                "external_candidate_id",
                "candidate_id",
                "admitted_candidate_id",
                "admitted_candidate_ids",
            }:
                if isinstance(item, list):
                    out.update(str(row).strip() for row in item if present(row))
                elif present(item):
                    out.add(str(item).strip())
            out.update(collect_candidate_ids(item))
    elif isinstance(value, list):
        for item in value:
            out.update(collect_candidate_ids(item))
    return out


def collect_named_values(value: Any, target_key: str) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized == target_key:
                if isinstance(item, list):
                    out.update(str(row).strip() for row in item if present(row))
                elif present(item):
                    out.add(str(item).strip())
            out.update(collect_named_values(item, target_key))
    elif isinstance(value, list):
        for item in value:
            out.update(collect_named_values(item, target_key))
    return out


def append_child_result(name: str, out: dict[str, Any], missing: list[str], warnings: list[str]) -> None:
    if not out.get("complete"):
        items = out.get("missing") if isinstance(out.get("missing"), list) else []
        if items:
            missing.extend(f"{name}: {item}" for item in items)
        else:
            missing.append(f"{name} failed without structured missing output")
    items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
    warnings.extend(f"{name}: {item}" for item in items)


def lint_external_gate(
    project: str,
    base: Path,
    gate: dict[str, Any],
    missing: list[str],
    warnings: list[str],
    details: dict[str, Any],
) -> None:
    """Validate the committed external-material gate without invoking PaperNexus."""
    required_true = ["lane_attempts_satisfied", "screening_completed"]
    for key in required_true:
        if gate.get(key) is not True:
            missing.append(f"PRE_IDEA_EVIDENCE_GATE.{key}=true")
    for key in [
        "innovation_slot_map_path",
        "campaign_ref",
        "campaign_sha256",
        "lint_ref",
        "lint_sha256",
        "slot_map_sha256",
    ]:
        if not present(gate.get(key)):
            missing.append(f"PRE_IDEA_EVIDENCE_GATE.{key}")
    if str(gate.get("status") or "").strip().lower() != "passed":
        missing.append("PRE_IDEA_EVIDENCE_GATE.status=passed")
    if str(gate.get("allowed_next_action") or "").strip() != "generate_experiment_idea_pool":
        missing.append("PRE_IDEA_EVIDENCE_GATE.allowed_next_action=generate_experiment_idea_pool")

    refs = {
        "campaign": ("campaign_ref", "campaign_sha256"),
        "lint": ("lint_ref", "lint_sha256"),
        "slot_map": ("innovation_slot_map_path", "slot_map_sha256"),
    }
    payloads: dict[str, Any] = {}
    for name, (ref_key, hash_key) in refs.items():
        path = resolve_ref(base, gate.get(ref_key))
        digest = sha256_file(path)
        details[f"{name}_path"] = str(path) if path else None
        details[f"{name}_sha256"] = digest
        if digest is None:
            missing.append(f"PRE_IDEA_EVIDENCE_GATE.{ref_key} target")
            continue
        if digest != str(gate.get(hash_key) or "").strip().lower():
            missing.append(f"PRE_IDEA_EVIDENCE_GATE.{hash_key} must match current {ref_key}")
        payloads[name] = read_json(path) if path else None

    lint_payload = payloads.get("lint")
    if not isinstance(lint_payload, dict) or lint_payload.get("complete") is not True:
        missing.append("external campaign lint record complete=true")
    campaign = payloads.get("campaign")
    if not isinstance(campaign, dict):
        missing.append("external campaign must be valid JSON")
    elif campaign.get("papernexus_used") is not False:
        missing.append("external campaign papernexus_used=false")

    skill_root = Path(__file__).resolve().parents[2]
    checker = skill_root / "autoreskill-gpu-idea-validation/scripts/idea_campaign.py"
    if not checker.is_file():
        checker_out = {
            "complete": False,
            "missing": ["autoreskill-gpu-idea-validation/scripts/idea_campaign.py"],
            "warnings": [],
            "returncode": 1,
        }
    else:
        checker_out = run_json(
            [sys.executable, str(checker), "check", "--project", str(Path(project).expanduser().resolve())]
        )
    details["external_campaign_check"] = checker_out
    append_child_result("external_campaign_check", checker_out, missing, warnings)

    gate_check = run_json(
        [
            sys.executable,
            str(checker),
            "verify-gate",
            "--project",
            str(Path(project).expanduser().resolve()),
        ]
    ) if checker.is_file() else {
        "complete": False,
        "missing": ["autoreskill-gpu-idea-validation/scripts/idea_campaign.py"],
        "warnings": [],
        "returncode": 1,
    }
    details["external_gate_check"] = gate_check
    append_child_result("external_gate_check", gate_check, missing, warnings)

    # The deterministic checker owns campaign admission semantics.  This local
    # comparison catches a torn materialization when both derived artifacts
    # expose candidate identities.
    campaign_ids = collect_candidate_ids(campaign)
    lint_ids = collect_named_values(lint_payload, "admitted_candidate_ids") or collect_candidate_ids(lint_payload)
    slot_ids = collect_candidate_ids(payloads.get("slot_map"))
    checker_ids = {
        str(item).strip()
        for item in checker_out.get("admitted_candidate_ids", [])
        if present(item)
    }
    details["external_candidate_ids"] = {
        "campaign": sorted(campaign_ids),
        "lint": sorted(lint_ids),
        "slot_map": sorted(slot_ids),
        "checker": sorted(checker_ids),
    }
    if campaign_ids and lint_ids and not lint_ids.issubset(campaign_ids):
        missing.append("external lint candidate IDs must exist in the current campaign")
    if slot_ids and campaign_ids and not slot_ids.issubset(campaign_ids):
        missing.append("external slot-map candidate IDs must exist in the current campaign")
    if checker_ids and lint_ids and checker_ids != lint_ids:
        missing.append("external lint admitted candidate IDs must match current campaign checker")
    if checker_ids and slot_ids and not slot_ids.issubset(checker_ids):
        missing.append("external slot-map candidate IDs must be admitted by current campaign checker")


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

    mode = evidence_source_mode(gate)
    details["evidence_source_mode"] = mode
    if mode not in EVIDENCE_SOURCE_MODES:
        missing.append(
            "PRE_IDEA_EVIDENCE_GATE.evidence_source_mode must be papernexus or external_material"
        )
        return {
            "complete": False,
            "status": "incomplete",
            "missing": missing,
            "warnings": warnings,
            "path": str(gate_path),
            "details": details,
        }
    if mode == "external_material":
        if allow_degraded and str(gate.get("status") or "").strip().lower() == "degraded_requires_user_approval":
            missing.append("external_material evidence cannot use approved_degraded readiness")
        if write_gate:
            warnings.append("external-material gates are committed by idea_campaign.py materialize; --write-gate is read-only here")
        lint_external_gate(project, base, gate, missing, warnings, details)
        slot_path = resolve_ref(base, gate.get("innovation_slot_map_path"))
        slot_map = read_json(slot_path) if slot_path else None
        if not isinstance(slot_map, dict):
            missing.append("ideation/INNOVATION_SLOT_MAP.json")
        else:
            for field in REQUIRED_SLOT_FIELDS:
                if not present(slot_map.get(field)):
                    missing.append(f"INNOVATION_SLOT_MAP.{field}")
            boundary = slot_map.get("evidence_boundary") or slot_map.get("evidence_boundaries")
            if not present(boundary):
                missing.append("INNOVATION_SLOT_MAP.evidence_boundary")
        return {
            "complete": not missing,
            "status": "complete" if not missing else "incomplete",
            "missing": missing,
            "warnings": warnings,
            "path": str(gate_path),
            "details": details,
        }

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
    abstract_lint = run_json(
        [
            sys.executable,
            str(skill_root / "autoreskill-papernexus-innovation/scripts/abstract_screening_audit_lint.py"),
            "--project",
            str(Path(project).expanduser().resolve()),
        ]
    )
    details["abstract_screening_audit_lint"] = abstract_lint
    if not abstract_lint.get("complete"):
        for item in abstract_lint.get("missing", []) if isinstance(abstract_lint.get("missing"), list) else []:
            missing.append(f"abstract_screening_audit_lint: {item}")
    for item in abstract_lint.get("warnings", []) if isinstance(abstract_lint.get("warnings"), list) else []:
        warnings.append(f"abstract_screening_audit_lint: {item}")

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
                "evidence_source_mode": "papernexus",
                "status": "passed" if complete else "blocked",
                "lane_attempts_satisfied": all(count >= 1 for count in lane_details.values()),
                "screening_completed": bool(paper_lint.get("complete")) and bool(abstract_lint.get("complete")),
                "abstract_screening_audit_path": "papernexus/ABSTRACT_SCREENING_AUDIT.json",
                "abstract_screening_status": abstract_lint.get("status"),
                "abstract_screening_row_count": abstract_lint.get("row_count"),
                "abstract_screening_expected_count": abstract_lint.get("expected_candidate_count"),
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
