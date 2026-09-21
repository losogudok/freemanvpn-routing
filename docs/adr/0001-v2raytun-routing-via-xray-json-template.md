# v2RayTun routing via the XRAY_JSON template

v2RayTun must receive the same routing as Happ (rules + DNS), but its native `routing` subscription header carries only an Xray RoutingObject — no DNS settings — and no delivery format can carry geo-file URLs, so the custom FreemanVPN geoip/geosite remain a manual per-device app setting. We replace the unused stub XRAY_JSON subscription template with the full FreemanVPN client configuration (DNS, routing rules, host injection) and add a response rule serving XRAY_JSON to v2RayTun User-Agents; Happ keeps its base64 response plus routing header. WHITELIST and JSONSUB profiles ship as full Xray JSON configs for manual import.

## Considered Options

- v2RayTun `routing` header — rejected: no DNS settings, partial parity only.
- Dedicated second template — rejected: the stub template had no consumers (only base64 is served to Happ), so replacing it in place leaves nothing to protect.

## Consequences

- Any future JSON-capable client (Streisand, V2Box, v2rayNG) pointed at XRAY_JSON will receive the full routing too, not a stub.
- Routing Synchronization must update the template together with the HAPP/INCY payloads — all targets or none.
