# LastDance v2: robust Lean coding-agent condition

LastDance v2 adds an opt-in `robust` profile without changing the published
LastDance defaults. It keeps generation, semantic judging, workspaces, and
result directories separate from the existing experiments.

## Robust pipeline

```text
TASK.md + Lean scaffold
          |
          v
  algorithm commitment ----> AlgorithmPlan.md
          |
          v
  hierarchical lemma plan --> ProofState.md
          |
          +---- guarded natural-language queries ----> Frenzymath LeanSearch
          |
          v
  Claude edits model-owned marker regions only
  and performs a requirement-by-requirement semantic audit
          |
          v
  independent merge + Lean compilation
          |
          +-- failure --> structured diagnostic fingerprint
          |                  |
          |          repeated fingerprint?
          |                  |
          |             rollback checkpoint + alternate strategy
          |
          v
  verified result + provenance/ledger artifacts
```

The robust profile enables:

| Measure | Durable evidence |
|---|---|
| Algorithm commitment | `AlgorithmPlan.md` |
| Hierarchical lemma manager | `ProofState.md` |
| Guarded Mathlib retrieval | `.lastdance/leansearch_queries.jsonl` and cache |
| Prompt-level semantic audit | saved initial/repair prompts and session ledger |
| Structured targeted repair | diagnostic fingerprints in `run_ledger.jsonl` |
| Stateful backtracking | `.lastdance/checkpoints/manifest.jsonl` |
| Provenance-aware output | hashes and ownership ranges in result JSON |
| Reproducibility ledger | `.lastdance/run_ledger.jsonl` |

Semantic review remains inside every generation/repair session: the model must
audit the implementation against `TASK.md` before its final check. No additional
semantic review stage runs after compilation. Teacher-owned `sorry` is recorded
in provenance but is not attributed to the model.

## Frenzymath LeanSearch v2 API

The robust profile uses Frenzymath's public
[LeanSearch v2](https://github.com/frenzymath/LeanSearch-v2) standard-mode API
at `https://leansearch.net/search` by default. No local PostgreSQL, Chroma,
model installation, or API key is required. The request uses the documented
`query`, `num_results`, and `rerank` fields.

Claude never receives general network access: it can only invoke
`./leansearch "one quoted natural-language query"`. The harness owns the API
URL and POST request, enables the hosted reranker, limits query/result sizes,
caches responses, and logs query provenance. Do not put secrets in a query;
queries are sent to a public third-party service.

The hosted corpus is Mathlib `v4.28.0-rc1`, while this AlgoVeri environment is
pinned to `v4.25.0-rc2`. Therefore every retrieved declaration is only a
suggestion and must pass the local `./check.sh`; retrieval never changes the
verification environment.

For a private mirror, override `LEANSEARCH_URL`. Local legacy LeanSearch CLI
mode remains available through `LEANSEARCH_ROOT` and `LEANSEARCH_PYTHON`, but
is not used by the robust default.

Before the first Claude call, the runner performs one cached query for
"commutativity of natural number addition." A failed API check
stops the experiment before model credit is spent. Set `LEANSEARCH_PREFLIGHT=0`
only for a deliberate search-failure ablation; individual `./leansearch` calls
will then report backend errors to the agent.

## Run a smoke case

Use the dedicated launcher and separate experiment name:

```bash
TASK=stack_push \
TASK_TIMEOUT_SECONDS=1800 \
bash scripts/runs_example_scripts/run_lean_lastdance_robust.sh
```

Defaults:

- result model name: `lastdance-opus-5-robust`;
- results: `results/lastdance_opus5_robust`;
- workspaces: `.agent_runs/lastdance_opus5_robust`;
- one initial session and up to two compiler-repair sessions;
- budgets: $2 initial and $2 per repair;
- five LeanSearch results per query, cached by backend/query/result count.

Run the selected no-teacher-`sorry` scope in the background:

```bash
mkdir -p logs
nohup env \
  EXCLUDE_TEACHER_SORRY=1 \
  bash scripts/runs_example_scripts/run_lean_lastdance_robust.sh \
  > logs/lastdance_robust.log 2>&1 &
echo $! > logs/lastdance_robust.pid
disown
```

Resume with the same command. Existing valid result files are skipped. Use
`RERUN_FAILED=1` to retry saved compilation failures or `REUSE_WORKSPACE=1`
with an explicit `TASK`/`TASKS` selection to continue a partial workspace.

## Ablations

Every major intervention can be overridden independently while retaining the
profile label and full configuration in the manifest/result JSON:

```bash
LASTDANCE_PROFILE=robust \
ALGORITHM_PLAN=0 \
LEMMA_PLAN=1 \
LEANSEARCH=1 \
BACKTRACKING=0 \
FEEDBACK_MODE=exact \
RESULT_MODEL_NAME=lastdance-ablation-no-plan \
RESULTS_ROOT=results/lastdance_ablation_no_plan \
WORK_ROOT=.agent_runs/lastdance_ablation_no_plan \
bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh
```

Boolean variables accept `1`, `0`, or empty (profile default):
`ALGORITHM_PLAN`, `LEMMA_PLAN`, `LEANSEARCH`, `SEMANTIC_AUDIT`,
`SEMANTIC_REMINDER`, `EARLY_CHECK`, and `BACKTRACKING`.
Other controls are `FEEDBACK_MODE=exact|structured`, `STAGNATION_THRESHOLD`,
`MAX_CHECKPOINTS`, `LEANSEARCH_RESULTS`, and `LEANSEARCH_TIMEOUT`.
`LEANSEARCH_RERANK=0|1` controls the API reranker,
`LEANSEARCH_RETRIEVE_K` controls first-stage width, and
`LEANSEARCH_PREFLIGHT=0|1` controls the fail-fast API query.

For fair ablations, change only one control, keep the task set/model/effort and
all monetary/time budgets fixed, and always use new result/work directories.

## Provenance-aware semantic judge

Run the semantic evaluator into another new directory:

```bash
TEST_MODEL=lastdance-opus-5-robust \
JUDGE_MODEL=gpt-5.4 \
TEMPERATURE=0 \
PROVENANCE_AWARE_JUDGE=1 \
ONLY_EXISTING_RESULTS=1 \
SKIP_EXISTING_SEMANTIC=1 \
RESULTS_ROOT=results/lastdance_opus5_robust \
SAVE_ROOT=results/lastdance_opus5_robust_semantic_gpt54_t0_provenance \
bash scripts/runs_example_scripts/run_lean_semantic_filter.sh
```

This condition explicitly tells the judge that only `auxcode`, `code`, `lemma`,
and `proof` marker blocks are student-owned. The saved `semantic_judge` metadata
contains `"provenance_aware": true`. Do not merge these results with the old
judge conditions; compare them as a separate evaluator ablation.
