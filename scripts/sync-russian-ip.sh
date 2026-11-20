#!/usr/bin/env bash

set -Eeuo pipefail

if (( $# != 1 )); then
  echo "Usage: $0 RENDERED_JSON" >&2
  exit 2
fi

: "${REMNAWAVE_API_BASE_URL:?Set the REMNAWAVE_API_BASE_URL repository variable}"
: "${REMNAWAVE_TOKEN:?Set the REMNAWAVE_TOKEN repository secret}"
: "${REMNAWAVE_RU_IP_TEMPLATE_UUID:?Set the REMNAWAVE_RU_IP_TEMPLATE_UUID repository variable}"

template_json="$1"
template_uuid="$REMNAWAVE_RU_IP_TEMPLATE_UUID"
[[ "$template_uuid" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || {
  echo "REMNAWAVE_RU_IP_TEMPLATE_UUID must be a UUID" >&2
  exit 1
}
jq -e '
  type == "object" and .remnawave.addVirtualHostAsOutbound == true
  and (.routing.rules | type == "array" and length > 0)
  and (.outbounds | type == "array")
' "$template_json" > /dev/null
if jq -e '.. | strings | select(test("^(geosite|geoip):"))' "$template_json" > /dev/null; then
  echo "Russian IP synchronization requires the expanded JSON, not the compact source" >&2
  exit 1
fi

work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
templates_url="${REMNAWAVE_API_BASE_URL%/}/subscription-templates"
target_url="$templates_url/$template_uuid"
auth_header="Authorization: Bearer ${REMNAWAVE_TOKEN}"

get_template() {
  curl -fsS --connect-timeout 10 --max-time 45 \
    -H "Accept: application/json" -H "$auth_header" "$target_url" -o "$1"
}

patch_template() {
  curl -fsS --connect-timeout 10 --max-time 45 -X PATCH \
    -H "Accept: application/json" -H "Content-Type: application/json" \
    -H "$auth_header" --data-binary "@$1" "$templates_url" -o "$2"
}

matches_template() {
  jq -e --arg uuid "$template_uuid" --slurpfile expected "$2" '
    (.response // .)
    | .uuid == $uuid and .templateType == "XRAY_JSON" and .templateJson == $expected[0]
  ' "$1" > /dev/null
}

get_template "$work_dir/current.json"
jq -e --arg uuid "$template_uuid" '
  (.response // .)
  | .uuid == $uuid and .templateType == "XRAY_JSON" and (.templateJson | type == "object")
' "$work_dir/current.json" > /dev/null || {
  echo "REMNAWAVE_RU_IP_TEMPLATE_UUID must identify an existing XRAY_JSON template" >&2
  exit 1
}
if matches_template "$work_dir/current.json" "$template_json"; then
  echo "Remnawave Russian IP template $template_uuid is already up to date"
  exit 0
fi
jq '(.response // .).templateJson' "$work_dir/current.json" > "$work_dir/previous.json"
jq -n --arg uuid "$template_uuid" --slurpfile tpl "$template_json" \
  '{uuid: $uuid, templateJson: $tpl[0]}' > "$work_dir/patch.json"
jq -n --arg uuid "$template_uuid" --slurpfile tpl "$work_dir/previous.json" \
  '{uuid: $uuid, templateJson: $tpl[0]}' > "$work_dir/rollback.json"

rollback() {
  local original_status=$?
  trap - ERR
  # A failed PATCH can still have been applied. Restore the previous template
  # even when the write's response was lost, then verify the persisted state.
  if patch_template "$work_dir/rollback.json" "$work_dir/rollback-response.json" \
    && matches_template "$work_dir/rollback-response.json" "$work_dir/previous.json" \
    && get_template "$work_dir/rollback-current.json" \
    && matches_template "$work_dir/rollback-current.json" "$work_dir/previous.json"; then
    echo "Rolled back Remnawave Russian IP template $template_uuid" >&2
  else
    echo "Remnawave Russian IP rollback incomplete; manual reconciliation required" >&2
  fi
  exit "$original_status"
}

trap rollback ERR
patch_template "$work_dir/patch.json" "$work_dir/patch-response.json"
matches_template "$work_dir/patch-response.json" "$template_json"
get_template "$work_dir/updated.json"
matches_template "$work_dir/updated.json" "$template_json"
trap - ERR
echo "Updated Remnawave Russian IP template $template_uuid"
