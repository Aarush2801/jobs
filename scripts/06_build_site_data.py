"""Merge PLFS tabulation, NCO descriptions and AI scores into site/data.json.

Reads data/occupations_in.csv, data/nco/nco_descriptions.json and
data/scores_in.json. Writes site/data.json with the exact top level shape
{"meta": {...}, "groups": {...}, "occupations": [...]}.

"groups" holds what is the same in every cut (title, division, AI score and
rationale) once per NCO code. "occupations" holds one row per code and cut,
and the page joins the two on nco_code.
"""

import argparse
import csv
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTIONS_PATH = ROOT / "data" / "nco" / "nco_descriptions.json"
OCCUPATIONS_IN_PATH = ROOT / "data" / "occupations_in.csv"
SCORES_IN_PATH = ROOT / "data" / "scores_in.json"
TABULATE_META_PATH = ROOT / "data" / "tabulate_meta.json"
SITE_DATA_PATH = ROOT / "site" / "data.json"

SURVEY_PERIOD = "January to December 2025"
PLFS_RELEASE = "DDI-IND-NSO-PLFS-Jan2025-Dec2025"
META_KEY = "_meta"
SECTOR_ORDER = {"all": 0, "rural": 1, "urban": 2}
SEX_ORDER = {"all": 0, "female": 1, "male": 2}
AGE_ORDER = {"all": 0, "15-29": 1, "30-44": 2, "45-59": 3, "60+": 4}
REQUIRED_COLUMNS = [
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

NA_WORDS = {"nan", "null", "none", "na", ""}


def fail(message: str) -> None:
    sys.exit(f"06_build_site_data.py: {message}")


def warn(label: str, codes: set[str]) -> None:
    if not codes:
        return
    listing = ", ".join(sorted(codes))
    print(f"WARNING: {label}: {listing}", file=sys.stderr)


def normalize_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)\.0+", text)
    if match:
        text = match.group(1)
    return text


