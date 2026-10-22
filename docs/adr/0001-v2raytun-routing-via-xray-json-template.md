# v2RayTun routing via the XRAY_JSON template

**Updated 2026-10-21:** the assumption that v2RayTun cannot receive geo-file
URLs in subscription headers is outdated. Android **5.26.83** added
`geoipurl` and `geositeurl` ([release notes](https://github.com/LXST-CODE/v2RayTun/releases/tag/android-v5.26.83)).
Compatible clients can use the [compact template bundle](../runbooks/v2raytun-compact-json.md)
with short geo references and download the files separately. The workflow
now automatically discovers and publishes the separate `V2RayTun Compact`
and `V2RayTun Auto Compact` templates when both exist, together with scoped
geo URL headers. Other platforms and older versions need separate verification.
The shared templates retain the expanded policy for other clients.

v2RayTun must receive the same routing as Happ (rules + DNS), but its native `routing` subscription header carries only an Xray RoutingObject — no DNS settings. The original implementation replaced the unused stub XRAY_JSON subscription template with the full FreemanVPN client configuration (DNS, routing rules, current-host outbound injection) and added a response rule serving XRAY_JSON to v2RayTun User-Agents. Before publishing the shared template to Remnawave, the synchronization workflow expands every FreemanVPN `geosite:` and `geoip:` reference into ordinary Xray domain and CIDR entries. WHITELIST and JSONSUB profiles remain source configs for manual import and therefore still require the FreemanVPN geo files to be configured in the app.

## Considered Options

- v2RayTun `routing` header — rejected: no DNS settings, partial parity only.
- App-specific `Geoipurl` / `Geositeurl` JSON fields — rejected: they belong to the Happ/INCY routing formats. v2RayTun Android 5.26.83 now supports separate lower-case `geoipurl` / `geositeurl` HTTP headers; use those for compact templates.
- Xray's scheduled `geodata` downloader — rejected for bootstrap: Xray builds routing before the scheduled downloader runs, so a config referencing FreemanVPN-only categories cannot start with v2RayTun's bundled standard files.
- `injectHosts.sameTagAsRecipient` — rejected for the current topology: the panel has no hidden hosts or host tags, so the selector produces no `proxy` outbound.
- Dedicated second template — rejected: the stub template had no consumers (only base64 is served to Happ), so replacing it in place leaves nothing to protect.

## Consequences

- Any future JSON-capable client (Streisand, V2Box, v2rayNG) pointed at XRAY_JSON will receive the full routing too, not a stub.
- `addVirtualHostAsOutbound` gives each generated config a `proxy` outbound for its current recipient host without requiring hidden hosts or tags.
- The Remnawave template is larger because it embeds the domain and CIDR data, but it has no runtime dependency on client geo files.
- Routing Synchronization must update the template together with the HAPP/INCY payloads — all targets or none.
