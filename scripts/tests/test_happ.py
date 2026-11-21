"""Exercise the compact Happ bundle through its command line interface."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


class HappRenderTest(unittest.TestCase):
    def test_bundle_preserves_each_policy_and_pins_both_geo_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info = {kind: {"tag": tag, "url": f"https://raw.githubusercontent.com/losogudok/freemanvpn-{kind}/{tag}/release/{kind}.dat", "sha256": "a" * 64}
                    for kind, tag in (("geoip", "202611211053"), ("geosite", "202611071812"))}
            (root / "info.json").write_text(json.dumps(info))
            result = subprocess.run(["python3", str(REPO / "scripts/render-happ.py"), str(root / "bundle"),
                                     "--build-info", str(root / "info.json")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            bundle = root / "bundle"
            default = json.loads((bundle / "default.json").read_text())
            self.assertEqual(default, json.loads((REPO / "XRAY_JSON/DEFAULT.JSON").read_text()))
            ru = json.loads((bundle / "russian-ip.json").read_text())
            self.assertEqual(ru, json.loads((REPO / "XRAY_JSON/RUSSIAN_IP.JSON").read_text()))
            auto = json.loads((bundle / "leastload.json").read_text())
            for field in ("dns", "inbounds", "fakedns", "outbounds"):
                self.assertEqual(auto.get(field), default.get(field))
            self.assertEqual(auto["routing"]["balancers"][0]["strategy"], {"type": "leastPing"})
            self.assertEqual(auto["routing"]["balancers"][0]["fallbackTag"], "block")
            self.assertTrue(auto["burstObservatory"]["subjectSelector"])
            for rule in auto["routing"]["rules"]:
                self.assertNotEqual(rule.get("outboundTag"), "proxy")
            link = (bundle / "routing.deeplink").read_text().strip()
            self.assertTrue(link.startswith("happ://routing/onadd/"))
            profile = json.loads(base64.b64decode(link.split("/onadd/")[1]))
            self.assertEqual(profile["Name"], "FreemanVPN JSON")
            self.assertEqual(profile["UseChunkFiles"], "false")
            self.assertEqual(profile["Geoipurl"], info["geoip"]["url"])
            self.assertEqual(profile["Geositeurl"], info["geosite"]["url"])
            self.assertEqual(profile["RemoteDNSDomain"], "https://8.8.8.8/dns-query")
            self.assertEqual(profile["DirectSites"], [])
            self.assertEqual(profile["ProxySites"], [])
            self.assertEqual(profile["BlockSites"], [])
            self.assertIn("geosite:", (bundle / "default.json").read_text())
            self.assertNotIn("Geoipurl", default)
