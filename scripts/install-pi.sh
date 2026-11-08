#!/usr/bin/env bash
# Raspberry Pi OS: install camera/WFB dependencies, never change a radio interface.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
sudo apt-get update
sudo apt-get install -y --no-install-recommends build-essential git pkg-config bc iw \
 libsodium-dev libpcap-dev rpicam-apps-lite python3-gi gir1.2-gstreamer-1.0 \
 gir1.2-gst-plugins-base-1.0 gstreamer1.0-tools gstreamer1.0-plugins-base \
 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav
vendor="$root/vendor/skvoz-wfb-ng"
commit=a5e7205d0b8608d15a06cdac2ac4e444544f8624
mkdir -p "$root/vendor"
if [[ ! -d "$vendor/.git" ]]; then
 if [[ -e "$vendor" ]]; then printf 'Existing vendor directory is not a Git checkout: %s\n' "$vendor" >&2; exit 1; fi
 git clone https://github.com/svpcom/wfb-ng.git "$vendor"
fi
if [[ -n $(git -C "$vendor" status --porcelain) ]]; then printf 'Vendor has local changes; preserve them and stop.\n' >&2; exit 1; fi
git -C "$vendor" checkout --detach "$commit"
make -C "$vendor" -j2 RELEASE=bvs-camera VERSION=0.1.0 COMMIT="$commit" wfb_tx wfb_rx wfb_tx_cmd wfb_keygen
printf 'Software installed. Check camera, matching keys and external radio before starting.\n'
