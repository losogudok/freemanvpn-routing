#!/usr/bin/env python3
"""Render the Russian IP host template without client geodata dependencies."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


REPO = Path(__file__).resolve().parents[1]


def render(output):
    # Use the same FreemanVPN release lists as the other XRAY_JSON templates.
    # Write the requested artifact only after rendering succeeds.
    with tempfile.TemporaryDirectory(prefix="russian-ip-render-") as directory:
        temporary = Path(directory)
        rendered_path = temporary / "rendered.json"
        subprocess.run(["bash", str(REPO / "scripts/render-xray-json.sh"),
                        str(REPO / "XRAY_JSON/RUSSIAN_IP.JSON"),
                        str(rendered_path)], check=True)
        rendered = json.loads(rendered_path.read_text())
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n")
    print(f"Rendered {output} from FreemanVPN GeoIP and Geosite releases")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.output)


if __name__ == "__main__":
    main()
