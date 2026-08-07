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

TEST_MODEL=${TEST_MODEL:?Set TEST_MODEL to the model whose generated results should be judged}
JUDGE_MODEL=${JUDGE_MODEL:-gpt-5.4}
REASONING_EFFORT=${REASONING_EFFORT:-medium}
TEMPERATURE=${TEMPERATURE:-1.0}
RESULTS_ROOT=${RESULTS_ROOT:-test_results_scale}
SAVE_ROOT=${SAVE_ROOT:-test_results_filter}
TASK=${TASK:-}
ONLY_EXISTING_RESULTS=${ONLY_EXISTING_RESULTS:-0}
SKIP_EXISTING_SEMANTIC=${SKIP_EXISTING_SEMANTIC:-0}

if [[ -z "${OPENAI_API_KEY:-}" && -z "${OPENAI_BASE_URL:-}" ]]; then
    echo "Set OPENAI_API_KEY before running the semantic filter." >&2
    exit 2
fi

run_problem() {
    local problem_dir=$1
    local task_name
    local generation_result
    local semantic_result
    task_name=$(basename "$problem_dir")
    generation_result="$RESULTS_ROOT/lean/${TEST_MODEL}_${task_name}_lean.json"
    semantic_result="$SAVE_ROOT/lean/${TEST_MODEL}_${task_name}_lean.json"
    if [[ "$ONLY_EXISTING_RESULTS" == "1" && ! -f "$generation_result" ]]; then
        echo "[skip missing generation] $task_name"
        return 0
    fi
    if [[ "$SKIP_EXISTING_SEMANTIC" == "1" && -f "$semantic_result" ]]; then
        echo "[skip existing semantic] $task_name"
        return 0
    fi
    echo "[semantic judge] $task_name"
    "$PYTHON_BIN" -m src.run_semantic_check \
        --model "$JUDGE_MODEL" \
        --testmodel "$TEST_MODEL" \
        --language lean \
        --reasoning_effort "$REASONING_EFFORT" \
        --temperature "$TEMPERATURE" \
        --results_root "$RESULTS_ROOT" \
        --save_root "$SAVE_ROOT" \
        --problem_dir "$problem_dir"
}

failures=0
if [[ -n "$TASK" ]]; then
    run_problem "algoveri_data/$TASK" || failures=$((failures + 1))
else
    for problem_dir in algoveri_data/*; do
        [[ -f "$problem_dir/lean_spec.lean" ]] || continue
        run_problem "$problem_dir" || failures=$((failures + 1))
    done
fi

"$PYTHON_BIN" scripts/summarize_lean_results.py \
    --model "$TEST_MODEL" \
    --results-root "$SAVE_ROOT" || true

if (( failures > 0 )); then
    exit 1
fi
