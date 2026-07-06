#!/usr/bin/env python3
"""Route reviewer weaknesses to AutoResearch child skills."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROUTES = [
    (
        "autoreskill-literature-review",
        ["citation", "reference", "recent paper", "related work", "arxiv", "missing paper", "coverage"],
        "repair citation queue, related-work evidence, or PaperNexus literature coverage",
    ),
    (
        "autoreskill-papernexus-innovation",
        ["novelty", "closest prior", "baseline", "protocol norm", "negative evidence", "source", "graph"],
        "run targeted PaperNexus discovery/material repair and update evidence boundaries",
    ),
    (
        "autoreskill-experiment-plan",
        ["experiment design", "hypothesis", "control", "falsifier", "metric drift", "dataset drift", "ablation plan"],
        "repair experiment plan, falsifier, locked protocol, or promotion gate",
    ),
    (
        "autoreskill-run-experiment",
        ["no experiment", "not significant", "trial", "std", "error bar", "replication", "seed", "ablation"],
        "schedule or repair experiment evidence under the locked protocol",
    ),
    (
        "autoreskill-analyze-results",
        ["statistic", "p-value", "confidence interval", "claim evidence", "unsupported claim", "best result"],
        "update claim-evidence matrix, statistics, unsupported claims, and narrative report",
    ),
    (
        "autoreskill-paper-write",
        ["structure", "writing", "transition", "claim too strong", "hedge", "abstract", "conclusion", "taxonomy", "clarity"],
        "revise paper representation, prose structure, claim strength, or survey taxonomy narrative",
    ),
    (
        "autoreskill-paper-write",
        ["figure", "table", "caption", "visualization", "booktabs", "axis", "legend"],
        "repair figure/table insight, captions, and manuscript integration",
    ),
]


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


def findings(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["issues", "findings", "review_findings", "items", "weaknesses"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def text_for(row: dict[str, Any]) -> str:
    fields = [
        row.get("title"),
        row.get("summary"),
        row.get("weakness"),
        row.get("description"),
        row.get("required_fix"),
        row.get("evidence_gap"),
        row.get("affected_claim"),
        row.get("section"),
    ]
    return " ".join(str(value) for value in fields if value is not None).lower()


def route(row: dict[str, Any]) -> dict[str, Any]:
    text = text_for(row)
    best: tuple[str, int, str] | None = None
    for skill, keywords, action in ROUTES:
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits and (best is None or hits > best[1]):
            best = (skill, hits, action)
    if best is None:
        return {
            "route_to": "autoreskill-review-gate",
            "confidence": "low",
            "repair_action": "triage ambiguous reviewer finding and write explicit repair packet",
        }
    confidence = "high" if best[1] >= 2 else "medium"
    return {"route_to": best[0], "confidence": confidence, "repair_action": best[2]}


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    payload = read_json(base / "reviewer/REVIEW_FINDINGS.json", {})
    rows = findings(payload)
    routed = []
    for index, row in enumerate(rows, start=1):
        item = route(row)
        routed.append(
            {
                "finding_id": row.get("finding_id") or row.get("id") or f"finding_{index:03d}",
                "severity": row.get("severity") or row.get("priority") or "unknown",
                "status": row.get("status") or row.get("state") or "open",
                "affected_claim_or_section": row.get("affected_claim") or row.get("section") or row.get("location"),
                **item,
            }
        )
    counts: dict[str, int] = {}
    for row in routed:
        counts[row["route_to"]] = counts.get(row["route_to"], 0) + 1
    return {
        "schema_version": 1,
        "generated_at": now(),
        "source": "reviewer/REVIEW_FINDINGS.json",
        "status": "complete" if routed else "incomplete",
        "grounding": "repair routing guidance only; REVIEW_FINDINGS.json remains the review authority",
        "route_counts": counts,
        "routes": routed,
        "warnings": [] if routed else ["no review findings found to route"],
    }


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    plan = read_json(base / "reviewer/WEAKNESS_ROUTING_PLAN.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(plan, dict) or not plan:
        missing.append("reviewer/WEAKNESS_ROUTING_PLAN.json")
    else:
        if plan.get("schema_version") != 1:
            missing.append("schema_version=1")
        if not isinstance(plan.get("routes"), list):
            missing.append("routes[]")
        warnings.extend(str(item) for item in plan.get("warnings", []) if isinstance(item, str))
    return {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        out = check(args.project)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        raise SystemExit(0 if out["complete"] else 1)
    payload = build(args.project)
    write_json(ar(args.project) / "reviewer/WEAKNESS_ROUTING_PLAN.json", payload)
    out = check(args.project)
    print(json.dumps({"ok": out["complete"], **out}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
