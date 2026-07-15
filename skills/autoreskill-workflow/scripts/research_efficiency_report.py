#!/usr/bin/env python3
"""Record and report evidence-only AutoResearch decision-throughput metrics."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
QUEUE_HELPER = HERE / "experiment_next_actions.py"
OBS_REL = Path(".autoreskill/metrics/THROUGHPUT_OBSERVATIONS.jsonl")
REPORT_REL = Path(".autoreskill/metrics/RESEARCH_EFFICIENCY_REPORT.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def load_queue_helper() -> Any:
    spec = importlib.util.spec_from_file_location("autoreskill_efficiency_queue", QUEUE_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {QUEUE_HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_observations(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def append_observation(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def accepted_entries(project: Path) -> list[dict[str, Any]]:
    ledger = read_json(project / ".autoreskill/coder/EXPERIMENT_LEDGER.json")
    return [
        item
        for item in ledger.get("entries", [])
        if isinstance(item, dict) and str(item.get("scientific_outcome_status") or "") == "accepted"
    ]


def observe_project(project: Path, force: bool = False) -> dict[str, Any]:
    helper = load_queue_helper()
    queue = helper.load_queue(project)
    if not queue:
        raise RuntimeError(f"queue missing for {project}")
    matrix = read_json(project / ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json")
    frontier = helper.frontier_status(queue, matrix=matrix, project=project)
    schedule = helper.select_launch_batch(queue, project)
    rows = [item for item in queue.get("rows", []) if isinstance(item, dict)]
    launch_count = sum(
        1 for item in rows if str(item.get("status") or "") in {"planned", "submitting", "needs_sync", "running"}
    )
    state = {
        "queue_revision": queue.get("queue_revision"),
        "selection_revision": frontier.get("selection_revision"),
        "program_contract_status": frontier.get("program_contract_status"),
        "program_contract_enforcement_mode": frontier.get("program_contract_enforcement_mode"),
        "program_claim_contract_sha256": frontier.get("program_claim_contract_sha256"),
        "program_scientific_status": frontier.get("program_scientific_status"),
        "active_nonterminal_track_count": frontier.get("active_nonterminal_track_count"),
        "method_portfolio_target": frontier.get("method_portfolio_target"),
        "active_method_candidate_count": frontier.get("active_method_candidate_count"),
        "method_portfolio_deficit": frontier.get("method_portfolio_deficit"),
        "diagnostic_active_track_count": frontier.get("diagnostic_active_track_count"),
        "portfolio_admission_deficit": frontier.get("portfolio_admission_deficit"),
        "portfolio_fillable_count": frontier.get("portfolio_fillable_count"),
        "portfolio_fillable_candidate_ids": frontier.get("portfolio_fillable_candidate_ids") or [],
        "launch_frontier_supply_count": frontier.get("launch_frontier_supply_count"),
        "launch_frontier_deficit": frontier.get("launch_frontier_deficit"),
        "fitting_assignment_count": len(schedule.get("assignments") or []),
        "fitting_row_ids": schedule.get("selected_row_ids") or [],
        "active_launch_count": launch_count,
        "parameter_profile_status_by_track": frontier.get("parameter_profile_status_by_track") or {},
        "parameter_coverage_deficit_by_track_and_dataset": frontier.get("parameter_coverage_deficit_by_track_and_dataset") or {},
        "seed_only_parameter_substitution_rejected_count": frontier.get("seed_only_substitution_rejected_count"),
        "dataset_coverage_deficit_by_track": frontier.get("dataset_coverage_deficit_by_track") or {},
        "paired_group_incomplete_count": frontier.get("paired_group_incomplete_count"),
        "paired_group_missing_dataset_legs": frontier.get("paired_group_missing_dataset_legs") or {},
        "cross_dataset_full_budget_ready_count": frontier.get("cross_dataset_full_budget_ready_count"),
        "robust_hpo_ready_count": frontier.get("robust_hpo_ready_count"),
        "accepted_scientific_outcome_count": len(accepted_entries(project)),
    }
    observation = {
        "schema_version": 1,
        "observed_at": now_iso(),
        "project_root": str(project),
        **state,
    }
    observation["state_signature"] = canonical_sha256(state)
    path = project / OBS_REL
    prior = read_observations(path)
    changed = not prior or prior[-1].get("state_signature") != observation["state_signature"]
    if changed or force:
        append_observation(path, observation)
    return {
        "ok": True,
        "project": str(project),
        "observation_path": str(path),
        "appended": bool(changed or force),
        "observation": observation,
    }


def shortlist_ids(helper: Any, project: Path) -> set[str]:
    base = project / ".autoreskill"
    scorecard = read_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json")
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json")
    selected = set(helper.shortlist_ids(scorecard))
    if selected:
        return selected
    return {
        str(item.get("id") or item.get("idea_id"))
        for item in helper.idea_pool_rows(pool)
        if isinstance(item, dict) and item.get("shortlisted") is True and str(item.get("id") or item.get("idea_id") or "")
    }


def valid_pilot_ids(helper: Any, project: Path) -> tuple[set[str], list[dict[str, Any]]]:
    queue = helper.load_queue(project)
    rows = {
        str(item.get("id") or ""): item
        for item in queue.get("rows", [])
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    accepted = accepted_entries(project)
    valid: set[str] = set()
    qualifying: list[dict[str, Any]] = []
    for entry in accepted:
        row = rows.get(str(entry.get("queue_row_id") or ""), {})
        stage = entry.get("validation_stage", row.get("validation_stage"))
        try:
            stage_number = int(stage)
        except (TypeError, ValueError):
            continue
        outcome = str(entry.get("outcome_class") or "")
        if stage_number < 2 or not outcome.startswith("valid_"):
            continue
        idea_id = str(entry.get("selected_idea_id") or row.get("selected_idea_id") or "")
        if idea_id:
            valid.add(idea_id)
        qualifying.append(entry)
    return valid, qualifying


def first_discriminator_metric(helper: Any, project: Path) -> dict[str, Any]:
    seeds = read_json(project / ".autoreskill/ideation/IDEA_TRACK_SEEDS.json")
    admissions: dict[str, datetime] = {}
    for track in seeds.get("tracks", []):
        if not isinstance(track, dict):
            continue
        admitted = parse_time(track.get("admitted_at"))
        if admitted is not None:
            for key in [track.get("track_id"), track.get("idea_id")]:
                if str(key or ""):
                    admissions[str(key)] = admitted
    _, qualifying = valid_pilot_ids(helper, project)
    elapsed: list[float] = []
    covered_tracks: set[str] = set()
    outcome_tracks: set[str] = set()
    for entry in qualifying:
        track_id = str(entry.get("track_id") or entry.get("selected_idea_id") or "")
        if track_id:
            outcome_tracks.add(track_id)
        admitted = admissions.get(str(entry.get("track_id") or "")) or admissions.get(str(entry.get("selected_idea_id") or ""))
        outcome_path = project / ".autoreskill" / str(entry.get("scientific_outcome_ref") or "")
        outcome = read_json(outcome_path)
        completed = parse_time(outcome.get("updated_at") or outcome.get("created_at") or entry.get("updated_at"))
        if admitted is None or completed is None or completed < admitted:
            continue
        elapsed.append((completed - admitted).total_seconds() / 3600.0)
        if track_id:
            covered_tracks.add(track_id)
    return {
        "unit": "hours",
        "values": sorted(round(value, 6) for value in elapsed),
        "median": round(statistics.median(elapsed), 6) if elapsed else None,
        "covered_outcome_tracks": len(covered_tracks),
        "eligible_outcome_tracks": len(outcome_tracks),
        "coverage": (len(covered_tracks) / len(outcome_tracks)) if outcome_tracks else None,
        "unknown_reason": None if elapsed else "admission or protocol-valid outcome timestamp unavailable",
    }


def gpu_hours_and_decisions(project: Path) -> dict[str, Any]:
    terminal_runs = 0
    covered_runs = 0
    gpu_hours = 0.0
    for path in sorted((project / ".autoreskill/coder/experiments").glob("*/REMOTE_RUN.json")):
        run = read_json(path)
        if str(run.get("status") or "") not in {"completed", "failed", "cancelled", "canceled", "timeout", "timed_out", "budget_stopped"}:
            continue
        terminal_runs += 1
        usage = run.get("resource_usage") if isinstance(run.get("resource_usage"), dict) else {}
        actual = finite_nonnegative(run.get("actual_gpu_hours"))
        if actual is None:
            actual = finite_nonnegative(usage.get("actual_gpu_hours"))
        if actual is not None:
            covered_runs += 1
            gpu_hours += actual
    decisions: set[str] = set()
    classes: dict[str, int] = {}
    for index, entry in enumerate(accepted_entries(project)):
        outcome = str(entry.get("outcome_class") or "")
        transition = str(entry.get("research_transition") or "")
        if not outcome.startswith("valid_") and not transition:
            continue
        decision_id = str(entry.get("scientific_decision_id") or f"entry:{entry.get('run_id') or index}")
        decisions.add(decision_id)
        label = transition or outcome
        classes[label] = classes.get(label, 0) + 1
    metric_ready = bool(decisions) and terminal_runs > 0 and covered_runs == terminal_runs
    if not decisions:
        unknown_reason = "accepted scientific decisions unavailable"
    elif terminal_runs == 0:
        unknown_reason = "no terminal run accounting evidence"
    elif covered_runs != terminal_runs:
        unknown_reason = "actual GPU-hours coverage incomplete"
    else:
        unknown_reason = None
    return {
        "actual_gpu_hours": round(gpu_hours, 6),
        "decision_count": len(decisions),
        "value": round(gpu_hours / len(decisions), 6) if metric_ready else None,
        "runtime_coverage": (covered_runs / terminal_runs) if terminal_runs else None,
        "covered_terminal_runs": covered_runs,
        "terminal_runs": terminal_runs,
        "decision_classes": classes,
        "unknown_reason": unknown_reason,
    }


def starvation_metric(observations: list[dict[str, Any]]) -> dict[str, Any]:
    supply_denominator = supply_starved = 0.0
    placement_denominator = placement_starved = 0.0
    for before, after in zip(observations, observations[1:]):
        start = parse_time(before.get("observed_at"))
        end = parse_time(after.get("observed_at"))
        if start is None or end is None or end <= start:
            continue
        seconds = (end - start).total_seconds()
        supply_opportunity = int(before.get("portfolio_admission_deficit") or 0) > 0 and int(before.get("portfolio_fillable_count") or 0) > 0
        placement_opportunity = int(before.get("fitting_assignment_count") or 0) > 0
        if supply_opportunity:
            supply_denominator += seconds
            if int(after.get("active_nonterminal_track_count") or 0) <= int(before.get("active_nonterminal_track_count") or 0):
                supply_starved += seconds
        if placement_opportunity:
            placement_denominator += seconds
            if int(after.get("active_launch_count") or 0) <= int(before.get("active_launch_count") or 0):
                placement_starved += seconds
    total_denominator = supply_denominator + placement_denominator
    total_starved = supply_starved + placement_starved
    return {
        "value": (total_starved / total_denominator) if total_denominator else None,
        "supply": {
            "value": (supply_starved / supply_denominator) if supply_denominator else None,
            "opportunity_hours": round(supply_denominator / 3600.0, 6),
            "starved_hours": round(supply_starved / 3600.0, 6),
        },
        "placement": {
            "value": (placement_starved / placement_denominator) if placement_denominator else None,
            "opportunity_hours": round(placement_denominator / 3600.0, 6),
            "starved_hours": round(placement_starved / 3600.0, 6),
        },
        "unknown_reason": None if total_denominator else "fewer than two timestamped opportunity observations",
    }


def project_report(helper: Any, project: Path) -> dict[str, Any]:
    shortlist = shortlist_ids(helper, project)
    pilots, _ = valid_pilot_ids(helper, project)
    observations = read_observations(project / OBS_REL)
    queue = helper.load_queue(project)
    rows = [row for row in queue.get("rows", []) if isinstance(row, dict)]
    matrix = read_json(project / ".autoreskill/orchestrator/TRACK_PLAN_MATRIX.json")
    frontier = helper.frontier_status(queue, matrix=matrix, project=project)
    program = read_json(project / ".autoreskill/orchestrator/PROGRAM_CLAIM_CONTRACT.json")
    required_datasets = {
        str(row.get("dataset_id"))
        for row in program.get("target_datasets", [])
        if isinstance(row, dict) and row.get("required") is True and row.get("dataset_id")
    }
    method_track_ids = {
        str(row.get("track_id")) for row in rows
        if row.get("claim_role") == "method_candidate" and row.get("track_id")
    }
    diagnostic_track_ids = {
        str(row.get("track_id")) for row in rows
        if row.get("claim_role") in {"diagnostic_only", "baseline_support", "protocol_support"} and row.get("track_id")
    }
    complete_before_hpo = 0
    for track_id in method_track_ids:
        stage2_datasets = {
            str(row.get("dataset_id") or row.get("dataset"))
            for row in rows
            if str(row.get("track_id") or "") == track_id
            and row.get("validation_stage") == 2
            and str(row.get("status") or "") in {"terminal_positive", "terminal_negative", "superseded"}
        }
        if required_datasets and required_datasets <= stage2_datasets:
            complete_before_hpo += 1
    decision_ledger = read_json(project / ".autoreskill/ideation/IDEA_DECISION_LEDGER.json")
    cross_decisions = [
        row for row in decision_ledger.get("cross_dataset_decisions", []) if isinstance(row, dict)
    ]
    closed_verdicts = {
        "single_point_parameterization_refuted",
        "calibrated_mechanism_refuted",
        "core_transfer_refuted",
        "cross_dataset_supported",
    }
    return {
        "project_root": str(project),
        "time_to_first_discriminator": first_discriminator_metric(helper, project),
        "portfolio_starvation_rate": starvation_metric(observations),
        "gpu_hours_per_decision": gpu_hours_and_decisions(project),
        "shortlist_to_pilot_yield": {
            "value": (len(pilots & shortlist) / len(shortlist)) if shortlist else None,
            "eligible_shortlisted_candidates": len(shortlist),
            "protocol_valid_stage2_candidate_count": len(pilots & shortlist),
            "unknown_reason": None if shortlist else "eligible shortlist unavailable",
        },
        "cross_dataset_method_throughput": {
            "method_candidate_track_count": len(method_track_ids),
            "diagnostic_or_support_track_count": len(diagnostic_track_ids),
            "method_tracks_complete_on_required_stage2_datasets": complete_before_hpo,
            "cross_dataset_stage2_coverage_rate": (
                complete_before_hpo / len(method_track_ids) if method_track_ids else None
            ),
            "cross_dataset_decision_count": len(cross_decisions),
            "bounded_contradiction_closure_rate": (
                sum(1 for row in cross_decisions if row.get("verdict") in closed_verdicts) / len(cross_decisions)
                if cross_decisions else None
            ),
            "current_method_portfolio_deficit": frontier.get("method_portfolio_deficit"),
            "current_diagnostic_track_count": frontier.get("diagnostic_active_track_count"),
            "current_parameter_coverage_deficit_by_track_and_dataset": frontier.get(
                "parameter_coverage_deficit_by_track_and_dataset"
            ) or {},
            "current_dataset_coverage_deficit_by_track": frontier.get("dataset_coverage_deficit_by_track") or {},
            "current_incomplete_paired_group_count": frontier.get("paired_group_incomplete_count"),
            "current_cross_dataset_full_budget_ready_count": frontier.get("cross_dataset_full_budget_ready_count"),
            "current_robust_hpo_ready_count": frontier.get("robust_hpo_ready_count"),
        },
        "observation_count": len(observations),
    }


def aggregate(projects: list[dict[str, Any]]) -> dict[str, Any]:
    shortlist = sum(item["shortlist_to_pilot_yield"]["eligible_shortlisted_candidates"] for item in projects)
    pilots = sum(item["shortlist_to_pilot_yield"]["protocol_valid_stage2_candidate_count"] for item in projects)
    gpu_hours = sum(item["gpu_hours_per_decision"]["actual_gpu_hours"] for item in projects)
    decisions = sum(item["gpu_hours_per_decision"]["decision_count"] for item in projects)
    covered = sum(item["gpu_hours_per_decision"]["covered_terminal_runs"] for item in projects)
    terminal = sum(item["gpu_hours_per_decision"]["terminal_runs"] for item in projects)
    gpu_metric_ready = decisions > 0 and terminal > 0 and covered == terminal
    if decisions == 0:
        gpu_unknown_reason = "accepted scientific decisions unavailable"
    elif terminal == 0:
        gpu_unknown_reason = "no terminal run accounting evidence"
    elif covered != terminal:
        gpu_unknown_reason = "actual GPU-hours coverage incomplete"
    else:
        gpu_unknown_reason = None
    return {
        "shortlist_to_pilot_yield": {
            "value": pilots / shortlist if shortlist else None,
            "eligible_shortlisted_candidates": shortlist,
            "protocol_valid_stage2_candidate_count": pilots,
        },
        "gpu_hours_per_decision": {
            "value": gpu_hours / decisions if gpu_metric_ready else None,
            "actual_gpu_hours": round(gpu_hours, 6),
            "decision_count": decisions,
            "runtime_coverage": covered / terminal if terminal else None,
            "covered_terminal_runs": covered,
            "terminal_runs": terminal,
            "unknown_reason": gpu_unknown_reason,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AutoResearch Efficiency Report",
        "",
        f"Updated: `{report['generated_at']}`",
        "",
        "| Project | First discriminator median (h) | Starvation | GPU h / decision | Shortlist -> pilot | Stage-2 cross-dataset coverage | Cross-dataset decisions | Contradiction closure | Coverage note |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["projects"]:
        first = item["time_to_first_discriminator"]
        starvation = item["portfolio_starvation_rate"]
        gpu = item["gpu_hours_per_decision"]
        yield_metric = item["shortlist_to_pilot_yield"]
        cross = item.get("cross_dataset_method_throughput") or {}
        note = "; ".join(
            value for value in [first.get("unknown_reason"), starvation.get("unknown_reason"), gpu.get("unknown_reason"), yield_metric.get("unknown_reason")] if value
        ) or "complete for reported fields"
        fmt = lambda value: "unknown" if value is None else f"{float(value):.4f}"
        lines.append(
            f"| {Path(item['project_root']).name} | {fmt(first.get('median'))} | {fmt(starvation.get('value'))} | "
            f"{fmt(gpu.get('value'))} | {fmt(yield_metric.get('value'))} | "
            f"{fmt(cross.get('cross_dataset_stage2_coverage_rate'))} | {int(cross.get('cross_dataset_decision_count') or 0)} | "
            f"{fmt(cross.get('bounded_contradiction_closure_rate'))} | {note} |"
        )
    lines.extend(["", "This report is observational evidence only; it cannot admit, launch, or promote experiments.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    observe = sub.add_parser("observe")
    observe.add_argument("--project", required=True)
    observe.add_argument("--force", action="store_true")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("--project", action="append", required=True)
    report_parser.add_argument("--out")
    report_parser.add_argument("--markdown-out")
    args = parser.parse_args()
    try:
        if args.command == "observe":
            payload = observe_project(Path(args.project).expanduser().resolve(), args.force)
        else:
            helper = load_queue_helper()
            projects = [project_report(helper, Path(value).expanduser().resolve()) for value in args.project]
            payload = {
                "schema_version": 1,
                "generated_at": now_iso(),
                "authority_boundary": "observational metric report only; never admits, launches, or promotes work",
                "projects": projects,
                "global": aggregate(projects),
            }
            out = Path(args.out).expanduser().resolve() if args.out else Path(args.project[0]).expanduser().resolve() / REPORT_REL
            atomic_write_json(out, payload)
            if args.markdown_out:
                markdown_out = Path(args.markdown_out).expanduser().resolve()
                markdown_out.parent.mkdir(parents=True, exist_ok=True)
                markdown_out.write_text(markdown(payload), encoding="utf-8")
            payload = {"ok": True, "out": str(out), "markdown_out": args.markdown_out, "report": payload}
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
