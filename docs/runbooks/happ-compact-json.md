# Happ: compact Xray JSON with FreemanVPN DAT

For shared client deployments, use [the consolidation plan](shared-client-routing.md).
Reuse the same compact DEFAULT/Auto/RU templates across compatible clients;
do not create another client-named copy. The separate-client setup below
is retained as the original rollout procedure.

Personal panel setup was applied on 2026-11-21. See the
[device acceptance report](happ-compact-acceptance-2026-11-21.md) for verified
behavior and remaining limits.

The rollout is personal until the Android acceptance below passes. General
`HAPP` delivery stays Base64. The three compact policies come from
`XRAY_JSON/DEFAULT.JSON`, DEFAULT plus the existing Auto pool settings, and
`XRAY_JSON/RUSSIAN_IP.JSON`. The generator preserves DNS, FakeDNS, sniffing,
listeners and route order. Only Auto's proxy destinations use the balancer.

## Build and checks

`build-xray` selects both numeric geo release tags once. The same downloaded
DAT files, SHA256 values and pinned URLs are used to validate all three
compact templates, the expanded policies, and the Happ routing profile.
No `Geoipurl` or `Geositeurl` fields are injected into Xray JSON.

```sh
python3 scripts/render-happ.py dist/xray-json/happ \
  --build-info dist/xray-json/russian-ip/build-info.json
python3 scripts/check-happ.py dist/xray-json/happ \
  --assets /path/to/downloaded-dat --xray /path/to/xray
```

The profile derives Tunnel DNS settings from `HAPP/JSONSUB.JSON`, uses
`UseChunkFiles: "false"`, and supplies no shared direct/proxy/block lists.
Each JSON keeps its own rules, including RU's special DNS policy.
The bundle contains `default.json`, `leastload.json`, `russian-ip.json`,
`routing.json`, `routing.deeplink`, and `build-info.json` under `happ/`.
All files are covered by the outer `SHA256SUMS`. The profile name stays
`FreemanVPN JSON` so Happ updates the existing entity by name; `LastUpdated`
uses the newest geo release time in Unix seconds.

The workflow's `update` job consumes that artifact rather than looking up
new geo tags for Happ. `HAPP/JSONSUB.JSON` and `.DEEPLINK` are refreshed
from it; DEFAULT and WHITELIST keep their policies and use the same geo URLs.
INCY's existing update logic remains independent.

[Happ's JSON subscription contract](https://github.com/HappDev/happ_su/blob/main/dev-docs/routing.md)
requires the routing profile to be bundled with JSON; rules remain in JSON.
DAT URLs belong in that profile, as described in the
[link parameters](https://github.com/HappDev/happ_su/blob/main/dev-docs/examples-of-links-and-parameters.md).

## Personal panel setup

Read current Response Rules, Host assignments and template names before the
first setup. Save their full contents privately for rollback. Never store
subscription identifiers or credentials in this repository.

Create three separate XRAY_JSON templates and configure these repository
variables (all three are required together):

| Variable | Suggested template name |
| --- | --- |
| `REMNAWAVE_HAPP_TEMPLATE_UUID` | `Happ Compact` |
| `REMNAWAVE_HAPP_AUTO_TEMPLATE_UUID` | `Happ Auto Compact` |
| `REMNAWAVE_HAPP_RU_TEMPLATE_UUID` | `Happ Russian IP Compact` |

Create an Auto Host on the existing virtual inbound, with its new compact
Auto template, and an RU Host on the existing RU inbound with its new compact
RU template. Tag both **only `HAPP_ONLY`**. Do not give these clones the
legacy Auto exclusion tags or `RUSSIAN_IP` tag. Keep existing Host assignments
for other clients. Ordinary server Hosts need no changes: the personal rule
selects `Happ Compact` as its default template.

The existing `HAPP_PRIVATE_RUSSIAN_IP` rule must be enabled, precede `HAPP`,
and use AND conditions matching Happ's user-agent and exactly one personal
`x-remnawave-injected-short-uuid`. Synchronization validates that scope;
it preserves the conditions and position. It sets JSON delivery, the compact
default, `ignoreHostXrayJsonTemplate: false`, and the bundled routing header.
It excludes legacy Auto, the v2RayTun-only Auto and the old RU entry.
All other non-browser rules exclude `HAPP_ONLY`, isolating the new entries.
The script never creates Hosts or templates or broadens the personal scope.

```sh
# Existing API/token, HAPP_DEFAULT, INCY_DEFAULT and RUNNER_TEMP are also required.
bash scripts/sync-remnawave-routing.sh dist/xray-json
```

The synchronizer requires a validated bundle for Happ, resolves every target
before PATCH, and includes all three templates in the existing transaction.
PATCH responses and GET readbacks verify template content and subscription
settings. An uncertain write, mismatch or readback failure rolls back settings
and attempted templates; failed rollback is reported explicitly. Existing
Auto listener ports are preserved. Host creation/assignment is a separate
one-time operation and must be reverted using the saved Host snapshot if
personal acceptance fails.

## Android acceptance and limits

Current local evidence (2026-11-21): generation tests and API fixture checks
pass; all three templates parse in Xray 26.11.9 with GeoIP `202611211053`
and Geosite `202611071812`. The exact workflow build step also passes
with the pinned official Xray 26.11.9 binary, including 25 compact and 25
expanded RU routing checks. Both review axes found no confirmed code defects;
50 unit/integration tests and actionlint pass. This is validation of compact categories and
configuration syntax, not evidence of a successful mobile connection.

Pending production/device acceptance:

1. Capture pre-change personal/general Happ responses and other client
   responses. Verify the general rule remains Base64 after personal setup.
2. Freshly import the personal subscription and update its existing import.
   Confirm both DAT downloads and active categories without relying on old
   cache. Record app/core versions and resulting payload sizes.
3. Connect ordinary VLESS/Reality and XHTTP entries. Verify direct/proxy/block,
   DNS, FakeDNS and sniffing through the actual phone tunnel.
4. Connect Auto. Fail the selected endpoint only for the test, verify new
   connections switch after health checks. Fail the whole test pool, verify
   proxy traffic blocks and intended direct routes still work; restore it.
5. Connect RU. Verify RU destinations use proxy, other destinations direct,
   and RU DNS uses its JSON policy. Distinguish route logs from service
   accessibility and from a real test on a foreign network. A shared RU bridge
   inbound may forward proxy destinations to Germany; the compact client
   cannot fix its server routing. See [Russian IP](russian-ip.md).
6. Ping real profiles both connected and disconnected. Record numeric results
   and whether `Ping checking` actually finishes, separately. A small prior
   SOCKS experiment produced numbers but a stuck connected indicator; that
   is not proof that real-profile ping or the UI defect is fixed.
7. Restore the previous panel snapshot on failure. General rollout needs
   successful personal acceptance; it is not enabled by this implementation.
