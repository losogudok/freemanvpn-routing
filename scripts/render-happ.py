#!/usr/bin/env python3
"""Build compact Happ templates and a routing profile from one geodata manifest."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[1]


def render(output, build_info):
    info = json.loads(build_info.read_text())
    profile = json.loads((REPO / "HAPP/JSONSUB.JSON").read_text())
    for kind, field in (("geoip", "Geoipurl"), ("geosite", "Geositeurl")):
        entry = info[kind]
        if not re.fullmatch(r"[0-9]{12}", entry["tag"]):
            raise ValueError(f"Invalid {kind} release tag")
        expected = (f"https://raw.githubusercontent.com/losogudok/freemanvpn-{kind}/"
                    f"{entry['tag']}/release/{kind}.dat")
        if entry["url"] != expected or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError(f"Expected pinned FreemanVPN {kind} URL and SHA256")
        profile[field] = entry["url"]
    profile["UseChunkFiles"] = "false"
    # Happ updates an existing routing profile by its stable name.
    profile["Name"] = "FreemanVPN JSON"
    newest_tag = max(info[kind]["tag"] for kind in ("geoip", "geosite"))
    updated = datetime.strptime(newest_tag, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    profile["LastUpdated"] = str(int(updated.timestamp()))
    for field in ("DirectSites", "DirectIp", "ProxySites", "ProxyIp", "BlockSites", "BlockIp"):
        profile[field] = []
    output.mkdir(parents=True, exist_ok=True)
    for source, target in (("DEFAULT.JSON", "default.json"), ("RUSSIAN_IP.JSON", "russian-ip.json")):
        data = json.loads((REPO / "XRAY_JSON" / source).read_text())
        (output / target).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    subprocess.run(["bash", str(REPO / "scripts/render-xray-least-load.sh"), "--rendered",
                    str(output / "default.json"), str(output / "leastload.json")], check=True)
    encoded = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    (output / "routing.json").write_text(encoded + "\n")
    (output / "routing.deeplink").write_text("happ://routing/onadd/" + base64.b64encode(encoded.encode()).decode() + "\n")
    (output / "build-info.json").write_text(json.dumps(info, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--build-info", required=True, type=Path)
    args = parser.parse_args()
    render(args.output_dir, args.build_info)
