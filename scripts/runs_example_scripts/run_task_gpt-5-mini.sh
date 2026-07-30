run_task_robust() {
    local INPUT_PATH=$1
    local TASK_NAME=$(basename "$INPUT_PATH")
    local MAX_RETRIES=2
    local attempt=1
    local LANGUAGE="lean"

    echo "------------------------------------------------"
    echo "Starting Task: $TASK_NAME"
    echo "------------------------------------------------"

    while [ $attempt -le $MAX_RETRIES ]; do
        # Execute the python command
        # We assume src.run_task uses the --url arg we pass below
        sleep 20
        echo "$INPUT_PATH" | python -m src.run_task \
            --language $LANGUAGE \
            --model "gpt-5-mini" \
            --debug
            
        
        # Capture exit code of python script
        EXIT_CODE=$?

        if [ $EXIT_CODE -eq 0 ]; then
            echo ">>> [Success] Task $TASK_NAME completed."
            return 0
        else
            echo "!!! [Warning] Task $TASK_NAME failed (Attempt $attempt/$MAX_RETRIES)."
            
            if [ $attempt -eq $MAX_RETRIES ]; then
                echo "!!! [Error] Max retries reached for $TASK_NAME. Moving to next task."
                return 1
            fi

            # --- RECOVERY LOGIC ---
            echo ">>> [Recovery] s..."
            sleep 10 # Wait a moment for dust to settle
            ((attempt++))
        fi
    done
}

# --- MAIN EXECUTION FLOW ---

# Run Benchmarks using the robust function


#############################################
# Data structure
#############################################
run_task_robust "algoveri_data/maxheap_push"
run_task_robust "algoveri_data/maxheap_popmax"
run_task_robust "algoveri_data/bst_search"
run_task_robust "algoveri_data/bst_delete"
run_task_robust "algoveri_data/bst_insert"
run_task_robust "algoveri_data/bst_zig"
run_task_robust "algoveri_data/bst_zigzig"
run_task_robust "algoveri_data/bst_zigzag"
run_task_robust "algoveri_data/stack_push"
run_task_robust "algoveri_data/stack_pop"
run_task_robust "algoveri_data/queue_enqueue"
run_task_robust "algoveri_data/queue_dequeue"
run_task_robust "algoveri_data/ringbuffer_enqueue"
run_task_robust "algoveri_data/ringbuffer_dequeue"
run_task_robust "algoveri_data/unionfind_find"
run_task_robust "algoveri_data/unionfind_linkroots"
run_task_robust "algoveri_data/splaytree_splay"
run_task_robust "algoveri_data/trie_search"
run_task_robust "algoveri_data/trie_insert"
run_task_robust "algoveri_data/trie_delete"
run_task_robust "algoveri_data/ternarysearchtree_search"
run_task_robust "algoveri_data/ternarysearchtree_insert"
run_task_robust "algoveri_data/ternarysearchtree_delete"
run_task_robust "algoveri_data/segmenttree_query"
run_task_robust "algoveri_data/segmenttree_modify"
run_task_robust "algoveri_data/segmenttree_build"
run_task_robust "algoveri_data/llrbt_delete"
run_task_robust "algoveri_data/llrbt_insert"
run_task_robust "algoveri_data/llrbt_rotateleft"
run_task_robust "algoveri_data/llrbt_rotateright"
run_task_robust "algoveri_data/llrbt_flipcolor"


#############################################
# Sorting, searching, and ordered statistics
#############################################

run_task_robust "algoveri_data/binary_search"
run_task_robust "algoveri_data/linear_search"
run_task_robust "algoveri_data/bubble_sort"
run_task_robust "algoveri_data/insertion_sort"
run_task_robust "algoveri_data/merge_sort"
run_task_robust "algoveri_data/quick_sort"
run_task_robust "algoveri_data/k_smallest"

#############################################
# basic algorithms, DP, xxx
#############################################

run_task_robust "algoveri_data/longest_common_subsequence"
run_task_robust "algoveri_data/coin_change"
run_task_robust "algoveri_data/jump_game"
run_task_robust "algoveri_data/knapsack_01"
run_task_robust "algoveri_data/knapsack_unbounded"
run_task_robust "algoveri_data/longest_increasing_subsequence"
run_task_robust "algoveri_data/maximum_subarray_sum"
run_task_robust "algoveri_data/rod_cutting"
run_task_robust "algoveri_data/lca"
run_task_robust "algoveri_data/house_robber"

#############################################
# Graph algorithms
#############################################

run_task_robust "algoveri_data/dfs"
run_task_robust "algoveri_data/bfs"
run_task_robust "algoveri_data/cycle_detection"
run_task_robust "algoveri_data/bipartite_check"
run_task_robust "algoveri_data/topological_sort"
run_task_robust "algoveri_data/dijkstra"
run_task_robust "algoveri_data/bellman_ford"
run_task_robust "algoveri_data/prim"
run_task_robust "algoveri_data/kruskal"
run_task_robust "algoveri_data/max_matching"
run_task_robust "algoveri_data/edmond_karp"
run_task_robust "algoveri_data/push_relabel"
run_task_robust "algoveri_data/scc_tarjan"

#############################################
# Math
#############################################

run_task_robust "algoveri_data/integer_exponential"
run_task_robust "algoveri_data/fast_exponential"
run_task_robust "algoveri_data/trial_division_naive"
run_task_robust "algoveri_data/trial_division_optimized"
run_task_robust "algoveri_data/sieve_method"
run_task_robust "algoveri_data/polymul_naive"
run_task_robust "algoveri_data/polymul_karatsuba"
run_task_robust "algoveri_data/discrete_logarithm"
run_task_robust "algoveri_data/linearsys_gf2"
run_task_robust "algoveri_data/gcd"
run_task_robust "algoveri_data/matrix_multiplication"

#############################################
# String
#############################################

run_task_robust "algoveri_data/bracket_matching"
run_task_robust "algoveri_data/longest_palindrome_substring"
run_task_robust "algoveri_data/string_search_naive"
run_task_robust "algoveri_data/kmp"
run_task_robust "algoveri_data/ac_automata"
