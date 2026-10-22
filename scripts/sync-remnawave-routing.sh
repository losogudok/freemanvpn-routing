#!/usr/bin/env bash

set -euo pipefail

: "${REMNAWAVE_API_BASE_URL:?Set the REMNAWAVE_API_BASE_URL repository variable}"
: "${REMNAWAVE_TOKEN:?Set the REMNAWAVE_TOKEN repository secret}"
: "${HAPP_DEFAULT:?Missing HAPP_DEFAULT}"
: "${INCY_DEFAULT:?Missing INCY_DEFAULT}"
: "${RUNNER_TEMP:?Missing RUNNER_TEMP}"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"
settings_json="$repo_dir/XRAY_JSON/LEASTLOAD.settings.json"
work_dir="$(mktemp -d "$RUNNER_TEMP/remnawave-sync.XXXXXX")"
trap 'rm -rf -- "$work_dir"' EXIT

# Both templates must use the exact same rendered geodata snapshot.
"$script_dir/render-xray-json.sh" "$repo_dir/XRAY_JSON/DEFAULT.JSON" "$work_dir/default.json"
"$script_dir/render-xray-least-load.sh" --rendered "$work_dir/default.json" "$work_dir/leastload.json"

TEMPLATES_URL="${REMNAWAVE_API_BASE_URL%/}/subscription-templates"
SETTINGS_URL="${REMNAWAVE_API_BASE_URL%/}/subscription-settings"
AUTH_HEADER="Authorization: Bearer ${REMNAWAVE_TOKEN}"

get_json() {
  curl -fsS -H "Accept: application/json" -H "$AUTH_HEADER" "$1"
}

TEMPLATES_LIST="$(get_json "$TEMPLATES_URL")"

