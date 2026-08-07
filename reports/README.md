# AlgoVeri Lean rerun paper

The report is self-contained and ready to upload to Overleaf:

- `algoveri_rerun_report.tex`: main paper source
- `references.bib`: bibliography
- `generated/case_tables.tex`: generated 77-task matrix and judge disagreements
- `data/result_summary.json`: aggregate statistics and task inventories
- `data/case_results.csv`: every condition/task outcome and full judge analysis
- `algoveri_rerun_report.pdf`: compiled 14-page paper

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
```
