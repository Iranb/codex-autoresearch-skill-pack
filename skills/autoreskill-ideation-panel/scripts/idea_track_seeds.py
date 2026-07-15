#!/usr/bin/env python3
"""Create or check IDEA_TRACK_SEEDS from the idea pool and scorecard."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
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
    "hypothesis_contract",
]
HYPOTHESIS_REQUIRED_FIELDS = [
    "track_id",
    "causal_signature",
    "causal_question",
    "intervention",
    "one_variable_delta",
    "mechanism",
    "predicted_pattern",
    "falsifier",
    "alternative_explanation",
    "minimum_discriminating_experiment",
    "dataset_transfer_assumption",
    "outcome_routes",
    "max_scientific_revisions",
    "scientific_revision_index",
    "belief_state",
]
EXTERNAL_CAMPAIGN_REF = "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
EXTERNAL_IDENTITY_FIELDS = [
    "external_campaign_ref",
    "external_campaign_sha256",
    "external_candidate_id",
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the stable seed authority content used to bind downstream plans."""

    return {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at", "semantic_sha256"}
    }


def semantic_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        semantic_payload(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_source_mode(base: Path) -> str:
    gate = read_json(base / "ideation/PRE_IDEA_EVIDENCE_GATE.json", {})
    if not isinstance(gate, dict):
        return "papernexus"
    return str(gate.get("evidence_source_mode") or "papernexus").strip().lower()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    handle, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def causal_signature(idea: dict[str, Any]) -> str:
    explicit = normalized_text(idea.get("causal_signature"))
    if explicit:
        return explicit
    fields = [normalized_text(idea.get(key)) for key in ["intervention", "mechanism", "predicted_pattern"]]
    return " | ".join(fields) if all(fields) else ""


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def track_seed_sha256(seed: dict[str, Any]) -> str:
    return canonical_sha256(
        {key: value for key, value in seed.items() if key not in {"track_seed_sha256", "admitted_at"}}
    )


def as_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def positive_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, bool):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed) and parsed > 0:
            return parsed
    return None


def ranking_tuple(row: dict[str, Any], idea: dict[str, Any]) -> list[Any]:
    targets = as_strings(row.get("unique_decision_targets") or row.get("decision_target_refs"))
    if not targets:
        target = row.get("decision_target") or idea.get("claim_target")
        targets = [str(target)] if present(target) else []
    cost = positive_number(
        row.get("estimated_falsifier_gpu_hours"),
        row.get("estimated_gpu_hours"),
        idea.get("estimated_falsifier_gpu_hours"),
        idea.get("estimated_gpu_hours"),
        (idea.get("track_seed_spec") or {}).get("estimated_gpu_hours")
        if isinstance(idea.get("track_seed_spec"), dict)
        else None,
    )
    resolved = row.get("competing_hypotheses_resolved_count")
    try:
        resolved_count = max(0, int(resolved))
    except (TypeError, ValueError):
        resolved_count = len(as_strings(row.get("competing_hypotheses_resolved"))) or len(targets)
    reuse = as_strings(row.get("reusable_invariant_refs") or idea.get("reusable_invariant_refs"))
    risks = as_strings(
        row.get("reviewer_risks")
        or row.get("reviewer_attack_surface")
        or idea.get("reviewer_risks")
        or idea.get("red_line_risks")
    )
    density = len(set(targets)) / cost if cost else None
    return [
        0 if row.get("changes_core_claim") is True or idea.get("changes_core_claim") is True else 1,
        -resolved_count,
        -density if density is not None else 0,
        cost if cost is not None else 1e30,
        -len(set(reuse)),
        len(set(risks)),
        str(idea.get("id") or row.get("idea_id") or row.get("id") or ""),
    ]


def active_track_limit(scorecard: dict[str, Any]) -> int:
    value = scorecard.get("active_track_limit")
    return value if isinstance(value, int) and not isinstance(value, bool) and 3 <= value <= 4 else 3


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


