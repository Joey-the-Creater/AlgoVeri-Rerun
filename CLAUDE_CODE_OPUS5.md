# LastDance: Claude Code + Opus 5 Lean toolchain

For the opt-in robust profile with algorithm planning, checkpointed repair,
the Frenzymath LeanSearch v2 API, prompt-level semantic auditing, and provenance-aware
evaluation, see [LASTDANCE_V2.md](LASTDANCE_V2.md). The legacy defaults in this
document remain unchanged for reproducibility.

**LastDance** uses Claude Code as a coding agent rather than calling the Anthropic
Messages API through AlgoVeri's original chat-and-revision loop. Each task gets
an isolated working directory containing `TASK.md`, `Original.lean`, and an
editable `Solution.lean`. Claude can inspect the task/scaffold/checker files,
edit only `Solution.lean`, and run the constrained `./check.sh` command.

A deny-by-default `PreToolUse` hook enforces that contract: reads are limited
to the task, solution, original, merged, and checker files in the isolated
workspace; edits and writes are limited to `Solution.lean`; and shell access is
limited to exactly `./check.sh`, `pwd`, and safe workspace listings.

The harness does not trust the agent's files or its reported success. It copies
only the `auxcode`, `code`, `lemma`, and `proof` marker blocks into the original
benchmark scaffold, rejects prohibited terms in those blocks, and performs a
fresh Lean compilation. The saved JSON uses the existing semantic evaluator's
schema.

The default enhanced condition is adaptive. Claude receives a $2 initial
session. If final independent compilation fails, the harness preserves the
current `Solution.lean`, supplies the exact verifier feedback to one fresh
repair session with another $2 budget, and verifies again. A successful first
pass does not spend the repair budget. The prompts also require an early Lean
check and a final requirement-by-requirement semantic self-audit.

## Prerequisites

From the repository root, confirm that Claude Code is authenticated and that
the local Lean environment works:

```bash
claude auth status
.venv/bin/python scripts/check_lean_environment.py \
  --config test/config_test.yaml
```

The runner uses Claude Code's current authentication. It does not source or
export an API key.

## Test one task

Start with a bounded smoke run:

```bash
TASK=stack_push \
TASK_TIMEOUT_SECONDS=1800 \
bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh
```

Results are written to
`results/claude_code_opus5/lean/claude-code-opus-5_stack_push_lean.json`.
The raw Claude event stream, stderr, and working files stay under
`.agent_runs/claude_code_opus5/stack_push/`.

The launcher defaults to `MAX_BUDGET_USD=2`, `REPAIR_BUDGET_USD=2`, and
`COMPILER_REPAIR_PASSES=1`. Thus the nominal maximum is $4 per failed case and
$2 per case that passes initially; provider-side accounting may slightly exceed
a requested session cap. The default timeout is 7,200 seconds **per session**.

## Run all 77 tasks

```bash
mkdir -p logs
nohup env \
  REASONING_EFFORT=medium \
  TASK_TIMEOUT_SECONDS=7200 \
  RESULTS_ROOT=results/claude_code_opus5 \
  WORK_ROOT=.agent_runs/claude_code_opus5 \
  bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh \
  > logs/claude_code_opus5.log 2>&1 &
echo $! > logs/claude_code_opus5.pid
disown
```

Override the adaptive policy when defining a different experimental condition:

```bash
MAX_BUDGET_USD=3 \
REPAIR_BUDGET_USD=1 \
COMPILER_REPAIR_PASSES=2 \
bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh
```

`COMPILER_REPAIR_PASSES` counts additional sessions, so `0` restores a
single-session run. Each repair preserves the preceding candidate and consumes
its own repair budget only after an independent verification failure. Monitor
the run with:

```bash
tail -f logs/claude_code_opus5.log
ps -p "$(cat logs/claude_code_opus5.pid)" -o pid,stat,etime,cmd
find results/claude_code_opus5/lean \
  -name 'claude-code-opus-5_*_lean.json' | wc -l
```

The runner saves one aggregate JSON after all configured compiler passes,
including per-session cost, turns, tokens, verifier feedback, and the final
candidate. It also saves a failure JSON for timeouts, empty responses,
validation failures, and runner exceptions. Therefore, the file count records
attempted cases rather than only successful responses.

## Targeted task lists

Set `TASKS` to a comma- or whitespace-separated list to run only that ordered
subset. For example:

```bash
TASKS='ac_automata,bipartite_check,gcd' \
bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh
```

`TASK` selects one case; `TASKS` selects several. Do not set both.

To run only cases with no teacher-provided `sorry` outside the four editable
sections, enable the source-aware filter:

```bash
EXCLUDE_TEACHER_SORRY=1 \
bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh
```

Preview the exact filtered set without invoking Claude or spending API credit:

```bash
EXCLUDE_TEACHER_SORRY=1 LIST_ONLY=1 \
bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh
```

## Resume and retry

Running the same command again skips every valid existing result and resumes at
the first case without a result file. To retry only saved failures:

```bash
RERUN_FAILED=1 \
bash scripts/runs_example_scripts/run_lean_claude_code_opus5.sh
```

Use `RERUN=1` only when intentionally replacing every existing result. List the
77 selected tasks without invoking Claude with `LIST_ONLY=1`.

