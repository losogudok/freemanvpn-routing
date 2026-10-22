"""Exercise the real sync script against a local Remnawave HTTP fixture."""

import copy
import base64
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
COMPACT_UUID = "44444444-4444-4444-8444-444444444444"
COMPACT_AUTO_UUID = "55555555-5555-4555-8555-555555555555"
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
        for name in ["sync-remnawave-routing.sh", "render-xray-least-load.sh", "render-v2raytun.py"]:
            shutil.copy(REPO / "scripts" / name, self.root / "scripts" / name)
            (self.root / "scripts" / name).chmod(0o755)
        # Isolate only the network geodata download. Pool rendering, target
        # discovery, API payloads, verification and rollback remain real code.
        renderer = self.root / "scripts/render-xray-json.sh"
        renderer.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf "render\\n" >> "$TEST_RENDER_LOG"\ncp -- "$1" "$2"\n')
        renderer.chmod(0o755)
        (self.root / "XRAY_JSON/DEFAULT.JSON").write_text(json.dumps(BASE))
        (self.root / "XRAY_JSON/LEASTLOAD.settings.json").write_text(json.dumps(POOL_SETTINGS))
        shutil.copy(REPO / "response_rules.json", self.root / "response_rules.json")
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
                                 "applyHeadersToEnd": True,
                                 "ignoreServeJsonAtBaseSubscription": True,
                                 "excludeHostsByTags": ["INCY_EXCLUDE"],
                                 "headers": [{"key": "routing", "value": "old-incy"}]}},
                         ]}}
        self.initial_templates = copy.deepcopy(self.templates)
        self.initial_settings = copy.deepcopy(self.settings)
        self.patches = []
        self.failure = None
        self.happ_payload = "new-happ"
        self.compact_pins = ("", "")
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

    def run_sync(self, pinned="", default_pinned=""):
        env = {**os.environ, "REMNAWAVE_API_BASE_URL": f"http://127.0.0.1:{self.server.server_port}/api",
               "REMNAWAVE_TOKEN": "fixture-token", "HAPP_DEFAULT": self.happ_payload, "INCY_DEFAULT": "new-incy",
               "RUNNER_TEMP": str(self.root / "runner"), "REMNAWAVE_LEASTLOAD_TEMPLATE_UUID": pinned,
               "REMNAWAVE_DEFAULT_TEMPLATE_UUID": default_pinned,
               "REMNAWAVE_V2RAYTUN_TEMPLATE_UUID": self.compact_pins[0],
               "REMNAWAVE_V2RAYTUN_AUTO_TEMPLATE_UUID": self.compact_pins[1],
               "TEST_RENDER_LOG": str(self.root / "renders.log")}
        return subprocess.run(["bash", str(self.root / "scripts/sync-remnawave-routing.sh")],
                              env=env, capture_output=True, text=True, timeout=20)

    def add_compact_templates(self):
        self.templates[COMPACT_UUID] = {"uuid": COMPACT_UUID, "name": "V2RayTun Compact",
                                        "templateType": "XRAY_JSON", "templateJson": {}}
        self.templates[COMPACT_AUTO_UUID] = {
            "uuid": COMPACT_AUTO_UUID, "name": "V2RayTun Auto Compact",
            "templateType": "XRAY_JSON", "templateJson": {},
        }
        self.settings["responseRules"]["rules"].extend([
            {"name": "V2RAYTUN", "enabled": True, "responseType": "XRAY_JSON",
             "conditions": [{"headerName": "user-agent", "operator": "CONTAINS", "value": "v2raytun"}],
             "responseModifications": {"headers": [
                 {"key": "support-url", "value": "https://support.invalid"},
                 {"key": "GeoIPUrl", "value": "https://old.invalid/geoip.dat"},
                 {"key": "routing", "value": "obsolete-shared-routing"}],
                 "excludeHostsByTags": ["KEEP_EXCLUSION"], "disableHwidCheck": True}},
            {"name": "V2RAYN", "responseType": "XRAY_JSON"},
            {"name": "Fallback", "responseType": "XRAY_BASE64"},
            {"name": "Browser", "responseType": "BROWSER"},
        ])
        self.geo_urls = {"Geoipurl": "https://geo.invalid/build-42/geoip.dat",
                         "Geositeurl": "https://geo.invalid/build-42/geosite.dat"}
        self.happ_payload = "happ://routing/onadd/" + base64.b64encode(json.dumps(self.geo_urls).encode()).decode()
        self.initial_templates = copy.deepcopy(self.templates)
        self.initial_settings = copy.deepcopy(self.settings)

    def test_compact_templates_are_discovered_populated_and_updated_idempotently(self):
        self.add_compact_templates()
        # An expanded renderer changes geodata; compact rendering must bypass it.
        base = copy.deepcopy(BASE)
        base["routing"]["rules"][0]["domain"] = ["geosite:private"]
        (self.root / "XRAY_JSON/DEFAULT.JSON").write_text(json.dumps(base))
        renderer = self.root / "scripts/render-xray-json.sh"
        renderer.write_text('#!/usr/bin/env bash\nset -euo pipefail\nprintf "render\\n" >> "$TEST_RENDER_LOG"\n'
                            'jq \'.routing.rules[0].domain = ["domain:expanded.invalid"]\' "$1" > "$2"\n')
        original_conditions = copy.deepcopy(self.settings["responseRules"]["rules"][2]["conditions"])
        previous_state = None
        for iteration in range(2):
            self.patches = []
            result = self.run_sync()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.patches, [DEFAULT_UUID, POOL_UUID, COMPACT_UUID, COMPACT_AUTO_UUID, "settings"])
            self.assertEqual(self.templates[COMPACT_UUID]["templateJson"], base)
            compact_auto = self.templates[COMPACT_AUTO_UUID]["templateJson"]
            self.assertEqual(compact_auto["dns"], base["dns"])
            self.assertEqual(compact_auto["routing"]["rules"][0]["domain"], ["geosite:private"])
            self.assertEqual(compact_auto["routing"]["rules"][1]["balancerTag"], "auto-leastload")
            self.assertEqual(compact_auto["routing"]["balancers"], POOL_SETTINGS["routing"]["balancers"])
            self.assertEqual(self.templates[DEFAULT_UUID]["templateJson"]["routing"]["rules"][0]["domain"],
                             ["domain:expanded.invalid"])
            rules = self.settings["responseRules"]["rules"]
            v2raytun = rules[2]
            self.assertEqual(v2raytun["conditions"], original_conditions)
            mods = v2raytun["responseModifications"]
            self.assertEqual(mods["subscriptionTemplate"], "V2RayTun Compact")
            self.assertFalse(mods["ignoreHostXrayJsonTemplate"])
            self.assertTrue(mods["disableHwidCheck"])
            self.assertTrue(mods["applyHeadersToEnd"])
            self.assertEqual(mods["excludeHostsByTags"], ["KEEP_EXCLUSION", "V2RAYTUN_EXCLUDE"])
            self.assertEqual(mods["headers"], [
                {"key": "support-url", "value": "https://support.invalid"},
                {"key": "geoipurl", "value": self.geo_urls["Geoipurl"]},
                {"key": "geositeurl", "value": self.geo_urls["Geositeurl"]},
            ])
            for index in (0, 1, 3, 4):
                self.assertIn("V2RAYTUN_ONLY", rules[index]["responseModifications"]["excludeHostsByTags"])
            self.assertIn("INCY_EXCLUDE", rules[1]["responseModifications"]["excludeHostsByTags"])
            self.assertEqual(rules[5], self.initial_settings["responseRules"]["rules"][5])
            state = (copy.deepcopy(self.templates), copy.deepcopy(self.settings))
            if iteration:
                self.assertEqual(state, previous_state)
            previous_state = state

    def test_compact_auto_keeps_its_existing_ports_and_does_not_confuse_pool_discovery(self):
        self.add_compact_templates()
        self.templates[COMPACT_AUTO_UUID]["templateJson"] = copy.deepcopy(self.templates[POOL_UUID]["templateJson"])
        self.templates[COMPACT_AUTO_UUID]["templateJson"]["inbounds"][1]["port"] = 10811
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.templates[COMPACT_AUTO_UUID]["templateJson"]["inbounds"][1]["port"], 10811)
        self.assertEqual(self.templates[POOL_UUID]["templateJson"]["inbounds"][1]["port"], 10810)

    def test_compact_pinned_renamed_templates(self):
        self.add_compact_templates()
        self.templates[COMPACT_UUID]["name"] = "Renamed compact"
        self.templates[COMPACT_AUTO_UUID]["name"] = "Renamed compact auto"
        self.compact_pins = (COMPACT_UUID, COMPACT_AUTO_UUID)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.settings["responseRules"]["rules"][2]["responseModifications"]["subscriptionTemplate"],
                         "Renamed compact")

    def test_invalid_compact_targets_and_rules_abort_before_any_write(self):
        self.add_compact_templates()
        for case in ("missing-auto", "duplicate-name", "wrong-type", "shared-pin", "same-pin", "missing-rule", "invalid-payload"):
            with self.subTest(case=case):
                self.templates = copy.deepcopy(self.initial_templates)
                self.settings = copy.deepcopy(self.initial_settings)
                self.compact_pins = ("", "")
                self.happ_payload = "happ://routing/onadd/" + base64.b64encode(json.dumps(self.geo_urls).encode()).decode()
                if case == "missing-auto": del self.templates[COMPACT_AUTO_UUID]
                elif case == "duplicate-name":
                    self.templates[OTHER_UUID] = {**copy.deepcopy(self.templates[COMPACT_UUID]), "uuid": OTHER_UUID}
                elif case == "wrong-type": self.templates[COMPACT_UUID]["templateType"] = "MIHOMO"
                elif case == "shared-pin": self.compact_pins = (DEFAULT_UUID, COMPACT_AUTO_UUID)
                elif case == "same-pin": self.compact_pins = (COMPACT_UUID, COMPACT_UUID)
                elif case == "missing-rule": del self.settings["responseRules"]["rules"][2]
                elif case == "invalid-payload": self.happ_payload = "not-a-routing-payload"
                result = self.run_sync()
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.patches, [])

    def test_compact_transaction_rolls_back_uncertain_writes_and_bad_responses(self):
        self.add_compact_templates()
        order = [DEFAULT_UUID, POOL_UUID, COMPACT_UUID, COMPACT_AUTO_UUID, "settings"]
        for target in order:
            for prefix in ("", "mismatch:"):
                with self.subTest(target=target, failure=prefix):
                    self.patches = []
                    self.failure = prefix + target
                    result = self.run_sync()
                    self.assertNotEqual(result.returncode, 0)
                    attempted = order[:order.index(target) + 1]
                    self.assertEqual(self.patches, attempted + list(reversed(attempted)), result.stderr)
                    self.assertEqual(self.templates, self.initial_templates)
                    self.assertEqual(self.settings, self.initial_settings)

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
        self.assertEqual(rules[0]["responseModifications"]["headers"], [{"key": "routing", "value": "new-happ"}])
        self.assertEqual(rules[1]["responseType"], "XRAY_BASE64")
        self.assertEqual(rules[1]["responseModifications"], {
            "applyHeadersToEnd": True,
            "ignoreServeJsonAtBaseSubscription": True,
            "excludeHostsByTags": ["INCY_EXCLUDE"],
            "headers": [{"key": "routing", "value": "new-incy"}],
        })
        self.assertNotIn("routing", self.settings["customResponseHeaders"])

    def test_happ_app_settings_are_preserved_without_requiring_provider_management(self):
        headers = self.settings["responseRules"]["rules"][0]["responseModifications"]["headers"]
        headers.extend([
            {"key": "Ping-Type", "value": "proxy-head"},
            {"key": "providerid", "value": "existing-provider-id"},
            {"key": "support-url", "value": "https://support.invalid"},
        ])
        other_rules = copy.deepcopy(self.settings["responseRules"]["rules"][1:])
        # Only INCY's routing value is managed by the sync.
        other_rules[0]["responseModifications"]["headers"][0]["value"] = "new-incy"
        local_rules = json.loads((REPO / "response_rules.json").read_text())["rules"]
        self.assertFalse(any(h["key"].lower() == "ping-type" for r in local_rules if r["name"] == "HAPP"
                             for h in r["responseModifications"]["headers"]))
        expected_headers = copy.deepcopy(headers)
        expected_headers[0]["value"] = "new-happ"
        for _ in range(2):
            result = self.run_sync()
            self.assertEqual(result.returncode, 0, result.stderr)
            rules = self.settings["responseRules"]["rules"]
            actual = rules[0]["responseModifications"]["headers"]
            self.assertEqual(actual, expected_headers)
            self.assertEqual(rules[0]["responseType"], "XRAY_JSON")
            self.assertEqual(rules[1:], other_rules)

    def test_renamed_default_with_virtual_template_is_selected(self):
        self.templates[DEFAULT_UUID]["name"] = "Default"
        self.templates[POOL_UUID]["name"] = "Auto test"
        self.templates[DEFAULT_UUID]["templateJson"] = copy.deepcopy(BASE)
        result = self.run_sync(POOL_UUID, DEFAULT_UUID)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.patches, [DEFAULT_UUID, POOL_UUID, "settings"])

    def test_missing_pinned_default_aborts_before_writing(self):
        self.assertNotEqual(self.run_sync(POOL_UUID, OTHER_UUID).returncode, 0)
        self.assertEqual(self.patches, [])

    def test_pinned_default_must_be_xray_json(self):
        self.templates[DEFAULT_UUID]["templateType"] = "MIHOMO"
        self.assertNotEqual(self.run_sync(POOL_UUID, DEFAULT_UUID).returncode, 0)
        self.assertEqual(self.patches, [])

    def test_same_uuid_for_both_templates_aborts_before_writing(self):
        self.assertNotEqual(self.run_sync(POOL_UUID, POOL_UUID).returncode, 0)
        self.assertEqual(self.patches, [])

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
