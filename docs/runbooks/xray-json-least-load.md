# Generate the YouTube Auto virtual-host template

The source of the client routing policy is [XRAY_JSON/DEFAULT.JSON](../../XRAY_JSON/DEFAULT.JSON).
[LEASTLOAD.settings.json](../../XRAY_JSON/LEASTLOAD.settings.json) currently
contains a complete rendered template. The renderer reads only its
virtual-host injection, probes, and balancer settings. It always takes
DNS, FakeDNS, inbounds, and routing rules from a freshly rendered DEFAULT,
so the embedded snapshot cannot overwrite current policy updates.
The supplied full template uses HTTP port `10810`; regenerating from
DEFAULT uses its HTTP port `10809` unless you explicitly adjust the output.

Generate the full template from the routing repository:

```sh
cd ~/Projects/freemanvpn/freemanvpn-routing
scripts/render-xray-least-load.sh XRAY_JSON/DEFAULT.JSON /tmp/freemanvpn-leastload.json
```

The renderer calls the existing geodata renderer, then replaces every
`outboundTag: "proxy"` rule with `balancerTag: "auto-leastload"`.
DNS, FakeDNS, inbounds, rule ordering, direct routes, and blocking rules
come from DEFAULT. Geosite/GeoIP references are expanded into domains and
CIDRs so the generated subscription does not need custom client geo files.
The generated file contains no customer credentials; the panel injects them
when generating each customer's subscription.

For initial setup, import `/tmp/freemanvpn-leastload.json` into a separate
Remnawave `XRAY_JSON` subscription template. Keep its name distinct from
`Default Xray JSON`. The workflow now renders DEFAULT once and derives the
virtual template from the same expanded geodata. Both templates and the
HAPP/INCY routing headers are synchronized together, with rollback on failure.

The synchronization script finds the existing virtual template by the
balancer tag and injected-host prefixes in the settings file, independent
of its name. A missing or ambiguous match aborts before any write. If you
have multiple matching variants, set the GitHub repository variable
`REMNAWAVE_LEASTLOAD_TEMPLATE_UUID` to the intended template UUID. Changing
these identifying tags requires updating the target template or selector
before the next synchronization.

The workflow preserves the virtual template's existing local inbound ports,
including HTTP `10810`, while regenerating DNS, sniffing, and routing from
DEFAULT. A local manual rendering uses DEFAULT's ports as described above.
The workflow does not change the HAPP rule's subscription response type;
the JSON migration remains a separate rollout step.

## Select the five hosts

Set the **host tag** of these five intended host entries to
`FREEMAN_AUTO_LEASTLOAD`:

| Connection address | Host tag |
| --- | --- |
| `xuyandex.party` | `FREEMAN_AUTO_LEASTLOAD` |
| `host3.lookmaimanengineer.cc` | `FREEMAN_AUTO_LEASTLOAD` |
| `forum.mmorpg.uk` | `FREEMAN_AUTO_LEASTLOAD` |
| `chat.mmorpg.uk` | `FREEMAN_AUTO_LEASTLOAD` |
| `news.freemanbot.uk` | `FREEMAN_AUTO_LEASTLOAD` |

Use the host tag field, not the inbound tag or remark. If existing host tags
are used by other integrations, replace the selector in the settings file
with `{"type":"uuids","values":[...]}` containing these five panel
**host UUIDs**, then regenerate. Connection addresses and inbound UUIDs
cannot substitute for host UUIDs.

Only intended pool members should carry this tag. If an address has several
host entries, choose the intended transport/inbound explicitly. Keep those
hosts enabled. `selectFrom: "ALL"` supports both visible and hidden hosts.
Customers need squad access to the inbounds of all selected hosts; disabled
or inaccessible members are omitted from their generated pool.

## Create the virtual host and select the response format

Remnawave must be **2.6.3+**. The live test-user JSON response was verified
on 2026-10-13 to contain this virtual host with all five injected members.
Reported cores: v2rayTun **26.6.27**, Happ **26.9.9**, servers **26.7.28**.

1. Create a separate enabled, visible host with remark `FreemanVPN Auto`.
   Associate it with an existing inbound accessible to the intended users.
   Copy one selected host's address/port for the required fields; the
   virtual address does not become a connection target in this template.
2. Leave its host tag empty and assign `FreemanVPN Auto — YouTube` as
   its Xray JSON template in Advanced.
