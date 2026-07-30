#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MODEL=gpt-5.6-sol exec "$SCRIPT_DIR/run_lean_openai.sh" "$@"

