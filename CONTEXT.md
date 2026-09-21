# Routing Distribution

This context describes how routing policy is published through subscription responses and adopted by compatible VPN clients.

## Language

**Response Rule Set**:
The authoritative ordered policy stored by Remnawave that selects a subscription response and its headers for each client request.
_Avoid_: Routing configuration, client rules

**Client Routing Payload**:
A client-specific deeplink carried in a subscription response header and adopted when the client refreshes its subscription.
_Avoid_: Client update, routing URL

**Client Routing Template**:
A full client configuration served by Remnawave as a subscription response body, carrying DNS and routing policy for clients that cannot adopt a Client Routing Payload.
_Avoid_: Xray JSON config, stub template

**Default Client Routing Profiles**:
The standard HAPP, INCY and v2RayTun routing policies distributed to every matching subscription request.
_Avoid_: Selected profiles, INCY profile, HAPP profile

**Routing Change**:
A byte-for-byte change to any generated Default Client Routing Profile artifact.
_Avoid_: Repository change, configuration change

**Routing Synchronization**:
The coordinated replacement of every distributed routing artifact — the HAPP and INCY Client Routing Payloads and the Client Routing Template — after a Routing Change. All targets are updated together or neither is changed.
_Avoid_: Client update, panel deployment
