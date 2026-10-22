# Compact v2RayTun subscriptions

v2RayTun Android **5.26.83** added `geoipurl` and `geositeurl` subscription
headers ([official release notes](https://github.com/LXST-CODE/v2RayTun/releases/tag/android-v5.26.83)).
These let the client fetch the FreemanVPN geo files instead of repeating
expanded domain and CIDR lists in every profile. Support on older Android,
iOS, macOS, and Windows versions must be verified separately.

The [`routing` header](https://docs.v2raytun.com/overview/supported-headers#routing)
contains a base64 routing profile. It does not carry the geo-file URLs, but
Android 5.26.83 **requires it to be non-empty to retain those URLs**. The bundle
therefore sends a small native routing profile with a stable ID, name, and
empty rules/balancers. Raw JSON profiles retain their own policy: ordinary
profiles route to `proxy`, while Auto routes to `auto-leastload`. DNS stays
in the JSON, including its short `geosite:` domain selectors.

## Generate

```sh
python3 scripts/render-v2raytun.py /tmp/freemanvpn-v2raytun
```

The command produces three credential-free artifacts:

- `default.json`: the source DEFAULT policy with unexpanded geo references.
- `leastload.json`: the same policy with Auto host injection, probes, and
  proxy-to-balancer rewrites from the existing leastload renderer.
- `response-rule.json`: the existing V2RAYTUN rule with the small `routing`
  metadata profile and `geoipurl` / `geositeurl` copied from
  `HAPP/DEFAULT.JSON`, selecting `V2RayTun Compact`.
  Set `--template-name NAME` if the panel template has another name.

Geo URLs use the same pinned versions as HAPP. Regenerate the bundle after
policy or geo-version updates for manual imports. The automated sync passes
the current build's HAPP payload to `--happ-routing`, so it uses the current
geo URLs even if the checkout predates the update job's generated commit.
Do not add `Geoipurl`/`Geositeurl` fields to
the Xray configuration itself; the lower-case HTTP headers belong to the
subscription response.

## Automated publication

Create these two **XRAY_JSON** subscription templates in Remnawave:

- `V2RayTun Compact`
- `V2RayTun Auto Compact`

Their names are enough: the synchronization script discovers them and
populates their JSON automatically, including empty initial objects. No new
UUID variables are required when the names match exactly. If you rename them,
set `REMNAWAVE_V2RAYTUN_TEMPLATE_UUID` and
`REMNAWAVE_V2RAYTUN_AUTO_TEMPLATE_UUID` in the GitHub repository variables.
Keep the existing shared default and leastload UUID variables unchanged.

The **Update Routing Configs** workflow builds both compact templates and
publishes them with the two shared expanded templates. It updates the live
`V2RAYTUN` response rule to select the compact default and sends both geo URL
headers plus the required routing metadata. Existing rule conditions, other
headers, and unrelated options are preserved; an old v2RayTun `routing`
header is replaced by the empty metadata profile. The workflow also updates the HAPP/INCY routing
headers as before. All four templates and the client headers are one
transaction, with verification and rollback of attempted writes on failure.

An incomplete pair of compact templates, ambiguous names, invalid UUIDs, or
a missing/duplicate live `V2RAYTUN` rule aborts before any writes. Panels with
neither compact template nor compact UUID settings retain the legacy sync.

After these code changes are on `main`, run **Update Routing Configs** with
`force_sync: true` once to populate the new templates. Subsequent routing
changes rebuild and publish them automatically. The separate manual renderer
remains available for inspection; it does not contact Remnawave.

## Auto host assignments and client visibility

Remnawave's [per-host template assignment takes precedence](https://docs.rw/learn-en/routing-rules/)
unless `ignoreHostXrayJsonTemplate` is true. The generated rule deliberately
keeps it false so selecting Auto does not turn it into an ordinary server.
To make the entire v2RayTun subscription compact:

1. Create a separate enabled, visible Auto host, using the existing Auto
   host's address/port and an inbound accessible to the same users.
2. Assign its advanced Xray JSON template to **V2RayTun Auto Compact** and
   set its **host tag** to `V2RAYTUN_ONLY`.
3. Keep the existing Auto host assigned to the shared expanded template and
   set its **host tag** to `V2RAYTUN_EXCLUDE`.

The sync adds `V2RAYTUN_EXCLUDE` to the V2RAYTUN rule's `excludeHostsByTags`.
It adds `V2RAYTUN_ONLY` to the other subscription response rules' exclusions,
preserving existing exclusions such as `INCY_EXCLUDE`. v2RayTun sees the new
Auto host; other clients keep the original. The pool member host tag
`FREEMAN_AUTO_LEASTLOAD` stays on the real injected servers, never either
virtual Auto host. If existing virtual host tags are used elsewhere, resolve
those assignments before changing them. Host creation, tags, and template
assignment are panel setup; the workflow does not change hosts.

Do not point the shared synchronization UUIDs at these compact templates:
the shared sync expands their policy again. New compact templates inherit
DEFAULT's ports (`10808` SOCKS, `10809` HTTP); subsequent syncs preserve the
compact Auto template's configured ports, separately from the shared Auto
template's ports. If required, set compact Auto's HTTP port to `10810` in
the panel after its first sync.

## Verify

Refresh a subscription on a compatible client and confirm that both geo URL
headers **and `routing`** reach the app and that both files download on a
fresh installation. Global GeoIP/GeoSite URL settings can remain at their
defaults: subscription-specific URLs and downloaded files are kept separately.
Check an ordinary profile and Auto separately: static DNS hosts, split DNS,
direct routes, block routes, and the five-member Auto pool must still work.
Confirm that the final runtime routing retains `auto-leastload` for Auto.
Core parsing with downloaded assets checks configuration validity; it does
not establish the app's header handling, download ordering, or failover.

## Android 5.26.83 header dependency

Investigating headers that arrived correctly but did not trigger geo downloads
found a dependency in the official APK's subscription updater: an empty
`routing` value clears both stored subscription geo URLs and prevents their
download. This was the cause of the initial integration failure, which sent
only `geoipurl` and `geositeurl`.

Static inspection of the official arm64 APK traced the non-empty check to
`k4.d.h` and the raw JSON configuration path to `k4.D.h` / `k4.D.k`. The latter
rebuilds local inbounds and stats without replacing JSON routing. The geo
manager uses a separate `subscription_geo` directory; the app's global geo
URL preferences are not proof of whether the subscription assets loaded.
APK SHA-256: `d530b4730376135f8f1a5dc1b927d9826e62dc125d3e8cd19c3e355ff7a274e9`.
This establishes the code paths in that published APK; confirm refresh,
download completion, and connection behavior on the target device.
