#!/usr/bin/env python3
"""Build or check a manuscript writing quality profile."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PATTERNS = {
    "claim_evidence_implication": ["therefore", "shows that", "indicates that", "as a result", "so that"],
    "compare_contrast": ["compared with", "in contrast", "unlike", "whereas", "trade-off", "tradeoff"],
    "concession_rebuttal": ["however", "although", "nevertheless", "despite", "but"],
    "funnel": ["we focus", "this paper", "in this work", "specifically", "we study"],
}


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


def infer_paper_type(base: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    for rel in ["paper/WRITING_QUALITY_PROFILE.json", "paper/RESEARCH_REPRESENTATION.json", "project_brief.json", "goal_state.json"]:
        payload = read_json(base / rel, {})
        if isinstance(payload, dict):
            value = payload.get("paper_type") or payload.get("manuscript_type") or payload.get("target_paper_type")
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
    text = " ".join(
        [
            read_text(base / "paper/main.tex")[:4000],
            read_text(base / "literature/LITERATURE_REVIEW.md")[:4000],
        ]
    ).lower()
    return "survey" if "survey" in text or "taxonomy" in text else "method"


def count_tex_sections(text: str) -> list[str]:
    return re.findall(r"\\(?:section|subsection)\{([^}]+)\}", text)


def pattern_hits(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {name: sum(lowered.count(token) for token in tokens) for name, tokens in PATTERNS.items()}


def list_files(base: Path, rel: str, suffixes: tuple[str, ...]) -> list[str]:
    root = base / rel
    if not root.exists():
        return []
    out = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in suffixes:
            out.append(str(path.relative_to(base)))
    return sorted(out)


def claim_counts(representation: Any) -> dict[str, int]:
    if not isinstance(representation, dict):
        return {}
    out = {}
    for key in ["gap_claims", "method_claims", "performance_claims", "ablation_claims", "limitation_claims", "related_work_claims", "blocked_claims"]:
        value = representation.get(key)
        out[key] = len(value) if isinstance(value, list) else 0
    return out


def build(project: str, paper_type: str | None) -> dict[str, Any]:
    base = ar(project)
    tex = read_text(base / "paper/main.tex")
    representation = read_json(base / "paper/RESEARCH_REPRESENTATION.json", {})
    citation_profile = read_json(base / "literature/CITATION_QUALITY_PROFILE.json", {})
    review = read_json(base / "reviewer/REVIEW_FINDINGS.json", {})
    grounded = read_json(base / "paper/GROUNDED_WRITE_PACKAGE.json", {})
    verifier = read_json(base / "paper/PAPER_CLAIM_VERIFICATION.json", {})
    kind = infer_paper_type(base, paper_type)
    sections = count_tex_sections(tex)
    figures = list_files(base, "analyzer/figures", (".pdf", ".png", ".jpg", ".jpeg", ".svg"))
    tables = list_files(base, "analyzer/tables", (".tex", ".csv", ".json", ".md"))
    warnings: list[str] = []
    blocked_claims = claim_counts(representation).get("blocked_claims", 0)
    if blocked_claims:
        warnings.append(f"{blocked_claims} blocked claims remain in RESEARCH_REPRESENTATION")
    if isinstance(grounded, dict) and grounded and grounded.get("ground_status") != "passed":
        warnings.append("GROUNDED_WRITE_PACKAGE ground_status is not passed")
    if isinstance(verifier, dict) and verifier and verifier.get("status") != "passed":
        warnings.append("PAPER_CLAIM_VERIFICATION status is not passed")
    hits = pattern_hits(tex)
    for name, count in hits.items():
        if tex and count == 0:
            warnings.append(f"paragraph logic pattern not observed in main.tex: {name}")
    if kind == "survey":
        citation_total = ((citation_profile.get("summary") or {}).get("total_citations") if isinstance(citation_profile, dict) else None) or 0
        if citation_total and citation_total < 80:
            warnings.append("survey-mode citation count below draft target 80")
        if len(tables) < 5:
            warnings.append("survey-mode table count below short-survey target 5")
        if len(figures) < 3:
            warnings.append("survey-mode figure count below short-survey target 3")
        if not any("taxonomy" in section.lower() or "background" in section.lower() for section in sections):
            warnings.append("survey-mode sections should include background/taxonomy structure")
    if isinstance(review, dict) and review.get("status") in {"blocked", "needs_repair", "failed"}:
        warnings.append("review findings indicate repair is still needed before final writing")
    score_dashboard = {
        "target_phase_score": 8.5 if kind == "survey" else None,
        "survey_targets_are_warnings": True,
        "claim_strength_rule": "claim strength must not exceed experiment/citation evidence strength",
    }
    return {
        "schema_version": 1,
        "generated_at": now(),
        "paper_type": kind,
        "status": "complete",
        "grounding": "writing dashboard only; does not replace grounded_write_lint.py or paper_claim_verifier.py",
        "sections": sections,
        "paragraph_logic_hits": hits,
        "claim_counts": claim_counts(representation),
        "figure_count": len(figures),
        "table_count": len(tables),
        "figures": figures,
        "tables": tables,
        "citation_quality_profile_present": bool(citation_profile),
        "score_dashboard": score_dashboard,
        "warnings": warnings,
    }


def check(project: str) -> dict[str, Any]:
    base = ar(project)
    profile = read_json(base / "paper/WRITING_QUALITY_PROFILE.json", {})
    missing: list[str] = []
    warnings: list[str] = []
    if not isinstance(profile, dict) or not profile:
        missing.append("paper/WRITING_QUALITY_PROFILE.json")
    else:
        if profile.get("schema_version") != 1:
            missing.append("schema_version=1")
        if not present(profile.get("paper_type")):
            missing.append("paper_type")
        if not isinstance(profile.get("paragraph_logic_hits"), dict):
            missing.append("paragraph_logic_hits")
        warnings.extend(str(item) for item in profile.get("warnings", []) if isinstance(item, str))
    return {"complete": not missing, "status": "complete" if not missing else "incomplete", "missing": missing, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--paper-type", choices=["method", "survey", "benchmark", "systems"], default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        out = check(args.project)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        raise SystemExit(0 if out["complete"] else 1)
    payload = build(args.project, args.paper_type)
    write_json(ar(args.project) / "paper/WRITING_QUALITY_PROFILE.json", payload)
    out = check(args.project)
    print(json.dumps({"ok": out["complete"], **out}, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
