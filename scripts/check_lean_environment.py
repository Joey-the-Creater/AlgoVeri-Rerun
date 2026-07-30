#!/usr/bin/env python3
"""Check the configured Lean/Mathlib environment without making API calls."""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.verifiers.lean_verifier import LeanVerifier


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="test/config_test.yaml")
    args = parser.parse_args()

    verifier = LeanVerifier(config_path=args.config)
    result = verifier.verify(
        source="import Mathlib\n#check Nat\n",
        spec="environment check",
        filename="algoveri_environment_check",
    )

    artifact = result.get("file")
    if result.get("ok"):
        if artifact:
            Path(artifact).unlink(missing_ok=True)
        print("Lean environment check passed: local Lake can import Mathlib.")
        return 0

    print(f"Lean environment check failed: {result.get('reason')}", file=sys.stderr)
    raw = result.get("raw") or {}
    diagnostics = (raw.get("stderr") or raw.get("stdout") or "").strip()
    if diagnostics:
        print(diagnostics[:2000], file=sys.stderr)
    print("Run: bash scripts/local_setup/lean.sh", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
