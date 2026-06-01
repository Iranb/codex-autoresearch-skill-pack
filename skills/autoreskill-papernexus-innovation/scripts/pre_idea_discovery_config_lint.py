#!/usr/bin/env python3
"""Lint PaperNexus discovery configuration before idea generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


LANES = {"target_domain", "near_neighbor", "far_neighbor"}
PLAN_REL = "literature/PRE_IDEA_DISCOVERY_PLAN.json"

REQUIRED_EQUALS = {
    "operation": "search",
    "depth": "deep",
    "searchMode": "deep",
    "planningMode": "llm_augmented",
    "llmQueryPlanner": True,
    "citationExpansion": True,
    "openAlexRelatedExpansion": True,
    "allowDownloads": False,
    "importResolved": False,
    "processImports": False,
    "returnPartial": True,
    "persist": True,
}

MIN_VALUES = {
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
}


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
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def check_config(config: Any, label: str) -> list[str]:
    missing: list[str] = []
    if not isinstance(config, dict):
        return [f"{label} required_literature_discovery_args"]

    for key, expected in REQUIRED_EQUALS.items():
        actual = config.get(key)
        if actual != expected:
            missing.append(f"{label}.{key}={expected!r} (found {actual!r})")

    for key, minimum in MIN_VALUES.items():
        actual = config.get(key)
        if not isinstance(actual, (int, float)) or actual < minimum:
            missing.append(f"{label}.{key}>={minimum} (found {actual!r})")

    if "lane" in config:
        missing.append(f"{label} must not pass lane as a literature_discovery MCP argument; encode lane focus in topic")
    if not present(config.get("topic")) and label.startswith("lane."):
        missing.append(f"{label}.topic with explicit lane focus")
    return missing


def latest_ideation_job(base: Path) -> dict[str, Any] | None:
    packets: list[tuple[str, Path, dict[str, Any]]] = []
    for path in (base / "job_packets").glob("job_*.json"):
        payload = read_json(path)
        if isinstance(payload, dict) and payload.get("stage") == "ideation":
            packets.append((str(payload.get("created_at") or path.stat().st_mtime), path, payload))
    if not packets:
        return None
    packets.sort(key=lambda row: row[0])
    path = packets[-1][1]
    payload = dict(packets[-1][2])
    payload["_path"] = str(path)
    return payload


def job_search_configs(job: dict[str, Any]) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    calls = job.get("mcp_calls")
    if not isinstance(calls, list):
        return configs
    for call in calls:
        if not isinstance(call, dict) or call.get("tool") != "literature_discovery":
            continue
        args = call.get("args")
        if isinstance(args, dict) and args.get("operation") == "search":
            configs.append(args)
    return configs


def lint(project: str, require_job_packet: bool = False) -> dict[str, Any]:
    base = ar(project)
    missing: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {
        "required_equals": REQUIRED_EQUALS,
        "min_values": MIN_VALUES,
    }

    plan_path = base / PLAN_REL
    plan = read_json(plan_path)
    if not isinstance(plan, dict):
        missing.append(PLAN_REL)
    else:
        missing.extend(check_config(plan.get("required_literature_discovery_args"), "plan"))
        policy = plan.get("metadata_pass_policy")
        if not isinstance(policy, dict):
            missing.append("PRE_IDEA_DISCOVERY_PLAN.metadata_pass_policy")
        else:
            if policy.get("encode_lane_focus_in_topic") is not True:
                missing.append("metadata_pass_policy.encode_lane_focus_in_topic=true")
            if policy.get("do_not_pass_lane_as_mcp_arg") is not True:
                missing.append("metadata_pass_policy.do_not_pass_lane_as_mcp_arg=true")

        lane_configs: dict[str, Any] = {}
        for row in plan.get("lanes", []) if isinstance(plan.get("lanes"), list) else []:
            if isinstance(row, dict):
                lane = str(row.get("lane") or "")
                if lane in LANES:
                    lane_configs[lane] = row.get("required_literature_discovery_args")
                    missing.extend(check_config(row.get("required_literature_discovery_args"), f"lane.{lane}"))
        for lane in sorted(LANES):
            if lane not in lane_configs:
                missing.append(f"PRE_IDEA_DISCOVERY_PLAN.lanes[{lane}].required_literature_discovery_args")
        details["lane_configs_found"] = sorted(lane_configs)

    job = latest_ideation_job(base)
    if not job:
        if require_job_packet:
            missing.append("latest ideation job packet with broad literature_discovery calls")
    else:
        details["latest_ideation_job_packet"] = job.get("_path")
        configs = job_search_configs(job)
        details["latest_ideation_job_search_call_count"] = len(configs)
        if len(configs) < 3:
            missing.append("latest ideation job packet has fewer than three literature_discovery search calls")
        for idx, config in enumerate(configs[:3], start=1):
            job_missing = check_config(config, f"latest_ideation_job.search_call_{idx}")
            if job_missing:
                missing.extend(job_missing)

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "path": str(plan_path),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--require-job-packet", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.require_job_packet)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