# Compact templates may be empty on first sync. Resolve names/UUIDs before
# legacy discovery so the two Auto variants do not become ambiguous matches.
jq \
  --arg default_pin "${REMNAWAVE_V2RAYTUN_TEMPLATE_UUID:-}" \
  --arg auto_pin "${REMNAWAVE_V2RAYTUN_AUTO_TEMPLATE_UUID:-}" '
  (.response // .).templates as $templates
  | def resolve($name; $pin):
      [$templates[] | select(.templateType == "XRAY_JSON")
        | select(if $pin != "" then .uuid == $pin else .name == $name end)]
      | if length == 1 then .[0]
        else error("expected exactly one XRAY_JSON template for " + $name + "; found " + (length | tostring)
          + ". Available templates: " + ([$templates[] | "\(.name) [\(.templateType)] (\(.uuid))"] | join(", "))) end;
    if $default_pin != "" or $auto_pin != ""
      or any($templates[]; .name == "V2RayTun Compact" or .name == "V2RayTun Auto Compact") then
      {default: resolve("V2RayTun Compact"; $default_pin),
       auto: resolve("V2RayTun Auto Compact"; $auto_pin)}
      | if .default.uuid == .auto.uuid then error("compact template UUIDs must be different") else . end
    else null end
' <<< "$TEMPLATES_LIST" > "$work_dir/compact-targets.json"
compact_enabled="$(jq '. != null' "$work_dir/compact-targets.json")"

TEMPLATE_UUID="$(
  jq -re --arg pinned "${REMNAWAVE_DEFAULT_TEMPLATE_UUID:-}" \
    --slurpfile compact "$work_dir/compact-targets.json" '
    (.response // .).templates
    | if type != "array" then error("unexpected subscription templates response") else . end
    | [.[] | select(.templateType == "XRAY_JSON")
        | select(.uuid != $compact[0].default.uuid and .uuid != $compact[0].auto.uuid)] as $templates
    | [$templates[] | select(.name == "Default Xray JSON")] as $named
    | [$templates[] | select(.uuid == $pinned)] as $byUuid
    | if $pinned != "" then
        if ($byUuid | length) == 1 then $byUuid[0].uuid
        else error("REMNAWAVE_DEFAULT_TEMPLATE_UUID does not identify one XRAY_JSON template") end
      elif ($named | length) == 1 then $named[0].uuid
      elif ($named | length) == 0 and ($templates | length) == 1 then $templates[0].uuid
      else error("cannot uniquely identify default template; set REMNAWAVE_DEFAULT_TEMPLATE_UUID. XRAY_JSON templates: "
        + ([$templates[] | "\(.name) (\(.uuid))"] | join(", "))) end
  ' <<< "$TEMPLATES_LIST"
)"

if [[ "$TEMPLATE_UUID" == "${REMNAWAVE_LEASTLOAD_TEMPLATE_UUID:-}" ]]; then
  echo "Default and virtual template UUIDs must be different" >&2
  exit 1
fi

# List responses omit content. Inspect each JSON template to find the pool,
# rejecting absent/ambiguous matches before any PATCH. An optional UUID pins it.
jq -er --arg default "$TEMPLATE_UUID" --arg pinned "${REMNAWAVE_LEASTLOAD_TEMPLATE_UUID:-}" \
  --slurpfile compact "$work_dir/compact-targets.json" '
  (.response // .).templates
  | [.[] | select(.templateType == "XRAY_JSON" and .uuid != $default)
      | select(.uuid != $compact[0].default.uuid and .uuid != $compact[0].auto.uuid)
      | select($pinned == "" or .uuid == $pinned) | .uuid]
  | .[]
' <<< "$TEMPLATES_LIST" > "$work_dir/candidate-uuids.txt" || {
  echo "No virtual XRAY_JSON template found; check its assignment/optional UUID" >&2
  exit 1
}

pool_uuids=()
while IFS= read -r uuid; do
  get_json "$TEMPLATES_URL/$uuid" > "$work_dir/candidate.json"
  if jq -e --slurpfile pool "$settings_json" '
    (.response // .).templateJson as $template
    | ($pool[0].routing.balancers[0].tag) as $tag
    | [$pool[0].remnawave.injectHosts[].tagPrefix] as $prefixes
    | any($template.routing.balancers[]?; .tag == $tag)
      and ([$template.remnawave.injectHosts[]?.tagPrefix] == $prefixes)
  ' "$work_dir/candidate.json" > /dev/null; then
    pool_uuids+=("$uuid")
    cp -- "$work_dir/candidate.json" "$work_dir/current-pool.json"
  fi
done < "$work_dir/candidate-uuids.txt"
if (( ${#pool_uuids[@]} != 1 )); then
  echo "Expected exactly one virtual template matching the balancer and host prefixes; found ${#pool_uuids[@]}" >&2
  exit 1
fi

get_json "$TEMPLATES_URL/$TEMPLATE_UUID" > "$work_dir/current-default.json"
CURRENT_SETTINGS="$(get_json "$SETTINGS_URL")"

template_uuids=("$TEMPLATE_UUID" "${pool_uuids[0]}")
rendered_templates=("$work_dir/default.json" "$work_dir/leastload.json")
current_responses=("$work_dir/current-default.json" "$work_dir/current-pool.json")
printf 'null\n' > "$work_dir/v2raytun-rule.json"
if [[ "$compact_enabled" == "true" ]]; then
  compact_default_uuid="$(jq -r '.default.uuid' "$work_dir/compact-targets.json")"
  compact_auto_uuid="$(jq -r '.auto.uuid' "$work_dir/compact-targets.json")"
  compact_default_name="$(jq -r '.default.name' "$work_dir/compact-targets.json")"
  python3 "$script_dir/render-v2raytun.py" "$work_dir/v2raytun" \
    --template-name "$compact_default_name" --happ-routing "$HAPP_DEFAULT"
  cp -- "$work_dir/v2raytun/response-rule.json" "$work_dir/v2raytun-rule.json"
  get_json "$TEMPLATES_URL/$compact_default_uuid" > "$work_dir/current-compact-default.json"
  get_json "$TEMPLATES_URL/$compact_auto_uuid" > "$work_dir/current-compact-auto.json"
  template_uuids+=("$compact_default_uuid" "$compact_auto_uuid")
  rendered_templates+=("$work_dir/v2raytun/default.json" "$work_dir/v2raytun/leastload.json")
  current_responses+=("$work_dir/current-compact-default.json" "$work_dir/current-compact-auto.json")
fi
if (( $(printf '%s\n' "${template_uuids[@]}" | sort -u | wc -l) != ${#template_uuids[@]} )); then
  echo "All managed template UUIDs must be different" >&2
  exit 1
fi

for i in "${!template_uuids[@]}"; do
  # Preserve existing listener ports in both Auto variants. Empty compact
  # templates inherit DEFAULT's ports on their first sync.
  if (( i == 1 || i == 3 )); then
    jq -e --slurpfile current "${current_responses[$i]}" '
      (.inbounds // []) |= map(
        . as $inbound
        | [($current[0].response // $current[0]).templateJson.inbounds[]?
            | select(.tag == $inbound.tag and .protocol == $inbound.protocol)] as $matches
        | if ($matches | length) == 1 then .port = $matches[0].port
          elif ($matches | length) == 0 then .
          else error("ambiguous virtual-template inbound tags") end
      )
    ' "${rendered_templates[$i]}" > "$work_dir/ports-$i.json"
    mv -- "$work_dir/ports-$i.json" "${rendered_templates[$i]}"
  fi
  jq -ce '
    (.response // .).templateJson
    | if type == "object" then . else error("unexpected template content") end
  ' "${current_responses[$i]}" > "$work_dir/current-$i.json"
  jq -cn --arg uuid "${template_uuids[$i]}" --slurpfile tpl "${rendered_templates[$i]}" \
    '{uuid: $uuid, templateJson: $tpl[0]}' > "$work_dir/patch-$i.json"
  jq -cn --arg uuid "${template_uuids[$i]}" --slurpfile tpl "$work_dir/current-$i.json" \
    '{uuid: $uuid, templateJson: $tpl[0]}' > "$work_dir/rollback-$i.json"
done

SETTINGS_PATCH_PAYLOAD="$(
  jq -ce \
    --arg happ "$HAPP_DEFAULT" \
    --arg incy "$INCY_DEFAULT" \
    --slurpfile v2raytun "$work_dir/v2raytun-rule.json" \
    '
      (.response // .) as $settings
      | ($settings.responseRules.rules // []) as $rules
      | if $settings.responseRules == null then
          error("responseRules is null in subscription settings; create Response Rules in the panel first")
        elif ([$rules[] | select(.name == "HAPP")] | length) != 1 then
          error("expected exactly one HAPP response rule; found rule names: " + ([$rules[].name] | join(", ") | if . == "" then "<none>" else . end))
        elif ([$rules[] | select(.name == "INCY")] | length) != 1 then
          error("expected exactly one INCY response rule; found rule names: " + ([$rules[].name] | join(", ") | if . == "" then "<none>" else . end))
        elif $v2raytun[0] != null and ([$rules[] | select(.name == "V2RAYTUN")] | length) != 1 then
          error("expected exactly one V2RAYTUN response rule before enabling compact templates")
        elif ([
          $rules[]
          | select(.name == "HAPP")
          | .responseModifications.headers[]?
          | select(((.key // "") | ascii_downcase) == "routing")
        ] | length) != 1 then
          error("expected exactly one routing header in HAPP response rule; found headers: " + ([$rules[] | select(.name == "HAPP") | .responseModifications.headers[]? | .key] | join(", ") | if . == "" then "<none>" else . end))
        elif ([
          $rules[]
          | select(.name == "INCY")
          | .responseModifications.headers[]?
          | select(((.key // "") | ascii_downcase) == "routing")
        ] | length) != 1 then
          error("expected exactly one routing header in INCY response rule; found headers: " + ([$rules[] | select(.name == "INCY") | .responseModifications.headers[]? | .key] | join(", ") | if . == "" then "<none>" else . end))
        else
          {
            uuid: $settings.uuid,
            customResponseHeaders: (
              $settings.customResponseHeaders
              | if . == null then null
                else with_entries(select((.key | ascii_downcase) != "routing"))
                end
            ),
            responseRules: (
              $settings.responseRules
              | .rules |= map(
                  if .name == "HAPP" then
                    .responseModifications.headers |= map(
                      if ((.key // "") | ascii_downcase) == "routing"
                      then .value = $happ
                      else .
                      end
                    )
                  elif .name == "INCY" then
                    .responseModifications.headers |= map(
                      if ((.key // "") | ascii_downcase) == "routing"
                      then .value = $incy
                      else .
                      end
                    )
                  elif .name == "V2RAYTUN" and $v2raytun[0] != null then
                    .responseType = "XRAY_JSON"
                    | .responseModifications.subscriptionTemplate = $v2raytun[0].responseModifications.subscriptionTemplate
                    | .responseModifications.ignoreHostXrayJsonTemplate = false
                    | .responseModifications.applyHeadersToEnd = true
                    | .responseModifications.headers = (
                        [ .responseModifications.headers[]?
                          | select(((.key // "") | ascii_downcase) as $key
                            | $key != "routing" and $key != "geoipurl" and $key != "geositeurl") ]
                        + [$v2raytun[0].responseModifications.headers[]
                            | select(.key == "routing" or .key == "geoipurl" or .key == "geositeurl")]
                      )
                  else
                    .
                  end
                  | if $v2raytun[0] != null
                      and (.responseType == "XRAY_JSON" or .responseType == "XRAY_BASE64"
                        or .responseType == "MIHOMO" or .responseType == "CLASH"
                        or .responseType == "STASH" or .responseType == "SINGBOX") then
                      .responseModifications.excludeHostsByTags = (
                        ((.responseModifications.excludeHostsByTags // [])
                         + [if .name == "V2RAYTUN" then "V2RAYTUN_EXCLUDE" else "V2RAYTUN_ONLY" end]) | unique
                      )
                    else . end
                )
            )
          }
        end
    ' <<< "$CURRENT_SETTINGS"
)"

SETTINGS_ROLLBACK_PAYLOAD="$(
  jq -ce '
    (.response // .) as $settings
    | {
        uuid: $settings.uuid,
        customResponseHeaders: ($settings.customResponseHeaders // null),
        responseRules: $settings.responseRules
      }
  ' <<< "$CURRENT_SETTINGS"
)"

CURRENT_SETTINGS_STATE="$(
  jq -ce '
    (.response // .)
    | {
        customResponseHeaders: (.customResponseHeaders // null),
        responseRules: .responseRules
      }
  ' <<< "$CURRENT_SETTINGS"
)"

attempted_templates=0
settings_updated=false

patch_template() {
  curl -fsS -X PATCH -H "Accept: application/json" -H "Content-Type: application/json" \
    -H "$AUTH_HEADER" --data-binary "@$1" "$TEMPLATES_URL"
}

rollback() {
  local original_status=$?
  local rollback_failed=false
  local rollback_response
  local i
  trap - ERR
  set +e

  if [[ "$settings_updated" == "true" ]]; then
    if rollback_response="$(
      curl -fsS -X PATCH -H "Accept: application/json" -H "Content-Type: application/json" \
        -H "$AUTH_HEADER" --data "$SETTINGS_ROLLBACK_PAYLOAD" "$SETTINGS_URL"
    )" && jq -e --argjson expected "$CURRENT_SETTINGS_STATE" '
      ((.response // .) | {
        customResponseHeaders: (.customResponseHeaders // null), responseRules: .responseRules
      }) == $expected
    ' <<< "$rollback_response" > /dev/null; then
      echo "Rolled back Remnawave client routing headers" >&2
    else
      echo "Failed to roll back Remnawave client routing headers" >&2
      rollback_failed=true
    fi
  fi

  # Mark attempts before PATCH: the server can apply a write then lose its
  # response. Roll back in reverse order, including an uncertain write.
  for (( i=attempted_templates-1; i>=0; i-- )); do
    if rollback_response="$(patch_template "$work_dir/rollback-$i.json")" \
      && jq -e --slurpfile expected "$work_dir/current-$i.json" \
        '(.response // .).templateJson == $expected[0]' \
        <<< "$rollback_response" > /dev/null; then
      echo "Rolled back Remnawave XRAY_JSON template ${template_uuids[$i]}" >&2
    else
      echo "Failed to roll back Remnawave XRAY_JSON template ${template_uuids[$i]}" >&2
      rollback_failed=true
    fi
  done
  if [[ "$rollback_failed" == "true" ]]; then
    echo "Remnawave rollback incomplete; manual reconciliation required" >&2
  fi
  if (( original_status == 0 )); then original_status=1; fi
  exit "$original_status"
}

trap rollback ERR
for i in "${!template_uuids[@]}"; do
  attempted_templates=$((i+1))
  TEMPLATE_PATCH_RESPONSE="$(patch_template "$work_dir/patch-$i.json")"
  jq -e --slurpfile tpl "${rendered_templates[$i]}" \
    '(.response // .).templateJson == $tpl[0]' \
    <<< "$TEMPLATE_PATCH_RESPONSE" > /dev/null
done

settings_updated=true
SETTINGS_PATCH_RESPONSE="$(
  curl -fsS -X PATCH -H "Accept: application/json" -H "Content-Type: application/json" \
    -H "$AUTH_HEADER" --data "$SETTINGS_PATCH_PAYLOAD" "$SETTINGS_URL"
)"
jq -e --argjson expected "$SETTINGS_PATCH_PAYLOAD" '
  ((.response // .) | {
    customResponseHeaders: (.customResponseHeaders // null), responseRules: .responseRules
  }) == ($expected | {customResponseHeaders: (.customResponseHeaders // null), responseRules: .responseRules})
' <<< "$SETTINGS_PATCH_RESPONSE" > /dev/null

trap - ERR
echo "Remnawave ${#template_uuids[@]} XRAY_JSON templates and client routing headers updated (v2rayTun compact: $compact_enabled)"
