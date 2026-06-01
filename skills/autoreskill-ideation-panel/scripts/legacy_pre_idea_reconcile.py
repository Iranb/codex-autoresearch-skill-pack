#!/usr/bin/env python3
"""Create a reconciliation report for legacy idea pools without a pre-idea gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALTERNATE_GATE_RELS = [
    "orchestrator/PRE_IDEA_EVIDENCE_GATE.json",
    "planner/PRE_IDEA_EVIDENCE_GATE.json",
    "PRE_IDEA_EVIDENCE_GATE.json",
]
REPAIR_REQUIRED = {"legacy_requires_evidence_reconciliation", "pre_idea_gate_misplaced"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_json(path: Path, data: Any, force: bool = True) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def idea_count(pool: Any) -> int:
    if isinstance(pool, dict):
        for key in ["ideas", "candidates"]:
            if isinstance(pool.get(key), list):
                return len(pool[key])
    return 0


def alternate_gates(base: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in ALTERNATE_GATE_RELS:
        payload = read_json(base / rel)
        if isinstance(payload, dict) and str(payload.get("status") or "").strip():
            rows.append({"path": rel, "status": payload.get("status"), "schema_version": payload.get("schema_version")})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-blocked-gate", action="store_true")
    args = parser.parse_args()

    base = ar(args.project)
    pool_path = base / "ideation/EXPERIMENT_IDEA_POOL.json"
    gate_path = base / "ideation/PRE_IDEA_EVIDENCE_GATE.json"
    report_path = base / "ideation/LEGACY_PRE_IDEA_RECONCILIATION.json"
    pool = read_json(pool_path)
    gate = read_json(gate_path)
    misplaced_gates = alternate_gates(base)
    count = idea_count(pool)
    has_gate = isinstance(gate, dict) and str(gate.get("status") or "").strip()

    if count <= 0:
        report = {
            "schema_version": 1,
            "created_at": now(),
            "status": "no_legacy_idea_pool",
            "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
            "idea_count": 0,
            "next_action": "run_pre_idea_evidence_expansion_before_ideation",
        }
    elif has_gate:
        report = {
            "schema_version": 1,
            "created_at": now(),
            "status": "pre_idea_gate_already_present",
            "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
            "pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
            "gate_status": gate.get("status"),
            "idea_count": count,
            "next_action": "run_pre_idea_evidence_gate_lint",
        }
    elif misplaced_gates:
        report = {
            "schema_version": 1,
            "created_at": now(),
            "status": "pre_idea_gate_misplaced",
            "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
            "idea_count": count,
            "reason": "idea pool exists with PRE_IDEA_EVIDENCE_GATE outside the canonical ideation path",
            "canonical_pre_idea_evidence_gate_path": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
            "found_gate_paths": misplaced_gates,
            "preserve_existing_idea_pool": True,
            "do_not_overwrite": [
                "ideation/EXPERIMENT_IDEA_POOL.json",
                "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
                *[row["path"] for row in misplaced_gates],
            ],
            "required_repair_artifacts": [
                "ideation/PRE_IDEA_EVIDENCE_GATE.json",
                "literature/PRE_IDEA_DISCOVERY_PLAN.json",
                "literature/TARGET_DOMAIN_DISCOVERY_PACKET.json",
                "literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
                "literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json",
                "papernexus/PAPER_SELECTION_SCORECARD.json",
                "papernexus/SPLIT_READING_EVIDENCE_PACK.json",
                "ideation/INNOVATION_SLOT_MAP.json",
            ],
            "next_action": "inspect_misplaced_gate_then_rebuild_or_relocate_canonical_pre_idea_gate",
        }
        if args.write_blocked_gate and not args.dry_run:
            write_json(
                gate_path,
                {
                    "schema_version": 1,
                    "created_at": now(),
                    "status": "blocked",
                    "lane_attempts_satisfied": False,
                    "screening_completed": False,
                    "eligible_import_ratio": None,
                    "lane_coverage": {},
                    "role_coverage": {},
                    "split_reading_status": "missing",
                    "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
                    "blocking_reasons": ["pre-idea evidence gate exists outside canonical ideation path"],
                    "allowed_next_action": "repair_pre_idea_gate_location_and_evidence",
                    "misplaced_gate_paths": misplaced_gates,
                    "legacy_reconciliation_path": "ideation/LEGACY_PRE_IDEA_RECONCILIATION.json",
                },
                force=True,
            )
    else:
        report = {
            "schema_version": 1,
            "created_at": now(),
            "status": "legacy_requires_evidence_reconciliation",
            "idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
            "idea_count": count,
            "reason": "idea pool exists without PRE_IDEA_EVIDENCE_GATE.json",
            "preserve_existing_idea_pool": True,
            "do_not_overwrite": ["ideation/EXPERIMENT_IDEA_POOL.json", "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json"],
            "required_repair_artifacts": [
                "literature/PRE_IDEA_DISCOVERY_PLAN.json",
                "literature/TARGET_DOMAIN_DISCOVERY_PACKET.json",
                "literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
                "literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json",
                "papernexus/PAPER_SELECTION_SCORECARD.json",
                "papernexus/SPLIT_READING_EVIDENCE_PACK.json",
                "ideation/INNOVATION_SLOT_MAP.json",
                "ideation/PRE_IDEA_EVIDENCE_GATE.json",
            ],
            "next_action": "run_pre_idea_evidence_expansion_then_re_score_or_regenerate_ideas",
        }
        if args.write_blocked_gate and not args.dry_run:
            write_json(
                gate_path,
                {
                    "schema_version": 1,
                    "created_at": now(),
                    "status": "blocked",
                    "lane_attempts_satisfied": False,
                    "screening_completed": False,
                    "eligible_import_ratio": None,
                    "lane_coverage": {},
                    "role_coverage": {},
                    "split_reading_status": "missing",
                    "innovation_slot_map_path": "ideation/INNOVATION_SLOT_MAP.json",
                    "blocking_reasons": ["legacy idea pool exists without pre-idea evidence gate"],
                    "allowed_next_action": "repair_pre_idea_evidence",
                    "legacy_reconciliation_path": "ideation/LEGACY_PRE_IDEA_RECONCILIATION.json",
                },
                force=True,
            )

    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "path": str(report_path), "status": report["status"], "idea_count": count, "report": report}, indent=2, ensure_ascii=False))
        raise SystemExit(1 if report["status"] in REPAIR_REQUIRED else 0)

    if report_path.exists() and not args.force:
        raise SystemExit(f"{report_path} already exists; pass --force to overwrite")
    write_json(report_path, report, force=True)
    print(json.dumps({"ok": True, "path": str(report_path), "status": report["status"], "idea_count": count}, indent=2, ensure_ascii=False))
    raise SystemExit(1 if report["status"] in REPAIR_REQUIRED else 0)


if __name__ == "__main__":
    main()
