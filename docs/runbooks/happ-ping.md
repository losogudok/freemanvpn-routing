# Happ Android: proxy HEAD ping hangs on mobile data

Reported with Happ Android **4.7.1**, an `XRAY_JSON` subscription, and the
default test URL `https://www.gstatic.com/generate_204`: proxy HEAD ping hangs
for every server on mobile data, while TCP ping and actual VPN browsing work.
The operator also confirmed that the Gstatic page loads in a browser through
the VPN on mobile data. This establishes browser access, not that HEAD works
through the temporary core used by Happ's ping helper.
The test URL controls Happ's UI ping. It is separate from the Auto profile's
YouTube burst observatory.

## Provider management is not a free workaround

The previous `ping-type: tcp` response-header workaround requires Happ's
provider-management feature. The operator reports that feature requires a
paid plan, so the repository no longer injects this header. The synchronization
script continues to preserve independently configured app-management headers;
it only manages the routing header.

If the previous change reached the panel, remove its `ping-type: tcp` entry
from the live HAPP response rule. The sync preserves existing headers and
does not delete it automatically. An account without provider management
cannot rely on that header to change existing users' app settings.

## What 4.7.1 actually tests

Read-only inspection of the [official 4.7.1 APK](https://github.com/Happ-proxy/happ-android/releases/tag/4.7.1)
on 2026-10-17 established the following implementation behavior:

- `uk8.h()` reads `pref_delay_test_url` and otherwise returns
  `https://www.gstatic.com/generate_204`.
- `XRayTestService` calls `l87.e()`, which passes the configuration, test URL,
  HTTP method, ping mode and timeout to
  `libxray.Libxray.measureOutboundDelayWithType()`.
- The native `MeasureOutboundDelayWithType` clears the inbounds and retains
  only the outbound-manager, dispatcher and logging modules from `config.App`.
  Supplied routing, DNS and observatory modules are not retained in the
  temporary ping instance. It tests selected proxy outbounds individually.

Consequently, changing `burstObservatory.pingConfig.destination`, adding a
`www.gstatic.com` routing rule or editing the JSON DNS configuration cannot
be relied on to repair this UI ping in 4.7.1. These are findings from static
inspection, not reproduction of the failure on the affected phone.

The inspected APK has SHA-256
`488923701e7d46e556b8566e50f03ef1b13ad807be0299feb892b83a2242a093`,
matching the [official release asset digest](https://github.com/Happ-proxy/happ-android/releases/expanded_assets/4.7.1).
Downloaded binaries and disassembly are kept outside the repository.

## Identify the free fix before a rollout

On the affected phone, compare proxy HEAD with proxy GET, and repeat HEAD
with the VPN disconnected. These are diagnostic changes on the operator's
phone only. If GET works while HEAD hangs, focus on the HTTP-method path;
if HEAD works only with the VPN disconnected, focus on the ping helper's
interaction with the active tunnel. Neither result by itself establishes a
subscription-template fix. Capture the ping/core log for the failing case.

1. With the VPN connected on the affected mobile network, open
   `https://www.gstatic.com/generate_204`. A completed empty response is
   normal. Compare with a HEAD request through an individual server's local
   SOCKS listener, using the exact subscription configuration:

   ```sh
   curl --noproxy '' --proxy socks5h://127.0.0.1:10808 --head --connect-timeout 5 --max-time 10 https://www.gstatic.com/generate_204
   ```

   Use the actual local SOCKS port and authentication if different. A desktop
   check alone does not reproduce the phone's mobile path; a browser check
   also differs from HEAD and is only an initial comparison.
2. If HEAD through the proxy fails, check the corresponding server access/error
   logs and its DNS/egress access to `www.gstatic.com:443`. Fixing the affected
   server's DNS or forwarding this destination through a working exit applies
   to users centrally without Happ app management. TCP ping and YouTube
   browsing alone do not establish that this separate destination works.
3. If HEAD succeeds through the real connection but Happ's button still hangs,
   collect the phone's ping/core log and compare a minimal JSON profile for
   the same outbound. Keep the existing subscription while testing. This
   distinguishes temporary-core initialization, transport and teardown
   problems from endpoint reachability. A client ping bug needs a client fix;
   the JSON template cannot force an app ping mode without app management.

No replacement fix has yet been verified on the affected phone. Do not change
all users to a different subscription format or remove the Auto balancer on
the assumption that either will repair the ping helper.

Sources:

- [Happ app management](https://www.happ.su/main/dev-docs/app-management)
- [Happ JSON passthrough behavior](https://www.happ.su/main/dev-docs/examples-of-links-and-parameters)
- [Happ ping methods](https://www.happ.su/main/faq/ping)
