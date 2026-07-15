#!/usr/bin/env python3
"""Validate and apply scientific outcomes to the existing idea lifecycle ledger."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from parameter_transfer import (
    canonical_value,
    distinct_values,
    required_dataset_ids,
    stable_hash as parameter_stable_hash,
    validate_parameter_transfer_contract,
)
from program_claim_contract import validate_replacement_authority


OUTCOME_RULES = {
    "infrastructure_failure": {
        "belief": {"none"},
        "transitions": {"WAIT_OR_RECONCILE_BACKEND"},
        "requires_valid_result": False,
    },
    "implementation_failure": {
        "belief": {"none"},
        "transitions": {"REFINE_IMPLEMENTATION"},
        "requires_valid_result": False,
    },
    "protocol_invalid": {
        "belief": {"none"},
        "transitions": {"REFINE_PROTOCOL"},
        "requires_valid_result": False,
    },
    "budget_stopped_no_scientific_conclusion": {
        "belief": {"none"},
        "transitions": {"WAIT_OR_RECONCILE_BACKEND", "CONCLUDE_PROGRAM"},
        "requires_valid_result": False,
    },
    "valid_positive_candidate": {
        "belief": {"support_increased"},
        "transitions": {"PROCEED_TO_ABLATION_OR_CONFIRMATION", "REQUEST_PRIMARY_RESELECTION"},
        "requires_valid_result": True,
    },
    "valid_negative": {
        "belief": {"support_weakened", "refuted"},
        "transitions": {
            "RUN_ONE_DISAMBIGUATOR",
            "PIVOT_TO_CHILD_TRACK",
            "RETIRE_TRACK",
            "SCOPE_CLAIM",
            "CONCLUDE_PROGRAM",
            "REFINE_IMPLEMENTATION",
        },
        "requires_valid_result": True,
    },
    "valid_inconclusive": {
        "belief": {"still_inconclusive"},
        "transitions": {"RUN_ONE_DISAMBIGUATOR", "RETIRE_TRACK", "CONCLUDE_PROGRAM"},
        "requires_valid_result": True,
    },
    "cross_dataset_contradiction": {
        "belief": {"scope_narrowed", "support_weakened"},
        "transitions": {"SCOPE_CLAIM", "PIVOT_TO_CHILD_TRACK", "RUN_ONE_DISAMBIGUATOR"},
        "requires_valid_result": True,
    },
    "duplicate_or_non_discriminating": {
        "belief": {"none", "still_inconclusive"},
        "transitions": {"RETIRE_TRACK", "RUN_ONE_DISAMBIGUATOR", "CONCLUDE_PROGRAM"},
        "requires_valid_result": True,
    },
}

SCIENTIFIC_TRANSITIONS = {"RUN_ONE_DISAMBIGUATOR", "PIVOT_TO_CHILD_TRACK"}
TERMINAL_TRACK_STATES = {"retired", "concluded", "refuted", "terminal"}
LIVE_QUEUE_STATUSES = {"ready", "planned", "claimed", "submitting", "needs_sync", "running"}
DEFAULT_GOAL_TYPE = "paper_producing_top_tier"
DEFAULT_CLAIM_MODE = "strong_paper_claims"
IDENTITY_FIELDS = [
    "run_id",
    "selected_idea_id",
    "track_id",
    "branch_id",
    "queue_row_id",
    "launch_identity_hash",
]
REQUIRED_OUTCOME_FIELDS = [
    *IDENTITY_FIELDS,
    "canonical_result_ref",
    "raw_evidence_refs",
    "validity",
    "falsifier_evaluation",
    "outcome_class",
    "belief_effect",
    "recommended_transition",
    "evidence_rationale",
    "operational_attempt",
    "scientific_revision",
    "claim_effect",
    "claim_limits",
    "adjudicator",
    "adjudicated_at",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


@contextmanager
def decision_lock(base: Path) -> Any:
    path = base / "ideation/IDEA_DECISION_LEDGER.json.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ["entries", "rows", "tracks", "decisions", "track_states"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    return []


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def workflow_scope(state: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    raw_goal_type = state.get("goal_type") or policy.get("goal_type")
    raw_claim_mode = state.get("claim_mode") or policy.get("claim_mode")
    if not present(raw_goal_type):
        warnings.append(f"goal_type missing; using documented default {DEFAULT_GOAL_TYPE}")
    if not present(raw_claim_mode):
        warnings.append(f"claim_mode missing; using documented default {DEFAULT_CLAIM_MODE}")
    return {
        "goal_type": str(raw_goal_type or DEFAULT_GOAL_TYPE).strip(),
        "claim_mode": str(raw_claim_mode or DEFAULT_CLAIM_MODE).strip(),
        "warnings": warnings,
    }


def decision_bearing_live_rows(base: Path) -> list[str]:
    queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {}) or {}
    return sorted(
        str(row.get("id") or row.get("row_id") or "")
        for row in queue.get("rows") or []
        if isinstance(row, dict)
        and str(row.get("status") or "") in LIVE_QUEUE_STATUSES
        and str(row.get("role") or "") != "monitor_sync"
        and str(row.get("launch_mode") or "") != "monitor_only"
        and str(row.get("decision_class") or "") != "resource_fill_diagnostic"
        and row.get("audit_only") is not True
        and row.get("audit_only_after_program_decision") is not True
        and row.get("program_decision_blocking") is not False
    )


def program_revision_id(program: dict[str, Any]) -> str:
    return str(program.get("contract_id") or program.get("semantic_sha256") or "").strip()


def active_program_revision_id(ledger: dict[str, Any]) -> str:
    active = ledger.get("active_program_revision") if isinstance(ledger.get("active_program_revision"), dict) else {}
    return str(active.get("program_revision_id") or ledger.get("program_revision_id") or ledger.get("active_program_contract_id") or "").strip()


def explicit_active_program_revision_id(ledger: dict[str, Any]) -> str:
    active = ledger.get("active_program_revision") if isinstance(ledger.get("active_program_revision"), dict) else {}
    return str(active.get("program_revision_id") or ledger.get("program_revision_id") or "").strip()


def candidate_supply_status(base: Path, ledger: dict[str, Any], program: dict[str, Any]) -> dict[str, Any]:
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json", {}) or {}
    scorecard = read_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", {}) or {}
    active_revision = active_program_revision_id(ledger)
    if not active_revision or not str(program.get("replacement_basis_decision_id") or "").strip():
        return {"status": "legacy_current", "current": True, "program_revision_id": active_revision or None}
    current_sha = str(program.get("semantic_sha256") or "").strip()
    artifacts = {"idea_pool": pool, "scorecard": scorecard}
    bindings = {
        name: {
            "program_revision_id": str(payload.get("program_revision_id") or "").strip() or None,
            "program_claim_contract_sha256": str(payload.get("program_claim_contract_sha256") or "").strip() or None,
        }
        for name, payload in artifacts.items()
    }
    binding_errors = [
        name
        for name, binding in bindings.items()
        if binding["program_revision_id"] != active_revision
        or binding["program_claim_contract_sha256"] != current_sha
    ]
    ideas = pool.get("ideas") if isinstance(pool.get("ideas"), list) else []
    shortlisted = scorecard.get("shortlisted_idea_ids") or scorecard.get("shortlist") or []
    selected = scorecard.get("selected_primary_idea_id") or scorecard.get("selected_idea_id")
    revision_events = current_revision_events(ledger, program)
    latest_event = revision_events[-1] if revision_events else {}
    recorded_card_count = int(latest_event.get("cards_generated") or 0)
    recorded_shortlist_count = int(latest_event.get("shortlisted_candidates") or 0)
    shape_errors: list[str] = []
    if not (8 <= len(ideas) <= 12 or 8 <= recorded_card_count <= 12):
        shape_errors.append("idea_pool_must_contain_8_to_12_cards")
    if not (
        (isinstance(shortlisted, list) and 3 <= len(shortlisted) <= 5)
        or 3 <= recorded_shortlist_count <= 5
    ):
        shape_errors.append("scorecard_must_contain_3_to_5_shortlisted_idea_ids")
    if not binding_errors and not shape_errors:
        return {
            "status": "current",
            "current": True,
            "program_revision_id": active_revision,
            "program_claim_contract_sha256": current_sha,
            "idea_count": len(ideas),
            "shortlist_count": len(shortlisted),
            "recorded_card_count": recorded_card_count or None,
            "recorded_shortlist_count": recorded_shortlist_count or None,
        }
    has_supply = bool(ideas or shortlisted or selected)
    status = "missing" if not has_supply else "stale_or_malformed"
    return {
        "status": status,
        "current": False,
        "program_revision_id": active_revision,
        "program_claim_contract_sha256": current_sha,
        "artifact_bindings": bindings,
        "binding_errors": binding_errors,
        "shape_errors": shape_errors,
        "idea_count": len(ideas),
        "shortlist_count": len(shortlisted) if isinstance(shortlisted, list) else 0,
        "recorded_card_count": recorded_card_count or None,
        "recorded_shortlist_count": recorded_shortlist_count or None,
    }


def current_revision_events(ledger: dict[str, Any], program: dict[str, Any]) -> list[dict[str, Any]]:
    events = [row for row in ledger.get("replenishment_events") or [] if isinstance(row, dict)]
    revision_id = active_program_revision_id(ledger)
    contract_sha = str(program.get("semantic_sha256") or "").strip()
    if not revision_id:
        return events
    return [
        row
        for row in events
        if str(row.get("program_revision_id") or "").strip() == revision_id
        or (
            not str(row.get("program_revision_id") or "").strip()
            and str(row.get("program_claim_contract_sha256") or "").strip() == contract_sha
        )
    ]


def replenishment_authorization(base: Path, basis_decision_id: str | None = None) -> dict[str, Any]:
    intervention = read_json(base / "control/REPLENISHMENT_INTERVENTION_REQUEST.json", {}) or {}
    authorization = intervention.get("authorization") if isinstance(intervention.get("authorization"), dict) else {}
    authorized_max = authorization.get("max_targeted_replenishments")
    if authorized_max is None:
        authorized_max = intervention.get("requested_max_targeted_replenishments")
    try:
        authorized_max = int(authorized_max)
    except (TypeError, ValueError):
        authorized_max = -1
    observed_basis = str(intervention.get("basis_decision_id") or "").strip()
    expected_basis = str(basis_decision_id or observed_basis).strip()
    status = str(intervention.get("status") or "").strip().lower()
    valid_status = bool(status) and not any(
        token in status for token in {"revoked", "cancelled", "rejected", "blocked"}
    )
    errors: list[dict[str, str]] = []
    if not valid_status:
        errors.append({"code": "replenishment_authorization_inactive", "field": "intervention.status"})
    if str(authorization.get("source") or "").strip() != "direct_user_instruction":
        errors.append({"code": "direct_user_authorization_missing", "field": "intervention.authorization.source"})
    if expected_basis and observed_basis != expected_basis:
        errors.append({"code": "replenishment_authorization_basis_mismatch", "field": observed_basis})
    if authorized_max < 0 or authorized_max > 8:
        errors.append({"code": "replenishment_authorization_cap_invalid", "field": str(authorized_max)})
    return {
        "complete": not errors,
        "errors": errors,
        "status": status,
        "basis_decision_id": observed_basis or None,
        "max_targeted_replenishments": authorized_max if authorized_max >= 0 else None,
        "request_id": intervention.get("request_id"),
    }


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _artifact_path(base: Path, ref: Any) -> Path | None:
    text = str(ref or "").strip()
    if not text or "://" in text or text.startswith("result:"):
        return None
    path = Path(text).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _calibration_packet(base: Path, track_id: str) -> tuple[dict[str, Any], Path]:
    path = base / f"planner/tracks/{track_id}/EXPERIMENT_REVIEW_PACKET.json"
    packet = read_json(path, {}) or {}
    return packet if isinstance(packet, dict) else {}, path


def _observation_index(evidence: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in evidence.get("observations") or []:
        if not isinstance(row, dict):
            continue
        dataset_id = str(row.get("dataset_id") or "").strip()
        setting_key = canonical_value(row.get("parameter_setting"))
        if dataset_id and (dataset_id, setting_key) not in index:
            index[(dataset_id, setting_key)] = row
    return index


def _tie_key(setting: Any) -> tuple[int, float | str]:
    numeric = _numeric(setting)
    return (0, numeric) if numeric is not None else (1, canonical_value(setting))


def proposed_calibration_decision(base: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    track_id = str(evidence.get("track_id") or "").strip()
    group_id = str(evidence.get("parameter_calibration_group_id") or "").strip()
    if not track_id:
        errors.append({"code": "outcome_missing", "field": "track_id"})
    if not group_id:
        errors.append({"code": "outcome_missing", "field": "parameter_calibration_group_id"})
    packet, packet_path = _calibration_packet(base, track_id)
    if not packet:
        errors.append({"code": "outcome_missing", "field": str(packet_path)})
        return {"errors": errors}
    contract = packet.get("parameter_transfer_contract")
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    datasets = required_dataset_ids(program if isinstance(program, dict) else {}, packet)
    validation = validate_parameter_transfer_contract(contract, datasets)
    for item in validation.get("errors") or []:
        errors.append({"code": "parameter_contract_invalid", "field": str(item)})
    if not isinstance(contract, dict):
        return {"errors": errors}
    if str(evidence.get("parameter_transfer_contract_sha256") or "") != str(
        contract.get("parameter_transfer_contract_sha256") or ""
    ):
        errors.append({"code": "identity_mismatch", "field": "parameter_transfer_contract_sha256"})
    if str(contract.get("parameter_calibration_group_id") or group_id) != group_id:
        errors.append({"code": "identity_mismatch", "field": "parameter_calibration_group_id"})
    selection_scope = str(evidence.get("selection_metric_scope") or "")
    if selection_scope not in {"train_only", "unlabeled_target"}:
        errors.append({"code": "test_derived_calibration_forbidden", "field": "selection_metric_scope"})
    if selection_scope != str(contract.get("calibration_data_scope") or ""):
        errors.append({"code": "calibration_scope_mismatch", "field": "selection_metric_scope"})
    observations = evidence.get("observations")
    if not isinstance(observations, list) or not observations:
        errors.append({"code": "outcome_missing", "field": "observations"})
        return {"errors": errors}
    index = _observation_index(evidence)
    candidates = contract.get("candidate_values_by_dataset") or {}
    seeds = contract.get("selection_seed_by_dataset") or {}
    for dataset_id in datasets:
        for setting in distinct_values(candidates.get(dataset_id)):
            row = index.get((dataset_id, canonical_value(setting)))
            if not row:
                errors.append({"code": "calibration_group_incomplete", "field": f"{dataset_id}:{setting}"})
                continue
            if row.get("terminal_valid") is not True:
                errors.append({"code": "calibration_group_incomplete", "field": f"{dataset_id}:{setting}:terminal_valid"})
            if canonical_value(row.get("seed")) != canonical_value(seeds.get(dataset_id)):
                errors.append({"code": "selection_seed_drift", "field": dataset_id})
            if _numeric(row.get("mechanism_readout")) is None:
                errors.append({"code": "outcome_missing", "field": f"{dataset_id}:{setting}:mechanism_readout"})
            if not present(row.get("result_ref")):
                errors.append({"code": "outcome_missing", "field": f"{dataset_id}:{setting}:result_ref"})
                continue
            result_path = _artifact_path(base, row.get("result_ref"))
            if result_path is None or not result_path.is_file():
                errors.append({"code": "calibration_result_artifact_missing", "field": f"{dataset_id}:{setting}:result_ref"})
                continue
            observed_sha256 = str(row.get("result_sha256") or "").strip().lower()
            if observed_sha256 != _file_sha256(result_path):
                errors.append({"code": "calibration_result_hash_mismatch", "field": f"{dataset_id}:{setting}:result_sha256"})
                continue
            artifact = read_json(result_path, {}) or {}
            provenance = artifact.get("metric_provenance") if isinstance(artifact.get("metric_provenance"), dict) else {}
            if str(artifact.get("dataset_id") or "") != dataset_id:
                errors.append({"code": "calibration_result_identity_mismatch", "field": f"{dataset_id}:{setting}:dataset_id"})
            if canonical_value(artifact.get("parameter_setting")) != canonical_value(setting):
                errors.append({"code": "calibration_result_identity_mismatch", "field": f"{dataset_id}:{setting}:parameter_setting"})
            if _numeric(artifact.get("mechanism_readout")) != _numeric(row.get("mechanism_readout")):
                errors.append({"code": "calibration_result_identity_mismatch", "field": f"{dataset_id}:{setting}:mechanism_readout"})
            if str(provenance.get("selection_metric") or "") != str(contract.get("selection_metric") or ""):
                errors.append({"code": "calibration_metric_provenance_mismatch", "field": f"{dataset_id}:{setting}:selection_metric"})
            if str(provenance.get("selection_metric_scope") or "") != selection_scope:
                errors.append({"code": "calibration_metric_provenance_mismatch", "field": f"{dataset_id}:{setting}:selection_metric_scope"})
            if provenance.get("target_labels_used") is not False or provenance.get("test_outcome_used") is not False:
                errors.append({"code": "test_derived_calibration_forbidden", "field": f"{dataset_id}:{setting}:metric_provenance"})
    if errors:
        return {"errors": errors}

    rule = contract.get("selection_rule_spec")
    if not isinstance(rule, dict):
        return {"errors": [{"code": "outcome_missing", "field": "parameter_transfer_contract.selection_rule_spec"}]}
    direction = str(rule.get("direction") or "max").strip().lower()
    tie_break = str(rule.get("tie_break") or "smaller_setting").strip().lower()
    if direction not in {"max", "min"} or tie_break != "smaller_setting":
        return {"errors": [{"code": "invalid_selection_rule", "field": "selection_rule_spec"}]}

    mode = str(contract.get("transfer_mode") or "")
    selected: dict[str, Any] = {}
    realized: dict[str, Any] = {}
    selected_rows: dict[str, dict[str, Any]] = {}
    if mode in {"shared_absolute", "shared_normalized"}:
        common_keys = None
        settings_by_key: dict[str, Any] = {}
        for dataset_id in datasets:
            values = distinct_values(candidates.get(dataset_id))
            keys = {canonical_value(value) for value in values}
            common_keys = keys if common_keys is None else common_keys & keys
            settings_by_key.update({canonical_value(value): value for value in values})
        scored: list[tuple[float, tuple[int, float | str], str]] = []
        for setting_key in sorted(common_keys or set()):
            readouts = [float(index[(dataset_id, setting_key)]["mechanism_readout"]) for dataset_id in datasets]
            robust_score = min(readouts) if direction == "max" else max(readouts)
            rank_score = -robust_score if direction == "max" else robust_score
            scored.append((rank_score, _tie_key(settings_by_key[setting_key]), setting_key))
        if not scored:
            return {"errors": [{"code": "calibration_group_incomplete", "field": "shared candidate intersection"}]}
        selected_key = min(scored)[2]
        selected_setting = settings_by_key[selected_key]
        for dataset_id in datasets:
            row = index[(dataset_id, selected_key)]
            selected[dataset_id] = selected_setting
            realized[dataset_id] = row.get("realized_parameter_value", selected_setting)
            selected_rows[dataset_id] = row
    else:
        for dataset_id in datasets:
            ranked: list[tuple[float, tuple[int, float | str], str]] = []
            settings_by_key = {
                canonical_value(value): value for value in distinct_values(candidates.get(dataset_id))
            }
            for setting_key, setting in settings_by_key.items():
                readout = float(index[(dataset_id, setting_key)]["mechanism_readout"])
                rank_score = -readout if direction == "max" else readout
                ranked.append((rank_score, _tie_key(setting), setting_key))
            selected_key = min(ranked)[2]
            row = index[(dataset_id, selected_key)]
            selected[dataset_id] = settings_by_key[selected_key]
            realized[dataset_id] = row.get("realized_parameter_value", settings_by_key[selected_key])
            selected_rows[dataset_id] = row

    source_refs = sorted(
        {str(row.get("result_ref")) for row in observations if isinstance(row, dict) and present(row.get("result_ref"))}
    )
    evidence_hash = parameter_stable_hash(evidence)
    decision_core = {
        "decision_type": "parameter_profile_selection",
        "track_id": track_id,
        "parameter_calibration_group_id": group_id,
        "parameter_transfer_contract_sha256": contract.get("parameter_transfer_contract_sha256"),
        "transfer_mode": mode,
        "selected_setting_by_dataset": selected,
        "realized_value_by_dataset": realized,
        "selection_rule_spec": rule,
        "selection_evidence_sha256": evidence_hash,
        "source_evidence_refs": source_refs,
        "claim_ceiling": contract.get("claim_ceiling"),
    }
    decision_id = "parameter-profile-decision-" + stable_hash(decision_core)[:16]
    decision = {**decision_core, "decision_id": decision_id, "decided_at": now()}
    decision["decision_sha256"] = stable_hash({key: value for key, value in decision.items() if key != "decision_sha256"})
    return decision


def run_calibration(base: Path, evidence_path: Path, write: bool) -> tuple[dict[str, Any], int]:
    evidence = read_json(evidence_path, {}) or {}
    if not isinstance(evidence, dict):
        return {"complete": False, "errors": [{"code": "outcome_missing", "field": str(evidence_path)}]}, 1
    proposal = proposed_calibration_decision(base, evidence)
    if proposal.get("errors"):
        return {"complete": False, "errors": proposal["errors"]}, 1
    ledger_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    ledger = read_json(ledger_path, {}) or {}
    decisions = [row for row in ledger.get("calibration_decisions") or [] if isinstance(row, dict)]
    existing = next((row for row in decisions if row.get("decision_id") == proposal.get("decision_id")), None)
    result = {"complete": True, "decision": existing or proposal, "idempotent": existing is not None, "write": write}
    if not write or existing is not None:
        return result, 0
    same_group = [
        row for row in decisions
        if str(row.get("parameter_calibration_group_id") or "") == str(proposal.get("parameter_calibration_group_id") or "")
    ]
    if same_group:
        return {
            "complete": False,
            "errors": [{"code": "calibration_decision_conflict", "field": str(proposal.get("parameter_calibration_group_id"))}],
        }, 1
    ledger["calibration_decisions"] = decisions + [proposal]
    ledger["updated_at"] = now()
    atomic_write_json(ledger_path, ledger)
    write_reconciliation_request(base, proposal["decision_id"])
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "experiment", "action": "parameter_profile_selection", "details": proposal})
    return result, 0


def proposed_cross_dataset_decision(base: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    track_id = str(evidence.get("track_id") or "").strip()
    group_id = str(evidence.get("paired_dataset_group_id") or "").strip()
    if not track_id:
        errors.append({"code": "outcome_missing", "field": "track_id"})
    if not group_id:
        errors.append({"code": "outcome_missing", "field": "paired_dataset_group_id"})
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    packet, packet_path = _calibration_packet(base, track_id)
    if not packet:
        errors.append({"code": "outcome_missing", "field": str(packet_path)})
        return {"errors": errors}
    expected_program_hash = str(program.get("semantic_sha256") or "")
    if str(evidence.get("program_claim_contract_sha256") or "") != expected_program_hash:
        errors.append({"code": "identity_mismatch", "field": "program_claim_contract_sha256"})
    contract = packet.get("parameter_transfer_contract")
    datasets = required_dataset_ids(program if isinstance(program, dict) else {}, packet)
    parameter_validation = validate_parameter_transfer_contract(contract, datasets)
    if not parameter_validation["complete"]:
        errors.extend(
            {"code": "parameter_contract_invalid", "field": str(item)}
            for item in parameter_validation.get("errors") or []
        )
    observations = [row for row in evidence.get("observations") or [] if isinstance(row, dict)]
    by_dataset: dict[str, dict[str, Any]] = {}
    allowed_comparisons = {
        "vs paper-reported baseline",
        "vs reproduced baseline",
        "vs matched reproduced baseline",
        "paper-report comparison not established",
    }
    for row in observations:
        dataset_id = str(row.get("dataset_id") or "").strip()
        if dataset_id in by_dataset:
            errors.append({"code": "duplicate_dataset_leg", "field": dataset_id})
        elif dataset_id:
            by_dataset[dataset_id] = row
    for dataset_id in datasets:
        row = by_dataset.get(dataset_id)
        if not row:
            errors.append({"code": "cross_dataset_group_incomplete", "field": dataset_id})
            continue
        for field in ["terminal_valid", "baseline_valid", "protocol_valid", "mechanism_pass", "support_pass"]:
            if not isinstance(row.get(field), bool):
                errors.append({"code": "outcome_missing", "field": f"{dataset_id}:{field}"})
        if row.get("terminal_valid") is True and _numeric(row.get("canonical_signed_delta")) is None:
            errors.append({"code": "outcome_missing", "field": f"{dataset_id}:canonical_signed_delta"})
        if str(row.get("comparison_source") or "") not in allowed_comparisons:
            errors.append({"code": "comparison_source_invalid", "field": dataset_id})
        if not present(row.get("result_ref")):
            errors.append({"code": "outcome_missing", "field": f"{dataset_id}:result_ref"})
    moderator_rows = packet.get("moderator_candidates") if isinstance(packet.get("moderator_candidates"), list) else []
    preregistered_moderators = {
        str(row.get("id") or "") if isinstance(row, dict) else str(row)
        for row in moderator_rows
        if present(row.get("id") if isinstance(row, dict) else row)
    }
    preregistered_normalization_children = {
        str(row.get("id") or "")
        for row in moderator_rows
        if isinstance(row, dict)
        and str(row.get("kind") or row.get("type") or "") in {"normalization", "scale_normalization"}
        and present(row.get("id"))
    }
    moderator_id = str(evidence.get("preregistered_moderator_id") or "").strip()
    normalization_child_id = str(evidence.get("qualified_normalization_child_id") or "").strip()
    if moderator_id and moderator_id not in preregistered_moderators:
        errors.append({"code": "posthoc_moderator_forbidden", "field": moderator_id})
    if normalization_child_id and normalization_child_id not in preregistered_normalization_children:
        errors.append({"code": "posthoc_normalization_child_forbidden", "field": normalization_child_id})
    if moderator_id and (
        evidence.get("moderator_prediction_matched") is not True
        or evidence.get("moderator_discriminator_changes_decision") is not True
    ):
        errors.append({"code": "moderator_not_decision_bearing", "field": moderator_id})
    stochastic_ambiguity = evidence.get("stochastic_ambiguity_band_crossed") is True
    if stochastic_ambiguity:
        if not present(evidence.get("stochastic_ambiguity_rule_ref")):
            errors.append({"code": "stochastic_ambiguity_not_preregistered", "field": "stochastic_ambiguity_rule_ref"})
        registered_seeds = {str(value) for value in evidence.get("registered_random_seeds") or []}
        if not registered_seeds or len(registered_seeds) >= 3:
            errors.append({"code": "stability_seed_budget_exhausted", "field": "registered_random_seeds"})
    if errors:
        return {"errors": errors}

    rows = [by_dataset[dataset_id] for dataset_id in datasets]
    all_valid = all(
        row.get("terminal_valid") is True
        and row.get("baseline_valid") is True
        and row.get("protocol_valid") is True
        for row in rows
    )
    coverage_complete = evidence.get("innovation_parameter_coverage_status") == "complete"
    all_supported = all(row.get("support_pass") is True and row.get("mechanism_pass") is True for row in rows)
    any_negative = any(row.get("support_pass") is False or row.get("mechanism_pass") is False for row in rows)
    scale_comparable = all(row.get("effective_strength_comparable") is True for row in rows)
    profile_status = str(evidence.get("parameter_profile_status") or packet.get("parameter_profile_status") or "")
    mode = str(contract.get("transfer_mode") or "") if isinstance(contract, dict) else ""
    single_value_exception = str(contract.get("single_value_exception") or "none") if isinstance(contract, dict) else "none"

    if not all_valid:
        verdict = "validity_or_baseline_failure"
        transition = "REFINE_PROTOCOL"
        program_status = "unresolved"
    elif not coverage_complete:
        verdict = "innovation_parameter_coverage_incomplete"
        transition = "RUN_ONE_DISAMBIGUATOR"
        program_status = "unresolved"
    elif any_negative and not scale_comparable:
        verdict = "parameter_scale_ambiguity"
        transition = "RUN_ONE_DISAMBIGUATOR"
        program_status = "unresolved"
    elif stochastic_ambiguity:
        verdict = "stochastic_ambiguity"
        transition = "RUN_ONE_DISAMBIGUATOR"
        program_status = "unresolved"
    elif all_supported:
        verdict = "cross_dataset_supported"
        transition = "PROCEED_TO_ABLATION_OR_CONFIRMATION"
        program_status = "supported"
    elif single_value_exception != "none" and profile_status != "frozen":
        verdict = "single_point_parameterization_refuted"
        transition = "SCOPE_CLAIM"
        program_status = "scoped"
    elif moderator_id:
        verdict = "moderator_supported_contradiction"
        transition = "PIVOT_TO_CHILD_TRACK"
        program_status = "unresolved"
    elif mode in {"shared_absolute", "shared_normalized"} and normalization_child_id:
        verdict = "shared_parameterization_refuted"
        transition = "PIVOT_TO_CHILD_TRACK"
        program_status = "unresolved"
    elif profile_status == "frozen" and mode == "dataset_calibrated":
        verdict = "calibrated_mechanism_refuted"
        transition = "RETIRE_TRACK"
        program_status = "refuted"
    elif any_negative:
        verdict = "core_transfer_refuted"
        transition = "SCOPE_CLAIM"
        program_status = "scoped"
    else:
        verdict = "core_transfer_refuted"
        transition = "SCOPE_CLAIM"
        program_status = "scoped"

    payload = {
        "schema_version": 1,
        "track_id": track_id,
        "paired_dataset_group_id": group_id,
        "program_claim_contract_ref": "orchestrator/PROGRAM_CLAIM_CONTRACT.json",
        "program_claim_contract_sha256": expected_program_hash,
        "parameter_transfer_contract_sha256": contract.get("parameter_transfer_contract_sha256") if isinstance(contract, dict) else None,
        "frozen_parameter_profile_sha256": evidence.get("frozen_parameter_profile_sha256") or packet.get("frozen_parameter_profile_sha256"),
        "parameter_transfer_mode": mode,
        "parameter_profile_status": profile_status,
        "innovation_parameter_coverage_status": evidence.get("innovation_parameter_coverage_status"),
        "required_dataset_ids": datasets,
        "observations": rows,
        "verdict": verdict,
        "recommended_transition": transition,
        "program_scientific_status": program_status,
        "claim_ceiling": evidence.get("claim_ceiling") or contract.get("claim_ceiling") if isinstance(contract, dict) else None,
        "source_evidence_refs": [str(row.get("result_ref")) for row in rows],
    }
    payload["decision_sha256"] = stable_hash(payload)
    payload["decision_id"] = "cross-dataset-" + payload["decision_sha256"][:16]
    payload["decided_at"] = now()
    return payload


def run_cross_dataset(base: Path, evidence_path: Path, write: bool) -> tuple[dict[str, Any], int]:
    evidence = read_json(evidence_path, {}) or {}
    if not isinstance(evidence, dict):
        return {"complete": False, "errors": [{"code": "outcome_missing", "field": str(evidence_path)}]}, 1
    proposal = proposed_cross_dataset_decision(base, evidence)
    if proposal.get("errors"):
        return {"complete": False, "errors": proposal["errors"]}, 1
    ledger_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    ledger = read_json(ledger_path, {}) or {}
    decisions = [row for row in ledger.get("cross_dataset_decisions") or [] if isinstance(row, dict)]
    existing = next((row for row in decisions if row.get("decision_id") == proposal.get("decision_id")), None)
    result = {"complete": True, "decision": existing or proposal, "idempotent": existing is not None, "write": write}
    if not write or existing is not None:
        return result, 0
    group_conflict = next(
        (
            row for row in decisions
            if str(row.get("track_id") or "") == str(proposal.get("track_id") or "")
            and str(row.get("paired_dataset_group_id") or "") == str(proposal.get("paired_dataset_group_id") or "")
        ),
        None,
    )
    if group_conflict:
        return {
            "complete": False,
            "errors": [{"code": "cross_dataset_decision_conflict", "field": str(proposal.get("paired_dataset_group_id"))}],
        }, 1
    aggregate_ref = f"analysis/CROSS_DATASET_DECISION.{proposal['paired_dataset_group_id']}.json"
    atomic_write_json(base / aggregate_ref, proposal)
    ledger["cross_dataset_decisions"] = decisions + [{**proposal, "aggregate_ref": aggregate_ref}]
    ledger["program_scientific_status"] = proposal["program_scientific_status"]
    ledger["updated_at"] = now()
    ledger["reconciliation_required"] = {
        "status": "pending",
        "reason": "cross_dataset_scientific_decision",
        "decision_id": proposal["decision_id"],
        "targets": ["orchestrator/TRACK_PLAN_MATRIX.json", "experiment/NEXT_EXPERIMENT_QUEUE.json"],
    }
    atomic_write_json(ledger_path, ledger)
    write_reconciliation_request(base, proposal["decision_id"])
    append_jsonl(
        base / "decision_log.jsonl",
        {"ts": now(), "stage": "experiment", "action": "cross_dataset_research_decision", "details": proposal},
    )
    return result, 0


def outcome_hash(outcome: dict[str, Any]) -> str:
    ignored = {"decision_id", "outcome_hash", "updated_at"}
    return stable_hash({key: value for key, value in outcome.items() if key not in ignored})


def selection_ref(payload: dict[str, Any]) -> str:
    return str(payload.get("selection_fingerprint") or payload.get("selected_primary_ref") or "").strip()


def find_run_entry(ledger: dict[str, Any], run_id: str) -> tuple[dict[str, Any] | None, int]:
    for index, row in enumerate(ledger.get("entries") or []):
        if not isinstance(row, dict):
            continue
        candidates = [row.get("run_id"), row.get("experiment_id")]
        if run_id in {str(value) for value in candidates if present(value)}:
            return row, index
    return None, -1


def outcome_path(base: Path, entry: dict[str, Any]) -> Path | None:
    explicit = entry.get("scientific_outcome_ref")
    if present(explicit):
        path = Path(str(explicit)).expanduser()
        return path if path.is_absolute() else base / path
    manifest_ref = entry.get("manifest")
    if present(manifest_ref):
        path = Path(str(manifest_ref)).expanduser()
        manifest_path = path if path.is_absolute() else base / path
        return manifest_path.parent / "SCIENTIFIC_OUTCOME.json"
    return None


def expected_identity(entry: dict[str, Any]) -> dict[str, str]:
    return {
        "run_id": str(entry.get("run_id") or entry.get("experiment_id") or "").strip(),
        "selected_idea_id": str(entry.get("selected_idea_id") or "").strip(),
        "track_id": str(entry.get("track_id") or "").strip(),
        "branch_id": str(entry.get("branch_id") or "").strip(),
        "queue_row_id": str(entry.get("queue_row_id") or "").strip(),
        "launch_identity_hash": str(entry.get("launch_identity_hash") or "").strip(),
        "selection_ref": selection_ref(entry),
    }


def validate_outcome(
    entry: dict[str, Any],
    outcome: dict[str, Any],
    base: Path | None = None,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for field in REQUIRED_OUTCOME_FIELDS:
        if field == "claim_limits":
            if field not in outcome:
                errors.append({"code": "outcome_missing", "field": field})
        elif not present(outcome.get(field)) and outcome.get(field) != 0:
            errors.append({"code": "outcome_missing", "field": field})
    if not selection_ref(outcome):
        errors.append({"code": "outcome_missing", "field": "selection_fingerprint or selected_primary_ref"})

    expected = expected_identity(entry)
    for field in IDENTITY_FIELDS:
        expected_value = expected.get(field) or ""
        observed = str(outcome.get(field) or "").strip()
        if expected_value and observed != expected_value:
            errors.append({"code": "identity_mismatch", "field": field, "expected": expected_value, "observed": observed})
    if expected["selection_ref"] and selection_ref(outcome) != expected["selection_ref"]:
        errors.append(
            {
                "code": "identity_mismatch",
                "field": "selection_fingerprint",
                "expected": expected["selection_ref"],
                "observed": selection_ref(outcome),
            }
        )

    outcome_class = normalized(outcome.get("outcome_class"))
    belief = normalized(outcome.get("belief_effect"))
    transition = str(outcome.get("recommended_transition") or "").strip().upper()
    rule = OUTCOME_RULES.get(outcome_class)
    if not rule:
        errors.append({"code": "invalid_transition", "field": "outcome_class", "observed": outcome_class})
        return errors
    if belief not in rule["belief"]:
        errors.append({"code": "invalid_transition", "field": "belief_effect", "observed": belief})
    if transition not in rule["transitions"]:
        errors.append({"code": "invalid_transition", "field": "recommended_transition", "observed": transition})
    if outcome_class == "valid_negative" and transition == "REFINE_IMPLEMENTATION" and not present(
        outcome.get("separate_implementation_defect_evidence_ref")
    ):
        errors.append(
            {
                "code": "invalid_transition",
                "field": "recommended_transition",
                "observed": "valid_negative cannot refine implementation without separate defect evidence",
            }
        )
    track_role = normalized(entry.get("track_role"))
    evidence_ceiling = normalized(entry.get("evidence_tier_ceiling"))
    non_primary_pilot = track_role in {"alternate", "risk_repair"} or evidence_ceiling == "pilot_only"
    if outcome_class == "valid_positive_candidate" and non_primary_pilot:
        if transition != "REQUEST_PRIMARY_RESELECTION":
            errors.append(
                {
                    "code": "invalid_transition",
                    "field": "recommended_transition",
                    "observed": "positive non-primary pilot must request primary reselection before matched rerun",
                }
            )
        if normalized(outcome.get("claim_effect")) not in {
            "candidate_only",
            "no_claim",
            "none",
            "reselection_candidate",
        }:
            errors.append(
                {
                    "code": "invalid_transition",
                    "field": "claim_effect",
                    "observed": "positive non-primary pilot cannot promote or close a claim",
                }
            )
    elif outcome_class == "valid_positive_candidate" and transition == "REQUEST_PRIMARY_RESELECTION":
        errors.append(
            {
                "code": "invalid_transition",
                "field": "recommended_transition",
                "observed": "current primary proceeds to ablation or confirmation without reselection",
            }
        )

    validity = outcome.get("validity") if isinstance(outcome.get("validity"), dict) else {}
    validity_fields = ["protocol_valid", "spec_valid", "evaluator_valid", "canonical_result_valid"]
    for field in validity_fields:
        if not isinstance(validity.get(field), bool):
            errors.append({"code": "outcome_missing", "field": f"validity.{field}"})
    if rule["requires_valid_result"] and not all(validity.get(field) is True for field in validity_fields):
        errors.append({"code": "invalid_transition", "field": "validity", "observed": "scientific outcome requires all validity gates"})
    if outcome_class == "protocol_invalid" and all(validity.get(field) is True for field in validity_fields):
        errors.append({"code": "invalid_transition", "field": "validity", "observed": "protocol_invalid cannot pass every validity gate"})
    for field in ["operational_attempt", "scientific_revision"]:
        value = outcome.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append({"code": "budget_counter_conflict", "field": field, "observed": str(value)})
    if base is not None:
        program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
        claim_role = str(entry.get("claim_role") or outcome.get("claim_role") or "")
        if (
            str(program.get("enforcement_mode") or "legacy") == "enforced"
            and str(program.get("claim_scope") or "") == "cross_dataset_method"
            and claim_role == "method_candidate"
        ):
            if str(outcome.get("program_claim_contract_sha256") or "") != str(program.get("semantic_sha256") or ""):
                errors.append({"code": "identity_mismatch", "field": "program_claim_contract_sha256"})
            for field in ["dataset_role", "paired_dataset_group_id", "claim_ceiling"]:
                if not present(outcome.get(field)):
                    errors.append({"code": "outcome_missing", "field": field})
            if _numeric(outcome.get("canonical_signed_delta")) is None:
                errors.append({"code": "outcome_missing", "field": "canonical_signed_delta"})
            if not isinstance(outcome.get("mechanism_gate_pass"), bool):
                errors.append({"code": "outcome_missing", "field": "mechanism_gate_pass"})
            if str(outcome.get("comparison_source") or "") not in {
                "vs paper-reported baseline",
                "vs reproduced baseline",
                "vs matched reproduced baseline",
                "paper-report comparison not established",
            }:
                errors.append({"code": "comparison_source_invalid", "field": "comparison_source"})
    return errors


def track_state(ledger: dict[str, Any], track_id: str) -> dict[str, Any]:
    for row in ledger.get("track_states") or []:
        if isinstance(row, dict) and str(row.get("track_id") or "") == track_id:
            return row
    return {}


def track_max_revisions(base: Path, track_id: str, prior: dict[str, Any]) -> int:
    value = prior.get("max_scientific_revisions")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
    for row in rows_from_payload(matrix):
        if str(row.get("track_id") or "") != track_id:
            continue
        contract = row.get("hypothesis_contract") if isinstance(row.get("hypothesis_contract"), dict) else {}
        value = contract.get("max_scientific_revisions")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 2


def transition_lifecycle(transition: str) -> str:
    return {
        "WAIT_OR_RECONCILE_BACKEND": "operational_wait",
        "REFINE_IMPLEMENTATION": "implementation_repair",
        "REFINE_PROTOCOL": "protocol_repair",
        "PROCEED_TO_ABLATION_OR_CONFIRMATION": "supported_pending_confirmation",
        "REQUEST_PRIMARY_RESELECTION": "reselection_candidate",
        "RUN_ONE_DISAMBIGUATOR": "disambiguation_pending",
        "PIVOT_TO_CHILD_TRACK": "pivot_required",
        "RETIRE_TRACK": "retired",
        "SCOPE_CLAIM": "scoped",
        "CONCLUDE_PROGRAM": "concluded",
    }[transition]


def validate_budget(base: Path, ledger: dict[str, Any], outcome: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    errors: list[dict[str, str]] = []
    track_id = str(outcome.get("track_id") or "")
    prior = track_state(ledger, track_id)
    prior_revision = int(prior.get("scientific_revision_index") or 0)
    prior_operational = int(prior.get("operational_attempt") or 0)
    revision = outcome.get("scientific_revision")
    operational = outcome.get("operational_attempt")
    transition = str(outcome.get("recommended_transition") or "").strip().upper()
    max_revisions = track_max_revisions(base, track_id, prior)

    if isinstance(revision, int):
        if revision < prior_revision or revision > max_revisions:
            errors.append({"code": "budget_counter_conflict", "field": "scientific_revision", "observed": str(revision)})
        if transition in SCIENTIFIC_TRANSITIONS and revision != prior_revision + 1:
            errors.append(
                {
                    "code": "budget_counter_conflict",
                    "field": "scientific_revision",
                    "observed": f"{revision}; expected {prior_revision + 1} for {transition}",
                }
            )
    if isinstance(operational, int) and operational < prior_operational:
        errors.append({"code": "budget_counter_conflict", "field": "operational_attempt", "observed": str(operational)})

    disambiguator_count = int(prior.get("disambiguator_count") or 0)
    if transition == "RUN_ONE_DISAMBIGUATOR" and disambiguator_count >= 1:
        errors.append({"code": "budget_counter_conflict", "field": "disambiguator_count", "observed": "default limit 1 exhausted"})
    if transition in SCIENTIFIC_TRANSITIONS and prior_revision >= max_revisions:
        errors.append({"code": "budget_counter_conflict", "field": "max_scientific_revisions", "observed": str(max_revisions)})
    return errors, {
        "prior": prior,
        "prior_revision": prior_revision,
        "prior_operational_attempt": prior_operational,
        "max_scientific_revisions": max_revisions,
        "disambiguator_count": disambiguator_count,
    }


def proposed_decision(base: Path, ledger: dict[str, Any], entry: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    digest = outcome_hash(outcome)
    for decision in ledger.get("experiment_decisions") or []:
        if not isinstance(decision, dict):
            continue
        if str(decision.get("run_id") or "") == str(outcome.get("run_id") or "") and decision.get("outcome_hash") == digest:
            return {**decision, "idempotent": True}

    budget_errors, budget = validate_budget(base, ledger, outcome)
    if budget_errors:
        return {"errors": budget_errors}
    transition = str(outcome.get("recommended_transition") or "").strip().upper()
    prior = budget["prior"]
    prior_revision = budget["prior_revision"]
    revision = int(outcome.get("scientific_revision") or 0)
    decision_id = "research-decision-" + stable_hash(
        {"run_id": outcome.get("run_id"), "outcome_hash": digest, "prior_revision": prior_revision}
    )[:16]
    return {
        "decision_id": decision_id,
        "run_id": outcome.get("run_id"),
        "experiment_id": entry.get("experiment_id"),
        "selected_idea_id": outcome.get("selected_idea_id"),
        "track_id": outcome.get("track_id"),
        "track_role": entry.get("track_role"),
        "evidence_tier_ceiling": entry.get("evidence_tier_ceiling"),
        "branch_id": outcome.get("branch_id"),
        "queue_row_id": outcome.get("queue_row_id"),
        "selection_fingerprint": selection_ref(outcome),
        "launch_identity_hash": outcome.get("launch_identity_hash"),
        "outcome_hash": digest,
        "outcome_class": normalized(outcome.get("outcome_class")),
        "prior_belief_state": prior.get("belief_state") or "untested",
        "belief_effect": normalized(outcome.get("belief_effect")),
        "next_belief_state": normalized(outcome.get("belief_effect")) if normalized(outcome.get("belief_effect")) != "none" else prior.get("belief_state") or "untested",
        "transition": transition,
        "next_track_lifecycle": transition_lifecycle(transition),
        "reselection_required": transition == "REQUEST_PRIMARY_RESELECTION",
        "matched_baseline_rerun_required": transition == "REQUEST_PRIMARY_RESELECTION",
        "operational_attempt": int(outcome.get("operational_attempt") or 0),
        "prior_scientific_revision": prior_revision,
        "scientific_revision_index": revision,
        "max_scientific_revisions": budget["max_scientific_revisions"],
        "disambiguator_count": budget["disambiguator_count"] + (1 if transition == "RUN_ONE_DISAMBIGUATOR" else 0),
        "claim_effect": outcome.get("claim_effect"),
        "claim_limits": outcome.get("claim_limits"),
        "evidence_refs": [entry.get("scientific_outcome_ref"), outcome.get("canonical_result_ref"), *(outcome.get("raw_evidence_refs") or [])],
        "reason": outcome.get("evidence_rationale"),
        "decided_at": now(),
    }


def update_idea_summary(ledger: dict[str, Any], decision: dict[str, Any]) -> None:
    idea_id = str(decision.get("selected_idea_id") or "")
    for row in ledger.get("decisions") or []:
        if not isinstance(row, dict) or str(row.get("idea_id") or "") != idea_id:
            continue
        row["belief_state"] = decision["next_belief_state"]
        row["scientific_revision_index"] = decision["scientific_revision_index"]
        row["last_scientific_decision_id"] = decision["decision_id"]
        row["last_scientific_outcome"] = decision["outcome_class"]
        row["next_action"] = decision["transition"]
        transition = decision["transition"]
        if transition in {"REFINE_IMPLEMENTATION", "REFINE_PROTOCOL"}:
            row["lifecycle_status"] = "repair_needed"
        elif transition == "REQUEST_PRIMARY_RESELECTION":
            row["lifecycle_status"] = "reselection_candidate"
            row["reselection_required"] = True
            row["matched_baseline_rerun_required"] = True
        elif transition in {"PIVOT_TO_CHILD_TRACK", "SCOPE_CLAIM"}:
            row["lifecycle_status"] = "advance_with_constraints"
        elif transition in {"RETIRE_TRACK", "CONCLUDE_PROGRAM"}:
            row["lifecycle_status"] = "parked"
            row["can_reenter"] = False
        return


def apply_decision(base: Path, ledger: dict[str, Any], entry_index: int, decision: dict[str, Any]) -> dict[str, Any]:
    if decision.get("idempotent"):
        return ledger
    ledger.setdefault("schema_version", 2)
    ledger["schema_version"] = max(2, int(ledger.get("schema_version") or 1))
    ledger.setdefault("experiment_decisions", []).append(decision)
    states = [row for row in ledger.get("track_states") or [] if isinstance(row, dict)]
    states = [row for row in states if str(row.get("track_id") or "") != str(decision.get("track_id") or "")]
    states.append(
        {
            "track_id": decision.get("track_id"),
            "idea_id": decision.get("selected_idea_id"),
            "belief_state": decision.get("next_belief_state"),
            "lifecycle_status": decision.get("next_track_lifecycle"),
            "operational_attempt": decision.get("operational_attempt"),
            "scientific_revision_index": decision.get("scientific_revision_index"),
            "max_scientific_revisions": decision.get("max_scientific_revisions"),
            "disambiguator_count": decision.get("disambiguator_count"),
            "last_run_id": decision.get("run_id"),
            "last_decision_id": decision.get("decision_id"),
            "last_outcome_class": decision.get("outcome_class"),
            "updated_at": now(),
        }
    )
    ledger["track_states"] = states
    update_idea_summary(ledger, decision)
    ledger["updated_at"] = now()
    ledger["reconciliation_required"] = {
        "status": "pending",
        "reason": "scientific_lifecycle_changed",
        "decision_id": decision.get("decision_id"),
        "targets": ["orchestrator/TRACK_PLAN_MATRIX.json", "experiment/NEXT_EXPERIMENT_QUEUE.json"],
    }
    return ledger


def strong_paper_workflow(base: Path) -> bool:
    state = read_json(base / "goal_state.json", {}) or {}
    policy = read_json(base / "autopilot_policy.json", {}) or {}
    goal_type = state.get("goal_type") or policy.get("goal_type") or "paper_producing_top_tier"
    claim_mode = state.get("claim_mode") or policy.get("claim_mode") or "strong_paper_claims"
    return goal_type == "paper_producing_top_tier" and claim_mode == "strong_paper_claims"


def queue_live_rows(base: Path) -> list[str]:
    queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {}) or {}
    live: list[str] = []
    for row in queue.get("rows") or []:
        if isinstance(row, dict) and normalized(row.get("status")) in LIVE_QUEUE_STATUSES:
            live.append(str(row.get("row_id") or row.get("id") or "unknown"))
    return live


def program_proposal(base: Path, ledger: dict[str, Any], experiment_ledger: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    states = [row for row in ledger.get("track_states") or [] if isinstance(row, dict)]
    matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
    active_ids = [
        str(row.get("track_id"))
        for row in rows_from_payload(matrix)
        if present(row.get("track_id"))
        and (row.get("selected_for_review") is True or normalized(row.get("track_role")) in {"primary", "alternate", "risk_repair"})
    ]
    if not active_ids:
        active_ids = [str(row.get("track_id")) for row in states if present(row.get("track_id"))]
    state_by_id = {str(row.get("track_id")): row for row in states if present(row.get("track_id"))}
    nonterminal = [track_id for track_id in active_ids if normalized(state_by_id.get(track_id, {}).get("lifecycle_status")) not in TERMINAL_TRACK_STATES]
    if not active_ids or nonterminal:
        errors.append({"code": "unresolved_live_work", "field": "track_states", "observed": ",".join(nonterminal) or "no active track states"})
    live_rows = queue_live_rows(base)
    if live_rows:
        errors.append({"code": "unresolved_live_work", "field": "queue", "observed": ",".join(live_rows)})

    accepted_run_ids = {
        str(row.get("run_id"))
        for row in ledger.get("experiment_decisions") or []
        if isinstance(row, dict) and present(row.get("run_id"))
    }
    unresolved_results: list[str] = []
    for entry in experiment_ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        status = normalized(entry.get("status"))
        if status not in {"completed", "failed", "budget_stopped", "terminal", "regressed"}:
            continue
        run_id = str(entry.get("run_id") or entry.get("experiment_id") or "")
        if run_id and run_id not in accepted_run_ids:
            unresolved_results.append(run_id)
    if unresolved_results:
        errors.append({"code": "unresolved_live_work", "field": "scientific_outcomes", "observed": ",".join(unresolved_results)})

    context = ledger.get("terminal_program_context") if isinstance(ledger.get("terminal_program_context"), dict) else {}
    for field in ["remaining_claim_scope", "mandatory_downgrade", "budget_or_value_rationale", "target_stage"]:
        if not present(context.get(field)):
            errors.append({"code": "outcome_missing", "field": f"terminal_program_context.{field}"})
    evaluator_refs = context.get("evaluator_evidence_refs") or []
    if strong_paper_workflow(base) and not present(evaluator_refs):
        errors.append({"code": "outcome_missing", "field": "terminal_program_context.evaluator_evidence_refs"})
    if context.get("target_stage") not in {"analysis", "idea_gate"}:
        errors.append({"code": "invalid_transition", "field": "terminal_program_context.target_stage", "observed": str(context.get("target_stage"))})
    if errors:
        return {"errors": errors}

    outcomes = [normalized(row.get("outcome_class")) for row in ledger.get("experiment_decisions") or [] if isinstance(row, dict)]
    if any(value == "valid_positive_candidate" for value in outcomes):
        status = "supported_result_available"
    elif outcomes and all(value == "valid_negative" for value in outcomes):
        status = "core_hypotheses_refuted"
    elif any(value == "protocol_invalid" for value in outcomes):
        status = "protocol_unresolvable"
    elif any(value in {"valid_inconclusive", "budget_stopped_no_scientific_conclusion"} for value in outcomes):
        status = "inconclusive_budget_exhausted"
    else:
        status = "no_valid_gain"
    evidence_refs = sorted(
        {
            str(ref)
            for row in ledger.get("experiment_decisions") or []
            if isinstance(row, dict)
            for ref in row.get("evidence_refs") or []
            if present(ref)
        }
    )
    payload = {
        "status": status,
        "terminal": True,
        "active_track_ids": active_ids,
        "final_track_states": [state_by_id[track_id] for track_id in active_ids],
        "evidence_refs": evidence_refs,
        "remaining_claim_scope": context.get("remaining_claim_scope"),
        "mandatory_downgrade": context.get("mandatory_downgrade"),
        "budget_or_value_rationale": context.get("budget_or_value_rationale"),
        "target_stage": context.get("target_stage"),
        "evaluator_evidence_refs": evaluator_refs,
        "improvement_claim_allowed": status == "supported_result_available" and bool(experiment_ledger.get("best_run")),
        "decided_at": now(),
    }
    payload["decision_id"] = "program-decision-" + stable_hash({key: value for key, value in payload.items() if key != "decided_at"})[:16]
    return payload


def write_reconciliation_request(base: Path, decision_id: str) -> None:
    atomic_write_json(
        base / "control/SCIENTIFIC_RECONCILIATION_REQUEST.json",
        {
            "schema_version": 1,
            "status": "pending",
            "decision_id": decision_id,
            "requested_at": now(),
            "targets": ["orchestrator/TRACK_PLAN_MATRIX.json", "experiment/NEXT_EXPERIMENT_QUEUE.json"],
        },
    )


def run_one(base: Path, run_id: str, write: bool) -> tuple[dict[str, Any], int]:
    experiment_path = base / "coder/EXPERIMENT_LEDGER.json"
    decision_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    experiment_ledger = read_json(experiment_path, {}) or {}
    decision_ledger = read_json(decision_path, {}) or {}
    entry, index = find_run_entry(experiment_ledger, run_id)
    if not entry:
        return {"complete": False, "errors": [{"code": "outcome_missing", "field": f"run:{run_id}"}]}, 1
    path = outcome_path(base, entry)
    outcome = read_json(path, {}) if path else {}
    if not isinstance(outcome, dict) or not outcome:
        return {"complete": False, "errors": [{"code": "outcome_missing", "field": "SCIENTIFIC_OUTCOME.json"}]}, 1
    errors = validate_outcome(entry, outcome, base)
    if errors:
        return {"complete": False, "run_id": run_id, "errors": errors}, 1
    decision = proposed_decision(base, decision_ledger, entry, outcome)
    if decision.get("errors"):
        return {"complete": False, "run_id": run_id, "errors": decision["errors"]}, 1
    result = {"complete": True, "run_id": run_id, "decision": decision, "write": write}
    if not write or decision.get("idempotent"):
        return result, 0
    decision_ledger = apply_decision(base, decision_ledger, index, decision)
    atomic_write_json(decision_path, decision_ledger)
    write_reconciliation_request(base, decision["decision_id"])
    append_jsonl(
        base / "decision_log.jsonl",
        {"ts": now(), "stage": "experiment", "action": "research_decision", "details": decision},
    )
    return result, 0


def run_program(base: Path, write: bool) -> tuple[dict[str, Any], int]:
    decision_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    decision_ledger = read_json(decision_path, {}) or {}
    experiment_ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json", {}) or {}
    proposal = program_proposal(base, decision_ledger, experiment_ledger)
    if proposal.get("errors"):
        return {"complete": False, "errors": proposal["errors"]}, 1
    existing = decision_ledger.get("program_decision") if isinstance(decision_ledger.get("program_decision"), dict) else {}
    idempotent = existing.get("decision_id") == proposal.get("decision_id")
    result = {"complete": True, "program_decision": proposal, "idempotent": idempotent, "write": write}
    if not write or idempotent:
        return result, 0
    decision_ledger["program_decision"] = proposal
    decision_ledger["updated_at"] = now()
    atomic_write_json(decision_path, decision_ledger)
    write_reconciliation_request(base, proposal["decision_id"])
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "experiment", "action": "terminal_program_decision", "details": proposal})
    return result, 0


def replenishment_basis(base: Path, ledger: dict[str, Any], program: dict[str, Any]) -> tuple[str, list[str]]:
    refs: set[str] = set()
    for collection in ["cross_dataset_decisions", "experiment_decisions"]:
        for row in ledger.get(collection) or []:
            if not isinstance(row, dict):
                continue
            for key in ["decision_id", "aggregate_ref", "parent_contradiction_ref"]:
                if present(row.get(key)):
                    refs.add(str(row.get(key)))
            for key in ["source_evidence_refs", "evidence_refs"]:
                for ref in row.get(key) or []:
                    if present(ref):
                        refs.add(str(ref))
    scorecard = read_json(base / "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json", {}) or {}
    payload = {
        "program_claim_contract_sha256": program.get("semantic_sha256"),
        "program_scientific_status": ledger.get("program_scientific_status") or "unresolved",
        "selection_revision": scorecard.get("selection_revision") or scorecard.get("selection_fingerprint"),
        "decision_and_evidence_refs": sorted(refs),
    }
    revision_id = explicit_active_program_revision_id(ledger)
    if revision_id:
        payload["program_revision_id"] = revision_id
    return stable_hash(payload), sorted(refs)


def replenishment_proposal(base: Path, frontier: dict[str, Any] | None = None) -> dict[str, Any]:
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    policy = read_json(base / "autopilot_policy.json", {}) or {}
    state = read_json(base / "goal_state.json", {}) or {}
    if frontier is None:
        from experiment_next_actions import frontier_status  # local import avoids a writer dependency at module load

        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {}) or {}
        matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
        frontier = frontier_status(queue, matrix, base.parent)
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    if str(program.get("contract_status") or "") != "active":
        errors.append({"code": "program_claim_inactive", "field": "contract_status"})
    if str(program.get("enforcement_mode") or "legacy") != "enforced":
        errors.append({"code": "program_claim_not_enforced", "field": "enforcement_mode"})
    if str(program.get("claim_scope") or "") != "cross_dataset_method":
        errors.append({"code": "program_claim_scope_ineligible", "field": "claim_scope"})
    scientific_status = str(ledger.get("program_scientific_status") or "unresolved")
    if scientific_status not in {"unresolved", "screened", "supported"}:
        errors.append({"code": "program_scientific_status_terminal", "field": scientific_status})
    if int(frontier.get("method_admission_deficit") or 0) <= 0:
        errors.append({"code": "method_portfolio_satisfied", "field": "method_admission_deficit"})
    supply = candidate_supply_status(base, ledger, program)
    if frontier.get("method_fillable_candidate_ids") and supply.get("current") is True:
        errors.append({"code": "committed_method_candidate_fillable", "field": "method_fillable_candidate_ids"})
    elif frontier.get("method_fillable_candidate_ids"):
        warnings.append("stale or unbound method candidates ignored for the active program revision")
    live_rows = decision_bearing_live_rows(base)
    if live_rows:
        errors.append({"code": "decision_bearing_rows_exist", "field": ",".join(sorted(live_rows))})
    autonomy = str(state.get("autonomy_level") or policy.get("autonomy_level") or "")
    scope = workflow_scope(state, policy)
    warnings.extend(scope["warnings"])
    goal_type = str(scope["goal_type"])
    if autonomy != "full_auto_bounded" or not goal_type.startswith("paper_producing_"):
        errors.append({"code": "autonomy_scope_ineligible", "field": "goal_state"})
    if policy.get("allow_autonomous_candidate_replenishment") is False:
        errors.append({"code": "candidate_replenishment_disabled", "field": "autopilot_policy"})
    if isinstance(ledger.get("program_decision"), dict) and ledger["program_decision"].get("terminal") is True:
        errors.append({"code": "terminal_program_closure", "field": "program_decision"})
    search_budget = program.get("search_budget") if isinstance(program.get("search_budget"), dict) else {}
    max_events = int(search_budget.get("max_targeted_replenishments") or 0)
    events = current_revision_events(ledger, program)
    if max_events <= 0 or len(events) >= max_events:
        errors.append({"code": "replenishment_budget_exhausted", "field": "max_targeted_replenishments"})
    basis_sha, refs = replenishment_basis(base, ledger, program)
    existing = next((row for row in events if row.get("replenishment_basis_sha256") == basis_sha), None)
    if existing is not None:
        errors.append({"code": "replenishment_basis_unchanged", "field": basis_sha})
    event = {
        "event_id": f"replenishment-{basis_sha[:16]}",
        "status": "authorized",
        "program_revision_id": active_program_revision_id(ledger) or program_revision_id(program),
        "replenishment_basis_sha256": basis_sha,
        "source_decision_and_evidence_refs": refs,
        "program_claim_contract_sha256": program.get("semantic_sha256"),
        "program_scientific_status": scientific_status,
        "method_admission_deficit": frontier.get("method_admission_deficit"),
        "portfolio_admission_deficit": frontier.get("portfolio_admission_deficit"),
        "selection_revision": frontier.get("selection_revision"),
        "budget_index": int(existing.get("budget_index") or 0) if existing is not None else len(events) + 1,
        "authorized_at": now(),
    }
    return {
        "complete": not errors,
        "errors": errors,
        "warnings": warnings,
        "candidate_supply": supply,
        "event": event,
        "idempotent": existing is not None,
    }


def run_replenishment(base: Path, write: bool) -> tuple[dict[str, Any], int]:
    proposal = replenishment_proposal(base)
    if not proposal.get("complete"):
        return proposal, 1
    result = {**proposal, "write": write}
    if not write:
        return result, 0
    ledger_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    ledger = read_json(ledger_path, {}) or {}
    events = [row for row in ledger.get("replenishment_events") or [] if isinstance(row, dict)]
    event = proposal["event"]
    if any(row.get("event_id") == event.get("event_id") for row in events):
        return {**result, "idempotent": True}, 0
    ledger["replenishment_events"] = events + [event]
    ledger["updated_at"] = now()
    atomic_write_json(ledger_path, ledger)
    append_jsonl(
        base / "decision_log.jsonl",
        {"ts": now(), "stage": "experiment", "action": "authorize_targeted_replenishment", "details": event},
    )
    return result, 0


def program_revision_activation_proposal(base: Path) -> dict[str, Any]:
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    state = read_json(base / "goal_state.json", {}) or {}
    policy = read_json(base / "autopilot_policy.json", {}) or {}
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    contract_sha = str(program.get("semantic_sha256") or "").strip()
    revision_id = program_revision_id(program)
    basis_id = str(program.get("replacement_basis_decision_id") or "").strip()
    if str(program.get("contract_status") or "") != "active":
        errors.append({"code": "replacement_contract_inactive", "field": "contract_status"})
    if str(program.get("enforcement_mode") or "legacy") != "enforced":
        errors.append({"code": "replacement_contract_not_enforced", "field": "enforcement_mode"})
    if not basis_id:
        errors.append({"code": "replacement_basis_decision_missing", "field": "replacement_basis_decision_id"})
    authority = validate_replacement_authority(base.parent, program)
    for error in authority.get("errors") or []:
        errors.append({"code": "replacement_authority_invalid", "field": str(error)})

    scope = workflow_scope(state, policy)
    warnings.extend(scope["warnings"])
    autonomy = str(state.get("autonomy_level") or policy.get("autonomy_level") or "").strip()
    if autonomy != "full_auto_bounded" or not str(scope["goal_type"]).startswith("paper_producing_"):
        errors.append({"code": "autonomy_scope_ineligible", "field": "goal_state"})
    if policy.get("allow_autonomous_candidate_replenishment") is False:
        errors.append({"code": "candidate_replenishment_disabled", "field": "autopilot_policy"})

    active_sha = str(ledger.get("active_program_contract_sha256") or "").strip()
    active_revision = active_program_revision_id(ledger)
    scientific_status = str(ledger.get("program_scientific_status") or "unresolved").strip()
    if active_sha == contract_sha and active_revision == revision_id and scientific_status in {
        "unresolved",
        "screened",
        "supported",
    }:
        return {
            "complete": True,
            "errors": [],
            "warnings": warnings,
            "idempotent": True,
            "program_revision_id": revision_id,
            "program_claim_contract_sha256": contract_sha,
            "replacement_authority": authority,
        }

    old_route = ledger.get("program_route_decision") if isinstance(ledger.get("program_route_decision"), dict) else {}
    if not old_route:
        errors.append({"code": "replacement_basis_route_missing", "field": basis_id})
    elif str(old_route.get("decision_id") or "").strip() != basis_id:
        errors.append({"code": "replacement_basis_route_mismatch", "field": str(old_route.get("decision_id") or "")})
    if old_route.get("terminal_for_project") is True:
        errors.append({"code": "terminal_project_cannot_reopen", "field": basis_id})
    live_rows = decision_bearing_live_rows(base)
    if live_rows:
        errors.append({"code": "decision_bearing_rows_exist", "field": ",".join(live_rows)})

    transition_id = "program-revision-" + stable_hash(
        {"program_revision_id": revision_id, "contract_sha256": contract_sha, "basis_decision_id": basis_id}
    )[:16]
    previous = {
        "program_scientific_status": ledger.get("program_scientific_status"),
        "program_route_decision": copy.deepcopy(old_route) if old_route else None,
        "program_decision": copy.deepcopy(ledger.get("program_decision"))
        if isinstance(ledger.get("program_decision"), dict)
        else None,
        "active_scientific_portfolio": copy.deepcopy(ledger.get("active_scientific_portfolio"))
        if isinstance(ledger.get("active_scientific_portfolio"), dict)
        else None,
        "selected_idea_id": ledger.get("selected_idea_id"),
        "selected_primary_idea_id": ledger.get("selected_primary_idea_id"),
        "selected_track_id": ledger.get("selected_track_id"),
        "selection_fingerprint": ledger.get("selection_fingerprint"),
        "active_program_contract_id": ledger.get("active_program_contract_id"),
        "active_program_contract_sha256": ledger.get("active_program_contract_sha256"),
    }
    return {
        "complete": not errors,
        "errors": errors,
        "warnings": warnings,
        "idempotent": False,
        "transition_id": transition_id,
        "basis_decision_id": basis_id,
        "program_revision_id": revision_id,
        "program_claim_contract_id": program.get("contract_id"),
        "program_claim_contract_revision": program.get("contract_revision"),
        "program_claim_contract_sha256": contract_sha,
        "unresolved_paper_decision_id": program.get("unresolved_paper_decision_id"),
        "previous": previous,
        "replacement_authority": authority,
    }


def run_program_revision_activation(base: Path, write: bool) -> tuple[dict[str, Any], int]:
    proposal = program_revision_activation_proposal(base)
    if not proposal.get("complete"):
        return proposal, 1
    result = {**proposal, "write": write}
    if not write or proposal.get("idempotent"):
        return result, 0

    ledger_path = base / "ideation/IDEA_DECISION_LEDGER.json"
    ledger = read_json(ledger_path, {}) or {}
    history = [row for row in ledger.get("program_revision_history") or [] if isinstance(row, dict)]
    if any(row.get("transition_id") == proposal.get("transition_id") for row in history):
        return {**result, "idempotent": True}, 0
    activated_at = now()
    history_entry = {
        "transition_id": proposal["transition_id"],
        "activated_at": activated_at,
        "basis_decision_id": proposal["basis_decision_id"],
        "previous": proposal["previous"],
        "next": {
            "program_revision_id": proposal["program_revision_id"],
            "program_claim_contract_id": proposal["program_claim_contract_id"],
            "program_claim_contract_revision": proposal["program_claim_contract_revision"],
            "program_claim_contract_sha256": proposal["program_claim_contract_sha256"],
            "program_scientific_status": "unresolved",
            "unresolved_paper_decision_id": proposal.get("unresolved_paper_decision_id"),
        },
        "interpretation": (
            "The previous route remains terminal in history. Unresolved status applies only to the reviewed "
            "replacement program revision and does not restore a retired candidate."
        ),
    }
    ledger["program_revision_history"] = history + [history_entry]
    ledger["program_contract_transitions"] = [
        row for row in ledger.get("program_contract_transitions") or [] if isinstance(row, dict)
    ] + [
        {
            "transition_id": proposal["transition_id"],
            "at": activated_at,
            "from": {
                "program_scientific_status": proposal["previous"].get("program_scientific_status"),
                "decision_id": proposal["basis_decision_id"],
                "selection_fingerprint": proposal["previous"].get("selection_fingerprint"),
            },
            "to": {
                "program_scientific_status": "unresolved",
                "contract_id": proposal["program_claim_contract_id"],
                "contract_revision": proposal["program_claim_contract_revision"],
                "contract_sha256": proposal["program_claim_contract_sha256"],
            },
        }
    ]
    ledger["active_program_revision"] = {
        "program_revision_id": proposal["program_revision_id"],
        "program_claim_contract_id": proposal["program_claim_contract_id"],
        "program_claim_contract_revision": proposal["program_claim_contract_revision"],
        "program_claim_contract_sha256": proposal["program_claim_contract_sha256"],
        "replacement_basis_decision_id": proposal["basis_decision_id"],
        "unresolved_paper_decision_id": proposal.get("unresolved_paper_decision_id"),
        "activated_at": activated_at,
    }
    ledger["program_revision_id"] = proposal["program_revision_id"]
    ledger["active_program_contract_id"] = proposal["program_claim_contract_id"]
    ledger["active_program_contract_revision"] = proposal["program_claim_contract_revision"]
    ledger["active_program_contract_sha256"] = proposal["program_claim_contract_sha256"]
    ledger["current_unresolved_paper_decision_id"] = proposal.get("unresolved_paper_decision_id")
    ledger["program_scientific_status"] = "unresolved"
    ledger.pop("program_route_decision", None)
    ledger.pop("program_decision", None)
    ledger["selected_idea_id"] = None
    ledger["selected_primary_idea_id"] = None
    ledger["selected_track_id"] = None
    ledger["selection_fingerprint"] = None

    old_portfolio = proposal["previous"].get("active_scientific_portfolio") or {}
    quarantined = []
    for key in ["primary", "alternates", "shortlist_only", "diagnostic_only"]:
        value = old_portfolio.get(key)
        values = value if isinstance(value, list) else [value] if present(value) else []
        for item in values:
            if present(item) and str(item) not in quarantined:
                quarantined.append(str(item))
    contract = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    budget = contract.get("search_budget") if isinstance(contract.get("search_budget"), dict) else {}
    ledger["active_scientific_portfolio"] = {
        "primary": None,
        "alternates": [],
        "shortlist_only": [],
        "diagnostic_only": [],
        "legacy_quarantined": quarantined,
        "retired": list(old_portfolio.get("retired") or []),
        "max_active_tracks": int(budget.get("portfolio_capacity_target") or 4),
        "method_portfolio_target": int(budget.get("method_portfolio_target") or 1),
        "claim_ceiling": "no improvement claim until the replacement program is supported",
    }
    ledger["replenishment_intervention_required"] = {
        "status": "resolved",
        "reason": "reviewed replacement contract is active and bound to a new program revision",
        "max_targeted_replenishments": int(budget.get("max_targeted_replenishments") or 0),
        "cards_generated": 0,
        "new_track_admitted": False,
        "resolved_at": activated_at,
    }
    ledger["reconciliation_required"] = {
        "status": "pending",
        "reason": "replacement_program_candidate_supply_required",
        "decision_id": proposal["transition_id"],
        "targets": [
            "ideation/EXPERIMENT_IDEA_POOL.json",
            "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
            "ideation/IDEA_TRACK_SEEDS.json",
            "orchestrator/TRACK_PLAN_MATRIX.json",
            "experiment/NEXT_EXPERIMENT_QUEUE.json",
        ],
        "requested_at": activated_at,
    }
    ledger["updated_at"] = activated_at
    atomic_write_json(ledger_path, ledger)
    write_reconciliation_request(base, proposal["transition_id"])
    append_jsonl(
        base / "decision_log.jsonl",
        {"ts": activated_at, "stage": "idea_gate", "action": "activate_program_revision", "details": history_entry},
    )
    return result, 0


def program_recovery_status(base: Path, frontier: dict[str, Any] | None = None) -> dict[str, Any]:
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    ledger = read_json(base / "ideation/IDEA_DECISION_LEDGER.json", {}) or {}
    state = read_json(base / "goal_state.json", {}) or {}
    policy = read_json(base / "autopilot_policy.json", {}) or {}
    contract_status = str(program.get("contract_status") or "").strip().lower()
    basis_id = str(program.get("replacement_basis_decision_id") or "").strip()
    route = ledger.get("program_route_decision") if isinstance(ledger.get("program_route_decision"), dict) else {}
    if not basis_id and contract_status != "superseded":
        return {"applicable": False, "phase": "none", "class": "none", "action": None}

    scope = workflow_scope(state, policy)
    autonomy = str(state.get("autonomy_level") or policy.get("autonomy_level") or "").strip()
    scope_ok = autonomy == "full_auto_bounded" and str(scope["goal_type"]).startswith("paper_producing_")
    policy_ok = policy.get("allow_autonomous_candidate_replenishment") is not False
    route_id = str(route.get("decision_id") or basis_id).strip()
    authorization = replenishment_authorization(base, route_id)
    if route.get("terminal_for_project") is True:
        return {
            "applicable": True,
            "phase": "project_terminal",
            "class": "hard_stop",
            "action": "conclude_program",
            "reason": "The scientific route is terminal for the project; replenishment cannot reopen it.",
            "authorization": authorization,
            "warnings": scope["warnings"],
        }
    if contract_status == "superseded":
        authorized = authorization.get("complete") is True and int(authorization.get("max_targeted_replenishments") or 0) > 0
        if authorized and scope_ok and policy_ok and route.get("terminal_for_project") is not True:
            return {
                "applicable": True,
                "phase": "review_and_commit_replacement_contract",
                "class": "auto_repairable",
                "action": "recover_replenishment_route",
                "reason": (
                    "The old program contract is superseded and the project-nonterminal route has direct budget authority; "
                    "construct, review, and CAS-commit one changed-basis replacement program."
                ),
                "authorization": authorization,
                "warnings": scope["warnings"],
            }
        reason = "Replacement-program recovery requires direct user budget authority and a bounded paper-producing autonomy scope."
        return {
            "applicable": True,
            "phase": "authorization_required",
            "class": "hard_stop",
            "action": "request_replenishment_budget_authorization",
            "reason": reason,
            "authorization": authorization,
            "warnings": scope["warnings"],
        }

    if contract_status != "active" or str(program.get("enforcement_mode") or "legacy") != "enforced":
        return {
            "applicable": True,
            "phase": "replacement_contract_invalid",
            "class": "hard_stop",
            "action": "repair_replacement_contract_authority",
            "reason": "The replacement contract is not active and enforced.",
            "warnings": scope["warnings"],
        }

    active_sha = str(ledger.get("active_program_contract_sha256") or "").strip()
    current_sha = str(program.get("semantic_sha256") or "").strip()
    scientific_status = str(ledger.get("program_scientific_status") or "unresolved").strip()
    if active_sha != current_sha or scientific_status not in {"unresolved", "screened", "supported"}:
        activation = program_revision_activation_proposal(base)
        return {
            "applicable": True,
            "phase": "activate_program_revision",
            "class": "auto_repairable" if activation.get("complete") else "hard_stop",
            "action": "recover_replenishment_route" if activation.get("complete") else "repair_replacement_contract_authority",
            "reason": (
                "The reviewed replacement contract is active, but the decision ledger is not yet bound to its unresolved program revision."
            ),
            "activation": activation,
            "warnings": scope["warnings"],
        }

    if frontier is None:
        from experiment_next_actions import frontier_status

        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json", {}) or {}
        matrix = read_json(base / "orchestrator/TRACK_PLAN_MATRIX.json", {}) or {}
        frontier = frontier_status(queue, matrix, base.parent)
    supply = candidate_supply_status(base, ledger, program)
    if supply.get("current") is True or int(frontier.get("method_admission_deficit") or 0) <= 0:
        return {
            "applicable": False,
            "phase": "current_candidate_supply_available",
            "class": "none",
            "action": None,
            "candidate_supply": supply,
            "warnings": scope["warnings"],
        }
    existing_revision_events = current_revision_events(ledger, program)
    if existing_revision_events:
        return {
            "applicable": True,
            "phase": "materialize_candidate_supply_from_existing_event",
            "class": "auto_repairable",
            "action": "recover_replenishment_route",
            "reason": (
                "A replenishment event already exists for the active program revision, but its candidate supply is "
                "missing, stale, or unbound; reconcile that supply without consuming another transaction."
            ),
            "candidate_supply": supply,
            "existing_replenishment_event": existing_revision_events[-1],
            "warnings": scope["warnings"],
        }
    proposal = replenishment_proposal(base, frontier)
    codes = {str(row.get("code") or "") for row in proposal.get("errors") or [] if isinstance(row, dict)}
    if proposal.get("complete"):
        phase = "authorize_and_generate_candidate_supply"
        klass = "auto_repairable"
        action = "recover_replenishment_route"
        reason = "The active replacement program has no current-revision candidate supply; authorize one changed basis and generate it."
    elif codes == {"replenishment_basis_unchanged"}:
        phase = "materialize_candidate_supply_from_existing_event"
        klass = "auto_repairable"
        action = "recover_replenishment_route"
        reason = "A replenishment event already exists for this basis, but its current-revision candidate supply is missing or stale."
    elif "decision_bearing_rows_exist" in codes:
        phase = "wait_for_decision_bearing_rows"
        klass = "none"
        action = None
        reason = "Current decision-bearing experiment rows must be reconciled before candidate replenishment."
    else:
        phase = "replenishment_blocked"
        klass = "hard_stop"
        action = "request_replenishment_budget_authorization" if "replenishment_budget_exhausted" in codes else "repair_replenishment_authority"
        reason = "Candidate replenishment remains blocked by scientific authority or contract invariants."
    return {
        "applicable": klass != "none",
        "phase": phase,
        "class": klass,
        "action": action,
        "reason": reason,
        "candidate_supply": supply,
        "replenishment": proposal,
        "warnings": scope["warnings"],
    }


def run_program_recovery_status(base: Path, write: bool) -> tuple[dict[str, Any], int]:
    if write:
        return {
            "complete": False,
            "errors": [{"code": "program_recovery_status_is_read_only", "field": "--write"}],
        }, 1
    status = program_recovery_status(base)
    return {"complete": True, "status": status}, 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--run-id")
    target.add_argument("--all-terminal", action="store_true")
    target.add_argument("--calibration-evidence")
    target.add_argument("--cross-dataset-evidence")
    target.add_argument("--replenishment", action="store_true")
    target.add_argument("--program-recovery-status", action="store_true")
    target.add_argument("--activate-program-revision", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    base = ar(args.project)
    lock = decision_lock(base) if args.write else nullcontext()
    with lock:
        if args.calibration_evidence:
            evidence_path = Path(args.calibration_evidence).expanduser()
            if not evidence_path.is_absolute():
                evidence_path = base / evidence_path
            result, code = run_calibration(base, evidence_path, args.write)
        elif args.cross_dataset_evidence:
            evidence_path = Path(args.cross_dataset_evidence).expanduser()
            if not evidence_path.is_absolute():
                evidence_path = base / evidence_path
            result, code = run_cross_dataset(base, evidence_path, args.write)
        elif args.program_recovery_status:
            result, code = run_program_recovery_status(base, args.write)
        elif args.activate_program_revision:
            result, code = run_program_revision_activation(base, args.write)
        elif args.replenishment:
            result, code = run_replenishment(base, args.write)
        elif args.all_terminal:
            result, code = run_program(base, args.write)
        else:
            result, code = run_one(base, str(args.run_id), args.write)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
