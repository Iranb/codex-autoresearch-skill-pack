#!/usr/bin/env python3
"""Materialize a three-lane pre-idea discovery plan."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LANES = {
    "target_domain": {
        "intent": "closest priors, SOTA, baselines, datasets, metrics, protocols, and negative evidence in the target domain",
        "expected_roles": ["closest_prior", "baseline_protocol", "dataset_metric", "mechanism", "limitation_future", "negative_evidence"],
        "exclusion_rules": ["do not treat generic surveys or benchmark-only papers as mechanism evidence"],
        "min_candidates": 12,
        "min_eligible": 8,
        "max_rounds": 5,
    },
    "near_neighbor": {
        "intent": "related but different directions with shared task/evaluation pressure and different mechanisms or assumptions",
        "expected_roles": ["near_neighbor_pressure", "mechanism", "limitation_future", "negative_evidence"],
        "exclusion_rules": ["exclude exact duplicate closest-prior lineage unless it supplies a distinct mechanism"],
        "min_candidates": 8,
        "min_eligible": 5,
        "max_rounds": 5,
    },
    "far_neighbor": {
        "intent": "storyline-driven source domains found through domain-agnostic challenge abstraction and transferable mechanisms",
        "expected_roles": ["transfer_bridge", "mechanism", "challenge_anchor", "limitation_future"],
        "exclusion_rules": ["exclude overly proximal subfields and generic analogies without source-backed mechanisms"],
        "min_candidates": 8,
        "min_eligible": 5,
        "max_rounds": 6,
    },
}

BROAD_METADATA_DISCOVERY = {
    "operation": "search",
    "depth": "deep",
    "searchMode": "deep",
    "planningMode": "llm_augmented",
    "llmQueryPlanner": True,
    "citationExpansion": True,
    "openAlexRelatedExpansion": True,
    "maxCandidates": 10000,
    "maxQueries": 48,
    "maxQueriesPerProvider": 8,
    "maxResultsPerQuery": 150,
    "maxLlmQueries": 16,
    "maxCitationSeeds": 24,
    "maxCitationsPerSeed": 50,
    "maxRelatedPerSeed": 50,
    "maxEntityQueries": 48,
    "maxExtractedEntities": 160,
    "maxSeedEntities": 100,
    "maxSeedPapers": 50,
    "maxSeedQueries": 40,
    "papersCoolMaxQueries": 48,
    "pasaMaxQueries": 20,
    "providerConcurrency": 4,
    "retryCount": 5,
    "timeoutMs": 300000,
    "searchBudgetMs": 300000,
    "preferMarkdown": True,
    "generateArxivMarkdownSources": True,
    "allowDownloads": False,
    "importResolved": False,
    "processImports": False,
    "returnPartial": True,
    "persist": True,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_json(path: Path, data: Any, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def infer_topic(project: str) -> str:
    base = ar(project)
    for rel in ["goal_state.json", "PROJECT_GOAL.json", "project_brief.json"]:
        payload = read_json(base / rel)
        if isinstance(payload, dict):
            for key in ["topic", "research_topic", "goal", "objective", "problem"]:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return "research topic required"


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    topic = args.topic.strip() if args.topic else infer_topic(args.project)
    target_domain = args.target_domain.strip() if args.target_domain else "target domain to be resolved"
    plan_lanes = []
    for lane, defaults in LANES.items():
        if lane == "target_domain":
            seed_terms = [topic, target_domain, "baseline", "dataset", "metric", "failure mode"]
            domain_constraints = [target_domain]
        elif lane == "near_neighbor":
            seed_terms = [topic, "related task different mechanism", "neighboring method family", "different assumptions"]
            domain_constraints = ["related but not identical direction"]
        else:
            seed_terms = [topic, "domain agnostic challenge", "transferable mechanism", "interdisciplinary insight"]
            domain_constraints = ["external source domains selected from unresolved challenge abstraction"]
        plan_lanes.append(
            {
                "lane": lane,
                "intent": defaults["intent"],
                "seed_terms": seed_terms,
                "domain_constraints": domain_constraints,
                "exclusion_rules": defaults["exclusion_rules"],
                "expected_roles": defaults["expected_roles"],
                "min_candidates": defaults["min_candidates"],
                "min_eligible": defaults["min_eligible"],
                "max_rounds": defaults["max_rounds"],
                "required_literature_discovery_args": {
                    **BROAD_METADATA_DISCOVERY,
                    "topic": " ".join(seed_terms),
                    "lane_focus": lane,
                },
            }
        )
    return {
        "schema_version": 1,
        "created_at": now(),
        "topic": topic,
        "target_domain": target_domain,
        "minimum_lane_attempts": {"target_domain": 1, "near_neighbor": 1, "far_neighbor": 1},
        "required_literature_discovery_args": BROAD_METADATA_DISCOVERY,
        "metadata_pass_policy": {
            "description": "First pass is broad metadata discovery: wide recall, no downloads, no imports, persisted diagnostics.",
            "lane_is_workflow_metadata": True,
            "encode_lane_focus_in_topic": True,
            "do_not_pass_lane_as_mcp_arg": True,
        },
        "lanes": plan_lanes,
        "query_families": {
            "target_domain": ["closest prior", "baseline protocol", "dataset metric", "negative evidence", "limitation future"],
            "near_neighbor": ["same task different mechanism", "same metric different assumption", "related failure mode"],
            "far_neighbor": ["domain agnostic challenge", "external source domain mechanism", "storyline transfer bridge"],
        },
        "expansion_triggers": [
            "lane raw candidates below threshold",
            "eligible candidates below threshold",
            "source-resolvable count too low",
            "duplicates dominate results",
            "target lane lacks closest prior or baseline/protocol",
            "near lane collapses into target-domain duplicate lineage",
            "far lane lacks transferable mechanisms or source spans",
            "split-reading role coverage is missing mechanism/evidence/future/negative layers",
        ],
        "paper_role_targets": [
            "closest_prior",
            "baseline_protocol",
            "dataset_metric",
            "mechanism",
            "limitation_future",
            "negative_evidence",
            "challenge_anchor",
            "transfer_bridge",
            "reviewer_risk",
        ],
        "source_resolution_policy": {
            "prefer": ["doi", "arxiv", "pmid", "pmcid", "open_access_pdf", "legal_markdown"],
            "reject_if_unresolved_after_bounded_retry": True,
        },
        "dedupe_policy": {
            "keys": ["doi", "arxiv", "pmid", "pmcid", "canonicalId", "normalized_title"],
            "keep_highest_role_coverage": True,
        },
        "status": "planned",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--topic")
    parser.add_argument("--target-domain")
    parser.add_argument("--output", default="literature/PRE_IDEA_DISCOVERY_PLAN.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    base = ar(args.project)
    out = base / args.output
    write_json(out, build_plan(args), args.force)
    print(json.dumps({"ok": True, "path": str(out), "lanes": sorted(LANES)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