3. Ensure the client's subscription response is `XRAY_JSON`. The current
   distribution uses JSON for v2rayTun, while Happ uses base64 plus a routing
   header. That Happ response cannot carry this multi-outbound virtual
   configuration. Test Happ with an explicit JSON subscription response
   and confirm it retains the balancer and observatory before rollout.
   See the [Happ migration verification](happ-xray-json-migration.md) for
   the verified live response and tunnel-DNS considerations.
   Response-format changes must be scoped to the intended users/client
   requests; the default Happ routing header alone does not enable balancing.
4. Refresh the subscription, then select `FreemanVPN Auto`.

## Behavior

### Match local ports in v2rayN

The DEFAULT template listens for SOCKS on `10808` and HTTP on `10809`.
v2rayN's configured local SOCKS/mixed port must point to the template's
SOCKS inbound. If the app uses `10809`, it sends SOCKS to the template's
HTTP listener and logs `malformed HTTP request "\x05\x01\x00"`.

For that client setting, create a variant with SOCKS on `10809` and HTTP
on `10810` after generating the template:

```sh
jq '.inbounds |= map(
  if .protocol == "socks" then .port = 10809
  elif .protocol == "http" then .port = 10810
  else . end
)' /tmp/freemanvpn-leastload.json > /tmp/freemanvpn-leastload-v2rayn.json
```

Import the port-adjusted variant into the test template in the panel,
then refresh the subscription and reload the client. Editing only a local
imported profile is temporary: subscription refresh replaces it.

### Probes and selection

The client probes all injected outbounds at an average interval of one
minute, retaining three recent results, with a five-second timeout and
`https://www.youtube.com/generate_204` as the destination. The default
HTTP method is HEAD. `leastPing` selects the alive candidate with the
smallest observed delay. There are no leastLoad-specific settings such
as `expected`, `maxRTT`, or `tolerance` in this variant. Existing
connections are not moved when selection changes.

This measures response latency to YouTube's web endpoint through each
server. It does not measure sustained video throughput or every
`googlevideo.com` CDN route, so a fast probe is not a guarantee of faster
video playback. The earlier leastLoad variant prioritized latency
variation; this variant prioritizes observed latency instead.

The existing file names, pool host tag `FREEMAN_AUTO_LEASTLOAD`, and
balancer tag `auto-leastload` are retained so existing host assignments
and generated routing references remain compatible. The strategy itself
is now `leastPing`.

If no candidate qualifies, **proxy-routed traffic** uses the `block`
fallback. DEFAULT's intentional direct routes continue to work. Selection
and failure detection depend on periodic probes, and a blocked probe
destination can exclude an otherwise working server.

## Verify

Check a generated subscription for a test user with access to all five hosts:

- The panel removes `remnawave` and injects exactly five real outbounds:
  `auto-proxy`, `auto-proxy-2`, through `auto-proxy-5`, with the five
  expected addresses and panel-generated transport settings.
- Both selectors contain `auto-proxy`, including the first outbound.
- Proxy rules reference `auto-leastload`; direct and block rules match the
  rendered DEFAULT policy. The fallback `block` is defined.

The generated customer subscription contains credentials; keep it private.
Extract its virtual-entry object from the subscription array and validate
with the client's core:

```sh
xray run -test -config /path/to/private-generated-auto.json
```

Test v2rayTun and Happ separately: wait for probes, confirm proxy traffic,
direct destinations and UDP/DNS, then make the chosen endpoint unreachable
on the test device and verify new proxy connections switch after probing.
Make all five endpoints unreachable and check that proxy destinations fail
while intentional direct destinations still work. Restore device
reachability afterward. Parsing alone does not establish this behavior.

## References

- [Remnawave host injection](https://docs.rw/learn/xray-json-advanced/)
- [Xray routing and leastPing](https://xtls.github.io/en/config/routing.html)
- [Xray leastPing implementation](https://github.com/XTLS/Xray-core/blob/main/app/router/strategy_leastping.go)

## Selecting by online-user counts

The client-side observatory measures its own outbound paths. It does not
receive server-wide online-user counts. Remnawave exposes node online-user
metrics, which a separate central selector could consume. The count must
be defined carefully: the node management page also shows connection
counts with duplicates, while online status can be based on recent traffic.

Assigning a server when a subscription is requested uses counts at refresh
time. It does not reassign at the next VPN connection and cannot guarantee
the least-populated node when the customer connects. Choosing at connection
time needs an additional gateway or client/controller integration. Fewer
users alone also does not imply lower YouTube latency: server capacity,
traffic volume, and the onward route matter.

- [Remnawave node metrics](https://f.docs.rw/t/topic/175)
- [Node connection-count display](https://docs.rw/learn-en/nodes/)
- [Online-status calculation](https://f.docs.rw/t/topic/263)
