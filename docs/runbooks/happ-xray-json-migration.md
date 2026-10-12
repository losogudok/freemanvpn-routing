# Happ: migration to the virtual-host Xray JSON subscription

Verified on 2026-10-13 against the supplied live test subscription and
[response_rules.json](../../response_rules.json). No panel settings, host
settings, or running Happ connection were changed. Customer subscription
bodies and credentials are kept outside the repository in a private
temporary directory.

## Result

The live JSON template is valid and its virtual entry connects successfully
with Happ's installed Xray core **26.9.9**. The Happ response rule currently
returns **XRAY_BASE64**, so Happ does not yet receive the multi-outbound
virtual configuration. A successful core check does not establish that an
existing Happ subscription migrates correctly on every platform.

The live JSON response, requested using the existing v2rayTun response rule,
contains eight configurations. Every configuration passed
`xray run -test`, every routing outbound/balancer reference resolved, and
the panel removed the `remnawave` directives. The virtual entry contains
exactly five VLESS outbounds:

| Tag | Address |
| --- | --- |
| `auto-proxy` | `xuyandex.party` |
| `auto-proxy-2` | `host3.lookmaimanengineer.cc` |
| `auto-proxy-3` | `forum.mmorpg.uk` |
| `auto-proxy-4` | `chat.mmorpg.uk` |
| `auto-proxy-5` | `news.freemanbot.uk` |

The virtual entry's DNS, routing, inbounds, FakeDNS pool, and burst observatory
exactly match [LEASTLOAD.settings.json](../../XRAY_JSON/LEASTLOAD.settings.json).
Despite the file and tag names, the strategy is **leastPing**. Both selectors
match the complete `auto-proxy` prefix, and `fallbackTag: block` is defined.

The supplied template's expanded domain/IP rules and DNS match a freshly
rendered DEFAULT. The live Happ header also matches DEFAULT's domain/IP
categories, route order intent, DNS endpoints, static DNS hosts, and FakeDNS
setting. The supplied template's HTTP port is `10810`; DEFAULT's is `10809`.

## Connection checks

An isolated process using `/opt/happ/bin/core/xray` and the live virtual-entry
configuration was started with a temporary SOCKS port on loopback, then
terminated. The existing Happ session was left running.

| Check | Result |
| --- | --- |
| YouTube `generate_204` | HTTP 204 via `auto-proxy-4` |
| GitHub | HTTP 200 via `auto-proxy-4` |
| Yandex `ya.ru` | HTTP 302 via `direct` |
| UDP query into Xray's DNS outbound for `www.youtube.com` | Successful response, 8 answers |
| UDP query into Xray's DNS outbound for `ya.ru` | Successful response, 3 answers |
| Static DNS host `lkfl2.nalog.ru` | Successful response containing `213.24.64.175` |
| `vortex.data.microsoft.com` | Blocked; access log selected `block` |

The DNS check added a temporary loopback DNS inbound and DNS outbound to
exercise Xray's resolver. These checks establish core behavior on this
workstation's current network. They do not establish Happ UI import behavior,
mobile tunnel behavior, physical DNS leakage, or failover after an outage.

## Proposed response rules

[response-rules.happ-xray-json.candidate.json](response-rules.happ-xray-json.candidate.json)
is a reviewable copy of the supplied rules with exactly one change:
the `HAPP` rule's `responseType` becomes `XRAY_JSON`. Its conditions,
position, routing header, and all other rules remain identical.
This candidate has **not** been imported into Remnawave.

Keep the existing routing header for the first migration test. Happ's
[current JSON-subscription documentation](https://www.happ.su/main/dev-docs/routing)
describes routing profiles as tunnel-DNS metadata rather than an injection
into the provider's JSON. Preserving the header is intended to retain the
existing Google tunnel DNS while the JSON retains its split DNS and balancer.
Verify this behavior in the target Happ versions before general rollout.

Do not assume that removing the header preserves DNS behavior. Happ's
[DNS-from-JSON option](https://www.happ.su/main/dev-docs/app-management)
requires JSON, no routing profile, and its enabled toggle. It takes the first
DNS server; this template lists Yandex first. Its documented DoH handling
also depends on `dns.hosts` and differs across platforms. Header removal is
a separate change requiring its own tunnel-DNS test.

The existing routing header still references external geo files. Keeping it
does not eliminate Happ's metadata/geo-download dependency. If eliminating
that dependency is required, test a minimal tunnel-DNS profile separately;
do not change the response format and DNS metadata simultaneously.

The synchronization workflow writes the DEFAULT routing header into the
rule named `HAPP`. An `off` command or custom profile placed there would be
replaced by the next sync. This proposed candidate retains the DEFAULT
header and is compatible with that behavior. The workflow now synchronizes
the default and virtual templates using one rendered geodata snapshot,
preserves the virtual template's local ports, and rolls both templates and
the headers back on failure. It does not change the HAPP response type.

## Renderer repair

The original least-load renderer merged the complete settings file over
freshly rendered DEFAULT. Because the settings file now contains a full
snapshot, it discarded new DNS, inbound, and routing policy changes.

The renderer now imports only `remnawave`, `burstObservatory`, and
`routing.balancers` from that file, then redirects DEFAULT's proxy rules
to the balancer. A regression using a new direct-domain rule and static
DNS host failed before the repair and passed afterward. DNS, inbounds,
FakeDNS, and both proxy-to-balancer rewrites were also checked. The supplied
settings file was left byte-for-byte unchanged.

## Rollout gate

1. Record supported Happ app/platform versions. Only the installed core
   26.9.9 has been exercised with the live generated response. The source
   template also parsed with standalone Xray 26.3.27.
2. Save the active rules/template, then use an isolated test subscription
   scope or staging environment for the candidate. Importing the supplied
   candidate globally changes the response for every matching Happ request.
3. Refresh an **existing** Happ subscription using its existing URL. Confirm
   the response is a JSON array, the virtual entry appears, and existing
   single-server entries remain available. Also test a clean import.
4. Select the virtual entry and reconnect. Inspect the effective runtime:
   injected outbounds, leastPing, burst observatory, block fallback, split
   DNS, and sniffing must survive Happ processing. Confirm tunnel DNS and
   FakeDNS handling on each platform; do not infer them from core parsing.
5. Repeat proxy/direct/block and DNS checks inside the actual Happ tunnel.
   Verify physical-interface DNS traffic when checking for DNS leakage.
6. On the test device, make the selected endpoint unreachable and verify
   **new** connections use another member after health results change.
   Make all pool members unreachable and verify proxy destinations fail
   while intentional direct routes still work. Restore reachability.
7. Restore the saved response rules if refresh, reconnect, DNS, or failover
   checks fail. Verify an existing subscription can refresh back to base64.

The core performs an initial health check immediately, but connections made
before a successful observation can hit the block fallback. Later detection
is periodic, and the three retained samples can delay exclusion. Existing
connections are not moved between servers. See the
[26.9.9 burst scheduler](https://github.com/XTLS/Xray-core/blob/v26.9.9/app/observatory/burst/healthping.go)
and [leastPing selection](https://github.com/XTLS/Xray-core/blob/v26.9.9/app/router/strategy_leastping.go).
