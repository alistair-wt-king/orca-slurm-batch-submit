#!/usr/bin/env bash
# submit-singleton.sh written by Alistair King & Copilot
# Submits SLURM jobs in each sub-folder using:
#   sbatch -v -d singleton job.slurm
#
# Features:
#   • Creates log immediately (even if sbatch missing)
#   • Prints and logs the exact command per folder
#   • Streams sbatch stdout/stderr to terminal and to the log
#   • Continues on errors; prints summary at end
#   • Optional: --dry-run (prints commands only)

set -u  # (avoid -e so we can keep going on errors)

JOB_FILE="job.slurm"
LOG_FILE="submit-singleton.log"
DRY_RUN="no"

# --- Colors (best-effort) ---
if [ -t 1 ]; then
  RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; BOLD="\033[1m"; RESET="\033[0m"
else
  RED=""; GREEN=""; YELLOW=""; BLUE=""; BOLD=""; RESET=""
fi

ts() { date +"%Y-%m-%d %H:%M:%S"; }
info() { printf "%b[INFO ]%b %s\n" "$BLUE" "$RESET" "$1"; echo "$(ts) INFO  $1" >> "$LOG_FILE"; }
warn() { printf "%b[WARN ]%b %s\n" "$YELLOW" "$RESET" "$1"; echo "$(ts) WARN  $1" >> "$LOG_FILE"; }
err()  { printf "%b[ERROR]%b %s\n" "$RED" "$RESET" "$1" >&2; echo "$(ts) ERROR $1" >> "$LOG_FILE"; }
ok()   { printf "%b[ OK  ]%b %s\n" "$GREEN" "$RESET" "$1"; echo "$(ts) OK    $1" >> "$LOG_FILE"; }

usage() {
  cat <<EOF
${BOLD}submit-singleton.sh${RESET}
Submits SLURM jobs in each sub-folder with: sbatch -v -d singleton job.slurm

Usage:
  $0           # submit for real
  $0 --dry-run # print what would be submitted (no sbatch calls)

Notes:
  • Log file: ${LOG_FILE}
  • 'singleton' serializes jobs that share the same job name.
    Ensure your job.slurm files use the same '#SBATCH --job-name=...'.
EOF
}

# --- Args ---
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN="yes"
elif [[ "${1:-}" =~ ^(-h|--help)$ ]]; then
  usage; exit 0
elif [[ $# -gt 0 ]]; then
  echo "Unrecognized option: $1" >&2
  usage; exit 1
fi

# --- Create log immediately ---
: > "$LOG_FILE" || { echo "ERROR: cannot create log file: $LOG_FILE" >&2; exit 1; }
echo "========== $(ts) submit-singleton.sh start ==========" >> "$LOG_FILE"
echo "PWD: $(pwd)" >> "$LOG_FILE"
echo "DRY_RUN=$DRY_RUN" >> "$LOG_FILE"
echo "PATH=$PATH" >> "$LOG_FILE"
info "Log initialized: $LOG_FILE"

# --- sbatch presence (unless dry-run) ---
if [[ "$DRY_RUN" == "no" ]]; then
  if ! command -v sbatch >/dev/null 2>&1; then
    err "'sbatch' not found in PATH. Are you on a SLURM node / module loaded?"
    echo "=========== $(ts) submit-singleton.sh end ===========" >> "$LOG_FILE"
    exit 1
  fi
  info "sbatch located at: $(command -v sbatch)"
  # Record sbatch version into log (stderr/ok both logged)
  { sbatch --version; } >> "$LOG_FILE" 2>&1 || warn "Could not query 'sbatch --version'."
else
  info "DRY-RUN enabled: skipping sbatch checks."
fi

# --- Discover sub-folders ---
shopt -s nullglob
SUBDIRS=(*/)

if (( ${#SUBDIRS[@]} == 0 )); then
  err "No sub-folders found under: $(pwd)"
  echo "=========== $(ts) submit-singleton.sh end ===========" >> "$LOG_FILE"
  exit 1
fi

# Sort subfolders (numeric-aware if available)
mapfile -t SUBDIRS < <(printf "%s\n" "${SUBDIRS[@]}" | sed 's:/*$::' | (sort -V 2>/dev/null || sort))
info "Found ${#SUBDIRS[@]} sub-folders to scan."

success=0; failed=0; skipped=0; total=0

for dn in "${SUBDIRS[@]}"; do
  (( total++ ))
  # Ensure directory still exists
  if [[ ! -d "$dn" ]]; then
    warn "Skipping '${dn}': not a directory."
    (( skipped++ ))
    continue
  fi

  # Check job file presence and readability
  if [[ ! -f "${dn}/${JOB_FILE}" ]]; then
    warn "Skipping '${dn}': ${JOB_FILE} not found."
    (( skipped++ ))
    continue
  fi
  if [[ ! -r "${dn}/${JOB_FILE}" ]]; then
    warn "Skipping '${dn}': ${JOB_FILE} not readable."
    (( skipped++ ))
    continue
  fi

  # Command to run
  CMD=(sbatch -v -d singleton "${JOB_FILE}")
  info "In '${dn}': ${CMD[*]}"
  echo "----- $(ts) ${dn} command begin -----" >> "$LOG_FILE"
  echo "${CMD[*]}" >> "$LOG_FILE"
  echo "----- $(ts) ${dn} command end -----" >> "$LOG_FILE"

  if [[ "$DRY_RUN" == "yes" ]]; then
    continue
  fi

  # Run sbatch in subfolder; stream output to terminal and log
  # We capture exit code, and tee output to log.
  submit_rc=0
  {
    echo "----- $(ts) ${dn} sbatch output begin -----"
    (
      cd "$dn" && "${CMD[@]}"
    )
    ec=$?
    echo "----- $(ts) ${dn} sbatch output end -----"
    exit $ec
  } 2>&1 | tee -a "$LOG_FILE"
  submit_rc=${PIPESTATUS[0]}  # exit code of the block above

  if [[ $submit_rc -ne 0 ]]; then
    err "Submission FAILED in '${dn}' (exit=$submit_rc)."
    (( failed++ ))
    continue
  fi

  ok "Submitted '${dn}'."
  (( success++ ))
done

info "Summary: success=${success} skipped=${skipped} failed=${failed} total=${total}"
echo "=========== $(ts) submit-singleton.sh end ===========" >> "$LOG_FILE"
exit 0

