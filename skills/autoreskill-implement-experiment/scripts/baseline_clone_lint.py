#!/usr/bin/env python3
"""Require experiments to patch a locked baseline clone instead of inventing code."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


CLONE_SOURCE_TYPES = {
    "git_clone",
    "github_clone",
    "official_repo_snapshot",
    "repo_snapshot",
    "local_git_worktree",
    "paper_official_repo",
}
BAD_SOURCE_MARKERS = {"fixture", "synthetic", "generated", "manual", "scratch", "self_created", "template"}
PATCH_KEYS = ["baseline_code_id", "base_revision", "patch_path", "changed_paths", "patch_applies_to_baseline"]


def ar(project: str) -> Path:
    return Path(project).expanduser().resolve() / ".autoreskill"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def resolve_project_path(project: str, raw: Any) -> Path | None:
    if not present(raw):
        return None
    root = Path(project).expanduser().resolve()
    path = Path(str(raw)).expanduser()
    return path if path.is_absolute() else root / path


def resolve_exp_path(project: str, exp_dir: Path, raw: Any) -> Path | None:
    if not present(raw):
        return None
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    candidate = exp_dir / path
    if candidate.exists():
        return candidate
    return Path(project).expanduser().resolve() / path


def rel(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def git(root: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def source_type_ok(source_type: str) -> bool:
    lowered = source_type.strip().lower()
    if lowered in CLONE_SOURCE_TYPES:
        return True
    return bool(lowered) and not any(marker in lowered for marker in BAD_SOURCE_MARKERS)


def source_ref_matches(source_ref: str, origin: str | None) -> bool:
    if not source_ref or not origin:
        return False
    normalized_source = source_ref.rstrip("/").removesuffix(".git").lower()
    normalized_origin = origin.rstrip("/").removesuffix(".git").lower()
    return normalized_source == normalized_origin or normalized_source in normalized_origin or normalized_origin in normalized_source


def validate_clone(project: str, baseline_code: dict[str, Any], missing: list[str], warnings: list[str]) -> dict[str, Any]:
    proof: dict[str, Any] = {}
    code_id = str(baseline_code.get("code_id") or "").strip()
    source_ref = str(baseline_code.get("source_ref") or "").strip()
    source_type = str(baseline_code.get("source_type") or "").strip()
    revision = str(baseline_code.get("revision") or "").strip()
    root = resolve_project_path(project, baseline_code.get("resolved_path"))

    if baseline_code.get("locked") is not True:
        missing.append("baseline_code.locked must be true")
    if not code_id:
        missing.append("baseline_code.code_id")
    if not source_ref:
        missing.append("baseline_code.source_ref")
    if not revision:
        missing.append("baseline_code.revision")
    if not source_type_ok(source_type):
        missing.append("baseline_code.source_type must be a clone/snapshot/worktree source, not generated/manual/fixture")
    if root is None or not root.exists():
        missing.append("baseline_code.resolved_path must exist as a baseline clone/worktree")
        return proof

    proof_path = root / "BASELINE_CLONE_PROOF.json"
    if (root / ".git").exists():
        inside = git(root, ["rev-parse", "--is-inside-work-tree"])
        head = git(root, ["rev-parse", "HEAD"])
        origin = git(root, ["remote", "get-url", "origin"])
        if inside != "true":
            missing.append("baseline clone path is not a git worktree")
        if revision and head and not head.startswith(revision) and not revision.startswith(head):
            missing.append(f"baseline clone HEAD {head} does not match locked revision {revision}")
        if source_ref and not source_ref_matches(source_ref, origin):
            missing.append(f"baseline clone origin {origin or '<missing>'} does not match source_ref {source_ref}")
        proof = {"kind": "git_worktree", "path": str(root), "head": head, "origin": origin}
    elif proof_path.exists():
        proof_payload = read_json(proof_path, {})
        if not isinstance(proof_payload, dict):
            missing.append("BASELINE_CLONE_PROOF.json invalid")
        else:
            if proof_payload.get("remote_verified") is not True and proof_payload.get("clone_verified") is not True:
                missing.append("BASELINE_CLONE_PROOF.json must set remote_verified=true or clone_verified=true")
            if revision and str(proof_payload.get("revision") or proof_payload.get("git_commit") or "").strip() != revision:
                missing.append("BASELINE_CLONE_PROOF.json revision does not match locked baseline revision")
            proof = proof_payload
    else:
        missing.append("baseline_code.resolved_path must contain .git or BASELINE_CLONE_PROOF.json")

    if proof and source_type not in CLONE_SOURCE_TYPES:
        warnings.append(f"baseline_code.source_type `{source_type}` accepted by proof but should be normalized to a clone/snapshot type")
    return proof


def load_patch_proof(manifest: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    for source in [manifest, audit]:
        for key in ["baseline_patch_proof", "baseline_patch", "proposed_patch_proof"]:
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, dict):
                return value
    return {}


def validate_patch_proof(
    project: str,
    base: Path,
    exp_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    audit: dict[str, Any],
    baseline_code: dict[str, Any],
    missing: list[str],
    warnings: list[str],
) -> None:
    patch = load_patch_proof(manifest, audit)
    label = rel(base, manifest_path)
    code_id = str(baseline_code.get("code_id") or "").strip()
    revision = str(baseline_code.get("revision") or "").strip()

    if not patch:
        missing.append(f"{label} baseline_patch_proof required; record a git diff/patch against the locked baseline clone")
        return

    for key in PATCH_KEYS:
        if not present(patch.get(key)):
            missing.append(f"{label} baseline_patch_proof.{key}")
    if code_id and str(patch.get("baseline_code_id") or "").strip() != code_id:
        missing.append(f"{label} baseline_patch_proof.baseline_code_id must match locked baseline")
    if revision and str(patch.get("base_revision") or "").strip() != revision:
        missing.append(f"{label} baseline_patch_proof.base_revision must match locked baseline revision")
    if patch.get("patch_applies_to_baseline") is not True:
        missing.append(f"{label} baseline_patch_proof.patch_applies_to_baseline must be true")

    patch_path = resolve_exp_path(project, exp_dir, patch.get("patch_path"))
    if patch_path is None or not patch_path.is_file() or not read_text(patch_path).strip():
        missing.append(f"{label} baseline_patch_proof.patch_path must point to a nonempty patch/diff file")
    else:
        patch_text = read_text(patch_path)
        if "diff --git" not in patch_text and "*** Begin Patch" not in patch_text:
            missing.append(f"{label} baseline_patch_proof.patch_path must contain a git/apply_patch style diff")

    changed_paths = patch.get("changed_paths")
    if not isinstance(changed_paths, list) or not changed_paths:
        missing.append(f"{label} baseline_patch_proof.changed_paths must list modified baseline paths")
    else:
        baseline_root = resolve_project_path(project, baseline_code.get("resolved_path"))
        existing_like = 0
        for raw_path in changed_paths:
            rel_path = str(raw_path).strip()
            if not rel_path or rel_path.startswith("/") or rel_path.startswith(".."):
                missing.append(f"{label} baseline_patch_proof.changed_paths contains unsafe path `{rel_path}`")
                continue
            if baseline_root and (baseline_root / rel_path).exists():
                existing_like += 1
        if baseline_root and existing_like == 0:
            missing.append(f"{label} baseline_patch_proof.changed_paths do not touch files from the locked baseline clone")

    adapter = manifest.get("baseline_adapter") if isinstance(manifest.get("baseline_adapter"), dict) else {}
    if adapter:
        if adapter.get("calls_locked_entrypoint") is not True:
            missing.append(f"{label} baseline_adapter.calls_locked_entrypoint must be true")
        if str(adapter.get("baseline_code_id") or "").strip() != code_id:
            missing.append(f"{label} baseline_adapter.baseline_code_id must match locked baseline")
        warnings.append(f"{label} uses an adapter; keep it thin and preserve patch proof against the cloned baseline")


def command_uses_baseline_or_adapter(
    manifest: dict[str, Any],
    baseline_code: dict[str, Any],
) -> tuple[bool, str]:
    commands = " ".join(
        str(manifest.get(key) or "")
        for key in ["baseline_train_command", "proposed_train_command", "evaluate_command", "train_command", "command"]
    )
    if not commands.strip():
        return False, "manifest launch command missing"
    entrypoints = [
        str(baseline_code.get("train_entrypoint") or "").strip(),
        str(baseline_code.get("eval_entrypoint") or "").strip(),
    ]
    if any(entry and entry in commands for entry in entrypoints):
        return True, "command references locked baseline entrypoint"
    adapter = manifest.get("baseline_adapter") if isinstance(manifest.get("baseline_adapter"), dict) else {}
    if adapter.get("calls_locked_entrypoint") is True and present(adapter.get("adapter_entrypoint")):
        return True, "command uses declared adapter"
    return False, "launch command must call locked baseline entrypoint or a declared adapter that calls it"


def lint(project: str) -> dict[str, Any]:
    base = ar(project)
    review = read_json(base / "planner/EXPERIMENT_REVIEW_PACKET.json", {}) or {}
    baseline_code = review.get("baseline_code") if isinstance(review.get("baseline_code"), dict) else {}
    missing: list[str] = []
    warnings: list[str] = []

    if not baseline_code:
        missing.append("planner/EXPERIMENT_REVIEW_PACKET.json baseline_code")
        baseline_code = {}
    validate_clone(project, baseline_code, missing, warnings)

    manifests = sorted(base.glob("coder/experiments/**/EXPERIMENT_MANIFEST.json"))
    if not manifests:
        missing.append("coder/experiments/**/EXPERIMENT_MANIFEST.json")
    for manifest_path in manifests:
        manifest = read_json(manifest_path, {}) or {}
        exp_dir = manifest_path.parent
        audit_path = exp_dir / str(manifest.get("baseline_data_audit") or "BASELINE_DATA_AUDIT.json")
        audit = read_json(audit_path, {}) or {}
        manifest_baseline = manifest.get("baseline_code") if isinstance(manifest.get("baseline_code"), dict) else {}
        if manifest_baseline.get("code_id") != baseline_code.get("code_id"):
            missing.append(f"{rel(base, manifest_path)} baseline_code.code_id must match review packet")
        if manifest_baseline.get("revision") != baseline_code.get("revision"):
            missing.append(f"{rel(base, manifest_path)} baseline_code.revision must match review packet")

        validate_patch_proof(project, base, exp_dir, manifest_path, manifest, audit, baseline_code, missing, warnings)
        ok, reason = command_uses_baseline_or_adapter(manifest, baseline_code)
        if not ok:
            missing.append(f"{rel(base, manifest_path)} {reason}")

    return {
        "complete": not missing,
        "status": "complete" if not missing else "incomplete",
        "missing": missing,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    out = lint(args.project)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    raise SystemExit(0 if out["complete"] else 1)


if __name__ == "__main__":
    main()
