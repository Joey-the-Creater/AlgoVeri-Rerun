# Reproducing the Lean baseline with GPT-5.5, GPT-5.6 Sol, and Claude Opus 5

These runners preserve AlgoVeri's one-pass, 15-attempt protocol. An attempt is
the initial generation or a compiler-feedback revision. Both models use the
OpenAI Responses API or Anthropic Messages API with explicit `medium` effort
and a 32,768-token output ceiling by default.

## 1. Prerequisites

- Python 3.10 or newer.
- `git`, `wget`, and `zstd` for the local Lean/Mathlib installation.
- An OpenAI API project with access to `gpt-5.5` and `gpt-5.6-sol`.
- An Anthropic account with access to `claude-opus-5`.
- API keys exported as `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`; do not commit
  either key to this repository.

Create the Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If the host Python lacks `ensurepip`, install `virtualenv` in your user account
and create the same isolated environment with:

```bash
python3 -m pip install --user virtualenv
python3 -m virtualenv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 2. Install Lean and Mathlib locally

The benchmark pins both Lean and Mathlib to `v4.25.0-rc2`. No container
runtime is required:

```bash
bash scripts/local_setup/lean.sh
```

The script downloads the Lean release to `lean_env/lean_bin`, creates a Lake
project in `lean_env/lean_project`, and downloads Mathlib's precompiled cache.
It requires Git because Lake uses it to resolve Mathlib dependencies. On a
minimal Ubuntu installation, install the prerequisites first:

```bash
sudo apt update
sudo apt install -y git wget zstd
```

The checked-in configuration already selects the local verifier:

```yaml
lean:
  method: local
  timeout: 300
  local:
    lake_path: lean_env/lean_bin/bin/lake
    project_path: lean_env/lean_project
```

Test the verifier before spending API credits:

```bash
python -m test.test_lean_verify
```

The repository's verifier test intentionally contains `sorry`, so this checks
the toolchain and Mathlib resolution, not benchmark correctness.
The OpenAI runners repeat a small `import Mathlib` preflight automatically and
exit before making a paid request if the environment is unavailable.

Check that your API project recognizes both model IDs without generating
tokens:

```bash
python scripts/check_openai_model_access.py gpt-5.5 gpt-5.6-sol
```

Anthropic's canonical API model ID is `claude-opus-5`. The runner uses the
native Messages API, preserves thinking blocks during multi-turn repair, and
passes `output_config={"effort": "medium"}`.

After exporting `ANTHROPIC_API_KEY`, check model access without generating
tokens:

```bash
python scripts/check_anthropic_model_access.py claude-opus-5
```

## 3. Check task discovery without API calls

```bash
OPENAI_API_KEY=placeholder LIST_ONLY=1 \
  bash scripts/runs_example_scripts/run_task_gpt-5-5.sh
```

This should print 77 task names.

## 4. Run a one-task smoke test

This step makes paid API calls:

```bash
export OPENAI_API_KEY='YOUR_KEY'

TASK=stack_push MAX_ROUNDS=2 DEBUG=1 \
  bash scripts/runs_example_scripts/run_task_gpt-5-5.sh

TASK=stack_push MAX_ROUNDS=2 DEBUG=1 \
  bash scripts/runs_example_scripts/run_task_gpt-5-6-sol.sh

TASK=stack_push MAX_ROUNDS=2 DEBUG=1 \
  bash scripts/runs_example_scripts/run_task_claude-opus-5.sh
```

Ensure the value has no trailing newline. If loading it from a file, use a
method that strips the line ending rather than exporting the raw file bytes.

## 5. Run the comparable 1x15 baselines

```bash
REASONING_EFFORT=medium MAX_ROUNDS=15 NUM_PASSES=1 \
  bash scripts/runs_example_scripts/run_task_gpt-5-5.sh

REASONING_EFFORT=medium MAX_ROUNDS=15 NUM_PASSES=1 \
  bash scripts/runs_example_scripts/run_task_gpt-5-6-sol.sh

REASONING_EFFORT=medium MAX_ROUNDS=15 NUM_PASSES=1 \
  bash scripts/runs_example_scripts/run_task_claude-opus-5.sh
```

To run all three sequentially with identical shell settings:

```bash
REASONING_EFFORT=medium MAX_ROUNDS=15 NUM_PASSES=1 \
  bash scripts/runs_example_scripts/run_lean_three_models.sh
```

Results are written to `test_results_scale/lean/`. Existing completed task
files are overwritten when that task is rerun, so use a distinct
`RESULTS_ROOT` for each experimental condition.

For example:

```bash
RESULTS_ROOT=results/gpt55_medium \
  bash scripts/runs_example_scripts/run_task_gpt-5-5.sh
```

The generic `MAX_OUTPUT_TOKENS` setting defaults to 32768 for every model.
Change it only as a separately recorded experimental condition.

## 6. Compute compiler and strict success rates

Compiler verification is available immediately:

```bash
python scripts/summarize_lean_results.py \
  --model gpt-5.5 --results-root test_results_scale
```

For the paper's stricter semantic-filtered metric, keep the judge fixed across
models. The released example uses GPT-5.4 as judge:

```bash
TEST_MODEL=gpt-5.5 JUDGE_MODEL=gpt-5.4 \
  bash scripts/runs_example_scripts/run_lean_semantic_filter.sh

TEST_MODEL=gpt-5.6-sol JUDGE_MODEL=gpt-5.4 \
  bash scripts/runs_example_scripts/run_lean_semantic_filter.sh

TEST_MODEL=claude-opus-5 JUDGE_MODEL=gpt-5.4 \
  bash scripts/runs_example_scripts/run_lean_semantic_filter.sh
```

The strict score counts a task only when at least one attempt has
`verified=true`, `parsed=true`, and `verdict=true`.

## Experimental controls

- Keep `REASONING_EFFORT`, `MAX_OUTPUT_TOKENS`, `MAX_ROUNDS`, and `NUM_PASSES`
  identical when comparing the three models.
- Start at `medium`; only evaluate higher efforts as separate treatments.
- Be aware that effort is provider-specific: matching the label controls the
  experiment but does not guarantee identical internal compute.
- Record the provider, model slug, effort, output ceiling, benchmark revision,
  Lean/Mathlib version, and semantic judge model with every reported score.
- Do not silently remove malformed tasks. In the current corpus,
  `trie_search/lean_spec.lean` appears to contain fixed scaffold errors; report
  it separately if the pinned toolchain confirms that diagnosis.
