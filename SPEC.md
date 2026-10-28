# India Job Market Visualizer — Design Spec

This document defines the India Job Market Visualizer. The project adapts the
upstream treemap tool to Indian data. It records every settled decision and the
reason for it. Implementation follows this document.

## Glossary

Define each term on first use.

- **PLFS** — Periodic Labour Force Survey. India's official employment survey,
  run by the National Statistical Office.
- **NCO** — National Classification of Occupations. India's occupation code
  system. This project uses NCO-2015.
- **NIC** — National Industrial Classification. India's industry code system.
- **ISCO-08** — International Standard Classification of Occupations, 2008.
- **MoSPI** — Ministry of Statistics and Programme Implementation.
- **Unit-level data** — one record per surveyed person, before aggregation.
- **Multiplier** — the survey weight. It states how many real people one
  surveyed person represents.
- **ps+ss** — principal status plus subsidiary status. India's standard
  definition of who counts as employed.
- **Minor group** — a 3-digit NCO code. NCO-2015 has 126 minor groups in this
  dataset.

## 1. Goal

Show how artificial intelligence exposure maps onto Indian employment. Each
rectangle is an occupation. Area is total employment. Color is a selected
metric.

The tool is a research instrument. It is not an official statistic.

## 2. Settled decisions

### 2.1 The eSankhyiki API cannot supply the core data

I queried the live MoSPI MCP server at `https://mcp.mospi.gov.in/mcp`.

The PLFS dataset there exposes 8 indicators: LFPR, WPR, unemployment rate,
percentage distribution of workers, and three earnings averages. Its filter
dimensions are NIC industry, employment status, enterprise size, enterprise
type, gender, state and year.

**There is no NCO dimension.** The API is industry-shaped. It also returns
percentages, not head counts.

Decision: the core data comes from PLFS unit-level microdata. The eSankhyiki
API supplies national context figures only.

Consequence: do not describe this project as eSankhyiki-backed.

### 2.2 The spine is NCO-2015 at 3 digits

About 126 minor groups, parsed from the official NCO-2015 Volume I. This is
the finest level that PLFS supports for both employment and earnings.

The reason is simple: **the latest PLFS rounds use NCO-2015.** The spine must
match the newest data, because the newest data drives every metric.

### 2.3 The workforce is the whole workforce

Include all workers aged 15 and above, on the ps+ss definition. This includes
self-employed workers, casual labour and agriculture.

Agriculture makes one very large rectangle. That is the intended result. About
45 percent of Indian workers are in agriculture, and the chart must show it.

Do not truncate the base data to make a prettier picture. Add filters instead.

### 2.4 One data frame: the latest PLFS

Every number in this tool comes from one release of PLFS, under the
post-January-2025 design. That release is **PLFS Calendar Year 2025, January to
December 2025**. See section 4.1 for its identifiers.

It covers a full 12 months, so no seasonal correction is needed.

MoSPI redesigned PLFS in January 2025. It states that comparisons across that
boundary may not be statistically valid. This tool never crosses that boundary,
so the warning does not apply to it.

The new design is better data, not merely newer. The sample rose from 12,800 to
22,692 first-stage units, and households per unit rose from 8 to 12. Cell sizes
at 3-digit NCO roughly double. Fewer groups hit the suppression rules in
section 2.13.

**Use the annual file, not a monthly or quarterly one.** Indian agricultural
employment swings hard by season, and agriculture is the largest rectangle on
the chart. A single month or quarter would distort the whole treemap. Two
shorter releases exist for 2025 and both cover April to December only. Do not
use them. They omit January to March, which spans the rabi harvest.

State the exact period in the output and on the page.

### 2.5 There is no trend layer

India publishes no occupational employment projections. No official body
forecasts employment by occupation. An earlier draft replaced the missing
projection with a measured trend across PLFS rounds. That is now cut.

The reasons:

- A trend needs rounds before January 2025. Those use the old sample design and
  the older NCO-2004 codes. Both breaks must be bridged.
- No published NCO-2004 to NCO-2015 concordance exists at 3 digits. The project
  would have to build one by hand, and the mapping is not one-to-one.
- Layout files differ between rounds, so seven extra rounds cost roughly seven
  times the parse work, not one time.
- The COVID-19 period sits in the middle of the series and distorts the fit.
- Where the concordance degrades to 2 digits, the resulting number carries
  almost no information, yet it still occupies a full color layer.

