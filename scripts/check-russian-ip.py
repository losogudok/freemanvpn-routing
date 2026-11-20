#!/usr/bin/env python3
"""Exercise the Russian IP template in Xray without external traffic."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def read_exact(connection, length):
    result = b""
    while len(result) < length:
        chunk = connection.recv(length - len(result))
        if not chunk:
            raise AssertionError("SOCKS connection closed during handshake")
        result += chunk
    return result


def check(path, xray, assets=None):
    template = json.loads(path.read_text())
    assert template["remnawave"] == {"addVirtualHostAsOutbound": True}
    if assets is None:
        assert "geosite:" not in json.dumps(template) and "geoip:" not in json.dumps(template)
    assert {outbound["tag"] for outbound in template["outbounds"]} == {"direct"}
    assert all(rule["outboundTag"] in {"proxy", "direct"}
               for rule in template["routing"]["rules"])
    assert not template["routing"].get("balancers")
    config = copy.deepcopy(template)
    config.pop("remnawave")
    # Every route terminates locally. No request can reach a real target or RU.
    config["outbounds"] = [{"tag": tag, "protocol": "blackhole"}
                           for tag in ("direct", "proxy")]
    socks_port, dns_port = available_port(), available_port()
    socks = config["inbounds"][0]
    socks["port"] = socks_port
    dns = copy.deepcopy(socks)
    dns.update(tag=config["dns"]["tag"], port=dns_port)
    config["inbounds"] = [socks, dns]
    config["dns"]["hosts"].update({
        "github.com": "8.8.4.4",
        "www.youtube.com": "8.8.4.4",
        "ads.msn.com": "8.8.4.4",
        "ru-address.routing-check.net": "77.88.55.60",
        "ru-v6-address.routing-check.net": "2a02:6b8::2:242",
        "global-address.routing-check.net": "8.8.4.4",
    })
    cases = [
        (socks_port, "ya.ru", "proxy"),
        (socks_port, "unlisted-service.ru", "proxy"),
        (socks_port, "service.su", "proxy"),
        (socks_port, "service.xn--p1ai", "proxy"),
        (socks_port, "sber.world", "proxy"),
        (socks_port, "emias.info", "proxy"),
        (socks_port, "api.ipify.org", "proxy"),
        (socks_port, "ipinfo.io", "proxy"),
        (socks_port, "77.88.55.60", "proxy"),
        (socks_port, "2a02:6b8::2:242", "proxy"),
        (socks_port, "ru-address.routing-check.net", "proxy"),
        (socks_port, "ru-v6-address.routing-check.net", "proxy"),
        (socks_port, "github.com", "direct"),
        (socks_port, "www.youtube.com", "direct"),
        (socks_port, "global-address.routing-check.net", "direct"),
        (socks_port, "8.8.4.4", "direct"),
        (socks_port, "5.8.43.1", "proxy"),
        (socks_port, "178.124.0.1", "proxy"),
        (socks_port, "17.57.144.1", "proxy"),
        (socks_port, "17.0.0.1", "direct"),
        (socks_port, "192.168.1.1", "direct"),
        (socks_port, "localhost", "direct"),
        (socks_port, "ads.msn.com", "direct"),
        (dns_port, "77.88.8.8", "proxy"),
        (dns_port, "8.8.8.8", "direct"),
    ]
    with tempfile.TemporaryDirectory(prefix="russian-ip-check-") as directory:
        temporary = Path(directory)
        access = temporary / "access.log"
        config["log"] = {"access": str(access), "loglevel": "warning"}
        config_path = temporary / "config.json"
        config_path.write_text(json.dumps(config))
        # Raw templates use the supplied FreemanVPN DAT files; rendered ones
        # run with no geodata to verify that release lists were expanded fully.
        environment = dict(os.environ, XRAY_LOCATION_ASSET=(
            str(assets.resolve()) if assets is not None else directory))
        subprocess.run([xray, "run", "-test", "-c", str(config_path)],
                       env=environment, check=True)
        with (temporary / "core.log").open("w+") as log:
            process = subprocess.Popen([xray, "run", "-c", str(config_path)],
                                       env=environment, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise AssertionError(log.read())
                    try:
                        with socket.create_connection(("127.0.0.1", socks_port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    raise AssertionError("Xray did not start")
                for port, host, expected in cases:
                    previous = access.read_text() if access.exists() else ""
                    with socket.create_connection(("127.0.0.1", port), timeout=3) as connection:
                        connection.sendall(b"\x05\x01\x00")
                        assert read_exact(connection, 2) == b"\x05\x00"
                        encoded = host.encode()
                        connection.sendall(b"\x05\x01\x00\x03" + bytes([len(encoded)])
                                           + encoded + b"\x01\xbb")
                        connection.recv(1024)
                    for _ in range(100):
                        added = access.read_text()[len(previous):] if access.exists() else ""
                        if "accepted tcp:" in added:
                            assert f"-> {expected}]" in added, (host, expected, added)
                            print(f"{host}: {expected}")
                            break
                        time.sleep(.02)
                    else:
                        raise AssertionError(f"No routing result for {host}")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    print(f"Passed {len(cases)} real-core route checks; no external connections made")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template_json", type=Path)
    parser.add_argument("--assets", type=Path,
                        help="Directory with FreemanVPN geoip.dat and geosite.dat for a raw template")
    parser.add_argument("--xray", default=shutil.which("xray") or "xray")
    args = parser.parse_args()
    check(args.template_json, args.xray, args.assets)
