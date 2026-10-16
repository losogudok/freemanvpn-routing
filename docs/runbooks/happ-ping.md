# Happ: apply TCP ping through the subscription

On the affected Android mobile network, proxy HEAD ping hangs for every
server while TCP ping works. This does not establish that YouTube blocking
is the cause. Happ's UI ping is configured separately from the Auto profile's
YouTube burst observatory.

The HAPP rule in [response_rules.json](../../response_rules.json) sends the
following HTTP response header with the `XRAY_JSON` subscription:

```http
ping-type: tcp
```

[Happ app-management documentation](https://www.happ.su/main/dev-docs/app-management)
lists `tcp` as a supported value. It requires a valid **Provider ID** in the
subscription for remote app settings. Keep the existing Provider ID configured
in the panel; this repository does not supply one.

## Rollout

The normal Remnawave synchronization now inserts or replaces `ping-type` in
the live rule named `HAPP`, alongside updating its routing header. It retains
other rule settings and headers, including an existing Provider ID. Existing
rollback and response verification cover the ping change too. The workflow
detects changes to the sync script, so publishing this change to `main` triggers
synchronization. For a manual workflow run, enable `force_sync`.

To apply the workaround directly in the panel, add the following entry to
**Subscription Settings → Response Rules → HAPP → responseModifications.headers**,
replacing any existing `ping-type` entry:

```json
{"key": "ping-type", "value": "tcp"}
```

Users receive the setting on their next successful subscription refresh,
including automatic refresh. This requires no manual change to each user's
Ping settings. Devices that have not refreshed retain their previous setting.

## Verification

Check a subscription response requested with Happ's User-Agent for
`ping-type: tcp` and the existing Provider ID. On an affected Android phone,
refresh an existing subscription while proxy HEAD is still selected, then
confirm Happ switches to TCP and ping completes on mobile data. Verify the
Auto entry separately as well as individual servers.

TCP ping measures connection establishment to the server. A successful result
does not verify the VLESS handshake or access through the tunnel. Auto selection
continues to use its configured YouTube probes. The repository's HTTP-fixture
tests verify header synchronization, deduplication, preservation and rollback;
they do not verify Happ's on-device application of the header.