def recommendation_ids(
    scorecard: dict[str, Any], rows: list[dict[str, Any]], ideas: dict[str, dict[str, Any]], limit: int
) -> list[str]:
    out: list[str] = []
    row_by_id = {
        str(row.get("id") or row.get("idea_id") or ""): row
        for row in rows
        if present(row.get("id") or row.get("idea_id"))
    }
    allowed = {"advance", "advance_with_constraints", "risk_repair"}
    for key in ["top_track_recommendations", "top_recommendations"]:
        value = scorecard.get(key)
        if isinstance(value, list):
            for item in value:
                idea_id = item.get("idea_id") if isinstance(item, dict) else item
                row = row_by_id.get(str(idea_id), {})
                decision = str(
                    row.get("promotion_recommendation")
                    or row.get("recommended_track_action")
                    or (item.get("recommended_track_action") if isinstance(item, dict) else "")
                    or ""
                ).strip().lower()
                if present(idea_id) and str(idea_id) not in out and (not decision or decision in allowed):
                    out.append(str(idea_id))
    ranked = sorted(
        rows,
        key=lambda row: tuple(
            row.get("deterministic_ranking_tuple")
            if isinstance(row.get("deterministic_ranking_tuple"), list)
            else ranking_tuple(row, ideas.get(str(row.get("id") or row.get("idea_id") or ""), {}))
        ),
    )
    for row in ranked:
        idea_id = row.get("id") or row.get("idea_id")
        if present(idea_id) and str(idea_id) not in out:
            decision = str(row.get("promotion_recommendation") or "").strip().lower()
            if decision in allowed:
                out.append(str(idea_id))
        if len(out) >= limit:
            break
    return out[:limit]


def build_seed(
    idea: dict[str, Any],
    row: dict[str, Any],
    index: int,
    primary_id: str | None,
    program_binding: dict[str, Any],
) -> dict[str, Any]:
    idea_id = str(idea.get("id"))
    track_spec = idea.get("track_seed_spec") if isinstance(idea.get("track_seed_spec"), dict) else {}
    paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
    role = "primary" if idea_id == primary_id or (primary_id is None and index == 0) else "alternate"
    if row.get("recommended_track_action") == "risk_repair":
        role = "risk_repair"
    stable_idea_component = re.sub(r"[^A-Za-z0-9._-]+", "-", idea_id).strip("-.") or canonical_sha256(idea_id)[:12]
    track_id = str(track_spec.get("track_id") or f"track-{stable_idea_component}")
    routes = idea.get("outcome_routes") if isinstance(idea.get("outcome_routes"), dict) else {}
    source_refs = idea.get("source_evidence_refs") or idea.get("paperNexus_evidence_ids") or idea.get("goe_path_refs") or []
    hypothesis_contract = {
        "track_id": track_id,
        "parent_track_id": idea.get("parent_track_id"),
        "derived_from_run_id": idea.get("derived_from_run_id"),
        "hypothesis_delta": idea.get("hypothesis_delta"),
        "causal_signature": causal_signature(idea),
        "causal_question": idea.get("research_question"),
        "intervention": idea.get("intervention"),
        "one_variable_delta": track_spec.get("one_variable_change") or idea.get("one_variable_change") or idea.get("intervention"),
        "mechanism": idea.get("mechanism"),
        "predicted_pattern": idea.get("predicted_pattern"),
        "falsifier": idea.get("falsifier") or paper.get("falsifier"),
        "alternative_explanation": idea.get("alternative_explanation"),
        "minimum_discriminating_experiment": idea.get("cheapest_discriminating_experiment"),
        "dataset_transfer_assumption": idea.get("dataset_transfer_assumption") or "Must be re-evaluated on each claim-bearing target dataset.",
        "outcome_routes": {
            "positive": routes.get("positive"),
            "negative": routes.get("negative"),
            "inconclusive": routes.get("inconclusive"),
            "invalid": routes.get("invalid"),
        },
        "max_scientific_revisions": 2,
        "scientific_revision_index": 0,
        "belief_state": "untested",
        "source_evidence_refs": source_refs,
        "closest_prior_refs": idea.get("closest_prior_refs") or idea.get("negative_evidence_refs") or [],
    }
    seed = {
        "track_id": track_id,
        "idea_id": idea_id,
        "track_role": role,
        "claim_role": row.get("claim_role") or idea.get("claim_role") or "method_candidate",
        "cross_dataset_prediction": row.get("cross_dataset_prediction") or idea.get("cross_dataset_prediction"),
        "transfer_assumption": row.get("transfer_assumption") or idea.get("transfer_assumption"),
        "parameter_transfer_mode": row.get("parameter_transfer_mode") or idea.get("parameter_transfer_mode"),
        "shared_method_formula": row.get("shared_method_formula") or idea.get("shared_method_formula"),
        "paired_low_fidelity_falsifier": row.get("paired_low_fidelity_falsifier") or idea.get("paired_low_fidelity_falsifier"),
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
        "hypothesis_contract": hypothesis_contract,
        "launch_approval": False,
        "deterministic_ranking": {
            "tuple": ranking_tuple(row, idea),
            "changes_core_claim": row.get("changes_core_claim") is True or idea.get("changes_core_claim") is True,
            "unique_decision_targets": as_strings(row.get("unique_decision_targets") or row.get("decision_target_refs")),
            "estimated_falsifier_gpu_hours": positive_number(
                row.get("estimated_falsifier_gpu_hours"),
                row.get("estimated_gpu_hours"),
                idea.get("estimated_falsifier_gpu_hours"),
                idea.get("estimated_gpu_hours"),
            ),
            "reviewer_risks": as_strings(row.get("reviewer_risks") or row.get("reviewer_attack_surface")),
        },
    }
    seed.update(program_binding)
    # External campaign identity is protected provenance.  It may be copied from
    # the source artifacts, but it must never be inferred from the local idea id.
    if any(present(idea.get(field)) or present(row.get(field)) for field in EXTERNAL_IDENTITY_FIELDS):
        for field in EXTERNAL_IDENTITY_FIELDS:
            seed[field] = idea.get(field) if present(idea.get(field)) else row.get(field)
    seed["track_seed_sha256"] = track_seed_sha256(seed)
    return seed


