#!/bin/bash
# Run one SKIRT f_esc case and print the direction-averaged escape
# fraction (mean over the 6 Fibonacci SEDInstruments).
#
#   ./run_fesc.sh <ski-file> <run-dir> [n_threads]
#
# Prints one line: "<run-dir> f_esc=<value>".
set -e
SKIRT=~/scratch/skirt_tst/SKIRT9/build/SKIRT/main/skirt
HERE="$(cd "$(dirname "$0")" && pwd)"

SKI="$1"
DIR="$2"
THREADS="${3:-16}"

mkdir -p "$DIR"
cp "$SKI" "$DIR/fesc.ski"
cd "$DIR"
"$SKIRT" -t "$THREADS" -b -k fesc.ski > fesc_log.txt 2>&1

python3 "$HERE/parse_fesc.py" "$DIR"
