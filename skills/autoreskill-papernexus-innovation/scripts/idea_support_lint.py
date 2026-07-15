#!/usr/bin/env python3
"""Verify source-backed PaperNexus support for the selected idea fragment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ACCEPTED_STATUSES = {"source_backed", "source-backed", "graph_grounded", "graph-grounded"}
ID_KEYS = {
    "fragment_id",
    "fragmentid",
    "idea_fragment_id",
    "ideafragmentid",
    "selected_idea_fragment_id",
    "selectedideafragmentid",
    "idea_id",
    "ideaid",
    "id",
}
LIST_ID_KEYS = {
    "fragment_ids",
    "fragmentids",
    "idea_fragment_ids",
    "ideafragmentids",
    "supporting_idea_fragment_ids",
    "supportingideafragmentids",
}
SOURCE_KEYS = {
    "paper_id",
    "paperid",
    "doi",
    "arxiv",
    "arxiv_id",
    "arxivid",
    "url",
    "source_id",
    "sourceid",
    "title",
}
SPAN_HINTS = ("span", "quote", "excerpt", "locator", "section", "claim_summary", "evidence_text", "source_text")
EVIDENCE_SOURCE_MODES = {"papernexus", "external_material"}


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
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def norm_key(value: str) -> str:
    return value.replace("-", "_").replace(" ", "_").lower()


def relpath(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def resolve_artifact_path(base: Path, value: Any, default_rel: str | None = None) -> Path | None:
    raw = str(value or default_rel or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == ".autoreskill":
        path = Path(*parts[1:])
    return base / path


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if present(mapping.get(key)):
            return mapping[key]
    return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def collect_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        if value.strip():
            out.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            out.extend(collect_strings(item))
    elif isinstance(value, dict):
        for item in value.values():
            out.extend(collect_strings(item))
    return out


def walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for item in value.values():
            found.extend(walk_dicts(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(walk_dicts(item))
    return found


def record_ids(record: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key, value in record.items():
        nkey = norm_key(str(key))
        if nkey in ID_KEYS:
            ids.update(collect_strings(value))
        if nkey in LIST_ID_KEYS:
            ids.update(collect_strings(value))
    return ids


def has_papernexus_provenance(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            nkey = norm_key(str(key))
            if nkey in {"source", "mcp_source", "source_type", "provider", "origin"}:
                strings = [s.lower() for s in collect_strings(item)]
                if any("papernexus" in s or "papernexus-remote" in s for s in strings):
                    return True
            if has_papernexus_provenance(item):
                return True
    elif isinstance(value, list):
        return any(has_papernexus_provenance(item) for item in value)
    return False


def status_values(value: Any) -> set[str]:
    statuses: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            nkey = norm_key(str(key))
            if any(token in nkey for token in ["status", "category", "boundary", "support_level"]):
                statuses.update(s.lower().replace(" ", "_") for s in collect_strings(item))
            if nkey == "source_backed" and item is True:
                statuses.add("source_backed")
            statuses.update(status_values(item))
    elif isinstance(value, list):
        for item in value:
            statuses.update(status_values(item))
    return statuses


def source_records(value: Any) -> list[dict[str, Any]]:
    records = []
    for record in walk_dicts(value):
        keys = {norm_key(str(key)) for key in record}
        if keys & SOURCE_KEYS:
            records.append(record)
    return records


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ["migrations", "mechanisms", "rows", "items", "records"]:
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def code_transfer_support(base: Path, packet: dict[str, Any] | None, selected_id: str | None) -> dict[str, Any]:
    if not selected_id or not isinstance(packet, dict):
        return {"complete": False, "reason": "missing_packet_or_selected_id"}
    support = packet.get("paper_code_transfer_support") or packet.get("source_code_transfer_support")
    if not isinstance(support, dict):
        return {"complete": False, "reason": "missing_paper_code_transfer_support"}
    authority = str(support.get("authority") or support.get("source") or "").strip().lower()
    if authority not in {"paper_code_transfer_lint", "paper_code_transfer", "code_migration_matrix"}:
        return {"complete": False, "reason": "unsupported_authority"}

    lint_rel = support.get("lint_result_path") or "survey/PAPER_CODE_TRANSFER_LINT_RESULT.json"
    lint_path = resolve_artifact_path(base, lint_rel)
    lint_payload = read_json(lint_path) if lint_path else None
    lint_complete = isinstance(lint_payload, dict) and lint_payload.get("complete") is True

    migration_refs = {str(item) for item in as_list(support.get("migration_refs") or support.get("migration_ids")) if present(item)}
    mechanism_refs = {str(item) for item in as_list(support.get("mechanism_refs") or support.get("mechanism_ids")) if present(item)}
    migration_payload = read_json(base / "ideation/INNOVATION_MIGRATION_MATRIX.json")
    mechanism_payload = read_json(base / "survey/CODE_MECHANISM_MAP.json")
    available_migrations = {str(row.get("migration_id")) for row in rows_from_payload(migration_payload) if present(row.get("migration_id"))}
    available_mechanisms = {str(row.get("mechanism_id")) for row in rows_from_payload(mechanism_payload) if present(row.get("mechanism_id"))}
    matched_migrations = sorted(migration_refs & available_migrations)
    matched_mechanisms = sorted(mechanism_refs & available_mechanisms)

    complete = lint_complete and bool(matched_migrations or matched_mechanisms)
    return {
        "complete": complete,
        "authority": authority,
        "selected_idea_fragment_id": selected_id,
        "lint_result_path": relpath(base, lint_path) if lint_path else None,
        "lint_complete": lint_complete,
        "matched_migration_refs": matched_migrations,
        "matched_mechanism_refs": matched_mechanisms,
        "claim_scope": support.get("claim_scope") or "static_code_transfer_support_only",
        "evidence_boundary": support.get("evidence_boundary")
        or "Paper-code static evidence supports implementability/mechanism transfer only, not target-task effectiveness or PaperNexus graph support.",
    }


def span_values(value: Any) -> list[str]:
    spans = []
    if isinstance(value, dict):
        for key, item in value.items():
            nkey = norm_key(str(key))
            if any(hint in nkey for hint in SPAN_HINTS):
                spans.extend(collect_strings(item))
            else:
                spans.extend(span_values(item))
    elif isinstance(value, list):
        for item in value:
            spans.extend(span_values(item))
    return spans


def candidate_records(payload: Any, selected_id: str) -> list[dict[str, Any]]:
    candidates = []
    for record in walk_dicts(payload):
        if selected_id in record_ids(record):
            candidates.append(record)
    return candidates


def proposal_manifest_ready(base: Path, packet: dict[str, Any] | None) -> tuple[bool, dict[str, Any] | None, list[str], list[str]]:
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(packet, dict):
        return False, None, missing, warnings

    manifest_value = first_present(
        packet,
        [
            "proposal_graph_session_manifest_path",
            "proposalSessionManifestPath",
            "proposal_session_manifest_path",
            "proposal_manifest_path",
        ],
    )
    result_value = first_present(
        packet,
        [
            "proposal_graph_session_path",
            "proposalGraphSessionPath",
            "proposal_session_path",
            "proposal_graph_session_result_path",
        ],
    )
    manifest_path = resolve_artifact_path(base, manifest_value) if manifest_value else None
    result_path = resolve_artifact_path(base, result_value, "papernexus/proposal_graph_session.json")

    manifest = read_json(manifest_path) if manifest_path else None
    result = read_json(result_path) if result_path else None
    if not isinstance(manifest, dict) and isinstance(result, dict) and isinstance(result.get("manifest"), dict):
        manifest = result["manifest"]

    if not isinstance(manifest, dict):
        return False, None, missing, warnings

    if str(manifest.get("final_status") or "").strip().lower() != "committed":
        missing.append("proposal graph session final_status=committed")
    if not present(manifest.get("committed_subgraph_id")):
        missing.append("proposal graph session committed_subgraph_id")
    proposal_paths = manifest.get("proposal_artifact_paths") if isinstance(manifest.get("proposal_artifact_paths"), dict) else {}
    if not present(proposal_paths.get("proposal_json")):
        missing.append("proposal graph session proposal_json")
    if not present(proposal_paths.get("proposal_md")):
        missing.append("proposal graph session proposal_md")
    if not present(manifest.get("evidence_export_paths")):
        missing.append("proposal graph session evidence_export_paths")
    if not present(manifest.get("controller_trace_paths")):
        missing.append("proposal graph session controller_trace_paths")

    return not missing, manifest, missing, warnings


def summarize_candidate(record: dict[str, Any], selected_id: str, root_has_provenance: bool) -> dict[str, Any]:
    statuses = status_values(record)
    sources = source_records(record)
    spans = span_values(record)
    provenance = root_has_provenance or has_papernexus_provenance(record)
    normalized_status = None
    if statuses & ACCEPTED_STATUSES:
        normalized_status = sorted(statuses & ACCEPTED_STATUSES)[0]
    elif sources and spans and provenance:
        normalized_status = "source_backed"
    complete = bool(normalized_status in ACCEPTED_STATUSES or normalized_status == "source_backed") and bool(sources) and bool(spans) and provenance
    return {
        "fragment_id": selected_id,
        "complete": complete,
        "evidence_status": normalized_status or "unsupported",
        "raw_statuses": sorted(statuses),
        "source_count": len(sources),
        "span_count": len(spans),
        "papernexus_provenance": provenance,
    }


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        out = {"stdout": proc.stdout}
    if not isinstance(out, dict):
        out = {"result": out}
    out.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        out["stderr"] = proc.stderr.strip()
    return out


def evidence_source_mode(base: Path, packet: dict[str, Any] | None) -> tuple[str, dict[str, Any], Path]:
    gate_value = (
        first_present(packet, ["pre_idea_evidence_gate_path", "preIdeaEvidenceGatePath"])
        if isinstance(packet, dict)
        else None
    )
    gate_path = resolve_artifact_path(base, gate_value, "ideation/PRE_IDEA_EVIDENCE_GATE.json")
    assert gate_path is not None
    gate = read_json(gate_path)
    if not isinstance(gate, dict):
        gate = {}
    mode = str(gate.get("evidence_source_mode") or "papernexus").strip().lower()
    return mode, gate, gate_path


def has_forbidden_papernexus_metadata(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            nkey = norm_key(str(key))
            if nkey == "papernexus_used" and item is False:
                continue
            if "papernexus" in nkey and "non_papernexus" not in nkey:
                return True
            if nkey == "mcp_attempted" and item is True:
                return True
            if has_forbidden_papernexus_metadata(item):
                return True
    elif isinstance(value, list):
        return any(has_forbidden_papernexus_metadata(item) for item in value)
    elif isinstance(value, str):
        text = value.lower().replace("-", "_")
        return "papernexus" in text and "non_papernexus" not in text
    return False


def dict_rows(value: Any, keys: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in walk_dicts(value):
        for key, item in record.items():
            if norm_key(str(key)) in keys and isinstance(item, list):
                rows.extend(row for row in item if isinstance(row, dict))
    return rows


def external_candidate_rows(campaign: Any, candidate_id: str) -> list[dict[str, Any]]:
    rows = dict_rows(campaign, {"candidates", "idea_candidates", "admitted_candidates"})
    out: list[dict[str, Any]] = []
    for row in rows:
        value = first_present(row, ["external_candidate_id", "candidate_id", "id"])
        if present(value) and str(value) == candidate_id:
            out.append(row)
    return out


def reference_strings(value: Any) -> set[str]:
    refs: set[str] = set()
    for record in walk_dicts(value):
        for key, item in record.items():
            nkey = norm_key(str(key))
            if nkey in {
                "source_ref",
                "source_refs",
                "evidence_ref",
                "evidence_refs",
                "material_ref",
                "material_refs",
                "source_id",
                "evidence_id",
            }:
                refs.update(collect_strings(item))
    return refs


def external_source_summary(campaign: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    refs = reference_strings(candidate)
    gap_refs = {
        str(row.get("gap_ref"))
        for row in candidate.get("gap_closures", [])
        if isinstance(row, dict) and present(row.get("gap_ref"))
    }
    gaps = {
        str(row.get("id")): row
        for row in (campaign.get("structural_gaps", []) if isinstance(campaign, dict) else [])
        if isinstance(row, dict) and present(row.get("id"))
    }
    lineage = campaign.get("method_lineage") if isinstance(campaign, dict) else {}
    lineage_nodes = {
        str(row.get("id")): row
        for row in (lineage.get("nodes", []) if isinstance(lineage, dict) else [])
        if isinstance(row, dict) and present(row.get("id"))
    }
    for gap_ref in gap_refs:
        gap = gaps.get(gap_ref, {})
        refs.update(collect_strings(gap.get("evidence_refs")))
        for node_ref in collect_strings(gap.get("lineage_node_refs")):
            refs.update(collect_strings(lineage_nodes.get(node_ref, {}).get("evidence_refs")))
    records = dict_rows(
        campaign,
        {"sources", "source_records", "evidence_records", "materials", "literature_evidence"},
    )
    matched: list[dict[str, Any]] = []
    integrity_ok = 0
    locator_count = 0
    excerpt_count = 0
    for row in records:
        row_ids = set()
        for key in ["source_id", "evidence_id", "material_id", "id", "stable_locator", "url", "doi", "arxiv"]:
            if present(row.get(key)):
                row_ids.add(str(row[key]))
        if refs and not (refs & row_ids):
            continue
        locator = first_present(row, ["locator", "stable_locator", "span", "section", "url", "doi", "arxiv"])
        excerpt = first_present(row, ["excerpt", "quote", "source_text", "evidence_text"])
        digest = first_present(row, ["excerpt_sha256", "source_excerpt_sha256", "sha256"])
        if present(locator):
            locator_count += 1
        if present(excerpt):
            excerpt_count += 1
        if present(excerpt) and present(digest):
            actual = hashlib.sha256(str(excerpt).encode("utf-8")).hexdigest()
            if actual == str(digest).strip().lower():
                integrity_ok += 1
        matched.append(row)
    return {
        "source_refs": sorted(refs),
        "source_count": len(matched),
        "locator_count": locator_count,
        "excerpt_count": excerpt_count,
        "integrity_verified_count": integrity_ok,
    }


def lint_external_support(
    project: str,
    base: Path,
    packet_path: Path,
    packet: dict[str, Any],
    gate: dict[str, Any],
    gate_path: Path,
) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []
    candidate_id = str(packet.get("external_candidate_id") or "").strip()
    fragment_id = str(packet.get("selected_idea_fragment_id") or "").strip()
    track_id = str(
        packet.get("track_id")
        or (packet.get("innovation_search_contract") or {}).get("track_id")
        or ""
    ).strip()
    for key, value in [
        ("external_campaign_ref", packet.get("external_campaign_ref")),
        ("external_campaign_sha256", packet.get("external_campaign_sha256")),
        ("external_candidate_id", candidate_id),
        ("selected_idea_fragment_id", fragment_id),
        ("track_id", track_id),
    ]:
        if not present(value):
            missing.append(f"INNOVATION_PACKET.{key}")
    if candidate_id and fragment_id and candidate_id == fragment_id:
        missing.append("external_candidate_id must remain distinct from selected_idea_fragment_id")
    if candidate_id and track_id and candidate_id == track_id:
        missing.append("external_candidate_id must remain distinct from track_id")

    campaign_ref = str(gate.get("campaign_ref") or "").strip()
    lint_ref = str(gate.get("lint_ref") or "").strip()
    if str(packet.get("external_campaign_ref") or "") != campaign_ref:
        missing.append("INNOVATION_PACKET.external_campaign_ref must match PRE_IDEA_EVIDENCE_GATE.campaign_ref")
    if str(packet.get("external_campaign_sha256") or "") != str(gate.get("campaign_sha256") or ""):
        missing.append("INNOVATION_PACKET.external_campaign_sha256 must match PRE_IDEA_EVIDENCE_GATE.campaign_sha256")

    campaign_path = resolve_artifact_path(base, campaign_ref)
    lint_path = resolve_artifact_path(base, lint_ref)
    campaign = read_json(campaign_path) if campaign_path else None
    lint_payload = read_json(lint_path) if lint_path else None
    campaign_hash = sha256_file(campaign_path)
    lint_hash = sha256_file(lint_path)
    if campaign_hash != str(gate.get("campaign_sha256") or "").strip().lower():
        missing.append("current external campaign hash must match PRE_IDEA_EVIDENCE_GATE.campaign_sha256")
    if lint_hash != str(gate.get("lint_sha256") or "").strip().lower():
        missing.append("current external lint hash must match PRE_IDEA_EVIDENCE_GATE.lint_sha256")
    if not isinstance(lint_payload, dict) or lint_payload.get("complete") is not True:
        missing.append("external lint record complete=true")
    if not isinstance(campaign, dict):
        missing.append("external campaign JSON")
        campaign = {}
    elif campaign.get("papernexus_used") is not False:
        missing.append("external campaign papernexus_used=false")
    if has_forbidden_papernexus_metadata(campaign) or has_forbidden_papernexus_metadata(packet):
        missing.append("external-material support must not contain PaperNexus or mcp_attempted=true metadata")

    candidates = external_candidate_rows(campaign, candidate_id) if candidate_id else []
    if not candidates:
        missing.append(f"admitted external candidate {candidate_id or '<missing>'} in current campaign")
        source_summary = {
            "source_refs": [],
            "source_count": 0,
            "locator_count": 0,
            "excerpt_count": 0,
            "integrity_verified_count": 0,
        }
    else:
        source_summary = external_source_summary(campaign, candidates[0])
        if source_summary["source_count"] < 1:
            missing.append("selected external candidate source record")
        if source_summary["locator_count"] < 1 or source_summary["excerpt_count"] < 1:
            missing.append("selected external candidate source locator/span and excerpt")
        if source_summary["integrity_verified_count"] < 1:
            missing.append("selected external candidate verified excerpt SHA-256")

    checker = Path(__file__).resolve().parents[2] / "autoreskill-gpu-idea-validation/scripts/idea_campaign.py"
    checker_out = (
        run_json([sys.executable, str(checker), "check", "--project", str(base.parent)])
        if checker.is_file()
        else {
            "complete": False,
            "missing": ["autoreskill-gpu-idea-validation/scripts/idea_campaign.py"],
            "warnings": [],
            "returncode": 1,
        }
    )
    if not checker_out.get("complete"):
        items = checker_out.get("missing") if isinstance(checker_out.get("missing"), list) else []
        missing.extend(f"external_campaign_check: {item}" for item in items or ["failed without structured missing output"])
    admitted_ids = {str(item) for item in checker_out.get("admitted_candidate_ids", []) if present(item)}
    if candidate_id and candidate_id not in admitted_ids:
        missing.append("INNOVATION_PACKET.external_candidate_id must be admitted by current campaign lint")

    alignment_script = Path(__file__).resolve().parents[2] / "autoreskill-gpu-idea-validation/scripts/external_alignment_lint.py"
    alignment = (
        run_json(
            [
                sys.executable,
                str(alignment_script),
                "--project",
                str(base.parent),
                "--stage",
                "experiment_plan",
            ]
        )
        if alignment_script.is_file()
        else {
            "complete": False,
            "missing": ["autoreskill-gpu-idea-validation/scripts/external_alignment_lint.py"],
            "warnings": [],
            "returncode": 1,
        }
    )
    if not alignment.get("complete"):
        items = alignment.get("missing") if isinstance(alignment.get("missing"), list) else []
        missing.extend(f"external_alignment_lint: {item}" for item in items or ["failed without structured missing output"])
    warnings.extend(
        f"external_alignment_lint: {item}"
        for item in alignment.get("warnings", [])
        if isinstance(item, str)
    )

    import_gate = packet.get("evidence_import_gate")
    if not isinstance(import_gate, dict):
        missing.append("INNOVATION_PACKET.evidence_import_gate")
    else:
        expected = {
            "status": "not_required",
            "source_mode": "external_material",
            "validation_ref": lint_ref,
            "launch_blocked": False,
        }
        for key, value in expected.items():
            if import_gate.get(key) != value:
                missing.append(f"INNOVATION_PACKET.evidence_import_gate.{key}={value!r}")
        material_refs = {str(item).removeprefix(".autoreskill/") for item in as_list(import_gate.get("material_refs"))}
        if campaign_ref.removeprefix(".autoreskill/") not in material_refs:
            missing.append("INNOVATION_PACKET.evidence_import_gate.material_refs must include campaign_ref")
        if not present(import_gate.get("reason")):
            missing.append("INNOVATION_PACKET.evidence_import_gate.reason")
        if import_gate.get("mcp_attempted") is True:
            missing.append("INNOVATION_PACKET.evidence_import_gate.mcp_attempted must not be true")

    supported = []
    if not missing:
        supported.append(
            {
                "fragment_id": fragment_id,
                "external_candidate_id": candidate_id,
                "complete": True,
                "evidence_status": "external_material_source_backed",
                "raw_statuses": ["external_material_source_backed"],
                "source_count": source_summary["source_count"],
                "span_count": source_summary["locator_count"],
                "integrity_verified_count": source_summary["integrity_verified_count"],
                "papernexus_provenance": False,
            }
        )
    return {
        "schema_version": 1,
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "evidence_source_mode": "external_material",
        "selected_idea_fragment_id": fragment_id or None,
        "external_candidate_id": candidate_id or None,
        "source_backed_fragment_count": len(supported),
        "missing": missing,
        "warnings": warnings,
        "packet_path": relpath(base, packet_path),
        "pre_idea_evidence_gate_path": relpath(base, gate_path),
        "evidence_export_path": relpath(base, campaign_path) if campaign_path else None,
        "external_campaign_check": checker_out,
        "external_alignment_lint": alignment,
        "source_summary": source_summary,
        "supported_fragments": supported,
    }


def lint_idea_support(
    project: str,
    packet_path: Path | None = None,
    evidence_export_path: Path | None = None,
) -> dict[str, Any]:
    base = ar(project)
    packet_path = packet_path or base / "orchestrator/INNOVATION_PACKET.json"
    packet = read_json(packet_path)
    missing: list[str] = []
    warnings: list[str] = []
    supported: list[dict[str, Any]] = []
    proposal_support: dict[str, Any] | None = None

    mode, source_gate, source_gate_path = evidence_source_mode(
        base, packet if isinstance(packet, dict) else None
    )
    if mode not in EVIDENCE_SOURCE_MODES:
        return {
            "schema_version": 1,
            "complete": False,
            "status": "incomplete",
            "evidence_source_mode": mode,
            "selected_idea_fragment_id": None,
            "source_backed_fragment_count": 0,
            "missing": [
                "PRE_IDEA_EVIDENCE_GATE.evidence_source_mode must be papernexus or external_material"
            ],
            "warnings": [],
            "packet_path": relpath(base, packet_path),
            "supported_fragments": [],
        }
    if mode == "external_material" and isinstance(packet, dict):
        return lint_external_support(project, base, packet_path, packet, source_gate, source_gate_path)

    if not isinstance(packet, dict):
        missing.append(relpath(base, packet_path))
        selected_id = None
        evidence_path = evidence_export_path or base / "papernexus/idea_catalyst_evidence_export.json"
    else:
        selected_id = first_present(
            packet,
            ["selected_idea_fragment_id", "selectedIdeaFragmentId", "selected_idea_id", "idea_id"],
        )
        if selected_id is not None:
            selected_id = str(selected_id)
        proposal_ready, proposal_manifest, proposal_missing, proposal_warnings = proposal_manifest_ready(base, packet)
        if proposal_manifest is not None:
            proposal_support = {
                "complete": proposal_ready,
                "committed_subgraph_id": proposal_manifest.get("committed_subgraph_id"),
                "missing": proposal_missing,
            }
            warnings.extend(proposal_warnings)

        evidence_path = evidence_export_path or resolve_artifact_path(
            base,
            first_present(
                packet,
                [
                    "idea_evidence_export_path",
                    "ideaEvidenceExportPath",
                    "evidence_export_path",
                    "evidenceExportPath",
                    "proposal_evidence_export_path",
                ],
            ),
            "papernexus/idea_catalyst_evidence_export.json",
        )

    if not selected_id:
        missing.append("INNOVATION_PACKET.selected_idea_fragment_id")
    if evidence_path is None and not (proposal_support or {}).get("complete"):
        missing.append("INNOVATION_PACKET.idea_evidence_export_path")
        evidence_payload = None
    else:
        evidence_payload = read_json(evidence_path) if evidence_path else None
        if evidence_payload is None and not (proposal_support or {}).get("complete"):
            missing.append(relpath(base, evidence_path))

    if selected_id and evidence_payload is None and (proposal_support or {}).get("complete"):
        supported.append(
            {
                "fragment_id": selected_id,
                "complete": True,
                "evidence_status": "proposal_graph_committed",
                "raw_statuses": ["proposal_graph_committed"],
                "source_count": 1,
                "span_count": 1,
                "papernexus_provenance": True,
                "committed_subgraph_id": proposal_support.get("committed_subgraph_id"),
            }
        )

    if selected_id and evidence_payload is not None:
        root_has_provenance = has_papernexus_provenance(evidence_payload)
        candidates = candidate_records(evidence_payload, selected_id)
        if not candidates:
            if (proposal_support or {}).get("complete"):
                supported.append(
                    {
                        "fragment_id": selected_id,
                        "complete": True,
                        "evidence_status": "proposal_graph_committed",
                        "raw_statuses": ["proposal_graph_committed"],
                        "source_count": 1,
                        "span_count": 1,
                        "papernexus_provenance": True,
                        "committed_subgraph_id": proposal_support.get("committed_subgraph_id"),
                    }
                )
            else:
                missing.append(f"source-backed evidence for selected idea fragment {selected_id}")
        else:
            supported = [summarize_candidate(candidate, selected_id, root_has_provenance) for candidate in candidates]
            if not any(row["complete"] for row in supported):
                if (proposal_support or {}).get("complete"):
                    warnings.append("selected idea fragment support inferred from committed proposal graph session")
                    supported.append(
                        {
                            "fragment_id": selected_id,
                            "complete": True,
                            "evidence_status": "proposal_graph_committed",
                            "raw_statuses": ["proposal_graph_committed"],
                            "source_count": 1,
                            "span_count": 1,
                            "papernexus_provenance": True,
                            "committed_subgraph_id": proposal_support.get("committed_subgraph_id"),
                        }
                    )
                else:
                    missing.append(f"selected idea fragment {selected_id} with PaperNexus provenance, source record, and source span")
            if any(row["evidence_status"] == "source_backed" and not row["raw_statuses"] for row in supported):
                warnings.append("evidence status inferred from PaperNexus provenance plus source/span records")

    code_support = code_transfer_support(base, packet if isinstance(packet, dict) else None, selected_id)
    if code_support.get("complete"):
        missing = [
            item
            for item in missing
            if item
            not in {
                f"source-backed evidence for selected idea fragment {selected_id}",
                f"selected idea fragment {selected_id} with PaperNexus provenance, source record, and source span",
            }
        ]
        supported.append(
            {
                "fragment_id": selected_id,
                "complete": True,
                "evidence_status": "paper_code_transfer_static_support",
                "raw_statuses": ["paper_code_transfer_static_support"],
                "source_count": len(code_support.get("matched_mechanism_refs") or []),
                "span_count": len(code_support.get("matched_migration_refs") or []),
                "papernexus_provenance": False,
                "code_transfer_support": code_support,
            }
        )
        warnings.append(
            "selected idea fragment support uses paper-code static evidence; this is not PaperNexus graph-grounded novelty evidence"
        )

    return {
        "schema_version": 1,
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "selected_idea_fragment_id": selected_id,
        "source_backed_fragment_count": sum(1 for row in supported if row["complete"]),
        "missing": missing,
        "warnings": warnings,
        "packet_path": relpath(base, packet_path),
        "evidence_export_path": relpath(base, evidence_path) if evidence_path else None,
        "proposal_graph_support": proposal_support,
        "supported_fragments": supported,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--packet")
    parser.add_argument("--evidence-export")
    args = parser.parse_args()

    base = ar(args.project)
    packet_path = resolve_artifact_path(base, args.packet) if args.packet else None
    evidence_path = resolve_artifact_path(base, args.evidence_export) if args.evidence_export else None
    out = lint_idea_support(args.project, packet_path, evidence_path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
