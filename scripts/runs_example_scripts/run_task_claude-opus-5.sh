#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MODEL=claude-opus-5 exec "$SCRIPT_DIR/run_lean_openai.sh" "$@"
