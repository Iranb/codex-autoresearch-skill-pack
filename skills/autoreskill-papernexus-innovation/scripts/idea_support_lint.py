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
        evidence_path = evidence_export_path or resolve_artifact_path(
            base,
            first_present(
                packet,
                ["idea_evidence_export_path", "ideaEvidenceExportPath", "evidence_export_path", "evidenceExportPath"],
            ),
            "papernexus/idea_catalyst_evidence_export.json",
        )

    if not selected_id:
        missing.append("INNOVATION_PACKET.selected_idea_fragment_id")
    if evidence_path is None:
        missing.append("INNOVATION_PACKET.idea_evidence_export_path")
        evidence_payload = None
    else:
        evidence_payload = read_json(evidence_path)
        if evidence_payload is None:
            missing.append(relpath(base, evidence_path))

    if selected_id and evidence_payload is not None:
        root_has_provenance = has_papernexus_provenance(evidence_payload)
        candidates = candidate_records(evidence_payload, selected_id)
        if not candidates:
            missing.append(f"source-backed evidence for selected idea fragment {selected_id}")
        else:
            supported = [summarize_candidate(candidate, selected_id, root_has_provenance) for candidate in candidates]
            if not any(row["complete"] for row in supported):
                missing.append(f"selected idea fragment {selected_id} with PaperNexus provenance, source record, and source span")
            if any(row["evidence_status"] == "source_backed" and not row["raw_statuses"] for row in supported):
                warnings.append("evidence status inferred from PaperNexus provenance plus source/span records")

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
