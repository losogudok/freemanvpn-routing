# v2RayTun routing via the XRAY_JSON template

v2RayTun must receive the same routing as Happ (rules + DNS), but its native `routing` subscription header carries only an Xray RoutingObject — no DNS settings — and v2RayTun has no supported subscription header for geo-file URLs. We replace the unused stub XRAY_JSON subscription template with the full FreemanVPN client configuration (DNS, routing rules, host injection) and add a response rule serving XRAY_JSON to v2RayTun User-Agents; Happ keeps its base64 response plus routing header. Before publishing the template to Remnawave, the synchronization workflow expands every FreemanVPN `geosite:` and `geoip:` reference into ordinary Xray domain and CIDR entries. WHITELIST and JSONSUB profiles remain source configs for manual import and therefore still require the FreemanVPN geo files to be configured in the app.

## Considered Options

- v2RayTun `routing` header — rejected: no DNS settings, partial parity only.
- App-specific `Geoipurl` / `Geositeurl` fields — rejected: they belong to the Happ/INCY routing formats and are not supported by v2RayTun's Xray JSON subscription format.
- Xray's scheduled `geodata` downloader — rejected for bootstrap: Xray builds routing before the scheduled downloader runs, so a config referencing FreemanVPN-only categories cannot start with v2RayTun's bundled standard files.
- Dedicated second template — rejected: the stub template had no consumers (only base64 is served to Happ), so replacing it in place leaves nothing to protect.

## Consequences

- Any future JSON-capable client (Streisand, V2Box, v2rayNG) pointed at XRAY_JSON will receive the full routing too, not a stub.
- The Remnawave template is larger because it embeds the domain and CIDR data, but it has no runtime dependency on client geo files.
- Routing Synchronization must update the template together with the HAPP/INCY payloads — all targets or none.
