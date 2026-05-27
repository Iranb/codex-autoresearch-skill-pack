#!/usr/bin/env python3
"""Run a deterministic Professor/Postdoc/PhDStudent/Critic panel scaffold."""

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


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                item = {"raw_text": line}
            if isinstance(item, dict):
                out.append(item)
    return out


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
    parser.add_argument("--force-ready", action="store_true", help="allow a ready contract from existing evidence")
    args = parser.parse_args()
    base = ar(args.project)
    evidence = rows(base / "evidence_cart.jsonl")
    evidence_ids = [row.get("evidence_id") for row in evidence if row.get("evidence_id")]
    status = "advance" if evidence_ids else "park"
    candidate = {
        "track_id": "track_001",
        "title": "Evidence-bound candidate direction",
        "status": status if status != "advance" else "advance_with_constraints",
        "evidence_ids": evidence_ids,
        "weakest_assumption": "The transfer mechanism improves the primary metric under the fixed protocol.",
        "falsifier": "A baseline-matched pilot shows no improvement or worse robustness.",
        "panel_scores": {
            "Professor": "significance requires graph-grounded novelty evidence",
            "Postdoc": "feasible only after a dry-runable experiment bundle",
            "PhDStudent": "prior-art risk must be checked against negative evidence",
            "Critic": "downgrade if evidence remains discovery-only",
        },
    }
    write_json(base / "ideation/CANDIDATE_POOL.json", {"schema_version": 1, "created_at": now(), "candidates": [candidate]})
    write_json(base / "ideation/TOURNAMENT_SCOREBOARD.json", {"schema_version": 1, "created_at": now(), "tracks": [candidate]})
    write_json(base / "reviewer/IDEA_GATE_REVIEW.json", {"schema_version": 1, "created_at": now(), "status": "ready" if evidence_ids else "blocked", "issues": [] if evidence_ids else [{"severity": "high", "status": "open", "message": "No evidence ids"}]})
    write_text(base / "ideation/TOP3_DIRECTION_SUMMARY.md", "# Top Directions\n\n- track_001: evidence-bound candidate direction\n")
    write_text(base / "ideation/WELL_ESTABLISHED_SOLUTION_CHECK.md", "Status: open_with_constraints\n")
    if args.force_ready and evidence_ids:
        write_json(base / "ideation/idea-catalyst/IDEA_CATALYST_CONTRACT.json", {"schema_version": 1, "created_at": now(), "status": "ready", "selected_idea_fragment_id": "track_001", "evidence_ids": evidence_ids})
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "idea_gate", "action": "panel_review", "details": {"evidence_count": len(evidence_ids), "status": status}})
    print(json.dumps({"ok": True, "candidate": candidate}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
