#!/usr/bin/env python3
"""Validate Happ's compact bundle against the exact downloaded DAT files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def check(bundle, assets, xray):
    info = json.loads((bundle / "build-info.json").read_text())
    profile = json.loads((bundle / "routing.json").read_text())
    for kind, field in (("geoip", "Geoipurl"), ("geosite", "Geositeurl")):
        actual = hashlib.sha256((assets / f"{kind}.dat").read_bytes()).hexdigest()
        if actual != info[kind]["sha256"] or profile[field] != info[kind]["url"]:
            raise ValueError(f"{kind} DAT/profile differs from the build manifest")
    environment = dict(os.environ, XRAY_LOCATION_ASSET=str(assets.resolve()))
    with tempfile.TemporaryDirectory(prefix="happ-check-") as directory:
        for name in ("default.json", "leastload.json", "russian-ip.json"):
            config = json.loads((bundle / name).read_text())
            config.pop("remnawave")
            # Panel-injected outbounds are represented by local stubs for parsing.
            # No process is started and no external connection is made.
            config["outbounds"].extend([{"tag": "proxy", "protocol": "blackhole"},
                                        {"tag": "auto-proxy", "protocol": "blackhole"}])
            path = Path(directory) / name
            path.write_text(json.dumps(config))
            subprocess.run([xray, "run", "-test", "-c", str(path)], env=environment, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--xray", default="xray")
    args = parser.parse_args()
    check(args.bundle, args.assets, args.xray)
