"""Extract NCO 2015 minor group descriptions from the official Volume I PDF.

Run from the repository root:
    python scripts/04_nco_descriptions.py

The PDF is a two column layout. Text extraction flattens it into narrow lines,
so nearly every title wraps. The structure is:

    Group 431                                  <- code alone on its line
    Numerical Clerks                           <- title, may wrap
                                               <- blank
    Numerical Clerks obtain, compile and       <- definition, wraps
    ... incidental to business matters.
                                               <- blank
    Occupations in this Group are classified
    into the following Families:
                                               <- blank
    4311 Accounting and Bookkeeping            <- family list, wraps
    Clerks
    ...
    Family 4311                                <- code alone on its line
    Accounting and Bookkeeping Clerks          <- title, may wrap

So a heading never carries its own title. The title is the following block of
non blank lines. That is the rule this parser applies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PDF_PATH = Path("data/nco/nco-2015-vol1.pdf")
RAW_PATH = Path("data/nco/nco_raw_text.txt")
OUT_PATH = Path("data/nco/nco_descriptions.json")

# A heading line holds only the keyword and the code.
GROUP_RE = re.compile(r"^Group\s+(\d{3})\s*$")
FAMILY_RE = re.compile(r"^Family\s+(\d{4})\s*$")

# An individual occupation appears in two places, in two shapes.
# In the code list the title sits on the same line, with an optional trailing
# NCO 2004 code:      4311.0200 Bank Clerk 4121.30
# In the description section the code sits alone and the title follows:
#                     4311.0200
#                     Bank Clerk
OCCUPATION_RE = re.compile(r"^(\d{4}\.\d{4})\s+(.*?)\s*(?:\d{4}\.\d{2})?\s*$")
BARE_CODE_RE = re.compile(r"^(\d{4}\.\d{4})\s*$")

# Page furniture and cross reference noise to drop before parsing.
NOISE_RE = re.compile(
    r"^(NATIONAL CLASSIFICATION OF OCCUPATIONS|VOLUME\s|Qualification Pack|QP NOS|"
    r"NSQF|ISCO 08|NCO 2015\s+NCO 2004|\d+\s*$)",
    re.IGNORECASE,
)

FAMILY_LIST_MARKER = "Occupations in this Group are classified"

MAX_TITLE = 90
MAX_DEFINITION = 1200
MAX_OCCUPATION_TITLES = 60


def extract_text(pdf_path: Path, raw_path: Path, refresh: bool) -> str:
    """Extract the PDF once and cache it. Extraction of 1519 pages is slow."""
    if raw_path.is_file() and not refresh:
        return raw_path.read_text(encoding="utf-8", errors="replace")
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is required. Run: uv sync")
    if not pdf_path.is_file():
        sys.exit(f"PDF not found at {pdf_path}. Download NCO 2015 Volume I first.")
    reader = PdfReader(str(pdf_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(text, encoding="utf-8")
    print(f"extracted {len(reader.pages)} pages to {raw_path}")
    return text


def clean_lines(text: str) -> list[str]:
    out = []
    for line in text.split("\n"):
        line = line.replace(" ", " ").rstrip()
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if NOISE_RE.match(stripped):
            continue
        out.append(stripped)
    return out


def take_block(lines: list[str], start: int) -> tuple[str, int]:
    """Join consecutive non blank lines from `start`. Return the text and the
    index of the first line after the block."""
    parts = []
    i = start
    while i < len(lines) and lines[i]:
        parts.append(lines[i])
        i += 1
    return " ".join(parts).strip(), i


def skip_blanks(lines: list[str], i: int) -> int:
    while i < len(lines) and not lines[i]:
        i += 1
    return i


def tidy(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # The extractor loses the blank line between a heading title and its
    # definition on some pages, so the block runs on. The definition always
    # restates the title, so cut where the opening words appear a second time.
    # Case insensitive: the definition often restates the title in lower case,
    # for example "Legislators and Senior Officials" then "Legislators and
    # senior officials determine ...". Try the longest head first, because a
    # longer head is more specific and less likely to match by accident.
    lower = text.lower()
    for head_len in range(20, 7, -2):
        if len(text) <= head_len:
            continue
        repeat = lower.find(lower[:head_len], 1)
        if repeat > 0:
            text = text[:repeat].strip()
            break
    if len(text) > limit:
        text = text[:limit].rstrip()
    return text.strip(" .,;:-")


def add_occupation(parent: dict, title: str) -> None:
    """Record one occupation title under its minor group, de-duplicated."""
    title = tidy(title, 120)
    if not title:
        return
    if len(parent["occupation_titles"]) >= MAX_OCCUPATION_TITLES:
        return
    if title not in parent["occupation_titles"]:
        parent["occupation_titles"].append(title)


def parse(lines: list[str]) -> dict:
    groups: dict[str, dict] = {}
    current: dict | None = None

    i = 0
    while i < len(lines):
        line = lines[i]

        group_match = GROUP_RE.match(line)
        if group_match:
            code = group_match.group(1)
            j = skip_blanks(lines, i + 1)
            title, j = take_block(lines, j)
            j = skip_blanks(lines, j)

            # The definition is the next block, unless the family list starts.
            definition = ""
            if j < len(lines) and not lines[j].startswith(FAMILY_LIST_MARKER):
                block, after = take_block(lines, j)
                if not block.startswith(FAMILY_LIST_MARKER) and not FAMILY_RE.match(block):
                    definition = block
                    j = after

            current = groups.setdefault(
                code,
                {
                    "nco_code": code,
                    "title": tidy(title, MAX_TITLE),
                    "definition": tidy(definition, MAX_DEFINITION) or None,
                    "division": code[0],
                    "subdivision": code[:2],
                    "unit_groups": [],
                    "occupation_titles": [],
                },
            )
            i = j
            continue

        family_match = FAMILY_RE.match(line)
        if family_match:
            code = family_match.group(1)
            j = skip_blanks(lines, i + 1)
            title, j = take_block(lines, j)
            parent = groups.get(code[:3])
            if parent is not None:
                known = {u["code"] for u in parent["unit_groups"]}
                if code not in known:
                    parent["unit_groups"].append({"code": code, "title": tidy(title, MAX_TITLE)})
            i = j
            continue

        bare_match = BARE_CODE_RE.match(line)
        if bare_match:
            # The code sits alone. Its title is the next non blank line only.
            code = bare_match.group(1)
            j = skip_blanks(lines, i + 1)
            title = lines[j] if j < len(lines) else ""
            parent = groups.get(code[:3])
            if parent is not None and title and not BARE_CODE_RE.match(title):
                add_occupation(parent, title)
            i = j + 1
            continue

        occupation_match = OCCUPATION_RE.match(line)
        if occupation_match and current is not None:
            code, title = occupation_match.groups()
            if parent is not None and title:
                add_occupation(parent, title)
            i += 1
            continue

        i += 1

    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse NCO 2015 Volume I into JSON.")
    parser.add_argument("--pdf", default=str(PDF_PATH))
    parser.add_argument("--raw", default=str(RAW_PATH))
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--refresh", action="store_true", help="re-extract the PDF")
    args = parser.parse_args()

    text = extract_text(Path(args.pdf), Path(args.raw), args.refresh)
    lines = clean_lines(text)
    groups = parse(lines)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(groups, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    unit_groups = sum(len(g["unit_groups"]) for g in groups.values())
    titles = sum(len(g["occupation_titles"]) for g in groups.values())
    longest_title = max((len(g["title"]) for g in groups.values()), default=0)
    with_definition = sum(1 for g in groups.values() if g["definition"])

    print(f"lines parsed:      {len(lines)}")
    print(f"groups found:      {len(groups)}")
    print(f"unit groups:       {unit_groups}")
    print(f"occupation titles: {titles}")
    print(f"with definition:   {with_definition}")
    print(f"longest title:     {longest_title} characters")
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

    if not 100 <= len(groups) <= 160:
        print(
            f"WARNING: expected roughly 130 minor groups, found {len(groups)}. "
            "NCO 2015 aligns to ISCO 08."
        )
    if longest_title > MAX_TITLE:
        print(f"WARNING: a title exceeds {MAX_TITLE} characters.")


if __name__ == "__main__":
    main()
