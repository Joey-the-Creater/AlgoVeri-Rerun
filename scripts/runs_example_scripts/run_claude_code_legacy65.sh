#!/usr/bin/env bash
set -uo pipefail

# Legacy architecture: the direct AlgoVeri API prompt transported through
# Claude Code, with only Solution.lean editing and the Lean compiler checker.
# The 12 tasks containing teacher-owned sorry are excluded, matching the
# established 65-case LastDance comparison scope.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

RESULT_MODEL_NAME=${RESULT_MODEL_NAME:-claude-code-api-equivalent}
# Reuse the completed fail-9 pilot roots so those cases are skipped rather
# than paid for a second time. The dashboard exposes the combined root as one
# canonical Legacy 65 experiment.
RESULTS_ROOT=${RESULTS_ROOT:-results/claude_code_api_equivalent_fail9}
WORK_ROOT=${WORK_ROOT:-.agent_runs/claude_code_api_equivalent_fail9}
SAVE_ROOT=${SAVE_ROOT:-results/claude_code_api_equivalent_fail9_semantic_gpt54_t0_provenance}
MAX_COMPILER_CHECKS=${MAX_COMPILER_CHECKS:-15}

echo "[Legacy 65] generation started"
echo "[Legacy 65] exact API prompt + Lean checker only; ${MAX_COMPILER_CHECKS} checks maximum"
echo "[Legacy 65] excluding tasks with teacher-owned sorry; existing results are resumed"
generation_status=0
LASTDANCE_PROFILE=api \
RESULT_MODEL_NAME="$RESULT_MODEL_NAME" \
RESULTS_ROOT="$RESULTS_ROOT" \
WORK_ROOT="$WORK_ROOT" \
REASONING_EFFORT=${REASONING_EFFORT:-medium} \
TASK_TIMEOUT_SECONDS=${TASK_TIMEOUT_SECONDS:-7200} \
UNLIMITED_BUDGET=1 \
COMPILER_REPAIR_PASSES=0 \
MAX_COMPILER_CHECKS="$MAX_COMPILER_CHECKS" \
EXCLUDE_TEACHER_SORRY=1 \
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

echo "[Legacy 65] generation finished with status $generation_status"
echo "[Legacy 65] terminal semantic evaluation started"
semantic_status=0
TEST_MODEL="$RESULT_MODEL_NAME" \
JUDGE_MODEL=gpt-5.4 \
TEMPERATURE=0 \
REASONING_EFFORT=medium \
PROVENANCE_AWARE_JUDGE=1 \
ONLY_EXISTING_RESULTS=1 \
SKIP_EXISTING_SEMANTIC=1 \
RESULTS_ROOT="$RESULTS_ROOT" \
SAVE_ROOT="$SAVE_ROOT" \
PYTHONUNBUFFERED=1 \
bash "$SCRIPT_DIR/run_lean_semantic_filter.sh" || semantic_status=$?

echo "[Legacy 65] semantic evaluation finished with status $semantic_status"
echo "[Legacy 65] all stages completed"
if (( generation_status != 0 )); then
    exit "$generation_status"
fi
exit "$semantic_status"
