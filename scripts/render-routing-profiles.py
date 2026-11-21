#!/usr/bin/env python3
"""Derive Happ/INCY routing profiles from the shared Xray policy and build metadata."""
import argparse
import base64
import copy
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]


def profile_from_xray(source, metadata):
    profile = copy.deepcopy(metadata)
    fields = {'block': ('BlockSites', 'BlockIp'), 'proxy': ('ProxySites', 'ProxyIp'),
              'direct': ('DirectSites', 'DirectIp')}
    for sites, ips in fields.values():
        profile[sites], profile[ips] = [], []
    rules = source['routing']['rules']
    if not rules or rules[-1] != {'network': 'tcp,udp', 'outboundTag': 'proxy'}:
        raise ValueError('Routing profile requires the final tcp,udp -> proxy rule')
    previous_priority = -1
    for rule in rules[:-1]:
        tag = rule.get('outboundTag')
        if tag not in fields or set(rule) not in ({'domain', 'outboundTag'}, {'ip', 'outboundTag'}):
            raise ValueError('Xray rule cannot be represented by a Happ/INCY routing profile')
        priority = ('block', 'proxy', 'direct').index(tag)
        if priority < previous_priority:
            raise ValueError('Xray rule order cannot be represented by block-proxy-direct')
        previous_priority = priority
        field = fields[tag][0 if 'domain' in rule else 1]
        profile[field].extend(rule.get('domain', rule.get('ip')))
    profile.update(GlobalProxy='true', RouteOrder='block-proxy-direct',
                   DomainStrategy=source['routing']['domainStrategy'],
                   DnsHosts=source['dns'].get('hosts', {}),
                   FakeDNS='true' if source.get('fakeDns', source.get('fakedns')) else 'false')
    domestic, remote = source['dns']['servers']
    # Native profiles choose domestic DNS by DirectSites. Xray-specific DNS
    # selectors stay in the full JSON; only resolver endpoints are projected.
    for prefix, address in (('Domestic', domestic['address']), ('Remote', remote)):
        parsed = urlsplit(address)
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('Expected an HTTPS DNS server')
        ipaddress.ip_address(parsed.hostname)
        profile.update({prefix + 'DNSType': 'DoH', prefix + 'DNSDomain': address,
                        prefix + 'DNSIP': parsed.hostname, prefix + 'Dns': parsed.hostname})
    return profile


def render(bundle, output):
    geo_profile = json.loads((bundle / 'routing.json').read_text())
    profiles = {'JSONSUB': geo_profile}
    for mode in ('DEFAULT', 'WHITELIST'):
        source = json.loads((REPO / 'XRAY_JSON' / (mode + '.JSON')).read_text())
        metadata = json.loads((REPO / 'HAPP' / (mode + '.JSON')).read_text())
        for field in ('Geoipurl', 'Geositeurl', 'LastUpdated'):
            metadata[field] = geo_profile[field]
        profiles[mode] = profile_from_xray(source, metadata)
    # Validate every policy before replacing any generated profile.
    for app in ('HAPP', 'INCY'):
        (output / app).mkdir(parents=True, exist_ok=True)
        for mode, profile in profiles.items():
            payload = json.dumps(profile, ensure_ascii=False, separators=(',', ':')).encode()
            (output / app / (mode + '.JSON')).write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
            (output / app / (mode + '.DEEPLINK')).write_text(
                app.lower() + '://routing/onadd/' + base64.b64encode(payload).decode() + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path, help='Validated Happ bundle from build-xray')
    parser.add_argument('output_root', type=Path)
    args = parser.parse_args()
    render(args.bundle, args.output_root)
