#!/usr/bin/env python3
"""Post-compose claim verifier for numerical, citation, method, and conclusion claims."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUALITATIVE_STRONG = {"robust", "near-optimal", "near optimal", "sota", "state-of-the-art", "consistent", "significant", "general"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


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


def citation_keys(payload: Any) -> set[str]:
    rows: list[Any] = []
    if isinstance(payload, dict):
        for key in ["citations", "references", "papers", "items"]:
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    elif isinstance(payload, list):
        rows = payload
    keys = set()
    for row in rows:
        if isinstance(row, dict):
            key = row.get("key") or row.get("citation_key") or row.get("id") or row.get("paper_id")
            if present(key):
                keys.add(str(key))
    return keys


def tex_citations(tex: str) -> set[str]:
    keys = set()
    for match in re.finditer(r"\\cite\w*\{([^}]+)\}", tex):
        for key in match.group(1).split(","):
            if key.strip():
                keys.add(key.strip())
    return keys


def numeric_claims(tex: str) -> list[str]:
    out = []
    for match in re.finditer(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?\s*(?:%|pp|x|\\%)?", tex):
        token = match.group(0).strip()
        if token and token not in {"1", "2", "3", "4"}:
            out.append(token)
    return out[:80]


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    tex = read_text(base / "paper/main.tex")
    citations = citation_keys(read_json(base / "literature/CITATION_QUEUE.json", {}))
    representation = read_json(base / "paper/RESEARCH_REPRESENTATION.json", {})
    grounded = read_json(base / "paper/GROUNDED_WRITE_PACKAGE.json", {})
    score = read_json(base / "analyzer/SCORE_VERIFICATION.json", {})
    best = read_json(base / "analyzer/BEST_RUN_SELECTION.json", {})
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not tex.strip():
        blocking.append({"kind": "missing_main_tex", "path": "paper/main.tex"})
    for key in sorted(tex_citations(tex) - citations):
        blocking.append({"kind": "citation_not_in_queue", "citation_key": key})
    nums = numeric_claims(tex)
    if nums and score.get("status") != "passed":
        blocking.append({"kind": "numerical_claims_without_score_verification", "numbers": nums[:10]})
    if nums and best.get("final_promotion_status") != "promoted":
        blocking.append({"kind": "numerical_claims_without_promoted_run", "numbers": nums[:10]})
    lowered = tex.lower()
    for phrase in sorted(QUALITATIVE_STRONG):
        if phrase in lowered:
            warnings.append({"kind": "strong_qualitative_term", "term": phrase, "action": "ensure representation evidence supports this wording"})
    if grounded.get("ground_status") != "passed":
        blocking.append({"kind": "grounded_write_package_not_passed"})
    claims = representation.get("claim_evidence_tags") if isinstance(representation, dict) else []
    if not claims:
        warnings.append({"kind": "no_research_representation_claims"})
    status = "passed" if not blocking else "blocked"
    return {
        "schema_version": 1,
        "generated_at": now(),
        "status": status,
        "blocking_failures": blocking,
        "warnings": warnings,
        "checks": {
            "numerical_claim_count": len(nums),
            "citation_claim_count": len(tex_citations(tex)),
            "ground_status": grounded.get("ground_status"),
            "score_verification_status": score.get("status"),
            "best_run_status": best.get("final_promotion_status"),
        },
    }


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    payload = read_json(base / "paper/PAPER_CLAIM_VERIFICATION.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        missing.append("paper/PAPER_CLAIM_VERIFICATION.json")
    elif payload.get("status") != "passed":
        missing.append("paper/PAPER_CLAIM_VERIFICATION.json status=passed")
    if isinstance(payload, dict) and payload.get("warnings"):
        warnings.append("paper claim verifier has non-blocking warnings")
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
    write_json(ar(args.project) / "paper/PAPER_CLAIM_VERIFICATION.json", payload)
    out = check(args.project)
    print(json.dumps({"ok": out["complete"], **out}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
