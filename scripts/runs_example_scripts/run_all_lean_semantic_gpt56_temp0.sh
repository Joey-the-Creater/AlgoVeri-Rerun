#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

JUDGE_MODEL=gpt-5.6-sol
REASONING_EFFORT=none
TEMPERATURE=0

run_condition() {
    local label=$1
    local test_model=$2
    local results_root=$3
    local save_root=$4
    echo "=== GPT-5.6 Sol temperature 0 semantic judge: $label ==="
    env \
        TEST_MODEL="$test_model" \
        JUDGE_MODEL="$JUDGE_MODEL" \
        REASONING_EFFORT="$REASONING_EFFORT" \
        TEMPERATURE="$TEMPERATURE" \
        ONLY_EXISTING_RESULTS=1 \
        SKIP_EXISTING_SEMANTIC=1 \
        RESULTS_ROOT="$results_root" \
        SAVE_ROOT="$save_root" \
        bash scripts/runs_example_scripts/run_lean_semantic_filter.sh
}

failures=0
run_condition "GPT-5.5" "gpt-5.5" \
    results/full_three results/full_three_semantic_gpt56_temp0 \
    || failures=$((failures + 1))
run_condition "GPT-5.6 Sol" "gpt-5.6-sol" \
    results/full_three results/full_three_semantic_gpt56_temp0 \
    || failures=$((failures + 1))
run_condition "Opus 5 thinking" "claude-opus-5" \
    results/full_three results/full_three_semantic_gpt56_temp0 \
    || failures=$((failures + 1))
run_condition "Opus 5 no-thinking" "claude-opus-5" \
    results/full_opus_no_thinking results/full_opus_no_thinking_semantic_gpt56_temp0 \
    || failures=$((failures + 1))
run_condition "Claude Code enhanced" "claude-code-opus-5" \
    results/claude_code_opus5 results/claude_code_opus5_semantic_gpt56_temp0 \
    || failures=$((failures + 1))

echo "GPT-5.6 Sol temperature 0 semantic evaluation finished; condition failures: $failures"
exit "$failures"
