"""Check that the PLFS 2025 download files are present.

Run from the repository root:
    python scripts/01_check_inputs.py
"""

import argparse
import os
import sys

DEFAULT_RAW_DIR = os.path.join("data", "plfs", "raw")
CATALOG_URL = "https://microdata.gov.in/NADA/index.php/catalog/284"

EXPECTED_FILES = (
    {"kind": "household", "match": "chhv12025", "records": 270472},
    {"kind": "person", "match": "cperv12025", "records": 1148634},
)


def detect_kind(file_name):
    name = file_name.lower()
    if "chhv12025" in name:
        return "household"
    if "cperv12025" in name:
        return "person"
    if "layout" in name:
        return "layout"
    return "unknown"


def scan(raw_dir):
    found = []
    if os.path.isdir(raw_dir):
        for root, _dirs, names in os.walk(raw_dir):
            for name in sorted(names):
                path = os.path.join(root, name)
                size_mb = os.path.getsize(path) / (1024.0 * 1024.0)
                found.append({"path": path, "size_mb": size_mb, "kind": detect_kind(name)})
    return found


def main():
    parser = argparse.ArgumentParser(
        description="Check that the PLFS 2025 download files are present."
    )
    parser.add_argument(
        "--raw-dir",
        default=DEFAULT_RAW_DIR,
        help="Directory with the downloaded PLFS files (default: %(default)s).",
    )
    args = parser.parse_args()

    files = scan(args.raw_dir)

    print(f"Files found under {args.raw_dir}:")
    if files:
        for entry in files:
            print(f"{entry['path']:<68} {entry['size_mb']:9.2f} MB  {entry['kind']}")
    else:
        print("  (none)")

    print()
    print("Expected record counts:")
    for entry in EXPECTED_FILES:
        print(f"  {entry['kind']:<10} {entry['match']}: {entry['records']} records")

    missing = [e for e in EXPECTED_FILES if not any(f["kind"] == e["kind"] for f in files)]
    if missing:
        kinds = ", ".join(e["kind"] for e in missing)
        found_names = "none" if not files else ", ".join(f["path"] for f in files)
        print()
        print(f"ERROR: missing required file(s): {kinds}")
        print("Expected a file matching chhv12025 and a file matching cperv12025")
        print(f"under {args.raw_dir}. Found: {found_names}.")
        print()
        print("Download the single PLFS 2025 archive from the catalog page:")
        print(f"  {CATALOG_URL}")
        print("A registered account on microdata.gov.in may be required.")
        print(f"Then unzip the archive into {args.raw_dir}.")
        sys.exit(1)

    print()
    print("All required files are present.")


if __name__ == "__main__":
    main()