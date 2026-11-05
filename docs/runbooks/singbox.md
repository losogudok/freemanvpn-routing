# Sing-box routing rollout

The sing-box routing is served by Remnawave's `SINGBOX` subscription template
named **`Default Singbox`**. The synchronization **overwrites** that template
with `SINGBOX/DEFAULT.JSON`; it does not create the template or the response
rule. This runbook covers the one-time panel setup, the first sync, verification
and rollback.

## Prerequisites

- Remnawave panel with a `SINGBOX` template named `Default Singbox`.
  Remnawave ships this template by default; if it is missing, create it.
- `REMNAWAVE_API_BASE_URL` and `REMNAWAVE_TOKEN` configured for the workflow.
- sing-box 1.13.x on the test device or workstation.
- The optional repository variable `REMNAWAVE_SINGBOX_TEMPLATE_UUID` if the
  template is renamed or more than one template matches the name.

## 1. Back up the current template

The sync replaces the whole `templateJson`, so export the current content first.
Use the template UUID from the panel:

```sh
curl -fsS -H "Authorization: Bearer $REMNAWAVE_TOKEN" \
  "${REMNAWAVE_API_BASE_URL%/}/subscription-templates/$SINGBOX_TEMPLATE_UUID" \
  > default-singbox.backup.json
```

Keep this file until the rollout has been verified. The workflow rollback only
restores writes that fail during synchronization; it does not undo a successful
overwrite.

## 2. Create the SINGBOX response rule

Open **Response Rules** in the panel and insert a rule named `SINGBOX` after
`THRONE` and before the Base64 fallback:

```json
{
  "name": "SINGBOX",
  "description": "Allow sing-box clients to get the FreemanVPN routing template",
  "enabled": true,
  "operator": "AND",
  "conditions": [
    {
      "headerName": "user-agent",
      "operator": "REGEX",
      "value": "^sfa|sfi|sfm|sft|karing|sing-box|singbox",
      "caseSensitive": false
    }
  ],
  "responseType": "SINGBOX",
  "responseModifications": {
    "subscriptionTemplate": "Default Singbox",
    "excludeHostsByTags": [
      "V2RAYTUN_ONLY"
    ]
  }
}
```

Why this order and regex:

- The fallback rule has no conditions and matches everything, so the sing-box
  rule must come before it.
- `THRONE` remains on `XRAY_JSON`; keeping it first preserves the existing
  client format.
- The regex covers `SFA/`, `SFI/`, `SFM/`, `SFT/`, Karing and the core's
  `sing-box` / `singbox` User-Agent strings. Karing may put its name later in
  the User-Agent, so `karing` is intentionally not anchored at the start.
- `V2RAYTUN_ONLY` excludes virtual hosts that are reserved for v2RayTun. The
  synchronization also adds this tag when compact v2RayTun templates are
  enabled.

The sync verifies that exactly one `SINGBOX` rule exists, that it is after
`THRONE`, and that it is before the fallback. It fails before any PATCH if the
rule is missing, duplicated or misordered; it does not create the rule.

## 3. Run the synchronization

Run **Update Routing Configs** from GitHub Actions with `force_sync: true` once.
The workflow:

1. Re-pins every `.srs` URL in `SINGBOX/DEFAULT.JSON` to the current
   `release` commits of `freemanvpn-geoip` and `freemanvpn-geosite`.
2. Verifies each rule-set URL.
3. Runs the parity, URL and sync tests.
4. Patches the `Default Singbox` template and the `SINGBOX` response rule in the
   same transaction as the HAPP/INCY/XRAY_JSON updates.
5. Rolls back every attempted template and the settings payload if a write or
   verification fails.

If `Default Singbox` is absent, the workflow skips sing-box and leaves the
response rule untouched. If the rule exists but the template is missing, the
sync fails before writing.

## 4. Verify

Check the generated subscription with a sing-box User-Agent:

```sh
curl -fsS \
  -A "SFA/1.0 (1; sing-box 1.13.12)" \
  -H "Accept: application/json" \
  "$SUBSCRIPTION_URL" > /tmp/freemanvpn-singbox.json

sing-box check -c /tmp/freemanvpn-singbox.json
```

The response should contain:

- `outbounds` with `Auto` (urltest), `proxy` (selector), `direct`, `block`, and
  one outbound per subscription server.
- `proxy.outbounds` containing `Auto` first and every server; `proxy.default`
  equal to `Auto`.
- `route.final` equal to `proxy`.
- Remote `route.rule_set` entries pinned to a commit SHA under
  `cdn.jsdelivr.net/gh/losogudok/freemanvpn-*@<sha>/sing-box/`.
- The fake-IP server, Yandex/Google DNS servers, and static `nalog.ru` hosts.

On a real client, verify:

- Auto is selected by default, and a specific server can still be selected.
- RU/BY services, Apple, gaming services, Twitch and Spotify go direct.
- YouTube, Telegram, GitHub, Google Play and Twitch ads go through the proxy.
- Ad, Windows telemetry and torrent-domain lists are blocked.
- `lkfl2.nalog.ru` and `lknpd.nalog.ru` resolve to their static addresses.
- IPv6-only connections are rejected and AAAA queries return no records.
- Rule-set downloads succeed on a fresh install and survive a restart from the
  client cache.

## 5. Rollback

If the routing must be reverted, restore the template exported in step 1:

```sh
jq -n --arg uuid "$SINGBOX_TEMPLATE_UUID" \
  --slurpfile backup default-singbox.backup.json \
  '{uuid: $uuid,
    templateJson: (($backup[0].response // $backup[0]).templateJson)}' \
  > singbox-rollback.json

curl -fsS -X PATCH \
  -H "Authorization: Bearer $REMNAWAVE_TOKEN" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  --data-binary @singbox-rollback.json \
  "${REMNAWAVE_API_BASE_URL%/}/subscription-templates"
```

Restore the response rule in the panel if it was changed. Do not point the
workflow at a template that must not be overwritten.

## Notes

- Manual import of `SINGBOX/DEFAULT.JSON` is not supported. The file is a
  Remnawave template with empty `Auto` and `proxy` outbound lists; the panel
  fills them from the subscription.
- Do not edit pinned `.srs` commit SHAs by hand. Run the update workflow; it
  advances all pins together and commits the result.
- The synchronization targets the exact template name unless
  `REMNAWAVE_SINGBOX_TEMPLATE_UUID` is set. An ambiguous name aborts before any
  write.
- Do not name a subscription host `Auto`, `proxy`, `direct` or `block`; those
  tags are reserved by the template and a duplicate tag makes the generated
  config invalid.
- sing-box 1.13.x is the compatibility floor. Older clients may reject the
  typed DNS servers or rule-set fields.
