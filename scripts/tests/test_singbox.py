"""Check the sing-box template against the shared Xray DEFAULT policy."""

import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SINGBOX_PATH = REPO / "SINGBOX/DEFAULT.JSON"
XRAY_PATH = REPO / "XRAY_JSON/DEFAULT.JSON"
RESPONSE_RULES_PATH = REPO / "response_rules.json"
UPDATE_SCRIPT = REPO / "scripts/update-singbox-geodata.py"
URL_RE = re.compile(
    r"^https://cdn\.jsdelivr\.net/gh/losogudok/freemanvpn-(?P<kind>geosite|geoip)"
    r"@(?P<sha>[0-9a-f]{40})/sing-box/(?P<category>[A-Za-z0-9_-]+)\.srs$"
)


def load_update_module():
    spec = importlib.util.spec_from_file_location("update_singbox_geodata", UPDATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def xray_domain_categories(xray, outbound):
    for rule in xray["routing"]["rules"]:
        if rule.get("outboundTag") == outbound and "domain" in rule:
            values = rule["domain"]
            break
    else:
        raise AssertionError(f"missing Xray domain rule for {outbound}")
    assert all(value.startswith("geosite:") for value in values), values
    return [value.split(":", 1)[1] for value in values]


def xray_ip_categories(xray, outbound):
    for rule in xray["routing"]["rules"]:
        if rule.get("outboundTag") == outbound and "ip" in rule:
            values = rule["ip"]
            break
    else:
        raise AssertionError(f"missing Xray IP rule for {outbound}")
    assert all(value.startswith("geoip:") for value in values), values
    return [value.split(":", 1)[1] for value in values]


def singbox_categories(rule, prefix):
    return [tag[len(prefix):] for tag in rule["rule_set"] if tag.startswith(prefix)]


class SingBoxTest(unittest.TestCase):
    def setUp(self):
        self.singbox = json.loads(SINGBOX_PATH.read_text())
        self.xray = json.loads(XRAY_PATH.read_text())
        self.rule_sets = {rule_set["tag"]: rule_set
                          for rule_set in self.singbox["route"]["rule_set"]}
        self.route_rules = self.singbox["route"]["rules"]

    def route_rule(self, outbound, prefix):
        return next(
            rule for rule in self.route_rules
            if rule.get("outbound") == outbound
            and any(tag.startswith(prefix) for tag in rule.get("rule_set", []))
        )

    def test_block_proxy_and_direct_policy_match_xray_default(self):
        block = self.route_rule("block", "geosite-")
        proxy = self.route_rule("proxy", "geosite-")
        direct_domains = self.route_rule("direct", "geosite-")
        direct_ips = self.route_rule("direct", "geoip-")

        self.assertEqual(singbox_categories(block, "geosite-"),
                         xray_domain_categories(self.xray, "block"))
        self.assertEqual(singbox_categories(proxy, "geosite-"),
                         xray_domain_categories(self.xray, "proxy"))
        self.assertEqual(singbox_categories(direct_domains, "geosite-"),
                         xray_domain_categories(self.xray, "direct"))
        self.assertEqual(singbox_categories(direct_ips, "geoip-"),
                         xray_ip_categories(self.xray, "direct"))

    def test_dns_split_and_static_hosts_match_xray_default(self):
        xray_dns = self.xray["dns"]["servers"][0]["domains"]
        self.assertTrue(all(value.startswith("geosite:") for value in xray_dns))
        expected = [value.split(":", 1)[1] for value in xray_dns]

        dns_direct = next(rule for rule in self.singbox["dns"]["rules"]
                          if rule.get("server") == "dns-yandex")
        self.assertEqual(singbox_categories(dns_direct, "geosite-"), expected)

        hosts = next(server for server in self.singbox["dns"]["servers"]
                     if server.get("tag") == "dns-hosts")
        self.assertEqual(hosts["predefined"], self.xray["dns"]["hosts"])

    def test_route_order_and_runtime_choices(self):
        actions = [(rule.get("action"), rule.get("outbound"),
                    rule.get("server"), tuple(rule.get("rule_set", [])))
                   for rule in self.route_rules if rule.get("rule_set")]
        self.assertEqual(actions[0][1], "block")
        self.assertEqual(actions[1][1], "proxy")
        self.assertEqual(actions[2][1], "direct")
        self.assertIn("geosite-spotify", actions[2][3])
        self.assertEqual(actions[3][1], "direct")
        self.assertIn("geoip-direct", actions[3][3])

        resolve = next(rule for rule in self.route_rules
                       if rule.get("action") == "resolve")
        self.assertEqual(resolve["server"], "dns-google")
        self.assertEqual(self.singbox["route"]["final"], "proxy")
        self.assertTrue(self.singbox["route"]["auto_detect_interface"])

        self.assertEqual(self.singbox["dns"]["strategy"], "ipv4_only")
        fakeip = next(server for server in self.singbox["dns"]["servers"]
                      if server.get("type") == "fakeip")
        self.assertEqual(fakeip["inet4_range"], "198.18.0.0/15")
        self.assertNotIn("inet6_range", fakeip)

        tun = next(inbound for inbound in self.singbox["inbounds"]
                   if inbound.get("type") == "tun")
        self.assertEqual(tun["address"], ["172.19.0.1/30"])
        self.assertFalse(any(":" in address for address in tun["address"]))

        urltest = next(outbound for outbound in self.singbox["outbounds"]
                       if outbound.get("type") == "urltest")
        self.assertEqual(urltest["tag"], "Auto")
        self.assertEqual(urltest["interval"], "5m")
        self.assertEqual(urltest["tolerance"], 150)

        selector = next(outbound for outbound in self.singbox["outbounds"]
                        if outbound.get("type") == "selector")
        self.assertEqual(selector["tag"], "proxy")
        self.assertEqual(selector["default"], "Auto")
        self.assertTrue(selector["interrupt_exist_connections"])

    def test_rule_set_urls_are_pinned_and_complete(self):
        referenced = set()
        for rule in self.singbox["dns"]["rules"]:
            referenced.update(rule.get("rule_set", []))
        for rule in self.route_rules:
            referenced.update(rule.get("rule_set", []))
        self.assertEqual(referenced, set(self.rule_sets))

        shas = {}
        for tag, rule_set in self.rule_sets.items():
            self.assertEqual(rule_set["type"], "remote")
            self.assertEqual(rule_set["format"], "binary")
            self.assertEqual(rule_set["download_detour"], "direct")
            match = URL_RE.fullmatch(rule_set["url"])
            self.assertIsNotNone(match, rule_set["url"])
            self.assertEqual(match.group("kind"), tag.split("-", 1)[0])
            self.assertEqual(match.group("category"), tag.split("-", 1)[1])
            shas.setdefault(match.group("kind"), set()).add(match.group("sha"))
        self.assertEqual(len(shas["geosite"]), 1)
        self.assertEqual(len(shas["geoip"]), 1)
        self.assertEqual(len(self.rule_sets), 25)

    def test_response_rule_is_ordered_and_scoped_to_singbox_clients(self):
        rules = json.loads(RESPONSE_RULES_PATH.read_text())["rules"]
        names = [rule["name"] for rule in rules]
        self.assertLess(names.index("THRONE"), names.index("SINGBOX"))
        self.assertLess(names.index("SINGBOX"), names.index("Fallback Base64"))
        rule = rules[names.index("SINGBOX")]
        self.assertEqual(rule["responseType"], "SINGBOX")
        self.assertEqual(rule["responseModifications"]["subscriptionTemplate"],
                         "Default Singbox")
        self.assertIn("V2RAYTUN_ONLY",
                      rule["responseModifications"]["excludeHostsByTags"])
        condition = rule["conditions"][0]
        self.assertEqual(condition["headerName"], "user-agent")
        self.assertEqual(condition["operator"], "REGEX")
        self.assertFalse(condition["caseSensitive"])
        for expected in ("sfa", "sfi", "sfm", "sft", "karing", "sing-box"):
            self.assertIn(expected, condition["value"])

    def test_url_rewriter_pins_release_paths(self):
        module = load_update_module()
        shas = {"geosite": "a" * 40, "geoip": "b" * 40}
        old = ("https://cdn.jsdelivr.net/gh/losogudok/freemanvpn-geosite"
               "@" + "1" * 40 + "/release/sing-box/youtube.srs")
        self.assertEqual(
            module.rewrite_url(old, shas),
            "https://cdn.jsdelivr.net/gh/losogudok/freemanvpn-geosite"
            "@" + "a" * 40 + "/sing-box/youtube.srs",
        )
        with self.assertRaises(ValueError):
            module.rewrite_url("https://example.invalid/youtube.srs", shas)

        document = copy.deepcopy(self.singbox)
        self.assertEqual(module.rewrite_document(document, shas), 25)
        urls = [rule_set["url"] for rule_set in document["route"]["rule_set"]]
        self.assertTrue(all("/sing-box/" in url for url in urls))
        self.assertTrue(all("/release/sing-box/" not in url for url in urls))
        self.assertTrue(all(("@" + "a" * 40) in url for url in urls
                            if "freemanvpn-geosite" in url))
        self.assertTrue(all(("@" + "b" * 40) in url for url in urls
                            if "freemanvpn-geoip" in url))

    def test_url_rewriter_check_mode_detects_stale_pins(self):
        first = next(iter(self.rule_sets.values()))
        match = URL_RE.fullmatch(first["url"])
        geosite_sha = geoip_sha = match.group("sha")
        for rule_set in self.rule_sets.values():
            match = URL_RE.fullmatch(rule_set["url"])
            if match.group("kind") == "geosite":
                geosite_sha = match.group("sha")
            else:
                geoip_sha = match.group("sha")

        current = subprocess.run(
            [sys.executable, str(UPDATE_SCRIPT), "--check",
             "--geosite-sha", geosite_sha, "--geoip-sha", geoip_sha,
             str(SINGBOX_PATH)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(current.returncode, 0, current.stderr)

        stale = subprocess.run(
            [sys.executable, str(UPDATE_SCRIPT), "--check",
             "--geosite-sha", "0" * 40, "--geoip-sha", geoip_sha,
             str(SINGBOX_PATH)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(stale.returncode, 1, stale.stderr)

    def test_rendered_config_passes_singbox_check(self):
        binary = shutil.which("sing-box")
        if binary is None:
            self.skipTest("sing-box is not installed")
        document = copy.deepcopy(self.singbox)
        for rule_set in document["route"]["rule_set"]:
            tag = rule_set["tag"]
            if tag.startswith("geoip-"):
                rules = [{"ip_cidr": ["203.0.113.0/24"]}]
            else:
                rules = [{"domain_suffix": ["example.invalid"]}]
            rule_set.clear()
            rule_set.update({"type": "inline", "tag": tag, "rules": rules})
        document["outbounds"].append({
            "type": "socks", "tag": "test-proxy",
            "server": "127.0.0.1", "server_port": 1080,
        })
        for outbound in document["outbounds"]:
            if outbound.get("type") == "urltest":
                outbound["outbounds"] = ["test-proxy"]
            elif outbound.get("type") == "selector":
                outbound["outbounds"] = ["Auto", "test-proxy"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document))
            result = subprocess.run(
                [binary, "check", "-c", str(path)],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
