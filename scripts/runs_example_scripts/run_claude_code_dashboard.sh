#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN=${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}
else
    PYTHON_BIN=${PYTHON_BIN:-python3}
fi

WORK_ROOT=${WORK_ROOT:-.agent_runs/claude_code_opus5}
RESULTS_ROOT=${RESULTS_ROOT:-results/claude_code_opus5}
RESULT_MODEL_NAME=${RESULT_MODEL_NAME:-claude-code-opus-5}
RUNNER_PID_FILE=${RUNNER_PID_FILE:-}
DASHBOARD_PID_FILE=${DASHBOARD_PID_FILE:-logs/claude_code_dashboard.pid}
DASHBOARD_HOST=${DASHBOARD_HOST:-127.0.0.1}
DASHBOARD_PORT=${DASHBOARD_PORT:-8765}
TASKS=${TASKS:-}
EXPERIMENT_CATALOG=${EXPERIMENT_CATALOG:-config/dashboard_experiments.json}
DEFAULT_RUN=${DEFAULT_RUN:-claude-code-opus5-enhanced}

args=(
    --work-root "$WORK_ROOT"
    --results-root "$RESULTS_ROOT"
    --result-model-name "$RESULT_MODEL_NAME"
    --dashboard-pid-file "$DASHBOARD_PID_FILE"
    --host "$DASHBOARD_HOST"
    --port "$DASHBOARD_PORT"
    --catalog "$EXPERIMENT_CATALOG"
    --default-run "$DEFAULT_RUN"
)
[[ -n "$RUNNER_PID_FILE" ]] && args+=(--runner-pid-file "$RUNNER_PID_FILE")
[[ -n "$TASKS" ]] && args+=(--tasks "$TASKS")

exec "$PYTHON_BIN" scripts/claude_code_dashboard.py "${args[@]}"
