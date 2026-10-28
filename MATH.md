# The Math Behind the Worker Estimates

This file explains every calculation behind the worker counts in
`site/data.json`. It accompanies SPEC.md section 2.10.

## 1. The multiplier formula

PLFS stores one survey weight per person row, named `mult`. The weight is
scaled by 100. One sampled person therefore represents `mult / 100` real
people.

```
workers in a cell = sum(mult / 100) over the cell's worker records
```

A worker record must meet all three tests:

- Age 15 or above (`age >= 15`).
- Employed on the principal or subsidiary status (activity status in
  `{11, 12, 21, 31, 41, 51}`). This is the ps+ss definition.
- Carry a valid 3-digit NCO-2015 occupation code.

## 2. Verified numbers

All figures come from `data/plfs/plfs_2025_per.parquet`, recalculated from
scratch. No value below is taken from a publication.

| Quantity | Value |
|---|---|
| Person records in the file | 1,148,634 |
| Worker records used | 494,645 |
| Weighted total population, all ages | 1,193,276,050 |
| Weighted population aged 15+ | 903,069,716 |
| Weighted workers aged 15+ | 518,617,651 |
| Implied WPR | 57.4283 percent |
| Sample share of the population | 43.064 percent |

## 3. The WPR validates against the official series

MoSPI's eSankhyiki service publishes the CY 2025 all-India WPR as 57.4
percent, for ps+ss, ages 15 and above. The file reproduces it:

```
518,617,651 / 903,069,716 = 57.4283 percent
```

The official number rounds to 57.4. The match proves the multiplier pipeline
is correct. MoSPI publishes PLFS rates only. It publishes no worker head
count for CY 2025, so the absolute total is an estimate by construction.

The monthly series (current weekly status) averages 52.4 percent over the
nine released months of 2025. It uses a different status definition and is
not comparable.

## 4. The scaling factor

The totals in section 2 are the survey speaking for itself. A scaling factor
is applied when an outside anchor exists for the 2025 population. The shipped
factor comes from the paragraph marked "settled".

### 4.1 No rescale — factor 1.0, 51.9 crore

The weights already reproduce the official WPR exactly. This option keeps
the survey's own estimate: 518.6 million workers.

### 4.2 Household count — factor 1.0056, 52.2 crore (rejected)

The PLFS CY 2025 annual report counts 30 crore households at an average of 4
persons each.

```
population estimate = 300,000,000 x 4 = 1,200,000,000
factor = 1,200,000,000 / 1,193,276,050 = 1.0056
workers = 518,617,651 x 1.0056 = 521,539,992
```

The report's count and the measured population agree to 0.56 percent, which
validates the multipliers. The option is rejected because a total-population
figure cannot feed the 15-plus WPR directly, and it changes the total by
under one percent.

### 4.3 UN WPP 2024 projection — factor 1.2031, 62.4 crore (rejected)

```
projected 15-plus population = 1,087,000,000
workers = 0.574 x 1,087,000,000 = 623,938,000
factor = 623,938,000 / 518,617,651 = 1.2031
```

Rejected because it imports a non-Indian population projection.

### 4.4 Technical Group 2019 projection — factor 1.1898, 61.7 crore (settled)

The Report of the Technical Group on Population Projections 2011-2036 is
India's official projection. Its 2021 and 2026 totals are 1,366.4 million
and 1,441.6 million. Interpolating to mid-2025 gives about 1,434 million.
The 15-plus share is about 75 percent, giving 1,075 million.

```
workers = 0.574 x 1,075,000,000 = 617,050,000 (61.7 crore)
factor = 617,050,000 / 518,617,651 = 1.1898
```

This is the shipped decision. It uses only the official WPR and the official
Indian population projection.

## 5. Sensitivity table

| Anchor | Target workers | Factor | Display |
|---|---|---|---|
| Survey as-is | 518,617,651 | 1.0000 | 51.9 crore |
| Household count | 521,539,992 | 1.0056 | 52.2 crore |
| TG projection (settled) | 617,050,000 | 1.1898 | 61.7 crore |
| UN WPP 2024 | 623,938,000 | 1.2031 | 62.4 crore |
| Round 600 million headline | 600,000,000 | 1.1569 | 60.0 crore |

## 6. Where the values live

| File | Item | Value |
|---|---|---|
| `scripts/03_tabulate.py` | `MULT_DIVISOR` | 100 |
| `scripts/03_tabulate.py` | `WPR_OFFICIAL` | 0.574 |
| `scripts/03_tabulate.py` | `POPULATION_15PLUS_ESTIMATE` | 1,075,000,000 |
| `scripts/03_tabulate.py` | `DEFAULT_TOTAL_WORKERS` | 617,050,000 |
| `data/tabulate_meta.json` | `scaling_factor` | 1.1898 |
| `data/tabulate_meta.json` | `total_workers_target` | 617,050,000 |
| `site/data.json` | `meta.scaling_factor` | 1.1898 |

The all/all cut of `site/data.json` sums to 615,881,465 workers, which shows
as 61.59 crore. The gap to the 617,050,000 target is about 1.17 million
workers in NCO code 343. Code 343 has employment data but no parsed NCO-2015
description, so `06_build_site_data.py` excludes it from the site data.

## 7. Sources

- PLFS CY 2025 microdata, reference ID DDI-IND-NSO-PLFS-Jan2025-Dec2025,
  catalog 284 on microdata.gov.in.
- eSankhyiki API, PLFS dataset, indicator WPR, annual, ps+ss, calendar year
  2025, all India, ages 15 and above: 57.4 percent.
- Report of the Technical Group on Population Projections 2011-2036,
  National Commission on Population, Ministry of Health and Family Welfare,
  November 2019.
- UN World Population Prospects 2024 (rejected anchor).