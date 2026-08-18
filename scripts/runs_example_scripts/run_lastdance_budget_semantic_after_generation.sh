#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

GENERATION_PID_FILE=${GENERATION_PID_FILE:-logs/lastdance_budget_eval13.pid}
[[ -f "$GENERATION_PID_FILE" ]] || { echo "Missing generation PID file" >&2; exit 2; }
generation_pid=$(cat "$GENERATION_PID_FILE")

while ps -p "$generation_pid" -o args= 2>/dev/null | grep -q 'run_lastdance_budget_eval13.sh'; do
    sleep 30
done

full_manifest=.agent_runs/lastdance_budget_full_13/run_manifest.json
if [[ ! -f "$full_manifest" ]] || [[ $(jq -r '.state // ""' "$full_manifest") != "completed" ]]; then
    echo "Generation evaluation did not complete; semantic evaluation was not started." >&2
    exit 1
fi

for condition in current boundary governor phased full; do
    echo "[budget semantic evaluation] starting ${condition}"
    TEST_MODEL="lastdance-budget-${condition}" \
    JUDGE_MODEL=gpt-5.4 \
    TEMPERATURE=0 \
    REASONING_EFFORT=medium \
    PROVENANCE_AWARE_JUDGE=1 \
    ONLY_EXISTING_RESULTS=1 \
    SKIP_EXISTING_SEMANTIC=1 \
    RESULTS_ROOT="results/lastdance_budget_${condition}_13" \
    SAVE_ROOT="results/lastdance_budget_${condition}_13_semantic_gpt54_t0" \
    bash "$SCRIPT_DIR/run_lean_semantic_filter.sh" || true
done

echo "[budget semantic evaluation] all conditions finished"
