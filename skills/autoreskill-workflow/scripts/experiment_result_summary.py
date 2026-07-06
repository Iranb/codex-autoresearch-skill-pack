#!/usr/bin/env python3
"""Build compact experiment trajectory, best-so-far, and final-result artifacts.

The parser intentionally targets the common AutoResearch metric-log shape:

    Train Accuracies: All 0.1234 | Old 0.2345 | New 0.3456
    Test Accuracies: All 0.1234 | Old 0.2345 | New 0.3456

It writes small JSON/CSV artifacts only. Raw logs, checkpoints, datasets, and
model weights remain outside git-managed result summaries.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METRICS = ("all", "old", "new")
TRAIN_RE = re.compile(
    r"^(?P<time>\S+ \S+).*Train Accuracies: All (?P<all>[0-9.]+) \| Old (?P<old>[0-9.]+) \| New (?P<new>[0-9.]+)"
)
TEST_RE = re.compile(
    r"^(?P<time>\S+ \S+).*Test Accuracies: All (?P<all>[0-9.]+) \| Old (?P<old>[0-9.]+) \| New (?P<new>[0-9.]+)"
)


@dataclass
class RunSpec:
    role: str
    tag: str
    log: Path
    status: str


def metric_dict(match: re.Match[str]) -> dict[str, float]:
    return {key: float(match.group(key)) for key in METRICS}


def parse_log(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    seen: set[tuple[Any, ...]] = set()
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            train_match = TRAIN_RE.search(line)
            if train_match:
                pending = {"time": train_match.group("time"), "metrics": metric_dict(train_match)}
                continue
            test_match = TEST_RE.search(line)
            if not test_match or pending is None:
                continue
            key = (
                pending["time"],
                test_match.group("time"),
                tuple(pending["metrics"][metric] for metric in METRICS),
                tuple(metric_dict(test_match)[metric] for metric in METRICS),
            )
            if key in seen:
                pending = None
                continue
            seen.add(key)
            rows.append(
                {
                    "count": len(rows) + 1,
                    "train_time": pending["time"],
                    "test_time": test_match.group("time"),
                    "train": pending["metrics"],
                    "test": metric_dict(test_match),
                }
            )
            pending = None
    return rows


def best_by_metric(rows: list[dict[str, Any]], split: str = "test") -> dict[str, Any]:
    best: dict[str, Any] = {}
    for metric in METRICS:
        if not rows:
            best[metric] = None
            continue
        row = max(rows, key=lambda item: float(item[split][metric]))
        best[metric] = {
            "count": row["count"],
            "time": row[f"{split}_time"],
            "value": row[split][metric],
            "all": row[split]["all"],
            "old": row[split]["old"],
            "new": row[split]["new"],
        }
    return best


def run_summary(spec: RunSpec, rows: list[dict[str, Any]], primary_metric: str) -> dict[str, Any]:
    final = rows[-1] if rows else None
    best = best_by_metric(rows, "test")
    return {
        "role": spec.role,
        "run_tag": spec.tag,
        "status": spec.status,
        "source_log_path": str(spec.log),
        "metric_count": len(rows),
        "final_metric": final,
        "best_so_far": {
            "split": "test",
            "primary_metric": primary_metric,
            "primary_metric_best": best.get(primary_metric),
            "by_metric": best,
        },
    }


def paired_rows(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    count_max = min(len(baseline_rows), len(candidate_rows))
    for idx in range(count_max):
        baseline = baseline_rows[idx]
        candidate = candidate_rows[idx]
        delta = {metric: round(candidate["test"][metric] - baseline["test"][metric], 6) for metric in METRICS}
        rows.append(
            {
                "count": idx + 1,
                "baseline": baseline,
                "candidate": candidate,
                "delta_candidate_minus_baseline": {"test": delta},
            }
        )
    return rows


def paired_summary(rows: list[dict[str, Any]], primary_metric: str) -> dict[str, Any]:
    best_delta: dict[str, Any] = {}
    for metric in METRICS:
        if not rows:
            best_delta[metric] = None
            continue
        row = max(rows, key=lambda item: float(item["delta_candidate_minus_baseline"]["test"][metric]))
        best_delta[metric] = {
            "count": row["count"],
            "value": row["delta_candidate_minus_baseline"]["test"][metric],
            "baseline": row["baseline"]["test"],
            "candidate": row["candidate"]["test"],
        }
    return {
        "paired_metric_count": len(rows),
        "latest_paired": rows[-1] if rows else None,
        "best_delta_so_far": {
            "split": "test",
            "primary_metric": primary_metric,
            "primary_metric_best_delta": best_delta.get(primary_metric),
            "by_metric": best_delta,
        },
    }


def write_csv(path: Path, paired: list[dict[str, Any]], candidate_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "count",
                "baseline_all",
                "baseline_old",
                "baseline_new",
                "candidate_all",
                "candidate_old",
                "candidate_new",
                "delta_all",
                "delta_old",
                "delta_new",
                "candidate_test_time",
            ]
        )
        if paired:
            for row in paired:
                baseline = row["baseline"]["test"]
                candidate = row["candidate"]["test"]
                delta = row["delta_candidate_minus_baseline"]["test"]
                writer.writerow(
                    [
                        row["count"],
                        f"{baseline['all']:.6f}",
                        f"{baseline['old']:.6f}",
                        f"{baseline['new']:.6f}",
                        f"{candidate['all']:.6f}",
                        f"{candidate['old']:.6f}",
                        f"{candidate['new']:.6f}",
                        f"{delta['all']:.6f}",
                        f"{delta['old']:.6f}",
                        f"{delta['new']:.6f}",
                        row["candidate"]["test_time"],
                    ]
                )
            return
        for row in candidate_rows:
            candidate = row["test"]
            writer.writerow(
                [
                    row["count"],
                    "",
                    "",
                    "",
                    f"{candidate['all']:.6f}",
                    f"{candidate['old']:.6f}",
                    f"{candidate['new']:.6f}",
                    "",
                    "",
                    "",
                    row["test_time"],
                ]
            )


def build_payload(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    candidate = RunSpec("candidate", args.candidate_tag, args.candidate_log, args.candidate_status)
    candidate_rows = parse_log(candidate.log)
    runs = {"candidate": run_summary(candidate, candidate_rows, args.primary_metric)}
    paired: list[dict[str, Any]] = []
    if args.baseline_log:
        baseline = RunSpec("baseline", args.baseline_tag or "baseline", args.baseline_log, args.baseline_status)
        baseline_rows = parse_log(baseline.log)
        runs["baseline"] = run_summary(baseline, baseline_rows, args.primary_metric)
        paired = paired_rows(baseline_rows, candidate_rows)
    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset": args.dataset,
        "method_family": args.method_family,
        "backbone": args.backbone,
        "primary_metric": args.primary_metric,
        "metric_suite": list(METRICS),
        "runs": runs,
        "same_count_comparison": paired_summary(paired, args.primary_metric) if args.baseline_log else None,
        "trajectory_csv_path": str(args.out_csv),
        "artifact_policy": "small JSON/CSV result summary only; raw logs/checkpoints/datasets/model weights are not embedded",
    }
    return payload, paired, candidate_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-log", type=Path, required=True)
    parser.add_argument("--candidate-tag", required=True)
    parser.add_argument("--candidate-status", default="active_or_unknown")
    parser.add_argument("--baseline-log", type=Path)
    parser.add_argument("--baseline-tag")
    parser.add_argument("--baseline-status", default="active_or_unknown")
    parser.add_argument("--dataset", default="")
    parser.add_argument("--method-family", default="")
    parser.add_argument("--backbone", default="")
    parser.add_argument("--primary-metric", choices=METRICS, default="all")
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args()

    payload, paired, candidate_rows = build_payload(args)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(args.out_csv, paired, candidate_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