The cost is concentrated and large. The output is weak and heavily qualified.
The metric is not the question this tool asks.

**When to revisit.** The monthly series runs unbroken from April 2025 under one
design and one classification. Once it spans about four years, compute the
trend directly from it. No concordance, no break, no COVID-19 round. That is
the clean re-entry point. Do not add the layer before then.

### 2.6 Pay is median monthly earnings, harmonized

PLFS carries three incompatible earnings concepts:

- Regular wage or salaried workers — earnings for the preceding calendar month.
- Casual labour — wage per day.
- Self-employed workers — gross earnings over the last 30 days.

Harmonize all three to a monthly figure.

For casual labour, do not apply a 26-day convention. The microdata carries
actual wage earnings per day, for each of the 7 days of the reference week, for
up to 2 activities per day. Sum those 14 fields to get weekly earnings, then
multiply by 30/7. This is measured, so it beats an assumed month length.

Take the weighted median across all workers who report an earnings value.

Two holes are unavoidable, so expose both rather than hide them:

- Unpaid helpers in household enterprises report no earnings. Exclude them from
  the earnings median. Keep them in the employment count.
- Self-employment "gross earnings" is revenue-flavoured, not wage-flavoured. It
  overstates true labour income.

Add two fields so a reader can discount the number:

- `earnings_coverage` — the share of the group's workers who report earnings.
- `informality_share` — the share who are self-employed or casual labour.

**Keep zero earnings in the median.** PLFS never leaves these fields blank for
a worker who is not an unpaid helper. It writes 0. Measured against the real
2025 file, zero appears for 3 percent of regular salaried workers, 10.5 percent
of self-employed workers and 15.7 percent of casual labourers.

A zero is a reported value, so the literal reading of this section keeps it.
Keeping it also makes the weaker claim: the median then describes typical
monthly income from the occupation, including the people who earned nothing.
Dropping zeros would describe earnings among those who earned, which reads
higher and hides the volatility of casual work.

### 2.7 Education means the education workers hold

The upstream tool shows *typical entry-level education required*. India
publishes no such standard.

PLFS records the general education level a worker actually holds. That is an
observed distribution, not a requirement.

Use the weighted median category. Rename the layer to **"Education level of
workers"**.

Do not reuse the inherited label. The gap between held and required credentials
is wide in India, and the label must not paper over it.

### 2.8 One AI exposure score

The inherited prompt assumes a high-wage, formal, digitized economy. India
inverts several of those assumptions.

Write one India rubric from scratch, against Indian labour market conditions.
Do not port the inherited rubric and patch it.

Keep the 0-10 scale. Add explicit clauses for the cost of automation against
the prevailing local wage, and for informality.

`exposure_in` is the only exposure column and the default treemap layer.

The rubric ships in `scripts/05_score.py`. Scoring runs `google/gemini-3.6-flash`
through OpenRouter, and `data/scores_in.json` records the model under `_meta`.

### 2.9 Occupation text for scoring comes from NCO-2015

Feed the model, per minor group:

- The official NCO-2015 group definition text.
- The titles of every 4-digit unit group beneath it.
- The status mix and the informality share, so the model can see how the work
  is actually organized in India.

Do not use National Career Service role pages for the first version. They need
a separate mapping step and add little over the NCO text.

### 2.10 Employment counts scale to the official total

Sum the PLFS multipliers to estimate workers per group. The multiplier divisor
is **100**. This is measured: mult over 100, summed across the person file,
gives 1,193.3 million people and 518.6 million workers aged 15 and above.

The worker estimate uses 494,645 sampled persons, who carry the weight of all
workers.

Validate the estimate against the official series. The eSankhyiki API reports
the CY 2025 all-India WPR (ps+ss, 15 years and above) as 57.4 percent. The
file reproduces this exactly: 518,617,651 workers over a 15-plus population of
903,069,716 gives 57.4283 percent. The unscaled estimate is therefore what
MoSPI itself reports.

**Ship with the scaling factor at 1.1898.** The default run of
`03_tabulate.py` applies it. The override flag `--total-workers` stays in the
code for later correction.

The factor's math:

- Official CY 2025 WPR, ps+ss, 15-plus: 57.4 percent.
- Technical Group 2019 projected mid-2025 population aged 15-plus: 1,075
  million. The projection interpolds the official 2021 and 2026 figures
  (1,366.4 and 1,441.6 million total).
