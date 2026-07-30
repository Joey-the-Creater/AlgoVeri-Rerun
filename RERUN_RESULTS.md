# AlgoVeri Lean Rerun Results

This repository contains a rerun of AlgoVeri's 77-case Lean benchmark using
GPT-5.5, GPT-5.6 Sol, and Claude Opus 5. The local modifications remove the
Lean runner's dependency on Apptainer, add OpenAI and Anthropic model runners,
and preserve generation and GPT-5.4 semantic-judge outputs.

## Experimental settings

- Benchmark size: 77 Lean tasks
- Lean: `v4.25.0-rc2`
- Mathlib: pinned to the matching `v4.25.0-rc2` revision
- Reasoning effort: `medium`
- Maximum generation/repair rounds: 15
- Number of passes: 1
- Maximum output tokens: 32,768
- Semantic judge: `gpt-5.4`
- Opus conditions: adaptive thinking and thinking disabled

The provider-specific meaning of `medium` is not necessarily identical across
OpenAI and Anthropic. Each result is one experimental run rather than an
estimate over multiple random seeds.

## Results

| Model/condition | Outputs | Lean verified | Semantic full mark |
| --- | ---: | ---: | ---: |
| GPT-5.5 | 77/77 | 75/77 (97.40%) | 24/77 (31.17%) |
| GPT-5.6 Sol | 77/77 | 71/77 (92.21%) | 25/77 (32.47%) |
| Claude Opus 5, adaptive thinking | 49/77 | 49/77 (63.64%) | 29/77 (37.66%) |
| Claude Opus 5, thinking disabled | 77/77 | 76/77 (98.70%) | 36/77 (46.75%) |

Adaptive-thinking Opus repeatedly exhausted its output budget on thinking
without returning Lean text. A one-attempt pass over its missing cases raised
its completed count from 47 to 49. Thinking-disabled Opus completed all 77
tasks and achieved the strongest end-to-end result in this rerun.

## Published directories

- `results/full_three`: generation outputs for GPT-5.5, GPT-5.6 Sol, and
  adaptive-thinking Opus 5.
- `results/full_three_semantic`: the corresponding GPT-5.4 semantic judgments.
- `results/full_opus_no_thinking`: thinking-disabled Opus 5 generation outputs.
- `results/full_opus_no_thinking_semantic`: GPT-5.4 judgments for the
  thinking-disabled outputs.

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

Twelve tasks contain such a `sorry` outside the editable regions. Every
compiler-verified answer evaluated for these tasks received a negative semantic
verdict in these runs, although some also had independent algorithmic issues.
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
