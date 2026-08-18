#!/usr/bin/env bash
set -uo pipefail

# Claude Code transport for the direct AlgoVeri API baseline. The agent receives
# the exact Lean API prompt plus a minimal file-I/O note, can edit Solution.lean,
# and can call only the local Lean checker (at most MAX_COMPILER_CHECKS times).

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

TASKS=${TASKS:-ac_automata,edmond_karp,kruskal,llrbt_delete,llrbt_insert,max_matching,prim,push_relabel,scc_tarjan}
RESULT_MODEL_NAME=${RESULT_MODEL_NAME:-claude-code-api-equivalent}
RESULTS_ROOT=${RESULTS_ROOT:-results/claude_code_api_equivalent_fail9}
WORK_ROOT=${WORK_ROOT:-.agent_runs/claude_code_api_equivalent_fail9}
SAVE_ROOT=${SAVE_ROOT:-results/claude_code_api_equivalent_fail9_semantic_gpt54_t0_provenance}
MAX_COMPILER_CHECKS=${MAX_COMPILER_CHECKS:-15}

echo "[Claude Code API-equivalent] generation started"
echo "[Claude Code API-equivalent] baseline prompt + Lean checker only; ${MAX_COMPILER_CHECKS} checks maximum"
generation_status=0
LASTDANCE_PROFILE=api \
TASKS="$TASKS" \
RESULT_MODEL_NAME="$RESULT_MODEL_NAME" \
RESULTS_ROOT="$RESULTS_ROOT" \
WORK_ROOT="$WORK_ROOT" \
REASONING_EFFORT=${REASONING_EFFORT:-medium} \
TASK_TIMEOUT_SECONDS=${TASK_TIMEOUT_SECONDS:-7200} \
UNLIMITED_BUDGET=1 \
COMPILER_REPAIR_PASSES=0 \
MAX_COMPILER_CHECKS="$MAX_COMPILER_CHECKS" \
ALGORITHM_PLAN=0 \
LEMMA_PLAN=0 \
LEANSEARCH=0 \
SEMANTIC_AUDIT=0 \
SEMANTIC_REMINDER=0 \
EARLY_CHECK=0 \
BACKTRACKING=0 \
FEEDBACK_MODE=exact \
RECOVER_PENDING_TOOL=0 \
PROGRESS_GOVERNOR=0 \
PHASE_SEPARATED=0 \
HARD_CASE_ROUTING=0 \
DIAGNOSTIC_WRAPPER=0 \
LEANSEARCH_PREFLIGHT=0 \
PYTHONUNBUFFERED=1 \
bash "$SCRIPT_DIR/run_lean_claude_code_opus5.sh" || generation_status=$?

echo "[Claude Code API-equivalent] generation finished with status $generation_status"
echo "[Claude Code API-equivalent] terminal semantic evaluation started"
semantic_failures=0
for task in ${TASKS//,/ }; do
    TEST_MODEL="$RESULT_MODEL_NAME" \
    JUDGE_MODEL=gpt-5.4 \
    TEMPERATURE=0 \
    REASONING_EFFORT=medium \
    PROVENANCE_AWARE_JUDGE=1 \
    ONLY_EXISTING_RESULTS=1 \
    SKIP_EXISTING_SEMANTIC=1 \
    RESULTS_ROOT="$RESULTS_ROOT" \
    SAVE_ROOT="$SAVE_ROOT" \
    TASK="$task" \
    PYTHONUNBUFFERED=1 \
    bash "$SCRIPT_DIR/run_lean_semantic_filter.sh" || semantic_failures=$((semantic_failures + 1))
done

echo "[Claude Code API-equivalent] semantic evaluation finished with $semantic_failures runner error(s)"
echo "[Claude Code API-equivalent] all stages completed"
exit "$generation_status"
