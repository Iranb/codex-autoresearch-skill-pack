#!/usr/bin/env python3
"""Capture PaperNexus MCP results into .autoreskill artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_PATHS = {
    "corpus_status": "papernexus/corpus_status.json",
    "source_discovery_plan": "papernexus/source_discovery_plan.json",
    "research_material_pack": "papernexus/research_material_pack.json",
    "negative_evidence_pack": "papernexus/negative_evidence_pack.json",
    "experiment_cost_materials": "papernexus/experiment_cost_materials.json",
    "graph_ideation_packet": "papernexus/graph_ideation_packet.json",
    "idea_catalyst_evidence_export": "papernexus/idea_catalyst_evidence_export.json",
    "proposal_graph_session": "papernexus/proposal_graph_session.json",
    "pre_idea_discovery_plan": "literature/PRE_IDEA_DISCOVERY_PLAN.json",
    "target_domain_discovery_packet": "literature/TARGET_DOMAIN_DISCOVERY_PACKET.json",
    "near_neighbor_discovery_packet": "literature/NEAR_NEIGHBOR_DISCOVERY_PACKET.json",
    "far_neighbor_discovery_packet": "literature/FAR_NEIGHBOR_DISCOVERY_PACKET.json",
    "literature_discovery_packet": "literature/LITERATURE_DISCOVERY_PACKET.json",
    "literature_discovery_run": "literature/LITERATURE_DISCOVERY_RUN.json",
    "paper_selection_scorecard": "papernexus/PAPER_SELECTION_SCORECARD.json",
    "graph_import_plan": "papernexus/GRAPH_IMPORT_PLAN.json",
    "graph_import_status": "papernexus/GRAPH_IMPORT_STATUS.json",
    "split_reading_evidence_pack": "papernexus/SPLIT_READING_EVIDENCE_PACK.json",
    "innovation_slot_map": "ideation/INNOVATION_SLOT_MAP.json",
    "pre_idea_evidence_gate": "ideation/PRE_IDEA_EVIDENCE_GATE.json",
    "experiment_monitor_plan": "experiment/EXPERIMENT_MONITOR_PLAN.json",
    "idea_catalyst_contract": "ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json",
    "graph_build_decision": "graph/GRAPH_BUILD_DECISION.json",
    "innovation_packet": "orchestrator/INNOVATION_PACKET.json",
    "experiment_review_packet": "planner/EXPERIMENT_REVIEW_PACKET.json",
    "research_controller_export": "papernexus/research_controller/controller-export.json",
    "research_controller_design_review": "papernexus/research_controller/design-review.json",
    "research_controller_innovation_brief": "papernexus/research_controller/innovation-brief.json",
}

CONTRACT_KINDS = {
    "idea_catalyst_contract",
    "idea_catalyst_evidence_export",
    "proposal_graph_session",
    "graph_build_decision",
    "innovation_packet",
    "experiment_review_packet",
    "research_controller_design_review",
    "research_controller_innovation_brief",
    "pre_idea_evidence_gate",
    "split_reading_evidence_pack",
    "innovation_slot_map",
    "paper_selection_scorecard",
    "graph_import_plan",
    "graph_import_status",
    "experiment_monitor_plan",
}


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


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_payload(source: str) -> Any:
    text = sys.stdin.read() if source == "-" else Path(source).expanduser().read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


def first_dict(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict):
            return value
    return None


def extract_idea_catalyst_evidence_export(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    nested = [
        payload.get("evidence_export"),
        payload.get("evidenceExport"),
    ]
    for key in ["payload", "result", "data", "response"]:
        value = payload.get(key)
        if isinstance(value, dict):
            nested.extend([value.get("evidence_export"), value.get("evidenceExport")])
    return first_dict(*nested) or payload


def normalize_payload(kind: str, payload: Any) -> Any:
    if kind == "idea_catalyst_evidence_export":
        return extract_idea_catalyst_evidence_export(payload)
    return payload


def artifact_path(base: Path, kind: str, output: str | None) -> Path:
    if output:
        out = Path(output)
        return out if out.is_absolute() else base / out
    rel = ARTIFACT_PATHS.get(kind)
    if not rel:
        raise SystemExit(f"unknown artifact kind {kind}; pass --output for custom artifacts")
    return base / rel


def update_artifact_index(base: Path, rel: str, kind: str, stage: str, source: str, status: str | None) -> None:
    path = base / "artifacts_index.json"
    index = read_json(path, {"schema_version": 1, "artifacts": []})
    artifacts = [row for row in index.get("artifacts", []) if row.get("path") != rel]
    artifacts.append(
        {
            "path": rel,
            "kind": kind,
            "stage": stage,
            "source": source,
            "status": status,
            "updated_at": now(),
        }
    )
    index["schema_version"] = 1
    index["artifacts"] = artifacts
    index["updated_at"] = now()
    write_json(path, index)


def add_evidence(base: Path, args: argparse.Namespace, rel: str) -> dict[str, Any] | None:
    if not args.evidence_note:
        return None
    row = {
        "schema_version": 1,
        "evidence_id": args.evidence_id or f"ev_{uuid.uuid4().hex[:12]}",
        "created_at": now(),
        "stage": args.stage,
        "source_type": "papernexus",
        "source_id": rel,
        "item_type": args.kind,
        "paper_id": None,
        "text": args.evidence_note,
        "tags": [tag for tag in args.tag],
        "confidence": args.confidence,
        "provenance": {"artifact_path": rel, "mcp_source": args.source},
    }
    append_jsonl(base / "evidence_cart.jsonl", row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--kind", required=True, choices=sorted(ARTIFACT_PATHS))
    parser.add_argument("--input", required=True, help="JSON file path or '-' for stdin")
    parser.add_argument("--output")
    parser.add_argument("--stage", default="papernexus")
    parser.add_argument("--source", default="papernexus-remote")
    parser.add_argument("--status")
    parser.add_argument("--evidence-note")
    parser.add_argument("--evidence-id")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--confidence", default="medium")
    args = parser.parse_args()

    base = ar(args.project)
    payload = normalize_payload(args.kind, load_payload(args.input))
    metadata = {
        "schema_version": 1,
        "captured_at": now(),
        "artifact_kind": args.kind,
        "stage": args.stage,
        "source": args.source,
        "status": args.status,
    }
    if args.kind in CONTRACT_KINDS and isinstance(payload, dict):
        captured = dict(payload)
        captured["_capture"] = metadata
    else:
        captured = dict(metadata)
        captured["payload"] = payload
    out = artifact_path(base, args.kind, args.output)
    write_json(out, captured)
    rel = str(out.relative_to(base)) if out.is_relative_to(base) else str(out)
    update_artifact_index(base, rel, args.kind, args.stage, args.source, args.status)
    evidence = add_evidence(base, args, rel)
    append_jsonl(
        base / "decision_log.jsonl",
        {
            "ts": now(),
            "stage": args.stage,
            "action": "capture_papernexus_artifact",
            "details": {"kind": args.kind, "path": rel, "source": args.source, "evidence_id": (evidence or {}).get("evidence_id")},
        },
    )
    print(json.dumps({"ok": True, "path": rel, "evidence": evidence}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
