#!/usr/bin/env bash

set -euo pipefail

if (( $# != 2 )); then
  echo "Usage: $0 SOURCE_JSON OUTPUT_JSON" >&2
  exit 2
fi

source_json="$1"
output_json="$2"

GEOIP_REPO="losogudok/freemanvpn-geoip"
GEOSITE_REPO="losogudok/freemanvpn-geosite"

latest_tag() {
  git ls-remote --tags "https://github.com/${1}.git" \
    | awk '{print $2}' \
    | sed -E 's@refs/tags/@@; s@\^\{\}@@' \
    | grep -E '^[0-9]{12}$' \
    | sort -r \
    | sed -n '1p'
}

geoip_tag="$(latest_tag "$GEOIP_REPO")"
geosite_tag="$(latest_tag "$GEOSITE_REPO")"
[[ -n "$geoip_tag" && -n "$geosite_tag" ]]

work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT

git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$geoip_tag" \
  "https://github.com/${GEOIP_REPO}.git" "$work_dir/geoip"
git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$geosite_tag" \
  "https://github.com/${GEOSITE_REPO}.git" "$work_dir/geosite"

references="$work_dir/references.txt"
jq -r '
  ..
  | strings
  | select(test("^(geosite|geoip):[A-Za-z0-9_-]+$"))
' "$source_json" | sort -u > "$references"

lookup="$work_dir/lookup.json"
printf '{}\n' > "$lookup"

while IFS= read -r reference; do
  kind="${reference%%:*}"
  name="${reference#*:}"

  case "$kind" in
    geosite)
      data_file="$work_dir/geosite/data/$name"
      [[ -f "$data_file" ]] || {
        echo "Missing geosite source for $reference at tag $geosite_tag" >&2
        exit 1
      }
      values="$work_dir/values.json"
      awk '
        /^[[:space:]]*($|#)/ { next }
        {
          sub(/[[:space:]]+#.*$/, "")
          gsub(/^[[:space:]]+|[[:space:]]+$/, "")
          if ($0 == "") next
          if ($0 ~ /^(domain|full|keyword|regexp):/) print
          else print "domain:" $0
        }
      ' "$data_file" | jq -Rsc 'split("\n") | map(select(length > 0))' > "$values"
      ;;
    geoip)
      data_file="$work_dir/geoip/release/text/$name.txt"
      [[ -f "$data_file" ]] || {
        echo "Missing geoip source for $reference at tag $geoip_tag" >&2
        exit 1
      }
      values="$work_dir/values.json"
      awk '
        /^[[:space:]]*($|#)/ { next }
        {
          sub(/[[:space:]]+#.*$/, "")
          gsub(/^[[:space:]]+|[[:space:]]+$/, "")
          if ($0 != "") print
        }
      ' "$data_file" | jq -Rsc 'split("\n") | map(select(length > 0))' > "$values"
      ;;
    *)
      echo "Unsupported geodata reference: $reference" >&2
      exit 1
      ;;
  esac

  next_lookup="$work_dir/lookup.next.json"
  jq --arg key "$reference" --slurpfile values "$values" \
    '. + {($key): $values[0]}' "$lookup" > "$next_lookup"
  mv "$next_lookup" "$lookup"
done < "$references"

jq --slurpfile lookup "$lookup" '
  def expand_geodata($values):
    walk(
      if type == "array" then
        reduce .[] as $item (
          [];
          if ($item | type) == "string" and $values[$item] != null then
            . + $values[$item]
          else
            . + [$item]
          end
        )
      else
        .
      end
    );

  expand_geodata($lookup[0])
' "$source_json" > "$output_json"

if jq -e '.. | strings | select(test("^(geosite|geoip):[A-Za-z0-9_-]+$"))' \
  "$output_json" >/dev/null; then
  echo "Rendered Xray JSON still contains geodata references" >&2
  exit 1
fi

jq -e 'type == "object"' "$output_json" >/dev/null
