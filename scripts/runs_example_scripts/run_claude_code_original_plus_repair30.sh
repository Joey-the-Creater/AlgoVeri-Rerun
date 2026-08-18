#!/usr/bin/env bash
set -uo pipefail

# Add exactly one $2 preserved-workspace repair to the historical 30-task pilot.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

RESULT_MODEL_NAME=lastdance-original-plus-repair
RESULTS_ROOT=results/claude_code_original_plus_repair30
SAVE_ROOT=results/claude_code_original_plus_repair30_semantic_gpt54_t0
DEST="$RESULTS_ROOT/lean"

HARD_TASKS=(ac_automata bipartite_check edmond_karp gcd k_smallest kmp linearsys_gf2 llrbt_rotateright longest_palindrome_substring max_matching)
REMAINING_TASKS=(discrete_logarithm bellman_ford bfs cycle_detection dfs dijkstra fast_exponential insertion_sort jump_game kruskal llrbt_delete maxheap_popmax maxheap_push maximum_subarray_sum polymul_karatsuba polymul_naive prim push_relabel scc_tarjan sieve_method)
HARD_FAILURES=(ac_automata bipartite_check edmond_karp linearsys_gf2 longest_palindrome_substring max_matching)
REMAINING_FAILURES=(bellman_ford dijkstra kruskal llrbt_delete prim push_relabel scc_tarjan)
ALL_TASKS=("${HARD_TASKS[@]}" "${REMAINING_TASKS[@]}")

mkdir -p "$DEST"

seed_results() {
    local source_root=$1
    shift
    local task source destination
    for task in "$@"; do
        source="$source_root/lean/claude-code-opus-5_${task}_lean.json"
        destination="$DEST/${RESULT_MODEL_NAME}_${task}_lean.json"
        [[ -f "$source" ]] || { echo "Missing original result: $source" >&2; exit 2; }
        if [[ ! -f "$destination" ]]; then
            cp -p "$source" "$destination"
        fi
    done
}

seed_results results/claude_code_hard10 "${HARD_TASKS[@]}"
seed_results results/claude_code_opus5_nonthinking20 "${REMAINING_TASKS[@]}"

repair_group() {
    local source_root=$1
    local work_root=$2
    shift 2
    local task original destination repair_copy
    for task in "$@"; do
        original="$source_root/lean/claude-code-opus-5_${task}_lean.json"
        destination="$DEST/${RESULT_MODEL_NAME}_${task}_lean.json"
        if [[ $(jq -r '.details.agent.baseline_plus_repair // false' "$destination") == true ]]; then
            echo "[original + repair] skip completed $task"
            continue
        fi
        echo "[original + repair] repairing $task"
        LASTDANCE_PROFILE=legacy \
        TASK="$task" \
        RESULT_MODEL_NAME="$RESULT_MODEL_NAME" \
        RESULTS_ROOT="$RESULTS_ROOT" \
        WORK_ROOT="$work_root" \
        REASONING_EFFORT=medium \
        TASK_TIMEOUT_SECONDS=7200 \
        MAX_BUDGET_USD=2 \
        REPAIR_BUDGET_USD=2 \
        COMPILER_REPAIR_PASSES=0 \
        RECOVER_PENDING_TOOL=0 \
        PROGRESS_GOVERNOR=0 \
        PHASE_SEPARATED=0 \
        HARD_CASE_ROUTING=0 \
        DIAGNOSTIC_WRAPPER=0 \
        REUSE_WORKSPACE=1 \
        RERUN_FAILED=1 \
        LEANSEARCH_PREFLIGHT=0 \
        PYTHONUNBUFFERED=1 \
        bash "$SCRIPT_DIR/run_lean_claude_code_opus5.sh" || true

        if [[ $(jq -r '.details.agent.prompt_kind // ""' "$destination") != compiler_repair ]]; then
            echo "[original + repair] no completed repair result for $task; leaving the seed result unchanged" >&2
            continue
        fi
        repair_copy="$destination.repair-only"
        cp -p "$destination" "$repair_copy"
        "$REPO_ROOT/.venv/bin/python" scripts/merge_claude_repair_result.py \
            --original "$original" \
            --repair "$repair_copy" \
            --output "$destination"
    done
}

repair_group results/claude_code_hard10 .agent_runs/claude_code_hard10 "${HARD_FAILURES[@]}"
repair_group results/claude_code_opus5_nonthinking20 .agent_runs/claude_code_opus5_nonthinking20 "${REMAINING_FAILURES[@]}"

echo "[original + repair] generation stage completed"
semantic_failures=0
for task in "${ALL_TASKS[@]}"; do
    TEST_MODEL="$RESULT_MODEL_NAME" \
    JUDGE_MODEL=gpt-5.4 \
    TEMPERATURE=0 \
    REASONING_EFFORT=medium \
    PROVENANCE_AWARE_JUDGE=0 \
    ONLY_EXISTING_RESULTS=1 \
    SKIP_EXISTING_SEMANTIC=1 \
    RESULTS_ROOT="$RESULTS_ROOT" \
    SAVE_ROOT="$SAVE_ROOT" \
    TASK="$task" \
    PYTHONUNBUFFERED=1 \
    bash "$SCRIPT_DIR/run_lean_semantic_filter.sh" || semantic_failures=$((semantic_failures + 1))
done

echo "[original + repair] semantic stage completed with $semantic_failures runner error(s)"
echo "[original + repair] all stages completed"
