#!/usr/bin/env python3
# written by Alistair King & Copilot
"""
orca6-batch-create.py

Creates numbered sub-folders for ORCA6 runs, in sub-folders, for each geometry extracted
from a geometrylist.xyz ensemble:

Requires
	- geometrylist.xyz
	- orca6.inp
	- slurm-batch-submission-script
	- cleanup.sh

Generates
	- geometry.xyz
	- orca6.inp            (from -i: text or file path)
	- job.slurm            (from -s: text or file path)
	- cleanup.sh           (safe defaults; adjust patterns if needed)

Geometries are provided by an number-of-lines argument (flagged with '-n'), which describes one complete geometry.
This is used to sequentially extract the separate ensemble geometries for placement in each folder.
Folder numbering starts at 1 and continues until the geometry list is exhausted.
The desired Slurm & ORCA inputs are provided in the same folder as the script.
The geometry should be defined using the '* xyzfile 0 1 geometry.xyz' formatting in the orca6.inp file.

The bash script 'submit-singleton.sh' can then be used to submit the runs


Usage examples:
  # Using file paths for ORCA and SLURM

python3 orca6-batch-create.py -g geometrylist.xyz -n 29 -i orca6.inp -s slurm-batch-submission-script

Folders should be checked to see if the geometry extraction has worked as planned.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple


def read_arg_text_or_file(value: str) -> str:
    """
    If 'value' is a path to an existing file, return file contents.
    Otherwise, return 'value' itself as literal text.
    """
    p = Path(value)
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Fallback to latin-1 if utf-8 fails
            return p.read_text(encoding="latin-1")
    return value


def chunk_lines(lines: List[str], n: int) -> List[List[str]]:
    """
    Return a list of chunks, each chunk containing 'n' lines.
    If len(lines) is not divisible by n, ignore the remainder (emit warning externally).
    """
    return [lines[i:i+n] for i in range(0, (len(lines) // n) * n, n)]


def write_file(path: Path, content: str, make_executable: bool = False) -> None:
    path.write_text(content, encoding="utf-8")
    if make_executable:
        # rwxr-xr-x
        os.chmod(path, 0o755)


def build_cleanup_script() -> str:
    """
    A conservative cleanup script that removes common ORCA scratch/intermediate files
    but keeps key outputs (e.g., *.out, *.xyz, *.gbw) intact. Adjust patterns to your workflow.
    """
    return """#!/usr/bin/env bash
# cleanup.sh — remove common ORCA scratch/intermediate files safely.
# Adjust patterns as needed; by default we keep *.out, *.xyz, *.gbw.

set -euo pipefail

# Patterns that are generally safe to delete (review for your case):
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
    # Note: Do not remove *.gbw, *.out, *.xyz by default.


def ensure_dir(path: Path, force: bool) -> None:
    """
    Create directory if not exists. If exists:
      - If empty: OK
      - If not empty: require force=True
    """
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return

    if not path.is_dir():
        raise RuntimeError(f"Path exists and is not a directory: {path}")

    # Check emptiness
    if any(path.iterdir()):
        if not force:
            raise RuntimeError(
                f"Directory {path} already exists and is not empty. "
                "Use --force to allow reuse."
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create ORCA6 batch sub-folders from a concatenated .xyz geometry list."
    )
    parser.add_argument(
        "-g", "--geometry-list", required=True,
        help="Path to the concatenated .xyz geometry list file."
    )
    parser.add_argument(
        "-n", "--lines-per-geometry", required=True, type=int,
        help="Number of lines per geometry chunk (fixed)."
    )
    parser.add_argument(
        "-i", "--orca-input", required=True,
        help=("ORCA input: either a path to a file (content will be copied) "
              "or a literal text string.")
    )
    parser.add_argument(
        "-s", "--slurm-input", required=True,
        help=("SLURM script: either a path to a file (content will be copied) "
              "or a literal text string.")
    )
    parser.add_argument(
        "-o", "--out", default=".",
        help="Output root directory (default: current directory)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Allow reuse of non-empty existing sub-folders."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without writing files."
    )

    args = parser.parse_args()

    geom_list_path = Path(args.geometry_list)
    if not geom_list_path.is_file():
        print(f"ERROR: Geometry list file not found: {geom_list_path}", file=sys.stderr)
        return 2

    if args.lines_per_geometry <= 0:
        print("ERROR: --lines-per-geometry (-n) must be a positive integer.", file=sys.stderr)
        return 2

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    # Read geometry list
    try:
        raw = geom_list_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = geom_list_path.read_text(encoding="latin-1")
    # Preserve line endings per line; strip trailing '\n' only when joining back.
    lines = raw.splitlines()

    # Build chunks
    n = args.lines_per_geometry
    chunks = chunk_lines(lines, n)
    total_lines = len(lines)
    total_chunks = len(chunks)
    remainder = total_lines - total_chunks * n
    if remainder:
        print(
            f"WARNING: Total lines ({total_lines}) is not a multiple of -n ({n}). "
            f"Ignoring last {remainder} line(s).",
            file=sys.stderr
        )

    # Read ORCA/SLURM content (file or text)
    orca_text = read_arg_text_or_file(args.orca_input)
    slurm_text = read_arg_text_or_file(args.slurm_input)
    cleanup_text = build_cleanup_script()

    if total_chunks == 0:
        print("No full geometry chunks to process (0). Nothing to do.", file=sys.stderr)
        return 0

    print(f"Found {total_chunks} geometry chunk(s) of {n} line(s) each.")
    print(f"Output root: {out_root.resolve()}")

    for idx, chunk in enumerate(chunks, start=1):
        subdir = out_root / str(idx)

        if args.dry_run:
            print(f"[DRY-RUN] Would create folder: {subdir}")
        else:
            ensure_dir(subdir, force=args.force)

        # geometry.xyz content
        geom_content = "\n".join(chunk) + "\n"

        # File paths
        geom_path = subdir / "geometry.xyz"
        orca_path = subdir / "orca6.inp"
        slurm_path = subdir / "job.slurm"
        cleanup_path = subdir / "cleanup.sh"

        if args.dry_run:
            print(f"[DRY-RUN] Would write: {geom_path} (lines={len(chunk)})")
            print(f"[DRY-RUN] Would write: {orca_path} (len={len(orca_text)} chars)")
            print(f"[DRY-RUN] Would write: {slurm_path} (len={len(slurm_text)} chars)")
            print(f"[DRY-RUN] Would write: {cleanup_path} (executable)")
        else:
            write_file(geom_path, geom_content)
            write_file(orca_path, orca_text)
            write_file(slurm_path, slurm_text)
            write_file(cleanup_path, cleanup_text, make_executable=True)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
