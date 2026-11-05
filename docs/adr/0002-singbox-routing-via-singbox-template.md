# Sing-box routing via the Default Singbox template

**2026-11-05**

xray-based clients receive the FreemanVPN DEFAULT policy from
`XRAY_JSON/DEFAULT.JSON`: block telemetry, torrent trackers and ads, proxy
YouTube/Telegram/GitHub/Google Play/Twitch ads, direct RU/BY, Apple, gaming and
selected services, then proxy the rest. The policy depends on the custom
`freemanvpn-geosite` and `freemanvpn-geoip` categories.

sing-box cannot consume those projects' `.dat` files. Geosite was deprecated in
sing-box 1.8 and removed in 1.12; the supported format is a binary `.srs`
rule-set referenced from `route.rule_set`. Both geo repositories already build
and publish `sing-box/*.srs` on their `release` branches.

Remnawave has a dedicated `SINGBOX` subscription-template type. Its generator
targets sing-box 1.13.x, appends the subscription's proxy outbounds, and fills
every `selector` and `urltest` outbound from the template with those proxy
tags. This makes a full routing template possible without a separate
client-side payload.

## Decision

- Maintain `SINGBOX/DEFAULT.JSON` as a separate, reviewed sing-box template
  rather than generating it from the Xray JSON. A parity test compares the
  block/proxy/direct category lists, direct-IP categories, DNS split and static
  hosts with `XRAY_JSON/DEFAULT.JSON`.
- Serve the template through the existing Remnawave template named
  `Default Singbox` (`templateType: SINGBOX`). The synchronization overwrites
  that template's JSON; `REMNAWAVE_SINGBOX_TEMPLATE_UUID` can pin a different
  UUID. An ambiguous match or a pin that does not match aborts before any
  write. A panel without the template skips sing-box during rollout unless a
  `SINGBOX` response rule is already present, which is an error.
- Add a `SINGBOX` response rule after `THRONE` and before the Base64 fallback.
  It matches the official sing-box family and Karing with the case-insensitive
  regex `^sfa|sfi|sfm|sft|karing|sing-box|singbox`. Throne remains on
  `XRAY_JSON`.
- Reference the geo repositories' `.srs` artifacts as remote rule sets. Pin
  every URL to the `release` branch commit
  (`.../freemanvpn-geosite@<commit>/sing-box/<category>.srs`); the update
  workflow advances all pins together and commits the template. Rule sets are
  downloaded through `direct` and cached by the client.
- Keep only the DEFAULT profile. Target sing-box 1.13.x and provide generic TUN
  plus mixed inbounds.
- Include an `Auto` `urltest` group and make it the selector's default. The
  Remnawave generator fills it with every proxy; users can still choose an
  individual server.
- Use IPv4-only behavior: no IPv6 TUN address, `ipv4_only` DNS, an empty
  NOERROR response for AAAA queries, and a route reject for `::/0`.
- Use fake-IP `198.18.0.0/15`; send direct-category queries to Yandex DoH and
  remote queries to Google DoH through the proxy. Keep the static
  `lkfl2.nalog.ru` and `lknpd.nalog.ru` hosts.
- Do not publish a manual-import profile. The file is the source and the exact
  Remnawave payload; manual imports are unsupported.

## Considered Options

- **Generate sing-box from `XRAY_JSON/DEFAULT.JSON`** — rejected: the Xray
  policy is simple enough to mirror, but the sing-box DNS, fake-IP, outbound
  and rule-set scaffolding is materially different. A dedicated template with
  a parity test is easier to review and evolve.
- **Expand domains and CIDRs inline** — rejected: it would repeat the current
  Xray template's multi-megabyte payload in every sing-box subscription and
  make byte-level review impractical.
- **Use `.dat` files** — rejected: sing-box 1.12 removed geosite and never
  consumed the Xray geodata format.
- **Rolling `release` URLs** — rejected: geo changes would bypass the routing
  transaction. Pinned commits keep the payload reproducible.
- **A separate manual profile** — rejected: sing-box has no mechanism to merge
  the user's active server into a raw config, and a second artifact would drift.
- **No `urltest`** — rejected: sing-box can select a working server natively,
  and Auto-first matches the behaviour users expect from the other clients.
- **Dual-stack** — rejected for the first version: IPv6 fake-IP and split DNS
  add complexity without a requirement.

## Consequences

- The `Default Singbox` template, when present, is overwritten on every
  routing synchronization. Export the current template before the first sync;
  the workflow's rollback only protects failed writes, not an intentional
  replacement.
- Any sing-box subscriber on the panel receives the new routing. The response
  rule is scoped by User-Agent, but the template itself is shared.
- Pinned release commits must stay reachable. The workflow re-pins on every geo
  release; if the geo repositories garbage-collect old commits, mirroring the
  `.srs` files becomes necessary.
- Remote rule sets are a runtime dependency. `download_detour: direct` keeps
  startup independent of the proxy, but the client must reach jsDelivr once and
  retain its rule-set cache.
- The parity test must be updated whenever the Xray DEFAULT categories or DNS
  split change.
- sing-box 1.13.x is the compatibility floor; older clients may reject the
  typed DNS servers or rule-set fields.
