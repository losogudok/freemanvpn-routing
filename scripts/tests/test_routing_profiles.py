"""Check policy sharing through the routing-profile generator CLI."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


class RoutingProfilesTest(unittest.TestCase):
    def test_both_clients_follow_one_xray_policy_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('scripts', 'XRAY_JSON', 'HAPP', 'bundle'):
                (root / folder).mkdir()
            script = REPO / 'scripts/render-routing-profiles.py'
            shutil.copy(script, root / 'scripts' / script.name)
            for name in ('DEFAULT', 'WHITELIST'):
                shutil.copy(REPO / 'XRAY_JSON' / (name + '.JSON'), root / 'XRAY_JSON' / (name + '.JSON'))
                shutil.copy(REPO / 'HAPP' / (name + '.JSON'), root / 'HAPP' / (name + '.JSON'))
            source_path = root / 'XRAY_JSON/DEFAULT.JSON'
            source = json.loads(source_path.read_text())
            direct = next(r for r in source['routing']['rules'] if r.get('outboundTag') == 'direct' and 'domain' in r)
            direct['domain'].append('full:shared-policy.invalid')
            source['dns']['servers'][0]['domains'].append('full:shared-policy.invalid')
            source['dns']['hosts']['shared-host.invalid'] = '192.0.2.12'
            source_path.write_text(json.dumps(source))
            profile = json.loads((REPO / 'HAPP/JSONSUB.JSON').read_text())
            (root / 'bundle/routing.json').write_text(json.dumps(profile))
            result = subprocess.run(['python3', str(root / 'scripts/render-routing-profiles.py'),
                                     str(root / 'bundle'), str(root / 'out')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for mode in ('DEFAULT', 'WHITELIST', 'JSONSUB'):
                happ = json.loads((root / 'out/HAPP' / (mode + '.JSON')).read_text())
                incy = json.loads((root / 'out/INCY' / (mode + '.JSON')).read_text())
                self.assertEqual(happ, incy)
                for app, scheme in (('HAPP', 'happ'), ('INCY', 'incy')):
                    link = (root / 'out' / app / (mode + '.DEEPLINK')).read_text().strip()
                    self.assertTrue(link.startswith(scheme + '://routing/onadd/'))
                    self.assertEqual(json.loads(base64.b64decode(link.split('/onadd/')[1])), happ)
            default = json.loads((root / 'out/HAPP/DEFAULT.JSON').read_text())
            self.assertIn('full:shared-policy.invalid', default['DirectSites'])
            self.assertEqual(default['DnsHosts']['shared-host.invalid'], '192.0.2.12')
            self.assertEqual(default['Geoipurl'], profile['Geoipurl'])
            self.assertEqual(default['Geositeurl'], profile['Geositeurl'])
            # Conditional rules must fail instead of losing selectors in native profiles.
            direct['port'] = '443'
            source_path.write_text(json.dumps(source))
            rejected = subprocess.run(['python3', str(root / 'scripts/render-routing-profiles.py'),
                                       str(root / 'bundle'), str(root / 'unsupported')], capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('cannot be represented', rejected.stderr)
            self.assertFalse((root / 'unsupported').exists())
