#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

RESULTS_ROOT=${RESULTS_ROOT:-results/full_three}
REASONING_EFFORT=${REASONING_EFFORT:-medium}
MAX_ROUNDS=${MAX_ROUNDS:-15}
NUM_PASSES=${NUM_PASSES:-1}
MAX_OUTPUT_TOKENS=${MAX_OUTPUT_TOKENS:-32768}
ANTHROPIC_THINKING=${ANTHROPIC_THINKING:-adaptive}
INVENTORY_ONLY=${INVENTORY_ONLY:-0}
WAIT_FOR_PID=${WAIT_FOR_PID:-}

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN=${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}
else
    PYTHON_BIN=${PYTHON_BIN:-python3}
fi

is_valid_json() {
    local result_file=$1
    [[ -f "$result_file" ]] &&
        "$PYTHON_BIN" -c \
            'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' \
            "$result_file" >/dev/null 2>&1
}

all_tasks=()
completed_tasks=()
pending_tasks=()

for problem_dir in algoveri_data/*; do
    [[ -d "$problem_dir" ]] || continue
    [[ -f "$problem_dir/lean_spec.lean" ]] || continue
    [[ -f "$problem_dir/lean_nl.txt" ]] || continue

    task=$(basename "$problem_dir")
    result="$RESULTS_ROOT/lean/claude-opus-5_${task}_lean.json"
    all_tasks+=("$task")

    if is_valid_json "$result"; then
        completed_tasks+=("$task")
    else
        pending_tasks+=("$task")
    fi
done

echo "Adaptive-thinking Opus inventory"
echo "Results root: $RESULTS_ROOT"
echo "Completed: ${#completed_tasks[@]}/${#all_tasks[@]}"
printf 'Completed cases:'
printf ' %s' "${completed_tasks[@]}"
printf '\n'
echo "Pending: ${#pending_tasks[@]}/${#all_tasks[@]}"
printf 'Pending cases:'
printf ' %s' "${pending_tasks[@]}"
printf '\n'

if [[ "$INVENTORY_ONLY" == "1" ]]; then
    exit 0
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "Set ANTHROPIC_API_KEY before running the Claude baseline." >&2
    exit 2
fi

if [[ -n "$WAIT_FOR_PID" ]]; then
    while kill -0 "$WAIT_FOR_PID" 2>/dev/null; do
        echo "Waiting for process $WAIT_FOR_PID before starting adaptive Opus ($(date))."
        sleep 60
    done
    echo "Process $WAIT_FOR_PID has finished; starting the single-attempt pass."
fi

attempted=0
produced=0
failed_tasks=()

for task in "${pending_tasks[@]}"; do
    result="$RESULTS_ROOT/lean/claude-opus-5_${task}_lean.json"

    # Recheck immediately before the call in case another process completed it.
    if is_valid_json "$result"; then
        echo "[skip newly completed] $task"
        continue
    fi

    attempted=$((attempted + 1))
    echo "[single attempt $attempted/${#pending_tasks[@]}] $task"

    PYTHONUNBUFFERED=1 \
    TASK="$task" \
    REASONING_EFFORT="$REASONING_EFFORT" \
    MAX_ROUNDS="$MAX_ROUNDS" \
    NUM_PASSES="$NUM_PASSES" \
    MAX_OUTPUT_TOKENS="$MAX_OUTPUT_TOKENS" \
    ANTHROPIC_THINKING="$ANTHROPIC_THINKING" \
    RESULTS_ROOT="$RESULTS_ROOT" \
        bash "$SCRIPT_DIR/run_task_claude-opus-5.sh" || true

    if is_valid_json "$result"; then
        produced=$((produced + 1))
        echo "[result saved] $task"
    else
        failed_tasks+=("$task")
        echo "[no result; moving on] $task"
    fi
done

echo "Single-attempt adaptive-thinking pass finished."
echo "Attempted: $attempted"
echo "New results: $produced"
echo "No result: ${#failed_tasks[@]}"
if (( ${#failed_tasks[@]} > 0 )); then
    printf 'Cases with no result:'
    printf ' %s' "${failed_tasks[@]}"
    printf '\n'
fi
