#!/usr/bin/env python3
"""Prepare compact Remnawave templates and geo headers for v2RayTun."""

import argparse
import base64
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlparse


REPO = Path(__file__).resolve().parents[1]


def render(output_dir, template_name, happ_routing=None):
    base = json.loads((REPO / "XRAY_JSON/DEFAULT.JSON").read_text())
    if happ_routing is None:
        happ = json.loads((REPO / "HAPP/DEFAULT.JSON").read_text())
    else:
        prefix = "happ://routing/onadd/"
        if not happ_routing.startswith(prefix):
            raise ValueError("Expected a happ://routing/onadd/ payload")
        happ = json.loads(base64.b64decode(happ_routing[len(prefix):], validate=True))
    headers = []
    for key, field in (("geoipurl", "Geoipurl"), ("geositeurl", "Geositeurl")):
        value = happ[field]
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc or any(c.isspace() for c in value):
            raise ValueError(f"Invalid {key} in HAPP/DEFAULT.JSON")
        headers.append({"key": key, "value": value})

    rules = json.loads((REPO / "response_rules.json").read_text())["rules"]
    matches = [rule for rule in rules if rule["name"] == "V2RAYTUN"]
    if len(matches) != 1:
        raise ValueError("Expected exactly one V2RAYTUN response rule")
    rule = copy.deepcopy(matches[0])
    rule["responseType"] = "XRAY_JSON"
    mods = rule.setdefault("responseModifications", {})
    mods["subscriptionTemplate"] = template_name
    # Preserve per-host Auto selection. A forced default would lose balancing.
    mods["ignoreHostXrayJsonTemplate"] = False
    mods["applyHeadersToEnd"] = True
    mods["excludeHostsByTags"] = list(dict.fromkeys(
        mods.get("excludeHostsByTags", []) + ["V2RAYTUN_EXCLUDE"]))
    # Routing stays in each small template: proxy and auto-leastload differ.
    mods["headers"] = [header for header in mods.get("headers", [])
                       if header["key"].lower() not in ("routing", "geoipurl", "geositeurl")]
    mods["headers"].extend(headers)

    with tempfile.TemporaryDirectory(prefix="v2raytun-render-") as directory:
        pool_path = Path(directory) / "leastload.json"
        # --rendered skips expansion, retaining the same source geo references.
        subprocess.run(["bash", str(REPO / "scripts/render-xray-least-load.sh"),
                        "--rendered", str(REPO / "XRAY_JSON/DEFAULT.JSON"), str(pool_path)],
                       check=True)
        pool = json.loads(pool_path.read_text())

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (("default.json", base), ("leastload.json", pool), ("response-rule.json", rule)):
        (output_dir / name).write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--template-name", default="V2RayTun Compact",
                        help="Name of the compact default template to select in Remnawave")
    parser.add_argument("--happ-routing", help="Use this build's HAPP routing payload for pinned geo URLs")
    args = parser.parse_args()
    if not args.template_name.strip():
        parser.error("--template-name must not be empty")
    render(args.output_dir, args.template_name, args.happ_routing)
    print(f"Compact templates and V2RAYTUN response rule written to {args.output_dir}")


if __name__ == "__main__":
    main()
