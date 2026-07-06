#!/usr/bin/env python3
"""Build a deterministic manuscript claim ledger for AutoResearch papers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|\\%|pp|x)?")
SECTION_RE = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{([^{}]+)\}")
CITE_RE = re.compile(r"\\cite\w*\{([^{}]+)\}")
CAPTION_RE = re.compile(r"\\caption(?:\[[^\]]*\])?\{([^{}]+)\}")
STAT_CUES = re.compile(
    r"\b(?:p\s*[<=>]|z\s*=|t\s*=|f\s*=|chi|n\s*=|sd|std|standard deviation|variance|grim)\b|\\pm|\+/-",
    re.IGNORECASE,
)
SCOPE_CUES = re.compile(
    r"\b(?:limitation|scope|assumption|we do not claim|does not imply|pilot|preliminary|future work|not intended)\b",
    re.IGNORECASE,
)
METRIC_WORDS = {
    "accuracy",
    "acc",
    "auc",
    "f1",
    "precision",
    "recall",
    "error",
    "loss",
    "success",
    "rate",
    "score",
    "miou",
    "map",
}


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def clean_latex(text: str) -> str:
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = text.replace("~", " ")
    text = re.sub(r"\\(?:textbf|emph|textit|mathbf|mathrm)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def evidence_hash(kind: str, location: dict[str, Any], text: str) -> str:
    basis = json.dumps(
        {"kind": kind, "location": location, "text": normalize_text(text)},
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def metric_from_context(text: str) -> str | None:
    lowered = text.lower()
    for metric in sorted(METRIC_WORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(metric)}\b", lowered):
            return metric
    return None


def parse_number(token: str) -> dict[str, Any] | None:
    raw = token.strip()
    match = re.match(r"([-+]?\d+(?:,\d{3})*(?:\.\d+)?)(?:\s*(%|\\%|pp|x))?", raw)
    if not match:
        return None
    value = float(match.group(1).replace(",", ""))
    unit = match.group(2) or ""
    if unit == "\\%":
        unit = "%"
    return {"raw": raw, "value": value, "unit": unit}


def split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?;])\s+", text)
    return [piece.strip() for piece in pieces if len(piece.strip()) >= 8]


def add_claim(claims: list[dict[str, Any]], kind: str, text: str, location: dict[str, Any], **extra: Any) -> None:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return
    claim: dict[str, Any] = {
        "claim_id": f"C{len(claims) + 1:04d}",
        "type": kind,
        "text_span": text[:600],
        "location": location,
        "evidence_hash": evidence_hash(kind, location, text),
        "confidence": extra.pop("confidence", "heuristic"),
        "observability_level": extra.pop("observability_level", "L1"),
    }
    claim.update(extra)
    claims.append(claim)


def line_location(path: str, line_no: int, section: str, in_abstract: bool, table_id: str | None = None) -> dict[str, Any]:
    loc: dict[str, Any] = {
        "file": path,
        "line": line_no,
        "section": "Abstract" if in_abstract else section,
    }
    if table_id:
        loc["table_id"] = table_id
    return loc


def build(project: str) -> dict[str, Any]:
    base = ar(project)
    tex_path = base / "paper/main.tex"
    tex = read_text(tex_path)
    source_hash = hashlib.sha1(tex.encode("utf-8")).hexdigest() if tex else ""
    if not tex.strip():
        return {
            "schema_version": 1,
            "complete": False,
            "status": "missing_manuscript",
            "observability_level": "L0",
            "missing": ["paper/main.tex"],
            "source_files": [],
            "source_hash": source_hash,
            "claims": [],
        }

    claims: list[dict[str, Any]] = []
    section = "FrontMatter"
    in_abstract = False
    in_tabular = False
    table_counter = 0
    table_id: str | None = None

    for line_no, raw_line in enumerate(tex.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        if "\\begin{abstract}" in line:
            in_abstract = True
            section = "Abstract"
        if "\\end{abstract}" in line:
            in_abstract = False

        section_match = SECTION_RE.search(line)
        if section_match:
            section = clean_latex(section_match.group(1)) or section

        for caption in CAPTION_RE.findall(line):
            add_claim(
                claims,
                "caption",
                clean_latex(caption),
                line_location("paper/main.tex", line_no, section, in_abstract, table_id),
                confidence="parsed",
            )

        if "\\begin{tabular" in line:
            in_tabular = True
            table_counter += 1
            table_id = f"T{table_counter:03d}"
        if in_tabular:
            clean = clean_latex(line)
            if NUMBER_RE.search(clean):
                for number_match in NUMBER_RE.finditer(clean):
                    parsed = parse_number(number_match.group(0))
                    if not parsed:
                        continue
                    add_claim(
                        claims,
                        "table_cell",
                        clean,
                        line_location("paper/main.tex", line_no, section, in_abstract, table_id),
                        value={**parsed, "metric": metric_from_context(clean)},
                        confidence="parsed",
                    )
            if "\\end{tabular" in line:
                in_tabular = False
                table_id = None
            continue

        for cite_body in CITE_RE.findall(line):
            for key in [part.strip() for part in cite_body.split(",") if part.strip()]:
                add_claim(
                    claims,
                    "citation",
                    key,
                    line_location("paper/main.tex", line_no, section, in_abstract),
                    value={"citation_key": key},
                    confidence="parsed",
                )

        clean = clean_latex(line)
        if not clean:
            continue
        for sentence in split_sentences(clean):
            add_claim(
                claims,
                "surface_text",
                sentence,
                line_location("paper/main.tex", line_no, section, in_abstract),
                confidence="parsed",
            )
            if SCOPE_CUES.search(sentence):
                add_claim(
                    claims,
                    "scope",
                    sentence,
                    line_location("paper/main.tex", line_no, section, in_abstract),
                    confidence="heuristic",
                )
            if STAT_CUES.search(sentence):
                add_claim(
                    claims,
                    "statistical",
                    sentence,
                    line_location("paper/main.tex", line_no, section, in_abstract),
                    confidence="heuristic",
                )
            for number_match in NUMBER_RE.finditer(sentence):
                parsed = parse_number(number_match.group(0))
                if not parsed:
                    continue
                if parsed["unit"] == "" and parsed["value"] in {1, 2, 3, 4}:
                    continue
                add_claim(
                    claims,
                    "number",
                    sentence,
                    line_location("paper/main.tex", line_no, section, in_abstract),
                    value={**parsed, "metric": metric_from_context(sentence)},
                    confidence="heuristic",
                )

    return {
        "schema_version": 1,
        "complete": True,
        "status": "complete",
        "observability_level": "L1",
        "missing": [],
        "source_files": [{"path": "paper/main.tex", "sha1": source_hash, "bytes": len(tex.encode("utf-8"))}],
        "source_hash": source_hash,
        "claim_count": len(claims),
        "claims": claims,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    payload = build(args.project)
    out_path = Path(args.out).expanduser() if args.out else ar(args.project) / "paper/PAPER_CLAIM_LEDGER.json"
    write_json(out_path, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
