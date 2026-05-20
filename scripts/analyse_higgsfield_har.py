"""Reverse-engineer HiggsField's REST API from a HAR capture.

Reads a .har file, extracts only HiggsField-API requests (filters out
analytics, ad networks, static assets, browser noise), then prints a
sanitised dump where every header value, cookie, and obvious secret in
the body is replaced with the placeholder ``<REDACTED>``.

Use this so we can share API shape (URL, method, header names, payload
structure) without exposing your auth.

Usage:
    python scripts/analyse_higgsfield_har.py higgsfield.har
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Hosts we want to inspect. Everything else is dropped.
INTERESTING_HOSTS = ("higgsfield.ai", "api.higgsfield.ai")

# Hosts we definitely want to skip (analytics, error tracking, ad nets).
NOISE_HOSTS = (
    "amplitude.higgsfield.ai",  # Amplitude proxy
    "sentry",
    "datadoghq",
    "google-analytics",
    "googletagmanager",
    "doubleclick",
    "facebook.com/tr",
    "snowplowanalytics",
)

# Header NAMES whose VALUES we always redact.
SECRET_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-api-key-id",
    "x-api-key-secret",
    "x-auth-token",
    "x-csrf-token",
    "x-session-token",
}

# Body field NAMES whose VALUES we always redact (case-insensitive substring).
SECRET_BODY_FIELDS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "auth",
    "session",
    "device_id",
    "user_id",
    "email",
)


def is_interesting(url: str, method: str = "") -> bool:
    if any(noise in url for noise in NOISE_HOSTS):
        return False
    if not any(host in url for host in INTERESTING_HOSTS):
        return False
    # Skip CDN media and Cloudflare image proxies
    if "cdn.higgsfield.ai" in url:
        return False
    if "/cdn-cgi/" in url:
        return False
    if "/_next/" in url:
        return False
    if "/static/" in url:
        return False
    # Skip static asset extensions
    if re.search(r"\.(js|mjs|css|woff2?|svg|png|jpe?g|gif|ico|map|mp4|webm|webp|m3u8|ts|json5)(\?|$)", url):
        return False
    # Skip HTML page navigations
    if re.search(r"\.html?(\?|$)", url):
        return False
    # Strong positive signal: anything under /api/ or with POST/PUT/PATCH/DELETE
    if "/api/" in url:
        return True
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return True
    # GETs that return JSON tend to be API too — keep them if they're not media
    return True


def redact_headers(headers: list[dict]) -> list[dict]:
    out = []
    for h in headers:
        name = h.get("name", "")
        if name.lower() in SECRET_HEADER_NAMES:
            out.append({"name": name, "value": "<REDACTED>"})
        else:
            out.append({"name": name, "value": h.get("value", "")[:200]})
    return out


def redact_value(value):
    if isinstance(value, dict):
        return {k: redact_value(v) if any(s in k.lower() for s in SECRET_BODY_FIELDS) is False else "<REDACTED>"
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value[:5]]
    if isinstance(value, str) and len(value) > 200:
        return value[:100] + "...<truncated>"
    return value


def redact_body(body_text: str) -> str:
    if not body_text:
        return ""
    try:
        data = json.loads(body_text)
    except Exception:
        # Not JSON. Show shape only.
        return f"<non-JSON body, {len(body_text)} chars>"
    return json.dumps(redact_value(data), indent=2)[:1500]


def analyse(har_path: Path) -> None:
    har = json.loads(har_path.read_text(encoding="utf-8"))
    entries = har.get("log", {}).get("entries", [])
    interesting = [
        e for e in entries
        if is_interesting(e["request"]["url"], e["request"].get("method", ""))
    ]
    print(f"Total entries: {len(entries)}")
    print(f"HiggsField API entries (after filtering noise): {len(interesting)}")
    print("=" * 70)

    for i, entry in enumerate(interesting, 1):
        req = entry["request"]
        resp = entry["response"]
        print(f"\n[{i}] {req['method']} {req['url']}")
        print(f"    Status: {resp['status']} {resp.get('statusText', '')}")
        print(f"    Request headers:")
        for h in redact_headers(req.get("headers", [])):
            print(f"      {h['name']}: {h['value']}")
        post_data = req.get("postData", {})
        if post_data.get("text"):
            print(f"    Request body (redacted):")
            for line in redact_body(post_data["text"]).splitlines():
                print(f"      {line}")
        resp_content = resp.get("content", {}).get("text", "")
        if resp_content:
            print(f"    Response body (redacted, first 800 chars):")
            for line in redact_body(resp_content).splitlines()[:30]:
                print(f"      {line}")

    if not interesting:
        print("\nNo HiggsField API requests found in this HAR.")
        print("Make sure you actually clicked Generate while recording.")
        print("Check for requests to a different host. Sample of all hosts seen:")
        hosts = {}
        for e in entries:
            url = e["request"]["url"]
            host = re.match(r"https?://([^/]+)", url)
            if host:
                hosts[host.group(1)] = hosts.get(host.group(1), 0) + 1
        for host, n in sorted(hosts.items(), key=lambda x: -x[1])[:15]:
            print(f"  {host}: {n}")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/analyse_higgsfield_har.py <path-to-har>")
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 1
    analyse(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
