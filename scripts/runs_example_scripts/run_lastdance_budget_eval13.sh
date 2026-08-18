#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CONDITIONS=${CONDITIONS:-current,boundary,governor,phased,full}
overall_status=0

IFS=',' read -r -a condition_list <<< "$CONDITIONS"
for condition in "${condition_list[@]}"; do
    echo "[budget evaluation] starting ${condition}"
    if CONDITION="$condition" bash "$SCRIPT_DIR/run_lastdance_budget_condition.sh"; then
        echo "[budget evaluation] ${condition} completed successfully"
    else
        status=$?
        echo "[budget evaluation] ${condition} completed with benchmark failures (${status})"
        overall_status=1
    fi
done

echo "[budget evaluation] all requested conditions finished"
exit "$overall_status"
