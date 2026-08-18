#!/usr/bin/env bash
set -uo pipefail

# LastDance: constrained Claude Code + Opus 5 evaluation harness.

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
LASTDANCE_PROFILE=${LASTDANCE_PROFILE:-legacy}
REASONING_EFFORT=${REASONING_EFFORT:-medium}
RESULTS_ROOT=${RESULTS_ROOT:-results/claude_code_opus5}
WORK_ROOT=${WORK_ROOT:-.agent_runs/claude_code_opus5}
CFG_PATH=${CFG_PATH:-test/config_test.yaml}
TASK_TIMEOUT_SECONDS=${TASK_TIMEOUT_SECONDS:-7200}
MAX_BUDGET_USD=${MAX_BUDGET_USD:-2}
REPAIR_BUDGET_USD=${REPAIR_BUDGET_USD:-2}
UNLIMITED_BUDGET=${UNLIMITED_BUDGET:-0}
COMPILER_REPAIR_PASSES=${COMPILER_REPAIR_PASSES:-1}
RECOVER_PENDING_TOOL=${RECOVER_PENDING_TOOL:-0}
PROGRESS_GOVERNOR=${PROGRESS_GOVERNOR:-0}
PRE_EDIT_TIMEOUT_SECONDS=${PRE_EDIT_TIMEOUT_SECONDS:-300}
PRE_EDIT_THINKING_TOKENS=${PRE_EDIT_THINKING_TOKENS:-12000}
POST_EDIT_CHECK_TIMEOUT_SECONDS=${POST_EDIT_CHECK_TIMEOUT_SECONDS:-180}
RESCUE_PRE_EDIT_TIMEOUT_SECONDS=${RESCUE_PRE_EDIT_TIMEOUT_SECONDS:-600}
RESCUE_PRE_EDIT_THINKING_TOKENS=${RESCUE_PRE_EDIT_THINKING_TOKENS:-30000}
RESCUE_POST_EDIT_CHECK_TIMEOUT_SECONDS=${RESCUE_POST_EDIT_CHECK_TIMEOUT_SECONDS:-300}
PHASE_SEPARATED=${PHASE_SEPARATED:-0}
PLANNING_BUDGET_USD=${PLANNING_BUDGET_USD:-0.4}
PLANNING_EFFORT=${PLANNING_EFFORT:-low}
HARD_CASE_ROUTING=${HARD_CASE_ROUTING:-0}
DIAGNOSTIC_WRAPPER=${DIAGNOSTIC_WRAPPER:-0}
ALGORITHM_PLAN=${ALGORITHM_PLAN:-}
LEMMA_PLAN=${LEMMA_PLAN:-}
LEANSEARCH=${LEANSEARCH:-}
SEMANTIC_AUDIT=${SEMANTIC_AUDIT:-}
SEMANTIC_REMINDER=${SEMANTIC_REMINDER:-}
EARLY_CHECK=${EARLY_CHECK:-}
BACKTRACKING=${BACKTRACKING:-}
FEEDBACK_MODE=${FEEDBACK_MODE:-}
STAGNATION_THRESHOLD=${STAGNATION_THRESHOLD:-}
MAX_CHECKPOINTS=${MAX_CHECKPOINTS:-20}
MAX_COMPILER_CHECKS=${MAX_COMPILER_CHECKS:-0}
LEANSEARCH_ROOT=${LEANSEARCH_ROOT:-}
LEANSEARCH_PYTHON=${LEANSEARCH_PYTHON:-}
LEANSEARCH_URL=${LEANSEARCH_URL:-}
LEANSEARCH_RESULTS=${LEANSEARCH_RESULTS:-5}
LEANSEARCH_TIMEOUT=${LEANSEARCH_TIMEOUT:-120}
LEANSEARCH_PREFLIGHT=${LEANSEARCH_PREFLIGHT:-1}
LEANSEARCH_RERANK=${LEANSEARCH_RERANK:-1}
LEANSEARCH_RETRIEVE_K=${LEANSEARCH_RETRIEVE_K:-}
EXCLUDE_TEACHER_SORRY=${EXCLUDE_TEACHER_SORRY:-0}
REUSE_WORKSPACE=${REUSE_WORKSPACE:-0}
TASK=${TASK:-}
TASKS=${TASKS:-}
RERUN=${RERUN:-0}
RERUN_FAILED=${RERUN_FAILED:-0}
LIST_ONLY=${LIST_ONLY:-0}

case "$UNLIMITED_BUDGET" in
    0)
        ;;
    1)
        # Omitting Claude Code's --max-budget-usd option removes the monetary
        # cap. The wall-clock timeout and compiler-repair limit still apply.
        MAX_BUDGET_USD=
        REPAIR_BUDGET_USD=
        ;;
    *)
        echo "UNLIMITED_BUDGET must be 0 or 1." >&2
        exit 2
        ;;
