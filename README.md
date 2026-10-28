# India Job Market Visualizer

A research tool for exploring India's employment structure by occupation. It
builds an interactive treemap of the Indian workforce. Each rectangle is an
occupation (NCO-2015 minor group). **Area** is total employment. **Color**
shows a selected metric — AI exposure, median monthly earnings, education level
of workers, or female share.

The data is one official source: the Periodic Labour Force Survey (PLFS)
Calendar Year 2025, January to December 2025, distributed by MoSPI's National
Data Archive. This is a development tool. It is not a report or an official
statistic.

## What's here

- **126 NCO-2015 minor groups**, covering all workers aged 15 and above on the
  principal-plus-subsidiary status definition — including agriculture,
  self-employment and casual labour.
- **617 million workers (61.7 crore)**, estimated from the PLFS survey weights
  and rescaled to India's projected population. The multiplier formula is
  `workers = sum(mult / 100) x 1.1898` per group, where `mult` is the survey
  weight. The raw weighted total is 518,617,651.38 workers, which reproduces
  the official CY 2025 WPR exactly: 57.43 percent measured versus 57.4 percent
  published by MoSPI. The factor 1.1898 rescales to the official WPR applied
  to the Technical Group 2019 projected 15-plus population (1,075 million =
  61.7 crore workers). See SPEC.md section 2.10 for the settled math.
- **Nine filter combinations**: rural / urban / all × female / male / all,
  precomputed in one JSON file.
- **Four color layers**: median monthly earnings (default), education level of
  workers, AI exposure, female share.
- **Confidence flags**: cells with fewer than 50 sample records render with a
  hatch pattern; below 20 records, earnings and education are suppressed.

## LLM-powered scoring

`scripts/05_score.py` scores each occupation group for AI exposure (0-10)
through OpenRouter. The India rubric is written from scratch. It weighs the
cost of automation against prevailing Indian wages and the informality of the
work, so the scores do not simply reflect US task content.

**What "AI exposure" is NOT:**
- It does **not** predict that a job will disappear. It estimates how much
  current AI reshapes the tasks of the work.
- The scores are rough LLM estimates, not rigorous predictions.
- Self-employed and casual workers dominate Indian employment. Their earnings
  figures and AI scores carry larger uncertainty than regular workers' do.

## Data pipeline

The canonical decisions live in [`SPEC.md`](SPEC.md). The full derivation of
the worker totals lives in [`MATH.md`](MATH.md). Run the steps in order:

1. **Check inputs** (`scripts/01_check_inputs.py`) — verify the PLFS download
   under `data/plfs/raw/`. The data is gated behind a free `microdata.gov.in`
   account (see SPEC section 5).
2. **Parse** (`scripts/02_parse_plfs.py`) — fixed-width PLFS CSV files become
   household and person Parquet files. Code columns stay zero-padded strings.
3. **Tabulate** (`scripts/03_tabulate.py`) — weighted aggregation to 3-digit
   NCO cells for all nine cuts. Uses `mult / 100` as the survey weight,
   applies the scaling factor 1.1898 (SPEC.md section 2.10; override with
   `--total-workers`), harmonizes the three earnings concepts, and applies
   the suppression rules. Writes `data/occupations_in.csv` and
   `data/tabulate_meta.json`.
4. **Describe** (`scripts/04_nco_descriptions.py`) — parses the official
   NCO-2015 Volume I PDF into per-group titles, definitions and unit groups.
   Writes `data/nco/nco_descriptions.json`.
5. **Score** (`scripts/05_score.py`) — sends each group's NCO text and PLFS
   labour context to the LLM with the India rubric. Writes
   `data/scores_in.json`. Fork this to write your own prompt.
6. **Build site data** (`scripts/06_build_site_data.py`) — merges the
   tabulation, descriptions and scores into `site/data.json`.
7. **Website** (`site/index.html`) — the interactive treemap.

## Key files

| File | Description |
|------|-------------|
| `SPEC.md` | Settled design decisions, schema, pipeline and source map |
| `data/plfs/plfs_2025_per.parquet` | Person-level PLFS microdata (git-ignored) |
| `data/occupations_in.csv` | Weighted tabulation, all cuts (git-ignored) |
| `data/nco/nco_descriptions.json` | NCO-2015 group text for scoring (git-ignored) |
| `data/scores_in.json` | AI exposure scores and rationale (git-ignored) |
| `site/data.json` | Compact site payload |
| `site/index.html` | Single-page treemap |

Generated artifacts (`*.parquet`, `occupations_in.csv`, the NCO JSON files,
scores) are git-ignored because they derive from login-gated microdata.
`scores_in.json` is committed so the site builds without a paid model run.

## Setup

```
uv sync
```

Requires an OpenRouter API key in `.env` (only for rescoring):

```
OPENROUTER_API_KEY=your_key_here
```

## Usage

```bash
# Verify the PLFS download (data/plfs/raw/)
python scripts/01_check_inputs.py

# Parse CSV to Parquet
python scripts/02_parse_plfs.py

# Tabulate (default applies the 1.1898 scaling factor; override with --total-workers)
python scripts/03_tabulate.py

# Parse NCO-2015 Volume I PDF
python scripts/04_nco_descriptions.py

# Score AI exposure (uses OpenRouter API; results cached)
python scripts/05_score.py

# Rebuild site data from any changed inputs
python scripts/06_build_site_data.py

# Serve the site locally
cd site && python -m http.server 8000
```

## Limits

- One survey period only. No trend, no projection.
- Education layer shows the education workers hold, not education a job needs.
- Self-employment earnings are revenue-flavoured and overstate labour income.
- Counts are PLFS estimates rescaled 1.1898x to the Technical Group 2019
  projected 15-plus population. The rescale is one flat factor, so it
  corrects nothing about how the occupations differ from the frame.
- Do not erase these limits from the page.