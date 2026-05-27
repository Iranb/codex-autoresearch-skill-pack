#!/usr/bin/env python3
"""Create an evidence-bound LaTeX/write package scaffold."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TARGET_VENUE = "unspecified_top_tier"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--title", default="TBD Evidence-Bound AutoResearch Manuscript")
    parser.add_argument("--venue", default=DEFAULT_TARGET_VENUE)
    args = parser.parse_args()
    base = ar(args.project)
    claim_ready = nonempty(base / "analyzer/CLAIM_EVIDENCE_MATRIX.md")
    tex = rf"""\documentclass{{article}}
\title{{{args.title}}}
\author{{TBD}}
\begin{{document}}
\maketitle
\begin{{abstract}}
This draft is generated from validated AutoResearch artifacts. Strong claims are intentionally withheld until PaperNexus graph evidence, experiment proof, and review gates are complete.
\end{{abstract}}
\section{{Introduction}}
Write only claims that appear in \texttt{{.autoreskill/analyzer/CLAIM\_EVIDENCE\_MATRIX.md}}.
\section{{Methods}}
Describe the baseline-first, one-variable experiment protocol.
\section{{Results}}
Report baseline and proposed results together; downgrade fixture-only evidence.
\section{{Limitations}}
Current scaffold status: claim matrix present = {str(claim_ready).lower()}.
\end{{document}}
"""
    write_text(base / "paper/main.tex", tex)
    write_text(base / "paper/refs.bib", "% Populate from CITATION_QUEUE after citation integrity checks.\n")
    write_json(
        base / "paper/write_package.json",
        {
            "schema_version": 1,
            "created_at": now(),
            "venue": args.venue,
            "title": args.title,
            "claim_matrix_present": claim_ready,
            "status": "draft_ready" if claim_ready else "blocked_missing_claim_matrix",
            "allowed_claim_strength": "bounded" if claim_ready else "none",
        },
    )
    write_json(base / "paper/story/PAPER_STORY_STATE.json", {"schema_version": 1, "status": "draft", "created_at": now(), "claims_source": "analyzer/CLAIM_EVIDENCE_MATRIX.md"})
    append_jsonl(base / "decision_log.jsonl", {"ts": now(), "stage": "writing", "action": "paper_scaffold", "details": {"claim_matrix_present": claim_ready}})
    print(json.dumps({"ok": True, "main_tex": "paper/main.tex"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
