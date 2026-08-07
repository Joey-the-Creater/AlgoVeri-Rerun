#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN=${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}
else
    PYTHON_BIN=${PYTHON_BIN:-python3}
fi

CLAUDE_BIN=${CLAUDE_BIN:-claude}
CLAUDE_CODE_MODEL=${CLAUDE_CODE_MODEL:-claude-opus-5}
RESULT_MODEL_NAME=${RESULT_MODEL_NAME:-claude-code-opus-5}
REASONING_EFFORT=${REASONING_EFFORT:-medium}
RESULTS_ROOT=${RESULTS_ROOT:-results/claude_code_opus5}
WORK_ROOT=${WORK_ROOT:-.agent_runs/claude_code_opus5}
CFG_PATH=${CFG_PATH:-test/config_test.yaml}
TASK_TIMEOUT_SECONDS=${TASK_TIMEOUT_SECONDS:-7200}
MAX_BUDGET_USD=${MAX_BUDGET_USD:-2}
REPAIR_BUDGET_USD=${REPAIR_BUDGET_USD:-2}
COMPILER_REPAIR_PASSES=${COMPILER_REPAIR_PASSES:-1}
EXCLUDE_TEACHER_SORRY=${EXCLUDE_TEACHER_SORRY:-0}
REUSE_WORKSPACE=${REUSE_WORKSPACE:-0}
TASK=${TASK:-}
TASKS=${TASKS:-}
RERUN=${RERUN:-0}
RERUN_FAILED=${RERUN_FAILED:-0}
LIST_ONLY=${LIST_ONLY:-0}

if [[ "$LIST_ONLY" != "1" ]]; then
    command -v "$CLAUDE_BIN" >/dev/null 2>&1 || {
        echo "Claude Code executable not found: $CLAUDE_BIN" >&2
        exit 2
    }
    "$PYTHON_BIN" scripts/check_lean_environment.py --config "$CFG_PATH" || exit 2
fi

args=(
    --claude-bin "$CLAUDE_BIN"
    --model "$CLAUDE_CODE_MODEL"
    --result-model-name "$RESULT_MODEL_NAME"
    --effort "$REASONING_EFFORT"
    --results-root "$RESULTS_ROOT"
    --work-root "$WORK_ROOT"
    --config "$CFG_PATH"
    --timeout-seconds "$TASK_TIMEOUT_SECONDS"
)

[[ -n "$TASK" ]] && args+=(--task "$TASK")
[[ -n "$TASKS" ]] && args+=(--tasks "$TASKS")
[[ -n "$MAX_BUDGET_USD" ]] && args+=(--max-budget-usd "$MAX_BUDGET_USD")
[[ -n "$REPAIR_BUDGET_USD" ]] && args+=(--repair-budget-usd "$REPAIR_BUDGET_USD")
args+=(--compiler-repair-passes "$COMPILER_REPAIR_PASSES")
[[ "$EXCLUDE_TEACHER_SORRY" == "1" ]] && args+=(--exclude-teacher-sorry)
[[ "$REUSE_WORKSPACE" == "1" ]] && args+=(--reuse-workspace)
[[ "$RERUN" == "1" ]] && args+=(--rerun)
[[ "$RERUN_FAILED" == "1" ]] && args+=(--rerun-failed)
[[ "$LIST_ONLY" == "1" ]] && args+=(--dry-run)

exec "$PYTHON_BIN" scripts/run_claude_code_lean.py "${args[@]}"
