# LastDance AlgoVeri Lean extension paper

The report presents the rerun as a direct extension of the findings in the original
ICML 2026 AlgoVeri paper. It uses the official ICML 2026 preprint format and is
self-contained and ready to upload to Overleaf. It also separates comparisons with
general open-weight AlgoVeri generators from Goedel-Code-Prover and other open neural
provers, whose published AlgoVeri evaluation is proof-only. LastDance is the report's
name for the constrained Claude Code + Opus 5 toolchain:

- `algoveri_rerun_report.tex`: main paper source
- `references.bib`: bibliography
- `icml2026.sty` and `icml2026.bst`: official conference template files
- `generated/case_tables.tex`: generated 77-task matrix and judge disagreements
- `data/result_summary.json`: aggregate statistics and task inventories
- `data/case_results.csv`: every condition/task outcome and full judge analysis
- `data/external_open_systems.csv`: published open-system comparisons with protocol provenance
- `data/category_results.csv`, `data/repair_curves.csv`, and `data/outcome_breakdown.csv`:
  machine-readable data behind the new figures
- `figures/`: vector pipeline, category, repair-depth, and outcome figures
- `prompts/`: exact legacy LastDance templates plus the robust initial,
  source-targeted repair templates
- `algoveri_rerun_report.pdf`: compiled conference-style paper

Compile with a standard TeX Live installation:

```bash
latexmk -pdf algoveri_rerun_report.tex
```

Alternatively, Tectonic can compile the same source:

```bash
tectonic algoveri_rerun_report.tex
```

Regenerate the tables and data from the repository root before compiling:

```bash
python3 scripts/analyze_rerun_results.py \
  --json-output reports/data/result_summary.json \
  --csv-output reports/data/case_results.csv \
  --latex-output reports/generated/case_tables.tex
python3 scripts/export_lastdance_prompts.py
python3 scripts/generate_report_figures.py
```
