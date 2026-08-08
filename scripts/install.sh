#!/usr/bin/env bash
# install.sh — Configure kratos_root for binary release users
#
# Usage: ./scripts/install.sh /path/to/kratos
#
# Writes the kratos_root path to ~/.config/kratos_linerad/paths.conf
# so the Python pipeline can auto-detect the Kratos binary.

set -euo pipefail

KRATOS_ROOT="${1:-}"
CONFIG_DIR="${HOME}/.config/kratos_linerad"
CONFIG_FILE="${CONFIG_DIR}/paths.conf"

if [ -z "${KRATOS_ROOT}" ]; then
    echo "Usage: $0 <path-to-kratos-directory>"
    echo ""
    echo "Example: $0 /opt/kratos_linerad/kratos"
    echo ""
    echo "The kratos directory must contain bin/kratos."
    exit 1
fi

# Resolve to absolute path
KRATOS_ROOT="$(cd "${KRATOS_ROOT}" && pwd)"

# Verify the binary exists
if [ ! -f "${KRATOS_ROOT}/bin/kratos" ]; then
    echo "ERROR: ${KRATOS_ROOT}/bin/kratos not found."
    echo "Ensure you have built Kratos (cd kratos && make USRDIR=usr_ext/line_rt -j8)."
    exit 1
fi

# Write config
mkdir -p "${CONFIG_DIR}"
cat > "${CONFIG_FILE}" << EOF
# kratos_linerad configuration
# Written by install.sh
kratos_root=${KRATOS_ROOT}
EOF

echo "Configured kratos_root = ${KRATOS_ROOT}"
echo "Written to ${CONFIG_FILE}"
echo ""
echo "The Python pipeline will now auto-detect the Kratos binary."
echo "You can also set KRATOS_ROOT=${KRATOS_ROOT} in your shell profile."
