#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

"$SCRIPT_DIR/run_task_gpt-5-5.sh" "$@"
"$SCRIPT_DIR/run_task_gpt-5-6-sol.sh" "$@"
"$SCRIPT_DIR/run_task_claude-opus-5.sh" "$@"
