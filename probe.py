#!/usr/bin/env python3
"""residential-probe — Is your residential proxy silently blocking services?

Some proxy providers block specific domains at the proxy layer (you get a
SOCKS5 "connection not allowed" error while everything else looks fine).
We found this the hard way: a major provider silently blocks *.stripe.com,
which killed every payment flow while all other sites worked.

This tool sends real requests THROUGH your proxy to a checklist of services
and classifies each result:

  OK      = a real HTTP response came back (any status — even 401/403/404
            means the request REACHED the service; e.g. a Cloudflare 403
            challenge on a homepage is a sign of life, not a block)
  BLOCKED = the proxy itself refused the connection (SOCKS5 error / curl 97)
            or the transport failed — this is the silent-block signature
  SLOW    = connected (or not) but timed out

Usage:
  RESIP_PROXY="socks5h://user:pass@host:port" python3 probe.py
  python3 probe.py --proxy "socks5h://user:pass@host:port"
  python3 probe.py --proxy "http://host:port" --json

Exit code: 0 = nothing blocked, 1 = at least one service blocked, 2 = usage.

No third-party dependencies; requires `curl` on PATH.
"""
import argparse
import json
import subprocess
import sys

# (label, url, why it matters)
TARGETS = [
    ("Exit-IP self-check", "https://ipinfo.io/json", "Exit IP / country / ASN sanity"),
    ("Claude web", "https://claude.ai", ""),
    ("Claude API", "https://api.anthropic.com", ""),
    ("LinkedIn", "https://www.linkedin.com", ""),
    ("Sentry ingest", "https://o0.ingest.sentry.io", "Telemetry — fingerprint trail"),
    ("Datadog intake", "https://browser-intake-datadoghq.com", "Telemetry — fingerprint trail"),
    ("Segment API", "https://api.segment.io", "Analytics — fingerprint trail"),
    ("Sift", "https://sift.com", "Fraud / device fingerprinting"),
    ("ChatGPT", "https://chatgpt.com", ""),
    ("OpenAI API", "https://api.openai.com", ""),
    ("Stripe JS", "https://js.stripe.com", "The classic silent block"),
    ("Stripe API", "https://api.stripe.com", ""),
    ("Stripe Checkout", "https://checkout.stripe.com", ""),
    ("PayPal", "https://www.paypal.com", ""),
    ("Google 204", "https://www.google.com/generate_204", "Baseline connectivity"),
    ("GitHub", "https://github.com", ""),
    ("X (Twitter)", "https://x.com", ""),
    ("YouTube", "https://www.youtube.com", ""),
]


def curl(proxy: str, url: str, timeout: int, body: bool = False):
    args = ["curl", "-sS", "--max-time", str(timeout), "--proxy", proxy]
    if not body:
        args += ["-o", "/dev/null", "-w", "%{http_code} %{time_total}"]
    args.append(url)
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout + 10)


def probe(proxy: str, url: str, timeout: int = 20):
    """Return (status_class, detail)."""
    try:
        out = curl(proxy, url, timeout)
        parts = out.stdout.strip().split()
        if out.returncode == 0 and parts and parts[0] != "000":
            return "OK", f"HTTP {parts[0]} · {parts[1]}s"
        err = (out.stderr or "").strip()
        if out.returncode == 28:
            return "SLOW", "timeout (no response)"
        if out.returncode == 97 or "SOCKS5" in err:
            return "BLOCKED", f"proxy refused (curl {out.returncode})"
        return "BLOCKED", f"transport failure (curl {out.returncode}) {err[:60]}"
    except subprocess.TimeoutExpired:
        return "SLOW", "overall timeout"


def exit_ip(proxy: str):
    try:
        out = curl(proxy, "https://ipinfo.io/json", 20, body=True)
        info = json.loads(out.stdout)
        return f"{info.get('ip')} · {info.get('city')}, {info.get('region')}, {info.get('country')} · {info.get('org')}"
    except Exception as e:  # noqa: BLE001
        return f"self-check failed: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe a residential proxy against a service checklist.")
    ap.add_argument("--proxy", required=True, help="Proxy URL, e.g. socks5h://user:pass@host:port")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    ap.add_argument("--timeout", type=int, default=20, help="Per-request timeout in seconds (default 20)")
    args = ap.parse_args()

    proxy = args.proxy
    host_hint = proxy.split("@")[-1] if "@" in proxy else proxy

    results = []
    exit_info = None
    for label, url, why in TARGETS:
        if "ipinfo" in url:
            exit_info = exit_ip(proxy)
            continue
        cls, detail = probe(proxy, url, args.timeout)
        results.append({"service": label, "url": url, "status": cls, "detail": detail, "why": why})

    blocked = [r["service"] for r in results if r["status"] == "BLOCKED"]
    slow = [r["service"] for r in results if r["status"] == "SLOW"]
    ok_count = sum(1 for r in results if r["status"] == "OK")

    if args.json:
        print(json.dumps(
            {"proxy": host_hint, "exit_ip": exit_info, "passed": ok_count, "total": len(results),
             "blocked": blocked, "slow": slow, "results": results},
            ensure_ascii=False, indent=2))
    else:
        print(f"Probing residential exit: {host_hint}\n")
        print(f"Exit IP: {exit_info}\n")
        icons = {"OK": "✅", "BLOCKED": "❌", "SLOW": "⚠️"}
        for r in results:
            line = f"{icons.get(r['status'], '?')} {r['service']:18s} {r['detail']}"
            if r["why"]:
                line += f"  ← {r['why']}"
            print(line)
        print(f"\n=== Summary ===\nPassed {ok_count}/{len(results)}")
        if blocked:
            print(f"Blocked: {', '.join(blocked)}")
        if slow:
            print(f"Timed out: {', '.join(slow)}")
    return 0 if not blocked else 1


if __name__ == "__main__":
    sys.exit(main())
