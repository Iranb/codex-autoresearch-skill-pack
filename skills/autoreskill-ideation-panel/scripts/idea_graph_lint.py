#!/usr/bin/env python3
"""Lint Graph-of-Evidence projection and idea evidence closure."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOP_RECOMMENDATIONS = {"advance", "advance_with_constraints"}
GOE_IDEA_FIELDS = [
    "goe_path_refs",
    "closest_prior_delta",
    "mechanism_source_path",
    "negative_evidence_refs",
    "reviewer_attack_surface",
    "falsifier_probe",
    "track_seed_spec",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def degraded_gate_approved(base: Path) -> bool:
    gate = read_json(base / "ideation/PRE_IDEA_EVIDENCE_GATE.json", {})
    if not isinstance(gate, dict):
        return False
    if str(gate.get("status") or "").strip().lower() != "degraded_requires_user_approval":
        return False
    approval = gate.get("degraded_approval") or gate.get("user_approval") or gate.get("approval")
    return isinstance(approval, dict) and approval.get("approved") is True and present(gate.get("claim_limits") or approval.get("claim_limits"))


def rows_from_scorecard(scorecard: Any) -> list[dict[str, Any]]:
    if isinstance(scorecard, dict):
        for key in ["rows", "ideas", "scores", "scorecard"]:
            if isinstance(scorecard.get(key), list):
                return [row for row in scorecard[key] if isinstance(row, dict)]
    return []


def ideas_from_pool(pool: Any) -> list[dict[str, Any]]:
    if isinstance(pool, dict) and isinstance(pool.get("ideas"), list):
        return [row for row in pool["ideas"] if isinstance(row, dict)]
    return []


def selected_or_top_ids(pool: Any, scorecard: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(pool, dict):
        value = pool.get("selected_idea_id") or pool.get("selected_candidate_id")
        if present(value):
            ids.add(str(value))
        for idea in ideas_from_pool(pool):
            if str(idea.get("status") or "").strip().lower() == "selected" and present(idea.get("id")):
                ids.add(str(idea.get("id")))
    for row in rows_from_scorecard(scorecard):
        if str(row.get("promotion_recommendation") or "").strip().lower() in TOP_RECOMMENDATIONS and present(row.get("id") or row.get("idea_id")):
            ids.add(str(row.get("id") or row.get("idea_id")))
    if isinstance(scorecard, dict):
        for key in ["top_track_recommendations", "top_recommendations"]:
            value = scorecard.get(key)
            if isinstance(value, list):
                for item in value[:4]:
                    if isinstance(item, dict) and present(item.get("idea_id") or item.get("id")):
                        ids.add(str(item.get("idea_id") or item.get("id")))
                    elif present(item):
                        ids.add(str(item))
    return ids


def lint(project: str, projection_rel: str) -> dict[str, Any]:
    base = ar(project)
    projection_path = base / projection_rel
    projection = read_json(projection_path, {})
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json", {})
    scorecard = read_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", {})
    degraded = degraded_gate_approved(base)
    missing: list[str] = []
    warnings: list[str] = []
    node_counts: dict[str, int] = {}
    lanes = {"target_domain": 0, "near_neighbor": 0, "far_neighbor": 0}
    source_paths: list[str] = []

    if not isinstance(projection, dict):
        if degraded:
            warnings.append(f"{projection_rel} missing under approved degraded gate")
        else:
            missing.append(projection_rel)
        projection = {}
    else:
        source_paths = [str(path) for path in projection.get("source_paths", []) if present(path)]
        for node in projection.get("nodes", []) if isinstance(projection.get("nodes"), list) else []:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("type") or "")
            node_counts[node_type] = node_counts.get(node_type, 0) + 1
            lane = str(node.get("lane") or "")
            if lane in lanes and node_type == "paper":
                lanes[lane] += 1
        edge_types = set(projection.get("edge_type_set") or [])
        for edge_type in ["supports", "transfers_to", "anchors"]:
            if edge_type not in edge_types:
                warnings.append(f"edge_type_set missing {edge_type}")

    if not degraded:
        if lanes["target_domain"] < 1:
            missing.append("target-domain paper/closest-prior anchor")
        if lanes["near_neighbor"] < 1:
            missing.append("near-neighbor evidence lane")
        if lanes["far_neighbor"] < 1:
            missing.append("far-neighbor evidence lane")
        if node_counts.get("method_mechanism", 0) + node_counts.get("transfer_bridge", 0) + node_counts.get("proposal_node", 0) < 3:
            missing.append("at least 3 candidate mechanism/transfer/proposal nodes")
        if node_counts.get("negative_evidence", 0) + node_counts.get("limitation", 0) < 1:
            missing.append("negative evidence or limitation node")
        if node_counts.get("protocol", 0) + node_counts.get("metric", 0) < 1:
            missing.append("baseline/protocol/dataset/metric node")

    top_ids = selected_or_top_ids(pool, scorecard)
    idea_by_id = {str(idea.get("id")): idea for idea in ideas_from_pool(pool) if present(idea.get("id"))}
    for idea_id in sorted(top_ids & set(idea_by_id)):
        idea = idea_by_id[idea_id]
        maturity = str(idea.get("evidence_maturity") or "").strip().lower()
        low_maturity = maturity in {"blue_sky", "promising"} or degraded
        for field in GOE_IDEA_FIELDS:
            if not present(idea.get(field)):
                target = warnings if low_maturity else missing
                target.append(f"ideas[{idea_id}].{field}")

    audit = {
        "schema_version": 1,
        "generated_at": now(),
        "status": "passed" if not missing else "blocked",
        "projection_path": projection_rel,
        "source_paths": source_paths,
        "node_counts": node_counts,
        "lane_paper_counts": lanes,
        "top_or_selected_idea_ids": sorted(top_ids),
        "missing": missing,
        "warnings": warnings,
        "recommended_repair_action": "proceed" if not missing else "repair_graph_evidence_or_mark_approved_degraded_boundary",
    }
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(projection_path),
        "audit": audit,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--projection", default="ideation/EVIDENCE_GRAPH_PROJECTION.json")
    parser.add_argument("--write-audit", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.projection)
    if args.write_audit:
        write_json(ar(args.project) / "ideation/GOE_IDEA_AUDIT.json", out["audit"])
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
