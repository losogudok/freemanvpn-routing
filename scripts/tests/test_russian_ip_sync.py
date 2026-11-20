"""Run the Russian IP deployment script against a local Remnawave API."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest


REPO = Path(__file__).resolve().parents[2]
TEMPLATE_UUID = "77777777-7777-4777-8777-777777777777"


class RussianIPSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "russian-ip.json"
        self.rendered = {
            "remnawave": {"addVirtualHostAsOutbound": True},
            "routing": {"rules": [
                {"domain": ["domain:ru"], "outboundTag": "proxy"},
                {"ip": ["77.88.55.60/32"], "outboundTag": "proxy"},
                {"network": "tcp,udp", "outboundTag": "direct"},
            ]},
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        }
        self.current = {
            "uuid": TEMPLATE_UUID, "name": "User-chosen RU template name",
            "templateType": "XRAY_JSON", "templateJson": {"old": "policy"},
        }
        self.original = copy.deepcopy(self.current)
        self.requests = []
        self.patches = []
        self.failure = None
        self.rollback_failure = False
        self.wrapped = True
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, obj, status=200):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                payload = {"response": obj} if test.wrapped else obj
                self.wfile.write(json.dumps(payload).encode())

            def authenticated(self):
                if self.headers.get("Authorization") != "Bearer fixture-token":
                    self.respond({}, 401)
                    return False
                test.requests.append((self.command, self.path))
                return True

            def do_GET(self):
                if not self.authenticated():
                    return
                if self.path != f"/api/subscription-templates/{TEMPLATE_UUID}" or test.current is None:
                    self.respond({}, 404)
                elif test.failure == "readback" and test.patches:
                    test.failure = None
                    self.respond({}, 500)
                else:
                    self.respond(test.current)

            def do_PATCH(self):
                if not self.authenticated():
                    return
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path != "/api/subscription-templates" or payload.get("uuid") != TEMPLATE_UUID:
                    self.respond({}, 400)
                    return
                test.patches.append(payload)
                test.current["templateJson"] = payload["templateJson"]
                response = copy.deepcopy(test.current)
                # Simulate a committed write whose response is lost or incorrect.
                if test.rollback_failure and len(test.patches) > 1:
                    self.respond({}, 500)
                elif test.failure == "http":
                    test.failure = None
                    self.respond({}, 500)
                elif test.failure == "response":
                    test.failure = None
                    response["templateJson"] = {"incorrect": "response"}
                    self.respond(response)
                elif test.failure == "persisted":
                    test.failure = None
                    test.current["templateJson"] = {"incorrect": "persisted state"}
                    self.respond(response)
                else:
                    self.respond(response)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_sync(self, uuid=TEMPLATE_UUID):
        self.source.write_text(json.dumps(self.rendered))
        environment = dict(
            os.environ,
            REMNAWAVE_API_BASE_URL=f"http://127.0.0.1:{self.server.server_port}/api/",
            REMNAWAVE_TOKEN="fixture-token",
            REMNAWAVE_RU_IP_TEMPLATE_UUID=uuid,
        )
        result = subprocess.run(
            ["bash", str(REPO / "scripts/sync-russian-ip.sh"), str(self.source)],
            env=environment, capture_output=True, text=True, timeout=15,
        )
        self.assertNotIn("fixture-token", result.stdout + result.stderr)
        return result

    def test_updates_only_target_json_and_verifies_persisted_state(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current, {**self.original, "templateJson": self.rendered})
        self.assertEqual(self.patches, [{"uuid": TEMPLATE_UUID, "templateJson": self.rendered}])
        self.assertEqual(self.requests, [
            ("GET", f"/api/subscription-templates/{TEMPLATE_UUID}"),
            ("PATCH", "/api/subscription-templates"),
            ("GET", f"/api/subscription-templates/{TEMPLATE_UUID}"),
        ])

    def test_repeat_deployment_does_not_write_again(self):
        self.assertEqual(self.run_sync().returncode, 0)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already up to date", result.stdout)
        self.assertEqual(len(self.patches), 1)

    def test_unwrapped_api_responses_are_supported(self):
        self.wrapped = False
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current["templateJson"], self.rendered)

    def test_large_rendered_json_does_not_hit_shell_argument_limit(self):
        self.rendered["routing"]["rules"][0]["domain"] = [
            f"full:service-{index}.ru" for index in range(30_000)
        ]
        self.assertGreater(len(json.dumps(self.rendered)), 500_000)
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current["templateJson"], self.rendered)

    def test_invalid_or_missing_uuid_aborts_before_api_calls(self):
        for uuid in ("", "not-a-uuid"):
            with self.subTest(uuid=uuid):
                result = self.run_sync(uuid)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.requests, [])

    def test_compact_source_is_rejected_before_api_calls(self):
        self.rendered["routing"]["rules"][1]["ip"] = ["geoip:direct"]
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expanded JSON", result.stderr)
        self.assertEqual(self.requests, [])

    def test_wrong_type_or_uuid_or_null_content_aborts_before_writing(self):
        for field, value in (("templateType", "SINGBOX"), ("uuid", "wrong"), ("templateJson", None)):
            with self.subTest(field=field):
                self.current = {**copy.deepcopy(self.original), field: value}
                result = self.run_sync()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("existing XRAY_JSON template", result.stderr)
                self.assertEqual(self.patches, [])

    def test_missing_template_aborts_before_writing(self):
        self.current = None
        self.assertNotEqual(self.run_sync().returncode, 0)
        self.assertEqual(self.patches, [])

    def test_uncertain_write_bad_response_and_failed_readback_are_rolled_back(self):
        for failure in ("http", "response", "persisted", "readback"):
            with self.subTest(failure=failure):
                self.current = copy.deepcopy(self.original)
                self.patches = []
                self.failure = failure
                result = self.run_sync()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Rolled back", result.stderr)
                self.assertEqual(self.current, self.original)
                self.assertEqual(len(self.patches), 2)
                self.assertEqual(self.patches[-1], {
                    "uuid": TEMPLATE_UUID, "templateJson": self.original["templateJson"],
                })

    def test_failed_rollback_is_reported(self):
        self.failure = "http"
        self.rollback_failure = True
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rollback incomplete", result.stderr)
        self.assertEqual(len(self.patches), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