esac

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
    --profile "$LASTDANCE_PROFILE"
    --effort "$REASONING_EFFORT"
    --results-root "$RESULTS_ROOT"
    --work-root "$WORK_ROOT"
    --config "$CFG_PATH"
    --timeout-seconds "$TASK_TIMEOUT_SECONDS"
    --max-checkpoints "$MAX_CHECKPOINTS"
    --max-compiler-checks "$MAX_COMPILER_CHECKS"
    --leansearch-results "$LEANSEARCH_RESULTS"
    --leansearch-timeout "$LEANSEARCH_TIMEOUT"
    --pre-edit-timeout-seconds "$PRE_EDIT_TIMEOUT_SECONDS"
    --pre-edit-thinking-tokens "$PRE_EDIT_THINKING_TOKENS"
    --post-edit-check-timeout-seconds "$POST_EDIT_CHECK_TIMEOUT_SECONDS"
    --rescue-pre-edit-timeout-seconds "$RESCUE_PRE_EDIT_TIMEOUT_SECONDS"
    --rescue-pre-edit-thinking-tokens "$RESCUE_PRE_EDIT_THINKING_TOKENS"
    --rescue-post-edit-check-timeout-seconds "$RESCUE_POST_EDIT_CHECK_TIMEOUT_SECONDS"
    --planning-budget-usd "$PLANNING_BUDGET_USD"
    --planning-effort "$PLANNING_EFFORT"
)
[[ "$LEANSEARCH_PREFLIGHT" == "0" ]] && args+=(--no-leansearch-preflight)
[[ "$LEANSEARCH_RERANK" == "0" ]] && args+=(--no-leansearch-rerank)
[[ -n "$LEANSEARCH_RETRIEVE_K" ]] && args+=(--leansearch-retrieve-k "$LEANSEARCH_RETRIEVE_K")

append_boolean_override() {
    local value=$1
    local option=$2
    if [[ "$value" == "1" ]]; then
        args+=("--$option")
    elif [[ "$value" == "0" ]]; then
        args+=("--no-$option")
    elif [[ -n "$value" ]]; then
        echo "$option must be 0, 1, or empty (profile default)." >&2
        exit 2
    fi
}

[[ -n "$TASK" ]] && args+=(--task "$TASK")
[[ -n "$TASKS" ]] && args+=(--tasks "$TASKS")
[[ -n "$MAX_BUDGET_USD" ]] && args+=(--max-budget-usd "$MAX_BUDGET_USD")
[[ -n "$REPAIR_BUDGET_USD" ]] && args+=(--repair-budget-usd "$REPAIR_BUDGET_USD")
args+=(--compiler-repair-passes "$COMPILER_REPAIR_PASSES")
append_boolean_override "$ALGORITHM_PLAN" algorithm-plan
append_boolean_override "$LEMMA_PLAN" lemma-plan
append_boolean_override "$LEANSEARCH" leansearch
append_boolean_override "$SEMANTIC_AUDIT" semantic-audit
append_boolean_override "$SEMANTIC_REMINDER" semantic-reminder
append_boolean_override "$EARLY_CHECK" early-check
append_boolean_override "$BACKTRACKING" backtracking
append_boolean_override "$RECOVER_PENDING_TOOL" recover-pending-tool
append_boolean_override "$PROGRESS_GOVERNOR" progress-governor
append_boolean_override "$PHASE_SEPARATED" phase-separated
append_boolean_override "$HARD_CASE_ROUTING" hard-case-routing
append_boolean_override "$DIAGNOSTIC_WRAPPER" diagnostic-wrapper
[[ -n "$FEEDBACK_MODE" ]] && args+=(--feedback-mode "$FEEDBACK_MODE")
[[ -n "$STAGNATION_THRESHOLD" ]] && args+=(--stagnation-threshold "$STAGNATION_THRESHOLD")
[[ -n "$LEANSEARCH_ROOT" ]] && args+=(--leansearch-root "$LEANSEARCH_ROOT")
[[ -n "$LEANSEARCH_PYTHON" ]] && args+=(--leansearch-python "$LEANSEARCH_PYTHON")
[[ -n "$LEANSEARCH_URL" ]] && args+=(--leansearch-url "$LEANSEARCH_URL")
[[ "$EXCLUDE_TEACHER_SORRY" == "1" ]] && args+=(--exclude-teacher-sorry)
[[ "$REUSE_WORKSPACE" == "1" ]] && args+=(--reuse-workspace)
[[ "$RERUN" == "1" ]] && args+=(--rerun)
[[ "$RERUN_FAILED" == "1" ]] && args+=(--rerun-failed)
[[ "$LIST_ONLY" == "1" ]] && args+=(--dry-run)

exec "$PYTHON_BIN" scripts/run_claude_code_lean.py "${args[@]}"
