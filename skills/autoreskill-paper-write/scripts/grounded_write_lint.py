#!/usr/bin/env python3
"""Ground-Critic-Resolve gate before composing paper prose."""

from __future__ import annotations

import argparse
import json
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


def open_high_review_findings(review: Any) -> list[dict[str, Any]]:
    if not isinstance(review, dict):
        return []
    rows: list[Any] = []
    for key in ["issues", "findings", "review_findings", "items"]:
        if isinstance(review.get(key), list):
            rows = review[key]
            break
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        severity = str(row.get("severity") or row.get("priority") or "").lower()
        status = str(row.get("status") or row.get("state") or "open").lower()
        if severity in {"critical", "high"} and status not in {"closed", "resolved", "waived", "accepted_risk", "fixed"}:
            out.append(row)
    return out


def build(project: str) -> tuple[dict[str, Any], str]:
    base = ar(project)
    representation = read_json(base / "paper/RESEARCH_REPRESENTATION.json", {})
    best = read_json(base / "analyzer/BEST_RUN_SELECTION.json", {})
    score = read_json(base / "analyzer/SCORE_VERIFICATION.json", {})
    review = read_json(base / "reviewer/REVIEW_FINDINGS.json", {})
    claims = representation.get("claim_evidence_tags") if isinstance(representation, dict) else []
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(representation, dict):
        blocking.append({"kind": "missing_artifact", "message": "paper/RESEARCH_REPRESENTATION.json"})
        claims = []
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        evidence = claim.get("evidence") if isinstance(claim.get("evidence"), dict) else {}
        if claim.get("claim_strength") in {"strong", "moderate"} and not evidence:
            blocking.append({"kind": "ungrounded_claim", "claim_id": claim.get("claim_id"), "message": "claim has no evidence tag"})
        if claim.get("claim_type") == "performance" and claim.get("claim_strength") == "strong":
            if best.get("final_promotion_status") != "promoted" or score.get("status") != "passed":
                blocking.append({"kind": "performance_without_promoted_evidence", "claim_id": claim.get("claim_id")})
        if claim.get("claim_strength") == "pilot":
            warnings.append({"kind": "pilot_claim", "claim_id": claim.get("claim_id"), "action": "soften or move out of main result"})
    for item in open_high_review_findings(review):
        blocking.append({"kind": "open_high_review_finding", "finding": item})
    ground_status = "passed" if not blocking else "blocked"
    package = {
        "schema_version": 1,
        "generated_at": now(),
        "ground_status": ground_status,
        "critic_status": "passed" if not blocking else "blocking_findings",
        "resolve_actions": [
            "delete unsupported claims",
            "downgrade pilot claims",
            "route citation gaps to PaperNexus",
            "route result contradictions to analysis or experiment",
        ],
        "main_claims": [claim for claim in claims if isinstance(claim, dict) and claim.get("claim_strength") not in {"unsupported", "pilot"}],
        "pilot_or_downgraded_claims": [claim for claim in claims if isinstance(claim, dict) and claim.get("claim_strength") in {"pilot", "speculative"}],
        "blocking_findings": blocking,
        "warnings": warnings,
        "source_representation": "paper/RESEARCH_REPRESENTATION.json",
    }
    unsupported_lines = ["# UNSUPPORTED_PAPER_CLAIMS", ""]
    for claim in (representation.get("blocked_claims") if isinstance(representation, dict) else []) or []:
        unsupported_lines.append(f"- `{claim.get('claim_id')}` {claim.get('text')} :: action=remove_or_downgrade")
    for item in blocking:
        unsupported_lines.append(f"- {item.get('kind')}: {item.get('message') or item.get('claim_id') or item.get('finding')}")
    unsupported_lines.append("")
    return package, "\n".join(unsupported_lines)


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    package = read_json(base / "paper/GROUNDED_WRITE_PACKAGE.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(package, dict):
        missing.append("paper/GROUNDED_WRITE_PACKAGE.json")
    elif package.get("ground_status") != "passed":
        missing.append("paper/GROUNDED_WRITE_PACKAGE.json ground_status=passed")
    if not (base / "paper/UNSUPPORTED_PAPER_CLAIMS.md").exists():
        warnings.append("paper/UNSUPPORTED_PAPER_CLAIMS.md")
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
    package, unsupported = build(args.project)
    base = ar(args.project)
    write_json(base / "paper/GROUNDED_WRITE_PACKAGE.json", package)
    write_text(base / "paper/UNSUPPORTED_PAPER_CLAIMS.md", unsupported)
    out = check(args.project)
    print(json.dumps({"ok": out["complete"], **out}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
