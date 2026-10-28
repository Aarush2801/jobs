"""Convert the PLFS 2025 JSON download into the CSV files 02_parse_plfs.py reads.

MoSPI also ships the release as Data_in_JSON.zip, one JSON array per file. This
streams each array straight out of the zip, so the 2 GB person file is never
unpacked or held in memory.

Run from the repository root:
    python scripts/00_json_to_csv.py ~/Downloads/Data_in_JSON.zip
"""

import argparse
import csv
import io
import json
import os
import zipfile

DEFAULT_OUT_DIR = os.path.join("data", "plfs", "raw")
MATCHES = ("chhv12025", "cperv12025")
CHUNK = 1 << 20


def iter_records(stream):
    # Walk a top-level JSON array one object at a time.
    decoder = json.JSONDecoder()
    buf = ""
    pos = 0
    started = False
    while True:
        chunk = stream.read(CHUNK)
        buf = buf[pos:] + chunk
        pos = 0
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n,":
                pos += 1
            if not started:
                if pos < len(buf) and buf[pos] == "[":
                    started = True
                    pos += 1
                    continue
                if pos < len(buf):
                    raise ValueError("Expected the file to start with a JSON array.")
            if pos < len(buf) and buf[pos] == "]":
                return
            try:
                record, end = decoder.raw_decode(buf, pos)
            except json.JSONDecodeError:
                if not chunk:
                    raise
                break
            yield record
            pos = end
        if not chunk:
            return


def cell(value):
    # Match how the CSV package writes values: integral floats lose their ".0",
    # nulls become empty, and code strings keep their leading zeros.
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return value


def convert(archive, member, out_path):
    rows = 0
    with archive.open(member) as raw, open(out_path, "w", newline="", encoding="utf-8") as out:
        stream = io.TextIOWrapper(raw, encoding="utf-8-sig")
        writer = None
        columns = None
        for record in iter_records(stream):
            if writer is None:
                columns = list(record)
                writer = csv.writer(out)
                writer.writerow(columns)
            elif list(record) != columns:
                extra = set(record) - set(columns)
                if extra:
                    raise ValueError(f"Row {rows + 1} has unexpected fields: {sorted(extra)}")
            writer.writerow([cell(record.get(name)) for name in columns])
            rows += 1
            if rows % 200000 == 0:
                print(f"  {rows} rows")
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Convert the PLFS 2025 JSON zip into CSV files."
    )
    parser.add_argument("zip_path", help="Path to Data_in_JSON.zip.")
    parser.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Directory for the CSV output (default: %(default)s).",
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    with zipfile.ZipFile(os.path.expanduser(args.zip_path)) as archive:
        for match in MATCHES:
            members = [
                name for name in archive.namelist()
                if match in name.lower() and name.lower().endswith(".json")
            ]
            if len(members) != 1:
                raise FileNotFoundError(f"Expected one JSON file matching {match!r}, found {members}")
            out_path = os.path.join(args.out_dir, f"{match}.csv")
            print(f"Converting {members[0]} -> {out_path}")
            rows = convert(archive, members[0], out_path)
            print(f"  Wrote {rows} rows")
    print("Done.")


if __name__ == "__main__":
    main()
