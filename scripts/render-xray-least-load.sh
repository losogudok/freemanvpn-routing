#!/usr/bin/env bash

set -euo pipefail

source_is_rendered=false
if [[ "${1:-}" == "--rendered" ]]; then
  source_is_rendered=true
  shift
fi

if (( $# != 2 )); then
  echo "Usage: $0 [--rendered] SOURCE_JSON OUTPUT_JSON" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_json="$1"
output_json="$2"
settings_json="$script_dir/../XRAY_JSON/LEASTLOAD.settings.json"

# Expand the same geodata as the default subscription before adding the pool.
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
if [[ "$source_is_rendered" == "true" ]]; then
  cp -- "$source_json" "$work_dir/default.json"
else
  "$script_dir/render-xray-json.sh" "$source_json" "$work_dir/default.json"
fi

jq -e --slurpfile settings "$settings_json" '
  if ([.routing.rules[] | select(.outboundTag == "proxy")] | length) == 0 then
    error("source template must contain proxy routing rules")
  else
    . as $base
    | $settings[0] as $pool
    # Import pool settings; DNS, inbounds and rules follow the source.
    | $base
    | .remnawave = $pool.remnawave
    | .burstObservatory = $pool.burstObservatory
    | .routing.balancers = $pool.routing.balancers
    | .routing.rules |= map(
        if .outboundTag == "proxy" then
          del(.outboundTag) | .balancerTag = $pool.routing.balancers[0].tag
        else
          .
        end
      )
  end
' "$work_dir/default.json" > "$work_dir/leastload.json"

cp -- "$work_dir/leastload.json" "$output_json"
