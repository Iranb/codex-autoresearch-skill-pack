#!/usr/bin/env python3
"""Strict reader for one committed external-material pre-idea gate."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import idea_campaign as campaign_tool


GATE_REF = "ideation/PRE_IDEA_EVIDENCE_GATE.json"
CAMPAIGN_REF = "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ExternalGateError(RuntimeError):
    """The external-material commit is missing, stale, unsafe, or malformed."""


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant {token!r} is forbidden")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r} is forbidden")
        result[key] = value
    return result


def _finite_json(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_json(child) for child in value.values())
    if isinstance(value, list):
        return all(_finite_json(child) for child in value)
    return True


def _read_strict_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_object_without_duplicates,
        )
    except FileNotFoundError as exc:
        raise ExternalGateError(f"{label} is missing: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ExternalGateError(f"{label} is not strict finite JSON: {exc}") from exc
    if not isinstance(payload, dict) or not _finite_json(payload):
        raise ExternalGateError(f"{label} must be a strict finite JSON object")
    return payload, hashlib.sha256(raw).hexdigest()


def _safe_ref(base: Path, ref: Any, label: str) -> tuple[Path, str]:
    if not isinstance(ref, str):
        raise ExternalGateError(f"{label} must be a string")
    token = ref.strip()
    relative = Path(token)
    if not token or "\\" in token or relative.is_absolute() or ".." in relative.parts:
        raise ExternalGateError(f"{label} is empty or unsafe")
    resolved_base = base.resolve()
    resolved = (resolved_base / relative).resolve()
    try:
        resolved.relative_to(resolved_base)
    except ValueError as exc:
        raise ExternalGateError(f"{label} escapes .autoreskill") from exc
    return resolved, token


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ExternalGateError(f"{label} must be a lowercase 64-hex SHA-256 string")
    token = value.strip()
    if not SHA_RE.fullmatch(token):
        raise ExternalGateError(f"{label} must be a lowercase 64-hex SHA-256")
    return token


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ExternalGateError(f"{label} must be a non-empty string list")
    rows = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(rows) != len(value) or len(rows) != len(set(rows)):
        raise ExternalGateError(f"{label} must contain unique non-empty strings")
    return rows


def _expect(payload: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    def same(observed: Any, value: Any) -> bool:
        if isinstance(value, bool):
            return observed is value
        if isinstance(value, int):
            return isinstance(observed, int) and not isinstance(observed, bool) and observed == value
        return observed == value

    mismatched = [key for key, value in expected.items() if not same(payload.get(key), value)]
    if mismatched:
        raise ExternalGateError(f"{label} has stale or invalid fields: {', '.join(mismatched)}")


def _content_ref(stem: str, digest: str) -> str:
    return f"ideation/committed/{stem}.{digest}.json"


def load_gate_source_mode(base: Path) -> tuple[str, dict[str, Any]]:
    """Read the gate strictly before choosing the legacy or external route."""

    base = base.expanduser().resolve()
    gate_path = base / GATE_REF
    if not gate_path.exists():
        return "papernexus", {}
    gate, _ = _read_strict_object(gate_path, "pre-idea gate")
    mode = gate.get("evidence_source_mode", "papernexus")
    if not isinstance(mode, str):
        raise ExternalGateError("pre-idea gate evidence_source_mode must be a string")
    return mode.strip().lower(), gate


def load_external_gate_commit(base: Path) -> dict[str, Any]:
    """Read and validate the complete current external-material commit chain."""

    base = base.expanduser().resolve()
    gate_path = base / GATE_REF
    gate, gate_sha = _read_strict_object(gate_path, "external pre-idea gate")
    _expect(
        gate,
        {
            "schema_version": 1,
            "status": "passed",
            "evidence_source_mode": "external_material",
            "lane_attempts_satisfied": True,
            "screening_completed": True,
            "allowed_next_action": "generate_experiment_idea_pool",
            "commit_layout": "content_addressed_v1",
            "campaign_ref": CAMPAIGN_REF,
        },
        "external pre-idea gate",
    )

    campaign_sha = _sha(gate.get("campaign_sha256"), "gate.campaign_sha256")
    lint_sha = _sha(gate.get("lint_sha256"), "gate.lint_sha256")
    slot_sha = _sha(gate.get("slot_map_sha256"), "gate.slot_map_sha256")
    campaign_path, campaign_ref = _safe_ref(base, gate.get("campaign_ref"), "gate.campaign_ref")
    lint_path, lint_ref = _safe_ref(base, gate.get("lint_ref"), "gate.lint_ref")
    slot_path, slot_ref = _safe_ref(
        base,
        gate.get("innovation_slot_map_path"),
        "gate.innovation_slot_map_path",
    )
    if campaign_ref != CAMPAIGN_REF:
        raise ExternalGateError(f"gate.campaign_ref must be {CAMPAIGN_REF}")
    if lint_ref != _content_ref("NON_PAPERNEXUS_IDEA_LINT", lint_sha):
        raise ExternalGateError("gate.lint_ref must be the content-addressed path named by lint_sha256")
    if slot_ref != _content_ref("INNOVATION_SLOT_MAP", slot_sha):
        raise ExternalGateError(
            "gate.innovation_slot_map_path must be the content-addressed path named by slot_map_sha256"
        )
    if gate.get("slot_map_ref") != slot_ref:
        raise ExternalGateError("gate.slot_map_ref must equal innovation_slot_map_path")

    campaign, observed_campaign_sha = _read_strict_object(campaign_path, "external campaign")
    lint, observed_lint_sha = _read_strict_object(lint_path, "committed external lint")
    slot, observed_slot_sha = _read_strict_object(slot_path, "committed external slot map")
    for label, expected, observed in (
        ("campaign", campaign_sha, observed_campaign_sha),
        ("lint", lint_sha, observed_lint_sha),
        ("slot map", slot_sha, observed_slot_sha),
    ):
        if observed != expected:
            raise ExternalGateError(f"committed {label} hash does not match the gate")

    if not isinstance(campaign.get("campaign_id"), str):
        raise ExternalGateError("campaign.campaign_id must be a string")
    campaign_id = campaign["campaign_id"].strip()
    campaign_revision = campaign.get("campaign_revision")
    if not campaign_id:
        raise ExternalGateError("campaign.campaign_id must be non-empty")
    if (
        not isinstance(campaign_revision, int)
        or isinstance(campaign_revision, bool)
        or campaign_revision < 1
    ):
        raise ExternalGateError("campaign.campaign_revision must be a positive integer")
    _expect(
        campaign,
        {
            "schema_version": 1,
            "source_mode": "external_material",
            "papernexus_used": False,
        },
        "external campaign",
    )
    _expect(
        gate,
        {"campaign_id": campaign_id, "campaign_revision": campaign_revision},
        "external pre-idea gate",
    )

    candidates = campaign.get("candidates")
    if not isinstance(candidates, list) or not candidates or not all(isinstance(row, dict) for row in candidates):
        raise ExternalGateError("campaign.candidates must be a non-empty object list")
    candidate_ids = [str(row.get("id") or "").strip() for row in candidates]
    if any(not item for item in candidate_ids) or len(candidate_ids) != len(set(candidate_ids)):
        raise ExternalGateError("campaign candidate ids must be unique and non-empty")
    admitted = _string_list(campaign.get("admitted_candidate_ids"), "campaign.admitted_candidate_ids")
    if not set(admitted) <= set(candidate_ids):
        raise ExternalGateError("campaign admitted candidate ids must resolve to canonical candidates")
    if _string_list(gate.get("admitted_candidate_ids"), "gate.admitted_candidate_ids") != admitted:
        raise ExternalGateError("gate admitted candidate ids must match the campaign")

    common_lineage = {
        "campaign_ref": CAMPAIGN_REF,
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign_id,
        "campaign_revision": campaign_revision,
    }
    _expect(
        lint,
        {
            "schema_version": 1,
            "complete": True,
            "status": "passed",
            **common_lineage,
            "slot_map_ref": slot_ref,
            "slot_map_sha256": slot_sha,
        },
        "committed external lint",
    )
    _expect(
        slot,
        {"schema_version": 1, "source_mode": "external_material", **common_lineage},
        "committed external slot map",
    )
    if _string_list(lint.get("admitted_candidate_ids"), "lint.admitted_candidate_ids") != admitted:
        raise ExternalGateError("lint admitted candidate ids must match the campaign")
    if _string_list(slot.get("admitted_candidate_ids"), "slot_map.admitted_candidate_ids") != admitted:
        raise ExternalGateError("slot-map admitted candidate ids must match the campaign")
    insights = slot.get("insight_clusters")
    if not isinstance(insights, list) or not all(isinstance(row, dict) for row in insights):
        raise ExternalGateError("slot_map.insight_clusters must be an object list")
    insight_ids = [str(row.get("external_candidate_id") or "").strip() for row in insights]
    if insight_ids != admitted:
        raise ExternalGateError("slot-map insight candidates must exactly match admitted campaign candidates")

    # Re-run the authoritative offline campaign validator.  A self-consistent
    # attacker-authored hash chain is not a passed campaign unless it produces
    # the same lint facts as the validator that created the commit.
    fresh_lint = campaign_tool.lint_campaign(str(base.parent))
    if fresh_lint.get("complete") is not True or fresh_lint.get("status") != "passed":
        raise ExternalGateError("the committed external campaign no longer passes full validation")
    expected_lint_keys = set(fresh_lint) | {"slot_map_ref", "slot_map_sha256"}
    if set(lint) != expected_lint_keys:
        raise ExternalGateError("committed external lint fields do not match a complete validator result")
    for key, value in fresh_lint.items():
        if key != "checked_at" and lint.get(key) != value:
            raise ExternalGateError(f"committed external lint field {key!r} is stale or invalid")
    if not isinstance(lint.get("checked_at"), str) or not lint["checked_at"].strip():
        raise ExternalGateError("committed external lint checked_at must be non-empty")

    expected_slot = campaign_tool.build_slot_map(campaign, campaign_sha, admitted)
    expected_slot["campaign_id"] = campaign_id
    expected_slot["campaign_revision"] = campaign_revision
    if set(slot) != set(expected_slot):
        raise ExternalGateError("committed external slot-map fields do not match the campaign projection")
    for key, value in expected_slot.items():
        if key != "generated_at" and slot.get(key) != value:
            raise ExternalGateError(f"committed external slot-map field {key!r} has drifted from the campaign")
    if not isinstance(slot.get("generated_at"), str) or not slot["generated_at"].strip():
        raise ExternalGateError("committed external slot-map generated_at must be non-empty")

    if gate.get("lane_coverage") != fresh_lint.get("evidence_lane_counts"):
        raise ExternalGateError("gate.lane_coverage must match the committed campaign lint")
    if gate.get("claim_limits") != campaign.get("claim_limits"):
        raise ExternalGateError("gate.claim_limits must match the committed campaign")
    if not isinstance(gate.get("committed_at"), str) or not gate["committed_at"].strip():
        raise ExternalGateError("gate.committed_at must be non-empty")

    return {
        "gate": gate,
        "gate_path": gate_path,
        "gate_sha256": gate_sha,
        "campaign": campaign,
        "campaign_path": campaign_path,
        "campaign_ref": campaign_ref,
        "campaign_sha256": campaign_sha,
        "lint": lint,
        "lint_path": lint_path,
        "lint_ref": lint_ref,
        "lint_sha256": lint_sha,
        "slot_map": slot,
        "slot_path": slot_path,
        "slot_ref": slot_ref,
        "slot_sha256": slot_sha,
        "admitted_candidate_ids": admitted,
        "identity": (gate_sha, campaign_sha, lint_sha, slot_sha, campaign_id, campaign_revision),
    }


def require_same_external_gate_commit(previous: dict[str, Any], current: dict[str, Any]) -> None:
    if previous.get("identity") != current.get("identity"):
        raise ExternalGateError("external-material commit changed while the consumer was building output")
