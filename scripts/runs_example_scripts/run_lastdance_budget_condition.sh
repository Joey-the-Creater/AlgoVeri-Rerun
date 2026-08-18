#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONDITION=${CONDITION:-current}
TASKS=${TASKS:-ac_automata,bellman_ford,bipartite_check,coin_change,dijkstra,edmond_karp,kruskal,linearsys_gf2,llrbt_delete,llrbt_insert,longest_palindrome_substring,prim,topological_sort}

export LASTDANCE_PROFILE=robust
export TASKS
export REASONING_EFFORT=${REASONING_EFFORT:-medium}
export TASK_TIMEOUT_SECONDS=${TASK_TIMEOUT_SECONDS:-7200}
export LEANSEARCH_PREFLIGHT=${LEANSEARCH_PREFLIGHT:-1}
export PRE_EDIT_TIMEOUT_SECONDS=${PRE_EDIT_TIMEOUT_SECONDS:-300}
export PRE_EDIT_THINKING_TOKENS=${PRE_EDIT_THINKING_TOKENS:-12000}
export POST_EDIT_CHECK_TIMEOUT_SECONDS=${POST_EDIT_CHECK_TIMEOUT_SECONDS:-180}

export RECOVER_PENDING_TOOL=0
export PROGRESS_GOVERNOR=0
export PHASE_SEPARATED=0
export HARD_CASE_ROUTING=0
export DIAGNOSTIC_WRAPPER=0
export MAX_BUDGET_USD=2
export REPAIR_BUDGET_USD=2
export COMPILER_REPAIR_PASSES=1

case "$CONDITION" in
    current)
        ;;
    boundary)
        export RECOVER_PENDING_TOOL=1
        ;;
    governor)
        export RECOVER_PENDING_TOOL=1
        export PROGRESS_GOVERNOR=1
        ;;
    phased)
        export RECOVER_PENDING_TOOL=1
        export PROGRESS_GOVERNOR=1
        export PHASE_SEPARATED=1
        export PLANNING_BUDGET_USD=0.4
        export PLANNING_EFFORT=low
        export MAX_BUDGET_USD=1.35
        export REPAIR_BUDGET_USD=0.75
        export COMPILER_REPAIR_PASSES=3
        ;;
    full)
        export RECOVER_PENDING_TOOL=1
        export PROGRESS_GOVERNOR=1
        export PHASE_SEPARATED=1
        export HARD_CASE_ROUTING=1
        export DIAGNOSTIC_WRAPPER=1
        export PLANNING_BUDGET_USD=0.4
        export PLANNING_EFFORT=low
        export MAX_BUDGET_USD=1.35
        export REPAIR_BUDGET_USD=0.75
        export COMPILER_REPAIR_PASSES=3
        ;;
    *)
        echo "Unknown CONDITION: $CONDITION" >&2
        exit 2
        ;;
esac

export RESULT_MODEL_NAME="lastdance-budget-${CONDITION}"
export RESULTS_ROOT="results/lastdance_budget_${CONDITION}_13"
export WORK_ROOT=".agent_runs/lastdance_budget_${CONDITION}_13"

exec "$SCRIPT_DIR/run_lean_claude_code_opus5.sh"
