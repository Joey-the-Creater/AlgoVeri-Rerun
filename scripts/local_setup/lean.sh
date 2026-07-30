#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
LEAN_VERSION=${LEAN_VERSION:-4.25.0-rc2}
MATHLIB_VERSION=${MATHLIB_VERSION:-v4.25.0-rc2}
ENV_ROOT=${ENV_ROOT:-$REPO_ROOT/lean_env}
LEAN_HOME="$ENV_ROOT/lean_bin"
PROJECT_HOME="$ENV_ROOT/lean_project"
ARCHIVE="$ENV_ROOT/lean-$LEAN_VERSION-linux.tar.zst"

for tool in wget tar zstd git; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Required tool not found: $tool" >&2
        echo "On Ubuntu, install missing tools with: sudo apt install git wget zstd" >&2
        exit 2
    fi
done

mkdir -p "$ENV_ROOT"

if [[ ! -x "$LEAN_HOME/bin/lake" ]]; then
    if [[ ! -f "$ARCHIVE" ]]; then
        wget -O "$ARCHIVE" \
            "https://github.com/leanprover/lean4/releases/download/v$LEAN_VERSION/lean-$LEAN_VERSION-linux.tar.zst"
    fi
    tar --use-compress-program=unzstd -xf "$ARCHIVE" -C "$ENV_ROOT"
    mv "$ENV_ROOT/lean-$LEAN_VERSION-linux" "$LEAN_HOME"
fi

mkdir -p "$PROJECT_HOME"

if [[ ! -f "$PROJECT_HOME/lakefile.lean" ]]; then
    sed "s/@MATHLIB_VERSION@/$MATHLIB_VERSION/g" \
        "$SCRIPT_DIR/lakefile.lean.template" > "$PROJECT_HOME/lakefile.lean"
fi

printf 'leanprover/lean4:v%s\n' "$LEAN_VERSION" > "$PROJECT_HOME/lean-toolchain"

export PATH="$LEAN_HOME/bin:$PATH"
cd "$PROJECT_HOME"
lake update

echo "Local Lean/Mathlib environment is ready at: $ENV_ROOT"
echo "Verify it with: $REPO_ROOT/.venv/bin/python -m test.test_lean_verify"
