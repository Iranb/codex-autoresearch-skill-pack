#!/usr/bin/env python3
"""Build, lint, and materialize a non-PaperNexus idea campaign.

The validator is deliberately offline and structural. It verifies provenance
integrity, explicit scientific commitments, reviewer verdicts, and protected
hashes; it does not claim to prove semantic novelty or experimental success.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


SKILL_ROOT = Path(__file__).resolve().parents[1]
DECK_ROOT = SKILL_ROOT / "references/researchstudio-idea"
MANIFEST_PATH = DECK_ROOT / "UPSTREAM_MANIFEST.json"
PINNED_DECK_AGGREGATE_SHA256 = "1e4057c6fe2b1eb8a3b630adad3ffd96d56039ce085e82d80b8c120e9434ebb2"

CAMPAIGN_REL = Path("ideation/NON_PAPERNEXUS_IDEA_CAMPAIGN.json")
GATE_REL = Path("ideation/PRE_IDEA_EVIDENCE_GATE.json")
PANEL_REL = Path("ideation/PANEL_DESIGN_REVIEW.json")
LOCK_REL = Path("ideation/.non_papernexus_materialize.lock")
COMMITTED_REL = Path("ideation/committed")
AUTHORITY_HISTORY_REL = Path("ideation/authority_history")

LANES = {"target_domain", "near_neighbor", "far_neighbor"}
EVIDENCE_LEVELS = {"full_text", "method_section", "code", "run_log", "user_prior"}
CITABLE_METHOD_LEVELS = {"full_text", "method_section"}
UNUSABLE_FULL_TEXT_STATUSES = {"", "abstract_only", "metadata_only", "not_acquired", "unavailable", "unknown"}
UNUSABLE_VERIFICATION_STATUSES = {"", "not_checked", "unverified", "unknown"}
VERIFIED_FULL_TEXT_STATUSES = {
    "full_text_acquired",
    "method_section_acquired",
    "locally_cached_full_text",
    "user_provided_full_text",
}
VERIFIED_SOURCE_STATUSES = {
    "verified_against_source",
    "verified_against_full_text",
    "verified_against_repository",
    "locally_verified",
}
GAP_TYPES = {"additive_leaf", "subtractive_shared_assumption", "other_structural"}
CONTRIBUTION_TYPES = {"ALGO", "CODE", "PARAM"}
EXECUTION_ROUTES = {"local", "ssh", "bjtu_hpc"}
BASELINE_COMPARISON_LABELS = {
    "vs paper-reported baseline",
    "vs reproduced baseline",
    "vs matched reproduced baseline",
    "paper-report comparison not established",
}
CHECK_NAMES = (
    "gap_closure_reject_check",
    "recipe_application_check",
    "anti_pattern_check",
    "paper_pointed_threat",
    "falsification_structure_check",
)
CHECK_VERDICTS = {"pass", "revise", "abandon"}
CAMPAIGN_STATUSES = {"draft", "ready", "abandoned"}
CANDIDATE_STATUSES = {"candidate", "shortlisted", "admitted", "revised", "abandoned"}
OUTCOME_ROUTE_KEYS = {
    "valid_positive_candidate",
    "valid_negative",
    "valid_inconclusive",
    "infrastructure_failure",
    "implementation_failure",
    "protocol_invalid",
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CAMPAIGN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
FORBIDDEN_PROVENANCE_KEYS = {
    "agent_materials",
    "agent_materials_ref",
    "mcp_attempted",
    "mcp_session",
    "papernexus_session",
    "proposal_graph_session",
    "provider_session",
    "research_controller_session",
}
PROVENANCE_VALUE_KEYS = {
    "backend",
    "corpus",
    "endpoint",
    "evidence_provider",
    "material_ref",
    "provider",
    "provider_ref",
    "session_ref",
    "source_ref",
    "source_type",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def project_root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def ar_root(project: str) -> Path:
    return project_root(project) / ".autoreskill"


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def strings(value: Any) -> List[str]:
    return [str(item).strip() for item in as_list(value) if str(item).strip()]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def serialized_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )


def nonfinite_paths(value: Any, prefix: str = "campaign") -> List[str]:
    paths: List[str] = []
    if isinstance(value, float) and not math.isfinite(value):
        paths.append(prefix)
    elif isinstance(value, dict):
        for key, child in value.items():
            paths.extend(nonfinite_paths(child, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(nonfinite_paths(child, f"{prefix}[{index}]"))
    return paths


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_with_sha(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return None, None
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None
    digest = sha256_bytes(raw)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=reject_json_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None, digest
    return (value if isinstance(value, dict) else None), digest


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    value, _ = read_json_with_sha(path)
    return value


def atomic_write_json(path: Path, value: Any) -> None:
    payload = serialized_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


@contextmanager
def materialize_lock(path: Path) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def require(mapping: Dict[str, Any], fields: Sequence[str], prefix: str, errors: List[str]) -> None:
    for field in fields:
        if not present(mapping.get(field)):
            errors.append(f"{prefix}.{field}")


def non_papernexus_provider(value: Any) -> bool:
    token = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    return bool(token) and "papernexus" not in token


def contains_papernexus(value: Any) -> bool:
    return "papernexus" in re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def non_papernexus_source(mapping: Dict[str, Any]) -> bool:
    return (
        non_papernexus_provider(mapping.get("provider"))
        and not contains_papernexus(mapping.get("source_ref"))
        and not contains_papernexus(mapping.get("source_type"))
    )


def validate_provenance(value: Any, errors: List[str], path: str = "campaign") -> None:
    """Reject structured PaperNexus/session provenance without scanning free prose."""
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = re.sub(r"[^a-z0-9_]", "", key.lower())
            child_path = f"{path}.{key}"
            if not (path == "campaign" and normalized == "papernexus_used"):
                if "papernexus" in normalized or normalized in FORBIDDEN_PROVENANCE_KEYS:
                    errors.append(f"{child_path} is forbidden PaperNexus/session provenance")
                elif normalized in PROVENANCE_VALUE_KEYS and contains_papernexus(child):
                    errors.append(f"{child_path} may not reference PaperNexus")
            validate_provenance(child, errors, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_provenance(child, errors, f"{path}[{index}]")


def is_citable_verified_evidence(record: Dict[str, Any]) -> bool:
    excerpt = str(record.get("excerpt") or "")
    return (
        record.get("citable") is True
        and str(record.get("evidence_level") or "").strip() in CITABLE_METHOD_LEVELS
        and str(record.get("full_text_status") or "").strip().lower() in VERIFIED_FULL_TEXT_STATUSES
        and str(record.get("source_verification_status") or "").strip().lower() in VERIFIED_SOURCE_STATUSES
        and str(record.get("excerpt_sha256") or "").strip().lower()
        == sha256_bytes(excerpt.encode("utf-8"))
        and non_papernexus_source(record)
    )


def verify_deck() -> Dict[str, Any]:
    errors: List[str] = []
    manifest = read_json(MANIFEST_PATH)
    if not manifest:
        return {"complete": False, "errors": [f"missing or invalid {MANIFEST_PATH}"]}
    rows = manifest.get("files")
    if not isinstance(rows, list):
        return {"complete": False, "errors": ["UPSTREAM_MANIFEST.files must be a list"]}
    if len(rows) != 50:
        errors.append(f"UPSTREAM_MANIFEST.files must contain exactly 50 entries, found {len(rows)}")

    aggregate_records: List[Tuple[str, str]] = []
    expected_paths: Set[Path] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"UPSTREAM_MANIFEST.files[{index}] must be an object")
            continue
        source = str(row.get("source_path") or "").strip()
        vendored = str(row.get("vendored_path") or row.get("path") or "").strip()
        expected_sha = str(row.get("sha256") or "").strip().lower()
        if not source or not vendored or not SHA_RE.fullmatch(expected_sha):
            errors.append(f"UPSTREAM_MANIFEST.files[{index}] requires source_path, vendored_path, sha256")
            continue
        path = Path(vendored)
        if not path.is_absolute():
            path = DECK_ROOT / path
        try:
            resolved = path.resolve()
            resolved.relative_to(DECK_ROOT.resolve())
        except (OSError, ValueError):
            errors.append(f"manifest path escapes vendored deck: {vendored}")
            continue
        expected_paths.add(resolved)
        if not resolved.is_file():
            errors.append(f"missing vendored deck file: {vendored}")
        else:
            observed = sha256_file(resolved)
            if observed != expected_sha:
                errors.append(f"deck hash mismatch: {vendored}")
            size = row.get("bytes")
            if isinstance(size, int) and resolved.stat().st_size != size:
                errors.append(f"deck byte-size mismatch: {vendored}")
        aggregate_records.append((source, f"{expected_sha}  {source}\n"))

    actual_files = {
        path.resolve()
        for path in DECK_ROOT.rglob("*")
        if path.is_file() and path.resolve() != MANIFEST_PATH.resolve()
    }
    extras = sorted(str(path.relative_to(DECK_ROOT.resolve())) for path in actual_files - expected_paths)
    if extras:
        errors.append(f"unmanifested upstream deck files: {extras}")
    missing_manifested = sorted(str(path.relative_to(DECK_ROOT.resolve())) for path in expected_paths - actual_files)
    if missing_manifested:
        errors.append(f"manifested files absent: {missing_manifested}")

    aggregate = sha256_bytes("".join(line for _, line in sorted(aggregate_records)).encode("utf-8"))
    expected_aggregate = str(manifest.get("aggregate_sha256") or "").strip().lower()
    if aggregate != expected_aggregate:
        errors.append("UPSTREAM_MANIFEST aggregate_sha256 mismatch")
    if expected_aggregate != "1e4057c6fe2b1eb8a3b630adad3ffd96d56039ce085e82d80b8c120e9434ebb2":
        errors.append("UPSTREAM_MANIFEST aggregate_sha256 is not the audited pinned core deck")
    license_sha = str(manifest.get("license_sha256") or "").strip().lower()
    if license_sha != "db60a6df93f1786929a223558ca0c202ef61095600785cf7503fbcd4bac1bd02":
        errors.append("UPSTREAM_MANIFEST license_sha256 does not match the pinned MIT LICENSE")
    if str(manifest.get("license") or manifest.get("license_id") or "").strip().upper() != "MIT":
        errors.append("UPSTREAM_MANIFEST license must be MIT")
    if str(manifest.get("commit") or "") != "868f0e9c30685b72ebd475f0dada1492a1982168":
        errors.append("UPSTREAM_MANIFEST commit is not the audited pinned commit")

    return {
        "complete": not errors,
        "errors": errors,
        "file_count": len(rows),
        "aggregate_sha256": aggregate,
        "commit": manifest.get("commit"),
        "manifest_path": str(MANIFEST_PATH),
    }


def pattern_catalog() -> Tuple[Set[str], Dict[str, str], List[str]]:
    errors: List[str] = []
    main_dir = DECK_ROOT / "ideation-patterns"
    sub_dir = DECK_ROOT / "ideation-sub-patterns"
    mains = {
        path.stem
        for path in main_dir.glob("*.md")
        if path.name not in {"overview.md", "companion-combos.md"}
    }
    mapping: Dict[str, str] = {}
    overview = sub_dir / "overview.md"
    if overview.exists():
        for line in overview.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\| `(?P<sub>C\d{2})` \| `(?P<parent>[^`]+)`", line)
            if match:
                mapping[match.group("sub")] = match.group("parent")
    if len(mains) != 15:
        errors.append(f"expected 15 main patterns, found {len(mains)}")
    if len(mapping) != 31:
        errors.append(f"expected 31 subpattern mappings, found {len(mapping)}")
    for sub, parent in mapping.items():
        if parent not in mains:
            errors.append(f"subpattern {sub} references unknown parent {parent}")
        if not (sub_dir / f"{sub}.md").is_file():
            errors.append(f"missing subpattern card {sub}.md")
    return mains, mapping, errors


def protected_payload(candidate: Dict[str, Any]) -> Dict[str, Any]:
    rapid = as_dict(candidate.get("rapid_validation"))
    resource = as_dict(rapid.get("resource_request"))
    return {
        "falsifier": as_dict(candidate.get("mechanism")).get("falsifier"),
        "observable_prediction": as_dict(candidate.get("mechanism")).get("predicted_observation"),
        "load_bearing_variable": as_dict(candidate.get("mechanism")).get("load_bearing_variable"),
        "negative_control": candidate.get("negative_control"),
        "baseline": {
            "source_ref": as_dict(rapid.get("baseline_code")).get("source_ref"),
            "revision": as_dict(rapid.get("baseline_code")).get("revision"),
            "comparison_label": as_dict(rapid.get("baseline_code")).get("comparison_label"),
        },
        "dataset": rapid.get("dataset"),
        "metric_policy": rapid.get("metric_policy"),
        "resource_ceiling": {
            "compute_backend": resource.get("compute_backend"),
            "execution_route": resource.get("execution_route"),
            "gpu_count": resource.get("gpu_count"),
            "estimated_gpu_hours": resource.get("estimated_gpu_hours"),
            "walltime_minutes": resource.get("walltime_minutes"),
            "smoke_minutes": resource.get("smoke_minutes"),
        },
        "seed_policy": rapid.get("seed_policy"),
        "evidence_tier": rapid.get("evidence_tier"),
        "outcome_routes": rapid.get("outcome_routes"),
    }


def protected_digest(candidate: Dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(protected_payload(candidate)))


def validate_evidence(campaign: Dict[str, Any], errors: List[str], warnings: List[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
    records = as_list(campaign.get("evidence_records"))
    by_id: Dict[str, Dict[str, Any]] = {}
    lane_counts = {lane: 0 for lane in sorted(LANES)}
    method_bottleneck = 0
    full_anchor = 0
    for index, raw in enumerate(records):
        prefix = f"evidence_records[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(
            raw,
            [
                "id",
                "lane",
                "source_type",
                "provider",
                "source_ref",
                "title",
                "locator",
                "excerpt",
                "excerpt_sha256",
                "evidence_level",
                "full_text_status",
                "source_verification_status",
                "source_verification_limit",
                "roles",
            ],
            prefix,
            errors,
        )
        evidence_id = str(raw.get("id") or "").strip()
        if evidence_id in by_id:
            errors.append(f"{prefix}.id duplicates {evidence_id}")
        elif evidence_id:
            by_id[evidence_id] = raw
        lane = str(raw.get("lane") or "").strip()
        if lane not in LANES:
            errors.append(f"{prefix}.lane must be one of {sorted(LANES)}")
        else:
            lane_counts[lane] += 1
        if not non_papernexus_source(raw):
            errors.append(f"{prefix}.provider must be explicit and non-PaperNexus; source provenance must also be non-PaperNexus")
        excerpt = str(raw.get("excerpt") or "")
        expected = str(raw.get("excerpt_sha256") or "").strip().lower()
        if expected != sha256_bytes(excerpt.encode("utf-8")):
            errors.append(f"{prefix}.excerpt_sha256 mismatch")
        level = str(raw.get("evidence_level") or "").strip()
        if level not in EVIDENCE_LEVELS:
            errors.append(f"{prefix}.evidence_level must be one of {sorted(EVIDENCE_LEVELS)}")
        roles = set(strings(raw.get("roles")))
        citable = raw.get("citable") is True
        full_text_status = str(raw.get("full_text_status") or "").strip().lower()
        verification_status = str(raw.get("source_verification_status") or "").strip().lower()
        full_text_usable = full_text_status in VERIFIED_FULL_TEXT_STATUSES
        verification_usable = verification_status in VERIFIED_SOURCE_STATUSES
        method_source_usable = full_text_usable and verification_usable and non_papernexus_source(raw)
        if citable and level in CITABLE_METHOD_LEVELS and not full_text_usable:
            errors.append(f"{prefix} citable method/full-text evidence requires acquired full text")
        if citable and level in CITABLE_METHOD_LEVELS and not verification_usable:
            errors.append(f"{prefix} citable method/full-text evidence requires checked source verification")
        if citable and level in CITABLE_METHOD_LEVELS and method_source_usable and "bottleneck_support" in roles:
            method_bottleneck += 1
        if citable and level in CITABLE_METHOD_LEVELS and method_source_usable and "closest_anchor" in roles:
            full_anchor += 1
    for lane, count in lane_counts.items():
        if count < 1:
            errors.append(f"evidence_records requires at least one {lane} record")
    if method_bottleneck < 2:
        errors.append("at least two citable method/full-text records must support the bottleneck")
    if full_anchor < 1:
        errors.append("at least one citable method/full-text closest_anchor is required")

    traces = as_list(campaign.get("literature_search_trace"))
    if not traces:
        errors.append("literature_search_trace must contain at least one query record")
    for index, raw in enumerate(traces):
        prefix = f"literature_search_trace[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(
            raw,
            [
                "query",
                "provider",
                "searched_at",
                "covered_time_range",
                "result_refs",
                "full_text_status",
                "source_verification_limit",
            ],
            prefix,
            errors,
        )
        if not non_papernexus_source(raw):
            errors.append(f"{prefix} provider/source provenance must be non-PaperNexus")
        unknown = sorted(set(strings(raw.get("result_refs"))) - set(by_id))
        if unknown:
            errors.append(f"{prefix}.result_refs contains unknown evidence ids {unknown}")
    readiness = str(campaign.get("evidence_readiness") or "").strip()
    if readiness != "ready":
        errors.append("evidence_readiness must be ready before candidate generation")
    return by_id, lane_counts


def validate_lineage_and_gaps(campaign: Dict[str, Any], evidence: Dict[str, Dict[str, Any]], errors: List[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    lineage = as_dict(campaign.get("method_lineage"))
    nodes: Dict[str, Dict[str, Any]] = {}
    for index, raw in enumerate(as_list(lineage.get("nodes"))):
        prefix = f"method_lineage.nodes[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(raw, ["id", "label", "provenance", "citable"], prefix, errors)
        node_id = str(raw.get("id") or "").strip()
        if node_id in nodes:
            errors.append(f"{prefix}.id duplicates {node_id}")
        elif node_id:
            nodes[node_id] = raw
        provenance = str(raw.get("provenance") or "").strip()
        refs = strings(raw.get("evidence_refs"))
        if provenance == "external_citable":
            if raw.get("citable") is not True:
                errors.append(f"{prefix}.citable must be true for external_citable")
            if not refs:
                errors.append(f"{prefix}.evidence_refs required for external_citable")
            if any(ref not in evidence for ref in refs):
                errors.append(f"{prefix}.evidence_refs contains unknown ids")
            for ref in refs:
                if ref in evidence and not is_citable_verified_evidence(evidence[ref]):
                    errors.append(f"{prefix}.evidence_refs[{ref}] must resolve to citable verified method evidence")
        elif provenance == "parametric_awareness_only":
            if raw.get("citable") is not False:
                errors.append(f"{prefix}.citable must be false for awareness-only")
            if refs:
                errors.append(f"{prefix}.evidence_refs must be empty for awareness-only")
        else:
            errors.append(f"{prefix}.provenance must be external_citable or parametric_awareness_only")
    if not nodes:
        errors.append("method_lineage.nodes must be non-empty")

    for index, raw in enumerate(as_list(lineage.get("edges"))):
        prefix = f"method_lineage.edges[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(raw, ["source", "target", "relation"], prefix, errors)
        source = str(raw.get("source") or "")
        target = str(raw.get("target") or "")
        if source not in nodes or target not in nodes:
            errors.append(f"{prefix} references an unknown node")
            continue
        refs = strings(raw.get("evidence_refs"))
        both_citable = all(str(nodes[node].get("provenance")) == "external_citable" for node in [source, target])
        if both_citable and not refs:
            errors.append(f"{prefix}.evidence_refs required between citable nodes")
        if any(ref not in evidence for ref in refs):
            errors.append(f"{prefix}.evidence_refs contains unknown ids")
        if both_citable:
            for ref in refs:
                if ref in evidence and not is_citable_verified_evidence(evidence[ref]):
                    errors.append(f"{prefix}.evidence_refs[{ref}] must resolve to citable verified method evidence")

    gaps: Dict[str, Dict[str, Any]] = {}
    for index, raw in enumerate(as_list(campaign.get("structural_gaps"))):
        prefix = f"structural_gaps[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(raw, ["id", "type", "description", "lineage_node_refs", "evidence_refs"], prefix, errors)
        gap_id = str(raw.get("id") or "").strip()
        if gap_id in gaps:
            errors.append(f"{prefix}.id duplicates {gap_id}")
        elif gap_id:
            gaps[gap_id] = raw
        gap_type = str(raw.get("type") or "")
        if gap_type not in GAP_TYPES:
            errors.append(f"{prefix}.type must be one of {sorted(GAP_TYPES)}")
        node_refs = strings(raw.get("lineage_node_refs"))
        evidence_refs = strings(raw.get("evidence_refs"))
        if not node_refs or any(ref not in nodes for ref in node_refs):
            errors.append(f"{prefix}.lineage_node_refs must resolve")
        if not evidence_refs or any(ref not in evidence for ref in evidence_refs):
            errors.append(f"{prefix}.evidence_refs must resolve")
        for ref in evidence_refs:
            if ref in evidence and not is_citable_verified_evidence(evidence[ref]):
                errors.append(f"{prefix}.evidence_refs[{ref}] must resolve to citable verified method evidence")
        for ref in node_refs:
            if ref in nodes and str(nodes[ref].get("provenance")) != "external_citable":
                errors.append(f"{prefix} may not use awareness-only node {ref} as gap support")
        if gap_type == "additive_leaf" and not present(raw.get("missing_leaf")):
            errors.append(f"{prefix}.missing_leaf")
        if gap_type == "subtractive_shared_assumption":
            if not present(raw.get("shared_assumption")):
                errors.append(f"{prefix}.shared_assumption")
            if len(set(node_refs)) < 2:
                errors.append(f"{prefix} requires at least two citable lineage nodes")
        if gap_type == "other_structural":
            if not present(raw.get("structural_shape")) or not present(raw.get("rationale")):
                errors.append(f"{prefix} requires structural_shape and rationale")
    if not gaps:
        errors.append("structural_gaps must be non-empty")
    anchor = str(campaign.get("anchor_gap_id") or "")
    if anchor not in gaps:
        errors.append("anchor_gap_id must reference a structural gap")
    return nodes, gaps


def validate_collision(candidate: Dict[str, Any], prefix: str, evidence: Dict[str, Dict[str, Any]], errors: List[str]) -> bool:
    collision = as_dict(candidate.get("collision_audit"))
    require(collision, ["signature_terms", "signature_window_months", "alias_terms", "alias_window_months", "query_trace", "status"], f"{prefix}.collision_audit", errors)
    if not isinstance(collision.get("signature_window_months"), int) or isinstance(collision.get("signature_window_months"), bool) or collision.get("signature_window_months") != 10:
        errors.append(f"{prefix}.collision_audit.signature_window_months must be 10")
    if not isinstance(collision.get("alias_window_months"), int) or isinstance(collision.get("alias_window_months"), bool) or collision.get("alias_window_months") != 48:
        errors.append(f"{prefix}.collision_audit.alias_window_months must be 48")
    if not strings(collision.get("signature_terms")) or not strings(collision.get("alias_terms")):
        errors.append(f"{prefix}.collision_audit signature_terms and alias_terms must be non-empty")
    channels: Set[str] = set()
    for index, raw in enumerate(as_list(collision.get("query_trace"))):
        qprefix = f"{prefix}.collision_audit.query_trace[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{qprefix} must be an object")
            continue
        require(raw, ["channel", "query", "searched_at", "provider", "result_refs"], qprefix, errors)
        channel = str(raw.get("channel") or "")
        if channel not in {"signature", "alias"}:
            errors.append(f"{qprefix}.channel must be signature or alias")
        else:
            channels.add(channel)
        if not non_papernexus_source(raw):
            errors.append(f"{qprefix} provider/source provenance must be non-PaperNexus")
        if any(ref not in evidence for ref in strings(raw.get("result_refs"))):
            errors.append(f"{qprefix}.result_refs contains unknown ids")
    if channels != {"signature", "alias"}:
        errors.append(f"{prefix}.collision_audit.query_trace must cover signature and alias channels")

    exact = False
    status = str(collision.get("status") or "")
    if status == "threat_found":
        prior = as_dict(collision.get("worst_case_prior"))
        require(prior, ["evidence_ref", "exact_result", "subsumption_argument", "overlap", "collision_channel"], f"{prefix}.collision_audit.worst_case_prior", errors)
        if prior.get("evidence_ref") not in evidence:
            errors.append(f"{prefix}.collision_audit.worst_case_prior.evidence_ref must resolve")
        if prior.get("collision_channel") not in {"signature", "alias"}:
            errors.append(f"{prefix}.collision_audit.worst_case_prior.collision_channel invalid")
        if prior.get("overlap") not in {"exact_mechanism", "partial", "none"}:
            errors.append(f"{prefix}.collision_audit.worst_case_prior.overlap invalid")
        exact = prior.get("overlap") == "exact_mechanism"
    elif status == "no_threat_found":
        if not present(collision.get("search_limitations")) or not present(collision.get("claim_limit")):
            errors.append(f"{prefix}.collision_audit no_threat_found requires search_limitations and claim_limit")
    else:
        errors.append(f"{prefix}.collision_audit.status must be threat_found or no_threat_found")
    return exact


def validate_gauntlet(candidate: Dict[str, Any], prefix: str, exact_collision: bool, errors: List[str]) -> None:
    gauntlet = as_dict(candidate.get("quality_gauntlet"))
    checks = as_dict(gauntlet.get("checks"))
    for name in CHECK_NAMES:
        check = as_dict(checks.get(name))
        require(check, ["verdict", "rationale"], f"{prefix}.quality_gauntlet.checks.{name}", errors)
        if check.get("verdict") not in CHECK_VERDICTS:
            errors.append(f"{prefix}.quality_gauntlet.checks.{name}.verdict invalid")
    verdict = str(gauntlet.get("verdict") or "")
    layer = str(gauntlet.get("verdict_layer") or "")
    if verdict not in {"advance", "revise", "abandon"}:
        errors.append(f"{prefix}.quality_gauntlet.verdict invalid")
    if layer not in {"hard_floor", "soft_judgment"}:
        errors.append(f"{prefix}.quality_gauntlet.verdict_layer invalid")
    if not isinstance(gauntlet.get("revision_targets"), list):
        errors.append(f"{prefix}.quality_gauntlet.revision_targets must be a list")
    check_verdicts = {
        name: str(as_dict(checks.get(name)).get("verdict") or "")
        for name in CHECK_NAMES
    }
    if any(value == "abandon" for value in check_verdicts.values()):
        if verdict != "abandon":
            errors.append(f"{prefix}.quality_gauntlet.verdict must be abandon when any named check abandons")
    elif any(value == "revise" for value in check_verdicts.values()):
        if verdict != "revise":
            errors.append(f"{prefix}.quality_gauntlet.verdict must be revise when any named check requires revision")
    elif all(value == "pass" for value in check_verdicts.values()) and verdict != "advance":
        errors.append(f"{prefix}.quality_gauntlet.verdict must be advance when all named checks pass")
    for name in ("gap_closure_reject_check", "anti_pattern_check"):
        check = as_dict(checks.get(name))
        if check.get("verdict") == "abandon" and check.get("hard_floor_triggered") is not True:
            errors.append(f"{prefix}.quality_gauntlet.checks.{name} abandon must set hard_floor_triggered=true")
    hard_floor = exact_collision or any(as_dict(checks.get(name)).get("hard_floor_triggered") is True for name in CHECK_NAMES)
    if hard_floor and (verdict != "abandon" or layer != "hard_floor"):
        errors.append(f"{prefix}.quality_gauntlet must abandon hard-floor collision/reject cases")
    repair = as_dict(gauntlet.get("repair"))
    count = repair.get("count", 0)
    if not isinstance(count, int) or isinstance(count, bool) or count not in {0, 1}:
        errors.append(f"{prefix}.quality_gauntlet.repair.count must be 0 or 1")
    if count == 1:
        if repair.get("check") != "falsification_structure_check":
            errors.append(f"{prefix}.quality_gauntlet repair may target only falsification_structure_check")
        if repair.get("protected_commitments_changed") is not False:
            errors.append(f"{prefix}.quality_gauntlet repair must preserve protected commitments")


def validate_implementability(candidate: Dict[str, Any], prefix: str, errors: List[str]) -> bool:
    mechanism = as_dict(candidate.get("mechanism"))
    steps = as_list(mechanism.get("method_steps"))
    step_ids: List[str] = []
    for index, raw in enumerate(steps):
        sprefix = f"{prefix}.mechanism.method_steps[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{sprefix} must be an object")
            continue
        require(raw, ["id", "action"], sprefix, errors)
        step_ids.append(str(raw.get("id") or ""))
    if not step_ids or len(step_ids) != len(set(step_ids)):
        errors.append(f"{prefix}.mechanism.method_steps requires unique non-empty ids")

    audit = as_dict(candidate.get("implementability_audit"))
    require(audit, ["generation_context_id", "reviewer_context_id", "reviewer_role", "status", "enriched_steps", "underspecified_points"], f"{prefix}.implementability_audit", errors)
    generation_context = str(audit.get("generation_context_id") or "").strip()
    reviewer_context = str(audit.get("reviewer_context_id") or "").strip()
    if not generation_context or not reviewer_context or generation_context == reviewer_context:
        errors.append(f"{prefix}.implementability_audit reviewer context must be separate")
    if audit.get("reviewer_role") != "skeptical_engineer":
        errors.append(f"{prefix}.implementability_audit.reviewer_role must be skeptical_engineer")
    enriched = as_list(audit.get("enriched_steps"))
    enriched_ids: List[str] = []
    for index, raw in enumerate(enriched):
        eprefix = f"{prefix}.implementability_audit.enriched_steps[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{eprefix} must be an object")
            continue
        require(raw, ["id", "what_changes", "build_procedure", "inputs", "outputs"], eprefix, errors)
        enriched_ids.append(str(raw.get("id") or ""))
    if enriched_ids != step_ids:
        errors.append(f"{prefix}.implementability_audit enriched step ids/order must exactly match mechanism steps")
    open_load_bearing = False
    for index, raw in enumerate(as_list(audit.get("underspecified_points"))):
        uprefix = f"{prefix}.implementability_audit.underspecified_points[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{uprefix} must be an object")
            continue
        require(raw, ["step_id", "hole", "fill", "severity", "load_bearing"], uprefix, errors)
        if raw.get("step_id") not in step_ids:
            errors.append(f"{uprefix}.step_id must resolve")
        if raw.get("severity") not in {"filled", "open"}:
            errors.append(f"{uprefix}.severity invalid")
        if raw.get("severity") == "open" and raw.get("load_bearing") is True:
            open_load_bearing = True
    if audit.get("protected_commitments_present") not in {None, False}:
        errors.append(f"{prefix}.implementability_audit must not carry protected commitments")
    return audit.get("status") == "passed" and not open_load_bearing


def validate_rapid(candidate: Dict[str, Any], prefix: str, errors: List[str]) -> float:
    rapid = as_dict(candidate.get("rapid_validation"))
    require(rapid, ["evidence_tier", "baseline_code", "dataset", "metric_policy", "evaluation_command", "decision_class", "expected_decision_change", "resource_request", "seed_policy", "outcome_routes"], f"{prefix}.rapid_validation", errors)
    if rapid.get("evidence_tier") != "pilot_only":
        errors.append(f"{prefix}.rapid_validation.evidence_tier must be pilot_only")
    if rapid.get("decision_class") != "falsify_core_mechanism":
        errors.append(f"{prefix}.rapid_validation.decision_class must be falsify_core_mechanism")
    if rapid.get("claim_intent") not in {None, "candidate_screening", "record_only"}:
        errors.append(f"{prefix}.rapid_validation.claim_intent may not promote or close claims")
    baseline = as_dict(rapid.get("baseline_code"))
    require(baseline, ["source_ref", "revision", "resolved_path", "train_entrypoint", "eval_entrypoint", "comparison_label", "locked"], f"{prefix}.rapid_validation.baseline_code", errors)
    if baseline.get("locked") is not True:
        errors.append(f"{prefix}.rapid_validation.baseline_code.locked must be true")
    if baseline.get("comparison_label") not in BASELINE_COMPARISON_LABELS:
        errors.append(
            f"{prefix}.rapid_validation.baseline_code.comparison_label must use an exact baseline-comparison label"
        )
    dataset = as_dict(rapid.get("dataset"))
    require(dataset, ["name", "proxy_rationale", "split"], f"{prefix}.rapid_validation.dataset", errors)
    metric = as_dict(rapid.get("metric_policy"))
    require(metric, ["primary_metric", "direction", "locked"], f"{prefix}.rapid_validation.metric_policy", errors)
    if metric.get("locked") is not True:
        errors.append(f"{prefix}.rapid_validation.metric_policy.locked must be true")
    resource = as_dict(rapid.get("resource_request"))
    require(resource, ["compute_backend", "execution_route", "gpu_count", "estimated_gpu_hours", "walltime_minutes", "smoke_minutes"], f"{prefix}.rapid_validation.resource_request", errors)
    if resource.get("compute_backend") != "local_gpu":
        errors.append(f"{prefix}.rapid_validation.resource_request.compute_backend must be local_gpu")
    if resource.get("execution_route") not in EXECUTION_ROUTES:
        errors.append(f"{prefix}.rapid_validation.resource_request.execution_route must be one of {sorted(EXECUTION_ROUTES)}")
    if not isinstance(resource.get("gpu_count"), int) or isinstance(resource.get("gpu_count"), bool) or resource.get("gpu_count") != 1:
        errors.append(f"{prefix}.rapid_validation.resource_request.gpu_count must be 1")
    hours_value = resource.get("estimated_gpu_hours")
    hours = float(hours_value) if finite_number(hours_value) else -1.0
    if hours <= 0 or hours > 1.0:
        errors.append(f"{prefix}.rapid_validation.resource_request.estimated_gpu_hours must be >0 and <=1")
    wall = resource.get("walltime_minutes")
    smoke = resource.get("smoke_minutes")
    if not finite_number(wall) or wall <= 0 or wall > 60:
        errors.append(f"{prefix}.rapid_validation.resource_request.walltime_minutes must be >0 and <=60")
    if not finite_number(smoke) or smoke < 0 or smoke > 10:
        errors.append(f"{prefix}.rapid_validation.resource_request.smoke_minutes must be between 0 and 10")
    seed = as_dict(rapid.get("seed_policy"))
    require(seed, ["planned_seed_count", "max_random_seeds", "seed", "retry_reuses_seed"], f"{prefix}.rapid_validation.seed_policy", errors)
    if not isinstance(seed.get("planned_seed_count"), int) or isinstance(seed.get("planned_seed_count"), bool) or seed.get("planned_seed_count") != 1:
        errors.append(f"{prefix}.rapid_validation.seed_policy.planned_seed_count must be 1")
    max_seeds = seed.get("max_random_seeds")
    if not isinstance(max_seeds, int) or isinstance(max_seeds, bool) or not 1 <= max_seeds <= 3:
        errors.append(f"{prefix}.rapid_validation.seed_policy.max_random_seeds must be 1..3")
    seed_value = seed.get("seed")
    if not isinstance(seed_value, int) or isinstance(seed_value, bool) or seed_value < 0:
        errors.append(f"{prefix}.rapid_validation.seed_policy.seed must be a non-negative integer")
    if seed.get("retry_reuses_seed") is not True:
        errors.append(f"{prefix}.rapid_validation.seed_policy.retry_reuses_seed must be true")
    routes = as_dict(rapid.get("outcome_routes"))
    if set(routes) != OUTCOME_ROUTE_KEYS or any(not present(value) for value in routes.values()):
        errors.append(f"{prefix}.rapid_validation.outcome_routes must define exactly {sorted(OUTCOME_ROUTE_KEYS)}")
    return max(0.0, hours)


def validate_candidates(campaign: Dict[str, Any], gaps: Dict[str, Dict[str, Any]], evidence: Dict[str, Dict[str, Any]], mains: Set[str], subparents: Dict[str, str], errors: List[str], warnings: List[str]) -> Tuple[Dict[str, Dict[str, Any]], List[str], List[str]]:
    rows = as_list(campaign.get("candidates"))
    if not 8 <= len(rows) <= 12:
        errors.append(f"candidates must contain 8..12 independent transactions, found {len(rows)}")
    candidates: Dict[str, Dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        prefix = f"candidates[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        require(raw, ["id", "status", "title", "research_question", "contribution_type", "gap_closures", "mechanism", "negative_control", "collision_audit", "quality_gauntlet", "implementability_audit", "rapid_validation", "protected_commitments"], prefix, errors)
        candidate_id = str(raw.get("id") or "").strip()
        if candidate_id in candidates:
            errors.append(f"{prefix}.id duplicates {candidate_id}")
        elif candidate_id:
            candidates[candidate_id] = raw
        if raw.get("status") not in CANDIDATE_STATUSES:
            errors.append(f"{prefix}.status invalid")
        if str(raw.get("contribution_type") or "").upper() not in CONTRIBUTION_TYPES:
            errors.append(f"{prefix}.contribution_type must be ALGO, CODE, or PARAM")

        closures = as_list(raw.get("gap_closures"))
        if not 1 <= len(closures) <= 3:
            errors.append(f"{prefix}.gap_closures must contain 1..3 counted entries")
        if len(closures) == 1:
            if raw.get("single_gap_fast_diagnostic") is not True:
                errors.append(f"{prefix}.single_gap_fast_diagnostic must be true when exactly one closure is used")
            else:
                warnings.append(f"{prefix} uses the local single-gap fast-diagnostic adaptation; paper default is two closures")
        elif raw.get("single_gap_fast_diagnostic") is True:
            errors.append(f"{prefix}.single_gap_fast_diagnostic is valid only when exactly one closure is used")
        for closure_index, closure in enumerate(closures):
            cprefix = f"{prefix}.gap_closures[{closure_index}]"
            if not isinstance(closure, dict):
                errors.append(f"{cprefix} must be an object")
                continue
            require(closure, ["gap_ref", "role", "main_pattern", "subpattern", "structural_fit", "recipe_application", "expected_artifact"], cprefix, errors)
            gap_ref = str(closure.get("gap_ref") or "")
            main = str(closure.get("main_pattern") or "")
            sub = str(closure.get("subpattern") or "")
            if gap_ref not in gaps:
                errors.append(f"{cprefix}.gap_ref must resolve")
            if main not in mains:
                errors.append(f"{cprefix}.main_pattern is not in the pinned deck")
            if sub not in subparents:
                errors.append(f"{cprefix}.subpattern is not in the pinned deck")
            elif subparents[sub] != main:
                errors.append(f"{cprefix}.subpattern parent must equal main_pattern")
            if closure.get("companion_pattern") is not None or closure.get("companion_role") is not None:
                errors.append(f"{cprefix} companion roles are disabled in v1")

        mechanism = as_dict(raw.get("mechanism"))
        require(mechanism, ["intervention", "one_variable_change", "load_bearing_variable", "predicted_observation", "falsifier", "alternative_explanation", "method_steps"], f"{prefix}.mechanism", errors)
        control = as_dict(raw.get("negative_control"))
        require(control, ["intervention", "expected_if_mechanism_true", "downstream_metric", "non_tautology_rationale"], f"{prefix}.negative_control", errors)
        exact = validate_collision(raw, prefix, evidence, errors)
        validate_gauntlet(raw, prefix, exact, errors)
        implementable = validate_implementability(raw, prefix, errors)
        validate_rapid(raw, prefix, errors)

        protected = as_dict(raw.get("protected_commitments"))
        expected_payload = protected_payload(raw)
        if protected.get("payload") != expected_payload:
            errors.append(f"{prefix}.protected_commitments.payload differs from canonical commitments")
        expected_sha = protected_digest(raw)
        if protected.get("sha256") != expected_sha:
            errors.append(f"{prefix}.protected_commitments.sha256 mismatch")
        if exact and raw.get("status") in {"shortlisted", "admitted"}:
            errors.append(f"{prefix} exact-mechanism collision cannot be shortlisted or admitted")
        if raw.get("status") == "admitted":
            if as_dict(raw.get("quality_gauntlet")).get("verdict") != "advance":
                errors.append(f"{prefix} admitted candidate requires quality_gauntlet.verdict=advance")
            if not implementable:
                errors.append(f"{prefix} admitted candidate requires passed implementability with no open load-bearing hole")

    shortlist = strings(campaign.get("shortlisted_candidate_ids"))
    admitted = strings(campaign.get("admitted_candidate_ids"))
    if not 3 <= len(shortlist) <= 5 or len(shortlist) != len(set(shortlist)):
        errors.append("shortlisted_candidate_ids must contain 3..5 unique ids")
    if not 1 <= len(admitted) <= 4 or len(admitted) != len(set(admitted)):
        errors.append("admitted_candidate_ids must contain 1..4 unique ids")
    if any(item not in candidates for item in shortlist):
        errors.append("shortlisted_candidate_ids contains unknown ids")
    if any(item not in shortlist for item in admitted):
        errors.append("admitted_candidate_ids must be a subset of shortlisted_candidate_ids")
    for candidate_id in shortlist:
        if candidate_id in candidates and candidates[candidate_id].get("status") not in {"shortlisted", "admitted"}:
            errors.append(f"shortlisted candidate {candidate_id} has inconsistent status")
    admitted_hours = 0.0
    for candidate_id in admitted:
        candidate = candidates.get(candidate_id, {})
        if candidate.get("status") != "admitted":
            errors.append(f"admitted candidate {candidate_id} has inconsistent status")
        rapid = as_dict(candidate.get("rapid_validation"))
        resource = as_dict(rapid.get("resource_request"))
        hours = resource.get("estimated_gpu_hours")
        if finite_number(hours):
            admitted_hours += float(hours)
    if admitted_hours > 4.0:
        errors.append("admitted candidates exceed the 4 GPU-hour quick campaign ceiling")
    return candidates, shortlist, admitted


def lint_campaign(project: str) -> Dict[str, Any]:
    base = ar_root(project)
    path = base / CAMPAIGN_REL
    errors: List[str] = []
    warnings: List[str] = []
    campaign, campaign_sha = read_json_with_sha(path)
    if not campaign:
        return {
            "complete": False,
            "missing": [
                f"{CAMPAIGN_REL} is missing or is not strict finite JSON"
                if path.exists()
                else str(CAMPAIGN_REL)
            ],
            "warnings": [],
            "campaign_sha256": None,
            "checked_at": utc_now(),
        }
    if campaign_sha is None:
        return {
            "complete": False,
            "missing": [f"{CAMPAIGN_REL} could not be hashed as strict finite JSON"],
            "warnings": [],
            "campaign_sha256": None,
            "checked_at": utc_now(),
        }
    for nonfinite_path in nonfinite_paths(campaign):
        errors.append(f"{nonfinite_path} must be a finite JSON number")
    if present(campaign.get("_template_metadata")):
        errors.append("_template_metadata marks a synthetic authoring-only template and must be removed after replacement")
    validate_provenance(campaign, errors)
    if not isinstance(campaign.get("schema_version"), int) or isinstance(campaign.get("schema_version"), bool) or campaign.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    require(campaign, ["campaign_id", "campaign_revision", "direction", "status", "source_mode", "papernexus_used", "method_reference", "deck_aggregate_sha256", "constraints", "claim_limits", "evidence_readiness"], "campaign", errors)
    revision = campaign.get("campaign_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append("campaign_revision must be a positive integer")
    if revision == 1 and present(campaign.get("parent_campaign_sha256")):
        errors.append("campaign_revision=1 must not set parent_campaign_sha256")
    if isinstance(revision, int) and revision > 1 and not SHA_RE.fullmatch(str(campaign.get("parent_campaign_sha256") or "")):
        errors.append("revised campaign requires parent_campaign_sha256")
    campaign_id = str(campaign.get("campaign_id") or "").strip()
    if not CAMPAIGN_ID_RE.fullmatch(campaign_id):
        errors.append("campaign_id must be a stable 3..128 character identifier")
    if campaign.get("status") not in CAMPAIGN_STATUSES or campaign.get("status") != "ready":
        errors.append("campaign.status must be ready for validation/materialization")
    if campaign.get("source_mode") != "external_material":
        errors.append("source_mode must be external_material")
    if campaign.get("papernexus_used") is not False:
        errors.append("papernexus_used must be false")
    method = as_dict(campaign.get("method_reference"))
    require(method, ["paper", "paper_version", "official_repo", "repo_commit", "workflow"], "method_reference", errors)
    if method.get("paper") != "arXiv:2607.04439" or method.get("paper_version") != "v1":
        errors.append("method_reference must identify arXiv:2607.04439v1")
    if method.get("repo_commit") != "868f0e9c30685b72ebd475f0dada1492a1982168":
        errors.append("method_reference.repo_commit must be the pinned audited commit")
    if campaign.get("deck_aggregate_sha256") != PINNED_DECK_AGGREGATE_SHA256:
        errors.append("deck_aggregate_sha256 must match the pinned audited ResearchStudio deck")

    constraints = as_dict(campaign.get("constraints"))
    expected_constraints = {
        "candidate_count_min": 8,
        "candidate_count_max": 12,
        "shortlist_min": 3,
        "shortlist_max": 5,
        "max_admitted_tracks": 4,
        "quick_campaign_gpu_hours": 4,
        "max_candidate_gpu_hours": 1,
        "max_random_seeds": 3,
    }
    for key, expected in expected_constraints.items():
        observed = constraints.get(key)
        if not isinstance(observed, int) or isinstance(observed, bool) or observed != expected:
            errors.append(f"constraints.{key} must be {expected}")
    if not present(campaign.get("claim_limits")):
        errors.append("claim_limits must be non-empty")

    deck = verify_deck()
    if not deck.get("complete"):
        errors.extend(f"deck: {item}" for item in deck.get("errors", []))
    mains, subparents, catalog_errors = pattern_catalog()
    errors.extend(f"deck: {item}" for item in catalog_errors)
    evidence, lane_counts = validate_evidence(campaign, errors, warnings)
    _, gaps = validate_lineage_and_gaps(campaign, evidence, errors)
    candidates, shortlist, admitted = validate_candidates(campaign, gaps, evidence, mains, subparents, errors, warnings)

    return {
        "schema_version": 1,
        "complete": not errors,
        "status": "passed" if not errors else "blocked",
        "missing": errors,
        "warnings": warnings,
        "campaign_ref": str(CAMPAIGN_REL),
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign.get("campaign_id"),
        "campaign_revision": campaign.get("campaign_revision"),
        "deck_aggregate_sha256": deck.get("aggregate_sha256"),
        "evidence_lane_counts": lane_counts,
        "candidate_count": len(candidates),
        "shortlisted_candidate_ids": shortlist,
        "admitted_candidate_ids": admitted,
        "checked_at": utc_now(),
        "validator": "autoreskill-gpu-idea-validation/idea_campaign.py",
        "semantic_boundary": "Structural validation records explicit evidence and independent review decisions; it does not prove novelty, source fidelity, or experimental success.",
    }


def build_slot_map(campaign: Dict[str, Any], campaign_sha: str, admitted: List[str]) -> Dict[str, Any]:
    evidence = {str(row.get("id")): row for row in as_list(campaign.get("evidence_records")) if isinstance(row, dict)}
    lineage = as_dict(campaign.get("method_lineage"))
    nodes = {str(row.get("id")): row for row in as_list(lineage.get("nodes")) if isinstance(row, dict)}
    gaps = [row for row in as_list(campaign.get("structural_gaps")) if isinstance(row, dict)]
    candidates = {str(row.get("id")): row for row in as_list(campaign.get("candidates")) if isinstance(row, dict)}
    return {
        "schema_version": 1,
        "source_mode": "external_material",
        "campaign_ref": str(CAMPAIGN_REL),
        "campaign_sha256": campaign_sha,
        "challenge_clusters": [
            {
                "slot_id": str(row.get("id")),
                "type": row.get("type"),
                "description": row.get("description"),
                "lineage_node_refs": row.get("lineage_node_refs"),
                "evidence_refs": row.get("evidence_refs"),
            }
            for row in gaps
        ],
        "insight_clusters": [
            {
                "slot_id": candidate_id,
                "title": candidates[candidate_id].get("title"),
                "mechanism": candidates[candidate_id].get("mechanism"),
                "gap_closures": candidates[candidate_id].get("gap_closures"),
                "external_candidate_id": candidate_id,
            }
            for candidate_id in admitted
            if candidate_id in candidates
        ],
        "transfer_bridges": [
            {
                "evidence_id": evidence_id,
                "lane": row.get("lane"),
                "source_ref": row.get("source_ref"),
                "roles": row.get("roles"),
            }
            for evidence_id, row in evidence.items()
            if row.get("lane") in {"near_neighbor", "far_neighbor"}
        ],
        "anchor_nodes": [
            {
                "node_id": node_id,
                "label": row.get("label"),
                "provenance": row.get("provenance"),
                "evidence_refs": row.get("evidence_refs", []),
            }
            for node_id, row in nodes.items()
        ],
        "relation_patterns": [
            {
                "source": row.get("source"),
                "target": row.get("target"),
                "relation": row.get("relation"),
                "evidence_refs": row.get("evidence_refs", []),
                "explicit": True,
            }
            for row in as_list(lineage.get("edges"))
            if isinstance(row, dict)
        ],
        "structural_gaps": gaps,
        "admitted_candidate_ids": admitted,
        "evidence_boundary": {
            "source_backed": sorted(
                evidence_id for evidence_id, row in evidence.items() if row.get("citable") is True
            ),
            "parametric_awareness_only": sorted(
                node_id for node_id, row in nodes.items() if row.get("provenance") == "parametric_awareness_only"
            ),
            "claim_limits": campaign.get("claim_limits"),
            "integrity_note": "Excerpt hashes prove captured-text integrity, not fidelity to the original source.",
        },
        "generated_at": utc_now(),
    }


def current_sha(path: Path) -> Optional[str]:
    return sha256_file(path) if path.is_file() else None


def content_ref(stem: str, digest: str) -> Path:
    return COMMITTED_REL / f"{stem}.{digest}.json"


def resolve_safe_ref(base: Path, raw_ref: Any) -> Optional[Path]:
    ref = str(raw_ref or "").strip()
    if not ref or "\\" in ref:
        return None
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    try:
        resolved = (base / relative).resolve()
        resolved.relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def write_content_addressed(base: Path, stem: str, value: Dict[str, Any]) -> Tuple[str, str]:
    digest = sha256_bytes(serialized_json_bytes(value))
    ref = content_ref(stem, digest)
    path = base / ref
    if path.exists():
        if not path.is_file() or sha256_file(path) != digest:
            raise RuntimeError(f"content-addressed artifact collision at {ref}")
    else:
        atomic_write_json(path, value)
        if sha256_file(path) != digest:
            raise RuntimeError(f"content-addressed artifact write mismatch at {ref}")
    return str(ref), digest


def validate_committed_gate(
    base: Path,
    gate: Dict[str, Any],
    campaign_sha: str,
    campaign_id: str,
    campaign_revision: int,
    admitted_candidate_ids: Sequence[str],
) -> List[str]:
    errors: List[str] = []
    if gate.get("schema_version") != 1 or isinstance(gate.get("schema_version"), bool):
        errors.append("gate.schema_version must be 1")
    required_values = {
        "status": "passed",
        "evidence_source_mode": "external_material",
        "lane_attempts_satisfied": True,
        "screening_completed": True,
        "allowed_next_action": "generate_experiment_idea_pool",
        "commit_layout": "content_addressed_v1",
        "campaign_ref": str(CAMPAIGN_REL),
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign_id,
        "campaign_revision": campaign_revision,
    }
    for key, expected in required_values.items():
        if gate.get(key) != expected:
            errors.append(f"gate.{key} must be {expected!r}")
    if strings(gate.get("admitted_candidate_ids")) != list(admitted_candidate_ids):
        errors.append("gate.admitted_candidate_ids must match the committed campaign")

    lint_ref = str(gate.get("lint_ref") or "")
    slot_ref = str(gate.get("innovation_slot_map_path") or "")
    lint_sha = str(gate.get("lint_sha256") or "").lower()
    slot_sha = str(gate.get("slot_map_sha256") or "").lower()
    if not SHA_RE.fullmatch(lint_sha) or lint_ref != str(content_ref("NON_PAPERNEXUS_IDEA_LINT", lint_sha)):
        errors.append("gate.lint_ref must be the content-addressed path named by lint_sha256")
    if not SHA_RE.fullmatch(slot_sha) or slot_ref != str(content_ref("INNOVATION_SLOT_MAP", slot_sha)):
        errors.append("gate.innovation_slot_map_path must be the content-addressed path named by slot_map_sha256")
    if gate.get("slot_map_ref") != slot_ref:
        errors.append("gate.slot_map_ref must equal innovation_slot_map_path")
    panel_ref = str(gate.get("panel_design_review_ref") or "")
    panel_sha = str(gate.get("panel_design_review_sha256") or "").lower()
    if panel_ref or panel_sha:
        panel_path = resolve_safe_ref(base, panel_ref)
        if panel_ref != str(PANEL_REL) or not SHA_RE.fullmatch(panel_sha):
            errors.append("gate panel design-review ref/hash is invalid")
        elif panel_path is None or not panel_path.is_file() or sha256_file(panel_path) != panel_sha:
            errors.append("gate panel design-review artifact is missing, unsafe, or hash-mismatched")

    lint_path = resolve_safe_ref(base, lint_ref)
    slot_path = resolve_safe_ref(base, slot_ref)
    lint_payload: Optional[Dict[str, Any]] = None
    slot_payload: Optional[Dict[str, Any]] = None
    if lint_path is None or not lint_path.is_file() or not SHA_RE.fullmatch(lint_sha) or sha256_file(lint_path) != lint_sha:
        errors.append("gate lint artifact is missing, unsafe, or hash-mismatched")
    else:
        lint_payload = read_json(lint_path)
        if lint_payload is None:
            errors.append("gate lint artifact is not strict finite JSON")
    if slot_path is None or not slot_path.is_file() or not SHA_RE.fullmatch(slot_sha) or sha256_file(slot_path) != slot_sha:
        errors.append("gate slot-map artifact is missing, unsafe, or hash-mismatched")
    else:
        slot_payload = read_json(slot_path)
        if slot_payload is None:
            errors.append("gate slot-map artifact is not strict finite JSON")

    if lint_payload is not None:
        expected_lint = {
            "complete": True,
            "status": "passed",
            "campaign_ref": str(CAMPAIGN_REL),
            "campaign_sha256": campaign_sha,
            "campaign_id": campaign_id,
            "campaign_revision": campaign_revision,
            "slot_map_ref": slot_ref,
            "slot_map_sha256": slot_sha,
        }
        for key, expected in expected_lint.items():
            if lint_payload.get(key) != expected:
                errors.append(f"committed lint {key} is stale or invalid")
    if slot_payload is not None:
        expected_slot = {
            "source_mode": "external_material",
            "campaign_ref": str(CAMPAIGN_REL),
            "campaign_sha256": campaign_sha,
            "campaign_id": campaign_id,
            "campaign_revision": campaign_revision,
        }
        for key, expected in expected_slot.items():
            if slot_payload.get(key) != expected:
                errors.append(f"committed slot map {key} is stale or invalid")
    return errors


def verify_current_gate(project: str) -> Dict[str, Any]:
    """Verify the exact materialized external commit without mutating it."""
    base = ar_root(project)
    campaign_path = base / CAMPAIGN_REL
    gate_path = base / GATE_REL
    with materialize_lock(base / LOCK_REL):
        campaign, campaign_sha = read_json_with_sha(campaign_path)
        gate, gate_sha = read_json_with_sha(gate_path)
        if campaign is None or campaign_sha is None:
            return {
                "complete": False,
                "missing": [f"{CAMPAIGN_REL} is missing or is not strict finite unique-key JSON"],
            }
        if gate is None or gate_sha is None:
            return {
                "complete": False,
                "missing": [f"{GATE_REL} is missing or is not strict finite unique-key JSON"],
            }
        campaign_lint = lint_campaign(project)
        if campaign_lint.get("complete") is not True:
            return {
                "complete": False,
                "missing": [
                    f"campaign: {item}"
                    for item in campaign_lint.get("missing", [])
                ],
                "warnings": campaign_lint.get("warnings", []),
            }
        errors = validate_committed_gate(
            base,
            gate,
            campaign_sha,
            str(campaign.get("campaign_id") or ""),
            campaign.get("campaign_revision"),
            strings(campaign.get("admitted_candidate_ids")),
        )
        return {
            "complete": not errors,
            "status": "passed" if not errors else "blocked",
            "missing": errors,
            "warnings": [],
            "campaign_sha256": campaign_sha,
            "gate_sha256": gate_sha,
            "gate_ref": str(GATE_REL),
        }


def materialize(project: str, expected_gate: str) -> Dict[str, Any]:
    base = ar_root(project)
    campaign_path = base / CAMPAIGN_REL
    gate_path = base / GATE_REL
    lock_path = base / LOCK_REL
    normalized_expected = expected_gate.strip().lower()

    with materialize_lock(lock_path):
        if not campaign_path.is_file():
            return {"complete": False, "error": f"missing {CAMPAIGN_REL}"}
        current_gate, observed_gate_sha = read_json_with_sha(gate_path)
        if normalized_expected == "absent":
            if observed_gate_sha is not None:
                return {"complete": False, "error": "gate CAS mismatch", "expected": "absent", "observed": observed_gate_sha}
        elif not SHA_RE.fullmatch(normalized_expected) or normalized_expected != observed_gate_sha:
            return {"complete": False, "error": "gate CAS mismatch", "expected": normalized_expected, "observed": observed_gate_sha}

        if gate_path.exists() and current_gate is None:
            return {"complete": False, "error": "refusing to overwrite an invalid or unknown evidence gate"}
        if current_gate:
            mode = str(current_gate.get("evidence_source_mode") or "papernexus")
            if mode != "external_material":
                return {"complete": False, "error": f"refusing to overwrite {mode} evidence gate"}

        lint = lint_campaign(project)
        if not lint.get("complete"):
            return {"complete": False, "error": "campaign validation failed", "details": lint}
        campaign_sha = str(lint.get("campaign_sha256") or "")
        campaign, reread_campaign_sha = read_json_with_sha(campaign_path)
        if campaign is None or reread_campaign_sha != campaign_sha:
            return {"complete": False, "error": "campaign changed or became invalid during locked validation"}
        campaign_id = str(campaign.get("campaign_id") or "")
        campaign_revision = campaign.get("campaign_revision")

        if current_gate:
            if current_gate.get("campaign_id") != campaign_id:
                return {"complete": False, "error": "campaign_id is immutable across gate revisions"}
            if current_gate.get("campaign_sha256") == campaign_sha:
                gate_errors = validate_committed_gate(
                    base,
                    current_gate,
                    campaign_sha,
                    campaign_id,
                    campaign_revision,
                    list(lint.get("admitted_candidate_ids") or []),
                )
                if not gate_errors:
                    return {
                        "complete": True,
                        "idempotent": True,
                        "campaign_sha256": campaign_sha,
                        "gate_sha256": observed_gate_sha,
                        "gate_ref": str(GATE_REL),
                    }
            else:
                old_revision = current_gate.get("campaign_revision")
                new_revision = campaign_revision
                if not isinstance(old_revision, int) or new_revision != old_revision + 1:
                    return {"complete": False, "error": "campaign revision must increment by one"}
                if campaign.get("parent_campaign_sha256") != current_gate.get("campaign_sha256"):
                    return {"complete": False, "error": "parent_campaign_sha256 does not match committed campaign"}

        slot_map = build_slot_map(campaign, campaign_sha, list(lint.get("admitted_candidate_ids") or []))
        slot_map["campaign_id"] = campaign_id
        slot_map["campaign_revision"] = campaign_revision
        slot_ref, slot_sha = write_content_addressed(base, "INNOVATION_SLOT_MAP", slot_map)

        committed_lint = dict(lint)
        committed_lint["slot_map_ref"] = slot_ref
        committed_lint["slot_map_sha256"] = slot_sha
        lint_ref, lint_sha = write_content_addressed(base, "NON_PAPERNEXUS_IDEA_LINT", committed_lint)

        if current_sha(gate_path) != observed_gate_sha:
            return {"complete": False, "error": "gate changed during locked materialization"}
        if current_sha(campaign_path) != campaign_sha:
            return {"complete": False, "error": "campaign changed during locked materialization"}

        gate = {
            "schema_version": 1,
            "status": "passed",
            "evidence_source_mode": "external_material",
            "lane_attempts_satisfied": True,
            "screening_completed": True,
            "commit_layout": "content_addressed_v1",
            "innovation_slot_map_path": slot_ref,
            "slot_map_ref": slot_ref,
            "campaign_ref": str(CAMPAIGN_REL),
            "campaign_sha256": campaign_sha,
            "campaign_id": campaign_id,
            "campaign_revision": campaign_revision,
            "lint_ref": lint_ref,
            "lint_sha256": lint_sha,
            "slot_map_sha256": slot_sha,
            "admitted_candidate_ids": lint.get("admitted_candidate_ids"),
            "lane_coverage": lint.get("evidence_lane_counts"),
            "allowed_next_action": "generate_experiment_idea_pool",
            "claim_limits": campaign.get("claim_limits"),
            "committed_at": utc_now(),
        }
        atomic_write_json(gate_path, gate)
        return {
            "complete": True,
            "idempotent": False,
            "campaign_sha256": campaign_sha,
            "lint_sha256": lint_sha,
            "lint_ref": lint_ref,
            "slot_map_sha256": slot_sha,
            "slot_map_ref": slot_ref,
            "gate_sha256": sha256_file(gate_path),
            "gate_ref": str(GATE_REL),
        }


def scaffold(direction: str) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "replace-with-stable-campaign-id",
        "campaign_revision": 1,
        "parent_campaign_sha256": None,
        "direction": direction,
        "status": "draft",
        "source_mode": "external_material",
        "papernexus_used": False,
        "method_reference": {
            "paper": "arXiv:2607.04439",
            "paper_version": "v1",
            "official_repo": "https://github.com/microsoft/ResearchStudio",
            "repo_commit": "868f0e9c30685b72ebd475f0dada1492a1982168",
            "workflow": "ResearchStudio-Idea Phase 0-4 plus local bounded GPU handoff",
        },
        "deck_aggregate_sha256": PINNED_DECK_AGGREGATE_SHA256,
        "constraints": {
            "candidate_count_min": 8,
            "candidate_count_max": 12,
            "shortlist_min": 3,
            "shortlist_max": 5,
            "max_admitted_tracks": 4,
            "quick_campaign_gpu_hours": 4,
            "max_candidate_gpu_hours": 1,
            "max_random_seeds": 3,
        },
        "claim_limits": ["All rapid runs are pilot_only; paper-report comparison not established."],
        "evidence_readiness": "not_ready",
        "literature_search_trace": [],
        "evidence_records": [],
        "method_lineage": {"nodes": [], "edges": []},
        "anchor_gap_id": None,
        "structural_gaps": [],
        "candidates": [],
        "shortlisted_candidate_ids": [],
        "admitted_candidate_ids": [],
    }


def campaign_authoring_template(direction: str) -> Dict[str, Any]:
    """Return a synthetic, non-materializable campaign with eight full candidate shapes."""
    evidence_specs = [
        ("replace-target-1", "target_domain", ["bottleneck_support", "closest_anchor"]),
        ("replace-target-2", "target_domain", ["bottleneck_support", "negative_evidence"]),
        ("replace-near-1", "near_neighbor", ["mechanism", "transfer_bridge"]),
        ("replace-far-1", "far_neighbor", ["mechanism", "transfer_bridge"]),
    ]
    evidence_records: List[Dict[str, Any]] = []
    for evidence_id, lane, roles in evidence_specs:
        excerpt = f"SYNTHETIC AUTHORING PLACEHOLDER for {evidence_id}; replace from a verified source."
        evidence_records.append(
            {
                "id": evidence_id,
                "lane": lane,
                "source_type": "paper",
                "provider": "replace-with-non-PaperNexus-provider",
                "source_ref": f"https://replace.invalid/{evidence_id}",
                "title": f"Replace synthetic {lane} evidence",
                "locator": "replace-with-exact-method-locator",
                "excerpt": excerpt,
                "excerpt_sha256": sha256_bytes(excerpt.encode("utf-8")),
                "evidence_level": "method_section",
                "full_text_status": "method_section_acquired",
                "source_verification_status": "verified_against_source",
                "source_verification_limit": "Synthetic template only; replace and independently verify.",
                "citable": True,
                "roles": roles,
            }
        )

    def candidate(index: int) -> Dict[str, Any]:
        candidate_id = f"replace-candidate-{index:02d}"
        checks = {
            name: {
                "verdict": "pass",
                "rationale": f"Replace synthetic rationale for {name}.",
                "hard_floor_triggered": False,
            }
            for name in CHECK_NAMES
        }
        row: Dict[str, Any] = {
            "id": candidate_id,
            "status": "candidate",
            "title": f"Replace synthetic candidate {index:02d}",
            "research_question": "Replace with one falsifiable research question.",
            "contribution_type": "ALGO",
            "gap_closures": [
                {
                    "gap_ref": "replace-gap-additive",
                    "role": "primary",
                    "main_pattern": "reframe_as_solvable_object",
                    "subpattern": "C00",
                    "structural_fit": "Replace with source-bound structural fit.",
                    "recipe_application": "Replace with the concrete pattern recipe application.",
                    "expected_artifact": "Replace with the method artifact.",
                },
                {
                    "gap_ref": "replace-gap-subtractive",
                    "role": "secondary",
                    "main_pattern": "assumption_audit_and_pivot",
                    "subpattern": "C01",
                    "structural_fit": "Replace with the shared-assumption fit.",
                    "recipe_application": "Replace with the assumption relaxation procedure.",
                    "expected_artifact": "Replace with the isolating ablation.",
                },
            ],
            "mechanism": {
                "intervention": "Replace with one intervention.",
                "one_variable_change": "Replace with one controlled variable change.",
                "load_bearing_variable": "replace-load-bearing-variable",
                "predicted_observation": "Replace with the matched predicted observation.",
                "falsifier": "Replace with an outcome that falsifies the mechanism.",
                "alternative_explanation": "Replace with the strongest alternative explanation.",
                "method_steps": [
                    {"id": "step-1", "action": "Replace with the first build action."},
                    {"id": "step-2", "action": "Replace with the second build action."},
                ],
            },
            "negative_control": {
                "intervention": "Replace with a non-tautological negative control.",
                "expected_if_mechanism_true": "Replace with the control prediction.",
                "downstream_metric": "replace-primary-metric",
                "non_tautology_rationale": "Replace with why the control isolates the mechanism.",
            },
            "collision_audit": {
                "signature_terms": ["replace-signature-term"],
                "signature_window_months": 10,
                "alias_terms": ["replace-alias-term"],
                "alias_window_months": 48,
                "query_trace": [
                    {
                        "channel": "signature",
                        "query": "replace signature query",
                        "searched_at": "replace-with-UTC-timestamp",
                        "provider": "replace-with-non-PaperNexus-provider",
                        "result_refs": ["replace-target-1"],
                    },
                    {
                        "channel": "alias",
                        "query": "replace alias query",
                        "searched_at": "replace-with-UTC-timestamp",
                        "provider": "replace-with-non-PaperNexus-provider",
                        "result_refs": ["replace-near-1"],
                    },
                ],
                "status": "no_threat_found",
                "search_limitations": "Synthetic template; repeat bounded live retrieval before use.",
                "claim_limit": "No novelty certificate.",
            },
            "quality_gauntlet": {
                "checks": checks,
                "verdict": "advance",
                "verdict_layer": "soft_judgment",
                "revision_targets": [],
                "repair": {"count": 0},
            },
            "implementability_audit": {
                "generation_context_id": f"replace-generation-{index:02d}",
                "reviewer_context_id": f"replace-independent-review-{index:02d}",
                "reviewer_role": "skeptical_engineer",
                "status": "passed",
                "enriched_steps": [
                    {
                        "id": "step-1",
                        "what_changes": "Replace with exact change.",
                        "build_procedure": "Replace with exact procedure.",
                        "inputs": ["replace-input"],
                        "outputs": ["replace-output"],
                    },
                    {
                        "id": "step-2",
                        "what_changes": "Replace with exact change.",
                        "build_procedure": "Replace with exact procedure.",
                        "inputs": ["replace-input"],
                        "outputs": ["replace-output"],
                    },
                ],
                "underspecified_points": [
                    {
                        "step_id": "step-2",
                        "hole": "Replace with identified hole.",
                        "fill": "Replace with concrete fill.",
                        "severity": "filled",
                        "load_bearing": True,
                    }
                ],
                "protected_commitments_present": False,
            },
            "rapid_validation": {
                "evidence_tier": "pilot_only",
                "claim_intent": "candidate_screening",
                "baseline_code": {
                    "source_ref": "https://replace.invalid/baseline",
                    "revision": "replace-with-immutable-revision",
                    "resolved_path": "/replace/with/local/baseline/path",
                    "train_entrypoint": "replace-train-entrypoint",
                    "eval_entrypoint": "replace-eval-entrypoint",
                    "comparison_label": "paper-report comparison not established",
                    "locked": True,
                },
                "dataset": {
                    "name": "replace-dataset",
                    "proxy_rationale": "Replace with the smallest protocol-aligned proxy rationale.",
                    "split": "replace-locked-split",
                },
                "metric_policy": {
                    "primary_metric": "replace-primary-metric",
                    "direction": "higher",
                    "locked": True,
                },
                "evaluation_command": "replace-with-evaluation-command",
                "decision_class": "falsify_core_mechanism",
                "expected_decision_change": "Replace with the decision changed by this pilot.",
                "resource_request": {
                    "compute_backend": "local_gpu",
                    "execution_route": "local",
                    "gpu_count": 1,
                    "estimated_gpu_hours": 0.5,
                    "walltime_minutes": 30,
                    "smoke_minutes": 5,
                },
                "seed_policy": {
                    "planned_seed_count": 1,
                    "max_random_seeds": 3,
                    "seed": 1000 + index,
                    "retry_reuses_seed": True,
                },
                "outcome_routes": {
                    "valid_positive_candidate": "survivor only; require matched confirmation and ablation",
                    "valid_negative": "lower belief or retire",
                    "valid_inconclusive": "allow at most one decision-changing discriminator",
                    "infrastructure_failure": "no hypothesis belief change",
                    "implementation_failure": "no hypothesis belief change",
                    "protocol_invalid": "no hypothesis belief change",
                },
            },
        }
        row["protected_commitments"] = {
            "payload": protected_payload(row),
            "sha256": protected_digest(row),
        }
        return row

    template = scaffold(direction)
    template.update(
        {
            "_template_metadata": {
                "synthetic": True,
                "authoring_only": True,
                "materialization_forbidden": True,
                "instruction": "Replace every synthetic/replace-* value, verify sources, then remove _template_metadata.",
            },
            "literature_search_trace": [
                {
                    "query": "replace with exact search query",
                    "provider": "replace-with-non-PaperNexus-provider",
                    "searched_at": "replace-with-UTC-timestamp",
                    "covered_time_range": "replace-with-covered-range",
                    "result_refs": [row["id"] for row in evidence_records],
                    "full_text_status": "method_sections_cached",
                    "source_verification_limit": "Synthetic authoring-only trace; replace completely.",
                }
            ],
            "evidence_records": evidence_records,
            "method_lineage": {
                "nodes": [
                    {
                        "id": "replace-method-a",
                        "label": "Replace citable method A",
                        "provenance": "external_citable",
                        "citable": True,
                        "evidence_refs": ["replace-target-1"],
                    },
                    {
                        "id": "replace-method-b",
                        "label": "Replace citable method B",
                        "provenance": "external_citable",
                        "citable": True,
                        "evidence_refs": ["replace-target-2"],
                    },
                ],
                "edges": [
                    {
                        "source": "replace-method-a",
                        "target": "replace-method-b",
                        "relation": "replace-explicit-relation",
                        "evidence_refs": ["replace-target-1", "replace-target-2"],
                    }
                ],
            },
            "anchor_gap_id": "replace-gap-additive",
            "structural_gaps": [
                {
                    "id": "replace-gap-additive",
                    "type": "additive_leaf",
                    "description": "Replace with a source-backed missing leaf.",
                    "lineage_node_refs": ["replace-method-b"],
                    "evidence_refs": ["replace-target-1", "replace-target-2"],
                    "missing_leaf": "replace-missing-leaf",
                },
                {
                    "id": "replace-gap-subtractive",
                    "type": "subtractive_shared_assumption",
                    "description": "Replace with a source-backed shared assumption.",
                    "lineage_node_refs": ["replace-method-a", "replace-method-b"],
                    "evidence_refs": ["replace-target-1", "replace-target-2"],
                    "shared_assumption": "replace-shared-assumption",
                },
            ],
            "candidates": [candidate(index) for index in range(1, 9)],
        }
    )
    return template


def panel_scaffold() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "draft",
        "verdict": "revise",
        "generation_context_id": "replace-with-generation-context-id",
        "reviewer_context_id": "replace-with-independent-review-context-id",
        "reviewer_role": "independent_panel",
        "external_campaign_ref": str(CAMPAIGN_REL),
        "external_campaign_sha256": "replace-with-current-campaign-sha256",
        "reviewed_candidate_ids": ["replace-with-admitted-candidate-id"],
        "rationale": "Replace with an evidence-bound independent panel rationale.",
        "created_at": "replace-with-UTC-timestamp",
    }


def expected_sha_matches(expected: str, observed: Optional[str]) -> bool:
    token = expected.strip().lower()
    if token == "absent":
        return observed is None
    return bool(SHA_RE.fullmatch(token) and token == observed)


def read_input_object(path: str) -> Optional[Dict[str, Any]]:
    return read_json(Path(path).expanduser().resolve())


def seed_campaign(project: str, input_path: str, expected_campaign: str) -> Dict[str, Any]:
    payload = read_input_object(input_path)
    if payload is None or nonfinite_paths(payload, "campaign"):
        return {"complete": False, "error": "seed input must be a strict finite JSON object"}
    with tempfile.TemporaryDirectory(prefix="gpu-idea-seed-validate-") as raw:
        validation_root = Path(raw)
        atomic_write_json(ar_root(str(validation_root)) / CAMPAIGN_REL, payload)
        validation = lint_campaign(str(validation_root))
    if not validation.get("complete"):
        return {"complete": False, "error": "seed campaign validation failed", "details": validation}

    base = ar_root(project)
    campaign_path = base / CAMPAIGN_REL
    gate_path = base / GATE_REL
    new_campaign_sha = sha256_bytes(serialized_json_bytes(payload))
    with materialize_lock(base / LOCK_REL):
        observed_campaign_sha = current_sha(campaign_path)
        if not expected_sha_matches(expected_campaign, observed_campaign_sha):
            return {
                "complete": False,
                "error": "campaign CAS mismatch",
                "expected": expected_campaign,
                "observed": observed_campaign_sha,
            }
        current_gate = read_json(gate_path)
        if gate_path.exists() and current_gate is None:
            return {"complete": False, "error": "refusing to seed beside an invalid or unknown evidence gate"}
        if current_gate:
            if current_gate.get("evidence_source_mode") != "external_material":
                return {"complete": False, "error": "refusing to seed beside a non-external evidence gate"}
            if current_gate.get("campaign_id") != payload.get("campaign_id"):
                return {"complete": False, "error": "campaign_id is immutable across gate revisions"}
            if new_campaign_sha != current_gate.get("campaign_sha256"):
                old_revision = current_gate.get("campaign_revision")
                if not isinstance(old_revision, int) or payload.get("campaign_revision") != old_revision + 1:
                    return {"complete": False, "error": "campaign revision must increment by one"}
                if payload.get("parent_campaign_sha256") != current_gate.get("campaign_sha256"):
                    return {"complete": False, "error": "parent_campaign_sha256 does not match committed campaign"}
        if observed_campaign_sha == new_campaign_sha:
            return {
                "complete": True,
                "idempotent": True,
                "campaign_ref": str(CAMPAIGN_REL),
                "campaign_sha256": new_campaign_sha,
            }
        atomic_write_json(campaign_path, payload)
        return {
            "complete": True,
            "idempotent": False,
            "campaign_ref": str(CAMPAIGN_REL),
            "campaign_sha256": sha256_file(campaign_path),
        }


def validate_panel(panel: Dict[str, Any], campaign: Dict[str, Any], campaign_sha: str) -> List[str]:
    errors: List[str] = []
    require(
        panel,
        [
            "schema_version",
            "status",
            "verdict",
            "generation_context_id",
            "reviewer_context_id",
            "reviewer_role",
            "external_campaign_ref",
            "external_campaign_sha256",
            "reviewed_candidate_ids",
            "rationale",
            "created_at",
        ],
        "panel",
        errors,
    )
    if panel.get("schema_version") != 1 or isinstance(panel.get("schema_version"), bool):
        errors.append("panel.schema_version must be 1")
    status = str(panel.get("status") or "")
    verdict = str(panel.get("verdict") or "")
    if status not in {"passed", "blocked"}:
        errors.append("panel.status must be passed or blocked")
    if verdict not in {"advance", "revise", "abandon"}:
        errors.append("panel.verdict must be advance, revise, or abandon")
    if status == "passed" and verdict != "advance":
        errors.append("panel passed status requires verdict=advance")
    if status == "blocked" and verdict == "advance":
        errors.append("panel blocked status may not advance")
    generation_context = str(panel.get("generation_context_id") or "").strip()
    reviewer_context = str(panel.get("reviewer_context_id") or "").strip()
    if not generation_context or not reviewer_context or generation_context == reviewer_context:
        errors.append("panel generation/reviewer contexts must be non-empty and separate")
    if panel.get("reviewer_role") != "independent_panel":
        errors.append("panel.reviewer_role must be independent_panel")
    if panel.get("external_campaign_ref") != str(CAMPAIGN_REL):
        errors.append(f"panel.external_campaign_ref must be {CAMPAIGN_REL}")
    if panel.get("external_campaign_sha256") != campaign_sha:
        errors.append("panel.external_campaign_sha256 must match the current campaign")
    reviewed = strings(panel.get("reviewed_candidate_ids"))
    admitted = set(strings(campaign.get("admitted_candidate_ids")))
    if not reviewed or len(reviewed) != len(set(reviewed)) or not set(reviewed) <= admitted:
        errors.append("panel.reviewed_candidate_ids must contain unique admitted candidate ids")
    return errors


def write_panel_design_review(
    project: str,
    input_path: str,
    expected_panel: str,
) -> Dict[str, Any]:
    panel = read_input_object(input_path)
    if panel is None or nonfinite_paths(panel, "panel"):
        return {"complete": False, "error": "panel input must be a strict finite JSON object"}
    base = ar_root(project)
    panel_path = base / PANEL_REL
    campaign_path = base / CAMPAIGN_REL
    gate_path = base / GATE_REL
    with materialize_lock(base / LOCK_REL):
        observed_panel_sha = current_sha(panel_path)
        if not expected_sha_matches(expected_panel, observed_panel_sha):
            return {
                "complete": False,
                "error": "panel CAS mismatch",
                "expected": expected_panel,
                "observed": observed_panel_sha,
            }
        campaign = read_json(campaign_path)
        gate = read_json(gate_path)
        if campaign is None:
            return {"complete": False, "error": "current campaign is required"}
        campaign_sha = sha256_file(campaign_path)
        if isinstance(gate, dict) and gate.get("evidence_source_mode") == "external_material":
            gate_errors = validate_committed_gate(
                base,
                gate,
                campaign_sha,
                str(campaign.get("campaign_id") or ""),
                campaign.get("campaign_revision"),
                strings(campaign.get("admitted_candidate_ids")),
            )
            if gate_errors:
                return {"complete": False, "error": "current evidence gate is not a valid passed commit", "details": gate_errors}
        errors = validate_panel(panel, campaign, campaign_sha)
        if errors:
            return {"complete": False, "error": "panel validation failed", "details": errors}
        new_sha = sha256_bytes(serialized_json_bytes(panel))
        if observed_panel_sha == new_sha:
            return {"complete": True, "idempotent": True, "panel_ref": str(PANEL_REL), "panel_sha256": new_sha}
        atomic_write_json(panel_path, panel)
        return {
            "complete": True,
            "idempotent": False,
            "panel_ref": str(PANEL_REL),
            "panel_sha256": sha256_file(panel_path),
        }


def current_selection_fingerprint(base: Path) -> str:
    for rel in [
        Path("ideation/IDEA_DECISION_LEDGER.json"),
        Path("ideation/IDEA_NOVELTY_VENUE_SCORECARD.json"),
        Path("orchestrator/TRACK_PLAN_MATRIX.json"),
    ]:
        payload = read_json(base / rel) or {}
        value = str(payload.get("selection_fingerprint") or payload.get("selection_revision") or "").strip()
        if value:
            return value
    return ""


def migration_journal_path(base: Path, operation_id: str) -> Path:
    return base / f"ideation/EVIDENCE_AUTHORITY_MIGRATION.{operation_id}.json"


def external_gate_payload(
    campaign: Dict[str, Any],
    campaign_sha: str,
    lint: Dict[str, Any],
    lint_ref: str,
    lint_sha: str,
    slot_ref: str,
    slot_sha: str,
    panel_sha: str,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "passed",
        "evidence_source_mode": "external_material",
        "lane_attempts_satisfied": True,
        "screening_completed": True,
        "commit_layout": "content_addressed_v1",
        "innovation_slot_map_path": slot_ref,
        "slot_map_ref": slot_ref,
        "campaign_ref": str(CAMPAIGN_REL),
        "campaign_sha256": campaign_sha,
        "campaign_id": campaign.get("campaign_id"),
        "campaign_revision": campaign.get("campaign_revision"),
        "lint_ref": lint_ref,
        "lint_sha256": lint_sha,
        "slot_map_sha256": slot_sha,
        "panel_design_review_ref": str(PANEL_REL),
        "panel_design_review_sha256": panel_sha,
        "admitted_candidate_ids": lint.get("admitted_candidate_ids"),
        "lane_coverage": lint.get("evidence_lane_counts"),
        "allowed_next_action": "generate_experiment_idea_pool",
        "claim_limits": campaign.get("claim_limits"),
        "committed_at": utc_now(),
    }


def migrate_evidence_authority(
    project: str,
    expected_gate_sha: str,
    expected_selection: str,
    input_campaign_sha: str,
    *,
    apply: bool,
    fail_after: str = "",
) -> Dict[str, Any]:
    base = ar_root(project)
    gate_path = base / GATE_REL
    campaign_path = base / CAMPAIGN_REL
    with materialize_lock(base / LOCK_REL):
        current_gate, current_gate_sha = read_json_with_sha(gate_path)
        if current_gate is None or current_gate_sha != expected_gate_sha:
            return {"complete": False, "error": "gate CAS mismatch", "observed": current_gate_sha}
        if str(current_gate.get("evidence_source_mode") or "papernexus") == "external_material":
            return {"complete": False, "error": "current gate is already external_material; use normal materialize revision"}
        selection = current_selection_fingerprint(base)
        if not selection or selection != expected_selection:
            return {"complete": False, "error": "selection fingerprint CAS mismatch", "observed": selection}
        campaign, campaign_sha = read_json_with_sha(campaign_path)
        if campaign is None or campaign_sha != input_campaign_sha:
            return {"complete": False, "error": "campaign SHA-256 mismatch", "observed": campaign_sha}
        lint = lint_campaign(project)
        if lint.get("complete") is not True or lint.get("campaign_sha256") != campaign_sha:
            return {"complete": False, "error": "campaign validation failed", "details": lint}
        panel = read_json(base / PANEL_REL)
        panel_errors = validate_panel(panel or {}, campaign, campaign_sha)
        if panel_errors or panel is None or panel.get("status") != "passed" or panel.get("verdict") != "advance":
            return {
                "complete": False,
                "error": "independent panel validation failed",
                "details": panel_errors,
            }
        panel_sha = sha256_file(base / PANEL_REL)
        queue = read_json(base / "experiment/NEXT_EXPERIMENT_QUEUE.json") or {}
        conflicting_rows = [
            str(row.get("id") or "")
            for row in queue.get("rows", [])
            if isinstance(row, dict)
            and str(row.get("status") or "") in {"planned", "submitting", "needs_sync", "running"}
            and str(row.get("selection_fingerprint") or "") == selection
        ]
        if conflicting_rows:
            return {"complete": False, "error": "active selection-bound launch rows block migration", "row_ids": conflicting_rows}

        operation_id = sha256_bytes(
            canonical_bytes(
                {"old_gate_sha256": current_gate_sha, "campaign_sha256": campaign_sha, "selection_fingerprint": selection}
            )
        )[:16]
        journal_path = migration_journal_path(base, operation_id)
        existing = read_json(journal_path) or {}
        if existing.get("state") == "COMMITTED":
            return {"complete": True, "idempotent": True, "operation_id": operation_id, "journal": str(journal_path)}

        slot_map = build_slot_map(campaign, campaign_sha, list(lint.get("admitted_candidate_ids") or []))
        slot_map["campaign_id"] = campaign.get("campaign_id")
        slot_map["campaign_revision"] = campaign.get("campaign_revision")
        slot_sha = sha256_bytes(serialized_json_bytes(slot_map))
        slot_ref = str(content_ref("INNOVATION_SLOT_MAP", slot_sha))
        committed_lint = dict(lint)
        committed_lint["slot_map_ref"] = slot_ref
        committed_lint["slot_map_sha256"] = slot_sha
        lint_sha = sha256_bytes(serialized_json_bytes(committed_lint))
        lint_ref = str(content_ref("NON_PAPERNEXUS_IDEA_LINT", lint_sha))
        gate = external_gate_payload(
            campaign,
            campaign_sha,
            lint,
            lint_ref,
            lint_sha,
            slot_ref,
            slot_sha,
            panel_sha,
        )
        new_gate_sha = sha256_bytes(serialized_json_bytes(gate))
        history_root = base / AUTHORITY_HISTORY_REL / current_gate_sha
        plan = {
            "complete": True,
            "dry_run": not apply,
            "operation_id": operation_id,
            "old_gate_sha256": current_gate_sha,
            "new_gate_sha256": new_gate_sha,
            "selection_fingerprint": selection,
            "campaign_sha256": campaign_sha,
            "history_root": str(history_root),
            "journal": str(journal_path),
        }
        if not apply:
            return plan

        history_root.mkdir(parents=True, exist_ok=True)
        archive_manifest: List[Dict[str, Any]] = []
        archive_sources: List[Tuple[str, Path]] = [(str(GATE_REL), gate_path)]
        for key, value in current_gate.items():
            if not (key.endswith("_ref") or key.endswith("_path")):
                continue
            source = resolve_safe_ref(base, value)
            if source is not None and source.is_file():
                archive_sources.append((str(value), source))
        seen_sources: Set[Path] = set()
        for rel, source in archive_sources:
            resolved = source.resolve()
            if resolved in seen_sources:
                continue
            seen_sources.add(resolved)
            digest = sha256_file(source)
            target = history_root / f"{digest}.{source.name}"
            if not target.exists():
                shutil.copy2(source, target)
            if fail_after == "archive_copied":
                os._exit(86)
            if sha256_file(target) != digest:
                return {"complete": False, "error": "authority archive verification failed", "source": rel}
            archive_manifest.append({"source_ref": rel, "sha256": digest, "archive_path": str(target)})
        journal = {
            "schema_version": 1,
            "operation_id": operation_id,
            "state": "PREPARED",
            "old_gate_sha256": current_gate_sha,
            "new_gate_sha256": new_gate_sha,
            "selection_fingerprint": selection,
            "campaign_sha256": campaign_sha,
            "archive_manifest": archive_manifest,
            "old_gate_archive_path": next(
                item["archive_path"] for item in archive_manifest if item["source_ref"] == str(GATE_REL)
            ),
            "prepared_at": utc_now(),
        }
        atomic_write_json(journal_path, journal)
        if fail_after == "archive_verified":
            os._exit(86)
        write_content_addressed(base, "INNOVATION_SLOT_MAP", slot_map)
        write_content_addressed(base, "NON_PAPERNEXUS_IDEA_LINT", committed_lint)
        if current_sha(gate_path) != current_gate_sha or current_selection_fingerprint(base) != selection:
            return {"complete": False, "error": "authority changed after archive preparation"}
        atomic_write_json(gate_path, gate)
        if fail_after == "gate_replaced":
            os._exit(86)
        if sha256_file(gate_path) != new_gate_sha:
            return {"complete": False, "error": "new gate verification failed"}
        journal["state"] = "COMMITTED"
        journal["committed_at"] = utc_now()
        atomic_write_json(journal_path, journal)
        return {**plan, "dry_run": False, "idempotent": False}


def recover_authority_migration(project: str, operation_id: str) -> Dict[str, Any]:
    base = ar_root(project)
    with materialize_lock(base / LOCK_REL):
        journal_path = migration_journal_path(base, operation_id)
        journal = read_json(journal_path) or {}
        if not journal:
            return {"complete": False, "error": "migration journal missing"}
        if journal.get("state") == "COMMITTED":
            return {"complete": True, "idempotent": True, "state": "COMMITTED"}
        gate_sha = current_sha(base / GATE_REL)
        if gate_sha == journal.get("new_gate_sha256"):
            journal["state"] = "COMMITTED"
            journal["recovered_at"] = utc_now()
            atomic_write_json(journal_path, journal)
            return {"complete": True, "idempotent": False, "state": "COMMITTED"}
        if gate_sha == journal.get("old_gate_sha256"):
            journal["state"] = "ROLLED_BACK"
            journal["recovered_at"] = utc_now()
            atomic_write_json(journal_path, journal)
            return {"complete": True, "idempotent": False, "state": "ROLLED_BACK"}
        return {"complete": False, "error": "live gate matches neither migration boundary", "observed": gate_sha}


def rollback_authority_migration(project: str, operation_id: str) -> Dict[str, Any]:
    base = ar_root(project)
    with materialize_lock(base / LOCK_REL):
        journal_path = migration_journal_path(base, operation_id)
        journal = read_json(journal_path) or {}
        if not journal:
            return {"complete": False, "error": "migration journal missing"}
        if current_selection_fingerprint(base) != journal.get("selection_fingerprint"):
            return {"complete": False, "error": "downstream selection consumed or changed after migration"}
        gate_path = base / GATE_REL
        if current_sha(gate_path) == journal.get("old_gate_sha256"):
            return {"complete": True, "idempotent": True, "state": "ROLLED_BACK"}
        if current_sha(gate_path) != journal.get("new_gate_sha256"):
            return {"complete": False, "error": "live gate is outside the migration boundary"}
        archive_path = Path(str(journal.get("old_gate_archive_path") or ""))
        if not archive_path.is_file() or sha256_file(archive_path) != journal.get("old_gate_sha256"):
            return {"complete": False, "error": "old gate archive is missing or corrupt"}
        atomic_write_bytes(gate_path, archive_path.read_bytes())
        journal["state"] = "ROLLED_BACK"
        journal["rolled_back_at"] = utc_now()
        atomic_write_json(journal_path, journal)
        return {"complete": True, "idempotent": False, "state": "ROLLED_BACK"}


def cmd_init(args: argparse.Namespace) -> int:
    path = ar_root(args.project) / CAMPAIGN_REL
    if path.exists():
        print(json.dumps({"complete": True, "idempotent": True, "path": str(path)}, ensure_ascii=False, indent=2))
        return 0
    atomic_write_json(path, scaffold(args.direction))
    print(json.dumps({"complete": True, "idempotent": False, "path": str(path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    result = lint_campaign(args.project)
    if args.write_result:
        written_ref, written_sha = write_content_addressed(
            ar_root(args.project), "NON_PAPERNEXUS_IDEA_LINT_CHECK", result
        )
        result = dict(result)
        result["written_ref"] = written_ref
        result["written_sha256"] = written_sha
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("complete") else 1


def cmd_materialize(args: argparse.Namespace) -> int:
    result = materialize(args.project, args.expected_current_gate_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("complete") else 1


def cmd_migrate_evidence_authority(args: argparse.Namespace) -> int:
    result = migrate_evidence_authority(
        args.project,
        args.expected_current_gate_sha256,
        args.expected_selection_fingerprint,
        args.input_campaign_sha256,
        apply=args.apply,
        fail_after=args.fail_after,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("complete") else 1


def cmd_recover_authority_migration(args: argparse.Namespace) -> int:
    result = recover_authority_migration(args.project, args.operation_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("complete") else 1


def cmd_rollback_authority_migration(args: argparse.Namespace) -> int:
    result = rollback_authority_migration(args.project, args.operation_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("complete") else 1


def cmd_verify_gate(args: argparse.Namespace) -> int:
    result = verify_current_gate(args.project)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result.get("complete") else 1


def cmd_verify_deck(_: argparse.Namespace) -> int:
    result = verify_deck()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("complete") else 1


def cmd_template(args: argparse.Namespace) -> int:
    payload = campaign_authoring_template(args.direction) if args.kind == "campaign" else panel_scaffold()
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    result = seed_campaign(args.project, args.input, args.expected_current_campaign_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result.get("complete") else 1


def cmd_write_panel(args: argparse.Namespace) -> int:
    result = write_panel_design_review(args.project, args.input, args.expected_current_panel_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result.get("complete") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create an idempotent external campaign scaffold.")
    init.add_argument("--project", required=True)
    init.add_argument("--direction", required=True)
    init.set_defaults(func=cmd_init)
    template = sub.add_parser("template", help="Print a strict campaign or panel authoring template.")
    template.add_argument("--kind", required=True, choices=["campaign", "panel-design-review"])
    template.add_argument("--direction", default="replace-with-research-direction")
    template.set_defaults(func=cmd_template)
    seed = sub.add_parser("seed", help="CAS-write a fully valid campaign from a strict JSON input.")
    seed.add_argument("--project", required=True)
    seed.add_argument("--input", required=True)
    seed.add_argument("--expected-current-campaign-sha256", required=True, help="Current campaign SHA-256 or 'absent'.")
    seed.set_defaults(func=cmd_seed)
    check = sub.add_parser("check", help="Validate a campaign without network or remote side effects.")
    check.add_argument("--project", required=True)
    check.add_argument("--write-result", action="store_true")
    check.set_defaults(func=cmd_check)
    materialize_parser = sub.add_parser("materialize", help="Commit a valid external campaign into the existing pre-idea gate.")
    materialize_parser.add_argument("--project", required=True)
    materialize_parser.add_argument("--expected-current-gate-sha256", required=True, help="Current gate SHA-256 or 'absent'.")
    materialize_parser.set_defaults(func=cmd_materialize)
    migrate_parser = sub.add_parser(
        "migrate-evidence-authority",
        help="Dry-run or atomically replace a legacy live gate with validated external-material authority.",
    )
    migrate_parser.add_argument("--project", required=True)
    migrate_parser.add_argument("--expected-current-gate-sha256", required=True)
    migrate_parser.add_argument("--expected-selection-fingerprint", required=True)
    migrate_parser.add_argument("--input-campaign-sha256", required=True)
    migrate_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration. Without this flag the command is read-only and returns the migration plan.",
    )
    migrate_parser.add_argument(
        "--fail-after",
        choices=["archive_copied", "archive_verified", "gate_replaced"],
        default="",
        help=argparse.SUPPRESS,
    )
    migrate_parser.set_defaults(func=cmd_migrate_evidence_authority)
    recover_parser = sub.add_parser(
        "recover-authority-migration",
        help="Resolve a prepared migration journal from the live gate hash.",
    )
    recover_parser.add_argument("--project", required=True)
    recover_parser.add_argument("--operation-id", required=True)
    recover_parser.set_defaults(func=cmd_recover_authority_migration)
    rollback_parser = sub.add_parser(
        "rollback-authority-migration",
        help="Restore the archived gate when downstream selection has not consumed the migration.",
    )
    rollback_parser.add_argument("--project", required=True)
    rollback_parser.add_argument("--operation-id", required=True)
    rollback_parser.set_defaults(func=cmd_rollback_authority_migration)
    verify_gate = sub.add_parser("verify-gate", help="Read-only verification of the exact content-addressed external gate.")
    verify_gate.add_argument("--project", required=True)
    verify_gate.set_defaults(func=cmd_verify_gate)
    panel = sub.add_parser("write-panel-design-review", help="CAS-write a validated independent panel review.")
    panel.add_argument("--project", required=True)
    panel.add_argument("--input", required=True)
    panel.add_argument("--expected-current-panel-sha256", required=True, help="Current panel SHA-256 or 'absent'.")
    panel.set_defaults(func=cmd_write_panel)
    verify = sub.add_parser("verify-deck", help="Verify the pinned ResearchStudio pattern deck and license.")
    verify.set_defaults(func=cmd_verify_deck)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
