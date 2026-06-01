#!/usr/bin/env python3
"""Build a local Graph-of-Evidence projection for ideation artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROLE_TO_NODE_TYPE = {
    "closest_prior": "paper",
    "baseline_protocol": "protocol",
    "dataset_metric": "metric",
    "mechanism": "method_mechanism",
    "limitation_future": "limitation",
    "negative_evidence": "negative_evidence",
    "transfer_bridge": "transfer_bridge",
    "challenge_anchor": "claim",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_root(project: str) -> Path:
    return Path(project).expanduser().resolve()


def ar(project: str) -> Path:
    return project_root(project) / ".autoreskill"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def text_of(row: dict[str, Any]) -> str:
    parts = [
        row.get("title"),
        row.get("name"),
        row.get("abstract"),
        row.get("summary"),
        row.get("rationale"),
        row.get("notes"),
    ]
    return " ".join(str(part) for part in parts if present(part)).lower()


def infer_roles(row: dict[str, Any]) -> list[str]:
    lane = str(row.get("lane") or row.get("evidence_lane") or "").strip().lower()
    text = text_of(row)
    roles: set[str] = set()
    if lane == "target_domain":
        roles.update({"closest_prior", "baseline_protocol"})
    if lane in {"near_neighbor", "far_neighbor"}:
        roles.update({"mechanism", "transfer_bridge"})
    if any(word in text for word in ["baseline", "protocol", "evaluation", "evaluator"]):
        roles.add("baseline_protocol")
    if any(word in text for word in ["dataset", "metric", "benchmark", "split"]):
        roles.add("dataset_metric")
    if any(word in text for word in ["mechanism", "prototype", "alignment", "adaptation", "control", "feedback", "optimization"]):
        roles.add("mechanism")
    if any(word in text for word in ["negative", "failure", "limitation", "fails", "risk"]):
        roles.update({"negative_evidence", "limitation_future"})
    if any(word in text for word in ["transfer", "bridge", "analogy", "external", "neighbor"]):
        roles.add("transfer_bridge")
    if any(word in text for word in ["claim", "gap", "challenge", "pressure"]):
        roles.add("challenge_anchor")
    return sorted(roles)


def node_payload(
    *,
    node_type: str,
    label: str,
    lane: str | None = None,
    roles: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    source_paths: list[str] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node_id = stable_id(node_type, label, lane, ",".join(roles or []), ",".join(evidence_ids or []))
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "lane": lane,
        "roles": roles or [],
        "evidence_ids": evidence_ids or [],
        "source_paths": source_paths or [],
        "data": data or {},
    }


def add_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> str:
    existing = nodes.get(node["id"])
    if existing:
        existing["roles"] = sorted(set(existing.get("roles", [])) | set(node.get("roles", [])))
        existing["evidence_ids"] = sorted(set(existing.get("evidence_ids", [])) | set(node.get("evidence_ids", [])))
        existing["source_paths"] = sorted(set(existing.get("source_paths", [])) | set(node.get("source_paths", [])))
        return existing["id"]
    nodes[node["id"]] = node
    return node["id"]


def add_edge(edges: dict[str, dict[str, Any]], source: str, target: str, edge_type: str, evidence_ids: list[str]) -> None:
    edge_id = stable_id("edge", source, target, edge_type)
    edges[edge_id] = {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": edge_type,
        "evidence_ids": sorted(set(evidence_ids)),
    }


def row_evidence_id(row: dict[str, Any], fallback: str) -> str:
    for key in ["evidence_id", "paper_id", "id", "doi", "arxiv", "pmid"]:
        value = row.get(key)
        if present(value):
            return str(value)
    identifiers = row.get("identifiers")
    if isinstance(identifiers, dict):
        for key in ["doi", "arxiv", "pmid", "pmcid", "semantic_scholar_id"]:
            value = identifiers.get(key)
            if present(value):
                return str(value)
    return fallback


def candidates_from_scorecard(scorecard: Any) -> list[dict[str, Any]]:
    if isinstance(scorecard, dict):
        for key in ["candidates", "papers", "rows", "items"]:
            if isinstance(scorecard.get(key), list):
                return [row for row in scorecard[key] if isinstance(row, dict)]
    return []


def add_candidate_nodes(base: Path, nodes: dict[str, dict[str, Any]], edges: dict[str, dict[str, Any]]) -> None:
    source_rel = "papernexus/PAPER_SELECTION_SCORECARD.json"
    rows = candidates_from_scorecard(read_json(base / source_rel, {}))
    for index, row in enumerate(rows):
        title = str(row.get("title") or row.get("paper_title") or row.get("id") or f"paper-{index + 1}").strip()
        lane = str(row.get("lane") or row.get("evidence_lane") or "unknown").strip()
        evidence_id = row_evidence_id(row, f"selection:{index + 1}")
        roles = sorted(set(row.get("roles") or []) | set(infer_roles(row)))
        paper_id = add_node(
            nodes,
            node_payload(
                node_type="paper",
                label=title,
                lane=lane,
                roles=roles,
                evidence_ids=[evidence_id],
                source_paths=[source_rel],
                data={
                    "decision": row.get("decision"),
                    "graph_or_material_selected": row.get("graph_or_material_selected"),
                },
            ),
        )
        for role in roles:
            node_type = ROLE_TO_NODE_TYPE.get(role)
            if not node_type or node_type == "paper":
                continue
            role_id = add_node(
                nodes,
                node_payload(
                    node_type=node_type,
                    label=f"{role}: {title}",
                    lane=lane,
                    roles=[role],
                    evidence_ids=[evidence_id],
                    source_paths=[source_rel],
                ),
            )
            edge_type = "supports"
            if node_type == "transfer_bridge":
                edge_type = "transfers_to"
            elif node_type in {"protocol", "metric"}:
                edge_type = "evaluates_on"
            elif node_type == "negative_evidence":
                edge_type = "contradicts"
            add_edge(edges, paper_id, role_id, edge_type, [evidence_id])


def add_split_reading_nodes(base: Path, nodes: dict[str, dict[str, Any]], edges: dict[str, dict[str, Any]]) -> None:
    source_rel = "papernexus/SPLIT_READING_EVIDENCE_PACK.json"
    pack = read_json(base / source_rel, {})
    views = pack.get("paper_material_views") if isinstance(pack, dict) else None
    if not isinstance(views, list):
        return
    for index, view in enumerate(row for row in views if isinstance(row, dict)):
        paper_label = str(view.get("title") or view.get("paper_id") or f"split-paper-{index + 1}")
        evidence_id = row_evidence_id(view, f"split:{index + 1}")
        roles = [str(role) for role in view.get("roles", []) if present(role)]
        paper_id = add_node(
            nodes,
            node_payload(
                node_type="paper",
                label=paper_label,
                lane=view.get("lane"),
                roles=roles,
                evidence_ids=[evidence_id],
                source_paths=[source_rel],
                data={"paper_material_view": True},
            ),
        )
        for role in roles:
            node_type = ROLE_TO_NODE_TYPE.get(role, "claim")
            if node_type == "paper":
                continue
            role_id = add_node(
                nodes,
                node_payload(
                    node_type=node_type,
                    label=f"{role}: {paper_label}",
                    lane=view.get("lane"),
                    roles=[role],
                    evidence_ids=[evidence_id],
                    source_paths=[source_rel],
                ),
            )
            add_edge(edges, paper_id, role_id, "supports", [evidence_id])


def add_slot_nodes(base: Path, nodes: dict[str, dict[str, Any]], edges: dict[str, dict[str, Any]]) -> None:
    source_rel = "ideation/INNOVATION_SLOT_MAP.json"
    slots = read_json(base / source_rel, {})
    if not isinstance(slots, dict):
        return
    mapping = {
        "challenge_clusters": "claim",
        "insight_clusters": "method_mechanism",
        "transfer_bridges": "transfer_bridge",
        "anchor_nodes": "claim",
        "relation_patterns": "claim",
    }
    previous_ids: list[str] = []
    for key, node_type in mapping.items():
        rows = slots.get(key)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(item for item in rows if isinstance(item, dict)):
            slot_id = str(row.get("slot_id") or row.get("id") or f"{key}:{index + 1}")
            label = str(row.get("summary") or row.get("label") or row.get("name") or slot_id)
            evidence_ids = [str(ref) for ref in row.get("evidence_ids", []) if present(ref)] or [slot_id]
            node_id = add_node(
                nodes,
                node_payload(
                    node_type=node_type,
                    label=label,
                    roles=[key],
                    evidence_ids=evidence_ids,
                    source_paths=[source_rel],
                    data={"slot_id": slot_id},
                ),
            )
            for prev in previous_ids[-3:]:
                add_edge(edges, prev, node_id, "extends", evidence_ids)
            previous_ids.append(node_id)


def add_proposal_nodes(base: Path, nodes: dict[str, dict[str, Any]], edges: dict[str, dict[str, Any]]) -> None:
    candidates = [
        "papernexus/proposal_graph_session.json",
        "papernexus/proposal-session-manifest.json",
    ]
    for source_rel in candidates:
        payload = read_json(base / source_rel, {})
        if not isinstance(payload, dict):
            continue
        run_id = str(payload.get("run_id") or payload.get("runId") or payload.get("session_id") or source_rel)
        label = str(payload.get("proposal_title") or payload.get("title") or payload.get("status") or run_id)
        evidence_ids = [run_id]
        proposal_id = add_node(
            nodes,
            node_payload(
                node_type="proposal_node",
                label=f"proposal graph: {label}",
                roles=["proposal_graph_session"],
                evidence_ids=evidence_ids,
                source_paths=[source_rel],
                data={
                    "run_id": run_id,
                    "committed_subgraph_id": payload.get("committed_subgraph_id") or payload.get("committedSubgraphId"),
                    "status": payload.get("status"),
                },
            ),
        )
        for node in list(nodes.values()):
            if node["id"] != proposal_id and node.get("type") in {"claim", "method_mechanism", "transfer_bridge", "reviewer_risk"}:
                add_edge(edges, proposal_id, node["id"], "anchors", evidence_ids)


def add_reviewer_risk_nodes(base: Path, nodes: dict[str, dict[str, Any]], edges: dict[str, dict[str, Any]]) -> None:
    source_rel = "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json"
    scorecard = read_json(base / source_rel, {})
    rows: list[dict[str, Any]] = []
    if isinstance(scorecard, dict):
        for key in ["rows", "ideas", "scores", "scorecard"]:
            if isinstance(scorecard.get(key), list):
                rows = [row for row in scorecard[key] if isinstance(row, dict)]
                break
    for index, row in enumerate(rows):
        idea_id = str(row.get("id") or row.get("idea_id") or f"idea-{index + 1}")
        risks = row.get("reviewer_attack_surface") or row.get("evidence_debt") or row.get("target_domain_method_overlap_risk")
        risk_items = risks if isinstance(risks, list) else [risks] if present(risks) else []
        for risk_index, risk in enumerate(risk_items[:3]):
            risk_id = add_node(
                nodes,
                node_payload(
                    node_type="reviewer_risk",
                    label=f"{idea_id}: {risk}",
                    roles=["reviewer_risk"],
                    evidence_ids=[idea_id],
                    source_paths=[source_rel],
                    data={"idea_id": idea_id},
                ),
            )
            for node in list(nodes.values()):
                if node.get("type") in {"method_mechanism", "claim"}:
                    add_edge(edges, risk_id, node["id"], "risks_overlap_with", [idea_id])
                    break


def lane_coverage(nodes: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
    coverage: dict[str, dict[str, int]] = {}
    for node in nodes.values():
        lane = str(node.get("lane") or "unassigned")
        bucket = coverage.setdefault(lane, {"papers": 0, "mechanisms": 0, "negative_evidence": 0, "protocols": 0})
        if node.get("type") == "paper":
            bucket["papers"] += 1
        if node.get("type") in {"method_mechanism", "transfer_bridge", "proposal_node"}:
            bucket["mechanisms"] += 1
        if node.get("type") in {"negative_evidence", "limitation"}:
            bucket["negative_evidence"] += 1
        if node.get("type") in {"protocol", "baseline", "dataset", "metric"}:
            bucket["protocols"] += 1
    return coverage


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    add_candidate_nodes(base, nodes, edges)
    add_split_reading_nodes(base, nodes, edges)
    add_slot_nodes(base, nodes, edges)
    add_proposal_nodes(base, nodes, edges)
    add_reviewer_risk_nodes(base, nodes, edges)
    paths = [
        "papernexus/PAPER_SELECTION_SCORECARD.json",
        "papernexus/SPLIT_READING_EVIDENCE_PACK.json",
        "ideation/INNOVATION_SLOT_MAP.json",
        "papernexus/proposal_graph_session.json",
        "papernexus/proposal-session-manifest.json",
        "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json",
    ]
    return {
        "schema_version": 1,
        "generated_at": now(),
        "artifact": "EVIDENCE_GRAPH_PROJECTION",
        "source_paths": [path for path in paths if (base / path).exists()],
        "node_type_set": sorted({str(node.get("type")) for node in nodes.values()}),
        "edge_type_set": sorted({str(edge.get("type")) for edge in edges.values()}),
        "lane_coverage": lane_coverage(nodes),
        "nodes": sorted(nodes.values(), key=lambda row: (str(row.get("type")), str(row.get("label")))),
        "edges": sorted(edges.values(), key=lambda row: str(row.get("id"))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", default="ideation/EVIDENCE_GRAPH_PROJECTION.json")
    args = parser.parse_args()
    base = ar(args.project)
    projection = build(args.project)
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = base / args.output
    write_json(output, projection)
    print(json.dumps({"ok": True, "path": str(output), "nodes": len(projection["nodes"]), "edges": len(projection["edges"])}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
