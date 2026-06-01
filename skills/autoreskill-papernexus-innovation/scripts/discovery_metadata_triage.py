#!/usr/bin/env python3
"""Triage PaperNexus literature discovery results for pre-idea evidence gating.

The historical output was a metadata-only import/watch/reject triage.  The
pre-idea gate needs a stronger, lane-aware scorecard that can reject duplicate,
weak, no-source, survey, and generic benchmark noise before anything is queued
for graph import or split-reading material extraction.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LANES = {"target_domain", "near_neighbor", "far_neighbor"}
HIGH_SIGNAL = {
    "generalized category discovery",
    "category discovery",
    "novel target discovery",
    "open-set domain adaptation",
    "source-free",
    "target-private",
    "unknown",
    "prototype",
    "domain shift",
    "domain adaptation",
    "class discovery",
}

BASELINE_HINTS = {"hilo", "dg-gcd", "sim gcd", "simgcd", "cms", "debgcd", "free", "fda", "cdad"}
BENCHMARK_HINTS = {"domainnet", "office-home", "visda", "ssb", "imagenet-r", "herbarium", "benchmark"}
MECHANISM_HINTS = {"mechanism", "module", "architecture", "objective", "loss", "optimization", "prototype", "adaptation", "regularization"}
LIMITATION_HINTS = {"limitation", "failure", "fails", "challenge", "open problem", "future work", "unresolved", "bottleneck"}
SUBSTANTIVE_LIMITATION_HINTS = {"limitation", "failure", "fails", "open problem", "future work", "unresolved", "bottleneck"}
NEGATIVE_HINTS = {"negative", "null result", "does not improve", "degradation", "regression", "failure case", "ablation"}
SURVEY_HINTS = {"survey", "review", "systematic literature review", "overview", "taxonomy"}
GENERIC_BENCHMARK_HINTS = {"benchmarking", "benchmark suite", "dataset benchmark", "leaderboard"}
FAR_TRANSFER_HINTS = {"analogy", "transfer", "control", "psychology", "sociology", "cognitive", "coordination", "feedback", "adaptation"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def resolve(base: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return base.parent / raw
    return base / path


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def unwrap(payload: Any) -> Any:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "text" in payload[0]:
        try:
            return json.loads(str(payload[0]["text"]))
        except json.JSONDecodeError:
            return payload
    if isinstance(payload, dict) and "payload" in payload:
        return payload["payload"]
    return payload


def collect_candidates(payload: Any) -> list[dict[str, Any]]:
    payload = unwrap(payload)
    if isinstance(payload, dict):
        rows: list[dict[str, Any]] = []
        for key in ["candidates", "papers", "results", "raw_results", "discovered_near_source_candidates"]:
            value = payload.get(key)
            if isinstance(value, list):
                rows.extend(row for row in value if isinstance(row, dict))
        attempts = payload.get("attempts")
        if isinstance(attempts, list):
            for attempt in attempts:
                if isinstance(attempt, dict):
                    rows.extend(collect_candidates(attempt))
        if rows:
            return rows
        nested = payload.get("payload")
        if nested is not None:
            return collect_candidates(nested)
    return []


def get_text(row: dict[str, Any]) -> str:
    props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    pieces = [
        row.get("title"),
        row.get("name"),
        row.get("abstract"),
        row.get("venue"),
        props.get("title"),
        props.get("name"),
        props.get("abstract"),
        props.get("venue"),
    ]
    return " ".join(str(piece or "") for piece in pieces).lower()


def identifiers(row: dict[str, Any]) -> dict[str, Any]:
    props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    ids = row.get("identifiers") if isinstance(row.get("identifiers"), dict) else {}
    pids = props.get("identifiers") if isinstance(props.get("identifiers"), dict) else {}
    out = dict(ids)
    out.update(pids)
    canonical = row.get("canonicalId") or props.get("canonicalId") or row.get("id")
    if canonical:
        out["canonicalId"] = canonical
    for key in ["doi", "arxiv", "arxivId", "pmid", "pmcid", "url", "pdfUrl", "openAccessPdf"]:
        if row.get(key) and key not in out:
            out[key] = row.get(key)
        if props.get(key) and key not in out:
            out[key] = props.get(key)
    return out


def title(row: dict[str, Any]) -> str:
    props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    return str(row.get("title") or row.get("name") or props.get("title") or props.get("name") or "").strip()


def venue(row: dict[str, Any]) -> str:
    props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    return str(row.get("venue") or props.get("venue") or "").strip()


def year(row: dict[str, Any]) -> Any:
    props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    return row.get("year") or props.get("year")


def norm_title(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def dedupe_key(row: dict[str, Any]) -> str:
    ids = identifiers(row)
    for key in ["doi", "arxiv", "arxivId", "pmid", "pmcid", "canonicalId"]:
        value = ids.get(key)
        if value:
            return f"{key}:{str(value).strip().lower()}"
    return "title:" + norm_title(title(row))


def source_resolvable(row: dict[str, Any]) -> bool:
    ids = identifiers(row)
    if any(ids.get(key) for key in ["doi", "arxiv", "arxivId", "pmid", "pmcid", "url", "pdfUrl", "openAccessPdf"]):
        return True
    text = get_text(row)
    return "arxiv.org" in text or "doi.org" in text or "pdf" in text


def bool_hint(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def lane_of(row: dict[str, Any], default_lane: str) -> str:
    props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    raw = str(row.get("lane") or props.get("lane") or default_lane or "").strip().lower()
    raw = raw.replace("-", "_").replace(" ", "_")
    return raw if raw in LANES else default_lane


def roles_for_candidate(row: dict[str, Any], lane: str) -> list[str]:
    text = get_text(row)
    roles: set[str] = set()
    if lane == "target_domain":
        roles.add("challenge_anchor")
    if bool_hint(text, BASELINE_HINTS):
        roles.update(["closest_prior", "baseline_protocol"])
    if bool_hint(text, BENCHMARK_HINTS) or "dataset" in text or "metric" in text:
        roles.add("dataset_metric")
    if bool_hint(text, MECHANISM_HINTS):
        roles.add("mechanism")
    if bool_hint(text, LIMITATION_HINTS):
        roles.add("limitation_future")
    if bool_hint(text, NEGATIVE_HINTS):
        roles.add("negative_evidence")
    if lane == "near_neighbor":
        roles.add("near_neighbor_pressure")
    if lane == "far_neighbor" or bool_hint(text, FAR_TRANSFER_HINTS):
        roles.add("transfer_bridge")
    return sorted(roles)


def score_candidate(row: dict[str, Any], lane: str, duplicate: bool = False) -> tuple[int, list[str], list[str], dict[str, bool]]:
    text = get_text(row)
    reasons: list[str] = []
    flags = {
        "duplicate": duplicate,
        "source_resolvable": source_resolvable(row),
        "survey_noise": bool_hint(text, SURVEY_HINTS),
        "substantive_limitation": bool_hint(text, SUBSTANTIVE_LIMITATION_HINTS),
        "generic_benchmark_risk": bool_hint(text, GENERIC_BENCHMARK_HINTS) or ("benchmark" in text and not bool_hint(text, MECHANISM_HINTS | LIMITATION_HINTS)),
    }
    roles = roles_for_candidate(row, lane)
    score = 0
    for term in sorted(HIGH_SIGNAL):
        if term in text:
            score += 1
            reasons.append(f"matches:{term}")
    if any(term in text for term in BASELINE_HINTS):
        score += 2
        reasons.append("baseline_or_named_method_pressure")
    if any(term in text for term in BENCHMARK_HINTS):
        score += 1
        reasons.append("dataset_or_benchmark_anchor")
    ids = identifiers(row)
    if ids.get("doi") or ids.get("arxiv") or ids.get("arxivId"):
        score += 1
        reasons.append("strong_identifier")
    if flags["source_resolvable"]:
        score += 1
        reasons.append("source_resolvable")
    if lane == "target_domain":
        score += 1
        reasons.append("target_domain_lane")
    if lane == "near_neighbor":
        score += 1
        reasons.append("near_neighbor_lane")
    if lane == "far_neighbor":
        score += 1
        reasons.append("far_neighbor_lane")
    if "mechanism" in roles:
        score += 2
        reasons.append("mechanism_extractable")
    if "limitation_future" in roles:
        score += 1
        reasons.append("limitation_or_future_extractable")
    if "negative_evidence" in roles:
        score += 1
        reasons.append("negative_evidence_potential")
    if "transfer_bridge" in roles:
        score += 2
        reasons.append("transfer_bridge_potential")
    if flags["survey_noise"]:
        score -= 2
        reasons.append("survey_noise_risk")
    if flags["generic_benchmark_risk"]:
        score -= 1
        reasons.append("generic_benchmark_risk")
    if duplicate:
        score -= 4
        reasons.append("duplicate_group")
    return score, reasons, roles, flags


def decision(score: int, roles: list[str], flags: dict[str, bool]) -> str:
    if flags.get("duplicate"):
        return "reject_duplicate"
    if not flags.get("source_resolvable"):
        return "reject_unresolved_source"
    if flags.get("survey_noise") and not ({"mechanism", "limitation_future", "negative_evidence"} & set(roles)):
        return "reject_survey_noise"
    if flags.get("generic_benchmark_risk") and "mechanism" not in roles and "negative_evidence" not in roles and not flags.get("substantive_limitation"):
        return "reject_generic_benchmark"
    if score >= 7 and roles:
        return "graph_import"
    if score >= 5 and roles:
        return "split_read_only"
    if score >= 2:
        return "watchlist"
    return "reject_weak_relevance"


def legacy_decision(decision_value: str, score: int) -> str:
    if decision_value in {"graph_import", "split_read_only"}:
        return "import_recommended"
    if decision_value == "watchlist" or score >= 2:
        return "watchlist"
    return "reject_irrelevant"


def enforce_selection_ratio(rows: list[dict[str, Any]]) -> None:
    eligible = [row for row in rows if row.get("eligible")]
    selected = [row for row in rows if row.get("graph_or_material_selected")]
    if not eligible:
        return
    max_selected = max(1, int(len(eligible) * 0.8))
    if len(selected) <= max_selected:
        return

    selected_by_lane: dict[str, int] = {}
    for row in selected:
        lane = str(row.get("lane") or "")
        selected_by_lane[lane] = selected_by_lane.get(lane, 0) + 1

    for row in sorted(selected, key=lambda item: (int(item.get("score") or 0), str(item.get("title") or ""))):
        if len([item for item in rows if item.get("graph_or_material_selected")]) <= max_selected:
            return
        lane = str(row.get("lane") or "")
        if selected_by_lane.get(lane, 0) <= 1:
            continue
        selected_by_lane[lane] -= 1
        row["decision"] = "watchlist"
        row["legacy_decision"] = "watchlist"
        row["graph_or_material_selected"] = False
        row["recommended_next_step"] = "keep as metadata-only prior pressure unless a later selected idea needs this niche"
        reasons = row.get("reasons") if isinstance(row.get("reasons"), list) else []
        row["reasons"] = [*reasons, "deferred_to_watchlist_to_keep_graph_material_selection_ratio"]


def recompute_stats(rows: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int], dict[str, dict[str, int]], int, int, float | None]:
    counts: dict[str, int] = {}
    legacy_counts = {"import_recommended": 0, "watchlist": 0, "reject_irrelevant": 0}
    lane_counts: dict[str, dict[str, int]] = {lane: {"raw": 0, "eligible": 0, "graph_or_material": 0} for lane in sorted(LANES)}
    for row in rows:
        dec = str(row.get("decision") or "")
        legacy = str(row.get("legacy_decision") or legacy_decision(dec, int(row.get("score") or 0)))
        counts[dec] = counts.get(dec, 0) + 1
        legacy_counts[legacy] = legacy_counts.get(legacy, 0) + 1
        lane = str(row.get("lane") or "")
        if lane in lane_counts:
            lane_counts[lane]["raw"] += 1
            if row.get("eligible"):
                lane_counts[lane]["eligible"] += 1
            if row.get("graph_or_material_selected"):
                lane_counts[lane]["graph_or_material"] += 1
    eligible_count = sum(1 for row in rows if row.get("eligible"))
    graph_or_material_count = sum(1 for row in rows if row.get("graph_or_material_selected"))
    ratio = graph_or_material_count / eligible_count if eligible_count else None
    return counts, legacy_counts, lane_counts, eligible_count, graph_or_material_count, ratio


def summarize(payload: Any, project: str, stage: str, source_path: str) -> dict[str, Any]:
    candidates = collect_candidates(payload)
    rows = []
    seen: set[str] = set()
    default_lane = "target_domain" if stage == "ideation" else "target_domain"
    for row in candidates:
        lane = lane_of(row, str(row.get("lane") or default_lane))
        key = dedupe_key(row)
        duplicate = bool(key and key in seen)
        if key:
            seen.add(key)
        score, reasons, roles, flags = score_candidate(row, lane, duplicate)
        dec = decision(score, roles, flags)
        legacy = legacy_decision(dec, score)
        rows.append(
            {
                "decision": dec,
                "legacy_decision": legacy,
                "score": score,
                "lane": lane,
                "eligible": dec in {"graph_import", "split_read_only", "watchlist"},
                "graph_or_material_selected": dec in {"graph_import", "split_read_only"},
                "title": title(row),
                "year": year(row),
                "venue": venue(row),
                "identifiers": identifiers(row),
                "dedupe_key": key,
                "roles": roles,
                "flags": flags,
                "reasons": reasons[:10],
                "recommended_next_step": (
                    "queue PaperNexus import or material/split-reading before idea generation"
                    if dec == "graph_import"
                    else "request PaperNexus split-reading material without forcing graph import"
                    if dec == "split_read_only"
                    else "keep as metadata-only prior pressure"
                    if dec == "watchlist"
                    else "reject from pre-idea graph/material set unless a later selected idea needs this niche"
                ),
            }
        )
    rows.sort(key=lambda item: (-int(item["score"]), item["title"]))
    enforce_selection_ratio(rows)
    counts, legacy_counts, lane_counts, eligible_count, graph_or_material_count, ratio = recompute_stats(rows)
    ratio_exception = None
    if ratio is None:
        ratio_exception = "no_high_signal_eligible_candidates"
    elif ratio < 0.6 or ratio > 0.8:
        ratio_exception = "outside_target_0.60_to_0.80_requires_manual_or_expansion_review"
    return {
        "schema_version": 1,
        "created_at": now(),
        "stage": stage,
        "source": source_path,
        "discovery_attempted": True,
        "status": "complete",
        "screening_completed": True,
        "policy": {
            "metadata_only": True,
            "import_resolved": False,
            "process_imports": False,
            "allow_downloads": False,
            "purpose": "pre-idea active screening; decide what to import or split-read before idea generation",
            "selection_denominator": "high_signal_eligible_set",
        },
        "candidate_count": len(candidates),
        "decision_counts": counts,
        "legacy_decision_counts": legacy_counts,
        "lane_counts": lane_counts,
        "eligible_candidate_count": eligible_count,
        "graph_or_material_selected_count": graph_or_material_count,
        "eligible_graph_or_material_ratio": ratio,
        "ratio_exception_reason": ratio_exception,
        "search_expansion_recommended": bool(
            ratio_exception
            or any(values["raw"] == 0 or values["eligible"] == 0 for values in lane_counts.values())
        ),
        "candidates": rows,
    }


def paper_ref(row: dict[str, Any]) -> str:
    ids = row.get("identifiers") if isinstance(row.get("identifiers"), dict) else {}
    for key in ["doi", "arxiv", "arxivId", "pmid", "pmcid", "canonicalId", "url", "pdfUrl", "openAccessPdf"]:
        value = ids.get(key)
        if value:
            return f"{key}:{str(value).strip()}"
    title_value = str(row.get("title") or "").strip()
    return f"title:{norm_title(title_value)}" if title_value else str(row.get("dedupe_key") or "").strip()


def import_action(row: dict[str, Any]) -> str:
    decision_value = str(row.get("decision") or "").strip()
    if decision_value == "graph_import":
        return "import"
    if decision_value == "split_read_only":
        return "material_view"
    return "skip_existing"


def graph_import_plan(triage: dict[str, Any]) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    role_balance: dict[str, int] = {}
    lane_balance: dict[str, int] = {}
    idempotency_keys: list[str] = []

    for index, row in enumerate(triage.get("candidates") or []):
        if not isinstance(row, dict):
            continue
        decision_value = str(row.get("decision") or "").strip()
        lane = str(row.get("lane") or "target_domain").strip()
        roles = [str(role) for role in (row.get("roles") or [])]
        flags = row.get("flags") if isinstance(row.get("flags"), dict) else {}
        ref = paper_ref(row)
        idempotency_key = str(row.get("dedupe_key") or ref or f"candidate:{index}").strip()
        if decision_value in {"graph_import", "split_read_only"}:
            selected.append(
                {
                    "paper_ref": ref,
                    "title": row.get("title"),
                    "year": row.get("year"),
                    "venue": row.get("venue"),
                    "lane": lane,
                    "roles": roles,
                    "selection_reason": "; ".join(str(item) for item in (row.get("reasons") or [])[:6]),
                    "source_resolution_status": "resolved" if flags.get("source_resolvable") else "unresolved",
                    "import_action": import_action(row),
                    "idempotency_key": idempotency_key,
                }
            )
            lane_balance[lane] = lane_balance.get(lane, 0) + 1
            for role in roles:
                role_balance[role] = role_balance.get(role, 0) + 1
            idempotency_keys.append(idempotency_key)
        elif decision_value.startswith("reject_") or flags.get("source_resolvable") is False:
            blocked.append(
                {
                    "paper_ref": ref,
                    "title": row.get("title"),
                    "lane": lane,
                    "decision": decision_value,
                    "reason": "; ".join(str(item) for item in (row.get("reasons") or [])[:4]),
                }
            )

    import_batch = [
        paper
        for paper in selected
        if paper.get("import_action") in {"import", "supplement", "skip_existing"}
    ]
    material_requests = [
        {
            "paper_ref": paper.get("paper_ref"),
            "roles": paper.get("roles"),
            "lane": paper.get("lane"),
            "request": "PaperNexus material view / split-reading evidence extraction",
        }
        for paper in selected
    ]
    split_reading_requests = [
        request
        for request in material_requests
        if set(request.get("roles") or [])
        & {"closest_prior", "baseline_protocol", "dataset_metric", "mechanism", "limitation_future", "negative_evidence", "transfer_bridge"}
    ]
    return {
        "schema_version": 1,
        "created_at": now(),
        "source": triage.get("source"),
        "stage": triage.get("stage"),
        "status": "planned" if selected else "blocked_no_selected_papers",
        "policy": {
            "raw_discovery_results_are_not_imported_directly": True,
            "selection_source": "papernexus/PAPER_SELECTION_SCORECARD.json",
            "next_step": "execute PaperNexus import/supplement/material-view calls for selected_papers, then capture GRAPH_IMPORT_STATUS.json and SPLIT_READING_EVIDENCE_PACK.json",
        },
        "selected_papers": selected,
        "lane_balance": lane_balance,
        "role_balance": role_balance,
        "import_batches": [import_batch] if import_batch else [],
        "material_requests": material_requests,
        "split_reading_requests": split_reading_requests,
        "blocked_papers": blocked,
        "idempotency_keys": idempotency_keys,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", default="literature/LITERATURE_DISCOVERY_PACKET.json")
    parser.add_argument("--output", default="papernexus/LITERATURE_DISCOVERY_TRIAGE.json")
    parser.add_argument("--scorecard-output", default="papernexus/PAPER_SELECTION_SCORECARD.json")
    parser.add_argument("--graph-plan-output", default="papernexus/GRAPH_IMPORT_PLAN.json")
    parser.add_argument("--stage", default="ideation")
    args = parser.parse_args()

    base = ar(args.project)
    input_path = resolve(base, args.input)
    payload = read_json(input_path)
    if payload is None:
        raise SystemExit(f"missing or invalid discovery packet: {input_path}")
    out = summarize(payload, args.project, args.stage, str(input_path))
    output_path = resolve(base, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    scorecard_path = resolve(base, args.scorecard_output) if args.scorecard_output else None
    if scorecard_path is not None:
        scorecard_path.parent.mkdir(parents=True, exist_ok=True)
        scorecard_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    graph_plan_path = resolve(base, args.graph_plan_output) if args.graph_plan_output else None
    if graph_plan_path is not None:
        graph_plan_path.parent.mkdir(parents=True, exist_ok=True)
        graph_plan_path.write_text(json.dumps(graph_import_plan(out), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "path": str(output_path),
                "scorecard_path": str(scorecard_path) if scorecard_path else None,
                "graph_plan_path": str(graph_plan_path) if graph_plan_path else None,
                "candidate_count": out["candidate_count"],
                "decision_counts": out["decision_counts"],
                "eligible_graph_or_material_ratio": out["eligible_graph_or_material_ratio"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
