# INCY: individual servers with a routing header

The current delivery choice is `XRAY_BASE64` for INCY: a base64-encoded list of
ordinary server links, with the existing `routing` header. INCY generates its
own tunnel configuration and applies the routing profile. There is no distinct
Remnawave subscription response type named `INCY`.

The repository's [`response_rules.json`](../../response_rules.json) is ready for
this delivery mode. Only the INCY response rule gains host exclusion and the
legacy JSON override. Happ remains `XRAY_JSON`; its rule and routing header are
unchanged by this change.

## Panel setup

The owner reports running the latest Remnawave panel. Per-rule
`responseModifications.excludeHostsByTags` was verified in **3.4.5** source.

1. Add the new host tag **`INCY_EXCLUDE` only to the virtual host** (`FreemanVPN
   Auto`). Preserve its existing tags, template assignment, enabled state and
   visibility for other clients. Do not put this tag on the physical pool
   members. The existing `FREEMAN_AUTO_LEASTLOAD` tag identifies real servers
   and must not be used as the exclusion tag.
2. Import the updated Response Rule Set, retaining any live rules that are not
   in the local file. Disable/remove the earlier **INCY JSON test** rule if it
   is still installed above INCY; first-match selection would otherwise keep
   serving JSON to that account. Alternatively, edit the existing INCY rule:

   ```json
   {
     "responseType": "XRAY_BASE64",
     "responseModifications": {
       "applyHeadersToEnd": true,
       "ignoreServeJsonAtBaseSubscription": true,
       "excludeHostsByTags": ["INCY_EXCLUDE"],
       "headers": [
         {"key": "routing", "value": "<keep the existing INCY routing value>"}
       ]
     }
   }
   ```

   This is an edit fragment, not a complete rule. Keep the INCY User-Agent
   condition and existing header value. Remove the old INCY JSON template
   override (`subscriptionTemplate` and `ignoreHostXrayJsonTemplate`) from any
   adapted test rule. `ignoreServeJsonAtBaseSubscription` prevents the legacy
   panel setting from converting the base64 response back to JSON.
3. Refresh the subscription in INCY and reconnect to an individual real server.
   The virtual entry should disappear from INCY, while remaining available to
   clients whose response rules do not exclude its tag.

## Result and limitations

Header-based direct/block/proxy policy is handled by INCY's ordinary server
configuration path, avoiding the full-JSON catch-all ordering defect. Each
selected server is a single connection target. The custom `auto-leastload`
balancer and observatory are no longer delivered to INCY, including for
explicit proxy domains. This does not claim automatic failover between the
individual entries.

Do not globally disable/delete/hide the virtual host or exclude it from all
base64 subscriptions: filtering belongs to the INCY response rule. If the panel
does not support per-rule tag exclusion, the exact INCY-only change needs a
panel upgrade or filtering in the subscription delivery service.

The rejected INCY JSON template, renderer, test candidate and optional CI
synchronization have been removed. Normal CI header synchronization preserves
the INCY response type and host filter; it does not import local response rules
or change host tags. If an unused INCY JSON template remains in the panel,
pin `REMNAWAVE_LEASTLOAD_TEMPLATE_UUID` to the actual virtual-host template so
automatic pool discovery cannot confuse the two.

## Why individual server links

The installed INCY Android 3.7.0 full-config patcher appends header policy after
provider JSON rules. A provider catch-all (`tcp,udp -> auto-leastload`) therefore
shadows direct rules such as `ya.ru`; moving the payload into the body produces
the same order. Removing the catch-all restores policy matching, but unmatched
traffic uses the first outbound without default balancing. Expanded policy in
JSON was rejected because it makes the subscription too large. Server links
let INCY build its ordinary configuration with the profile supplied separately.

## Verification

Before considering the rollout complete, verify a fresh INCY request returns
base64 server links with a `routing` header, contains every intended physical
server, and omits the virtual entry. Verify the same virtual entry remains in a
Happ `XRAY_JSON` response. On Android 3.7.0, refresh and test `ya.ru` direct,
a known blocked destination, and a proxy destination through the selected
server. The agent has not changed live hosts or panel settings or tested this
new response on the phone.

Sources checked on 2026-10-13:

- [INCY subscription formats](https://docs.incy.cc/en/subscription-format/)
- [Remnawave 3.4.5 response modifications](https://github.com/remnawave/backend/blob/3.4.5/libs/contract/models/response-rules/response-rule-modifications.schema.ts)
- [Remnawave 3.4.5 per-rule host filtering](https://github.com/remnawave/backend/blob/3.4.5/src/modules/subscription-template/resolve-proxy/resolve-proxy-config.service.ts)
- [Remnawave 3.4.5 base64 link generation](https://github.com/remnawave/backend/blob/3.4.5/src/modules/subscription-template/generators/xray.generator.service.ts)
