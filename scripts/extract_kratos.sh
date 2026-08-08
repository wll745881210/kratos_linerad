#!/bin/bash
# Extract the line_rt-relevant parts from the full Kratos source tree.
# Usage: ./scripts/extract_kratos.sh <kratos_source> <dest_dir>
# Example: ./scripts/extract_kratos.sh ~/code/kratos ./kratos
set -euo pipefail

SRC="${1:?Usage: $0 <kratos_source> <dest_dir>}"
DEST="${2:?Usage: $0 <kratos_source> <dest_dir>}"

if [ ! -d "$SRC/src" ]; then
    echo "Error: $SRC/src not found. Is this a Kratos source tree?"
    exit 1
fi

echo "Extracting Kratos from $SRC to $DEST ..."

# --- src/ : only needed subdirectories (exclude chemistry, dynamics, multigrid, cic, indices.h) ---
mkdir -p "$DEST/src/modules/particle"
rsync -a --exclude='.git' --exclude='__pycache__' \
    --exclude='modules/chemistry' \
    --exclude='modules/dynamics' \
    --exclude='modules/multigrid' \
    --exclude='modules/particle/cic' \
    "$SRC/src/" "$DEST/src/"
# Remove indices.h (only referenced by excluded modules)
rm -f "$DEST/src/modules/indices.h"

# --- usr/extension/algo/ : header-only interpolation library (interp.h, 24 KB) ---
mkdir -p "$DEST/usr/extension"
rsync -a --exclude='.git' "$SRC/usr/extension/algo/" "$DEST/usr/extension/algo/"

# --- usr_ext/line_rt/ : the line_rt module ---
mkdir -p "$DEST/usr_ext"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='obj/' --exclude='bin/' \
    "$SRC/usr_ext/line_rt/" "$DEST/usr_ext/line_rt/"

# --- visual/binary_io.py : binary I/O reader for standalone tests ---
mkdir -p "$DEST/visual"
cp "$SRC/visual/binary_io.py" "$DEST/visual/binary_io.py"

# --- Makefile ---
cp "$SRC/Makefile" "$DEST/Makefile"

echo "Extraction complete."
echo "Contents:"
du -sh "$DEST" "$DEST/src" "$DEST/usr" "$DEST/usr_ext" "$DEST/visual"
echo "Total files: $(find "$DEST" -type f | wc -l)"
