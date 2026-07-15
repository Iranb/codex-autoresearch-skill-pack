#!/usr/bin/env python3
"""Classify blockers and append blocker ledger rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def base(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def allowed_external_wait_text(text: str) -> bool:
    wait_markers = ["wait", "waiting", "pending", "queued", "running", "in_progress", "async", "external"]
    has_wait_marker = any(marker in text for marker in wait_markers)
    if not has_wait_marker:
        return False
    if "papernexus" in text and "literature" in text and "discovery" in text:
        return True
    if "literature_discovery" in text and any(marker in text for marker in ["run", "progress", "report", "poll"]):
        return True
    if any(marker in text for marker in ["import_workflow", "graph import", "graph_import", "authoritative sync", "authoritative_sync", "graph sync"]):
        return True
    if "experiment" in text and any(marker in text for marker in ["runtime", "remote", "resource", "gpu", "slurm", "training"]):
        return True
    return False


def classify_typed(reason: str, failure_class: str = "") -> tuple[str, str, str]:
    typed = failure_class.strip().lower()
    if typed == "infrastructure_failure":
        return "auto_repairable", "repair_or_reconcile_infrastructure", "operational"
    if typed == "implementation_failure":
        return "auto_repairable", "refine_implementation", "operational"
    if typed == "protocol_invalid":
        return "auto_repairable", "repair_protocol", "operational"
    if typed == "budget_stopped_no_scientific_conclusion":
        return "hard_stop", "conclude_or_request_resource_decision", "none"
    if typed in {
        "valid_positive_candidate",
        "valid_negative",
        "valid_inconclusive",
        "cross_dataset_contradiction",
        "duplicate_or_non_discriminating",
    }:
        return "scientific_transition", "apply_research_decision", "scientific_revision"
    text = reason.lower()
    if allowed_external_wait_text(text):
        return "async_wait", "schedule_async_poll", "none"
    if any(k in text for k in ["controller_unavailable", "single_seed", "cost_evidence", "provider", "sparse", "stale"]):
        return "degradable", "advance_with_downgrade_or_fallback", "none"
    if any(k in text for k in ["budget", "license", "unsafe", "no_viable", "papernexus_unavailable_without_cached"]):
        return "hard_stop", "rollback_or_negative_result_route", "none"
    return "auto_repairable", "schedule_repair", "operational"


def classify(reason: str) -> tuple[str, str]:
    """Preserve the legacy two-value API for existing callers."""
    klass, action, _ = classify_typed(reason)
    return klass, action


def failure_signature(failure_class: str, reason: str, artifact: str | None) -> str:
    normalized_reason = re.sub(r"\s+", " ", reason.strip().lower())
    payload = f"{failure_class.strip().lower()}|{artifact or ''}|{normalized_reason}"
    return "failure-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--artifact")
    parser.add_argument("--failure-class", default="")
    parser.add_argument("--failure-signature")
    parser.add_argument("--repair-kind", choices=["operational", "scientific_revision", "none"])
    parser.add_argument("--operational-attempt", type=int, default=0)
    parser.add_argument("--scientific-revision", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    klass, action, inferred_repair_kind = classify_typed(args.reason, args.failure_class)
    repair_kind = args.repair_kind or inferred_repair_kind
    row = {
        "schema_version": 2,
        "ts": now(),
        "stage": args.stage,
        "reason": args.reason,
        "artifact": args.artifact,
        "failure_class": args.failure_class or "untyped_legacy_blocker",
        "failure_signature": args.failure_signature or failure_signature(args.failure_class, args.reason, args.artifact),
        "repair_kind": repair_kind,
        "operational_attempt": args.operational_attempt,
        "scientific_revision": args.scientific_revision,
        "class": klass,
        "recommended_action": action,
        "status": "triaged",
    }
    if not args.dry_run:
        append_jsonl(base(args.project) / "blocker_ledger.jsonl", row)
    print(json.dumps(row, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
