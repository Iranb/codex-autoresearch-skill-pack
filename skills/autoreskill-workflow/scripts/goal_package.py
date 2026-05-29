#!/usr/bin/env python3
"""Prepare an evidence-bounded venue submission package scaffold."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contract_lint import lint
from goal_state import ar, load_state, save_state


READY = {"ready", "complete", "completed", "pass", "passed", "verified"}
DEFAULT_TARGET_VENUE = "unspecified_top_tier"
GENERATED_TEXT_MARKERS = (
    "Status: draft scaffold.",
    "Replace this with the final target-venue summary",
    "TBD after final manuscript",
    "- `paper/",
    "- `reviewer/",
    "- `analyzer/",
)

VENUE_PROFILES = {
    "unspecified_top_tier": {
        "display": "Unspecified Top-Tier Venue",
        "family": "custom",
        "tier": "top_venue",
        "summary_title": "Target-Venue Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["generic top-tier profile; choose a venue-specific profile before final administrative checks"],
    },
    "nmi": {
        "display": "Nature Machine Intelligence",
        "family": "journal",
        "tier": "top_journal",
        "summary_title": "NMI Summary Paragraph",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/SIGNIFICANCE_STATEMENT.md",
            "paper/COVER_LETTER_DRAFT.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
            "paper/REPORTING_CHECKLIST_GAPS.md",
        ],
        "notes": ["broad-reader summary paragraph", "significance statement", "journal reporting/admin statements"],
    },
    "neurips": {
        "display": "NeurIPS",
        "family": "conference",
        "tier": "top_conference",
        "summary_title": "NeurIPS Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/ETHICS_IMPACT_STATEMENT.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["reproducibility checklist", "broader impact/ethics checks", "supplementary material readiness"],
    },
    "icml": {
        "display": "ICML",
        "family": "conference",
        "tier": "top_conference",
        "summary_title": "ICML Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/ETHICS_IMPACT_STATEMENT.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["empirical protocol clarity", "reproducibility checklist", "limitations and ethics statement"],
    },
    "iclr": {
        "display": "ICLR",
        "family": "conference",
        "tier": "top_conference",
        "summary_title": "ICLR Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/ETHICS_IMPACT_STATEMENT.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["open-review style clarity", "reproducibility evidence", "limitations and ethics statement"],
    },
    "cvpr": {
        "display": "CVPR",
        "family": "conference",
        "tier": "top_conference",
        "summary_title": "CVPR Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/ETHICS_IMPACT_STATEMENT.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["visual benchmark fairness", "dataset/license checks", "supplementary material readiness"],
    },
    "acl": {
        "display": "ACL",
        "family": "conference",
        "tier": "top_conference",
        "summary_title": "ACL Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/LIMITATIONS.md",
            "paper/ETHICS_IMPACT_STATEMENT.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["limitations section", "ethics statement", "dataset and annotation transparency"],
    },
    "tpami": {
        "display": "IEEE TPAMI",
        "family": "journal",
        "tier": "top_journal",
        "summary_title": "TPAMI Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/COVER_LETTER_DRAFT.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["journal cover letter", "extended empirical evidence", "data/code availability"],
    },
    "jmlr": {
        "display": "JMLR",
        "family": "journal",
        "tier": "top_journal",
        "summary_title": "JMLR Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/COVER_LETTER_DRAFT.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["archival clarity", "complete proofs/appendices where relevant", "data/code availability"],
    },
}

VENUE_ALIASES = {
    "": "unspecified_top_tier",
    "unspecified": "unspecified_top_tier",
    "unspecified top tier": "unspecified_top_tier",
    "unspecified top-tier": "unspecified_top_tier",
    "top tier": "unspecified_top_tier",
    "top-tier": "unspecified_top_tier",
    "nature machine intelligence": "nmi",
    "nat mach intell": "nmi",
    "nmi": "nmi",
    "neurips": "neurips",
    "nips": "neurips",
    "icml": "icml",
    "iclr": "iclr",
    "cvpr": "cvpr",
    "iccv": "cvpr",
    "eccv": "cvpr",
    "acl": "acl",
    "emnlp": "acl",
    "naacl": "acl",
    "tpami": "tpami",
    "ieee tpami": "tpami",
    "jmlr": "jmlr",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def update_artifact_index(base: Path, rels: list[str]) -> None:
    path = base / "artifacts_index.json"
    index = read_json(path, {"schema_version": 1, "artifacts": []})
    artifacts = [row for row in index.get("artifacts", []) if row.get("path") not in set(rels)]
    for rel in rels:
        artifacts.append({"path": rel, "kind": "venue_package", "stage": "submission_ready", "source": "goal_package", "updated_at": now()})
    index["schema_version"] = 1
    index["artifacts"] = artifacts
    index["updated_at"] = now()
    write_json(path, index)


def gap_list(base: Path) -> list[str]:
    gaps = []
    checks = {
        "paper/main.tex": nonempty(base / "paper/main.tex"),
        "paper/main.pdf": (base / "paper/main.pdf").exists(),
        "paper/refs.bib": nonempty(base / "paper/refs.bib"),
        "reviewer/REVIEW_FINDINGS.json": (base / "reviewer/REVIEW_FINDINGS.json").exists(),
        "reviewer/CITATION_INTEGRITY_REPORT.md": nonempty(base / "reviewer/CITATION_INTEGRITY_REPORT.md"),
        "analyzer/CLAIM_EVIDENCE_MATRIX.md": nonempty(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md"),
        "paper/write_package.json": (base / "paper/write_package.json").exists(),
    }
    for rel, ok in checks.items():
        if not ok:
            gaps.append(rel)
    return gaps


def normalize_venue(value: str) -> str:
    key = " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())
    return VENUE_ALIASES.get(key, key or DEFAULT_TARGET_VENUE)


def venue_profile(value: str) -> dict[str, Any]:
    key = normalize_venue(value)
    profile = VENUE_PROFILES.get(key)
    if profile:
        return {"key": key, **profile}
    return {
        "key": key,
        "display": value or key.upper(),
        "family": "custom",
        "tier": "top_venue",
        "summary_title": f"{value or key.upper()} Submission Summary",
        "required": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
        ],
        "notes": ["custom venue profile; verify venue-specific administrative requirements manually"],
    }


def actual_submission_blockers(base: Path, existing: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    """Keep mechanical package readiness separate from venue submission readiness."""
    blockers = []
    track_verdicts = (base / "analyzer/TRACK_VERDICTS.md").read_text(encoding="utf-8", errors="ignore") if (base / "analyzer/TRACK_VERDICTS.md").exists() else ""
    citation_report = (base / "reviewer/CITATION_INTEGRITY_REPORT.md").read_text(encoding="utf-8", errors="ignore") if (base / "reviewer/CITATION_INTEGRITY_REPORT.md").exists() else ""
    checklist = (base / "paper/REPORTING_CHECKLIST_GAPS.md").read_text(encoding="utf-8", errors="ignore") if (base / "paper/REPORTING_CHECKLIST_GAPS.md").exists() else ""

    lowered_verdicts = track_verdicts.lower()
    repaired_stress_pilot = "repaired" in lowered_verdicts or "distance_tail" in lowered_verdicts or "distance-tail" in lowered_verdicts
    if ("mixed" in lowered_verdicts or "partially falsif" in lowered_verdicts) and not repaired_stress_pilot:
        blockers.append("real visual-feature evidence is mixed or partially falsifying and requires method repair or claim downgrade")
    if repaired_stress_pilot and ("fixed-count stress baseline" in lowered_verdicts or "fair-baseline gap" in lowered_verdicts):
        blockers.append("repaired real visual-feature stress pilot still lacks full fair literature-baseline visual GCD benchmark")
    elif "protocol-simulator" in lowered_verdicts or "fixed-count stress baseline" in lowered_verdicts:
        blockers.append("full fair literature-baseline visual GCD benchmark is not verified")
    if "single" in lowered_verdicts:
        blockers.append("multi-seed manuscript statistics are not verified")
    if not citation_report or "verified bibliography" not in citation_report.lower():
        blockers.append("bibliography has not been independently verified against DOI/arXiv/venue metadata")
    if "compute" in checklist.lower() or "cost" in checklist.lower():
        blockers.append("compute/cost evidence is not complete for final manuscript reporting")
    if not checklist or "tbd" in checklist.lower() or "gap" in checklist.lower():
        blockers.append(f"{profile['display']} administrative statements and reporting checklist still require final author-supplied details")
    if not blockers:
        blockers.append(f"final {profile['display']} submission readiness requires explicit human/editorial confirmation")
    return blockers


def package_text(base: Path, rel: str, default_text: str) -> str:
    """Preserve evidence-bound package text instead of overwriting it with scaffold prose."""
    path = base / rel
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="ignore")
        if existing.strip() and not any(marker in existing for marker in GENERATED_TEXT_MARKERS):
            return existing
    return default_text


def review_ready(base: Path) -> bool:
    findings = read_json(base / "reviewer/REVIEW_FINDINGS.json", {})
    status = str(findings.get("status", "")).lower() if isinstance(findings, dict) else ""
    return status in READY


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--venue", default=DEFAULT_TARGET_VENUE)
    parser.add_argument("--advance", action="store_true", help="move goal_state to submission_ready")
    args = parser.parse_args()

    project = str(Path(args.project).expanduser().resolve())
    base = ar(project)
    state = load_state(project)
    profile = venue_profile(args.venue)
    gaps = gap_list(base)
    ready = not gaps and review_ready(base)
    status = "ready" if ready else "blocked"
    claim_matrix = "present" if nonempty(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md") else "missing"
    paper_title = read_json(base / "paper/write_package.json", {}).get("title", "TBD: evidence-bound manuscript title")
    existing_package = read_json(base / "submission_ready.json", {})
    submission_blockers = actual_submission_blockers(base, existing_package, profile)

    summary = (
        f"# {profile['summary_title']}\n\n"
        f"Title: {paper_title}\n\n"
        f"Target venue: {profile['display']}\n\n"
        "Status: draft scaffold. Replace this with the final target-venue summary only after "
        "the manuscript, claim-evidence matrix, citation integrity report, and review findings are ready.\n\n"
        f"Claim-evidence matrix: {claim_matrix}\n"
    )
    venue_profile_text = (
        "# Venue Profile\n\n"
        f"- venue: {profile['display']}\n"
        f"- profile_key: {profile['key']}\n"
        f"- family: {profile['family']}\n"
        f"- tier: {profile['tier']}\n"
        "- notes:\n"
        + "\n".join(f"  - {note}" for note in profile["notes"])
        + "\n"
    )
    significance = (
        "# Significance Statement\n\n"
        "Status: draft scaffold. State only validated contributions that appear in the claim-evidence matrix. "
        "Do not promote unsupported or single-seed claims.\n"
    )
    cover = (
        "# Cover Letter Draft\n\n"
        f"Venue: {profile['display']}\n\n"
        "Dear Editors,\n\n"
        "TBD after final manuscript, author information, competing interests, data availability, code availability, "
        "and validated contribution claims are complete.\n"
    )
    checklist = (
        f"# {profile['display']} Checklist Gaps\n\n"
        + ("\n".join(f"- `{gap}`" for gap in gaps) if gaps else "- none\n")
        + "\n\nVenue-specific required package artifacts:\n"
        + "\n".join(f"- `{rel}`" for rel in profile["required"])
        + "\n"
    )
    reproducibility = (
        "# Reproducibility Checklist\n\n"
        "Status: draft scaffold. Fill this from experiment manifests, remote run ledgers, seeds, datasets, "
        "environment files, and claim-evidence matrix before final submission.\n"
    )
    ethics = (
        "# Ethics and Impact Statement\n\n"
        "Status: draft scaffold. State only risks, limitations, dataset/license constraints, and broader impacts "
        "supported by project artifacts or author-provided facts.\n"
    )
    limitations = (
        "# Limitations\n\n"
        "Status: draft scaffold. Carry forward unsupported claims, failed pilots, scope limits, and benchmark gaps "
        "from analyzer/UNSUPPORTED_CLAIMS.md and analyzer/TRACK_VERDICTS.md.\n"
    )

    rel_text = {
        "paper/VENUE_PROFILE.md": package_text(base, "paper/VENUE_PROFILE.md", venue_profile_text),
        "paper/TARGET_VENUE_SUMMARY.md": package_text(base, "paper/TARGET_VENUE_SUMMARY.md", summary),
        "paper/SIGNIFICANCE_STATEMENT.md": package_text(base, "paper/SIGNIFICANCE_STATEMENT.md", significance),
        "paper/COVER_LETTER_DRAFT.md": package_text(base, "paper/COVER_LETTER_DRAFT.md", cover),
        "paper/VENUE_CHECKLIST_GAPS.md": package_text(base, "paper/VENUE_CHECKLIST_GAPS.md", checklist),
        "paper/REPORTING_CHECKLIST_GAPS.md": package_text(base, "paper/REPORTING_CHECKLIST_GAPS.md", checklist),
        "paper/REPRODUCIBILITY_CHECKLIST.md": package_text(base, "paper/REPRODUCIBILITY_CHECKLIST.md", reproducibility),
        "paper/ETHICS_IMPACT_STATEMENT.md": package_text(base, "paper/ETHICS_IMPACT_STATEMENT.md", ethics),
        "paper/LIMITATIONS.md": package_text(base, "paper/LIMITATIONS.md", limitations),
    }
    if profile["key"] == "nmi":
        rel_text["paper/NMI_SUMMARY_PARAGRAPH.md"] = package_text(base, "paper/NMI_SUMMARY_PARAGRAPH.md", summary)
    for rel, text in rel_text.items():
        write_text(base / rel, text)

    package = {
        "schema_version": 1,
        "created_at": now(),
        "venue": args.venue,
        "venue_profile": profile,
        "status": status,
        "ready": ready,
        "ready_scope": "mechanical_autoreskill_contract_only",
        "actual_submission_ready": ready and not submission_blockers,
        "actual_target_submission_ready": ready and not submission_blockers,
        "actual_submission_blockers": submission_blockers,
        "gaps": gaps,
        "required_artifacts": sorted(set(profile["required"] + ["paper/VENUE_PROFILE.md", "reviewer/CITATION_INTEGRITY_REPORT.md"])),
        "generated_artifacts": sorted(rel_text),
        "paper_main_tex": str(base / "paper/main.tex"),
        "paper_main_pdf": str(base / "paper/main.pdf"),
        "review_ready": review_ready(base),
    }
    if profile["key"] == "nmi":
        package["actual_nmi_submission_ready"] = ready and not submission_blockers
        package["deprecated_fields"] = ["actual_nmi_submission_ready"]
    write_json(base / "submission_ready.json", package)
    package["submission_contract"] = lint(project, "submission_ready")
    write_json(base / "submission_ready.json", package)
    update_artifact_index(base, sorted([*rel_text, "submission_ready.json"]))
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "submission_ready", "action": "venue_package_scaffold", "details": package})
    if args.advance:
        state.update({"stage": "submission_ready", "owner": "WorkflowGuard", "next_action": "package_for_submission", "blocking_reason": None if ready else "; ".join(gaps)})
        save_state(project, state, "advance_to_submission_package", package)
    print(json.dumps(package, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
