"""Check compact templates against the real shared routing policy."""

import json
import base64
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]


class V2RayTunTest(unittest.TestCase):
    def test_compact_bundle_preserves_policy_and_separate_auto_routing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(["python3", str(REPO / "scripts/render-v2raytun.py"), directory,
                                     "--template-name", "Test compact template"],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = Path(directory)
            default = json.loads((output / "default.json").read_text())
            pool = json.loads((output / "leastload.json").read_text())
            rule = json.loads((output / "response-rule.json").read_text())
            source = json.loads((REPO / "XRAY_JSON/DEFAULT.JSON").read_text())
            settings = json.loads((REPO / "XRAY_JSON/LEASTLOAD.settings.json").read_text())
            self.assertEqual(default, source)
            for key in ("dns", "fakeDns", "inbounds", "outbounds"):
                self.assertEqual(pool[key], source[key])
            self.assertEqual(pool["remnawave"], settings["remnawave"])
            self.assertEqual(pool["burstObservatory"], settings["burstObservatory"])
            self.assertEqual(pool["routing"]["balancers"], settings["routing"]["balancers"])
            self.assertEqual(len(pool["routing"]["rules"]), len(source["routing"]["rules"]))
            for original, generated in zip(source["routing"]["rules"], pool["routing"]["rules"]):
                if original.get("outboundTag") == "proxy":
                    restored = dict(generated)
                    self.assertEqual(restored.pop("balancerTag"), "auto-leastload")
                    restored["outboundTag"] = "proxy"
                    self.assertEqual(restored, original)
                else:
                    self.assertEqual(generated, original)
            # A rendered policy snapshot would inflate these files to megabytes.
            self.assertLess((output / "default.json").stat().st_size, 10000)
            self.assertLess((output / "leastload.json").stat().st_size, 10000)
            mods = rule["responseModifications"]
            self.assertEqual(mods["subscriptionTemplate"], "Test compact template")
            self.assertFalse(mods["ignoreHostXrayJsonTemplate"])
            self.assertTrue(mods["applyHeadersToEnd"])
            headers = {header["key"].lower(): header["value"] for header in mods["headers"]}
            # Android 5.26.83 requires nonblank routing to retain the geo URLs.
            # The metadata must not point ordinary profiles at Auto or vice versa.
            metadata = json.loads(base64.b64decode(headers["routing"], validate=True))
            self.assertEqual(metadata["rules"], [])
            self.assertEqual(metadata["balancers"], [])
            self.assertEqual(metadata["name"], "FreemanVPN Geo Files")
            self.assertTrue(metadata["id"])
            happ = json.loads((REPO / "HAPP/DEFAULT.JSON").read_text())
            self.assertEqual(headers["geoipurl"], happ["Geoipurl"])
            self.assertEqual(headers["geositeurl"], happ["Geositeurl"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
