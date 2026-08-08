#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UUID="mousehair-magnifier@maximumbeans"
TARGET_DIR="${HOME}/.local/share/cinnamon/extensions/${UUID}"

mkdir -p "$(dirname -- "${TARGET_DIR}")"
rm -rf -- "${TARGET_DIR}"
cp -a -- "${SOURCE_DIR}/${UUID}" "${TARGET_DIR}"

printf 'Installed version 4.5 to:\n  %s\n\n' "${TARGET_DIR}"
printf '%s\n' \
  'Restart Cinnamon with Alt+F2, type r, press Enter.' \
  'Then disable and re-enable "Mousehair Magnifier Proof".'
