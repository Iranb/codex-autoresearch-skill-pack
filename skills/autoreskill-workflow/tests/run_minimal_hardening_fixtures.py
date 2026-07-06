#!/usr/bin/env python3
"""Focused regression checks for minimal hardening contract behavior."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/minimal_hardening"


def load_contract_lint():
    spec = importlib.util.spec_from_file_location("contract_lint", ROOT / "scripts/contract_lint.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_contains(items: list[str], needle: str) -> None:
    require(any(needle in item for item in items), f"expected missing item containing {needle!r}, got {items}")


def main() -> None:
    lint = load_contract_lint()

    missing, _, _ = lint.validate_writing_hardening(FIXTURES / "pass_claim_verification/.autoreskill")
    require(not missing, f"pass_claim_verification should pass writing hardening, got {missing}")

    missing, _, _ = lint.validate_writing_hardening(FIXTURES / "fail_defensive_claim_upgrade/.autoreskill")
    require_contains(missing, "necessary_limitations_preserved")
    require_contains(missing, "unsupported claim upgrades")

    missing, _, _ = lint.validate_score_verification_hardening(FIXTURES / "fail_aggregate_slice_loss/.autoreskill")
    require_contains(missing, "regressed critical slice")
    require_contains(missing, "top-level claim_status cannot pass")

    missing, _, _ = lint.validate_score_verification_hardening(FIXTURES / "fail_mechanism_no_evidence/.autoreskill")
    require_contains(missing, "mechanism_support.evidence_ref")
    require_contains(missing, "cannot allow strong mechanism wording")

    missing, _, details = lint.validate_selected_projection_alignment(FIXTURES / "selection_pass/.autoreskill")
    require(not missing, f"selection_pass should pass selected projection alignment, got {missing}")
    require(details["idea_gate"]["selection_fingerprint"] == "idea-a/track-main/v1", "selection fingerprint should propagate")

    missing, _, _ = lint.validate_selected_projection_alignment(FIXTURES / "selection_missing_ref/.autoreskill")
    require_contains(missing, "selection_fingerprint or selected_primary_ref")

    with tempfile.TemporaryDirectory() as tmp:
        scoped_fixture = Path(tmp) / "scope_out_standalone_missing"
        shutil.copytree(FIXTURES / "scope_out_standalone_missing", scoped_fixture)
        out = lint.lint(str(scoped_fixture), "writing")
    scoped = out.get("details", {}).get("out_of_scope_with_claim_limits") or []
    require(scoped, "standalone scope should record out_of_scope_with_claim_limits")
    require(scoped[0].get("claim_limits_present") is True, "scope fixture should expose claim_limits_present=true")
    require(
        any(item.get("gate") == "paper_forensics_lint" for item in scoped),
        "standalone scope should record skipped paper_forensics_lint gate",
    )


if __name__ == "__main__":
    main()
