#!/usr/bin/env python3
"""Lint .autoreskill stage contracts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


READY = {"ready", "complete", "completed", "pass", "passed", "verified"}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def nonempty(path: Path) -> bool:
    return path.exists() and path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())


def has_any(base: Path, rels: list[str]) -> bool:
    return any(nonempty(base / rel) or (base / rel).exists() for rel in rels)


def has_glob(base: Path, pattern: str) -> bool:
    return any(path.is_file() and nonempty(path) for path in base.glob(pattern))


def result(
    stage: str,
    complete: bool,
    missing: list[str],
    source: str,
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "missing": missing,
        "warnings": warnings or [],
        "contract_source": source,
        "details": details or {},
    }


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"stdout": proc.stdout}
    parsed.setdefault("returncode", proc.returncode)
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    return parsed


def lint(project: str, stage: str) -> dict[str, Any]:
    base = ar(project)
    if stage == "init":
        missing = [
            rel
            for rel in [
                "goal_state.json",
                "autopilot_policy.json",
                "capabilities.json",
                "memory.md",
                "decision_log.jsonl",
                "blocker_ledger.jsonl",
                "repair_queue.jsonl",
                "async_jobs.jsonl",
            ]
            if not (base / rel).exists()
        ]
        return result(stage, not missing, missing, "init_contract")

    if stage == "topic_search":
        ok = has_any(base, ["literature/LITERATURE_DISCOVERY_PACKET.json", "literature/LITERATURE_DISCOVERY_RUN.json"])
        return result(stage, ok, [] if ok else ["literature discovery evidence"], "topic_search_contract")

    if stage == "graph_build":
        decision = read_json(base / "graph/GRAPH_BUILD_DECISION.json")
        ok = bool(decision and decision.get("decision") == "complete" and decision.get("source_backed_graph_claim") is True)
        return result(stage, ok, [] if ok else ["graph/GRAPH_BUILD_DECISION.json decision=complete source_backed_graph_claim=true"], "graph_build_contract")

    if stage == "frontier_mapping":
        ok = has_any(base, ["papernexus/research_material_pack.json", "papernexus/source_discovery_plan.json", "ideation/CHALLENGE_INSIGHT_TREE.md"])
        return result(stage, ok, [] if ok else ["frontier mapping material pack or challenge insight tree"], "frontier_mapping_contract")

    if stage == "literature_review":
        missing = [
            rel
            for rel in ["literature/SOTA_MATRIX.md", "literature/GAP_SYNTHESIS.md"]
            if not nonempty(base / rel)
        ]
        return result(stage, not missing, missing, "literature_review_contract")

    if stage == "ideation":
        skill_root = Path(__file__).resolve().parents[2]
        contract = read_json(base / "ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json")
        pool_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--pool",
                "ideation/EXPERIMENT_IDEA_POOL.json",
            ]
        )
        missing = []
        warnings = []
        if not (contract and contract.get("status") == "ready"):
            missing.append("ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json status=ready")
        if not pool_lint.get("complete"):
            items = pool_lint.get("missing") if isinstance(pool_lint.get("missing"), list) else []
            missing.extend(f"idea_pool_lint: {item}" for item in items)
            if pool_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_pool_lint failed without structured missing output")
        items = pool_lint.get("warnings") if isinstance(pool_lint.get("warnings"), list) else []
        warnings.extend(f"idea_pool_lint: {item}" for item in items)
        return result(stage, not missing, missing, "ideation_contract", warnings, {"idea_pool_lint": pool_lint})

    if stage == "idea_gate":
        skill_root = Path(__file__).resolve().parents[2]
        pool_lint = run_json(
            [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/idea_pool_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
                "--pool",
                "ideation/EXPERIMENT_IDEA_POOL.json",
                "--require-selected",
            ]
        )
        missing = []
        warnings = []
        if not has_any(base, ["ideation/TOURNAMENT_SCOREBOARD.json", "ideation/TOP3_DIRECTION_SUMMARY.md", "reviewer/IDEA_GATE_REVIEW.json"]):
            missing.append("idea gate review or tournament scoreboard")
        if not pool_lint.get("complete"):
            items = pool_lint.get("missing") if isinstance(pool_lint.get("missing"), list) else []
            missing.extend(f"idea_pool_lint: {item}" for item in items)
            if pool_lint.get("returncode", 1) != 0 and not items:
                missing.append("idea_pool_lint failed without structured missing output")
        items = pool_lint.get("warnings") if isinstance(pool_lint.get("warnings"), list) else []
        warnings.extend(f"idea_pool_lint: {item}" for item in items)
        return result(stage, not missing, missing, "idea_gate_contract", warnings, {"idea_pool_lint": pool_lint})

    if stage == "experiment_plan":
        skill_root = Path(__file__).resolve().parents[2]
        scripts = {
            "prelaunch_lint": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/prelaunch_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ],
            "innovation_lint": [
                sys.executable,
                str(skill_root / "autoreskill-experiment-plan/scripts/innovation_lint.py"),
                "--project",
                str(Path(project).expanduser().resolve()),
            ],
        }
        details = {name: run_json(cmd) for name, cmd in scripts.items()}
        missing: list[str] = []
        warnings: list[str] = []
        complete = True
        for name, out in details.items():
            if not out.get("complete"):
                complete = False
                items = out.get("missing") if isinstance(out.get("missing"), list) else []
                missing.extend(f"{name}: {item}" for item in items)
                if out.get("returncode", 1) != 0 and not items:
                    missing.append(f"{name} failed without structured missing output")
            items = out.get("warnings") if isinstance(out.get("warnings"), list) else []
            warnings.extend(f"{name}: {item}" for item in items)
        return result(stage, complete, missing, "experiment_plan_contract", warnings, details)

    if stage == "code":
        missing = []
        if not nonempty(base / "coder/EXPERIMENT_INDEX.md"):
            missing.append("coder/EXPERIMENT_INDEX.md")
        if not has_glob(base, "coder/experiments/**/EXPERIMENT_MANIFEST.json"):
            missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
        if not has_glob(base, "coder/experiments/**/logs/dry_run*"):
            missing.append("coder/experiments/**/logs/dry_run*")
        return result(stage, not missing, missing, "code_contract")

    if stage == "experiment":
        missing = []
        if not nonempty(base / "coder/EXPERIMENT_LEDGER.json"):
            missing.append("coder/EXPERIMENT_LEDGER.json")
        if not (has_glob(base, "coder/experiments/**/REMOTE_RUN.json") or has_glob(base, "coder/experiments/**/results/*")):
            missing.append("REMOTE_RUN.json or experiment results")
        return result(stage, not missing, missing, "experiment_contract")

    if stage == "analysis":
        missing = []
        warnings = []
        if not nonempty(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md"):
            missing.append("analyzer/CLAIM_EVIDENCE_MATRIX.md")
        if not nonempty(base / "analyzer/TRACK_VERDICTS.md"):
            missing.append("analyzer/TRACK_VERDICTS.md")
        if not (nonempty(base / "coder/EXPERIMENT_LEDGER.json") or nonempty(base / "coder/EXPERIMENT_INDEX.md")):
            missing.append("coder/EXPERIMENT_LEDGER.json or coder/EXPERIMENT_INDEX.md")
        if not nonempty(base / "analyzer/UNSUPPORTED_CLAIMS.md"):
            warnings.append("analyzer/UNSUPPORTED_CLAIMS.md")
        if not (nonempty(base / "analyzer/NARRATIVE_REPORT.md") or nonempty(base / "analyzer/ANALYSIS_REPORT.md")):
            warnings.append("analyzer/NARRATIVE_REPORT.md or analyzer/ANALYSIS_REPORT.md")
        return result(stage, not missing, missing, "analysis_contract", warnings)

    if stage == "review_pressure":
        findings = read_json(base / "reviewer/REVIEW_FINDINGS.json")
        status = str((findings or {}).get("status", "")).lower()
        issues = []
        if isinstance(findings, dict):
            for key in ["issues", "findings", "review_findings", "items"]:
                if isinstance(findings.get(key), list):
                    issues = findings[key]
                    break
        blocking = [
            issue
            for issue in issues
            if isinstance(issue, dict)
            and str(issue.get("severity") or issue.get("priority") or "").lower() in {"critical", "high"}
            and str(issue.get("status") or issue.get("state") or "open").lower() not in {"closed", "resolved", "waived", "accepted_risk", "fixed"}
        ]
        ok = bool(findings and status in READY and not blocking)
        missing = []
        if not findings:
            missing.append("reviewer/REVIEW_FINDINGS.json")
        if findings and status not in READY:
            missing.append("reviewer/REVIEW_FINDINGS.json status ready")
        if blocking:
            missing.append("open high/critical review findings")
        return result(stage, ok, missing, "review_pressure_contract")

    if stage == "writing":
        ok = nonempty(base / "paper/main.tex")
        return result(stage, ok, [] if ok else ["paper/main.tex"], "writing_contract")

    if stage == "submission_ready":
        package = read_json(base / "submission_ready.json")
        status = str((package or {}).get("status", "")).lower()
        ok = nonempty(base / "paper/main.tex") and (base / "paper/main.pdf").exists() and status in READY
        missing = []
        if not nonempty(base / "paper/main.tex"):
            missing.append("paper/main.tex")
        if not (base / "paper/main.pdf").exists():
            missing.append("paper/main.pdf")
        if status not in READY:
            missing.append("submission_ready.json status ready")
        return result(stage, ok, missing, "submission_ready_contract")

    return result(stage, False, [f"unknown stage {stage}"], "unknown_contract")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    out = lint(args.project, args.stage)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
