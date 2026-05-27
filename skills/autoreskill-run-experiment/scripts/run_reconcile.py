#!/usr/bin/env python3
"""Record local/remote experiment run metadata and reconcile ledgers."""

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


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
    parser.add_argument("--backend", choices=["local", "ssh", "autodl", "bjtu_hpc", "manual"], default="local")
    parser.add_argument("--status", choices=["queued", "running", "completed", "failed"], default="completed")
    parser.add_argument("--fixture-result", action="store_true")
    args = parser.parse_args()
    base = ar(args.project)
    experiments = list(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json"))
    if not experiments:
        raise SystemExit("no EXPERIMENT_MANIFEST.json found")
    ledger_entries = []
    for manifest_path in experiments:
        manifest = read_json(manifest_path, {})
        exp_dir = manifest_path.parent
        remote = {
            "schema_version": 1,
            "created_at": now(),
            "backend": args.backend,
            "status": args.status,
            "track_id": manifest.get("track_id"),
            "experiment_id": manifest.get("experiment_id"),
            "command": "fixture/manual reconcile" if args.fixture_result else "recorded external command required",
            "protocol_locked": True,
            "metric": manifest.get("primary_metric"),
            "dataset": manifest.get("dataset"),
        }
        write_json(exp_dir / "REMOTE_RUN.json", remote)
        if args.fixture_result:
            write_json(exp_dir / "results/metrics.json", {"primary_metric": 0.0, "baseline": 0.0, "proposed": 0.0, "fixture": True})
        ledger_entries.append({"manifest": str(manifest_path.relative_to(base)), "remote_run": str((exp_dir / "REMOTE_RUN.json").relative_to(base)), "status": args.status})
    ledger = {"schema_version": 1, "created_at": now(), "ready_for_analysis": args.status == "completed", "entries": ledger_entries}
    write_json(base / "coder/EXPERIMENT_LEDGER.json", ledger)
    write_text(base / "coder/EXPERIMENT_INDEX.md", "# Experiment Index\n\n" + "\n".join(f"- `{row['manifest']}` status `{row['status']}`" for row in ledger_entries) + "\n")
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "experiment", "action": "run_reconcile", "details": {"backend": args.backend, "status": args.status, "count": len(ledger_entries)}})
    print(json.dumps({"ok": True, "ledger": "coder/EXPERIMENT_LEDGER.json", "count": len(ledger_entries)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
