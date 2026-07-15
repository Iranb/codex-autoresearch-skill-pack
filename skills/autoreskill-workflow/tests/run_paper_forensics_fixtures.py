#!/usr/bin/env python3
"""Regression checks for paper forensics lint and contract integration."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/paper_forensics"
FORENSICS = ROOT / "scripts/paper_forensics_lint.py"
CONTRACT = ROOT / "scripts/contract_lint.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_json(cmd: list[str], expect_code: int | None = None) -> tuple[dict[str, Any], int]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"command did not emit JSON: {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}") from exc
    if expect_code is not None and proc.returncode != expect_code:
        raise AssertionError(
            f"unexpected exit code {proc.returncode}, expected {expect_code}: {' '.join(cmd)}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return payload, proc.returncode


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def finding_ids(project: Path) -> set[str]:
    payload = read_json(project / ".autoreskill/paper/PAPER_FORENSICS_FINDINGS.json")
    return {str(item.get("check_id")) for item in payload.get("findings", [])}


def run_forensics_fixture(name: str, expected_complete: bool) -> tuple[dict[str, Any], set[str], dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / name
        shutil.copytree(FIXTURES / name, project)
        payload, _ = run_json(
            ["python", str(FORENSICS), "--project", str(project), "--stage", "writing"],
            expect_code=0 if expected_complete else 1,
        )
        findings_payload = read_json(project / ".autoreskill/paper/PAPER_FORENSICS_FINDINGS.json")
        findings = findings_payload.get("findings") if isinstance(findings_payload.get("findings"), list) else []
        finding_hashes = [str(item.get("finding_hash") or "") for item in findings if isinstance(item, dict)]
        require(payload.get("input_hashes", {}).get("paper/main.tex"), f"{name} should record paper/main.tex input hash")
        require("finding_hashes" in payload, f"{name} should record finding_hashes")
        require(payload["finding_hashes"] == finding_hashes, f"{name} report finding hashes should match findings payload")
        require(all(finding_hashes), f"{name} every finding should have a deterministic finding_hash")
        require(isinstance(payload.get("downgraded_counts"), dict), f"{name} should record downgraded_counts")
        ids = finding_ids(project)
        ais = read_json(project / ".autoreskill/paper/AIS_STYLE_IMPRESSIONS.json")
    return payload, ids, ais


def assert_forensics_fixture(name: str, expected_complete: bool, expected_check: str | None = None) -> dict[str, Any]:
    payload, ids, ais = run_forensics_fixture(name, expected_complete)
    require(payload["complete"] is expected_complete, f"{name} complete mismatch: {payload}")
    if expected_check:
        require(expected_check in ids, f"{name} should contain {expected_check}, got {sorted(ids)}")
    return ais


def story_doc(headings: list[str]) -> str:
    para = (
        "This narrative uses near-neighbor transfer evidence, promoted experiment support, "
        "claim limits, reviewer risk, and downgraded alternatives to keep the paper story "
        "evidence-aligned and auditable for a top-tier venue. "
    )
    lines: list[str] = ["# Story"]
    for heading in headings:
        lines.extend([f"## {heading}", para * 3])
    if "Final Narrative Spine" in headings:
        lines.extend(
            [
                "1. The target protocol exposes a concrete tension.",
                "2. A near-neighbor mechanism resolves the hidden cause.",
                "3. The promoted evidence supports the bounded claim.",
            ]
        )
    return "\n\n".join(lines)


def populate_story(base: Path) -> None:
    write_text(
        base / "user_view/innovation_story/00_STORYLINE_DESIGN.md",
        story_doc(
            [
                "Paper Thesis",
                "Reader Belief Shift",
                "Opening Tension",
                "Hidden Cause",
                "Core Scientific Contribution",
                "Method As Resolution",
                "Novelty Positioning",
                "Proof Ladder",
                "Figure Story",
                "Reviewer Risk And Defense",
                "Final Narrative Spine",
            ]
        ),
    )
    write_text(
        base / "user_view/innovation_story/01_METHOD_INNOVATION_STORY.md",
        story_doc(
            [
                "Core Problem Tension",
                "Where The Method Comes From",
                "Method Idea In One Sentence",
                "Mechanism Construction",
                "Contribution Roles And Dependencies",
                "What Is Actually New",
                "Evidence Chain",
                "Experiment Implications",
                "Current User-Facing Summary",
            ]
        ),
    )
    write_text(
        base / "user_view/innovation_story/02_CLAIM_EVIDENCE_MAP.md",
        story_doc(
            [
                "Main Claims",
                "Evidence Support",
                "Claim Limits",
                "Core Contribution Evidence",
                "Experiment Mapping",
                "Revision Notes",
            ]
        ),
    )


def effective_points() -> dict[str, Any]:
    return {
        "status": "passed",
        "effective_innovation_points": [
            {
                "innovation_point_id": "core-1",
                "contribution_class": "core_scientific_contribution",
                "story_role": "method mechanism",
                "evidence_status": "effective",
                "claim_scope": "strong bounded claim",
                "evidence_ref": "evidence:core-1",
            }
        ],
        "negative_knowledge_summary": "Failed and parked routes remain downgraded.",
    }


def claim_verification() -> dict[str, Any]:
    return {
        "status": "passed",
        "claim_drift_status": "passed",
        "scientific_alignment_status": "passed",
        "numeric_grounding_status": "passed",
        "non_defensive_writing_status": {
            "status": "passed",
            "necessary_limitations_preserved": True,
            "evidence_boundary_preserved": True,
            "claim_upgrades_blocked": True,
            "unsupported_claim_upgrades": False,
            "defensive_underclaim_remaining": False,
            "top_tier_claim_posture": "checked",
            "locations_checked": ["title", "abstract", "introduction", "contribution"],
        },
    }


def populate_common(project: Path, tex: str, submission: bool = False) -> None:
    base = project / ".autoreskill"
    write_json(base / "goal_state.json", {"goal_type": "paper_producing_top_tier", "claim_mode": "strong_paper_claims"})
    write_json(base / "autopilot_policy.json", {"goal_type": "paper_producing_top_tier", "claim_mode": "strong_paper_claims"})
    write_text(base / "paper/main.tex", tex)
    write_json(base / "paper/write_package.json", {"status": "ready"})
    write_json(base / "paper/RESEARCH_REPRESENTATION.json", {"claim_evidence_tags": ["c1"], "performance_claims": []})
    write_text(base / "paper/RESEARCH_REPRESENTATION.md", "Representation with bounded claims and evidence refs.")
    write_json(base / "paper/GROUNDED_WRITE_PACKAGE.json", {"ground_status": "passed"})
    write_json(base / "paper/PAPER_CLAIM_VERIFICATION.json", claim_verification())
    write_text(
        base / "paper/CCFA_WRITING_AUDIT.md",
        "Non-Defensive Writing Pass. Necessary Limitations Preserved. Claim Upgrades Blocked. Top-Tier Reviewer Risk.",
    )
    write_text(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md", "Claim evidence matrix.")
    write_json(base / "analyzer/IDEA_OUTCOME_SUMMARY.json", effective_points())
    populate_story(base)
    if submission:
        write_text(base / "paper/main.pdf", "%PDF-1.4\n% test placeholder\n")
        write_json(base / "submission_ready.json", {"status": "ready", "required_artifacts": [
            "paper/TARGET_VENUE_SUMMARY.md",
            "paper/REPRODUCIBILITY_CHECKLIST.md",
            "paper/VENUE_CHECKLIST_GAPS.md",
            "reviewer/CITATION_INTEGRITY_REPORT.md",
        ]})
        write_text(base / "paper/TARGET_VENUE_SUMMARY.md", "Target venue summary.")
        write_text(base / "paper/REPRODUCIBILITY_CHECKLIST.md", "Reproducibility checklist.")
        write_text(base / "paper/VENUE_CHECKLIST_GAPS.md", "No unresolved checklist gaps.")
        write_text(base / "reviewer/CITATION_INTEGRITY_REPORT.md", "Citation integrity report.")
        write_json(base / "literature/CITATION_QUEUE.json", {"citations": []})
        write_text(base / "paper/refs.bib", "@article{dummy,title={Dummy}}\n")
        write_json(
            base / "reviewer/MULTI_ROUND_REVIEW_GATE.json",
            {
                "status": "passed",
                "completed_rounds": 2,
                "open_blocking_count": 0,
                "review_axes": [
                    "novelty",
                    "soundness method",
                    "experiments statistics",
                    "clarity writing",
                    "reproducibility limitations",
                    "claim drift",
                    "scientific alignment",
                    "defensive underclaim",
                ],
            },
        )
        write_json(base / "reviewer/REVIEW_REPAIR_LEDGER.json", {"repairs": [{"status": "passed"}, {"status": "passed"}]})


def test_contract_stage(stage: str, tex_name: str, expected_complete: bool) -> None:
    tex = (FIXTURES / tex_name / ".autoreskill/paper/main.tex").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        populate_common(project, tex, submission=stage == "submission_ready")
        payload, code = run_json(["python", str(CONTRACT), "--project", str(project), "--stage", stage])
        require(payload["complete"] is expected_complete, f"{stage}/{tex_name} complete mismatch: {payload}")
        if expected_complete:
            require(code == 0, f"{stage}/{tex_name} expected exit 0, got {code}")
        else:
            require(code != 0, f"{stage}/{tex_name} expected nonzero exit")
            require(
                any("paper_forensics_lint" in str(item) for item in payload.get("missing", [])),
                f"{stage}/{tex_name} should fail through paper_forensics_lint, got {payload.get('missing')}",
            )


def main() -> None:
    assert_forensics_fixture("pass_clean", True)
    assert_forensics_fixture("fail_delta_error", False, "NUMERIC-RELATIVE-ARITHMETIC")
    assert_forensics_fixture("fail_grim", False, "STAT-GRIM-IMPOSSIBLE-PERCENT")
    assert_forensics_fixture("fail_pipeline_artifact", False, "PRESENTATION-EXACT-RESIDUE")
    ais = assert_forensics_fixture("warn_ais_only", True)
    require(ais.get("zero_weight") is True, "AIS report must be zero-weight")
    require(ais.get("impressions"), "AIS-only fixture should record impressions")

    test_contract_stage("writing", "pass_clean", True)
    test_contract_stage("writing", "fail_delta_error", False)
    test_contract_stage("submission_ready", "pass_clean", True)
    test_contract_stage("submission_ready", "fail_delta_error", False)


if __name__ == "__main__":
    main()
