#!/usr/bin/env python3
"""Lint the ideation-stage experiment idea pool before implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


AUDIT_KEYS = [
    "metric_drift",
    "eval_drift",
    "dataset_drift",
    "data_leakage",
    "prediction_cheating",
    "training_budget_drift",
]
VALID_TYPES = {"ALGO", "CODE", "PARAM"}
BAD_AUDIT_STRINGS = {"true", "yes", "fail", "failed", "violation", "drift", "cheat", "leak"}


def project_root(project: str) -> Path:
    return Path(project).expanduser().resolve()


def resolve_artifact(project: str, raw: str) -> Path:
    root = project_root(project)
    base = root / ".autoreskill"
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if raw.startswith(".autoreskill/"):
        return root / raw
    return base / path


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


def audit_violation(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in BAD_AUDIT_STRINGS:
        return True
    return False


def ideas_from_pool(pool: dict[str, Any], warnings: list[str]) -> list[Any]:
    ideas = pool.get("ideas")
    if isinstance(ideas, list):
        return ideas
    legacy = pool.get("candidates")
    if isinstance(legacy, list):
        warnings.append("legacy field `candidates` found; use `ideas` because the 12-15 items are optimization ideas")
        return legacy
    return []


def idea_source_backed(idea: dict[str, Any]) -> bool:
    return any(
        present(idea.get(key))
        for key in ["source_paper_or_technique", "paperNexus_evidence_ids", "derived_from_idea_fragment_ids"]
    )


def lint(pool: Any, require_selected: bool) -> dict[str, Any]:
    missing: list[str] = []
    warnings: list[str] = []

    if not isinstance(pool, dict):
        return {
            "complete": False,
            "status": "incomplete",
            "missing": ["ideation/EXPERIMENT_IDEA_POOL.json"],
            "warnings": [],
        }

    ideas = ideas_from_pool(pool, warnings)

    count = len(ideas)
    if count < 12 or count > 15:
        missing.append(f"idea count must be 12-15, got {count}")

    ids: set[str] = set()
    duplicate_ids: set[str] = set()
    type_counts = {"ALGO": 0, "CODE": 0, "PARAM": 0}
    selected_ideas: list[str] = []
    source_backed_algo = 0

    for index, idea in enumerate(ideas):
        prefix = f"ideas[{index}]"
        if not isinstance(idea, dict):
            missing.append(f"{prefix} must be an object")
            continue

        idea_id = str(idea.get("id") or "").strip()
        if not idea_id:
            missing.append(f"{prefix}.id")
        elif idea_id in ids:
            duplicate_ids.add(idea_id)
        else:
            ids.add(idea_id)

        itype = str(idea.get("type") or "").upper()
        if itype not in VALID_TYPES:
            missing.append(f"{prefix}.type must be one of ALGO/CODE/PARAM")
        else:
            type_counts[itype] += 1

        for key in ["priority", "risk", "description", "hypothesis", "one_variable_change", "expected_metric_impact", "implementation_scope", "status"]:
            if not present(idea.get(key)):
                missing.append(f"{prefix}.{key}")

        if itype == "ALGO" and idea_source_backed(idea):
            source_backed_algo += 1

        if str(idea.get("status") or "").lower() == "selected" and idea_id:
            selected_ideas.append(idea_id)

        audit = idea.get("red_line_audit")
        if not isinstance(audit, dict):
            missing.append(f"{prefix}.red_line_audit")
        else:
            for key in AUDIT_KEYS:
                if key not in audit:
                    missing.append(f"{prefix}.red_line_audit.{key}")
                elif audit_violation(audit.get(key)):
                    missing.append(f"{prefix}.red_line_audit.{key} indicates a red-line violation")

    if duplicate_ids:
        missing.append("duplicate idea ids: " + ", ".join(sorted(duplicate_ids)))

    if type_counts["PARAM"] > 4:
        missing.append(f"PARAM ideas must be <= 4, got {type_counts['PARAM']}")
    if type_counts["ALGO"] < 6:
        missing.append(f"need at least 6 ALGO ideas, got {type_counts['ALGO']}")
    if type_counts["CODE"] < 6:
        missing.append(f"need at least 6 CODE ideas, got {type_counts['CODE']}")
    if source_backed_algo < 3:
        missing.append(f"need at least 3 ALGO ideas with source paper/technique or PaperNexus evidence, got {source_backed_algo}")

    selected_id = str(pool.get("selected_idea_id") or pool.get("selected_candidate_id") or "").strip()
    if require_selected and not selected_id and not selected_ideas:
        missing.append("selected_idea_id or one idea with status=SELECTED")
    if selected_id and selected_id not in ids:
        missing.append(f"selected_idea_id {selected_id!r} is not in ideas")

    protocol = pool.get("locked_protocol")
    if not isinstance(protocol, dict):
        missing.append("locked_protocol")
    else:
        for key in ["dataset", "primary_metric", "baseline_eval_protocol", "evaluation_command"]:
            if not present(protocol.get(key)):
                missing.append(f"locked_protocol.{key}")
        if not present(protocol.get("metric_direction")):
            warnings.append("locked_protocol.metric_direction missing; default higher may be assumed")
        if not present(protocol.get("protected_paths")):
            warnings.append("protected_paths missing; hash eval/test/metric files when available")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
        "idea_count": count,
        "type_counts": type_counts,
        "source_backed_algo_count": source_backed_algo,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--pool", default="ideation/EXPERIMENT_IDEA_POOL.json")
    parser.add_argument("--require-selected", action="store_true")
    args = parser.parse_args()

    path = resolve_artifact(args.project, args.pool)
    out = lint(read_json(path), args.require_selected)
    out["path"] = str(path)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