def build(
    project: str,
    capacity_target: int | None = None,
    admit_idea_ids: list[str] | None = None,
) -> dict[str, Any]:
    base = ar(project)
    program_contract = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    program_binding = {
        "program_claim_contract_ref": "orchestrator/PROGRAM_CLAIM_CONTRACT.json",
        "program_claim_contract_sha256": program_contract.get("semantic_sha256"),
        "program_claim_contract_revision": program_contract.get("contract_revision"),
    } if isinstance(program_contract, dict) and program_contract else {}
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json", {})
    scorecard = read_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", {})
    ideas = {str(idea.get("id")): idea for idea in ideas_from_pool(pool) if present(idea.get("id"))}
    rows = rows_from_scorecard(scorecard)
    rows_by_id = {str(row.get("id") or row.get("idea_id")): row for row in rows if present(row.get("id") or row.get("idea_id"))}
    scorecard_payload = scorecard if isinstance(scorecard, dict) else {}
    limit = active_track_limit(scorecard_payload)
    if capacity_target is not None:
        if capacity_target < 1 or capacity_target > 4:
            raise SystemExit("--capacity-target must be between 1 and 4")
        limit = capacity_target
    primary_id = None
    if isinstance(scorecard, dict):
        primary_id = scorecard.get("selected_primary_idea_id") or scorecard.get("selected_idea_id")
    if not present(primary_id) and isinstance(pool, dict):
        primary_id = pool.get("selected_idea_id")
    ranked_ids = recommendation_ids(scorecard_payload, rows, ideas, 4)
    current = read_json(base / "ideation/IDEA_TRACK_SEEDS.json", {})
    current_by_idea = {
        str(item.get("idea_id") or ""): item
        for item in (current.get("tracks") if isinstance(current, dict) else []) or []
        if isinstance(item, dict) and present(item.get("idea_id"))
    }
    if admit_idea_ids is None:
        ids = ranked_ids[:limit]
    else:
        current_ids = [
            str(item.get("idea_id"))
            for item in (current.get("tracks") if isinstance(current, dict) else []) or []
            if isinstance(item, dict) and present(item.get("idea_id"))
        ]
        requested = current_ids + [str(item) for item in admit_idea_ids if present(item)]
        requested_set = set(requested)
        ids = [idea_id for idea_id in ranked_ids if idea_id in requested_set]
        ids.extend(idea_id for idea_id in requested if idea_id not in ids)
        ids = ids[:limit]
    if present(primary_id) and str(primary_id) in ideas and str(primary_id) not in ids:
        ids.insert(0, str(primary_id))
        ids = ids[:limit]
    generated_at = now()
    seeds = [
        build_seed(
            ideas[idea_id],
            rows_by_id.get(idea_id, {}),
            index,
            str(primary_id) if present(primary_id) else None,
            program_binding,
        )
        for index, idea_id in enumerate(ids)
        if idea_id in ideas
    ]
    for seed in seeds:
        prior = current_by_idea.get(str(seed.get("idea_id") or ""), {})
        seed["admitted_at"] = prior.get("admitted_at") or generated_at
        seed["track_seed_sha256"] = track_seed_sha256(seed)
    payload = {
        "schema_version": 2,
        "generated_at": generated_at,
        "artifact": "IDEA_TRACK_SEEDS",
        "source_idea_pool_path": "ideation/EXPERIMENT_IDEA_POOL.json",
        "source_scorecard_path": "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
        "selection_revision": scorecard_payload.get("selection_revision")
        or scorecard_payload.get("selection_fingerprint")
        or canonical_sha256(
            {
                "idea_pool_sha256": sha256_file(base / "ideation/EXPERIMENT_IDEA_POOL.json")
                if (base / "ideation/EXPERIMENT_IDEA_POOL.json").exists()
                else None,
                "scorecard_sha256": sha256_file(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json")
                if (base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json").exists()
                else None,
            }
        ),
        "selected_primary_idea_id": primary_id,
        "alternate_track_idea_ids": [seed["idea_id"] for seed in seeds if seed["track_role"] != "primary"],
        "track_selection_policy": "bounded_explore_exploit_seed_only_no_launch_approval",
        "active_track_limit": limit,
        **program_binding,
        "tracks": seeds,
    }
    payload["semantic_sha256"] = semantic_sha256(payload)
    return payload


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    program_contract = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    program_mode = str(program_contract.get("enforcement_mode") or "legacy").strip().lower() if isinstance(program_contract, dict) else "legacy"
    payload = read_json(base / "ideation/IDEA_TRACK_SEEDS.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": ["ideation/IDEA_TRACK_SEEDS.json"], "warnings": []}
    recorded_semantic_sha = str(payload.get("semantic_sha256") or "").strip().lower()
    computed_semantic_sha = semantic_sha256(payload)
    if recorded_semantic_sha:
        if recorded_semantic_sha != computed_semantic_sha:
            missing.append("semantic_sha256 must match canonical seed content")
    else:
        warnings.append("legacy seed authority has no semantic_sha256; regenerate explicitly before admitting alternate tracks")
    if not present(payload.get("selection_revision")):
        missing.append("selection_revision")
    if program_contract and program_mode == "enforced":
        if payload.get("program_claim_contract_sha256") != program_contract.get("semantic_sha256"):
            missing.append("program_claim_contract_sha256 must match the live contract")
        if payload.get("program_claim_contract_revision") != program_contract.get("contract_revision"):
            missing.append("program_claim_contract_revision must match the live contract")
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        missing.append("tracks")
        tracks = []
    primary_count = 0
    causal_signatures: set[str] = set()
    for index, track in enumerate(row for row in tracks if isinstance(row, dict)):
        prefix = f"tracks[{index}]"
        for field in REQUIRED_SEED_FIELDS:
            if field not in track or (field != "evidence_debt" and not present(track.get(field))):
                missing.append(f"{prefix}.{field}")
        if track.get("ablation_required") is not True:
            missing.append(f"{prefix}.ablation_required=true")
        if track.get("confirmation_required") is not True:
            missing.append(f"{prefix}.confirmation_required=true")
        if track.get("launch_approval") is True:
            missing.append(f"{prefix}.launch_approval must remain false at idea_gate")
        if str(track.get("track_role") or "") == "primary":
            primary_count += 1
        contract = track.get("hypothesis_contract") if isinstance(track.get("hypothesis_contract"), dict) else {}
        for field in HYPOTHESIS_REQUIRED_FIELDS:
            if not present(contract.get(field)) and field != "scientific_revision_index":
                missing.append(f"{prefix}.hypothesis_contract.{field}")
        routes = contract.get("outcome_routes") if isinstance(contract.get("outcome_routes"), dict) else {}
        for route in ["positive", "negative", "inconclusive", "invalid"]:
            if not present(routes.get(route)):
                missing.append(f"{prefix}.hypothesis_contract.outcome_routes.{route}")
        signature = str(contract.get("causal_signature") or "").strip()
        if signature and signature in causal_signatures:
            missing.append(f"{prefix}.hypothesis_contract.causal_signature duplicates another active track")
        elif signature:
            causal_signatures.add(signature)
        recorded_track_sha = str(track.get("track_seed_sha256") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", recorded_track_sha):
            missing.append(f"{prefix}.track_seed_sha256 lowercase sha256")
        elif recorded_track_sha != track_seed_sha256(track):
            missing.append(f"{prefix}.track_seed_sha256 must match canonical track content")
        if contract.get("max_scientific_revisions") != 2:
            missing.append(f"{prefix}.hypothesis_contract.max_scientific_revisions=2")
    if primary_count != 1:
        missing.append("exactly one primary track")
    if len(tracks) > 4:
        missing.append("active track seeds must not exceed 4")
    if len(tracks) < int(payload.get("active_track_limit") or 1):
        warnings.append("portfolio is below its capacity target; this is valid only when no additional shortlist candidate passes admission gates")
    mode = evidence_source_mode(base)
    if mode == "external_material":
        campaign_path = base / EXTERNAL_CAMPAIGN_REF
        campaign = read_json(campaign_path, {})
        if not campaign_path.exists() or not isinstance(campaign, dict) or not campaign:
            missing.append(EXTERNAL_CAMPAIGN_REF)
        else:
            campaign_sha = sha256_file(campaign_path)
            admitted = {
                str(item).strip()
                for item in campaign.get("admitted_candidate_ids", [])
                if str(item).strip()
            } if isinstance(campaign.get("admitted_candidate_ids"), list) else set()
            seen: list[str] = []
            for index, track in enumerate(row for row in tracks if isinstance(row, dict)):
                prefix = f"tracks[{index}]"
                for field in EXTERNAL_IDENTITY_FIELDS:
                    if not present(track.get(field)):
                        missing.append(f"{prefix}.{field}")
                if track.get("external_campaign_ref") != EXTERNAL_CAMPAIGN_REF:
                    missing.append(f"{prefix}.external_campaign_ref must be {EXTERNAL_CAMPAIGN_REF}")
                if track.get("external_campaign_sha256") != campaign_sha:
                    missing.append(f"{prefix}.external_campaign_sha256 must match current campaign")
                candidate_id = str(track.get("external_candidate_id") or "").strip()
                if candidate_id:
                    seen.append(candidate_id)
                    if candidate_id not in admitted:
                        missing.append(f"{prefix}.external_candidate_id must be admitted by current campaign")
                    if candidate_id in {str(track.get("track_id") or ""), str(track.get("idea_id") or "")}:
                        missing.append(f"{prefix} track_id/idea_id must remain distinct from external_candidate_id")
            if len(seen) != len(set(seen)):
                missing.append("external_candidate_id must be unique across active track seeds")
            if set(seen) != admitted:
                missing.append("IDEA_TRACK_SEEDS external candidate ids must exactly match admitted campaign ids")
    elif mode != "papernexus":
        missing.append(f"unsupported evidence_source_mode: {mode}")
    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "track_count": len(tracks),
        "semantic_sha256": computed_semantic_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--capacity-target", type=int)
    parser.add_argument("--admit-idea-id", action="append")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.check:
        out = check(args.project)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        raise SystemExit(0 if out["complete"] else 1)
    payload = build(
        args.project,
        capacity_target=args.capacity_target,
        admit_idea_ids=args.admit_idea_id,
    )
    if not args.dry_run:
        write_json(ar(args.project) / "ideation/IDEA_TRACK_SEEDS.json", payload)
    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": args.dry_run,
                "path": "ideation/IDEA_TRACK_SEEDS.json",
                "track_count": len(payload["tracks"]),
                "semantic_sha256": payload["semantic_sha256"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
