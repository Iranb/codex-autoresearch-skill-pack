#!/usr/bin/env python3
"""Validate external campaign identity propagation across AutoResearch stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


CAMPAIGN_REL = "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"
GATE_REL = "ideation/PRE_IDEA_EVIDENCE_GATE.json"
POOL_REL = "ideation/EXPERIMENT_IDEA_POOL.json"
SCORECARD_REL = "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json"
SEEDS_REL = "ideation/IDEA_TRACK_SEEDS.json"
LEDGER_REL = "ideation/IDEA_DECISION_LEDGER.json"
MATRIX_REL = "orchestrator/TRACK_PLAN_MATRIX.json"
PANEL_REL = "ideation/PANEL_DESIGN_REVIEW.json"
INNOVATION_REL = "orchestrator/INNOVATION_PACKET.json"
REVIEW_REL = "planner/EXPERIMENT_REVIEW_PACKET.json"
COMMITTED_REL = "ideation/committed"
SHA_CHARS = set("0123456789abcdef")
ROW_KEYS: Dict[str, Tuple[str, ...]] = {
    POOL_REL: ("ideas",),
    SCORECARD_REL: ("candidates",),
    SEEDS_REL: ("tracks", "track_seeds"),
    LEDGER_REL: ("decisions",),
    MATRIX_REL: ("tracks",),
}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json_with_sha(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return None, None
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"non-finite JSON constant: {token}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None, digest
    return (value if isinstance(value, dict) else None), digest


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    value, _ = read_json_with_sha(path)
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def strings(value: Any) -> List[str]:
    return [str(item).strip() for item in as_list(value) if str(item).strip()]


def finite_json(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_json(child) for child in value.values())
    if isinstance(value, list):
        return all(finite_json(child) for child in value)
    return True


def valid_sha(value: Any) -> bool:
    token = str(value or "").strip().lower()
    return len(token) == 64 and set(token) <= SHA_CHARS


def resolve_safe_ref(base: Path, raw_ref: Any) -> Optional[Path]:
    ref = str(raw_ref or "").strip()
    if not ref or "\\" in ref:
        return None
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    try:
        resolved = (base / relative).resolve()
        resolved.relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def expected_content_ref(stem: str, digest: str) -> str:
    return f"{COMMITTED_REL}/{stem}.{digest}.json"


def canonical_rows(payload: Dict[str, Any], rel: str, errors: List[str]) -> List[Dict[str, Any]]:
    supported = ROW_KEYS.get(rel, ())
    present_keys = [key for key in supported if key in payload]
    if len(present_keys) != 1:
        errors.append(f"{rel} must contain exactly one canonical row list: {list(supported)}")
        return []
    key = present_keys[0]
    raw_rows = payload.get(key)
    if not isinstance(raw_rows, list):
        errors.append(f"{rel}.{key} must be a list")
        return []
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            errors.append(f"{rel}.{key}[{index}] must be an object")
            continue
        rows.append(row)
    return rows


def validate_row(row: Dict[str, Any], label: str, campaign_sha: str, campaign_ids: Set[str], errors: List[str]) -> Optional[str]:
    campaign_ref = str(row.get("external_campaign_ref") or "")
    row_sha = str(row.get("external_campaign_sha256") or "")
    candidate_id = str(row.get("external_candidate_id") or "")
    if campaign_ref != CAMPAIGN_REL:
        errors.append(f"{label}.external_campaign_ref must be {CAMPAIGN_REL}")
    if row_sha != campaign_sha:
        errors.append(f"{label}.external_campaign_sha256 is stale or missing")
    if candidate_id not in campaign_ids:
        errors.append(f"{label}.external_candidate_id must resolve to the current campaign")
        return None
    track_id = str(row.get("track_id") or "")
    fragment_id = str(row.get("selected_idea_fragment_id") or "")
    if track_id and track_id == candidate_id:
        errors.append(f"{label}.track_id may not impersonate external_candidate_id")
    if fragment_id and fragment_id == candidate_id:
        errors.append(f"{label}.selected_idea_fragment_id may not impersonate external_candidate_id")
    return candidate_id


def require_payload(base: Path, rel: str, errors: List[str]) -> Optional[Dict[str, Any]]:
    payload = read_json(base / rel)
    if payload is None:
        errors.append(f"{rel} is missing or is not strict finite JSON")
    elif not finite_json(payload):
        errors.append(f"{rel} contains non-finite JSON numbers")
        return None
    return payload


def validate_artifact_refs(
    base: Path,
    rel: str,
    campaign_sha: str,
    campaign_ids: Set[str],
    errors: List[str],
) -> Tuple[Optional[Dict[str, Any]], Set[str]]:
    payload = require_payload(base, rel, errors)
    if payload is None:
        return None, set()
    rows = canonical_rows(payload, rel, errors)
    if not rows:
        errors.append(f"{rel} has no canonical protected external rows")
    seen: Set[str] = set()
    for index, row in enumerate(rows):
        candidate_id = validate_row(row, f"{rel} canonical_row[{index}]", campaign_sha, campaign_ids, errors)
        if candidate_id:
            seen.add(candidate_id)
    return payload, seen


def validate_single_artifact_ref(
    base: Path,
    rel: str,
    campaign_sha: str,
    campaign_ids: Set[str],
    errors: List[str],
) -> Tuple[Optional[Dict[str, Any]], Set[str]]:
    payload = require_payload(base, rel, errors)
    if payload is None:
        return None, set()
    candidate_id = validate_row(payload, rel, campaign_sha, campaign_ids, errors)
    return payload, {candidate_id} if candidate_id else set()


def validate_packet_gate_chain(
    payload: Dict[str, Any],
    rel: str,
    gate: Dict[str, Any],
    candidate_commitments: Dict[str, str],
    errors: List[str],
) -> None:
    candidate_id = str(payload.get("external_candidate_id") or "")
    expected_commitment = candidate_commitments.get(candidate_id, "")
    if not expected_commitment or payload.get("protected_commitment_sha256") != expected_commitment:
        errors.append(f"{rel}.protected_commitment_sha256 must match the selected campaign candidate")
    if str(payload.get("pre_idea_evidence_gate_path") or "") != GATE_REL:
        errors.append(f"{rel}.pre_idea_evidence_gate_path must be {GATE_REL}")
    committed_slot_ref = str(gate.get("innovation_slot_map_path") or "")
    committed_lint_ref = str(gate.get("lint_ref") or "")
    if str(payload.get("innovation_slot_map_path") or "") != committed_slot_ref:
        errors.append(f"{rel}.innovation_slot_map_path must match the committed gate")
    import_gate = payload.get("evidence_import_gate") if isinstance(payload.get("evidence_import_gate"), dict) else {}
    material_refs = set(strings(import_gate.get("material_refs")))
    if import_gate.get("source_mode") != "external_material" or import_gate.get("status") != "not_required":
        errors.append(f"{rel}.evidence_import_gate must identify the external_material route")
    if CAMPAIGN_REL not in material_refs:
        errors.append(f"{rel}.evidence_import_gate.material_refs must include {CAMPAIGN_REL}")
    if import_gate.get("validation_ref") != committed_lint_ref:
        errors.append(f"{rel}.evidence_import_gate.validation_ref must match the committed gate")

    norms = payload.get("external_evidence_norms") or payload.get("evidence_norms")
    if not isinstance(norms, dict):
        errors.append(f"{rel}.external_evidence_norms")
        return
    if norms.get("campaign_ref") != CAMPAIGN_REL:
        errors.append(f"{rel}.external_evidence_norms.campaign_ref must be {CAMPAIGN_REL}")
    if norms.get("campaign_sha256") != gate.get("campaign_sha256"):
        errors.append(f"{rel}.external_evidence_norms.campaign_sha256 must match the gate")
    integrity = norms.get("source_integrity") if isinstance(norms.get("source_integrity"), dict) else {}
    for key, expected in (
        ("lint_ref", committed_lint_ref),
        ("lint_sha256", gate.get("lint_sha256")),
        ("slot_map_sha256", gate.get("slot_map_sha256")),
    ):
        if integrity.get(key) != expected:
            errors.append(f"{rel}.external_evidence_norms.source_integrity.{key} must match the committed gate")


def load_committed_artifact(
    base: Path,
    gate: Dict[str, Any],
    ref_key: str,
    sha_key: str,
    stem: str,
    errors: List[str],
) -> Optional[Dict[str, Any]]:
    ref = str(gate.get(ref_key) or "")
    digest = str(gate.get(sha_key) or "").strip().lower()
    if not valid_sha(digest) or ref != expected_content_ref(stem, digest):
        errors.append(f"{GATE_REL}.{ref_key} must be the content-addressed path named by {sha_key}")
        return None
    path = resolve_safe_ref(base, ref)
    if path is None or not path.is_file():
        errors.append(f"{ref} is missing or unsafe")
        return None
    payload, observed_digest = read_json_with_sha(path)
    if observed_digest != digest:
        errors.append(f"{GATE_REL}.{sha_key} does not match {ref}")
        return None
    if payload is None or not finite_json(payload):
        errors.append(f"{ref} is not strict finite JSON")
        return None
    return payload


def lint(project: str, stage: str) -> Dict[str, Any]:
    base = ar(project)
    errors: List[str] = []
    warnings: List[str] = []
    campaign_path = base / CAMPAIGN_REL
    campaign, campaign_sha = read_json_with_sha(campaign_path)
    if campaign is None or not finite_json(campaign):
        errors.append(f"{CAMPAIGN_REL} is missing or is not strict finite JSON")
    if campaign is None:
        return {"complete": False, "missing": errors, "warnings": warnings, "stage": stage}
    if campaign_sha is None:
        return {"complete": False, "missing": errors, "warnings": warnings, "stage": stage}
    campaign_id_rows = [
        str(row.get("id") or "").strip()
        for row in as_list(campaign.get("candidates"))
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    ]
    campaign_ids = set(campaign_id_rows)
    if len(campaign_id_rows) != len(campaign_ids):
        errors.append("campaign candidate ids must be unique")
    candidate_commitments: Dict[str, str] = {}
    for row in as_list(campaign.get("candidates")):
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("id") or "").strip()
        protected = row.get("protected_commitments") if isinstance(row.get("protected_commitments"), dict) else {}
        digest = str(
            row.get("protected_commitment_sha256")
            or row.get("protected_commitments_sha256")
            or protected.get("sha256")
            or ""
        ).strip().lower()
        if candidate_id and len(digest) == 64 and all(char in "0123456789abcdef" for char in digest):
            candidate_commitments[candidate_id] = digest
    shortlist = set(strings(campaign.get("shortlisted_candidate_ids")))
    admitted = set(strings(campaign.get("admitted_candidate_ids")))
    if campaign.get("source_mode") != "external_material" or campaign.get("papernexus_used") is not False:
        errors.append("campaign must declare source_mode=external_material and papernexus_used=false")
    if not 8 <= len(campaign_ids) <= 12:
        errors.append("campaign candidate identity set must contain 8..12 ids")
    if not 3 <= len(shortlist) <= 5 or not shortlist <= campaign_ids:
        errors.append("campaign shortlist identity set must contain 3..5 current candidate ids")
    if not 1 <= len(admitted) <= 4 or not admitted <= shortlist:
        errors.append("campaign admitted identity set must contain 1..4 shortlisted ids")

    gate = require_payload(base, GATE_REL, errors)
    lint_payload: Optional[Dict[str, Any]] = None
    slot_payload: Optional[Dict[str, Any]] = None
    if gate:
        if gate.get("schema_version") != 1 or isinstance(gate.get("schema_version"), bool):
            errors.append(f"{GATE_REL}.schema_version must be 1")
        expected_gate_values = {
            "status": "passed",
            "evidence_source_mode": "external_material",
            "lane_attempts_satisfied": True,
            "screening_completed": True,
            "allowed_next_action": "generate_experiment_idea_pool",
            "commit_layout": "content_addressed_v1",
            "campaign_ref": CAMPAIGN_REL,
            "campaign_sha256": campaign_sha,
            "campaign_id": campaign.get("campaign_id"),
            "campaign_revision": campaign.get("campaign_revision"),
        }
        for key, expected in expected_gate_values.items():
            if gate.get(key) != expected:
                errors.append(f"{GATE_REL}.{key} must be {expected!r}")
        if gate.get("slot_map_ref") != gate.get("innovation_slot_map_path"):
            errors.append(f"{GATE_REL}.slot_map_ref must equal innovation_slot_map_path")
        if strings(gate.get("admitted_candidate_ids")) != strings(campaign.get("admitted_candidate_ids")):
            errors.append(f"{GATE_REL}.admitted_candidate_ids must match the current campaign")
        lint_payload = load_committed_artifact(
            base, gate, "lint_ref", "lint_sha256", "NON_PAPERNEXUS_IDEA_LINT", errors
        )
        slot_payload = load_committed_artifact(
            base, gate, "innovation_slot_map_path", "slot_map_sha256", "INNOVATION_SLOT_MAP", errors
        )
    if lint_payload:
        expected_lint_values = {
            "complete": True,
            "status": "passed",
            "campaign_ref": CAMPAIGN_REL,
            "campaign_sha256": campaign_sha,
            "campaign_id": campaign.get("campaign_id"),
            "campaign_revision": campaign.get("campaign_revision"),
            "slot_map_ref": gate.get("innovation_slot_map_path") if gate else None,
            "slot_map_sha256": gate.get("slot_map_sha256") if gate else None,
        }
        for key, expected in expected_lint_values.items():
            if lint_payload.get(key) != expected:
                errors.append(f"committed lint {key} is incomplete or stale")
    if slot_payload:
        expected_slot_values = {
            "source_mode": "external_material",
            "campaign_ref": CAMPAIGN_REL,
            "campaign_sha256": campaign_sha,
            "campaign_id": campaign.get("campaign_id"),
            "campaign_revision": campaign.get("campaign_revision"),
        }
        for key, expected in expected_slot_values.items():
            if slot_payload.get(key) != expected:
                errors.append(f"committed slot map {key} is stale")

    pool, pool_ids = validate_artifact_refs(base, POOL_REL, campaign_sha, campaign_ids, errors)
    if pool is not None:
        rows = canonical_rows(pool, POOL_REL, errors)
        if not 8 <= len(rows) <= 12:
            errors.append(f"{POOL_REL} must contain 8..12 candidate rows")
        if pool_ids != campaign_ids:
            errors.append(f"{POOL_REL} external candidate ids must exactly match the campaign")

    _, scorecard_ids = validate_artifact_refs(base, SCORECARD_REL, campaign_sha, campaign_ids, errors)
    if not shortlist <= scorecard_ids:
        errors.append(f"{SCORECARD_REL} must carry every shortlisted external candidate id")

    if stage in {"idea_gate", "experiment_plan"}:
        _, seed_ids = validate_artifact_refs(base, SEEDS_REL, campaign_sha, campaign_ids, errors)
        if seed_ids != admitted:
            errors.append(f"{SEEDS_REL} external candidate ids must exactly match admitted tracks")
        _, ledger_ids = validate_artifact_refs(base, LEDGER_REL, campaign_sha, campaign_ids, errors)
        if not admitted <= ledger_ids:
            errors.append(f"{LEDGER_REL} must carry every admitted external candidate id")
        _, matrix_ids = validate_artifact_refs(base, MATRIX_REL, campaign_sha, campaign_ids, errors)
        if not admitted <= matrix_ids:
            errors.append(f"{MATRIX_REL} must carry every admitted external candidate id")

    selected_ids: Set[str] = set()
    if stage == "experiment_plan":
        packet_selected_ids: List[str] = []
        for rel in (INNOVATION_REL, REVIEW_REL):
            payload, ids = validate_single_artifact_ref(base, rel, campaign_sha, campaign_ids, errors)
            if payload is not None and len(ids) != 1:
                errors.append(f"{rel} must identify exactly one external candidate")
            if len(ids) == 1:
                packet_selected_ids.append(next(iter(ids)))
            if payload is not None and gate:
                validate_packet_gate_chain(payload, rel, gate, candidate_commitments, errors)
            selected_ids.update(ids)
        if len(packet_selected_ids) == 2 and packet_selected_ids[0] != packet_selected_ids[1]:
            errors.append("INNOVATION_PACKET and EXPERIMENT_REVIEW_PACKET must select the same external candidate")
        if not selected_ids or not selected_ids <= admitted:
            errors.append("experiment packets must select one admitted external candidate")
        panel = require_payload(base, PANEL_REL, errors)
        if panel:
            if panel.get("status") != "passed":
                errors.append(f"{PANEL_REL}.status must be passed")
            if panel.get("external_campaign_ref") != CAMPAIGN_REL or panel.get("external_campaign_sha256") != campaign_sha:
                errors.append(f"{PANEL_REL} campaign identity is stale or missing")
            generation_context = str(panel.get("generation_context_id") or "").strip()
            reviewer_context = str(panel.get("reviewer_context_id") or "").strip()
            if not generation_context or not reviewer_context or generation_context == reviewer_context:
                errors.append(f"{PANEL_REL} generation/reviewer contexts must be non-empty and separate")
            if str(panel.get("reviewer_role") or "").strip() != "independent_panel":
                errors.append(f"{PANEL_REL}.reviewer_role must be independent_panel")
            reviewed = set(strings(panel.get("reviewed_candidate_ids")))
            if not reviewed or not reviewed <= admitted:
                errors.append(f"{PANEL_REL}.reviewed_candidate_ids must be non-empty admitted ids")
            if not selected_ids <= reviewed:
                errors.append(f"{PANEL_REL} must review the selected candidate")
            if panel.get("verdict") not in {"advance", "revise", "abandon"}:
                errors.append(f"{PANEL_REL}.verdict invalid")
            if panel.get("verdict") != "advance":
                errors.append(f"{PANEL_REL} must advance the selected candidate before planning")

    return {
        "schema_version": 1,
        "complete": not errors,
        "status": "passed" if not errors else "blocked",
        "stage": stage,
        "missing": errors,
        "warnings": warnings,
        "details": {
            "campaign_ref": CAMPAIGN_REL,
            "campaign_sha256": campaign_sha,
            "candidate_count": len(campaign_ids),
            "shortlist_count": len(shortlist),
            "admitted_count": len(admitted),
            "selected_candidate_ids": sorted(selected_ids),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", required=True, choices=["ideation", "idea_gate", "experiment_plan"])
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = lint(args.project, args.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
