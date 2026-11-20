#!/usr/bin/env bash

set -euo pipefail

if (( $# < 1 || $# > 2 )); then
  echo "Usage: $0 OUTPUT_DIR [XRAY_BINARY]" >&2
  exit 2
fi

output_dir="$1"
xray_binary="${2:-xray}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT

latest_tag() {
  git ls-remote --tags "https://github.com/${1}.git" \
    | awk '{print $2}' \
    | sed -E 's@refs/tags/@@; s@\^\{\}@@' \
    | grep -E '^[0-9]{12}$' \
    | sort -r \
    | sed -n '1p'
}

FREEMAN_GEOIP_TAG="${FREEMAN_GEOIP_TAG:-$(latest_tag losogudok/freemanvpn-geoip)}"
FREEMAN_GEOSITE_TAG="${FREEMAN_GEOSITE_TAG:-$(latest_tag losogudok/freemanvpn-geosite)}"
export FREEMAN_GEOIP_TAG FREEMAN_GEOSITE_TAG
[[ "$FREEMAN_GEOIP_TAG" =~ ^[0-9]{12}$ && "$FREEMAN_GEOSITE_TAG" =~ ^[0-9]{12}$ ]] || {
  echo "FreemanVPN geodata tags must contain 12 digits" >&2
  exit 1
}

geoip_url="https://raw.githubusercontent.com/losogudok/freemanvpn-geoip/${FREEMAN_GEOIP_TAG}/release/geoip.dat"
geosite_url="https://raw.githubusercontent.com/losogudok/freemanvpn-geosite/${FREEMAN_GEOSITE_TAG}/release/geosite.dat"
mkdir -p "$work_dir/assets" "$work_dir/publish"
curl -fsSL --retry 3 --retry-delay 2 -o "$work_dir/assets/geoip.dat" "$geoip_url"
curl -fsSL --retry 3 --retry-delay 2 -o "$work_dir/assets/geosite.dat" "$geosite_url"

python3 "$script_dir/check-russian-ip.py" "$repo_dir/XRAY_JSON/RUSSIAN_IP.JSON" \
  --xray "$xray_binary" --assets "$work_dir/assets"
python3 "$script_dir/render-russian-ip.py" "$work_dir/publish/RUSSIAN_IP.JSON"
python3 "$script_dir/check-russian-ip.py" "$work_dir/publish/RUSSIAN_IP.JSON" \
  --xray "$xray_binary"
cp -- "$repo_dir/XRAY_JSON/RUSSIAN_IP.JSON" "$work_dir/publish/RUSSIAN_IP.compact.JSON"

jq -n \
  --arg commit "$(git -C "$repo_dir" rev-parse HEAD)" \
  --arg xray "$("$xray_binary" version | sed -n '1p')" \
  --arg geoip_tag "$FREEMAN_GEOIP_TAG" --arg geoip_url "$geoip_url" \
  --arg geoip_sha256 "$(sha256sum "$work_dir/assets/geoip.dat" | awk '{print $1}')" \
  --arg geosite_tag "$FREEMAN_GEOSITE_TAG" --arg geosite_url "$geosite_url" \
  --arg geosite_sha256 "$(sha256sum "$work_dir/assets/geosite.dat" | awk '{print $1}')" \
  '{sourceCommit: $commit, xrayVersion: $xray,
    geoip: {tag: $geoip_tag, url: $geoip_url, sha256: $geoip_sha256},
    geosite: {tag: $geosite_tag, url: $geosite_url, sha256: $geosite_sha256}}' \
  > "$work_dir/publish/build-info.json"
(
  cd -- "$work_dir/publish"
  sha256sum RUSSIAN_IP.JSON RUSSIAN_IP.compact.JSON build-info.json > SHA256SUMS
)

# Publish files locally only after both template variants pass the real core.
mkdir -p "$output_dir"
cp -- "$work_dir/publish/"* "$output_dir/"
echo "Russian IP build written to $output_dir"
