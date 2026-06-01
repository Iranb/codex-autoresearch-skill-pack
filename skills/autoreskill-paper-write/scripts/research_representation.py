#!/usr/bin/env python3
"""Build a claim-evidence tagged research representation before prose."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def extract_claim_lines(text: str, limit: int = 24) -> list[str]:
    claims: list[str] = []
    for line in text.splitlines():
        stripped = line.strip(" -*\t")
        if len(stripped) < 20:
            continue
        if any(word in stripped.lower() for word in ["claim", "evidence", "improve", "outperform", "method", "baseline", "limitation", "prior", "result"]):
            claims.append(stripped)
        if len(claims) >= limit:
            break
    return claims


def citation_keys(citation_queue: Any) -> list[str]:
    rows: list[Any] = []
    if isinstance(citation_queue, dict):
        for key in ["citations", "references", "papers", "items"]:
            if isinstance(citation_queue.get(key), list):
                rows = citation_queue[key]
                break
    elif isinstance(citation_queue, list):
        rows = citation_queue
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            key = row.get("key") or row.get("citation_key") or row.get("id") or row.get("paper_id")
            if present(key):
                out.append(str(key))
    return out


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    claim_matrix = read_text(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md")
    track_verdicts = read_text(base / "analyzer/TRACK_VERDICTS.md")
    story = read_text(base / "user_view/innovation_story/00_STORYLINE_DESIGN.md")
    method_story = read_text(base / "user_view/innovation_story/01_METHOD_INNOVATION_STORY.md")
    claim_map = read_text(base / "user_view/innovation_story/02_CLAIM_EVIDENCE_MAP.md")
    best = read_json(base / "analyzer/BEST_RUN_SELECTION.json", {})
    score = read_json(base / "analyzer/SCORE_VERIFICATION.json", {})
    citations = citation_keys(read_json(base / "literature/CITATION_QUEUE.json", {}))
    review = read_json(base / "reviewer/REVIEW_FINDINGS.json", {})
    selected_run = best.get("selected_run_id") if isinstance(best, dict) else None
    score_passed = isinstance(score, dict) and score.get("status") == "passed"
    lines = extract_claim_lines("\n".join([claim_matrix, claim_map, track_verdicts, story, method_story]))
    if not lines and selected_run:
        lines = [f"The selected promoted run is {selected_run} under the locked protocol."]
    claims: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for index, text in enumerate(lines):
        lowered = text.lower()
        claim_type = "method"
        if any(word in lowered for word in ["improve", "outperform", "%", "score", "metric", "result"]):
            claim_type = "performance"
        elif any(word in lowered for word in ["prior", "related", "cite", "paper"]):
            claim_type = "related_work"
        elif "limitation" in lowered or "fail" in lowered:
            claim_type = "limitation"
        strength = "moderate"
        evidence: dict[str, Any] = {}
        if claim_type == "performance":
            if selected_run and score_passed:
                strength = "strong"
                evidence["best_run_ref"] = "analyzer/BEST_RUN_SELECTION.json"
                evidence["score_verification_ref"] = "analyzer/SCORE_VERIFICATION.json"
            else:
                strength = "pilot"
                evidence["unsupported_marker"] = "no promoted score verification"
        elif claim_type == "related_work":
            if citations:
                evidence["citation_queue_ref"] = citations[:3]
            else:
                strength = "unsupported"
                evidence["unsupported_marker"] = "missing citation queue entries"
        elif claim_type == "method":
            evidence["review_finding_ref"] = "reviewer/REVIEW_FINDINGS.json" if review else None
            evidence["papernexus_evidence_id"] = "method_story"
        else:
            evidence["review_finding_ref"] = "reviewer/REVIEW_FINDINGS.json" if review else None
        claim = {
            "claim_id": f"C{index + 1:03d}",
            "text": text,
            "claim_type": claim_type,
            "claim_strength": strength,
            "evidence": {key: value for key, value in evidence.items() if present(value)},
        }
        if strength == "unsupported" or "unsupported_marker" in evidence:
            blocked.append(claim)
        else:
            claims.append(claim)
    return {
        "schema_version": 1,
        "generated_at": now(),
        "paper_thesis": (extract_claim_lines(story, 1) or ["Evidence-bound paper thesis pending story refinement."])[0],
        "reader_belief_shift": "Derived from innovation story; revise if this remains generic.",
        "gap_claims": [claim for claim in claims if claim["claim_type"] == "related_work"],
        "method_claims": [claim for claim in claims if claim["claim_type"] == "method"],
        "performance_claims": [claim for claim in claims if claim["claim_type"] == "performance"],
        "ablation_claims": [],
        "limitation_claims": [claim for claim in claims if claim["claim_type"] == "limitation"],
        "related_work_claims": [claim for claim in claims if claim["claim_type"] == "related_work"],
        "claim_evidence_tags": claims,
        "source_artifacts": [
            rel
            for rel in [
                "analyzer/CLAIM_EVIDENCE_MATRIX.md",
                "analyzer/TRACK_VERDICTS.md",
                "analyzer/BEST_RUN_SELECTION.json",
                "analyzer/SCORE_VERIFICATION.json",
                "literature/CITATION_QUEUE.json",
                "reviewer/REVIEW_FINDINGS.json",
                "user_view/innovation_story/00_STORYLINE_DESIGN.md",
                "user_view/innovation_story/01_METHOD_INNOVATION_STORY.md",
                "user_view/innovation_story/02_CLAIM_EVIDENCE_MAP.md",
            ]
            if (base / rel).exists()
        ],
        "blocked_claims": blocked,
        "required_repairs": ["repair or downgrade blocked_claims before composing prose"] if blocked else [],
    }


def to_markdown(payload: dict[str, Any]) -> str:
    lines = ["# RESEARCH_REPRESENTATION", "", f"Thesis: {payload.get('paper_thesis')}", ""]
    lines.extend(["## Claim Evidence Tags", ""])
    for claim in payload.get("claim_evidence_tags", []):
        evidence = ", ".join(f"{key}={value}" for key, value in (claim.get("evidence") or {}).items()) or "unsupported"
        lines.append(f"- `{claim.get('claim_id')}` [{claim.get('claim_type')}/{claim.get('claim_strength')}] {claim.get('text')} :: {evidence}")
    lines.append("")
    if payload.get("blocked_claims"):
        lines.extend(["## Blocked Claims", ""])
        for claim in payload["blocked_claims"]:
            lines.append(f"- `{claim.get('claim_id')}` {claim.get('text')}")
        lines.append("")
    return "\n".join(lines)


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    payload = read_json(base / "paper/RESEARCH_REPRESENTATION.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"complete": False, "status": "incomplete", "missing": ["paper/RESEARCH_REPRESENTATION.json"], "warnings": []}
    claims = payload.get("claim_evidence_tags")
    if not isinstance(claims, list) or not claims:
        missing.append("claim_evidence_tags")
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        evidence = claim.get("evidence") if isinstance(claim.get("evidence"), dict) else {}
        if claim.get("claim_strength") == "strong" and not evidence:
            missing.append(f"{claim.get('claim_id')}.evidence for strong claim")
        if claim.get("claim_type") == "performance" and claim.get("claim_strength") == "strong":
            if not evidence.get("best_run_ref") or not evidence.get("score_verification_ref"):
                missing.append(f"{claim.get('claim_id')}.promoted performance evidence")
        if claim.get("claim_strength") == "unsupported":
            warnings.append(f"{claim.get('claim_id')} remains unsupported")
    if not (base / "paper/RESEARCH_REPRESENTATION.md").exists():
        missing.append("paper/RESEARCH_REPRESENTATION.md")
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
    base = ar(args.project)
    write_json(base / "paper/RESEARCH_REPRESENTATION.json", payload)
    write_text(base / "paper/RESEARCH_REPRESENTATION.md", to_markdown(payload))
    out = check(args.project)
    print(json.dumps({"ok": out["complete"], **out}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
