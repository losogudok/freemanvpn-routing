#!/usr/bin/env python3
"""Pin the sing-box remote rule-set URLs to FreemanVPN release commits.

The geo repositories publish their sing-box artifacts on the `release`
branch. Pinning the commit SHA makes the routing payload reproducible; the
update workflow advances every URL in one commit when a new release appears.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


RELEASE_BRANCH = "release"
REPOS = {
    "geosite": "losogudok/freemanvpn-geosite",
    "geoip": "losogudok/freemanvpn-geoip",
}
URL_PREFIX = "https://cdn.jsdelivr.net/gh/losogudok/freemanvpn-"
URL_RE = re.compile(
    r"^https://cdn\.jsdelivr\.net/gh/losogudok/freemanvpn-(?P<kind>geosite|geoip)"
    r"(?:@[0-9a-f]{40})?/(?:release/)?sing-box/"
    r"(?P<category>[A-Za-z0-9_-]+)\.srs$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def latest_release_sha(repo):
    """Return the current commit of a geo repository's release branch."""
    result = subprocess.run(
        ["git", "ls-remote", f"https://github.com/{repo}.git",
         f"refs/heads/{RELEASE_BRANCH}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    line = result.stdout.strip()
    if not line:
        raise ValueError(f"no {RELEASE_BRANCH} branch found for {repo}")
    sha = line.split()[0]
    if not SHA_RE.fullmatch(sha):
        raise ValueError(f"invalid release commit for {repo}: {sha!r}")
    return sha


def canonical_url(kind, sha, category):
    return (
        f"https://cdn.jsdelivr.net/gh/losogudok/freemanvpn-{kind}"
        f"@{sha}/sing-box/{category}.srs"
    )


def rewrite_url(url, shas):
    match = URL_RE.fullmatch(url)
    if match is None:
        raise ValueError(f"not a FreemanVPN sing-box rule-set URL: {url}")
    return canonical_url(match.group("kind"), shas[match.group("kind")],
                         match.group("category"))


def walk_urls(value):
    """Yield (parent, key, url) for every rule-set URL in a JSON value."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str) and item.startswith(URL_PREFIX):
                yield value, key, item
            else:
                yield from walk_urls(item)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, str) and item.startswith(URL_PREFIX):
                yield value, index, item
            else:
                yield from walk_urls(item)


def rewrite_document(document, shas):
    """Rewrite all pinned URLs in place and return the number of changes."""
    changes = 0
    for parent, key, url in list(walk_urls(document)):
        replacement = rewrite_url(url, shas)
        if replacement != url:
            parent[key] = replacement
            changes += 1
    return changes


def document_urls(document):
    return [url for _, _, url in walk_urls(document)]


def verify_url(url):
    """Confirm that a pinned URL serves a binary sing-box rule set."""
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "freemanvpn-routing/1"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError(f"{url}: HTTP {response.status}")
                magic = response.read(3)
                if magic != b"SRS":
                    raise RuntimeError(
                        f"{url}: expected an SRS rule set, got {magic!r}"
                    )
                return
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if attempt == 2:
                raise RuntimeError(f"{url}: {error}") from error
            time.sleep(2)


def resolve_shas(args):
    shas = {}
    for kind, repo in REPOS.items():
        pinned = getattr(args, f"{kind}_sha")
        if pinned:
            if not SHA_RE.fullmatch(pinned):
                raise ValueError(f"--{kind}-sha must be a 40-character commit SHA")
            shas[kind] = pinned
        else:
            shas[kind] = latest_release_sha(repo)
    return shas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path("SINGBOX/DEFAULT.JSON"),
        help="sing-box template to update (default: SINGBOX/DEFAULT.JSON)",
    )
    parser.add_argument("--geosite-sha", help="pin the geosite release commit")
    parser.add_argument("--geoip-sha", help="pin the geoip release commit")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the file is not pinned to the current release commits",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip HTTP HEAD verification of each rule-set URL",
    )
    args = parser.parse_args()

    try:
        document = json.loads(args.path.read_text(encoding="utf-8"))
        shas = resolve_shas(args)
        changes = rewrite_document(document, shas)
        urls = document_urls(document)
        if not urls:
            raise ValueError("template contains no FreemanVPN sing-box rule-set URLs")
        if args.check:
            if changes:
                print(
                    f"{args.path}: {changes} URL(s) are not pinned to the current "
                    f"release commits",
                    file=sys.stderr,
                )
                return 1
            print(f"{args.path}: pinned URLs are current ({len(urls)} rule sets)")
            return 0
        if not args.no_verify:
            for url in urls:
                verify_url(url)
        if changes:
            args.path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        print(
            f"{args.path}: {len(urls)} rule-set URL(s), {changes} updated "
            f"(geosite {shas['geosite']}, geoip {shas['geoip']})"
        )
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"{parser.prog}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