def load_descriptions() -> dict[str, dict[str, Any]]:
    if not DESCRIPTIONS_PATH.exists():
        fail("Missing data/nco/nco_descriptions.json. Run scripts/04_nco_descriptions.py first.")
    try:
        payload = json.loads(DESCRIPTIONS_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        fail(f"Cannot read data/nco/nco_descriptions.json: {exc}")
    if not isinstance(payload, dict):
        fail("data/nco/nco_descriptions.json must hold a JSON object keyed by nco_code.")
    descriptions: dict[str, dict[str, Any]] = {}
    for code, entry in payload.items():
        normalized = normalize_code(code)
        if normalized is None or not isinstance(entry, dict):
            continue
        descriptions[normalized] = entry
    return descriptions


def load_scores() -> dict[str, dict[str, Any]]:
    if not SCORES_IN_PATH.exists():
        fail("Missing data/scores_in.json. Run scripts/05_score.py first.")
    try:
        payload = json.loads(SCORES_IN_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        fail(f"Cannot read data/scores_in.json: {exc}")
    if not isinstance(payload, dict):
        fail("data/scores_in.json must hold a JSON object keyed by nco_code.")
    code_pattern = re.compile(r"^\d{3}$")
    scores: dict[str, dict[str, Any]] = {}
    for code, entry in payload.items():
        normalized = normalize_code(code)
        if (
            normalized is None
            or not isinstance(entry, dict)
            or not code_pattern.fullmatch(normalized)
        ):
            continue
        scores[normalized] = entry
    return scores


def load_scoring_model() -> str | None:
    if not SCORES_IN_PATH.exists():
        return None
    try:
        payload = json.loads(SCORES_IN_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None
    meta = payload.get(META_KEY)
    if isinstance(meta, dict) and meta.get("model"):
        return str(meta["model"])
    warn("data/scores_in.json has no scoring model in _meta", {"_meta"})
    return None


def load_scaling_factor() -> float | None:
    if not TABULATE_META_PATH.exists():
        return None
    try:
        payload = json.loads(TABULATE_META_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"WARNING: cannot read data/tabulate_meta.json ({exc}); "
            "scaling_factor is null",
            file=sys.stderr,
        )
        return None
    if not isinstance(payload, dict):
        print(
            "WARNING: data/tabulate_meta.json must hold a JSON object; "
            "scaling_factor is null",
            file=sys.stderr,
        )
        return None
    value = payload.get("scaling_factor")
    if value is None:
        print(
            "WARNING: data/tabulate_meta.json has no scaling_factor; "
            "scaling_factor is null",
            file=sys.stderr,
        )
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        print(
            f"WARNING: scaling_factor {value!r} is not a number; "
            "scaling_factor is null",
            file=sys.stderr,
        )
        return None


def to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if math.isnan(value) else float(value)
    text = str(value).strip()
    if text.lower() in NA_WORDS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def to_int(value: Any) -> int | None:
    number = to_number(value)
    if number is None:
        return None
    return round(number)


def to_bool(value: Any) -> bool | None:
    text = to_str(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    return None


def parse_status_mix(value: Any) -> dict[str, float | None] | None:
    text = to_str(value)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print(f"WARNING: unparseable status_mix {text!r}; setting null", file=sys.stderr)
        return None
    if not isinstance(payload, dict):
        return None
    cleaned: dict[str, float | None] = {}
    for key, item in payload.items():
        key_text = str(key).strip()
        cleaned[key_text or str(key)] = to_number(item)
    return cleaned


def build_group(
    code: str,
    description: dict[str, Any],
    score: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "title": to_str(description.get("title")),
        "division": to_str(description.get("division")),
        "subdivision": to_str(description.get("subdivision")),
        # NCO 2015 aligns to ISCO 08 at the 3-digit level, so the code carries over.
        "isco_code": code,
        "exposure_in": score.get("exposure") if score else None,
        "exposure_in_rationale": to_str(score.get("rationale")) if score else None,
    }


def build_row(code: str, csv_row: dict[str, str]) -> dict[str, Any]:
    return {
        "nco_code": code,
        "cut_sector": to_str(csv_row.get("cut_sector")),
        "cut_sex": to_str(csv_row.get("cut_sex")),
        "cut_age": to_str(csv_row.get("cut_age")),
        "workers": to_int(csv_row.get("workers")),
        "sample_n": to_int(csv_row.get("sample_n")),
        "female_share": to_number(csv_row.get("female_share")),
        "rural_share": to_number(csv_row.get("rural_share")),
        "status_mix": parse_status_mix(csv_row.get("status_mix")),
        "informality_share": to_number(csv_row.get("informality_share")),
        "median_monthly_earnings_inr": to_int(csv_row.get("median_monthly_earnings_inr")),
        "earnings_coverage": to_number(csv_row.get("earnings_coverage")),
        "education_median": to_str(csv_row.get("education_median")),
        "low_confidence": to_bool(csv_row.get("low_confidence")),
    }


def cut_key(sector: str, sex: str, age: str) -> tuple[int, int, int]:
    return (SECTOR_ORDER.get(sector, 9), SEX_ORDER.get(sex, 9), AGE_ORDER.get(age, 9))


def make_cut_list(cuts: set[tuple[str, str, str]]) -> list[dict[str, str]]:
    ordered = sorted(cuts, key=lambda cut: cut_key(*cut))
    return [
        {"cut_sector": sector, "cut_sex": sex, "cut_age": age}
        for sector, sex, age in ordered
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge PLFS tabulation, NCO descriptions and AI scores into site/data.json."
    )
    parser.add_argument(
        "--output",
        default=str(SITE_DATA_PATH),
        help=f"Output path (default: {SITE_DATA_PATH})",
    )
    return parser.parse_args()


def main(arguments: argparse.Namespace) -> None:
    descriptions = load_descriptions()
    scores = load_scores()
    scoring_model = load_scoring_model()
    scaling_factor = load_scaling_factor()

    with open(OCCUPATIONS_IN_PATH, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_columns = [
            column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])
        ]
        if missing_columns:
            fail(
                "Missing columns in data/occupations_in.csv: " + ", ".join(missing_columns) +
                ". Run scripts/03_tabulate.py first."
            )
        rows: list[dict[str, Any]] = []
        groups: dict[str, dict[str, Any]] = {}
        csv_codes: set[str] = set()
        cuts: set[tuple[str, str, str]] = set()
        for csv_row in reader:
            code = normalize_code(csv_row.get("nco_code"))
            if code is None:
                continue
            csv_codes.add(code)
            sector = to_str(csv_row.get("cut_sector"))
            sex = to_str(csv_row.get("cut_sex"))
            age = to_str(csv_row.get("cut_age"))
            cuts.add((sector or "", sex or "", age or ""))
            description = descriptions.get(code)
            if description is None:
                continue
            if code not in groups:
                groups[code] = build_group(code, description, scores.get(code))
            rows.append(build_row(code, csv_row))

    description_codes = set(descriptions)
    score_codes = set(scores)
    warn(
        "groups in nco_descriptions.json with no row in occupations_in.csv",
        description_codes - csv_codes,
    )
    warn(
        "groups in occupations_in.csv with no entry in nco_descriptions.json",
        csv_codes - description_codes,
    )
    warn(
        "groups with a score but no entry in nco_descriptions.json or occupations_in.csv",
        score_codes - (description_codes | csv_codes),
    )
    warn(
        "groups with no AI score (exposure_in is null)",
        (description_codes & csv_codes) - score_codes,
    )

    rows.sort(key=lambda row: (row["nco_code"], *cut_key(
        row["cut_sector"] or "", row["cut_sex"] or "", row["cut_age"] or "")))

    meta = {
        "survey_period": SURVEY_PERIOD,
        "plfs_release": PLFS_RELEASE,
        "scaling_factor": scaling_factor,
        "scoring_model": scoring_model,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "occupation_count": len(groups),
        "cut_list": make_cut_list(cuts),
    }
    payload = {"meta": meta, "groups": dict(sorted(groups.items())), "occupations": rows}

    output_path = Path(arguments.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    byte_size = os.path.getsize(output_path)
    print(
        f"wrote {output_path}: {len(rows)} rows, "
        f"{meta['occupation_count']} occupations, {byte_size} bytes"
    )


if __name__ == "__main__":
    main(parse_args())