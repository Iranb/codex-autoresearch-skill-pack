#!/usr/bin/env python3
"""Deterministic paper-integrity forensic lint for AutoResearch manuscripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any

import paper_claim_ledger


READY = {"ready", "complete", "completed", "pass", "passed", "verified"}
SEVERITY_ORDER = {"info": 0, "minor": 1, "major": 2, "critical": 3}
SURFACE_RESIDUES = [
    "as an ai language model",
    "as a large language model",
    "as an ai assistant",
    "i'm sorry, but i cannot",
    "i cannot fulfill",
    "regenerate response",
    "[citation needed]",
    "lorem ipsum",
    "<your text here>",
    "[insert ",
    "<insert ",
    "todo: cite",
]
AIS_DEFENSIVE_PATTERNS = [
    "we do not claim",
    "we make no claim",
    "we cannot claim",
    "this does not mean",
    "not intended to",
    "we acknowledge that",
    "it is important to note",
    "we are not suggesting",
]
HEADLINE_SECTIONS = {"abstract", "introduction", "conclusion"}
METRIC_TERMS = {
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


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def file_sha1(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def workflow_scope(base: Path) -> dict[str, Any]:
    state = read_json(base / "goal_state.json", {}) or {}
    policy = read_json(base / "autopilot_policy.json", {}) or {}
    goal_type = str(state.get("goal_type") or policy.get("goal_type") or "paper_producing_top_tier").strip()
    claim_mode = str(state.get("claim_mode") or policy.get("claim_mode") or "strong_paper_claims").strip()
    return {
        "goal_type": goal_type,
        "claim_mode": claim_mode,
        "paper_forensics_minor_blocks": bool(policy.get("paper_forensics_minor_blocks") is True),
    }


def strong_required(scope: dict[str, Any]) -> bool:
    return scope.get("goal_type") == "paper_producing_top_tier" and scope.get("claim_mode") == "strong_paper_claims"


def flatten_numbers(payload: Any) -> set[float]:
    numbers: set[float] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            numbers.update(flatten_numbers(value))
    elif isinstance(payload, list):
        for value in payload:
            numbers.update(flatten_numbers(value))
    elif isinstance(payload, (int, float)) and not isinstance(payload, bool):
        if math.isfinite(float(payload)):
            numbers.add(round(float(payload), 3))
            numbers.add(round(float(payload), 1))
    elif isinstance(payload, str):
        for match in re.finditer(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", payload):
            try:
                value = float(match.group(0))
            except ValueError:
                continue
            numbers.add(round(value, 3))
            numbers.add(round(value, 1))
    return numbers


def collect_input_hashes(base: Path, ledger: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    source_files = ledger.get("source_files") if isinstance(ledger.get("source_files"), list) else []
    for source in source_files:
        if not isinstance(source, dict):
            continue
        path = str(source.get("path") or "").strip()
        sha1 = str(source.get("sha1") or "").strip()
        if path and sha1:
            hashes[path] = sha1
    if "paper/main.tex" not in hashes and ledger.get("source_hash"):
        hashes["paper/main.tex"] = str(ledger.get("source_hash"))
    for rel in ["analyzer/SCORE_VERIFICATION.json", "goal_state.json", "autopilot_policy.json"]:
        digest = file_sha1(base / rel)
        if digest:
            hashes[rel] = digest
    return hashes


def deterministic_finding_hash(finding: dict[str, Any]) -> str:
    evidence_payload: list[Any] = []
    evidence = finding.get("evidence") if isinstance(finding.get("evidence"), list) else []
    for item in evidence:
        if isinstance(item, dict):
            evidence_payload.append(
                {
                    key: item.get(key)
                    for key in ["claim_id", "evidence_hash", "location", "path"]
                    if key in item
                }
            )
        else:
            evidence_payload.append(item)
    payload = {
        "family": finding.get("family"),
        "check_id": finding.get("check_id"),
        "final_severity": finding.get("final_severity"),
        "zero_weight": finding.get("zero_weight"),
        "false_positive_risk": finding.get("false_positive_risk"),
        "downgrade_reason": finding.get("downgrade_reason"),
        "message": finding.get("message"),
        "evidence": evidence_payload,
    }
    return hashlib.sha1(stable_json(payload).encode("utf-8")).hexdigest()[:16]


def make_finding(
    findings: list[dict[str, Any]],
    family: str,
    check_id: str,
    severity: str,
    message: str,
    evidence: list[dict[str, Any]],
    recommendation: str,
    false_positive_risk: str = "low",
    zero_weight: bool = False,
) -> None:
    finding = {
        "finding_id": f"F{len(findings) + 1:04d}",
        "family": family,
        "check_id": check_id,
        "severity": severity,
        "final_severity": "info" if zero_weight else severity,
        "zero_weight": zero_weight,
        "false_positive_risk": false_positive_risk,
        "message": message,
        "evidence": evidence,
        "recommendation": recommendation,
    }
    if false_positive_risk == "high" and not zero_weight and SEVERITY_ORDER.get(finding["final_severity"], 0) > 1:
        finding["final_severity"] = "minor"
        finding["downgrade_reason"] = "high false-positive risk"
    finding["finding_hash"] = deterministic_finding_hash(finding)
    findings.append(finding)


def claim_evidence(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": claim.get("claim_id"),
        "location": claim.get("location"),
        "text_span": claim.get("text_span"),
        "evidence_hash": claim.get("evidence_hash"),
    }


def number_value(claim: dict[str, Any]) -> float | None:
    value = claim.get("value")
    if not isinstance(value, dict):
        return None
    raw = value.get("value")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    return None


def number_unit(claim: dict[str, Any]) -> str:
    value = claim.get("value")
    if not isinstance(value, dict):
        return ""
    return str(value.get("unit") or "")


def section_kind(claim: dict[str, Any]) -> str:
    loc = claim.get("location") if isinstance(claim.get("location"), dict) else {}
    return normalized(loc.get("section"))


def metric_hint(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in METRIC_TERMS)


def check_relative_arithmetic(claims: list[dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    pattern = re.compile(
        r"from\s+(?P<start>[-+]?\d+(?:\.\d+)?)\s*(?P<sunit>%|\\%)?\s+to\s+"
        r"(?P<end>[-+]?\d+(?:\.\d+)?)\s*(?P<eunit>%|\\%)?.{0,120}?"
        r"(?P<stated>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>%|\\%|pp|points?)?\s+"
        r"(?P<kind>relative\s+)?(?P<word>improvement|increase|gain|boost|reduction|drop)",
        re.IGNORECASE,
    )
    seen_text: set[str] = set()
    for claim in claims:
        if claim.get("type") != "surface_text":
            continue
        text = str(claim.get("text_span") or "")
        key = normalized(text)
        if key in seen_text:
            continue
        seen_text.add(key)
        for match in pattern.finditer(text):
            start = float(match.group("start"))
            end = float(match.group("end"))
            stated = float(match.group("stated"))
            unit = (match.group("unit") or "").replace("\\%", "%").lower()
            word = match.group("word").lower()
            is_relative = bool(match.group("kind")) or unit == "%"
            direction = -1 if word in {"reduction", "drop"} else 1
            if is_relative:
                denom = abs(start)
                if denom <= 1e-12:
                    continue
                expected = direction * (end - start) / denom * 100.0
            else:
                expected = direction * (end - start)
            tolerance = max(0.5, abs(expected) * 0.02)
            if abs(stated - expected) > tolerance:
                make_finding(
                    findings,
                    "numeric_consistency",
                    "NUMERIC-RELATIVE-ARITHMETIC",
                    "major",
                    f"Stated {stated:g}{unit or ''} {word} does not match recomputed {expected:.2f}{unit or ''}.",
                    [claim_evidence(claim)],
                    "Fix the arithmetic, clarify whether the claim is absolute points or relative percent, or downgrade the claim.",
                )


def check_headline_numbers(
    claims: list[dict[str, Any]],
    score_numbers: set[float],
    findings: list[dict[str, Any]],
) -> None:
    table_numbers = {
        round(value, precision)
        for claim in claims
        if claim.get("type") == "table_cell"
        for value in [number_value(claim)]
        if value is not None
        for precision in (1, 3)
    }
    supported = set(table_numbers) | set(score_numbers)
    for claim in claims:
        if claim.get("type") != "number":
            continue
        section = section_kind(claim)
        if section not in HEADLINE_SECTIONS:
            continue
        text = str(claim.get("text_span") or "")
        value = number_value(claim)
        if value is None:
            continue
        if number_unit(claim) not in {"%", "\\%", "pp"} and not metric_hint(text):
            continue
        if re.search(r"\b(?:year|epoch|gpu|seed|section|figure|table)\b", text, re.IGNORECASE):
            continue
        if round(value, 1) in supported or round(value, 3) in supported:
            continue
        make_finding(
            findings,
            "numeric_consistency",
            "NUMERIC-HEADLINE-NOT-BACKED",
            "minor",
            f"Headline number {value:g}{number_unit(claim)} is not found in table cells or SCORE_VERIFICATION.",
            [claim_evidence(claim)],
            "Add the supporting table/result artifact, revise the number, or make the number explicitly qualitative/background.",
            false_positive_risk="medium",
        )


def decimals(value_text: str) -> int:
    if "." not in value_text:
        return 0
    return len(value_text.split(".", 1)[1])


def check_grim(claims: list[dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    percent_re = re.compile(r"(?P<pct>\d+(?:\.\d+)?)\s*(?:%|\\%)")
    n_re = re.compile(r"\b[Nn]\s*=\s*(?P<n>\d+)\b")
    skip_re = re.compile(r"\b(mean|average|macro|micro|across|folds?|seeds?|runs?|batches?)\b", re.IGNORECASE)
    seen_text: set[str] = set()
    for claim in claims:
        if claim.get("type") != "surface_text":
            continue
        text = str(claim.get("text_span") or "")
        key = normalized(text)
        if key in seen_text:
            continue
        seen_text.add(key)
        n_match = n_re.search(text)
        if not n_match or skip_re.search(text):
            continue
        n = int(n_match.group("n"))
        if n <= 0 or n > 1000:
            continue
        for pct_match in percent_re.finditer(text):
            pct_text = pct_match.group("pct")
            pct = float(pct_text)
            if not (0 <= pct <= 100):
                continue
            count = pct * n / 100.0
            rounded_count = round(count)
            implied_pct = rounded_count / n * 100.0
            tolerance = 0.5 * (10 ** -decimals(pct_text))
            if abs(implied_pct - pct) > tolerance + 1e-9:
                make_finding(
                    findings,
                    "statistical_consistency",
                    "STAT-GRIM-IMPOSSIBLE-PERCENT",
                    "major",
                    f"{pct:g}% cannot be produced by an integer count over N={n}.",
                    [claim_evidence(claim)],
                    "Check the numerator/denominator, change the reported precision, or state that the value is not a single integer-count proportion.",
                )


def check_impossible_variance(claims: list[dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    pattern = re.compile(
        r"(?P<mean>\d+(?:\.\d+)?)\s*(?:%|\\%)\s*(?:\\pm|\+/-|\+-)\s*"
        r"(?P<spread>\d+(?:\.\d+)?)\s*(?:%|\\%)",
        re.IGNORECASE,
    )
    for claim in claims:
        text = str(claim.get("text_span") or "")
        if not re.search(r"\b(sd|std|standard deviation)\b", text, re.IGNORECASE):
            continue
        for match in pattern.finditer(text):
            mean = float(match.group("mean"))
            spread = float(match.group("spread"))
            if mean - spread < -1e-9 or mean + spread > 100 + 1e-9:
                make_finding(
                    findings,
                    "statistical_consistency",
                    "STAT-IMPOSSIBLE-BOUNDED-SD",
                    "major",
                    f"Reported mean {mean:g}% with SD {spread:g}% exceeds a bounded [0, 100] percent range.",
                    [claim_evidence(claim)],
                    "Check whether the spread is SD, standard error, confidence interval, or a value in percentage points; revise the notation.",
                    false_positive_risk="medium",
                )


def check_p_values(claims: list[dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    pattern = re.compile(
        r"\bz\s*=\s*(?P<z>[-+]?\d+(?:\.\d+)?).{0,80}?\bp\s*(?P<op><=|>=|<|>|=)\s*(?P<p>0?\.\d+|\d*\.\d+)",
        re.IGNORECASE,
    )
    normal = NormalDist()
    seen_text: set[str] = set()
    for claim in claims:
        if claim.get("type") != "surface_text":
            continue
        text = str(claim.get("text_span") or "")
        key = normalized(text)
        if key in seen_text:
            continue
        seen_text.add(key)
        for match in pattern.finditer(text):
            z = abs(float(match.group("z")))
            reported = float(match.group("p"))
            computed = 2 * (1 - normal.cdf(z))
            op = match.group("op")
            inconsistent = False
            if op in {"=", "<=", ">="} and abs(reported - computed) > 0.02 and (reported < 0.05) != (computed < 0.05):
                inconsistent = True
            elif op == "<" and computed >= reported + 0.01:
                inconsistent = True
            elif op == ">" and computed <= reported - 0.01:
                inconsistent = True
            if inconsistent:
                make_finding(
                    findings,
                    "statistical_consistency",
                    "STAT-Z-PVALUE-MISMATCH",
                    "major",
                    f"Reported p {op} {reported:g} is inconsistent with two-sided z={z:g} (computed p={computed:.3f}).",
                    [claim_evidence(claim)],
                    "Check the test statistic, one-sided/two-sided convention, and reported p-value.",
                    false_positive_risk="medium",
                )


def check_surface_residue(claims: list[dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    for claim in claims:
        if claim.get("type") not in {"surface_text", "caption"}:
            continue
        text = str(claim.get("text_span") or "")
        lowered = text.lower()
        for phrase in SURFACE_RESIDUES:
            if phrase in lowered:
                make_finding(
                    findings,
                    "presentation_residue",
                    "PRESENTATION-EXACT-RESIDUE",
                    "major",
                    f"Exact presentation/template residue found: {phrase!r}. This is not an AI-authorship verdict.",
                    [claim_evidence(claim)],
                    "Remove the template or pipeline residue and inspect nearby generated text for unresolved placeholders.",
                )


def check_duplicate_tables(claims: list[dict[str, Any]], findings: list[dict[str, Any]]) -> None:
    rows: dict[str, list[str]] = defaultdict(list)
    evidence_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        if claim.get("type") != "table_cell":
            continue
        loc = claim.get("location") if isinstance(claim.get("location"), dict) else {}
        table_id = str(loc.get("table_id") or "unknown")
        value = number_value(claim)
        if value is not None:
            rows[table_id].append(f"{value:.4g}")
        if len(evidence_by_table[table_id]) < 2:
            evidence_by_table[table_id].append(claim_evidence(claim))
    signatures: dict[str, list[str]] = defaultdict(list)
    for table_id, values in rows.items():
        if len(values) >= 3:
            signatures["|".join(values)].append(table_id)
    for signature, table_ids in signatures.items():
        if len(table_ids) > 1:
            evidence = []
            for table_id in table_ids[:3]:
                evidence.extend(evidence_by_table[table_id][:1])
            make_finding(
                findings,
                "presentation_residue",
                "PRESENTATION-DUPLICATE-TABLE-SIGNATURE",
                "minor",
                f"Duplicate numeric table signature appears in tables {', '.join(table_ids)}.",
                evidence,
                "Confirm that the duplicate table is intentional; otherwise update/remove the copied table.",
                false_positive_risk="medium",
            )


def build_ais_impressions(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    impressions: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        if claim.get("type") != "surface_text":
            continue
        section = section_kind(claim)
        if section in {"acknowledgments", "acknowledgements", "references"}:
            continue
        lowered = str(claim.get("text_span") or "").lower()
        for pattern in AIS_DEFENSIVE_PATTERNS:
            if pattern in lowered:
                counts[pattern] += 1
                if len(evidence[pattern]) < 3:
                    evidence[pattern].append(claim_evidence(claim))
    for pattern, count in sorted(counts.items()):
        impressions.append(
            {
                "impression_id": f"AIS{len(impressions) + 1:04d}",
                "track": "AIS_style_impression",
                "pattern": pattern,
                "count": count,
                "zero_weight": True,
                "verdict_weight": 0,
                "message": "Defensive hedge/style cue for writing repair only; not an AI-authorship or integrity verdict.",
                "evidence": evidence[pattern],
            }
        )
    return impressions


def render_report_md(report: dict[str, Any], findings: list[dict[str, Any]], ais: list[dict[str, Any]]) -> str:
    lines = [
        "# Paper Forensics Report",
        "",
        f"- Status: {report['status']}",
        f"- Overall verdict: {report['overall_verdict']}",
        f"- Blocking findings: {len(report['blocking_findings'])}",
        f"- AIS style impressions: {len(ais)} (zero verdict weight)",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No deterministic forensic findings.")
    for finding in findings:
        lines.extend(
            [
                f"### {finding['finding_id']} {finding['check_id']}",
                "",
                f"- Family: {finding['family']}",
                f"- Severity: {finding['final_severity']}",
                f"- Finding hash: {finding['finding_hash']}",
                f"- Zero weight: {finding['zero_weight']}",
                f"- Message: {finding['message']}",
                f"- Recommendation: {finding['recommendation']}",
                "",
            ]
        )
    if ais:
        lines.extend(["## AIS Style Impressions", "", "These impressions are zero-weight and never imply AI authorship."])
        for item in ais:
            lines.append(f"- {item['impression_id']}: {item['pattern']} ({item['count']})")
    lines.append("")
    return "\n".join(lines)


def run(project: str, stage: str, out_dir: str | None = None) -> dict[str, Any]:
    base = ar(project)
    paper_dir = Path(out_dir).expanduser() if out_dir else base / "paper"
    scope = workflow_scope(base)
    required = strong_required(scope)

    ledger = paper_claim_ledger.build(project)
    write_json(paper_dir / "PAPER_CLAIM_LEDGER.json", ledger)
    claims = ledger.get("claims") if isinstance(ledger.get("claims"), list) else []

    findings: list[dict[str, Any]] = []
    if not ledger.get("complete"):
        make_finding(
            findings,
            "observability",
            "OBS-MISSING-MAIN-TEX",
            "major",
            "paper/main.tex is missing or empty, so manuscript-level forensic checks cannot run.",
            [{"path": "paper/main.tex"}],
            "Produce a manuscript source file before passing writing or submission readiness.",
        )
    else:
        score_numbers = flatten_numbers(read_json(base / "analyzer/SCORE_VERIFICATION.json", {}))
        check_relative_arithmetic(claims, findings)
        check_headline_numbers(claims, score_numbers, findings)
        check_grim(claims, findings)
        check_impossible_variance(claims, findings)
        check_p_values(claims, findings)
        check_surface_residue(claims, findings)
        check_duplicate_tables(claims, findings)

    ais = build_ais_impressions(claims)
    write_json(paper_dir / "AIS_STYLE_IMPRESSIONS.json", {"schema_version": 1, "zero_weight": True, "impressions": ais})

    blocks_minor = bool(scope.get("paper_forensics_minor_blocks"))
    blocking_findings = [
        finding
        for finding in findings
        if not finding.get("zero_weight")
        and (
            SEVERITY_ORDER.get(str(finding.get("final_severity") or "info"), 0) >= SEVERITY_ORDER["major"]
            or (blocks_minor and finding.get("final_severity") == "minor")
        )
    ]
    warning_findings = [finding for finding in findings if finding not in blocking_findings]
    if not required:
        warning_findings = findings
        blocking_findings = []

    missing = [
        f"{finding['check_id']}: {finding['message']}"
        for finding in blocking_findings
    ]
    warnings = [
        f"{finding['check_id']}: {finding['message']}"
        for finding in warning_findings
        if not finding.get("zero_weight")
    ]
    if not required and findings:
        warnings.append("paper_forensics_lint findings are scoped as warnings because this project is not strong-paper mode")
    if ais:
        warnings.append("AIS style impressions recorded with zero verdict weight")

    complete = required is False or not missing
    downgrade_counter = Counter(
        str(finding.get("downgrade_reason"))
        for finding in findings
        if finding.get("downgrade_reason")
    )
    report = {
        "schema_version": 1,
        "generated_at": now(),
        "stage": stage,
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "overall_verdict": "pass" if complete and not findings else ("warn" if complete else "blocked"),
        "required": required,
        "scope": scope,
        "observability_level": ledger.get("observability_level", "L0"),
        "input_hashes": collect_input_hashes(base, ledger),
        "finding_counts": Counter(str(finding.get("final_severity") or "info") for finding in findings),
        "finding_hashes": [str(finding.get("finding_hash") or "") for finding in findings],
        "downgraded_counts": {
            "total": sum(downgrade_counter.values()),
            "by_reason": dict(downgrade_counter),
        },
        "blocking_findings": [finding["finding_id"] for finding in blocking_findings],
        "warnings": warnings,
        "missing": missing,
        "ais_count": len(ais),
        "artifacts": {
            "ledger": "paper/PAPER_CLAIM_LEDGER.json",
            "findings": "paper/PAPER_FORENSICS_FINDINGS.json",
            "report_json": "paper/PAPER_FORENSICS_REPORT.json",
            "report_md": "paper/PAPER_FORENSICS_REPORT.md",
            "ais_style": "paper/AIS_STYLE_IMPRESSIONS.json",
        },
    }
    report["finding_counts"] = dict(report["finding_counts"])
    findings_payload = {"schema_version": 1, "stage": stage, "findings": findings}
    write_json(paper_dir / "PAPER_FORENSICS_FINDINGS.json", findings_payload)
    write_json(paper_dir / "PAPER_FORENSICS_REPORT.json", report)
    write_text(paper_dir / "PAPER_FORENSICS_REPORT.md", render_report_md(report, findings, ais))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--stage", default="writing")
    parser.add_argument("--out-dir")
    args = parser.parse_args()
    report = run(args.project, args.stage, args.out_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
