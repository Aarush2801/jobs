"""Parse the PLFS 2025 household and person CSV files into Parquet.

Run from the repository root:
    python scripts/02_parse_plfs.py
"""

import argparse
import os

import pandas as pd

DEFAULT_RAW_DIR = os.path.join("data", "plfs", "raw")
DEFAULT_OUT_DIR = os.path.join("data", "plfs")

EXPECTED_FILES = (
    {
        "kind": "household",
        "match": "chhv12025",
        "records": 270472,
        "out_name": "plfs_2025_hh.parquet",
        "required": ("mult", "nsc", "zst", "panel", "sec", "st"),
    },
    {
        "kind": "person",
        "match": "cperv12025",
        "records": 1148634,
        "out_name": "plfs_2025_per.parquet",
        "required": (
            "ocu_pas", "ocu_sas", "pas", "sas", "gedu_lvl", "sex", "age",
            "sec", "st", "mult", "ern_reg", "ern_self", "job_pas",
            "leave_pas", "ssec_pas",
            "ern11", "ern12", "ern13", "ern14", "ern15", "ern16", "ern17",
            "ern21", "ern22", "ern23", "ern24", "ern25", "ern26", "ern27",
        ),
    },
)

# PLFS code columns are zero padded, for example gedu_lvl "01" and pas "11".
# Pandas reads them as integers and drops the leading zero, which then breaks
# every downstream lookup keyed on the code string. So force them to string.
STRING_COLUMNS = (
    "ocu_pas", "ocu_sas",
    "pas", "sas",
    "gedu_lvl", "tedu_lvl",
    "ind_pas", "ind_sas",
    "job_pas", "leave_pas", "ssec_pas",
    "job_sas", "leave_sas", "ssec_sas",
    "sec", "st", "dc", "nsc", "panel", "sex",
)

# The user may also unpack the STATA package into the same directory. Only the
# CSV package is supported input, so ignore every other extension.
DATA_SUFFIXES = (".csv",)


def find_file(raw_dir, match):
    candidates = []
    if os.path.isdir(raw_dir):
        for root, _dirs, names in os.walk(raw_dir):
            for name in names:
                if match.lower() not in name.lower():
                    continue
                if not name.lower().endswith(DATA_SUFFIXES):
                    continue
                candidates.append(os.path.join(root, name))
    if not candidates:
        raise FileNotFoundError(
            f"Required file matching {match!r} not found under {raw_dir}. "
            f"Expected {match} data from the PLFS 2025 annual release."
        )
    if len(candidates) > 1:
        raise FileNotFoundError(
            f"More than one file matches {match!r} under {raw_dir}: "
            f"{', '.join(candidates)}"
        )
    return candidates[0]


def read_csv(path):
    header = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
    columns = {str(column).strip().lower() for column in header.columns}
    dtype = {column: str for column in STRING_COLUMNS if column in columns}
    return pd.read_csv(path, dtype=dtype, encoding="utf-8-sig")


def lowercase_columns(frame):
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    return frame


def process(entry, args):
    path = find_file(args.raw_dir, entry["match"])
    print(f"Reading {entry['kind']} file: {path}")
    try:
        frame = read_csv(path)
    except Exception as exc:  # noqa: BLE001 - wrap any reader failure with context
        raise RuntimeError(
            f"Could not read the {entry['kind']} file {path}. "
            f"It may be corrupt or not a CSV. Original error: {exc}"
        )
    frame = lowercase_columns(frame)

    rows, cols = frame.shape
    print(f"  {entry['kind']} file: {rows} rows, {cols} columns")
    if rows != entry["records"]:
        print(
            f"  WARNING: expected {entry['records']} rows for the {entry['kind']} file, "
            f"found {rows}."
        )

    missing = [name for name in entry["required"] if name not in frame.columns]
    if missing:
        print(f"  WARNING: required variables not found: {', '.join(missing)}")
    else:
        print("  All required variables present.")

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, entry["out_name"])
    try:
        frame.to_parquet(out_path, index=False)
    except Exception as exc:  # noqa: BLE001 - wrap any writer failure with context
        raise RuntimeError(
            f"Could not write {out_path}. Original error: {exc}"
        )
    print(f"  Wrote {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Parse the PLFS 2025 CSV files into Parquet."
    )
    parser.add_argument(
        "--raw-dir",
        default=DEFAULT_RAW_DIR,
        help="Directory with the downloaded PLFS files (default: %(default)s).",
    )
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Directory for the Parquet output (default: %(default)s).",
    )
    args = parser.parse_args()

    for entry in EXPECTED_FILES:
        process(entry, args)
    print("Done.")


if __name__ == "__main__":
    main()