#!/usr/bin/env bash
set -uo pipefail

# Evaluate LastDance's fixed-budget current architecture on the five enhanced
# semantic failures that were outside the original 13-task budget ablation.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

TASKS=${TASKS:-bubble_sort,max_matching,polymul_naive,push_relabel,scc_tarjan}
RESULT_MODEL_NAME=${RESULT_MODEL_NAME:-lastdance-current-enhanced-fail5}
RESULTS_ROOT=${RESULTS_ROOT:-results/lastdance_current_enhanced_fail5}
WORK_ROOT=${WORK_ROOT:-.agent_runs/lastdance_current_enhanced_fail5}
SAVE_ROOT=${SAVE_ROOT:-results/lastdance_current_enhanced_fail5_semantic_gpt54_t0}

echo "[enhanced fail-5] generation started"
generation_status=0
LASTDANCE_PROFILE=robust \
TASKS="$TASKS" \
RESULT_MODEL_NAME="$RESULT_MODEL_NAME" \
RESULTS_ROOT="$RESULTS_ROOT" \
WORK_ROOT="$WORK_ROOT" \
REASONING_EFFORT=medium \
TASK_TIMEOUT_SECONDS=7200 \
MAX_BUDGET_USD=2 \
REPAIR_BUDGET_USD=2 \
COMPILER_REPAIR_PASSES=1 \
RECOVER_PENDING_TOOL=0 \
PROGRESS_GOVERNOR=0 \
PHASE_SEPARATED=0 \
HARD_CASE_ROUTING=0 \
DIAGNOSTIC_WRAPPER=0 \
PYTHONUNBUFFERED=1 \
bash "$SCRIPT_DIR/run_lean_claude_code_opus5.sh" || generation_status=$?

echo "[enhanced fail-5] generation finished with status $generation_status"
echo "[enhanced fail-5] matched semantic evaluation started"
semantic_failures=0
for task in ${TASKS//,/ }; do
    TEST_MODEL="$RESULT_MODEL_NAME" \
    JUDGE_MODEL=gpt-5.4 \
    TEMPERATURE=0 \
    REASONING_EFFORT=medium \
    PROVENANCE_AWARE_JUDGE=0 \
    ONLY_EXISTING_RESULTS=1 \
    SKIP_EXISTING_SEMANTIC=0 \
    RESULTS_ROOT="$RESULTS_ROOT" \
    SAVE_ROOT="$SAVE_ROOT" \
    TASK="$task" \
    PYTHONUNBUFFERED=1 \
    bash "$SCRIPT_DIR/run_lean_semantic_filter.sh" || semantic_failures=$((semantic_failures + 1))
done

echo "[enhanced fail-5] semantic evaluation finished with $semantic_failures runner error(s)"
echo "[enhanced fail-5] all stages completed"
exit "$generation_status"
