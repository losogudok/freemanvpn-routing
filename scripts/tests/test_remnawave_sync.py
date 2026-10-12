"""Exercise the real sync script against a local Remnawave HTTP fixture."""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest


REPO = Path(__file__).resolve().parents[2]
DEFAULT_UUID = "11111111-1111-4111-8111-111111111111"
POOL_UUID = "22222222-2222-4222-8222-222222222222"
OTHER_UUID = "33333333-3333-4333-8333-333333333333"
BASE = {
    "remnawave": {"addVirtualHostAsOutbound": True},
    "dns": {"hosts": {"fresh-policy.invalid": "192.0.2.123"}},
    "fakeDns": {"ipPool": "198.18.0.0/15", "poolSize": 65535},
    "inbounds": [
        {"tag": "socks", "protocol": "socks", "port": 10808},
        {"tag": "http", "protocol": "http", "port": 10809},
    ],
    "outbounds": [{"tag": "direct", "protocol": "freedom"}, {"tag": "block", "protocol": "blackhole"}],
    "routing": {"rules": [
        {"domain": ["full:fresh-policy.invalid"], "outboundTag": "direct"},
        {"network": "tcp,udp", "outboundTag": "proxy"},
    ]},
}
POOL_SETTINGS = {
    "remnawave": {
        "addVirtualHostAsOutbound": False,
        "injectHosts": [{"selector": {"type": "tagRegex", "pattern": "^FREEMAN_AUTO_LEASTLOAD$"},
                         "selectFrom": "ALL", "tagPrefix": "auto-proxy"}],
    },
    "burstObservatory": {"subjectSelector": ["auto-proxy"], "pingConfig": {"interval": "1m"}},
    "routing": {"balancers": [{"tag": "auto-leastload", "selector": ["auto-proxy"],
                               "strategy": {"type": "leastPing"}, "fallbackTag": "block"}],
                "rules": [{"network": "tcp,udp", "balancerTag": "auto-leastload"}]},
    "dns": {"hosts": {"stale-policy.invalid": "192.0.2.1"}},
}


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "XRAY_JSON").mkdir()
        (self.root / "runner").mkdir()
        for name in ["sync-remnawave-routing.sh", "render-xray-least-load.sh"]:
            shutil.copy(REPO / "scripts" / name, self.root / "scripts" / name)
            (self.root / "scripts" / name).chmod(0o755)
        # Isolate only the network geodata download. Pool rendering, target
        # discovery, API payloads, verification and rollback remain real code.
        renderer = self.root / "scripts/render-xray-json.sh"
        renderer.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf "render\\n" >> "$TEST_RENDER_LOG"\ncp -- "$1" "$2"\n')
        renderer.chmod(0o755)
        (self.root / "XRAY_JSON/DEFAULT.JSON").write_text(json.dumps(BASE))
        (self.root / "XRAY_JSON/LEASTLOAD.settings.json").write_text(json.dumps(POOL_SETTINGS))
        old_pool = copy.deepcopy(POOL_SETTINGS)
        old_pool["inbounds"] = copy.deepcopy(BASE["inbounds"])
        old_pool["inbounds"][1]["port"] = 10810
        self.templates = {
            DEFAULT_UUID: {"uuid": DEFAULT_UUID, "name": "Default Xray JSON", "templateType": "XRAY_JSON",
                           "templateJson": {"old": "default"}},
            POOL_UUID: {"uuid": POOL_UUID, "name": "Existing user-chosen pool name", "templateType": "XRAY_JSON",
                        "templateJson": old_pool},
        }
        self.settings = {"uuid": "settings", "customResponseHeaders": {"routing": "old-global"},
                         "responseRules": {"rules": [
                             {"name": "HAPP", "responseType": "XRAY_JSON", "responseModifications": {
                                 "headers": [{"key": "routing", "value": "old-happ"}]}},
                             {"name": "INCY", "responseType": "XRAY_BASE64", "responseModifications": {
                                 "headers": [{"key": "routing", "value": "old-incy"}]}},
                         ]}}
        self.initial_templates = copy.deepcopy(self.templates)
        self.initial_settings = copy.deepcopy(self.settings)
        self.patches = []
        self.failure = None
        self.rollback_failure = None
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, obj, status=200):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"response": obj}).encode())

            def do_GET(self):
                if self.path == "/api/subscription-templates":
                    # The real listing omits content, requiring detail GETs.
                    self.respond({"templates": [{**v, "templateJson": None} for v in test.templates.values()]})
                elif self.path.startswith("/api/subscription-templates/"):
                    self.respond(test.templates[self.path.rsplit("/", 1)[1]])
                elif self.path == "/api/subscription-settings":
                    self.respond(test.settings)
                else:
                    self.respond({}, 404)

            def do_PATCH(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                target = payload["uuid"]
                test.patches.append(target)
                if self.path == "/api/subscription-templates":
                    test.templates[target]["templateJson"] = payload["templateJson"]
                    obj = test.templates[target]
                else:
                    test.settings.update(payload)
                    obj = test.settings
                # Emulate an ambiguous write: the server commits, but the
                # client sees a failure or an incorrect response body.
                if test.rollback_failure == target and test.patches.count(target) > 1:
                    self.respond({}, 500)
                elif test.failure == target:
                    test.failure = None
                    self.respond({}, 500)
                elif test.failure == "mismatch:" + target:
                    test.failure = None
                    self.respond({})
                else:
                    self.respond(obj)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_sync(self, pinned=""):
        env = {**os.environ, "REMNAWAVE_API_BASE_URL": f"http://127.0.0.1:{self.server.server_port}/api",
               "REMNAWAVE_TOKEN": "fixture-token", "HAPP_DEFAULT": "new-happ", "INCY_DEFAULT": "new-incy",
               "RUNNER_TEMP": str(self.root / "runner"), "REMNAWAVE_LEASTLOAD_TEMPLATE_UUID": pinned,
               "TEST_RENDER_LOG": str(self.root / "renders.log")}
        return subprocess.run(["bash", str(self.root / "scripts/sync-remnawave-routing.sh")],
                              env=env, capture_output=True, text=True, timeout=20)

    def test_success_uses_same_policy_and_preserves_ports_and_format(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.patches, [DEFAULT_UUID, POOL_UUID, "settings"])
        self.assertEqual((self.root / "renders.log").read_text().splitlines(), ["render"])
        default = self.templates[DEFAULT_UUID]["templateJson"]
        pool = self.templates[POOL_UUID]["templateJson"]
        self.assertEqual(default, BASE)
        self.assertEqual(pool["dns"], BASE["dns"])
        self.assertEqual(pool["routing"]["rules"][0], BASE["routing"]["rules"][0])
        self.assertEqual(pool["routing"]["rules"][1]["balancerTag"], "auto-leastload")
        self.assertEqual(pool["inbounds"][1]["port"], 10810)
        rules = self.settings["responseRules"]["rules"]
        self.assertEqual(rules[0]["responseType"], "XRAY_JSON")
        self.assertEqual(rules[0]["responseModifications"]["headers"][0]["value"], "new-happ")
        self.assertNotIn("routing", self.settings["customResponseHeaders"])

    def test_uncertain_writes_and_mismatched_responses_roll_back(self):
        for failure, expected in [
            (DEFAULT_UUID, [DEFAULT_UUID, DEFAULT_UUID]),
            (POOL_UUID, [DEFAULT_UUID, POOL_UUID, POOL_UUID, DEFAULT_UUID]),
            ("settings", [DEFAULT_UUID, POOL_UUID, "settings", "settings", POOL_UUID, DEFAULT_UUID]),
            ("mismatch:" + POOL_UUID, [DEFAULT_UUID, POOL_UUID, POOL_UUID, DEFAULT_UUID]),
            ("mismatch:settings", [DEFAULT_UUID, POOL_UUID, "settings", "settings", POOL_UUID, DEFAULT_UUID]),
        ]:
            with self.subTest(failure=failure):
                self.patches = []
                self.failure = failure
                result = self.run_sync()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.patches, expected, result.stderr)
                self.assertEqual(self.templates, self.initial_templates)
                self.assertEqual(self.settings, self.initial_settings)

    def test_missing_pool_aborts_before_writing(self):
        del self.templates[POOL_UUID]
        self.assertNotEqual(self.run_sync().returncode, 0)
        self.assertEqual(self.patches, [])

    def test_ambiguous_pool_aborts_before_writing(self):
        self.templates[OTHER_UUID] = {**copy.deepcopy(self.templates[POOL_UUID]), "uuid": OTHER_UUID}
        self.assertNotEqual(self.run_sync().returncode, 0)
        self.assertEqual(self.patches, [])

    def test_pinned_pool_resolves_ambiguity(self):
        self.templates[OTHER_UUID] = {**copy.deepcopy(self.templates[POOL_UUID]), "uuid": OTHER_UUID}
        result = self.run_sync(POOL_UUID)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.templates[OTHER_UUID]["templateJson"], self.initial_templates[POOL_UUID]["templateJson"])

    def test_pinned_default_is_rejected_before_writing(self):
        self.assertNotEqual(self.run_sync(DEFAULT_UUID).returncode, 0)
        self.assertEqual(self.patches, [])

    def test_invalid_response_rules_abort_before_writing(self):
        self.settings["responseRules"]["rules"][0]["responseModifications"]["headers"] = []
        self.assertNotEqual(self.run_sync().returncode, 0)
        self.assertEqual(self.patches, [])

    def test_rollback_failure_is_reported_and_other_rollbacks_continue(self):
        self.failure = "settings"
        self.rollback_failure = POOL_UUID
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rollback incomplete", result.stderr)
        self.assertEqual(self.patches, [DEFAULT_UUID, POOL_UUID, "settings", "settings", POOL_UUID, DEFAULT_UUID])


if __name__ == "__main__":
    unittest.main(verbosity=2)
