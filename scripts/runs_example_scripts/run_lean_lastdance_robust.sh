#!/usr/bin/env bash
set -uo pipefail

# LastDance v2: robust planning, retrieval, repair, and verification.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

export LASTDANCE_PROFILE=${LASTDANCE_PROFILE:-robust}
export RESULT_MODEL_NAME=${RESULT_MODEL_NAME:-lastdance-opus-5-robust}
export RESULTS_ROOT=${RESULTS_ROOT:-results/lastdance_opus5_robust}
export WORK_ROOT=${WORK_ROOT:-.agent_runs/lastdance_opus5_robust}
export MAX_BUDGET_USD=${MAX_BUDGET_USD:-2}
export REPAIR_BUDGET_USD=${REPAIR_BUDGET_USD:-2}
export COMPILER_REPAIR_PASSES=${COMPILER_REPAIR_PASSES:-2}

exec "$SCRIPT_DIR/run_lean_claude_code_opus5.sh"
