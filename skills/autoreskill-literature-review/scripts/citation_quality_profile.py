#!/usr/bin/env python3
"""Build or check an LQS-style citation quality profile."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MUST_CITE_THRESHOLD = 7.0
CONDITIONAL_THRESHOLD = 5.0


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


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d{4}|\d+", value)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return None
    return None


def entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["entries", "citations", "references", "papers", "items"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def first(row: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if present(row.get(key)):
            return row.get(key)
    return default


def year_score(year: int | None, current_year: int) -> float:
    if year is None:
        return 3.0
    age = max(0, current_year - year)
    if age <= 0:
        return 10.0
    if age == 1:
        return 8.0
    if age == 2:
        return 5.0
    if age == 3:
        return 3.0
    return 2.0


def citation_impact_score(row: dict[str, Any], year: int | None, current_year: int) -> float:
    explicit = first(row, ["citations_per_month", "citation_rate", "cites_per_month"])
    if explicit is not None:
        try:
            rate = float(explicit)
        except (TypeError, ValueError):
            rate = 0.0
    else:
        count = first(row, ["citation_count", "citations", "num_citations", "cited_by_count"], 0)
        try:
            citation_count = float(count)
        except (TypeError, ValueError):
            citation_count = 0.0
        months = max(1, (current_year - year + 1) * 12) if year else 36
        rate = citation_count / months
    if rate >= 50:
        return 10.0
    if rate >= 10:
        return 8.0
    if rate >= 3:
        return 6.0
    if rate >= 1:
        return 4.0
    return 2.0


def venue_score(row: dict[str, Any]) -> float:
    text = " ".join(str(first(row, keys, "")) for keys in [["venue_tier"], ["venue"], ["journal"], ["conference"], ["source"]]).lower()
    if any(token in text for token in ["nature", "science", "cell", "neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "acl", "emnlp", "siggraph", "kdd", "sigmod", "vldb"]):
        return 10.0
    if any(token in text for token in ["accepted", "journal", "transactions", "aaai", "ijcai", "workshop oral"]):
        return 7.0
    if "workshop" in text:
        return 4.0
    if "arxiv" in text or "preprint" in text:
        return 3.0
    return 5.0 if text.strip() else 3.0


def institution_score(row: dict[str, Any]) -> float:
    text = " ".join(str(first(row, keys, "")) for keys in [["institution"], ["affiliation"], ["affiliations"], ["authors"]]).lower()
    if any(token in text for token in ["google", "deepmind", "openai", "meta", "microsoft", "stanford", "mit", "berkeley", "cmu", "oxford", "cambridge", "tsinghua", "pku"]):
        return 9.0
    return 5.0 if text.strip() else 3.0


def acceptance_score(row: dict[str, Any]) -> float:
    status = str(first(row, ["acceptance_status", "status", "publication_status", "venue_status"], "")).lower()
    venue = str(first(row, ["venue", "journal", "conference"], "")).lower()
    if any(token in status for token in ["accepted", "published", "inproceedings"]) or (venue and "arxiv" not in venue and "preprint" not in venue):
        return 10.0
    if any(token in status for token in ["under review", "submitted", "revision"]):
        return 5.0
    return 3.0


def citation_depth(score: float, row: dict[str, Any]) -> str:
    explicit = str(first(row, ["citation_depth", "depth", "tier"], "")).strip().upper()
    if explicit in {"A", "B", "C", "D"}:
        return explicit
    role = str(first(row, ["role", "citation_role", "evidence_role"], "")).lower()
    if score >= MUST_CITE_THRESHOLD and any(token in role for token in ["closest", "baseline", "protagonist", "mechanism", "sota"]):
        return "A"
    if score >= MUST_CITE_THRESHOLD:
        return "B"
    if score >= CONDITIONAL_THRESHOLD:
        return "C"
    return "D"


def stable_key(row: dict[str, Any], index: int) -> str:
    for key in ["citation_key", "key", "paper_id", "id", "doi", "arxiv_id", "arxivId", "pmid", "pmcid"]:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    title = row.get("title")
    if isinstance(title, str) and title.strip():
        return re.sub(r"\W+", "_", title.strip().lower())[:80]
    return f"citation_{index:03d}"


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    queue = read_json(base / "literature/CITATION_QUEUE.json", {})
    rows = entries(queue)
    current_year = datetime.now(timezone.utc).year
    scored: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, row in enumerate(rows, start=1):
        year = as_int(first(row, ["year", "publication_year", "published_year", "date", "published_at"]))
        dimensions = {
            "recency": year_score(year, current_year),
            "citation_impact": citation_impact_score(row, year, current_year),
            "venue": venue_score(row),
            "institution": institution_score(row),
            "acceptance": acceptance_score(row),
        }
        score = round(
            dimensions["recency"] * 0.30
            + dimensions["citation_impact"] * 0.25
            + dimensions["venue"] * 0.20
            + dimensions["institution"] * 0.10
            + dimensions["acceptance"] * 0.15,
            2,
        )
        if score >= MUST_CITE_THRESHOLD:
            recommendation = "must_cite"
        elif score >= CONDITIONAL_THRESHOLD:
            recommendation = "conditional"
        else:
            recommendation = "drop_or_watchlist"
        if not present(first(row, ["title", "doi", "paper_id", "id", "arxiv_id", "arxivId"])):
            warnings.append(f"{stable_key(row, index)} lacks title/doi/paper id")
        scored.append(
            {
                "citation_id": stable_key(row, index),
                "title": first(row, ["title"], ""),
                "year": year,
                "lqs": score,
                "dimensions": dimensions,
                "depth_tier": citation_depth(score, row),
                "recommendation": recommendation,
                "evidence_role": first(row, ["role", "citation_role", "evidence_role"], ""),
                "accepted_or_published": dimensions["acceptance"] >= 10,
                "arxiv_only": "arxiv" in str(first(row, ["venue", "source", "publication_status"], "")).lower()
                and dimensions["acceptance"] < 10,
            }
        )
    total = len(scored)
    within_one_year = sum(1 for row in scored if isinstance(row.get("year"), int) and current_year - int(row["year"]) <= 1)
    accepted = sum(1 for row in scored if row["accepted_or_published"])
    arxiv_only = sum(1 for row in scored if row["arxiv_only"])
    depth_counts = {tier: sum(1 for row in scored if row["depth_tier"] == tier) for tier in ["A", "B", "C", "D"]}
    summary = {
        "total_citations": total,
        "must_cite_count": sum(1 for row in scored if row["recommendation"] == "must_cite"),
        "conditional_count": sum(1 for row in scored if row["recommendation"] == "conditional"),
        "drop_or_watchlist_count": sum(1 for row in scored if row["recommendation"] == "drop_or_watchlist"),
        "within_one_year_ratio": round(within_one_year / total, 3) if total else 0.0,
        "accepted_ratio": round(accepted / total, 3) if total else 0.0,
        "arxiv_only_ratio": round(arxiv_only / total, 3) if total else 0.0,
        "depth_counts": depth_counts,
    }
    if total and summary["within_one_year_ratio"] < 0.40:
        warnings.append("within-one-year citation ratio below survey target 0.40")
    if total and summary["accepted_ratio"] < 0.30:
        warnings.append("accepted/published citation ratio below survey target 0.30")
    if total and summary["arxiv_only_ratio"] > 0.60:
        warnings.append("arXiv-only citation ratio above survey target 0.60")
    return {
        "schema_version": 1,
        "generated_at": now(),
        "source": "literature/CITATION_QUEUE.json",
        "status": "complete" if total else "incomplete",
        "grounding": "quality dashboard only; does not replace PaperNexus evidence closure or citation integrity lint",
        "summary": summary,
        "citations": scored,
        "warnings": warnings,
    }


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    profile = read_json(base / "literature/CITATION_QUALITY_PROFILE.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(profile, dict) or not profile:
        missing.append("literature/CITATION_QUALITY_PROFILE.json")
    else:
        if profile.get("schema_version") != 1:
            missing.append("schema_version=1")
        if not isinstance(profile.get("summary"), dict):
            missing.append("summary")
        if not isinstance(profile.get("citations"), list):
            missing.append("citations[]")
        warnings.extend(str(item) for item in profile.get("warnings", []) if isinstance(item, str))
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
    write_json(ar(args.project) / "literature/CITATION_QUALITY_PROFILE.json", payload)
    out = check(args.project)
    print(json.dumps({"ok": out["complete"], **out}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
