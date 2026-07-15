#!/usr/bin/env python3
"""Build and maintain component-addressed execution and capability passports."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


PROJECT_REL = Path(".autoreskill/resources/PROJECT_EXECUTION_PASSPORT.json")
CAPABILITY_REL = Path(".autoreskill/resources/RESOURCE_CAPABILITY_PASSPORT.json")
LOCK_REL = Path(".autoreskill/resources/RESOURCE_PASSPORT.lock")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMPONENT_STATES = {"verified", "suspect", "invalid"}
COMPONENT_TYPES = {
    "baseline",
    "code",
    "dataset",
    "metric",
    "runtime",
    "launcher",
    "checkpoint",
    "path_mapping",
    "stability_policy",
}


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def now_iso() -> str:
    return now().isoformat()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def atomic_write_json(path: Path, value: Any, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_name, mode)
        os.replace(temp_name, path)
        if mode is not None:
            os.chmod(path, mode)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@contextmanager
def passport_lock(project: Path) -> Iterator[None]:
    path = project / LOCK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def safe_id(value: Any, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.:-]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized or fallback


def semantic_component(component: dict[str, Any]) -> dict[str, Any]:
    payload = component.get("semantic_payload")
    if not isinstance(payload, dict):
        payload = {
            key: value
            for key, value in component.items()
            if key not in {"semantic_sha256", "verified_at", "updated_at", "notes"}
        }
    return {
        "component_id": str(component.get("component_id") or ""),
        "component_type": str(component.get("component_type") or ""),
        "semantic_payload": payload,
    }


def normalize_component(component: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(component)
    normalized["component_id"] = safe_id(component.get("component_id"), "component")
    normalized["component_type"] = safe_id(component.get("component_type"), "runtime")
    semantic = semantic_component(normalized)
    normalized["semantic_payload"] = semantic["semantic_payload"]
    normalized["semantic_sha256"] = canonical_sha256(semantic)
    return normalized


def profile_hash(profile_id: str, required: list[dict[str, str]], route_requirements: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "profile_id": profile_id,
            "required_components": sorted(required, key=lambda item: item["component_id"]),
            "route_requirements": route_requirements,
        }
    )


def normalize_project_passport(payload: dict[str, Any], project: Path, revision: int) -> dict[str, Any]:
    components = [normalize_component(item) for item in payload.get("components", []) if isinstance(item, dict)]
    components.sort(key=lambda item: str(item.get("component_id") or ""))
    by_id = {str(item["component_id"]): item for item in components}
    profiles: list[dict[str, Any]] = []
    for raw in payload.get("execution_profiles", []):
        if not isinstance(raw, dict):
            continue
        profile_id = safe_id(raw.get("profile_id"), "default")
        ids = sorted({str(value) for value in raw.get("required_component_ids", []) if str(value).strip()})
        required = [
            {"component_id": component_id, "semantic_sha256": str(by_id.get(component_id, {}).get("semantic_sha256") or "")}
            for component_id in ids
        ]
        route = raw.get("route_requirements") if isinstance(raw.get("route_requirements"), dict) else {}
        profile = dict(raw)
        profile.update(
            {
                "profile_id": profile_id,
                "required_component_ids": ids,
                "required_components": required,
                "route_requirements": route,
                "execution_profile_sha256": profile_hash(profile_id, required, route),
            }
        )
        profiles.append(profile)
    profiles.sort(key=lambda item: str(item.get("profile_id") or ""))
    normalized = {
        "schema_version": 1,
        "passport_revision": revision,
        "project_id": safe_id(payload.get("project_id") or project.name, "project"),
        "project_root_ref": str(project),
        "updated_at": now_iso(),
        "components": components,
        "execution_profiles": profiles,
    }
    normalized["index_semantic_sha256"] = canonical_sha256(
        {
            "schema_version": 1,
            "project_id": normalized["project_id"],
            "components": [
                {
                    "component_id": item["component_id"],
                    "component_type": item["component_type"],
                    "semantic_sha256": item["semantic_sha256"],
                }
                for item in components
            ],
            "execution_profiles": [
                {
                    "profile_id": item["profile_id"],
                    "execution_profile_sha256": item["execution_profile_sha256"],
                }
                for item in profiles
            ],
        }
    )
    return normalized


def derived_project_spec(project: Path) -> dict[str, Any]:
    base = project / ".autoreskill"
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json")
    innovation = read_json(base / "orchestrator/INNOVATION_PACKET.json")
    components: list[dict[str, Any]] = []

    def add(component_id: str, component_type: str, semantic_payload: dict[str, Any], source_ref: str) -> None:
        if any(present(value) for value in semantic_payload.values()):
            components.append(
                {
                    "component_id": component_id,
                    "component_type": component_type,
                    "source_ref": source_ref,
                    "semantic_payload": semantic_payload,
                }
            )

    review_ref = "planner/EXPERIMENT_REVIEW_PACKET.json"
    innovation_ref = "orchestrator/INNOVATION_PACKET.json"
    add(
        "baseline:locked",
        "baseline",
        {
            "baseline_reference": review.get("baseline_reference"),
            "training_protocol": review.get("baseline_training_protocol"),
            "eval_protocol": review.get("baseline_eval_protocol"),
        },
        review_ref,
    )
    add("code:baseline", "code", {"baseline_code": review.get("baseline_code")}, review_ref)
    dataset_id = safe_id(review.get("dataset"), "target")
    add(
        f"dataset:{dataset_id}",
        "dataset",
        {
            "dataset": review.get("dataset"),
            "split": review.get("data_split"),
            "inventory": review.get("dataset_requirement_inventory"),
            "runtime_plan": review.get("dataset_runtime_plan"),
        },
        review_ref,
    )
    add(
        "metric:primary",
        "metric",
        {
            "primary_metric": review.get("primary_metric"),
            "direction": review.get("metric_direction"),
            "evaluation_command": review.get("evaluation_command"),
        },
        review_ref,
    )
    add(
        "runtime:default",
        "runtime",
        {
            "compute_backend": review.get("compute_backend"),
            "environment": review.get("runtime_environment") or innovation.get("runtime_environment"),
        },
        review_ref,
    )
    add(
        "launcher:default",
        "launcher",
        {
            "execution_route": review.get("execution_route") or innovation.get("execution_route"),
            "resource_request": review.get("resource_request"),
        },
        review_ref,
    )
    add(
        "paths:default",
        "path_mapping",
        {"path_mapping": review.get("path_mapping") or innovation.get("path_mapping")},
        review_ref,
    )
    add(
        "stability:claim-policy",
        "stability_policy",
        {"stability_seed_policy": review.get("stability_seed_policy") or innovation.get("stability_seed_policy")},
        review_ref if review else innovation_ref,
    )
    checkpoint = review.get("checkpoint") or review.get("checkpoint_ref") or innovation.get("checkpoint_ref")
    if present(checkpoint):
        add("checkpoint:default", "checkpoint", {"checkpoint": checkpoint}, review_ref)
    return {
        "project_id": project.name,
        "components": components,
        "execution_profiles": [
            {
                "profile_id": "default",
                "required_component_ids": [item["component_id"] for item in components],
                "route_requirements": {
                    "execution_route": review.get("execution_route") or innovation.get("execution_route"),
                    "gpu_count": 1,
                },
            }
        ],
    }


def lint_project_passport(passport: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if passport.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(passport.get("passport_revision"), int):
        errors.append("passport_revision must be an integer")
    components = passport.get("components") if isinstance(passport.get("components"), list) else []
    profiles = passport.get("execution_profiles") if isinstance(passport.get("execution_profiles"), list) else []
    if not components:
        errors.append("components must be non-empty")
    if not profiles:
        errors.append("execution_profiles must be non-empty")
    ids: set[str] = set()
    component_by_id: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        prefix = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{prefix} must be an object")
            continue
        component_id = str(component.get("component_id") or "")
        if not component_id or component_id in ids:
            errors.append(f"{prefix}.component_id must be nonempty and unique")
        ids.add(component_id)
        component_by_id[component_id] = component
        if str(component.get("component_type") or "") not in COMPONENT_TYPES:
            errors.append(f"{prefix}.component_type is unsupported")
        expected = canonical_sha256(semantic_component(component))
        if str(component.get("semantic_sha256") or "") != expected:
            errors.append(f"{prefix}.semantic_sha256 does not match component content")
    profile_ids: set[str] = set()
    for index, profile in enumerate(profiles):
        prefix = f"execution_profiles[{index}]"
        if not isinstance(profile, dict):
            errors.append(f"{prefix} must be an object")
            continue
        profile_id = str(profile.get("profile_id") or "")
        if not profile_id or profile_id in profile_ids:
            errors.append(f"{prefix}.profile_id must be nonempty and unique")
        profile_ids.add(profile_id)
        required_ids = profile.get("required_component_ids")
        if not isinstance(required_ids, list) or not required_ids:
            errors.append(f"{prefix}.required_component_ids must be non-empty")
            continue
        unknown = sorted(set(str(value) for value in required_ids) - ids)
        if unknown:
            errors.append(f"{prefix} references unknown components {unknown}")
        required = [
            {"component_id": component_id, "semantic_sha256": str(component_by_id.get(component_id, {}).get("semantic_sha256") or "")}
            for component_id in sorted(set(str(value) for value in required_ids))
        ]
        route = profile.get("route_requirements") if isinstance(profile.get("route_requirements"), dict) else {}
        expected = profile_hash(profile_id, required, route)
        if str(profile.get("execution_profile_sha256") or "") != expected:
            errors.append(f"{prefix}.execution_profile_sha256 does not match selected components")
    normalized = normalize_project_passport(
        passport,
        Path(str(passport.get("project_root_ref") or ".")).expanduser(),
        int(passport.get("passport_revision") or 0),
    )
    if str(passport.get("index_semantic_sha256") or "") != normalized.get("index_semantic_sha256"):
        errors.append("index_semantic_sha256 does not match the component/profile index")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "details": {"component_count": len(components), "profile_count": len(profiles)}}


def capability_semantic_sha256(passport: dict[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in passport.items()
        if key not in {"capability_revision", "updated_at", "capability_semantic_sha256"}
    }
    return canonical_sha256(semantic)


def empty_capability(project_passport: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "capability_revision": 0,
        "project_id": project_passport.get("project_id"),
        "project_passport_index_sha256": project_passport.get("index_semantic_sha256"),
        "updated_at": now_iso(),
        "pools": [],
    }


def pool_components(pool: dict[str, Any], *, at: datetime | None = None) -> dict[str, str]:
    checked_at = at or now()
    negative = pool.get("negative_cache") if isinstance(pool.get("negative_cache"), dict) else {}
    negative_expiry = parse_time(negative.get("expires_at"))
    negative_active = negative_expiry is not None and negative_expiry > checked_at
    negative_ids = {
        str(value)
        for value in negative.get("component_ids", [])
        if str(value).strip()
    } if negative_active else set()
    # Legacy negative-cache records did not identify components. Fail closed for
    # those records until they expire or a fresh scoped probe replaces them.
    if negative_active and not negative_ids:
        return {}
    verified: dict[str, str] = {}
    for proof in pool.get("components", []):
        if not isinstance(proof, dict) or str(proof.get("state") or "") != "verified":
            continue
        expires = parse_time(proof.get("expires_at"))
        if expires is not None and expires <= checked_at:
            continue
        component_id = str(proof.get("component_id") or "")
        digest = str(proof.get("semantic_sha256") or "")
        if component_id and component_id not in negative_ids and SHA256_RE.fullmatch(digest):
            verified[component_id] = digest
    return verified


def satisfied_profiles(project_passport: dict[str, Any], pool: dict[str, Any]) -> list[str]:
    verified = pool_components(pool)
    out: list[str] = []
    for profile in project_passport.get("execution_profiles", []):
        if not isinstance(profile, dict):
            continue
        required = profile.get("required_components") if isinstance(profile.get("required_components"), list) else []
        if required and all(verified.get(str(item.get("component_id") or "")) == str(item.get("semantic_sha256") or "") for item in required if isinstance(item, dict)):
            out.append(str(profile.get("execution_profile_sha256") or ""))
    return sorted(value for value in out if value)


def cmd_build_project(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    current = read_json(project / PROJECT_REL)
    spec = read_json(Path(args.input).expanduser().resolve()) if args.input else derived_project_spec(project)
    revision = int(current.get("passport_revision") or 0) + 1
    passport = normalize_project_passport(spec, project, revision)
    lint = lint_project_passport(passport)
    payload = {"ok": lint["ok"], "dry_run": args.dry_run, "passport": passport, "lint": lint}
    if lint["ok"] and not args.dry_run:
        with passport_lock(project):
            atomic_write_json(project / PROJECT_REL, passport, mode=0o600)
        payload["path"] = str(project / PROJECT_REL)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if lint["ok"] else 1


def cmd_lint_project(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    lint = lint_project_passport(read_json(project / PROJECT_REL))
    print(json.dumps(lint, indent=2, ensure_ascii=False))
    return 0 if lint["ok"] else 1


def cmd_plan_capability(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    passport = read_json(project / PROJECT_REL)
    lint = lint_project_passport(passport)
    if not lint["ok"]:
        print(json.dumps({"ok": False, "errors": lint["errors"]}, indent=2, ensure_ascii=False))
        return 1
    capability = read_json(project / CAPABILITY_REL) or empty_capability(passport)
    pool = next((item for item in capability.get("pools", []) if isinstance(item, dict) and str(item.get("pool_id") or "") == args.pool), {})
    verified = pool_components(pool)
    component_by_id = {str(item.get("component_id") or ""): item for item in passport.get("components", []) if isinstance(item, dict)}
    profiles = passport.get("execution_profiles", [])
    selected_profiles = [item for item in profiles if isinstance(item, dict) and (not args.profile or str(item.get("profile_id") or "") in args.profile)]
    required_ids = sorted({str(value) for profile in selected_profiles for value in profile.get("required_component_ids", [])})
    items: list[dict[str, Any]] = []
    total_bytes = 0
    for component_id in required_ids:
        component = component_by_id[component_id]
        digest = str(component.get("semantic_sha256") or "")
        if verified.get(component_id) == digest:
            continue
        size = component.get("expected_bytes")
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not math.isfinite(float(size)) or float(size) < 0:
            size = None
        if size is not None:
            total_bytes += int(size)
        items.append(
            {
                "component_id": component_id,
                "component_type": component.get("component_type"),
                "expected_sha256": digest,
                "source_ref": component.get("source_ref"),
                "destination_ref": (component.get("pool_destinations") or {}).get(args.pool) if isinstance(component.get("pool_destinations"), dict) else None,
                "expected_bytes": size,
                "verification_command": component.get("verification_command") or "content hash and route-specific probe required",
                "rollback": "remove only plan-owned temporary/partial path after explicit approval",
            }
        )
    plan = {
        "schema_version": 1,
        "kind": "missing_only_capability_staging_plan",
        "project_id": passport.get("project_id"),
        "project_passport_index_sha256": passport.get("index_semantic_sha256"),
        "pool_id": args.pool,
        "profile_ids": [item.get("profile_id") for item in selected_profiles],
        "created_at": now_iso(),
        "remote_mutation_authorized": False,
        "missing_items": items,
        "missing_item_count": len(items),
        "known_total_bytes": total_bytes,
        "unknown_size_count": sum(1 for item in items if item.get("expected_bytes") is None),
    }
    plan["plan_sha256"] = canonical_sha256({key: value for key, value in plan.items() if key not in {"created_at", "plan_sha256"}})
    if args.out:
        atomic_write_json(Path(args.out).expanduser().resolve(), plan, mode=0o600)
    print(json.dumps({"ok": True, "plan": plan, "out": args.out}, indent=2, ensure_ascii=False))
    return 0


def cmd_commit_capability(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    probe_path = Path(args.input).expanduser().resolve()
    probe = read_json(probe_path)
    passport = read_json(project / PROJECT_REL)
    project_lint = lint_project_passport(passport)
    if not project_lint["ok"]:
        print(json.dumps({"ok": False, "errors": project_lint["errors"]}, indent=2, ensure_ascii=False))
        return 1
    errors: list[str] = []
    pool_id = str(probe.get("pool_id") or "")
    if not pool_id:
        errors.append("probe.pool_id is required")
    if str(probe.get("project_passport_index_sha256") or "") != str(passport.get("index_semantic_sha256") or ""):
        errors.append("probe project passport index is stale")
    component_by_id = {str(item.get("component_id") or ""): item for item in passport.get("components", []) if isinstance(item, dict)}
    proofs: list[dict[str, Any]] = []
    for index, proof in enumerate(probe.get("components", [])):
        if not isinstance(proof, dict):
            errors.append(f"probe.components[{index}] must be an object")
            continue
        component_id = str(proof.get("component_id") or "")
        expected = str(component_by_id.get(component_id, {}).get("semantic_sha256") or "")
        observed = str(proof.get("semantic_sha256") or "")
        state = str(proof.get("state") or "verified")
        if not expected or observed != expected:
            errors.append(f"probe component {component_id or index} does not match the project passport")
        if state not in COMPONENT_STATES:
            errors.append(f"probe component {component_id or index} has invalid state")
        verified_at = parse_time(proof.get("verified_at"))
        expires_at = parse_time(proof.get("expires_at"))
        if verified_at is None or expires_at is None or expires_at <= verified_at:
            errors.append(f"probe component {component_id or index} requires aware verified_at/expires_at")
        if not present(proof.get("evidence_ref")):
            errors.append(f"probe component {component_id or index} requires evidence_ref")
        proofs.append(dict(proof))
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2, ensure_ascii=False))
        return 1
    with passport_lock(project):
        capability = read_json(project / CAPABILITY_REL) or empty_capability(passport)
        current_revision = int(capability.get("capability_revision") or 0)
        if current_revision != args.expected_revision:
            print(json.dumps({"ok": False, "error": "stale capability revision", "current_revision": current_revision}, indent=2))
            return 1
        pools = [item for item in capability.get("pools", []) if isinstance(item, dict)]
        existing = next((item for item in pools if str(item.get("pool_id") or "") == pool_id), None)
        if existing is None:
            existing = {"pool_id": pool_id}
            pools.append(existing)
        prior_proofs = {
            str(item.get("component_id") or ""): dict(item)
            for item in existing.get("components", [])
            if isinstance(item, dict) and str(item.get("component_id") or "").strip()
        }
        for proof in proofs:
            prior_proofs[str(proof.get("component_id") or "")] = proof
        existing.update(
            {
                "backend": probe.get("backend"),
                "execution_route": probe.get("execution_route") or probe.get("backend"),
                "account_ref": probe.get("account_ref"),
                "host_ref": probe.get("host_ref"),
                "components": sorted(prior_proofs.values(), key=lambda item: str(item.get("component_id") or "")),
                "verification_probe_ref": str(probe_path),
                "verification_probe_sha256": file_sha256(probe_path),
                "updated_at": now_iso(),
            }
        )
        negative = existing.get("negative_cache") if isinstance(existing.get("negative_cache"), dict) else {}
        remaining_negative_ids = sorted(
            set(str(value) for value in negative.get("component_ids", []))
            - set(str(proof.get("component_id") or "") for proof in proofs)
        )
        if remaining_negative_ids:
            negative["component_ids"] = remaining_negative_ids
            existing["negative_cache"] = negative
        else:
            existing.pop("negative_cache", None)
        capability.update(
            {
                "schema_version": 1,
                "project_id": passport.get("project_id"),
                "project_passport_index_sha256": passport.get("index_semantic_sha256"),
                "capability_revision": current_revision + 1,
                "updated_at": now_iso(),
                "pools": sorted(pools, key=lambda item: str(item.get("pool_id") or "")),
            }
        )
        for item in capability["pools"]:
            item["satisfied_execution_profile_sha256s"] = satisfied_profiles(passport, item)
        capability["capability_semantic_sha256"] = capability_semantic_sha256(capability)
        atomic_write_json(project / CAPABILITY_REL, capability, mode=0o600)
    print(json.dumps({"ok": True, "pool_id": pool_id, "capability_revision": capability["capability_revision"], "satisfied_execution_profile_sha256s": existing.get("satisfied_execution_profile_sha256s")}, indent=2, ensure_ascii=False))
    return 0


def cmd_invalidate_capability(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    passport = read_json(project / PROJECT_REL)
    with passport_lock(project):
        capability = read_json(project / CAPABILITY_REL)
        current_revision = int(capability.get("capability_revision") or 0)
        if current_revision != args.expected_revision:
            print(json.dumps({"ok": False, "error": "stale capability revision", "current_revision": current_revision}, indent=2))
            return 1
        pool = next((item for item in capability.get("pools", []) if isinstance(item, dict) and str(item.get("pool_id") or "") == args.pool), None)
        if pool is None:
            print(json.dumps({"ok": False, "error": f"unknown pool {args.pool}"}, indent=2))
            return 1
        requested = set(args.component_id or [])
        found: set[str] = set()
        for proof in pool.get("components", []):
            if not isinstance(proof, dict) or str(proof.get("component_id") or "") not in requested:
                continue
            proof["state"] = args.state
            proof["invalidated_at"] = now_iso()
            proof["invalidation_reason"] = args.reason
            proof["invalidation_evidence_ref"] = args.evidence_ref
            found.add(str(proof.get("component_id")))
        missing = sorted(requested - found)
        if missing:
            print(json.dumps({"ok": False, "error": "unknown pool components", "missing": missing}, indent=2))
            return 1
        pool["negative_cache"] = {
            "reason": args.reason,
            "component_ids": sorted(requested),
            "created_at": now_iso(),
            "expires_at": (now() + timedelta(minutes=args.negative_cache_minutes)).isoformat(),
        }
        pool["satisfied_execution_profile_sha256s"] = satisfied_profiles(passport, pool)
        capability["capability_revision"] = current_revision + 1
        capability["updated_at"] = now_iso()
        capability["capability_semantic_sha256"] = capability_semantic_sha256(capability)
        atomic_write_json(project / CAPABILITY_REL, capability, mode=0o600)
    print(json.dumps({"ok": True, "pool_id": args.pool, "invalidated_component_ids": sorted(requested), "capability_revision": capability["capability_revision"]}, indent=2))
    return 0


def cmd_enrich_snapshot(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    source_path = Path(args.input).expanduser().resolve()
    payload = read_json(source_path)
    snapshot = payload.get("resource_snapshot") if isinstance(payload.get("resource_snapshot"), dict) else payload
    passport = read_json(project / PROJECT_REL)
    capability = read_json(project / CAPABILITY_REL)
    capability_by_pool = {str(item.get("pool_id") or ""): item for item in capability.get("pools", []) if isinstance(item, dict)}
    pools: list[dict[str, Any]] = []
    for raw in snapshot.get("pools", []):
        if not isinstance(raw, dict):
            continue
        pool = dict(raw)
        pool_id = str(pool.get("pool_id") or "")
        capability_pool = capability_by_pool.get(pool_id, {})
        satisfied = satisfied_profiles(passport, capability_pool) if capability_pool else []
        pool.update(
            {
                "capability_enforced": True,
                "capability_passport_sha256": capability.get("capability_semantic_sha256"),
                "project_passport_index_sha256": passport.get("index_semantic_sha256"),
                "execution_profile_sha256s": satisfied,
                "capability_fit_count": len(satisfied),
                "capability_negative_cache": capability_pool.get("negative_cache"),
            }
        )
        pools.append(pool)
    enriched = dict(snapshot)
    enriched["pools"] = pools
    enriched["capability_enriched"] = True
    enriched["capability_enriched_at"] = now_iso()
    enriched["project_passport_index_sha256"] = passport.get("index_semantic_sha256")
    enriched["capability_passport_sha256"] = capability.get("capability_semantic_sha256")
    enriched["source_snapshot_sha256"] = canonical_sha256(snapshot)
    enriched["resource_snapshot_sha256"] = canonical_sha256({key: value for key, value in enriched.items() if key != "resource_snapshot_sha256"})
    out_path = Path(args.out).expanduser().resolve()
    atomic_write_json(out_path, enriched, mode=0o600)
    print(json.dumps({"ok": True, "out": str(out_path), "pool_count": len(pools), "fitting_profile_count": sum(len(item.get("execution_profile_sha256s") or []) for item in pools)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-project")
    build.add_argument("--project", required=True)
    build.add_argument("--input")
    build.add_argument("--dry-run", action="store_true")
    build.set_defaults(func=cmd_build_project)
    lint = sub.add_parser("lint-project")
    lint.add_argument("--project", required=True)
    lint.set_defaults(func=cmd_lint_project)
    plan = sub.add_parser("plan-capability")
    plan.add_argument("--project", required=True)
    plan.add_argument("--pool", required=True)
    plan.add_argument("--profile", action="append")
    plan.add_argument("--out")
    plan.set_defaults(func=cmd_plan_capability)
    commit = sub.add_parser("commit-capability")
    commit.add_argument("--project", required=True)
    commit.add_argument("--input", required=True)
    commit.add_argument("--expected-revision", type=int, required=True)
    commit.set_defaults(func=cmd_commit_capability)
    invalidate = sub.add_parser("invalidate-capability")
    invalidate.add_argument("--project", required=True)
    invalidate.add_argument("--pool", required=True)
    invalidate.add_argument("--component-id", action="append", required=True)
    invalidate.add_argument("--state", choices=["suspect", "invalid"], default="suspect")
    invalidate.add_argument("--reason", required=True)
    invalidate.add_argument("--evidence-ref", required=True)
    invalidate.add_argument("--negative-cache-minutes", type=int, default=30)
    invalidate.add_argument("--expected-revision", type=int, required=True)
    invalidate.set_defaults(func=cmd_invalidate_capability)
    enrich = sub.add_parser("enrich-snapshot")
    enrich.add_argument("--project", required=True)
    enrich.add_argument("--input", required=True)
    enrich.add_argument("--out", required=True)
    enrich.set_defaults(func=cmd_enrich_snapshot)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
