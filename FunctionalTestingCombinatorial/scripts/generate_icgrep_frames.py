#!/usr/bin/env python3
"""
Generate a combinatorial frame CSV for icgrep.

Applies constraints in models/icgrep_constraints.txt:
  - count=1 => line_numbers=0
  - file_type=missing_path => line_numbers=0
"""

from __future__ import annotations

import argparse
import csv
from itertools import product
from pathlib import Path


PATTERN_TYPES = (
    "literal",
    "char_class",
    "negated_class",
    "anchor_start",
    "anchor_end",
    "alternation",
    "repetition",
    "unicode_property",
    "empty",
    "invalid",
)

FILE_TYPES = (
    "empty",
    "no_match",
    "one_match",
    "many_match",
    "unicode_content",
    "missing_path",
)

SOURCE_TYPES = ("inline", "file_flag")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    out_path = args.out or (project_root / "frames" / "icgrep_frames_full.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "id",
        "tool",
        "source_type",
        "pattern_type",
        "file_type",
        "count",
        "invert",
        "ignore_case",
        "line_numbers",
    ]

    rows = []
    case_id = 0
    for st, pt, ft, count, invert, ign, ln in product(
        SOURCE_TYPES,
        PATTERN_TYPES,
        FILE_TYPES,
        (0, 1),
        (0, 1),
        (0, 1),
        (0, 1),
    ):
        if count == 1 and ln == 1:
            continue
        if ft == "missing_path" and ln == 1:
            continue

        case_id += 1
        rows.append(
            {
                "id": str(case_id),
                "tool": "icgrep",
                "source_type": st,
                "pattern_type": pt,
                "file_type": ft,
                "count": str(count),
                "invert": str(invert),
                "ignore_case": str(ign),
                "line_numbers": str(ln),
            }
        )

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} frames to {out_path}")


if __name__ == "__main__":
    main()
