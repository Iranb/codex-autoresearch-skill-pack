#!/usr/bin/env python3
"""Run the portable AutoResearch Phase-8 validation matrix that can run locally."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contract_lint import lint
from goal_state import STAGES, ar, load_state


FORBIDDEN_DEP_RE = re.compile(r"(?<!prohibition: )(research_workflow|\\.openclaw-research|PROJECT_MANIFEST)")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {"cmd": cmd, "returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def dependency_scan(skill_root: Path) -> dict[str, Any]:
    hits = []
    for path in skill_root.glob("autoreskill-*/**/*"):
        if path.is_dir():
            continue
        if path.suffix not in {".md", ".py", ".yaml", ".json"}:
            continue
        text = read_text(path)
        for idx, line in enumerate(text.splitlines(), 1):
            if any(token in line for token in ["research_workflow", ".openclaw-research", "PROJECT_MANIFEST"]):
                lowered = line.lower()
                allowed = (
                    any(phrase in lowered for phrase in ["do not", "forbidden", "prohibit", "without", "不能", "不依赖", "禁止", "removed"])
                    or path.name in {"goal_validate.py", "source_traceability.md"}
                )
                hits.append({"path": str(path), "line": idx, "allowed_prohibition_text": allowed, "text": line.strip()[:240]})
    bad = [hit for hit in hits if not hit["allowed_prohibition_text"]]
    return {"complete": not bad, "hits": hits, "bad_hits": bad}


def py_compile(skill_root: Path) -> dict[str, Any]:
    scripts = [str(path) for path in skill_root.glob("autoreskill-*/scripts/*.py")]
    if not scripts:
        return {"complete": False, "missing": ["scripts/*.py"]}
    out = run([sys.executable, "-m", "py_compile", *scripts])
    return {"complete": out["returncode"] == 0, "result": out}


def mcp_config_probe(capabilities_path: Path | None = None) -> dict[str, Any]:
    codex = run(["bash", "-lc", "command -v codex >/dev/null 2>&1 && codex mcp get papernexus-remote || true"])
    remote_url = os.environ.get("PAPERNEXUS_REMOTE_MCP_URL", "").strip()
    if remote_url:
        reachable = run(
            [
                "bash",
                "-lc",
                "env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy "
                "curl --noproxy '*' -sS -o /dev/null -w 'http_code=%{http_code}\\n' --connect-timeout 5 --max-time 8 "
                "\"${PAPERNEXUS_REMOTE_MCP_URL}\" || true",
            ],
            env={**os.environ, "PAPERNEXUS_REMOTE_MCP_URL": remote_url},
        )
        initialize = run(
            [
                "bash",
                "-lc",
                "if [ -z \"${PAPERNEXUS_REMOTE_API_TOKEN:-}\" ]; then echo token_missing; else "
                "env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy "
                "curl --noproxy '*' -sS -o /tmp/autoreskill_pn_init_body.json -w 'http_code=%{http_code}\\n' "
                "--connect-timeout 5 --max-time 8 "
                "-H \"Authorization: Bearer ${PAPERNEXUS_REMOTE_API_TOKEN}\" "
                "-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' "
                "--data '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"autoreskill-diagnostic\",\"version\":\"0\"}}}' "
                "\"${PAPERNEXUS_REMOTE_MCP_URL}\"; fi",
            ],
            env={**os.environ, "PAPERNEXUS_REMOTE_MCP_URL": remote_url},
        )
    else:
        reachable = {"cmd": ["env", "PAPERNEXUS_REMOTE_MCP_URL"], "returncode": 0, "stdout": "papernexus_remote_mcp_url_missing\n", "stderr": ""}
        initialize = {"cmd": ["env", "PAPERNEXUS_REMOTE_MCP_URL"], "returncode": 0, "stdout": "papernexus_remote_mcp_url_missing\n", "stderr": ""}
    caps = read_json(capabilities_path, {}) if capabilities_path else {}
    recorded_callable = caps.get("papernexus_remote_callable")
    callable_value = recorded_callable if isinstance(recorded_callable, bool) else None
    capability_record = {
        "path": str(capabilities_path) if capabilities_path else None,
        "papernexus_remote_callable": callable_value,
        "active_corpus": caps.get("active_corpus"),
        "research_controller_available": caps.get("research_controller_available"),
        "agent_materials_operations": caps.get("agent_materials_operations", []),
        "updated_at": caps.get("updated_at"),
    }
    return {
        "configured": "papernexus-remote" in codex["stdout"],
        "reachable_diagnostic": reachable["stdout"].strip(),
        "initialize_diagnostic": initialize["stdout"].strip(),
        "callable": callable_value,
        "note": "Reachability/initialize are diagnostics only; callable is copied from .autoreskill/capabilities.json after a successful papernexus-remote MCP tool call is recorded.",
        "capability_record": capability_record,
        "codex_mcp_get": codex,
    }


def specialized_linters(project: str, skill_root: Path) -> dict[str, Any]:
    scripts = {
        "controller": "autoreskill-papernexus-research-controller/scripts/controller_lint.py",
        "idea_support": "autoreskill-papernexus-innovation/scripts/idea_support_lint.py",
        "literature": "autoreskill-literature-review/scripts/literature_lint.py",
        "ideation": "autoreskill-ideation-panel/scripts/ideation_lint.py",
        "innovation": "autoreskill-experiment-plan/scripts/innovation_lint.py",
        "prelaunch": "autoreskill-experiment-plan/scripts/prelaunch_lint.py",
        "experiment_drift": "autoreskill-implement-experiment/scripts/experiment_drift_lint.py",
        "analysis": "autoreskill-analyze-results/scripts/analysis_lint.py",
        "write_package": "autoreskill-paper-write/scripts/write_package_lint.py",
        "review": "autoreskill-review-gate/scripts/review_lint.py",
        "citation": "autoreskill-review-gate/scripts/citation_lint.py",
        "submission": "autoreskill-review-gate/scripts/submission_lint.py",
    }
    out: dict[str, Any] = {}
    for name, rel_script in scripts.items():
        script = skill_root / rel_script
        result = run([sys.executable, str(script), "--project", project])
        parsed: Any = None
        if result["stdout"].strip():
            try:
                parsed = json.loads(result["stdout"])
            except json.JSONDecodeError:
                parsed = result["stdout"]
        out[name] = {"complete": result["returncode"] == 0, "result": parsed, "stderr": result["stderr"]}
    adapter = run(
        [
            sys.executable,
            str(skill_root / "academic-paper-reviewer/scripts/review_findings_adapter.py"),
            "--project",
            project,
            "--self-test",
            "--dry-run",
        ]
    )
    parsed_adapter: Any = None
    if adapter["stdout"].strip():
        try:
            parsed_adapter = json.loads(adapter["stdout"])
        except json.JSONDecodeError:
            parsed_adapter = adapter["stdout"]
    out["review_adapter_self_test"] = {"complete": adapter["returncode"] == 0, "result": parsed_adapter, "stderr": adapter["stderr"]}
    return out


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validation_summary(checks: dict[str, Any]) -> dict[str, Any]:
    stage_contracts = checks.get("stage_contracts", [])
    specialized = checks.get("specialized_linters", {})
    stage_failures = [
        {
            "stage": row.get("stage"),
            "status": row.get("status"),
            "missing": row.get("missing", []),
            "warnings": row.get("warnings", []),
        }
        for row in stage_contracts
        if not row.get("complete")
    ]
    specialized_failures = [
        {
            "name": name,
            "result": row.get("result"),
            "stderr": row.get("stderr", ""),
        }
        for name, row in specialized.items()
        if not row.get("complete")
    ]
    dependency_ok = bool(checks.get("dependency_scan", {}).get("complete"))
    python_compile_ok = bool(checks.get("python_compile", {}).get("complete"))
    clean_state_ok = bool(checks.get("clean_state_present", {}).get("complete"))
    papernexus_callable = checks.get("papernexus_config_transport", {}).get("callable") is True
    complete = all(
        [
            clean_state_ok,
            dependency_ok,
            python_compile_ok,
            papernexus_callable,
            not stage_failures,
            not specialized_failures,
        ]
    )
    return {
        "complete": complete,
        "clean_state_ok": clean_state_ok,
        "dependency_ok": dependency_ok,
        "python_compile_ok": python_compile_ok,
        "papernexus_callable": papernexus_callable,
        "stage_contract_count": len(stage_contracts),
        "stage_contract_failures": stage_failures,
        "specialized_linter_count": len(specialized),
        "specialized_failures": specialized_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--skill-root", default=os.environ.get("CODEX_SKILL_ROOT", "~/.codex/skills"))
    parser.add_argument("--output", default="validation/PHASE8_VALIDATION.json")
    args = parser.parse_args()

    project = str(Path(args.project).expanduser().resolve())
    base = ar(project)
    skill_root = Path(args.skill_root).expanduser()
    state = load_state(project)
    stage_contracts = [lint(project, stage) for stage in STAGES]
    checks = {
        "clean_state_present": {"complete": (base / "goal_state.json").exists()},
        "dependency_scan": dependency_scan(skill_root),
        "python_compile": py_compile(skill_root),
        "papernexus_config_transport": mcp_config_probe(base / "capabilities.json"),
        "stage_contracts": stage_contracts,
        "specialized_linters": specialized_linters(project, skill_root),
    }
    summary = validation_summary(checks)
    result = {
        "schema_version": 1,
        "created_at": now(),
        "project_root": project,
        "goal_state": state,
        "summary": summary,
        "checks": checks,
    }
    out = Path(args.output).expanduser()
    if not out.is_absolute():
        out = base / out
    write_json(out, result)
    print(json.dumps({"ok": summary["complete"], "path": str(out), "validation": result}, indent=2, ensure_ascii=False))
    if not summary["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
