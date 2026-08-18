#!/usr/bin/env bash
set -uo pipefail

# Re-evaluate the nine failures from the fixed-budget current LastDance run.
# Claude Code receives no semantic-judge feedback. Each task gets one uncapped
# initial session and at most 15 uncapped compiler-repair sessions. The external
# semantic judge runs once, after the generation stage has ended.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

TASKS=${TASKS:-ac_automata,edmond_karp,kruskal,llrbt_delete,llrbt_insert,max_matching,prim,push_relabel,scc_tarjan}
RESULT_MODEL_NAME=${RESULT_MODEL_NAME:-lastdance-current-unlimited}
RESULTS_ROOT=${RESULTS_ROOT:-results/lastdance_current_unlimited_fail9}
WORK_ROOT=${WORK_ROOT:-.agent_runs/lastdance_current_unlimited_fail9}
SAVE_ROOT=${SAVE_ROOT:-results/lastdance_current_unlimited_fail9_semantic_gpt54_t0_provenance}
COMPILER_REPAIR_PASSES=${COMPILER_REPAIR_PASSES:-15}

echo "[unlimited fail-9] generation started"
echo "[unlimited fail-9] no dollar cap; 1 initial + up to ${COMPILER_REPAIR_PASSES} compiler repairs per task"
generation_status=0
LASTDANCE_PROFILE=robust \
TASKS="$TASKS" \
RESULT_MODEL_NAME="$RESULT_MODEL_NAME" \
RESULTS_ROOT="$RESULTS_ROOT" \
WORK_ROOT="$WORK_ROOT" \
REASONING_EFFORT=${REASONING_EFFORT:-medium} \
TASK_TIMEOUT_SECONDS=${TASK_TIMEOUT_SECONDS:-7200} \
UNLIMITED_BUDGET=1 \
COMPILER_REPAIR_PASSES="$COMPILER_REPAIR_PASSES" \
RECOVER_PENDING_TOOL=0 \
PROGRESS_GOVERNOR=0 \
PHASE_SEPARATED=0 \
HARD_CASE_ROUTING=0 \
DIAGNOSTIC_WRAPPER=0 \
LEANSEARCH_PREFLIGHT=${LEANSEARCH_PREFLIGHT:-1} \
PYTHONUNBUFFERED=1 \
bash "$SCRIPT_DIR/run_lean_claude_code_opus5.sh" || generation_status=$?

echo "[unlimited fail-9] generation finished with status $generation_status"
echo "[unlimited fail-9] terminal semantic evaluation started"
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

echo "[unlimited fail-9] semantic evaluation finished with $semantic_failures runner error(s)"
echo "[unlimited fail-9] all stages completed"
exit "$generation_status"
