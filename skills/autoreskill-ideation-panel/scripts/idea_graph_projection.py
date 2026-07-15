#!/usr/bin/env python3
"""Build a local Graph-of-Evidence projection for ideation artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXTERNAL_GATE_SCRIPT_DIR = (
    Path(__file__).resolve().parents[2] / "autoreskill-gpu-idea-validation/scripts"
)
if str(EXTERNAL_GATE_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_GATE_SCRIPT_DIR))

from external_gate_commit import (  # noqa: E402
    ExternalGateError,
    load_external_gate_commit,
    load_gate_source_mode,
    require_same_external_gate_commit,
)


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
EVIDENCE_SOURCE_MODES = {"papernexus", "external_material"}


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


def evidence_source_mode(base: Path) -> str:
    mode, _ = load_gate_source_mode(base)
    return mode


def object_rows(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    for key in keys:
        rows = value.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def refs_of(row: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ["evidence_ids", "evidence_refs", "source_refs", "material_refs", "supporting_source_refs"]:
        value = row.get(key)
        if isinstance(value, list):
            refs.extend(str(item).strip() for item in value if present(item))
        elif present(value):
            refs.append(str(value).strip())
    return sorted(set(refs))


def external_row_id(row: dict[str, Any], fallback: str) -> str:
    for key in ["external_candidate_id", "candidate_id", "node_id", "gap_id", "pattern_id", "source_id", "id"]:
        if present(row.get(key)):
            return str(row[key]).strip()
    return fallback


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


def add_external_slot_nodes(
    slots: dict[str, Any],
    slot_rel: str | None,
    nodes: dict[str, dict[str, Any]],
) -> None:
    """Project external slots without inventing lineage from array order."""
    if slot_rel is None:
        return
    mapping = {
        "challenge_clusters": "claim",
        "insight_clusters": "method_mechanism",
        "transfer_bridges": "transfer_bridge",
        "anchor_nodes": "claim",
        "relation_patterns": "claim",
    }
    for key, node_type in mapping.items():
        rows = slots.get(key)
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(item for item in rows if isinstance(item, dict)):
            slot_id = external_row_id(row, f"{key}:{index + 1}")
            label = str(row.get("summary") or row.get("label") or row.get("name") or slot_id)
            evidence_ids = refs_of(row) or [slot_id]
            add_node(
                nodes,
                node_payload(
                    node_type=node_type,
                    label=label,
                    roles=[key],
                    evidence_ids=evidence_ids,
                    source_paths=[slot_rel],
                    data={
                        "slot_id": slot_id,
                        "external_candidate_id": row.get("external_candidate_id"),
                        "explicit_relations": row.get("relations") or row.get("lineage_edges") or [],
                    },
                ),
            )


def build_external_projection(base: Path, commit: dict[str, Any]) -> dict[str, Any]:
    gate = commit["gate"]
    campaign = commit["campaign"]
    campaign_path = commit["campaign_path"]
    campaign_rel = commit["campaign_ref"]
    lint_path = commit["lint_path"]
    lint_rel = commit["lint_ref"]
    slot_path = commit["slot_path"]
    slot_rel = commit["slot_ref"]
    slot_map = commit["slot_map"]
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    id_map: dict[str, str] = {}
    source_rel = campaign_rel or "ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json"

    source_rows = object_rows(
        campaign,
        ("sources", "source_records", "materials", "evidence_records", "literature_evidence"),
    )
    for index, row in enumerate(source_rows):
        source_id = external_row_id(row, f"source:{index + 1}")
        lane = str(row.get("lane") or row.get("evidence_lane") or row.get("source_role") or "unassigned")
        label = str(row.get("title") or row.get("label") or row.get("stable_locator") or source_id)
        projected = add_node(
            nodes,
            node_payload(
                node_type="paper",
                label=label,
                lane=lane,
                roles=[str(role) for role in row.get("roles", []) if present(role)],
                evidence_ids=[source_id],
                source_paths=[source_rel],
                data={
                    "source_id": source_id,
                    "provider": row.get("provider"),
                    "locator": row.get("locator") or row.get("stable_locator"),
                    "excerpt_sha256": row.get("excerpt_sha256"),
                },
            ),
        )
        id_map[source_id] = projected

    lineage = campaign.get("method_lineage") if isinstance(campaign, dict) else None
    lineage_nodes = object_rows(lineage, ("nodes", "methods", "lineage_nodes"))
    if not lineage_nodes:
        lineage_nodes = object_rows(campaign, ("lineage_nodes", "methods", "method_nodes"))
    for index, row in enumerate(lineage_nodes):
        item_id = external_row_id(row, f"method:{index + 1}")
        label = str(row.get("label") or row.get("name") or row.get("method") or item_id)
        projected = add_node(
            nodes,
            node_payload(
                node_type="method_mechanism",
                label=label,
                lane=row.get("lane"),
                roles=["explicit_method_lineage"],
                evidence_ids=refs_of(row) or [item_id],
                source_paths=[source_rel],
                data={"external_node_id": item_id, "mechanism": row.get("mechanism")},
            ),
        )
        id_map[item_id] = projected

    gap_rows = object_rows(campaign, ("structural_gaps", "gaps", "gap_records"))
    for index, row in enumerate(gap_rows):
        gap_id = external_row_id(row, f"gap:{index + 1}")
        projected = add_node(
            nodes,
            node_payload(
                node_type="structural_gap",
                label=str(row.get("label") or row.get("gap") or row.get("summary") or gap_id),
                roles=[str(row.get("gap_type") or "structural_gap")],
                evidence_ids=refs_of(row) or [gap_id],
                source_paths=[source_rel],
                data={"gap_id": gap_id, "lineage_refs": row.get("lineage_refs") or []},
            ),
        )
        id_map[gap_id] = projected

    pattern_rows = object_rows(campaign, ("patterns", "selected_patterns", "pattern_selections"))
    for index, row in enumerate(pattern_rows):
        pattern_id = external_row_id(row, f"pattern:{index + 1}")
        projected = add_node(
            nodes,
            node_payload(
                node_type="pattern",
                label=str(row.get("label") or row.get("main_pattern") or row.get("name") or pattern_id),
                roles=["gap_closure_pattern"],
                evidence_ids=refs_of(row) or [pattern_id],
                source_paths=[source_rel],
                data={"pattern_id": pattern_id, "subpattern": row.get("subpattern")},
            ),
        )
        id_map[pattern_id] = projected

    candidate_rows = object_rows(campaign, ("candidates", "idea_candidates", "admitted_candidates"))
    for index, row in enumerate(candidate_rows):
        candidate_id = external_row_id(row, f"candidate:{index + 1}")
        evidence_ids = refs_of(row) or [candidate_id]
        candidate_node = add_node(
            nodes,
            node_payload(
                node_type="candidate",
                label=str(row.get("title") or row.get("name") or row.get("hypothesis") or candidate_id),
                roles=["external_candidate"],
                evidence_ids=evidence_ids,
                source_paths=[source_rel],
                data={"external_candidate_id": candidate_id, "status": row.get("status") or row.get("verdict")},
            ),
        )
        id_map[candidate_id] = candidate_node
        mechanism = row.get("mechanism") or row.get("method") or row.get("intervention")
        if present(mechanism):
            mechanism_label = (
                mechanism.get("intervention") or mechanism.get("one_variable_change")
                if isinstance(mechanism, dict)
                else mechanism
            )
            mechanism_node = add_node(
                nodes,
                node_payload(
                    node_type="method_mechanism",
                    label=f"{candidate_id}: {mechanism_label}",
                    roles=["candidate_mechanism"],
                    evidence_ids=evidence_ids,
                    source_paths=[source_rel],
                    data={"external_candidate_id": candidate_id},
                ),
            )
            add_edge(edges, candidate_node, mechanism_node, "anchors", evidence_ids)
        for closure_index, closure in enumerate(
            item for item in row.get("gap_closures", []) if isinstance(item, dict)
        ):
            main_pattern = str(closure.get("main_pattern") or f"pattern:{closure_index + 1}")
            subpattern = str(closure.get("subpattern") or "")
            gap_ref = str(closure.get("gap_ref") or "")
            closure_evidence = list(evidence_ids)
            gap_row = next(
                (item for item in gap_rows if external_row_id(item, "") == gap_ref),
                {},
            )
            closure_evidence = sorted(set(closure_evidence) | set(refs_of(gap_row))) or [candidate_id]
            pattern_node = add_node(
                nodes,
                node_payload(
                    node_type="pattern",
                    label=f"{main_pattern} / {subpattern}" if subpattern else main_pattern,
                    roles=["gap_closure_pattern"],
                    evidence_ids=closure_evidence,
                    source_paths=[source_rel],
                    data={
                        "external_candidate_id": candidate_id,
                        "main_pattern": main_pattern,
                        "subpattern": subpattern,
                        "gap_ref": gap_ref,
                    },
                ),
            )
            add_edge(edges, pattern_node, candidate_node, "anchors", closure_evidence)
            if gap_ref in id_map:
                add_edge(edges, pattern_node, id_map[gap_ref], "transfers_to", closure_evidence)
        negative = row.get("negative_control") or row.get("negativeControl")
        if present(negative):
            negative_node = add_node(
                nodes,
                node_payload(
                    node_type="negative_evidence",
                    label=f"{candidate_id}: {negative}",
                    roles=["negative_control"],
                    evidence_ids=evidence_ids,
                    source_paths=[source_rel],
                    data={"external_candidate_id": candidate_id},
                ),
            )
            add_edge(edges, negative_node, candidate_node, "contradicts", evidence_ids)
        protocol = row.get("pilot_protocol") or row.get("validation_protocol") or row.get("protocol") or row.get("rapid_validation")
        if present(protocol):
            protocol_node = add_node(
                nodes,
                node_payload(
                    node_type="protocol",
                    label=f"{candidate_id}: bounded pilot protocol",
                    roles=["falsification_protocol"],
                    evidence_ids=evidence_ids,
                    source_paths=[source_rel],
                    data={"external_candidate_id": candidate_id, "protocol": protocol},
                ),
            )
            add_edge(edges, protocol_node, candidate_node, "evaluates_on", evidence_ids)
        for source_id in refs_of(row):
            if source_id in id_map:
                add_edge(edges, id_map[source_id], candidate_node, "supports", [source_id])

    explicit_edges = object_rows(lineage, ("edges", "relations", "lineage_edges"))
    explicit_edges.extend(object_rows(campaign, ("lineage_edges", "explicit_relations")))
    for row in explicit_edges:
        source = str(row.get("source") or row.get("from") or row.get("source_id") or "").strip()
        target = str(row.get("target") or row.get("to") or row.get("target_id") or "").strip()
        if source not in id_map or target not in id_map:
            continue
        relation = str(row.get("type") or row.get("relation") or row.get("edge_type") or "supports").strip()
        evidence_ids = refs_of(row)
        if not evidence_ids:
            # Explicit but unsupported lineage is intentionally not projected.
            continue
        add_edge(edges, id_map[source], id_map[target], relation, evidence_ids)

    add_external_slot_nodes(slot_map, slot_rel, nodes)
    add_reviewer_risk_nodes(base, nodes, edges)
    scorecard_rel = "ideation/IDEA_NOVELTY_VENUE_SCORECARD.json"
    source_candidates = [
        (campaign_path, source_rel),
        (lint_path, lint_rel),
        (slot_path, slot_rel),
        (base / scorecard_rel, scorecard_rel),
    ]
    return {
        "schema_version": 1,
        "generated_at": now(),
        "artifact": "EVIDENCE_GRAPH_PROJECTION",
        "evidence_source_mode": "external_material",
        "external_campaign_ref": source_rel,
        "external_campaign_sha256": gate.get("campaign_sha256") if isinstance(gate, dict) else None,
        "source_paths": [rel for path, rel in source_candidates if path is not None and rel is not None and path.exists()],
        "node_type_set": sorted({str(node.get("type")) for node in nodes.values()}),
        "edge_type_set": sorted({str(edge.get("type")) for edge in edges.values()}),
        "lane_coverage": lane_coverage(nodes),
        "nodes": sorted(nodes.values(), key=lambda row: (str(row.get("type")), str(row.get("label")))),
        "edges": sorted(edges.values(), key=lambda row: str(row.get("id"))),
    }


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


def build(project: str, external_commit: dict[str, Any] | None = None) -> dict[str, Any]:
    base = ar(project)
    if external_commit is not None:
        return build_external_projection(base, external_commit)
    mode = evidence_source_mode(base)
    if mode == "external_material":
        return build_external_projection(base, load_external_gate_commit(base))
    if mode not in EVIDENCE_SOURCE_MODES:
        return {
            "schema_version": 1,
            "generated_at": now(),
            "artifact": "EVIDENCE_GRAPH_PROJECTION",
            "evidence_source_mode": mode,
            "source_paths": [],
            "node_type_set": [],
            "edge_type_set": [],
            "lane_coverage": {},
            "nodes": [],
            "edges": [],
            "errors": ["evidence_source_mode must be papernexus or external_material"],
        }
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", default="ideation/EVIDENCE_GRAPH_PROJECTION.json")
    args = parser.parse_args()
    base = ar(args.project)
    external_commit = None
    try:
        if evidence_source_mode(base) == "external_material":
            external_commit = load_external_gate_commit(base)
        projection = build(args.project, external_commit)
        if external_commit is not None:
            require_same_external_gate_commit(external_commit, load_external_gate_commit(base))
    except ExternalGateError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": "external_gate_invalid", "message": str(exc)}},
                indent=2,
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = base / args.output
    write_json(output, projection)
    print(json.dumps({"ok": True, "path": str(output), "nodes": len(projection["nodes"]), "edges": len(projection["edges"])}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
