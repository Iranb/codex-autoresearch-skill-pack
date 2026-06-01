#!/usr/bin/env python3
"""Create or check IDEA_TRACK_SEEDS from the idea pool and scorecard."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_SEED_FIELDS = [
    "track_id",
    "idea_id",
    "track_role",
    "one_variable_change",
    "expected_metric_effect",
    "baseline_pressure",
    "locked_or_missing_protocol_fields",
    "minimum_pilot",
    "ablation_required",
    "confirmation_required",
    "red_line_risks",
    "evidence_debt",
    "kill_condition",
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


def ideas_from_pool(pool: Any) -> list[dict[str, Any]]:
    if isinstance(pool, dict) and isinstance(pool.get("ideas"), list):
        return [row for row in pool["ideas"] if isinstance(row, dict)]
    return []


def rows_from_scorecard(scorecard: Any) -> list[dict[str, Any]]:
    if isinstance(scorecard, dict):
        for key in ["rows", "ideas", "scores", "scorecard"]:
            if isinstance(scorecard.get(key), list):
                return [row for row in scorecard[key] if isinstance(row, dict)]
    return []


def recommendation_ids(scorecard: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for key in ["top_track_recommendations", "top_recommendations"]:
        value = scorecard.get(key)
        if isinstance(value, list):
            for item in value:
                idea_id = item.get("idea_id") if isinstance(item, dict) else item
                if present(idea_id) and str(idea_id) not in out:
                    out.append(str(idea_id))
    ranked = sorted(
        rows,
        key=lambda row: (
            int(row.get("rank") or 9999) if str(row.get("rank") or "").isdigit() else 9999,
            int(row.get("paper_potential_rank") or 9999) if str(row.get("paper_potential_rank") or "").isdigit() else 9999,
        ),
    )
    for row in ranked:
        idea_id = row.get("id") or row.get("idea_id")
        if present(idea_id) and str(idea_id) not in out:
            decision = str(row.get("promotion_recommendation") or "").strip().lower()
            if decision in {"advance", "advance_with_constraints", "park"}:
                out.append(str(idea_id))
        if len(out) >= 4:
            break
    return out[:4]


def build_seed(idea: dict[str, Any], row: dict[str, Any], index: int, primary_id: str | None) -> dict[str, Any]:
    idea_id = str(idea.get("id"))
    track_spec = idea.get("track_seed_spec") if isinstance(idea.get("track_seed_spec"), dict) else {}
    paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
    role = "primary" if idea_id == primary_id or (primary_id is None and index == 0) else "alternate"
    if row.get("recommended_track_action") == "risk_repair":
        role = "risk_repair"
    return {
        "track_id": str(track_spec.get("track_id") or f"track-{index + 1:02d}-{idea_id}"),
        "idea_id": idea_id,
        "track_role": role,
        "one_variable_change": track_spec.get("one_variable_change") or idea.get("one_variable_change"),
        "expected_metric_effect": track_spec.get("expected_metric_effect") or idea.get("expected_metric_impact"),
        "baseline_pressure": track_spec.get("baseline_pressure") or paper.get("baseline_pressure") or row.get("closest_prior_pressure"),
        "locked_or_missing_protocol_fields": track_spec.get("locked_or_missing_protocol_fields") or idea.get("missing_materials") or ["baseline", "dataset", "metric", "eval_command"],
        "minimum_pilot": track_spec.get("minimum_pilot") or paper.get("minimum_experiment_table") or ["baseline", "proposed"],
        "ablation_required": True,
        "confirmation_required": True,
        "red_line_risks": track_spec.get("red_line_risks") or idea.get("red_line_audit") or row.get("reviewer_attack_surface") or [],
        "evidence_debt": track_spec.get("evidence_debt") or row.get("evidence_debt") or idea.get("missing_materials") or [],
        "kill_condition": track_spec.get("kill_condition") or idea.get("falsifier_probe") or paper.get("falsifier") or "No improvement under locked protocol.",
        "source_scorecard_row": row.get("id") or row.get("idea_id"),
        "launch_approval": False,
    }


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json", {})
    scorecard = read_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", {})
    ideas = {str(idea.get("id")): idea for idea in ideas_from_pool(pool) if present(idea.get("id"))}
    rows = rows_from_scorecard(scorecard)
    rows_by_id = {str(row.get("id") or row.get("idea_id")): row for row in rows if present(row.get("id") or row.get("idea_id"))}
    ids = recommendation_ids(scorecard if isinstance(scorecard, dict) else {}, rows)
    primary_id = None
    if isinstance(scorecard, dict):
        primary_id = scorecard.get("selected_primary_idea_id") or scorecard.get("selected_idea_id")
    if not present(primary_id) and isinstance(pool, dict):
        primary_id = pool.get("selected_idea_id")
    seeds = [
        build_seed(ideas[idea_id], rows_by_id.get(idea_id, {}), index, str(primary_id) if present(primary_id) else None)
        for index, idea_id in enumerate(ids)
        if idea_id in ideas
    ]
    return {
        "schema_version": 1,
        "generated_at": now(),
        "artifact": "IDEA_TRACK_SEEDS",
        "source_idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
        "source_scorecard_path": "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
        "selected_primary_idea_id": primary_id,
        "alternate_track_idea_ids": [seed["idea_id"] for seed in seeds if seed["track_role"] != "primary"],
        "track_selection_policy": "bounded_explore_exploit_seed_only_no_launch_approval",
        "tracks": seeds,
    }


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    payload = read_json(base / "ideation/IDEA_TRACK_SEEDS.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": ["ideation/IDEA_TRACK_SEEDS.json"], "warnings": []}
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        missing.append("tracks")
        tracks = []
    primary_count = 0
    for index, track in enumerate(row for row in tracks if isinstance(row, dict)):
        prefix = f"tracks[{index}]"
        for field in REQUIRED_SEED_FIELDS:
            if not present(track.get(field)):
                missing.append(f"{prefix}.{field}")
        if track.get("ablation_required") is not True:
            missing.append(f"{prefix}.ablation_required=true")
        if track.get("confirmation_required") is not True:
            missing.append(f"{prefix}.confirmation_required=true")
        if track.get("launch_approval") is True:
            missing.append(f"{prefix}.launch_approval must remain false at idea_gate")
        if str(track.get("track_role") or "") == "primary":
            primary_count += 1
    if primary_count != 1:
        missing.append("exactly one primary track")
    if len(tracks) < 3:
        warnings.append("prefer 3-4 track seeds for bounded exploration")
    return {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "warnings": warnings, "track_count": len(tracks)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        out = check(args.project)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        raise SystemExit(0 if out["complete"] else 1)
    payload = build(args.project)
    write_json(ar(args.project) / "ideation/IDEA_TRACK_SEEDS.json", payload)
    print(json.dumps({"ok": True, "path": "ideation/IDEA_TRACK_SEEDS.json", "track_count": len(payload["tracks"])}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