For a targeted rerun interrupted by a transient API failure, preserve the
existing partial `Solution.lean` and append to its trace with
`REUSE_WORKSPACE=1`. Combine it with an explicit `TASK` or `TASKS` list and
`RERUN=1`; successful cases outside that list remain untouched.

## Live web dashboard

The read-only dashboard follows Claude's JSONL event stream and saved result
files. It shows the case queue, current stage, narrated agent messages, tool
calls and denials, Lean-check output, thinking-token estimates, code diffs,
compiler-pass boundaries, duration, turns, lines of code added, and known cost.
LOC added is the number
of `+` lines in the line diff from the original Lean scaffold to the generated
solution. It also indexes the four direct-API reruns and presents all Claude
Code batches as one combined historical experiment. The enhanced 65-case run is
tracked separately with its live workspace, generation results, and semantic
results through `config/dashboard_experiments.json`; the underlying directories
remain unchanged for reproducibility.

Start it for the enhanced no-teacher-`sorry` run:

```bash
nohup env DASHBOARD_PORT=8765 \
  bash scripts/runs_example_scripts/run_claude_code_dashboard.sh \
  > logs/claude_code_dashboard.log 2>&1 &
disown
```

The default dashboard experiment is **LastDance · enhanced**. It reads
`.agent_runs/claude_code_opus5`, `results/claude_code_opus5`,
`results/claude_code_opus5_semantic`, and `logs/claude_code_opus5.pid`, using
the exact filtered 65-case scope. No manual result import is required.

The server binds to the workstation's loopback interface. From a separate
terminal on your Windows computer, create an SSH tunnel:

```powershell
ssh -L 8765:127.0.0.1:8765 jumpyjoey@128.100.23.226
```

Keep that SSH window open and visit `http://localhost:8765` in your local
browser. Use the experiment selector in the top bar to switch between models,
inspect their per-case generated code and diagnostics, or choose **Compare** to
view all selected runs together. The comparison view provides:

- cumulative compilation success at any repair/check try using the slider;
- final compilation and semantic-full-mark rates as separate metrics;
- common-task scope for a fair denominator, or each run's native scope;
- a case-level result matrix whose cells open that exact model/case result;
- four outcome colors: compiled with a semantic pass, compiled without a
  semantic pass, compilation failure, and missing output. Compiled results
  whose semantic check has not run use the second color but retain an explicit
  **not evaluated** tooltip.

For the original direct-API loop, try `k` means `details.rounds + 1`, so a
solution accepted without a revision is try 1. For Claude Code, it means the
number of observed `./check.sh` calls through the successful check. This is a
cumulative success-at-try curve, not an independent pass@k estimate. Independent
passes are kept as a separate metric in the API; the current published runs
contain one pass per case. An absent semantic result is displayed as **not
evaluated**, never as a semantic failure.

The page refreshes every 1.5 seconds. It remains useful after a run finishes or
is interrupted because it reads durable files rather than terminal output. Add
future result directories or experimental conditions to
`config/dashboard_experiments.json`. Stop the dashboard with:

```bash
kill "$(cat logs/claude_code_dashboard.pid)"
```

## Semantic evaluation

After generation finishes:

```bash
TEST_MODEL=claude-code-opus-5 \
JUDGE_MODEL=gpt-5.4 \
ONLY_EXISTING_RESULTS=1 \
SKIP_EXISTING_SEMANTIC=1 \
RESULTS_ROOT=results/claude_code_opus5 \
SAVE_ROOT=results/claude_code_opus5_semantic \
bash scripts/runs_example_scripts/run_lean_semantic_filter.sh
```

`ONLY_EXISTING_RESULTS=1` limits evaluation to saved generation outputs, which
is useful for the filtered 65-case condition. `SKIP_EXISTING_SEMANTIC=1` makes
the command resumable without spending judge calls on already saved cases.

To judge GPT-5.5, GPT-5.6 Sol, both Opus 5 conditions, and Claude Code at
temperature 0 without touching the temperature-1 directories, run:

```bash
bash scripts/runs_example_scripts/run_all_lean_semantic_temp0.sh
```

The dashboard's **5.4 judge · T0** tab reads the separate
`*_semantic_temp0` directories. Each saved result also records the judge model,
temperature, and configured reasoning effort in `semantic_judge` metadata.

GPT-5.6 Sol rejects an explicit temperature when reasoning is enabled. The
supported temperature-0 condition therefore uses `reasoning.effort=none` and
separate `*_semantic_gpt56_temp0` directories:

```bash
bash scripts/runs_example_scripts/run_all_lean_semantic_gpt56_temp0.sh
```

It appears under the dashboard's **5.6 judge · T0** tab and remains separate
from both GPT-5.4 semantic conditions.

The GPT-5.4 semantic judge remains a post-generation evaluator. Its feedback is
not fed back into Claude in this condition; semantic-judge-guided repair should
use a separate result/work directory and be reported as a separate experiment.

Summarize compilation or semantic results with:

```bash
.venv/bin/python scripts/summarize_lean_results.py \
  --model claude-code-opus-5 \
  --results-root results/claude_code_opus5_semantic
```

## Interpretation

This is a coding-agent condition, not a direct replacement for the original
baseline. Claude receives compiler tools, persistent task files, and a variable
number of turns. Report it as a separate experimental condition from the
direct-API GPT and Opus runs.