- Target worker total: 0.574 x 1,075,000,000 = 617,050,000 (61.7 crore).
- Measured worker total: 518,617,651.
- Factor: 617,050,000 / 518,617,651 = 1.1898.

Two other anchors were checked and rejected:

- The PLFS 2025 annual report counts 30 crore households at an average of 4
  persons each, giving 1.2 billion people. That is a total-population figure,
  so it cannot feed the 15-plus WPR directly.
- The UN WPP 2024 projection gives 623.9 million workers (factor 1.2031).

The 61.7 crore anchor uses only India's own official projection and the
official WPR, which is why it is the settled decision.

The factor spreads one flat correction across every occupation. It does not
change any share, median or rate. The full derivation lives in `MATH.md`.

Record the factor and the target in the output. A reader must be able to see
them. State on the page that counts are PLFS estimates rescaled to the
projected 15-plus population.

### 2.11 Scope is all-India, with two filters

State-level cells are too thin at 3-digit NCO. Defer state drill-down.

Ship two filters, because PLFS supports both well at national level:

- Rural, urban, or all.
- Female, male, or all.

Precompute all nine combinations. The result is 1,141 rows in
`data/occupations_in.csv`, which is small enough to ship in one JSON file.
`data/tabulate_meta.json` records the row count and the scaling factor.

### 2.12 Female share is a color layer

India's female labour force participation is one of the most distinct features
of its labour market. The field costs nothing extra to compute.

Add `female_share` as the fourth color layer.

### 2.13 Thin cells are flagged, not hidden

Carry the unweighted sample count `sample_n` for every cell.

- `sample_n < 50` — set `low_confidence = true`. Render a hatch pattern.
- `sample_n < 20` — suppress earnings and education. Keep employment.

The larger post-2025 sample means fewer groups trip these rules. Keep the rules
anyway. They protect the thin tail of the occupation distribution.

Measured against the 2025 file: 3 cells in the all/all cut are low confidence,
and 1 cell is suppressed.

### 2.14 There is no US comparison

This project adapts the software. It does not compare the two countries.

No SOC crosswalk. No second exposure score. No US columns in the schema. No US
baseline data in the repository. Nothing in the pipeline may depend on US data.

Delete the inherited US artifacts during the rebuild: `html/`, `pages/`,
`occupations.csv`, `occupations.json`, `scores.json`, `prompt.md`,
`occupational_outlook_handbook.html` and the old `site/data.json`. Git history
retains them, so the deletion is reversible.

Every number in this tool comes from an Indian source.

## 3. Output schema

One record per minor group, per filter combination.

| Field | Type | Note |
|---|---|---|
| `nco_code` | string | 3-digit NCO-2015 |
| `title` | string | Official minor group title |
| `division` | string | 1-digit parent, used for treemap grouping |
| `subdivision` | string | 2-digit parent |
| `isco_code` | string | ISCO-08 equivalent. NCO-2015 aligns to ISCO-08 at 3 digits, so the code carries over |
| `cut_sector` | string | `all`, `rural` or `urban` |
| `cut_sex` | string | `all`, `female` or `male` |
| `workers` | int | PLFS estimate, scaled by the factor in `meta` |
| `sample_n` | int | Unweighted count |
| `female_share` | float | 0 to 1 |
| `rural_share` | float | 0 to 1 |
| `status_mix` | object | Self-employed, regular, casual shares |
| `informality_share` | float | 0 to 1 |
| `median_monthly_earnings_inr` | int \| null | Harmonized |
| `earnings_coverage` | float | 0 to 1 |
| `education_median` | string \| null | Observed level |
| `exposure_in` | int | 0 to 10 |
| `exposure_in_rationale` | string | |
| `low_confidence` | bool | |

Record once, at the top level of `site/data.json`, under `meta`: the survey
period, the scaling factor, the PLFS release identifier and the model used for
scoring. `site/data.json` holds 1,132 rows today. One NCO code, 343, has
employment but no parsed NCO description, so it does not appear in the site
data.

## 4. Pipeline

