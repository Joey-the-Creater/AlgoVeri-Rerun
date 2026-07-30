#!/bin/bash
#SBATCH --job-name=algoveri
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=40
#SBATCH --mem=400G
#SBATCH --gres=gpu:4
#SBATCH --time=23:59:00
#SBATCH --output=slurm_output/%x-%j.out
#SBATCH --mail-type=ALL
#SBATCH --mail-user=YOUR_EMAIL
#SBATCH --partition=YOUR_PARTITION
#SBATCH --qos=YOUR_QUEUE_IF_EXIST

# CHANGE TO YOUR OWN ANACONDA/MINICONDA PATH
source YOUR_MINICONDA_PATH/miniconda3/etc/profile.d/conda.sh
conda activate algoveri

# --- CONFIGURATION ---
# JUST DOWNLOAD VLLM NIGHTLY IF NEEDED TO USE gpt-oss-120B
CONTAINER="apptainer_imgs/vllm-nightly.sif"
#MODEL_PATH="gpt-oss-120b"
MODEL_PATH="gpt-5.4"

# THE MODEL BEING TESTED
TEST_MODEL_PATH="gpt-5.3-codex"
LANGUAGE="dafny"

# Setup Network Variables
HEAD_NODE_IP=$(hostname -I | awk '{print $1}')
WORKER_PORT=$(python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
SERVER_URL="http://localhost:${WORKER_PORT}/v1"
SERVER_PID=""

echo "Configuration: Node IP ${HEAD_NODE_IP}, Port ${WORKER_PORT}"

# IF YOU USE VLLM (LIKE GPT-OSS-120B), UNCOMMENT THE FOLLOW
# IT IS THE SAME LOGIC AS TESTING OPEN SOURCE MODELS USING VLLM

# --- FUNCTION 1: Start/Restart vLLM ---
# start_vllm() {
#     echo ">>> [System] Starting vLLM Server..."
    
#     export TIKTOKEN_CACHE_DIR="YOUR_PATH_TO_TIKTOKEN_CACHE/tiktoken_cache"
#     # 1. Start the server in the background
#     apptainer exec --nv --bind /scratch:/scratch \
#         --bind "${TIKTOKEN_CACHE_DIR}:/app/tiktoken_cache" \
#         --env VLLM_HOST_IP=${HEAD_NODE_IP} \
#         --env TIKTOKEN_CACHE_DIR="/app/tiktoken_cache" \
#         --env TIKTOKEN_RS_CACHE_DIR="/app/tiktoken_cache" \
#         $CONTAINER \
#         vllm serve "${MODEL_PATH}" \
#         --port ${WORKER_PORT} \
#         --tensor-parallel-size 4 \
#         --max-model-len 131072 \
#         --trust-remote-code \
#         --host 0.0.0.0 &> "slurm_output/vllm_server_${SLURM_JOB_ID}.log" &
    
#     # 2. Capture the PID
#     SERVER_PID=$!
#     echo ">>> [System] Server Process ID: $SERVER_PID"

#     # 3. Wait loop (Health Check)
#     echo ">>> [System] Waiting for health check..."
#     local retries=0
#     # Wait up to 30 minutes (90 * 20s) for the server to load
#     while ! curl -s -o /dev/null -w "%{http_code}" http://localhost:${WORKER_PORT}/v1/models | grep -q "200"; do
#         sleep 20
#         ((retries++))
        
#         # Check if process died while loading
#         if ! kill -0 $SERVER_PID 2>/dev/null; then
#             echo "!!! [Error] vLLM process died during startup. Check vllm_server.log"
#             exit 1
#         fi

#         if [ $retries -ge 90 ]; then
#             echo "!!! [Error] Timed out waiting for server to start."
#             exit 1
#         fi
#         echo "   ... loading model ($retries/90)"
#     done
#     echo ">>> [System] vLLM is READY!"
#     sleep 60
# }

# --- FUNCTION 2: Run Task with Retry Logic ---
run_task_robust() {
    local INPUT_PATH=$1
    local TASK_NAME=$(basename "$INPUT_PATH")
    local MAX_RETRIES=2
    local attempt=1

    echo "------------------------------------------------"
    echo "Starting Task: $TASK_NAME"
    echo "------------------------------------------------"

    while [ $attempt -le $MAX_RETRIES ]; do
        # Execute the python command

        sleep 20
        echo "$INPUT_PATH" | python -m src.run_semantic_check \
            --model "${MODEL_PATH}" \
            --testmodel "${TEST_MODEL_PATH}" \
            --language "${LANGUAGE}" \
            --url "${SERVER_URL}"
        
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
            echo ">>> [Recovery] Diagnosing Server Status..."
            sleep 10 # Wait a moment for dust to settle

            # IF YOU USE VLLM, UNCOMMENT THE FOLLOW

            ## Check if server endpoint responds
            #if curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:${WORKER_PORT}/v1/models | grep -q "200"; then
            #    echo ">>> [Recovery] Server appears HEALTHY. Retrying task immediately..."
            #else
            #    echo "!!! [Recovery] Server appears DEAD or STUCK. Restarting..."
            #    
            #    # Kill old server if it exists
            #    kill $SERVER_PID 2>/dev/null
            #    wait $SERVER_PID 2>/dev/null
            #    
            #    # Start fresh
            #    start_vllm
            #fi
            #
            ((attempt++))
        fi
    done
}

# --- MAIN EXECUTION FLOW ---

# IF YOU USE VLLM, UNCOMMENT THE FOLLOW
# 1. Initial Start
#start_vllm

# 2. Run Benchmarks using the robust function


tasks=(
    "algoveri_data/maxheap_push"
    "algoveri_data/maxheap_popmax"
    "algoveri_data/bst_search"
    "algoveri_data/bst_delete"
    "algoveri_data/bst_insert"
    "algoveri_data/bst_zig"
    "algoveri_data/bst_zigzig"
    "algoveri_data/bst_zigzag"
    "algoveri_data/stack_push"
    "algoveri_data/stack_pop"
    "algoveri_data/queue_enqueue"
    "algoveri_data/queue_dequeue"
    "algoveri_data/ringbuffer_enqueue"
    "algoveri_data/ringbuffer_dequeue"
    "algoveri_data/unionfind_find"
    "algoveri_data/unionfind_linkroots"
    "algoveri_data/splaytree_splay"
    "algoveri_data/trie_search"
    "algoveri_data/trie_insert"
    "algoveri_data/trie_delete"
    "algoveri_data/ternarysearchtree_search"
    "algoveri_data/ternarysearchtree_insert"
    "algoveri_data/ternarysearchtree_delete"
    "algoveri_data/segmenttree_query"
    "algoveri_data/segmenttree_modify"
    "algoveri_data/segmenttree_build"
    "algoveri_data/llrbt_delete"
    "algoveri_data/llrbt_insert"
    "algoveri_data/llrbt_rotateleft"
    "algoveri_data/llrbt_rotateright"
    "algoveri_data/llrbt_flipcolor"
    #     # sorting
    "algoveri_data/binary_search"
    "algoveri_data/linear_search"
    "algoveri_data/bubble_sort"
    "algoveri_data/insertion_sort"
    "algoveri_data/merge_sort"
    "algoveri_data/quick_sort"
    "algoveri_data/k_smallest"
    # basic algo, DP
    "algoveri_data/longest_common_subsequence"
    "algoveri_data/coin_change"
    "algoveri_data/jump_game"
    "algoveri_data/knapsack_01"
    "algoveri_data/knapsack_unbounded"
    "algoveri_data/longest_increasing_subsequence"
    "algoveri_data/maximum_subarray_sum"
    "algoveri_data/rod_cutting"
    "algoveri_data/lca"
    "algoveri_data/house_robber"
    # graph
    "algoveri_data/dfs"
    "algoveri_data/bfs"
    "algoveri_data/cycle_detection"
    "algoveri_data/bipartite_check"
    "algoveri_data/topological_sort"
    "algoveri_data/dijkstra"
    "algoveri_data/bellman_ford"
    "algoveri_data/prim"
    "algoveri_data/kruskal"
    "algoveri_data/max_matching"
    "algoveri_data/edmond_karp"
    "algoveri_data/push_relabel"
    "algoveri_data/scc_tarjan"
    # math
    "algoveri_data/integer_exponential"
    "algoveri_data/fast_exponential"
    "algoveri_data/trial_division_naive"
    "algoveri_data/trial_division_optimized"
    "algoveri_data/sieve_method"
    "algoveri_data/polymul_naive"
    "algoveri_data/polymul_karatsuba"
    "algoveri_data/discrete_logarithm"
    "algoveri_data/linearsys_gf2"
    "algoveri_data/gcd"
    "algoveri_data/matrix_multiplication"
    # string
    "algoveri_data/bracket_matching"
    "algoveri_data/longest_palindrome_substring"
    "algoveri_data/string_search_naive"
    "algoveri_data/kmp"
    "algoveri_data/ac_automata"
)

# Define the total number of parallel groups
NUM_GROUPS=77
group_pids=() # Create an empty array to store PIDs

# Loop to create the parallel groups
for ((g=0; g<NUM_GROUPS; g++)); do
    (
        # This inner loop picks tasks using modulo arithmetic (Round Robin)
        # Group 0 does tasks 0, 4, 8...
        # Group 1 does tasks 1, 5, 9...
        for ((i=g; i<${#tasks[@]}; i+=NUM_GROUPS)); do
            task_path="${tasks[i]}"
            echo "Group $g running: $task_path"
            
            # Run your actual function here
            run_task_robust "$task_path"
        done
    ) & # Put this entire group in the background

    # SAVE THE PID of the specific background group we just started
    group_pids+=($!) 
done

# --- The Critical Change ---

# Do NOT use 'wait'. Use 'wait' with specific PIDs.
# This waits for all the logic groups to finish, but ignores the vLLM server.
wait "${group_pids[@]}"

# IF YOU USE VLLM, UNCOMMENT THE FOLLOW
# 3. Final Cleanup
# echo ">>>All tasks finished. Shutting down server..."
# kill $SERVER_PID
