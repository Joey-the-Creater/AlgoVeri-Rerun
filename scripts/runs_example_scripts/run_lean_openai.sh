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

MODEL=${MODEL:-gpt-5.5}
REASONING_EFFORT=${REASONING_EFFORT:-medium}
MAX_ROUNDS=${MAX_ROUNDS:-15}
NUM_PASSES=${NUM_PASSES:-1}
MAX_OUTPUT_TOKENS=${MAX_OUTPUT_TOKENS:-32768}
ANTHROPIC_THINKING=${ANTHROPIC_THINKING:-adaptive}
CFG_PATH=${CFG_PATH:-test/config_test.yaml}
RESULTS_ROOT=${RESULTS_ROOT:-test_results_scale}
TASK=${TASK:-}
LIST_ONLY=${LIST_ONLY:-0}
DEBUG=${DEBUG:-0}

if [[ "$LIST_ONLY" != "1" ]]; then
    case "$MODEL" in
        claude-*)
            if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
                echo "Set ANTHROPIC_API_KEY before running the Claude baseline." >&2
                exit 2
            fi
            ;;
        *)
            if [[ -z "${OPENAI_API_KEY:-}" && -z "${OPENAI_BASE_URL:-}" ]]; then
                echo "Set OPENAI_API_KEY before running the OpenAI baseline." >&2
                exit 2
            fi
            ;;
    esac
fi

if [[ ! -f "$CFG_PATH" ]]; then
    echo "Config file not found: $CFG_PATH" >&2
    exit 2
fi

if [[ "$LIST_ONLY" != "1" ]]; then
    "$PYTHON_BIN" scripts/check_lean_environment.py --config "$CFG_PATH" || exit 2
fi

run_problem() {
    local problem_dir=$1
    local task_name
    task_name=$(basename "$problem_dir")

    if [[ "$LIST_ONLY" == "1" ]]; then
        echo "$task_name"
        return 0
    fi

    echo "[$MODEL][$REASONING_EFFORT] $task_name"
    local debug_args=()
    if [[ "$DEBUG" == "1" ]]; then
        debug_args+=(--debug)
    fi

    "$PYTHON_BIN" -m src.run_task \
        --language lean \
        --model "$MODEL" \
        --reasoning_effort "$REASONING_EFFORT" \
        --max_rounds "$MAX_ROUNDS" \
        --num_passes "$NUM_PASSES" \
        --max_output_tokens "$MAX_OUTPUT_TOKENS" \
        --anthropic_thinking "$ANTHROPIC_THINKING" \
        --cfg_path "$CFG_PATH" \
        --results_root "$RESULTS_ROOT" \
        --problem_dir "$problem_dir" \
        "${debug_args[@]}"
}

failures=0
if [[ -n "$TASK" ]]; then
    problem_dir="algoveri_data/$TASK"
    if [[ ! -f "$problem_dir/lean_spec.lean" || ! -f "$problem_dir/lean_nl.txt" ]]; then
        echo "Unknown or incomplete Lean task: $TASK" >&2
        exit 2
    fi
    run_problem "$problem_dir" || failures=$((failures + 1))
else
    for problem_dir in algoveri_data/*; do
        [[ -d "$problem_dir" ]] || continue
        [[ -f "$problem_dir/lean_spec.lean" ]] || continue
        [[ -f "$problem_dir/lean_nl.txt" ]] || continue
        run_problem "$problem_dir" || failures=$((failures + 1))
    done
fi

if [[ "$LIST_ONLY" != "1" ]]; then
    "$PYTHON_BIN" scripts/summarize_lean_results.py \
        --model "$MODEL" \
        --results-root "$RESULTS_ROOT" || true
fi

if (( failures > 0 )); then
    echo "$failures task runner(s) exited with an error; completed JSON results were preserved." >&2
    exit 1
fi
