#!/usr/bin/env bash
# Run once on a trusted machine; refuses to replace an existing pair.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
output=${1:-"$root/keys/pair"}
if [[ -e "$output/drone.key" || -e "$output/gs.key" ]]; then printf 'Existing keys found; refusing to overwrite them.\n' >&2; exit 1; fi
umask 077
mkdir -p "$output"
(cd "$output" && "$root/vendor/skvoz-wfb-ng/wfb_keygen")
printf 'Keep drone.key on Pi. Transfer only gs.key to the matching NSU. Neither file belongs in Git.\n'
