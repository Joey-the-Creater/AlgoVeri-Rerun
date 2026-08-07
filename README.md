# AlgoVeri Lean Rerun Results

This repository contains a rerun of AlgoVeri's 77-case Lean benchmark using
GPT-5.5, GPT-5.6 Sol, Claude Opus 5, and a Claude Code + Opus 5 coding-agent
condition. The local modifications remove the Lean runner's dependency on
Apptainer, add OpenAI and Anthropic model runners, preserve three independent
semantic-judge views, and provide a result-audit dashboard.

The complete academic report is available as both
[`reports/algoveri_rerun_report.tex`](reports/algoveri_rerun_report.tex) and the
compiled [`reports/algoveri_rerun_report.pdf`](reports/algoveri_rerun_report.pdf).

## Experimental settings

- Benchmark size: 77 Lean tasks
- Lean: `v4.25.0-rc2`
- Mathlib: pinned to the matching `v4.25.0-rc2` revision
- Reasoning effort: `medium`
- Maximum generation/repair rounds: 15
- Number of passes: 1
- Maximum output tokens: 32,768
- Semantic judges: `gpt-5.4` at temperatures 1 and 0; `gpt-5.6-sol` at
  temperature 0 with reasoning disabled
- Opus conditions: adaptive thinking and thinking disabled

The provider-specific meaning of `medium` is not necessarily identical across
OpenAI and Anthropic. Each result is one experimental run rather than an
estimate over multiple random seeds.

## Results

| Model/condition | Outputs | Lean verified | GPT-5.4 T1 | GPT-5.4 T0 | GPT-5.6 Sol T0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPT-5.5 | 77/77 | 75/77 (97.40%) | 24/77 | 24/77 | 24/77 |
| GPT-5.6 Sol | 77/77 | 71/77 (92.21%) | 25/77 | 27/77 | 30/77 |
| Claude Opus 5, adaptive thinking | 49/77 | 49/77 (63.64%) | 29/77 | 29/77 | 31/77 |
| Claude Opus 5, thinking disabled | 77/77 | 76/77 (98.70%) | 36/77 | 39/77 | 44/77 |
| Claude Code + Opus 5, enhanced 65-task scope | 65/65 | 63/65 (96.92%) | 53/65 | 53/65 | 55/65 |

Adaptive-thinking Opus repeatedly exhausted its output budget on thinking
without returning Lean text. A one-attempt pass over its missing cases raised
its completed count from 47 to 49. Thinking-disabled Opus completed all 77
tasks and achieved the strongest direct-API result in this rerun. The coding
agent is reported separately because it has compiler tools, multiple turns, and
an adaptive per-task budget.

## Published directories

- `results/full_three`: generation outputs for GPT-5.5, GPT-5.6 Sol, and
  adaptive-thinking Opus 5.
- `results/full_three_semantic`: the corresponding GPT-5.4 semantic judgments.
- `results/full_opus_no_thinking`: thinking-disabled Opus 5 generation outputs.
- `results/full_opus_no_thinking_semantic`: GPT-5.4 judgments for the
  thinking-disabled outputs.
- `results/claude_code_opus5`: enhanced coding-agent outputs for the 65 tasks
  without teacher-owned `sorry`.
- The matching `*_semantic_temp0` and `*_semantic_gpt56_temp0` directories hold
  the non-overwriting temperature-0 judgments.
- `reports/data`: the complete case-level CSV and recomputed JSON summary.

Each JSON file preserves the generated Lean code, verifier response, model
conversation history, and recorded token usage. No API keys or local runtime
logs are included.

## Known benchmark and evaluation issues

### Malformed `trie_search` scaffold

`algoveri_data/trie_search/lean_spec.lean` declares `is_valid_key` twice and
references an undefined `well_formed`. These errors are outside the four
model-editable sections, so the model cannot repair them under the benchmark
prompt. Direct compilation reports:

```text
line 62: `is_valid_key` has already been declared
line 69: Unknown identifier `well_formed`
line 79: Unknown identifier `well_formed`
```

### Teacher-owned `sorry` versus the semantic judge

The Lean generation prompt permits pre-existing `sorry` outside the editable
sections, primarily in teacher-provided termination proofs. The semantic judge
instead treats any visible `sorry` as cheating. Because the pipeline merges
student sections into the complete teacher scaffold before judging, the judge
can attribute teacher-owned termination placeholders to the model.

Twelve tasks contain such a `sorry` outside the editable regions. GPT-5.4 at
both temperatures rejected every compiler-verified direct-model answer on this
subset, although some also had independent algorithmic issues. GPT-5.6 Sol at
temperature 0 accepted one answer after correctly identifying the `sorry` terms
as teacher-owned.
For example, the judge described the generated `segmenttree_modify` algorithm
as genuine and appropriate, but rejected it because the teacher definitions
contained `decreasing_by all_goals sorry`.

The compiler-revision prompt also focuses only on correcting compiler messages
and does not restate the semantic requirement to preserve the exact named
algorithm. This can incentivize easier-to-prove alternatives that later fail
the stricter semantic judge.

The reported table preserves the original judge prompt for baseline
comparability. It should not be interpreted as a corrected score for these
prompt-ownership issues.

## Recompute summaries

From the repository root:

```bash
.venv/bin/python scripts/summarize_lean_results.py \
  --model gpt-5.5 --results-root results/full_three_semantic

.venv/bin/python scripts/summarize_lean_results.py \
  --model gpt-5.6-sol --results-root results/full_three_semantic

.venv/bin/python scripts/summarize_lean_results.py \
  --model claude-opus-5 --results-root results/full_three_semantic

.venv/bin/python scripts/summarize_lean_results.py \
  --model claude-opus-5 \
  --results-root results/full_opus_no_thinking_semantic
```

See `BASELINE_GPT55_GPT56.md` for environment setup and runner usage.

## Coding-agent condition

An additional runner uses Claude Code with Opus 5 as a tool-using coding agent.
It gives each benchmark case an isolated `Solution.lean` file and a constrained
Lean check command, then independently validates and recompiles the final
candidate. The enhanced default uses a $2 initial session and, only after an
independent failure, one preserved-workspace $2 compiler-repair session with
exact verifier feedback. Its outputs remain compatible with the existing
GPT-5.4 semantic filter, but should be reported separately from the direct-API
baseline because the agent has compiler tools and a variable number of turns.

See `CLAUDE_CODE_OPUS5.md` for the one-case smoke test, full 77-case command,
resume behavior, model/result switching, success-at-try comparisons, and
semantic-evaluation commands.

## Reproduce the paper tables

```bash
python3 scripts/analyze_rerun_results.py \
  --json-output reports/data/result_summary.json \
  --csv-output reports/data/case_results.csv \
  --latex-output reports/generated/case_tables.tex

cd reports
latexmk -pdf algoveri_rerun_report.tex
```
