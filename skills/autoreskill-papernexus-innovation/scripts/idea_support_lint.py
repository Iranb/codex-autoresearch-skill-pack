#!/usr/bin/env python3
"""Verify source-backed PaperNexus support for the selected idea fragment."""

from __future__ import annotations

import argparse
import json
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
