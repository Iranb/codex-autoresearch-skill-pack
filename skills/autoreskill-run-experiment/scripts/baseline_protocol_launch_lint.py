#!/usr/bin/env python3
"""Preflight guard for baseline-aligned AutoResearch experiment launches.

This linter separates environment/data probes from launchable experiment runs.
It intentionally rejects ambiguous frozen-feature pilots and repeated
off-protocol sweeps before GPU time is spent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALIGNED_STATUSES = {"baseline_aligned", "pre_registered_feature_protocol"}
OFF_PROTOCOL_STATUSES = {"off_protocol", "off_protocol_probe", "diagnostic_only"}
SMALL_MODEL_MARKERS = [
    "resnet18",
    "torchvision.models",
    "torchvision resnet",
    "sklearn",
    "small_model",
    "tiny_model",
    "feature_pilot",
    "domainnet_feature_pilot",
    "3 images per class",
    "three images per class",
]
FEATURE_WORDS = ["frozen feature", "frozen-feature", "feature pilot", "frozen backbone", "frozen-backbone"]
REQUIRED_FEATURE_PROTOCOL = [
    "protocol_id",
    "baseline_code_id",
    "feature_extractor",
    "extraction_entrypoint",
    "dataset",
    "data_split",
    "metric_parser",
    "evidence_scope",
]
VALID_PARAMETER_ROLES = {
    "baseline_protocol",
    "innovation_load_bearing",
    "innovation_derived",
    "diagnostic_only",
}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def safe_component(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and Path(value).name == value


def text_blob(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    except TypeError:
        return str(value).lower()


def mentions_any(value: Any, markers: list[str]) -> list[str]:
    blob = text_blob(value)
    return [marker for marker in markers if marker in blob]


def is_archived_infra_failure(entry: Any) -> bool:
    """Ignore repaired setup failures that mention packages but are not method runs."""
    if not isinstance(entry, dict):
        return False
    status_blob = " ".join(
        str(entry.get(key) or "").strip().lower()
        for key in ["status", "canonical_eval_status", "failure_class", "next_action"]
    )
    if entry.get("counts_as_method_result") is not False:
        return False
    if "failed_archived" not in status_blob and "archived" not in status_blob:
        return False
    infra_markers = [
        "runtime_dependency_missing_before_training",
        "dependency_repaired",
        "full_protocol_relaunched",
        "environment",
        "dependency",
    ]
    return any(marker in status_blob for marker in infra_markers)


def nested_get(mapping: Any, *keys: str) -> Any:
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def validate_feature_protocol(protocol: Any, baseline_code: dict[str, Any], missing: list[str], warnings: list[str]) -> None:
    if not isinstance(protocol, dict):
        missing.append("EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol required for frozen-feature/backbone pilots")
        return
    for key in REQUIRED_FEATURE_PROTOCOL:
        if not present(protocol.get(key)):
            missing.append(f"EXPERIMENT_REVIEW_PACKET.pre_registered_feature_protocol.{key}")
    baseline_code_id = str(baseline_code.get("code_id") or "").strip()
    if baseline_code_id and str(protocol.get("baseline_code_id") or "").strip() != baseline_code_id:
        missing.append("pre_registered_feature_protocol.baseline_code_id must match locked baseline_code.code_id")
    evidence_scope = str(protocol.get("evidence_scope") or "").strip().lower()
    extractor_markers = mentions_any(protocol.get("feature_extractor"), SMALL_MODEL_MARKERS)
    if extractor_markers and evidence_scope != "diagnostic_only":
        missing.append(
            "pre_registered_feature_protocol uses small/convenience extractor markers "
            f"{extractor_markers}; mark diagnostic_only or use locked baseline feature path"
        )
    if evidence_scope == "diagnostic_only":
        warnings.append("pre_registered_feature_protocol is diagnostic_only; it cannot support candidate/promotion evidence")


def validate_parameter_roles(
    base: Path,
    review: dict[str, Any],
    candidate: dict[str, Any] | None,
    missing: list[str],
) -> None:
    program = read_json(base / "orchestrator/PROGRAM_CLAIM_CONTRACT.json", {}) or {}
    if str(program.get("enforcement_mode") or "legacy") != "enforced":
        return
    if str(program.get("claim_scope") or "") != "cross_dataset_method":
        return
    if str(review.get("claim_role") or "") != "method_candidate":
        return
    inventory = review.get("parameter_role_inventory")
    if not isinstance(inventory, list) or not inventory:
        missing.append("EXPERIMENT_REVIEW_PACKET.parameter_role_inventory")
        return
    load_bearing: list[dict[str, Any]] = []
    for index, row in enumerate(inventory):
        if not isinstance(row, dict):
            missing.append(f"parameter_role_inventory[{index}] must be an object")
            continue
        role = str(row.get("parameter_role") or "")
        if role not in VALID_PARAMETER_ROLES:
            missing.append(f"parameter_role_inventory[{index}].parameter_role is invalid")
        if not present(row.get("parameter_name")):
            missing.append(f"parameter_role_inventory[{index}].parameter_name")
        if role == "baseline_protocol" and row.get("dataset_specific_allowed") is not True:
            missing.append(f"parameter_role_inventory[{index}] baseline_protocol must declare dataset_specific_allowed=true")
        if role == "innovation_load_bearing":
            load_bearing.append(row)
    contract = review.get("parameter_transfer_contract")
    if len(load_bearing) != 1 or not isinstance(contract, dict):
        missing.append("exactly one classified innovation_load_bearing parameter and its transfer contract are required")
        return
    if load_bearing[0].get("parameter_name") != contract.get("parameter_name"):
        missing.append("classified innovation_load_bearing parameter must match parameter_transfer_contract.parameter_name")
    if load_bearing[0].get("parameter_transfer_contract_sha256") != contract.get("parameter_transfer_contract_sha256"):
        missing.append("classified innovation_load_bearing parameter must bind parameter_transfer_contract_sha256")
    if candidate:
        candidate_name = candidate.get("load_bearing_parameter_name") or candidate.get("innovation_parameter_name")
        if present(candidate_name) and str(candidate_name) != str(contract.get("parameter_name") or ""):
            missing.append("candidate_run load-bearing parameter is not the reviewed innovation parameter")


def existing_off_protocol(base: Path) -> list[str]:
    hits: list[str] = []
    ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json", {})
    for idx, entry in enumerate((ledger or {}).get("entries") or []):
        if is_archived_infra_failure(entry):
            continue
        blob = text_blob(entry)
        if "off_protocol" in blob or "off-protocol" in blob or mentions_any(entry, SMALL_MODEL_MARKERS):
            hits.append(f"coder/EXPERIMENT_LEDGER.json entries[{idx}]")
    for remote_path in sorted(base.glob("coder/experiments/**/REMOTE_RUN.json")):
        remote = read_json(remote_path, {})
        blob = text_blob(remote)
        if "off_protocol" in blob or "off-protocol" in blob or mentions_any(remote, SMALL_MODEL_MARKERS):
            try:
                hits.append(str(remote_path.relative_to(base)))
            except ValueError:
                hits.append(str(remote_path))
    return hits


def dataset_subset_drift(base: Path) -> list[str]:
    hits: list[str] = []
    for remote_path in sorted(base.glob("coder/experiments/**/REMOTE_RUN.json")):
        remote = read_json(remote_path, {})
        blob = text_blob(remote)
        if "missing from" in blob and ("quickdraw" in blob or "infograph" in blob):
            try:
                hits.append(str(remote_path.relative_to(base)))
            except ValueError:
                hits.append(str(remote_path))
    return hits


def validate_candidate(
    candidate: dict[str, Any],
    review: dict[str, Any],
    baseline_code: dict[str, Any],
    feature_protocol: Any,
    missing: list[str],
    warnings: list[str],
) -> bool:
    status = str(candidate.get("protocol_status") or candidate.get("status") or "").strip().lower()
    diagnostic = candidate.get("diagnostic_only") is True
    if not status:
        missing.append("candidate_run.protocol_status must be baseline_aligned, pre_registered_feature_protocol, or diagnostic_only")
    elif status in OFF_PROTOCOL_STATUSES:
        if not diagnostic or candidate.get("user_approved") is not True:
            missing.append("off-protocol candidate_run requires diagnostic_only=true and user_approved=true")
        if candidate.get("target_sweep") is True or present(candidate.get("targets")):
            missing.append("off-protocol candidate_run cannot launch target sweeps")
        warnings.append("off-protocol candidate_run is diagnostic only and cannot be promoted")
        return False
    elif status not in ALIGNED_STATUSES:
        missing.append("candidate_run.protocol_status must be baseline_aligned or pre_registered_feature_protocol")

    locked_code_id = str(baseline_code.get("code_id") or "").strip()
    candidate_code_id = str(candidate.get("baseline_code_id") or nested_get(candidate, "baseline_code", "code_id") or "").strip()
    if locked_code_id and candidate_code_id and candidate_code_id != locked_code_id:
        missing.append("candidate_run baseline_code_id drifts from locked baseline")
    if locked_code_id and not candidate_code_id:
        missing.append("candidate_run.baseline_code_id")

    for key, candidate_key in [
        ("dataset", "dataset"),
        ("data_split", "data_split"),
        ("primary_metric", "primary_metric"),
    ]:
        expected = review.get(key)
        actual = candidate.get(candidate_key)
        if present(expected) and present(actual) and actual != expected:
            missing.append(f"candidate_run.{candidate_key} drifts from EXPERIMENT_REVIEW_PACKET.{key}")

    if status == "pre_registered_feature_protocol":
        if not isinstance(feature_protocol, dict):
            missing.append("candidate_run uses pre_registered_feature_protocol but review packet lacks it")
        elif str(candidate.get("feature_protocol_id") or "").strip() != str(feature_protocol.get("protocol_id") or "").strip():
            missing.append("candidate_run.feature_protocol_id must match pre_registered_feature_protocol.protocol_id")

    markers = mentions_any(candidate, SMALL_MODEL_MARKERS)
    if markers and status != "pre_registered_feature_protocol":
        missing.append(f"candidate_run contains off-protocol/small-model markers: {markers}")
    if markers and isinstance(feature_protocol, dict):
        fp_markers = mentions_any(feature_protocol, SMALL_MODEL_MARKERS)
        if not fp_markers:
            missing.append(f"candidate_run small-model markers are not declared in pre_registered_feature_protocol: {markers}")

    command = str(candidate.get("command") or candidate.get("train_command") or candidate.get("eval_command") or "")
    train_entry = str(baseline_code.get("train_entrypoint") or "").strip()
    eval_entry = str(baseline_code.get("eval_entrypoint") or "").strip()
    adapter = candidate.get("baseline_adapter_of") == locked_code_id
    if status == "baseline_aligned" and command and train_entry and eval_entry:
        if train_entry not in command and eval_entry not in command and not adapter:
            missing.append("baseline_aligned candidate_run command must call locked train/eval entrypoint or declare baseline_adapter_of")
    return status in ALIGNED_STATUSES


def lint(project: str, candidate_run: str | None, track_id: str | None = None) -> dict[str, Any]:
    base = ar(project)
    candidate_payload = read_json(Path(candidate_run).expanduser(), None) if candidate_run else None
    resolved_track_id = str(
        track_id
        or ((candidate_payload or {}).get("track_id") if isinstance(candidate_payload, dict) else "")
        or ""
    ).strip()
    if resolved_track_id and not safe_component(resolved_track_id):
        return {
            "complete": False,
            "status": "incomplete",
            "missing": ["track_id must be one safe path component"],
            "warnings": [],
            "candidate_run": candidate_run,
        }
    review_ref = (
        f"planner/tracks/{resolved_track_id}/EXPERIMENT_REVIEW_PACKET.json"
        if resolved_track_id
        else "planner/EXPERIMENT_REVIEW_PACKET.json"
    )
    innovation_ref = (
        f"orchestrator/tracks/{resolved_track_id}/INNOVATION_PACKET.json"
        if resolved_track_id
        else "orchestrator/INNOVATION_PACKET.json"
    )
    review = read_json(base / review_ref, {}) or {}
    innovation = read_json(base / innovation_ref, {}) or {}
    manifests = [
        payload
        for path in sorted(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json"))
        if isinstance((payload := read_json(path, {}) or {}), dict)
        and (not resolved_track_id or str(payload.get("track_id") or "").strip() == resolved_track_id)
    ]
    missing: list[str] = []
    warnings: list[str] = []

    baseline_code = review.get("baseline_code") if isinstance(review.get("baseline_code"), dict) else {}
    if resolved_track_id and str(review.get("track_id") or "").strip() != resolved_track_id:
        missing.append(f"{review_ref}.track_id must match requested track")
    role = str(review.get("track_role") or innovation.get("track_role") or "").strip().lower()
    ceiling = str(review.get("evidence_tier_ceiling") or innovation.get("evidence_tier_ceiling") or "").strip()
    if role in {"alternate", "risk_repair"} and ceiling != "pilot_only":
        missing.append(f"{review_ref}.evidence_tier_ceiling must be pilot_only for non-primary tracks")
    if baseline_code.get("locked") is not True:
        missing.append("EXPERIMENT_REVIEW_PACKET.baseline_code.locked must be true")
    for key in ["code_id", "resolved_path", "train_entrypoint", "eval_entrypoint"]:
        if not present(baseline_code.get(key)):
            missing.append(f"EXPERIMENT_REVIEW_PACKET.baseline_code.{key}")

    feature_protocol = review.get("pre_registered_feature_protocol")
    plan_mentions_features = mentions_any({"review": review, "innovation": innovation, "manifests": manifests}, FEATURE_WORDS)
    if plan_mentions_features:
        validate_feature_protocol(feature_protocol, baseline_code, missing, warnings)

    candidate_aligned = False
    candidate_run_used = candidate_run
    if candidate_run:
        candidate = candidate_payload
        if not isinstance(candidate, dict):
            missing.append(f"candidate_run invalid JSON: {candidate_run}")
        else:
            if resolved_track_id and str(candidate.get("track_id") or "").strip() != resolved_track_id:
                missing.append("candidate_run.track_id must match the selected per-track packet")
            if role in {"alternate", "risk_repair"} and candidate.get("evidence_tier") != "pilot_only":
                missing.append("non-primary candidate_run.evidence_tier must be pilot_only")
            candidate_aligned = validate_candidate(candidate, review, baseline_code, feature_protocol, missing, warnings)
    else:
        for candidate_path in sorted(base.glob("coder/experiments/**/*CANDIDATE_RUN*.json")):
            candidate = read_json(candidate_path, None)
            if not isinstance(candidate, dict):
                continue
            if resolved_track_id and str(candidate.get("track_id") or "").strip() != resolved_track_id:
                continue
            trial_missing: list[str] = []
            trial_warnings: list[str] = []
            aligned = validate_candidate(candidate, review, baseline_code, feature_protocol, trial_missing, trial_warnings)
            if aligned and not trial_missing:
                candidate_aligned = True
                try:
                    candidate_run_used = str(candidate_path.relative_to(base))
                except ValueError:
                    candidate_run_used = str(candidate_path)
                warnings.append(f"auto-detected corrective candidate_run: {candidate_run_used}")
                break

    validate_parameter_roles(
        base,
        review,
        candidate_payload if isinstance(candidate_payload, dict) else None,
        missing,
    )

    off_protocol_hits = existing_off_protocol(base)
    if off_protocol_hits and not candidate_aligned:
        missing.append(
            "existing off-protocol probe requires a corrective baseline_aligned or pre_registered_feature_protocol candidate-run spec before more launches: "
            + "; ".join(off_protocol_hits[:6])
        )
        if len(off_protocol_hits) > 6:
            warnings.append(f"{len(off_protocol_hits) - 6} additional off-protocol hits omitted")

    subset_hits = dataset_subset_drift(base)
    if subset_hits and not candidate_aligned:
        missing.append(
            "existing DomainNet subset drift/missing domains require plan revision or full data materialization before target sweeps: "
            + "; ".join(subset_hits[:4])
        )

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "candidate_run": candidate_run_used,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--candidate-run")
    parser.add_argument("--track-id")
    args = parser.parse_args()
    out = lint(args.project, args.candidate_run, args.track_id)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
