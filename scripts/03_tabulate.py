"""03_tabulate.py - PLFS 2025 weighted aggregation to NCO 3-digit cells.

Reads the person and household Parquet files produced by 02_parse_plfs.py and
writes data/occupations_in.csv plus data/tabulate_meta.json.

Estimates follow SPEC.md sections 2.3, 2.6, 2.7, 2.10 to 2.13 and 4.1.
Survey period: PLFS Calendar Year 2025, January to December 2025.
Scope: all India, no state drill-down (section 2.11).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# PLFS stores the multiplier multiplied by MULT_DIVISOR. DIVIDED by 100 and
# summed over all person rows, mult gives 1193 million people and 519 million
# workers aged 15 and above. Both match published India figures.
MULT_DIVISOR = 100

# Rescale target, from SPEC.md section 2.10. The target is the official CY
# 2025 WPR (57.4 percent, ps+ss, 15+) applied to the Technical Group 2019
# projected 15-plus population of 1,075 million: 0.574 x 1,075,000,000 =
# 617,050,000 workers (61.7 crore). When --total-workers is omitted,
# 03_tabulate.py applies this target, so a default run reproduces the
# shipped site data.
WPR_OFFICIAL = 0.574
POPULATION_15PLUS_ESTIMATE = 1_075_000_000
DEFAULT_TOTAL_WORKERS = WPR_OFFICIAL * POPULATION_15PLUS_ESTIMATE
SCALING_FACTOR = DEFAULT_TOTAL_WORKERS / 518617651.38

# Activity status codes, verified against Schedule 10.4 Block 5.1 col (3),
# shipped with the PLFS 2025 release. Education codes verified against col (8).
SELF_EMPLOYED = {"11", "12", "21"}  # own-account worker, employer, unpaid helper
REGULAR = {"31"}  # regular wage or salaried
CASUAL = {"41", "51"}  # casual labour: public works, other work
# Verified against Schedule 10.4, Block 5.1 col (3). There is no code 42.
EMPLOYED = SELF_EMPLOYED | REGULAR | CASUAL  # ps+ss employed definition

# General education codes, zero padded, in ordinal order. There is no code 09.
# The list order below is the ordinal order used for the weighted median.
GEDU_LABELS = {
    "01": "Not literate",
    "02": "Literate without formal schooling, EGS/NFEC/AEC",
    "03": "Literate without formal schooling, TLC",
    "04": "Literate without formal schooling, other",
    "05": "Below primary",
    "06": "Primary",
    "07": "Middle",
    "08": "Secondary",
    "10": "Higher secondary",
    "11": "Diploma or certificate",
    "12": "Graduate",
    "13": "Postgraduate and above",
}
GEDU_RANK = {code: i + 1 for i, code in enumerate(GEDU_LABELS)}
RANK_TO_LABEL = {i + 1: label for i, label in enumerate(GEDU_LABELS.values())}

OUT_COLUMNS = [
    "nco_code",
    "cut_sector",
    "cut_sex",
    "cut_age",
    "workers",
    "sample_n",
    "female_share",
    "rural_share",
    "status_mix",
    "informality_share",
    "median_monthly_earnings_inr",
    "earnings_coverage",
    "education_median",
    "low_confidence",
]

# Stat keys produced by cell_stats, in the order tabulate_cut emits them.
CELL_STAT_COLUMNS = [
    "nco_code",
    "cut_sector",
    "cut_sex",
    "cut_age",
    "workers_w",
    "sample_n",
    "female_share",
    "rural_share",
    "status_mix_json",
    "informality_share",
    "earnings_median",
    "earnings_coverage",
    "education_rank_median",
]

# The filter combinations from section 2.11, in a fixed display order.
# 3 sectors x 3 sexes x 5 age bands = 45 cuts.
CUT_SECTORS = ["all", "rural", "urban"]
CUT_SEXES = ["all", "female", "male"]
# Age bands in completed years. 15-29 matches the PLFS youth definition.
AGE_BANDS = {
    "15-29": (15, 29),
    "30-44": (30, 44),
    "45-59": (45, 59),
    "60+": (60, 200),
}
CUT_AGES = ["all", *AGE_BANDS]

# Casual earnings fields: activity 1 and 2, days 1 to 7 (section 2.6).
CASUAL_COLUMNS = [f"ern{i}{d}" for i in (1, 2) for d in range(1, 8)]

PERSON_REQUIRED = {
    "ocu_pas", "ocu_sas", "pas", "sas", "gedu_lvl", "age", "sex", "sec",
    "mult", "ern_reg", "ern_self",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_parquet(path: Path) -> pd.DataFrame:
    if not path.is_file():
        fail(
            f"input parquet not found: {path}. "
            "Run scripts/02_parse_plfs.py to create it from the PLFS archive "
            "before running this script."
        )
    return pd.read_parquet(path)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Weighted median: the value at 50 percent of cumulative weight.

    Ties at the midpoint resolve to the lower value, matching the common
    median convention for discrete categories such as gedu_lvl.
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.size == 0:
        return np.nan
    order = np.argsort(values, kind="mergesort")
    cumulative = np.cumsum(weights[order])
    total = cumulative[-1]
    if total <= 0:
        return np.nan
    index = int(np.searchsorted(cumulative, 0.5 * total))
    return float(values[order[index]])


def prepare_workers(per: pd.DataFrame) -> pd.DataFrame:
    """Return one row per worker (age 15+, ps+ss employed) with derived fields."""
    mult = numeric(per["mult"])
    weight_ok = mult.notna()
    if int(weight_ok.sum()) == 0:
        fail("column 'mult' has no usable values in the person file")

    pas = per["pas"].astype(str).str.strip()
    sas = per["sas"].astype(str).str.strip()
    emp_pas = pas.isin(EMPLOYED)
    emp_sas = sas.isin(EMPLOYED)

    # Employment basis: the principal activity when it employs the person,
    # otherwise the subsidiary activity. This decides the earnings concept.
    basis = pas.where(emp_pas, sas)
    basis = basis.where(emp_pas | emp_sas)

    # Occupation: the principal code when present. Fall back to the subsidiary
    # code only when the principal code is missing AND the person is employed
    # through the subsidiary activity. This strict reading of section 2.3 and
    # section 4.1 stops a stray subsidiary code (from an activity that does
    # not employ the person) from placing a worker in a wrong cell.
    ocu_pas = per["ocu_pas"].replace("", np.nan)
    ocu_sas = per["ocu_sas"].replace("", np.nan)
    occupation = ocu_pas.where(ocu_pas.notna(), ocu_sas.where(emp_sas & ocu_pas.isna(), np.nan))

    sex = per["sex"].astype(str).str.strip()
    sec = per["sec"].astype(str).str.strip()

    df = pd.DataFrame(
        {
            "weight": mult / MULT_DIVISOR,
            "basis": basis,
            "occupation": occupation,
            "female": sex == "2",  # 2 = female in PLFS
            "male": sex == "1",  # 1 = male in PLFS
            "rural": sec == "1",  # 1 = rural in PLFS
            "urban": sec == "2",  # 2 = urban in PLFS
        }
    )

    age = numeric(per["age"])
    df["age"] = age
    age_ok = age >= 15

    # ---- Monthly earnings, harmonised per section 2.6 ---------------------
    # Regular: ern_reg as reported. Self employed: ern_self as reported.
    # Casual: sum the 14 daily fields ern11..ern27 for a weekly total, then
    # multiply by 30/7. The daily fields are measured; no 26-day convention
    # is applied.
    casual_cols = [c for c in CASUAL_COLUMNS if c in per.columns]
    missing_casual = [c for c in CASUAL_COLUMNS if c not in per.columns]
    if missing_casual:
        fail(f"person file lacks casual earnings columns: {sorted(missing_casual)}")
    casual_weekly = per[casual_cols].apply(numeric).sum(axis=1, min_count=1)
    casual_monthly = casual_weekly * (30.0 / 7.0)

    # Unpaid helpers (status 21) are excluded from the earnings figure but
    # stay in the employment count (section 2.6).
    earnings = np.select(
        [
            basis.isin(REGULAR),
            basis.isin(SELF_EMPLOYED - {"21"}),
            basis.isin(CASUAL),
        ],
        [
            numeric(per["ern_reg"]).to_numpy(),
            numeric(per["ern_self"]).to_numpy(),
            casual_monthly.to_numpy(),
        ],
        default=np.nan,
    )
    df["monthly_earnings"] = earnings
    df["has_earnings"] = ~np.isnan(earnings)

    # Status category of the employment basis, for status_mix and informality.
    df["basis_cat"] = np.select(
        [basis.isin(SELF_EMPLOYED), basis.isin(REGULAR), basis.isin(CASUAL)],
        ["self employed", "regular", "casual"],
        default=None,
    )

    # Education: map the zero padded code to its ordinal rank. Codes outside
    # the map (none expected per section 4.1) get NaN and stay out of the
    # median, which is the least distorting reading.
    gedu = per["gedu_lvl"].astype(str).str.strip()
    df["gedu_rank"] = gedu.map(GEDU_RANK).astype(float)

    # Filter last: every derived array above is row-aligned with the source
    # frame, so dropping rows here cannot misalign any of them.
    df = df[weight_ok & age_ok & (emp_pas | emp_sas) & df["occupation"].notna()]

    return df


def cell_stats(g: pd.DataFrame) -> dict:
    """All weighted measures for one occupation cell in one cut."""
    w = g["weight"].to_numpy()
    n = len(g)
    total = float(w.sum())

    basis_cat = g["basis_cat"].to_numpy()
    self_employed_w = float(w[basis_cat == "self employed"].sum())
    regular_w = float(w[basis_cat == "regular"].sum())
    casual_w = float(w[basis_cat == "casual"].sum())

    female_w = float(w[g["female"].to_numpy()].sum())
    rural_w = float(w[g["rural"].to_numpy()].sum())

    has_earnings = g["has_earnings"].to_numpy()
    earnings_w = w[has_earnings]
    earnings_median = weighted_median(
        g["monthly_earnings"].to_numpy()[has_earnings], earnings_w
    )

    rank = g["gedu_rank"].to_numpy()
    rank_ok = ~np.isnan(rank)
    rank_median = weighted_median(rank[rank_ok], w[rank_ok])

    status_mix = {
        "self_employed": round(self_employed_w / total, 4) if total > 0 else 0.0,
        "regular": round(regular_w / total, 4) if total > 0 else 0.0,
        "casual": round(casual_w / total, 4) if total > 0 else 0.0,
    }

    return {
        "workers_w": total,
        "sample_n": n,
        "female_share": female_w / total if total > 0 else np.nan,
        "rural_share": rural_w / total if total > 0 else np.nan,
        "status_mix_json": json.dumps(status_mix, separators=(",", ":")),
        "informality_share": (self_employed_w + casual_w) / total if total > 0 else np.nan,
        "earnings_median": earnings_median,
        # Coverage = weighted share of the cell's workers with a usable
        # earnings value. Unpaid helpers report none, so they lower coverage
        # while staying in the count (section 2.6).
        "earnings_coverage": earnings_w.sum() / total if total > 0 else np.nan,
        "education_rank_median": rank_median,
    }


def tabulate_cut(df: pd.DataFrame, sector: str, sex: str, age: str) -> pd.DataFrame:
    # Missing sex is neither female nor male, and missing sec is neither rural
    # nor urban, so such records fall only in the 'all' cuts. Sex "3"
    # (transgender) belongs to 'all' and to neither male nor female. The
    # variables are near-complete per section 4.1.
    sector_mask = np.asarray({
        "all": np.ones(len(df), dtype=bool),
        "rural": df["rural"],
        "urban": df["urban"],
    }[sector])
    sex_mask = np.asarray({
        "all": np.ones(len(df), dtype=bool),
        "female": df["female"],
        "male": df["male"],
    }[sex])
    if age == "all":
        age_mask = np.ones(len(df), dtype=bool)
    else:
        lo, hi = AGE_BANDS[age]
        age_mask = np.asarray(df["age"].between(lo, hi))
    sub = df[sector_mask & sex_mask & age_mask]

    rows = []
    for code, g in sub.groupby("occupation", sort=True):
        stats = cell_stats(g)
        stats["nco_code"] = str(code).zfill(3)
        stats["cut_sector"] = sector
        stats["cut_sex"] = sex
        stats["cut_age"] = age
        rows.append(stats)
    return pd.DataFrame(rows, columns=CELL_STAT_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tabulate PLFS 2025 into NCO 3-digit cells with all sector/sex/age cuts."
    )
    parser.add_argument(
        "--person-file",
        default="data/plfs/plfs_2025_per.parquet",
        help="person-level parquet from 02_parse_plfs.py",
    )
    parser.add_argument(
        "--household-file",
        default="data/plfs/plfs_2025_hh.parquet",
        help="household-level parquet from 02_parse_plfs.py",
    )
    parser.add_argument("--output", default="data/occupations_in.csv")
    parser.add_argument("--meta", default="data/tabulate_meta.json")
    parser.add_argument(
        "--total-workers",
        type=float,
        default=DEFAULT_TOTAL_WORKERS,
        help=f"target total workers for rescaling. The default ({DEFAULT_TOTAL_WORKERS:,.0f}) "
        "applies the scaling factor 1.1898, which is the official CY 2025 WPR of 57.4 percent "
        "applied to the Technical Group 2019 projected 15-plus population of 1,075 million, "
        "giving 617 million workers (61.7 crore). It reproduces the settled decision in "
        "SPEC.md section 2.10.",
    )
    args = parser.parse_args()

    per_path = Path(args.person_file)
    hh_path = Path(args.household_file)

    per = load_parquet(per_path)
    hh = load_parquet(hh_path)

    missing_cols = sorted(PERSON_REQUIRED - set(per.columns))
    if missing_cols:
        fail(f"person file is missing columns {missing_cols}; check 02_parse_plfs.py output")

    print("survey period: January 2025 to December 2025 (PLFS CY 2025)")
    print(f"person file: {per_path} ({len(per):,} records)")
    print(f"household file: {hh_path} ({len(hh):,} records)")
    print(f"multiplier divisor: /{MULT_DIVISOR} (PLFS stores the multiplier x{MULT_DIVISOR})")

    workers = prepare_workers(per)
    if workers.empty:
        fail("no workers found; check the pas/sas/age columns from 02_parse_plfs.py")
    print(f"workers (age 15+, ps+ss): {len(workers):,} records")

    # Scaling (section 2.10): one constant factor applied to every cell, so
    # shares inside each cut are preserved. The national target applies to
    # the all/all cut; the same factor then scales every other cell.
    weighted_total = float(workers["weight"].sum())
    if args.total_workers <= 0:
        fail("--total-workers must be positive")
    if weighted_total <= 0:
        fail("weighted worker total is zero; cannot rescale")
    factor = args.total_workers / weighted_total
    print(f"national worker estimate (raw weighted): {weighted_total:,.0f}")
    print(f"target workers: {args.total_workers:,.0f}")
    print(f"scaling factor: {factor:.6f}")

    frame = pd.concat(
        [
            tabulate_cut(workers, s, x, a)
            for s in CUT_SECTORS for x in CUT_SEXES for a in CUT_AGES
        ],
        ignore_index=True,
    )

    frame["workers"] = (frame["workers_w"] * factor).round().astype(int)
    for col in ("female_share", "rural_share", "informality_share", "earnings_coverage"):
        frame[col] = frame[col].round(4)

    # Suppression (section 2.13): thin cells keep employment but lose
    # earnings and education below 20 records; below 50 they are flagged.
    frame["low_confidence"] = frame["sample_n"] < 50
    thin = frame["sample_n"] < 20
    frame.loc[thin, ["earnings_median", "education_rank_median"]] = np.nan

    frame["median_monthly_earnings_inr"] = frame["earnings_median"].apply(
        lambda v: round(v) if not np.isnan(v) else None
    )
    frame["education_median"] = frame["education_rank_median"].apply(
        lambda v: RANK_TO_LABEL[int(v)] if not np.isnan(v) else None
    )

    out = frame.rename(columns={"status_mix_json": "status_mix"})[OUT_COLUMNS]
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"wrote {out_path} ({len(out):,} rows)")

    meta = {
        "survey_period": "January 2025 to December 2025 (PLFS CY 2025)",
        "release_id": "DDI-IND-NSO-PLFS-Jan2025-Dec2025",
        "scaling_factor": factor,
        "total_workers_target": args.total_workers,
        "multiplier_divisor": MULT_DIVISOR,
        "row_counts": {
            "person_records": len(per),
            "household_records": len(hh),
            "worker_records_used": len(workers),
            "output_rows": len(out),
        },
    }
    meta_path = Path(args.meta)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {meta_path}")


if __name__ == "__main__":
    main()