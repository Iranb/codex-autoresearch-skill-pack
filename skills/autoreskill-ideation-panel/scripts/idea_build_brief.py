#!/usr/bin/env python3
"""Generate a ScientistOne-style ideation brief from GOE projection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def ensure_projection(project: str, projection_path: Path) -> None:
    if projection_path.exists():
        return
    script = Path(__file__).resolve().parent / "idea_graph_projection.py"
    subprocess.run([sys.executable, str(script), "--project", str(Path(project).expanduser().resolve())], check=False)


def nodes_of(projection: dict[str, Any], *types: str) -> list[dict[str, Any]]:
    wanted = set(types)
    rows = projection.get("nodes") if isinstance(projection.get("nodes"), list) else []
    return [row for row in rows if isinstance(row, dict) and row.get("type") in wanted]


def summarize_nodes(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        out.append(
            {
                "label": row.get("label"),
                "node_id": row.get("id"),
                "lane": row.get("lane"),
                "evidence_ids": row.get("evidence_ids") or [],
                "source_paths": row.get("source_paths") or [],
            }
        )
    return out


def falsifier_candidates(base: Path, projection: dict[str, Any]) -> list[dict[str, Any]]:
    pool = read_json(base / "ideation/EXPERIMENT_IDEA_POOL.json", {})
    ideas = pool.get("ideas") if isinstance(pool, dict) else []
    out: list[dict[str, Any]] = []
    if isinstance(ideas, list):
        for idea in ideas:
            if not isinstance(idea, dict):
                continue
            paper = idea.get("paper_contribution") if isinstance(idea.get("paper_contribution"), dict) else {}
            falsifier = idea.get("falsifier_probe") or paper.get("falsifier")
            if present(falsifier):
                out.append({"idea_id": idea.get("id"), "falsifier": falsifier, "evidence_ids": idea.get("goe_path_refs") or []})
    if len(out) < 3:
        for node in nodes_of(projection, "negative_evidence", "limitation")[: 3 - len(out)]:
            out.append({"idea_id": None, "falsifier": f"Mechanism fails if {node.get('label')}", "evidence_ids": node.get("evidence_ids") or []})
    while len(out) < 3:
        out.append({"idea_id": None, "falsifier": "No gain under locked baseline, dataset split, and canonical evaluator.", "evidence_ids": []})
    return out[:6]


def reviewer_risks(projection: dict[str, Any]) -> list[dict[str, Any]]:
    risks = summarize_nodes(nodes_of(projection, "reviewer_risk", "negative_evidence", "limitation"), 6)
    defaults = [
        "Closest-prior overlap could make the novelty boundary too narrow.",
        "Ablation may not isolate the proposed mechanism.",
        "Dataset or metric shift could make the result non-comparable.",
    ]
    for risk in defaults:
        if len(risks) >= 3:
            break
        risks.append({"label": risk, "node_id": None, "lane": None, "evidence_ids": [], "source_paths": []})
    return risks


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    projection_path = base / "ideation/EVIDENCE_GRAPH_PROJECTION.json"
    ensure_projection(project, projection_path)
    projection = read_json(projection_path, {})
    if not isinstance(projection, dict):
        projection = {}
    gate = read_json(base / "ideation/PRE_IDEA_EVIDENCE_GATE.json", {})
    claim_limits = gate.get("claim_limits") if isinstance(gate, dict) else None
    mechanisms = nodes_of(projection, "method_mechanism", "transfer_bridge", "proposal_node")
    target_anchors = [
        row
        for row in nodes_of(projection, "paper", "protocol", "metric", "claim")
        if row.get("lane") in {"target_domain", None, ""}
    ]
    closest_priors = [row for row in nodes_of(projection, "paper") if "closest_prior" in set(row.get("roles") or []) or row.get("lane") == "target_domain"]
    negative = nodes_of(projection, "negative_evidence", "limitation")
    protocol = nodes_of(projection, "protocol", "metric", "baseline", "dataset")
    sparse = len(mechanisms) < 3 or len(target_anchors) < 1 or len(negative) < 1 or len(protocol) < 1
    return {
        "schema_version": 1,
        "generated_at": now(),
        "artifact": "IDEA_BUILD_BRIEF",
        "source_projection_path": "ideation/EVIDENCE_GRAPH_PROJECTION.json",
        "source_paths": projection.get("source_paths") or [],
        "evidence_boundary": "sparse_or_degraded" if sparse or claim_limits else "graph_projected",
        "claim_limits": claim_limits or ([] if not sparse else ["Brief is sparse; do not promote novelty or performance claims without closure."]),
        "current_field_anchor": summarize_nodes(target_anchors, 8),
        "candidate_mechanisms": summarize_nodes(mechanisms, 8),
        "closest_prior_pressure": summarize_nodes(closest_priors, 8),
        "negative_evidence": summarize_nodes(negative, 8),
        "baseline_protocol_norms": summarize_nodes(protocol, 8),
        "proposal_graph_candidates": summarize_nodes(nodes_of(projection, "proposal_node"), 5),
        "reviewer_risks": reviewer_risks(projection),
        "falsifier_candidates": falsifier_candidates(base, projection),
        "idea_generation_instruction": (
            "Generate 8-12 lightweight falsifiable causal hypotheses from current-field pressure plus "
            "near/far-neighbor or cross-lane transfer mechanisms. Deepen only a 3-5 idea shortlist, detect "
            "semantic duplicates by intervention-mechanism-prediction signature, and treat target-domain-only "
            "mechanisms as baselines or ablations unless current-field absence evidence is explicit."
        ),
    }


def md_section(title: str, rows: list[dict[str, Any]], empty: str) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.extend([empty, ""])
        return lines
    for row in rows:
        evidence = ", ".join(str(item) for item in row.get("evidence_ids", []) if present(item)) or "evidence pending"
        lines.append(f"- {row.get('label') or row.get('falsifier')} [evidence: {evidence}]")
    lines.append("")
    return lines


def to_markdown(brief: dict[str, Any]) -> str:
    lines = [
        "# IDEA_BUILD_BRIEF",
        "",
        f"Generated: {brief.get('generated_at')}",
        f"Evidence boundary: `{brief.get('evidence_boundary')}`",
        "",
    ]
    if brief.get("claim_limits"):
        lines.append("## Claim Limits")
        lines.append("")
        for item in brief["claim_limits"]:
            lines.append(f"- {item}")
        lines.append("")
    lines.extend(md_section("Current Field Anchor", brief.get("current_field_anchor", []), "No current-field anchor projected."))
    lines.extend(md_section("Candidate Mechanisms", brief.get("candidate_mechanisms", []), "No candidate mechanism projected."))
    lines.extend(md_section("Closest Prior Pressure", brief.get("closest_prior_pressure", []), "No closest-prior pressure projected."))
    lines.extend(md_section("Negative Evidence", brief.get("negative_evidence", []), "No negative evidence projected."))
    lines.extend(md_section("Baseline And Protocol Norms", brief.get("baseline_protocol_norms", []), "No baseline/protocol norms projected."))
    lines.extend(md_section("Reviewer Risks", brief.get("reviewer_risks", []), "No reviewer risks projected."))
    lines.extend(md_section("Falsifier Candidates", brief.get("falsifier_candidates", []), "No falsifiers projected."))
    lines.extend(["## Instruction", "", str(brief.get("idea_generation_instruction") or ""), ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    base = ar(args.project)
    brief = build(args.project)
    write_json(base / "ideation/IDEA_BUILD_BRIEF.json", brief)
    write_text(base / "ideation/IDEA_BUILD_BRIEF.md", to_markdown(brief))
    print(json.dumps({"ok": True, "json": "ideation/IDEA_BUILD_BRIEF.json", "markdown": "ideation/IDEA_BUILD_BRIEF.md", "evidence_boundary": brief.get("evidence_boundary")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
