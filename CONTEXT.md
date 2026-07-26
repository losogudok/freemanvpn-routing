# Routing Distribution

This context describes how routing policy is published through subscription responses and adopted by compatible VPN clients.

## Language

**Response Rule Set**:
The authoritative ordered policy stored by Remnawave that selects a subscription response and its headers for each client request.
_Avoid_: Routing configuration, client rules

**Client Routing Payload**:
A client-specific deeplink carried in a subscription response header and adopted when the client refreshes its subscription.
_Avoid_: Client update, routing URL

**Default Client Routing Profiles**:
The standard HAPP and INCY routing policies distributed to every matching subscription request.
_Avoid_: Selected profiles, INCY profile, HAPP profile

**Routing Change**:
A byte-for-byte change to either generated Default Client Routing Profile payload.
_Avoid_: Repository change, configuration change

**Routing Synchronization**:
The coordinated replacement of both HAPP and INCY Client Routing Payloads in the authoritative Response Rule Set after a Routing Change. Both targets are updated together or neither is changed.
_Avoid_: Client update, panel deployment
