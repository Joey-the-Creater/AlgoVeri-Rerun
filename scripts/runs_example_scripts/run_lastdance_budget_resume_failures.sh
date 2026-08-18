#!/usr/bin/env bash
set -uo pipefail

# Resume only non-verified budget-ablation cases, preserving their current Lean
# candidates, plans, checkpoints, and event history.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
cd "$REPO_ROOT"

CONDITIONS=${CONDITIONS:-current,boundary,governor,phased,full}

for condition in ${CONDITIONS//,/ }; do
    result_dir="results/lastdance_budget_${condition}_13/lean"
    prefix="lastdance-budget-${condition}_"
    suffix="_lean.json"
    failed=()
    for result in "$result_dir"/"${prefix}"*"${suffix}"; do
        [[ -f "$result" ]] || continue
        [[ $(jq -r '.verified == true' "$result") == true ]] && continue
        name=${result##*/}
        name=${name#"$prefix"}
        name=${name%"$suffix"}
        failed+=("$name")
    done
    if [[ ${#failed[@]} -eq 0 ]]; then
        echo "[$condition] no failed tasks remain"
        continue
    fi
    task_csv=$(IFS=,; echo "${failed[*]}")
    echo "[$condition] resuming ${#failed[@]} task(s): $task_csv"
    CONDITION="$condition" \
    TASKS="$task_csv" \
    REUSE_WORKSPACE=1 \
    RERUN_FAILED=1 \
    PYTHONUNBUFFERED=1 \
    bash "$SCRIPT_DIR/run_lastdance_budget_condition.sh" || true
done

echo "All requested ablation repair queues completed."
