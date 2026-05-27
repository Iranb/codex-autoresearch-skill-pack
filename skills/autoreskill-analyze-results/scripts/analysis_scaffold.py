#!/usr/bin/env python3
"""Create claim-evidence analysis artifacts from experiment ledger."""

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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    base = ar(args.project)
    ledger = read_json(base / "coder/EXPERIMENT_LEDGER.json", {})
    if not ledger and args.strict:
        raise SystemExit("missing coder/EXPERIMENT_LEDGER.json")
    entries = ledger.get("entries", []) if isinstance(ledger, dict) else []
    lines = ["# Claim Evidence Matrix", "", "| Claim | Evidence | Verdict |", "| --- | --- | --- |"]
    if entries:
        for idx, row in enumerate(entries, 1):
            verdict = "fixture_only" if "fixture" in json.dumps(row).lower() else "supported_pending_statistics"
            lines.append(f"| claim_{idx} | `{row.get('remote_run')}` | {verdict} |")
    else:
        lines.append("| no_claim | no experiment ledger | unsupported |")
    write_text(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md", "\n".join(lines) + "\n")
    write_text(base / "analyzer/TRACK_VERDICTS.md", "# Track Verdicts\n\n- track_001: provisional; promote only with non-fixture results.\n")
    write_text(base / "analyzer/UNSUPPORTED_CLAIMS.md", "# Unsupported Claims\n\n- Strong novelty or performance claims require live PaperNexus and non-fixture experiment evidence.\n")
    write_text(base / "analyzer/NARRATIVE_REPORT.md", f"# Narrative Report\n\nCreated {now()}. Results are evidence-bound and downgrade fixture-only claims.\n")
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "analysis", "action": "analysis_scaffold", "details": {"entries": len(entries)}})
    print(json.dumps({"ok": True, "entries": len(entries)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