```
data/
  plfs/raw/          user-downloaded archive, git-ignored
  plfs/              household and person Parquet, git-ignored
  nco/               NCO-2015 source PDF, raw text and parsed JSON
  reference/         PLFS docs and the committed variable dictionary
    plfs_2025_variables.json   from the public NADA API
    plfs_docs/       official layouts, schedules and instructions
scripts/
  01_check_inputs.py       verify the download against a manifest
  02_parse_plfs.py         fixed-width to Parquet
  03_tabulate.py           weighted aggregation to NCO 3-digit, all cuts
  04_nco_descriptions.py   NCO-2015 PDF to per-group description JSON
  05_score.py              India rubric through OpenRouter
  06_build_site_data.py    merge into site/data.json
site/
  index.html
  data.json
```

### 4.1 Source dataset and variable map

| Item | Value |
|---|---|
| Catalog page | `https://microdata.gov.in/NADA/index.php/catalog/284` |
| Reference ID | `DDI-IND-NSO-PLFS-Jan2025-Dec2025` |
| Published | 27 March 2026 |
| Household file `F1` | `chhv12025`, 270,472 records, 48 variables |
| Person file `F2` | `cperv12025`, 1,148,634 records, 153 variables |

The full variable dictionary is public through the NADA API, and no login is
needed to read it. A copy is committed at
`data/reference/plfs_2025_variables.json`. Refresh it with:

```
curl "https://microdata.gov.in/NADA/index.php/api/catalog/DDI-IND-NSO-PLFS-Jan2025-Dec2025/variables"
```

The variables this project needs, all confirmed present:

| Purpose | Variable | Label |
|---|---|---|
| Occupation, principal | `ocu_pas` | Occupation Code (NCO) |
| Occupation, subsidiary | `ocu_sas` | Occupation Code (NCO) |
| Activity status, principal | `pas` | Status Code |
| Activity status, subsidiary | `sas` | Status Code |
| Education | `gedu_lvl` | General Education Level |
| Age | `age` | |
| Gender | `sex` | |
| Rural or urban | `sec` | Sector |
| Survey weight | `mult` | Multiplier, in both files |
| Design fields | `nsc`, `zst`, `panel`, `st` | Needed for correct estimation |
| Earnings, regular | `ern_reg` | Earnings for regular salaried or wage activity |
| Earnings, self-employed | `ern_self` | Earnings for self-employed |
| Earnings, casual | `ern11`…`ern17`, `ern21`…`ern27` | Wage earning per day, 7 days, 2 activities |
| Informality | `job_pas`, `leave_pas`, `ssec_pas` | Job contract, paid leave, social security |

Two notes for the implementer:

- `ocu_pas` and `ocu_sas` are 3-digit NCO codes. Confirm the NCO version
  against the survey instrument before mapping, because PLFS used NCO-2004 in
  its earlier rounds. See section 2.2.
- The ps+ss definition needs both the principal and the subsidiary columns.
  Assign each worker to their principal occupation. Use the subsidiary columns
  only to decide who counts as employed.

## 5. Manual step

PLFS unit-level data needs a registered account on `microdata.gov.in`. The
portal states plainly: "To access data for this study, user must be logged in."
No script can complete that step, and no agent should register an account on a
user's behalf.

Only one PLFS release is needed, because the tool uses one data frame. The
download is a single archive from catalog 284.

The metadata is not gated. The variable dictionary in section 4.1 came from the
public API, so `02_parse_plfs.py` can be written and reviewed before anyone
logs in. Only the final run needs the file.

`01_check_inputs.py` checks the result against a manifest of expected files and
prints the download steps when a file is missing. The upstream tool had the
same shape of problem. Its scraper needed a visible browser, because the source
site blocks robots. A manual step is acceptable here.

## 6. Front-end changes

- Currency is the rupee. Format earnings as monthly rupees.
- Use Indian digit grouping for worker counts. Use lakh and crore labels.
- Four color layers, in this order: Median monthly earnings, Education level
  of workers, AI exposure, Female share.
- **Median monthly earnings is the default layer.**
- Two filter controls: rural and urban, and gender.
- Show the survey period in the page header, for example "12 months to June
  2026".
- The detail panel shows `exposure_in` and its rationale, `earnings_coverage`,
  `informality_share`, `status_mix` and `sample_n`.
- Grey means "no data". Never let a null value render as a mid-scale color.

## 7. What this tool must not claim

- It does not publish an official statistic.
- It shows one period. It shows no trend and no projection.
- It does not measure required education. It measures held education.
- Self-employment earnings overstate labour income.
- Exposure scores are model estimates, not predictions of job loss.

Put these statements on the page, not only in this file.