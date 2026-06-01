#!/usr/bin/env python3
"""Lint lane-aware pre-idea paper selection scorecards."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LANES = {"target_domain", "near_neighbor", "far_neighbor"}
SELECTED_DECISIONS = {"graph_import", "split_read_only"}
ELIGIBLE_DECISIONS = {"graph_import", "split_read_only", "watchlist"}
REJECT_DECISIONS = {
    "reject_duplicate",
    "reject_weak_relevance",
    "reject_unresolved_source",
    "reject_survey_noise",
    "reject_generic_benchmark",
    "reject_out_of_scope",
}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def resolve(base: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return base.parent / raw
    return base / path


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        return [row for row in payload["candidates"] if isinstance(row, dict)]
    return []


def lane_has_blocker(payload: dict[str, Any], lane: str) -> bool:
    blockers = payload.get("lane_blockers") or payload.get("expansion_blockers") or payload.get("blocking_reasons")
    if isinstance(blockers, dict):
        value = blockers.get(lane)
        return present(value)
    if isinstance(blockers, list):
        for item in blockers:
            if isinstance(item, dict) and str(item.get("lane") or "").strip() == lane and present(item.get("reason") or item.get("blocking_reason")):
                return True
            if isinstance(item, str) and lane in item:
                return True
    return False


def ratio_exception_approved(payload: dict[str, Any]) -> bool:
    approval = payload.get("ratio_exception_approval") or payload.get("manual_ratio_review")
    if isinstance(approval, dict):
        approved = approval.get("approved") is True
        reason = present(approval.get("reason") or approval.get("rationale"))
        approver = present(approval.get("approved_by") or approval.get("reviewer"))
        return approved and reason and approver
    return payload.get("ratio_exception_approved") is True and present(payload.get("ratio_exception_reason"))


def lint(project: str, scorecard_rel: str) -> dict[str, Any]:
    base = ar(project)
    path = resolve(base, scorecard_rel)
    payload = read_json(path)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": [scorecard_rel], "warnings": [], "path": str(path)}

    if payload.get("screening_completed") is not True:
        missing.append("screening_completed=true")
    if payload.get("discovery_attempted") is not True:
        missing.append("discovery_attempted=true")
    if payload.get("policy", {}).get("selection_denominator") != "high_signal_eligible_set":
        missing.append("policy.selection_denominator=high_signal_eligible_set")

    candidates = rows(payload)
    if not candidates:
        missing.append("candidates")

    lane_counts: dict[str, dict[str, int]] = {lane: {"raw": 0, "eligible": 0, "selected": 0} for lane in LANES}
    for index, row in enumerate(candidates):
        prefix = f"candidates[{index}]"
        lane = str(row.get("lane") or "").strip()
        decision = str(row.get("decision") or "").strip()
        if lane not in LANES:
            missing.append(f"{prefix}.lane target_domain/near_neighbor/far_neighbor")
            continue
        if decision not in ELIGIBLE_DECISIONS | REJECT_DECISIONS:
            missing.append(f"{prefix}.decision valid pre-idea decision")
        lane_counts[lane]["raw"] += 1
        if decision in ELIGIBLE_DECISIONS:
            lane_counts[lane]["eligible"] += 1
        if decision in SELECTED_DECISIONS:
            lane_counts[lane]["selected"] += 1
        flags = row.get("flags") if isinstance(row.get("flags"), dict) else {}
        if decision in SELECTED_DECISIONS:
            if flags.get("duplicate"):
                missing.append(f"{prefix} selected despite duplicate flag")
            if flags.get("source_resolvable") is False:
                missing.append(f"{prefix} selected without source resolution")
            if not present(row.get("roles")):
                missing.append(f"{prefix}.roles for selected paper")
        if decision == "graph_import" and flags.get("survey_noise") and "mechanism" not in set(row.get("roles") or []):
            missing.append(f"{prefix} graph_import survey without mechanism role")

    for lane, counts in sorted(lane_counts.items()):
        lane_blocked = lane_has_blocker(payload, lane)
        if counts["raw"] < 1:
            if lane_blocked:
                warnings.append(f"{lane} has no raw candidate but records an explicit blocker")
            else:
                missing.append(f"{lane} at least one raw candidate/search result")
        if counts["eligible"] < 1:
            if lane_blocked:
                warnings.append(f"{lane} has no eligible candidate but records an explicit blocker")
            else:
                missing.append(f"{lane} at least one eligible candidate or explicit expansion blocker")
    eligible_count = int(payload.get("eligible_candidate_count") or 0)
    selected_count = int(payload.get("graph_or_material_selected_count") or 0)
    ratio = payload.get("eligible_graph_or_material_ratio")
    if eligible_count <= 0:
        missing.append("eligible_candidate_count > 0")
    if selected_count <= 0:
        missing.append("graph_or_material_selected_count > 0")
    if isinstance(ratio, (int, float)):
        if ratio < 0.6 or ratio > 0.8:
            if ratio_exception_approved(payload):
                warnings.append(f"selected/eligible ratio {ratio:.2f} outside 0.60-0.80 with explicit approval")
            else:
                missing.append("selected/eligible ratio must be 0.60-0.80 unless ratio_exception_approval.approved=true with reason and approver")
    else:
        missing.append("eligible_graph_or_material_ratio")
    details["lane_counts"] = lane_counts

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(path),
        "candidate_count": len(candidates),
        "eligible_candidate_count": eligible_count,
        "graph_or_material_selected_count": selected_count,
        "eligible_graph_or_material_ratio": ratio,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--scorecard", default="papernexus/PAPER_SELECTION_SCORECARD.json")
    args = parser.parse_args()
    out = lint(args.project, args.scorecard)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
