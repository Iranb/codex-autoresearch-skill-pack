#!/usr/bin/env python3
"""Lint cross-lane literature breadth before ideation.

This is intentionally venue-agnostic. A paper workflow should not pass the
pre-idea gate merely because each discovery lane has one attempt; target-domain,
near-neighbor, and far-neighbor lanes must all have enough screened candidates
to support novelty construction.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LANE_PACKETS = {
    "target_domain": "literature/TARGET_DOMAIN_DISCOVERY_PACKET.json",
    "near_neighbor": "literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
    "far_neighbor": "literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json",
}
LANE_THRESHOLDS = {
    "target_domain": {"raw": 10, "eligible": 6, "selected": 4},
    "near_neighbor": {"raw": 12, "eligible": 8, "selected": 5},
    "far_neighbor": {"raw": 10, "eligible": 7, "selected": 4},
}
SELECTED_DECISIONS = {"graph_import", "split_read_only"}
ELIGIBLE_DECISIONS = {"graph_import", "split_read_only", "watchlist"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


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
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def attempts_count(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    attempts = payload.get("attempts")
    if isinstance(attempts, list):
        return len([row for row in attempts if isinstance(row, dict)])
    if payload.get("discovery_attempted") is True:
        return 1
    return 0


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        return [row for row in payload["candidates"] if isinstance(row, dict)]
    return []


def approved_exception(payload: dict[str, Any]) -> bool:
    approval = payload.get("breadth_exception_approval") or payload.get("manual_breadth_review")
    if not isinstance(approval, dict):
        return False
    return (
        approval.get("approved") is True
        and present(approval.get("reason") or approval.get("rationale"))
        and present(approval.get("approved_by") or approval.get("reviewer"))
    )


def lane_counts(candidates: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary = {
        lane: {"raw": 0, "eligible": 0, "selected": 0, "watchlist": 0, "rejected": 0}
        for lane in LANE_THRESHOLDS
    }
    for row in candidates:
        lane = str(row.get("lane") or "").strip()
        decision = str(row.get("decision") or "").strip()
        if lane not in summary:
            continue
        summary[lane]["raw"] += 1
        if decision in ELIGIBLE_DECISIONS:
            summary[lane]["eligible"] += 1
        if decision in SELECTED_DECISIONS:
            summary[lane]["selected"] += 1
        if decision == "watchlist":
            summary[lane]["watchlist"] += 1
        if decision.startswith("reject"):
            summary[lane]["rejected"] += 1
    return summary


def lint(project: str, scorecard_rel: str = "papernexus/PAPER_SELECTION_SCORECARD.json") -> dict[str, Any]:
    base = ar(project)
    scorecard_path = base / scorecard_rel
    scorecard = read_json(scorecard_path)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"thresholds": LANE_THRESHOLDS}

    if not isinstance(scorecard, dict):
        return {
            "complete": False,
            "status": "incomplete",
            "missing": [scorecard_rel],
            "warnings": [],
            "path": str(scorecard_path),
        }

    candidates = rows(scorecard)
    counts = lane_counts(candidates)
    lane_attempts: dict[str, int] = {}
    for lane, rel in LANE_PACKETS.items():
        packet = read_json(base / rel)
        lane_attempts[lane] = attempts_count(packet)
        if lane_attempts[lane] < 1:
            missing.append(f"{rel} with at least one persisted discovery attempt")
    details["lane_attempts"] = lane_attempts
    details["lane_counts"] = counts

    for lane, threshold in LANE_THRESHOLDS.items():
        current = counts[lane]
        for key, minimum in threshold.items():
            if current[key] < minimum:
                missing.append(f"{lane} {key}_candidate_count >= {minimum} (found {current[key]})")

    total_eligible = sum(item["eligible"] for item in counts.values())
    total_selected = sum(item["selected"] for item in counts.values())
    if total_eligible < 21:
        missing.append(f"total eligible current/near/far candidates >= 21 (found {total_eligible})")
    if total_selected < 13:
        missing.append(f"total graph_import/split_read selected candidates >= 13 (found {total_selected})")

    if missing and approved_exception(scorecard):
        warnings.extend(f"breadth exception approved: {item}" for item in missing)
        missing = []

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(scorecard_path),
        "details": details,
        "eligible_total": total_eligible,
        "selected_total": total_selected,
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
