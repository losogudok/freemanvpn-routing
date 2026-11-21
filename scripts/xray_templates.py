"""Shared compact policy templates; subscription headers belong to each client."""
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[1]


def write_compact_templates(output_dir):
    policies = {
        "default.json": json.loads((REPO / "XRAY_JSON/DEFAULT.JSON").read_text()),
        "russian-ip.json": json.loads((REPO / "XRAY_JSON/RUSSIAN_IP.JSON").read_text()),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, policy in policies.items():
        (output_dir / name).write_text(json.dumps(policy, ensure_ascii=False, separators=(",", ":")) + "\n")
    subprocess.run(["bash", str(REPO / "scripts/render-xray-least-load.sh"), "--rendered",
                    str(output_dir / "default.json"), str(output_dir / "leastload.json")], check=True)
