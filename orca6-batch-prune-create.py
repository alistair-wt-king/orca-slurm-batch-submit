#!/usr/bin/env python3
# written by Alistair King & Copilot
"""
orca6-batch-prune-create.py

A modified version of orca6-batch-create.py, which prunes geometries from the list.

Create numbered sub-folders for ORCA6 runs from a concatenated .xyz geometry list.

Flags (only these are supported):
  -g  Path to concatenated .xyz geometry list file (required)
  -n  Lines per geometry (fixed chunk size, required)
  -i  ORCA input: either a file path or literal text (required)
  -s  SLURM input: either a file path or literal text (required)
  -first  Number of initial geometries to always include (>=0, required)
  -prune  Optional denominator P to take a 1/P fraction from the remaining geometries
          using stride behavior: select one, then skip (P-1), repeat.

Behavior:
  1) Split geometry list into chunks of exactly -n lines. Ignore trailing remainder lines.
  2) Create sub-folders 1..M for selected geometries.
  3) In each folder, write:
        geometry.xyz     (chunk)
        orca6.inp        (from -i: file content or literal text)
        job.slurm        (from -s: file content or literal text)
        cleanup.sh       (simple safe cleanup; executable)
  4) Selection:
        - Always include the first F geometries (-first F).
        - If -prune P is given and P>0:
            From the remaining R geometries, select indices with stride P:
            take first of remainder, then every P-th after that.
        - If -first >= total, pruning is skipped.

No other flags or modes are implemented (by request).
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List


def read_text_or_file(value: str) -> str:
    """If value is a path to an existing file, return its content; else return value as text."""
    p = Path(value)
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return p.read_text(encoding="latin-1")
    return value


def chunk_lines(lines: List[str], n: int) -> List[List[str]]:
    """Return fixed-size chunks of length n; ignore trailing remainder."""
    if n <= 0:
        return []
    usable = (len(lines) // n) * n
    return [lines[i:i + n] for i in range(0, usable, n)]


def write_file(path: Path, content: str, make_executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if make_executable:
        os.chmod(path, 0o755)


def build_cleanup_script() -> str:
    return """#!/usr/bin/env bash
# cleanup.sh — remove common ORCA scratch/intermediate files safely.
# Adjust patterns as needed; by default we keep *.out, *.xyz, *.gbw.

set -euo pipefail

patterns=(
  "*.tmp"
  "*.trj"
  "*.pc_*.xyz"
  "*.engrad"
  "*.hess"
  "*.molden.input"
  "*.mdci"
  "*.mdprop"
  "orca.*"
  "scratch"
  "tmp"
)

shopt -s nullglob
for p in "${patterns[@]}"; do
  rm -rf $p
done

echo "Cleanup done."
"""


def select_indices(total: int, first_count: int, prune_den: int | None) -> List[int]:
    """
    Selection per spec:
      - Include [0..first_count-1] (clamped to total).
      - If prune_den provided and > 0:
          From remaining indices [first_count..total-1], select stride(P):
          first_count + 0, first_count + P, first_count + 2P, ...
    Returns sorted unique indices.
    """
    if total <= 0:
        return []
    first = max(0, min(first_count, total))
    selected = list(range(first))

    if prune_den is not None:
        if prune_den <= 0:
            raise ValueError("-prune must be a positive integer.")
        remaining = total - first
        base = first
        j = 0
        while j < remaining:
            selected.append(base + j)
            j += prune_den

    # Ensure increasing order & uniqueness
    return sorted(set(selected))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create ORCA6 batch sub-folders with -first and stride-based -prune."
    )
    # Only the requested flags:
    parser.add_argument("-g", required=True, dest="geometry_list",
                        help="Path to concatenated .xyz geometry list file.")
    parser.add_argument("-n", required=True, type=int, dest="lines_per_geometry",
                        help="Number of lines per geometry (fixed).")
    parser.add_argument("-i", required=True, dest="orca_input",
                        help="ORCA input: file path or literal text.")
    parser.add_argument("-s", required=True, dest="slurm_input",
                        help="SLURM script: file path or literal text.")
    parser.add_argument("-first", required=True, type=int, dest="first",
                        help="Number of initial geometries to always include (>=0).")
    parser.add_argument("-prune", type=int, default=None, dest="prune",
                        help="Denominator P to take a 1/P stride fraction from the remainder.")

    args = parser.parse_args()

    geom_list_path = Path(args.geometry_list)
    if not geom_list_path.is_file():
        print(f"ERROR: geometry list file not found: {geom_list_path}", file=sys.stderr)
        return 2

    if args.lines_per_geometry <= 0:
        print("ERROR: -n must be a positive integer.", file=sys.stderr)
        return 2

    if args.first < 0:
        print("ERROR: -first must be >= 0.", file=sys.stderr)
        return 2

    if args.prune is not None and args.prune <= 0:
        print("ERROR: -prune must be a positive integer when provided.", file=sys.stderr)
        return 2

    # Read geometry list and split
    try:
        raw = geom_list_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = geom_list_path.read_text(encoding="latin-1")
    lines = raw.splitlines()

    chunks = chunk_lines(lines, args.lines_per_geometry)
    total = len(chunks)
    if total == 0:
        print("No full geometry chunks available. Nothing to do.", file=sys.stderr)
        return 0

    remainder_lines = len(lines) - total * args.lines_per_geometry
    if remainder_lines:
        print(f"WARNING: ignoring last {remainder_lines} line(s) not forming a complete chunk.",
              file=sys.stderr)

    # Compute selection
    try:
        indices = select_indices(total=total, first_count=args.first, prune_den=args.prune)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not indices:
        print("Selection is empty. Nothing to do.", file=sys.stderr)
        return 0

    # Prepare content
    orca_text = read_text_or_file(args.orca_input)
    slurm_text = read_text_or_file(args.slurm_input)
    cleanup_text = build_cleanup_script()

    # Create folders 1..M in ascending source index order
    for ord_idx, geom_idx in enumerate(indices, start=1):
        subdir = Path(str(ord_idx))
        # Ensure new or empty directory (simple safety: if exists and not empty, abort)
        if subdir.exists() and subdir.is_dir():
            if any(subdir.iterdir()):
                print(f"ERROR: directory '{subdir}' exists and is not empty. "
                      f"Remove it or rename before running.", file=sys.stderr)
                return 2
        else:
            subdir.mkdir(parents=True, exist_ok=True)

        geom_content = "\n".join(chunks[geom_idx]) + "\n"
        write_file(subdir / "geometry.xyz", geom_content)
        write_file(subdir / "orca6.inp", orca_text)
        write_file(subdir / "job.slurm", slurm_text)
        write_file(subdir / "cleanup.sh", cleanup_text, make_executable=True)

    print(f"Done. Created {len(indices)} folder(s) from {total} geometries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
