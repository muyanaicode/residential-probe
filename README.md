# residential-probe

**Is your residential proxy silently blocking services?**

Some proxy providers block specific domains *at the proxy layer* — the connection is refused by the proxy itself while everything else looks perfectly fine. We found this the hard way: a well-known static-residential provider silently blocks `*.stripe.com`. Every payment flow died; every other site worked. It took days to pin down because the failure looks like a Stripe problem, not a proxy problem.

This tool sends real requests **through** your proxy to a checklist of services and tells you which ones are blocked, before your users find out at checkout.

## Quick start

```bash
python3 probe.py --proxy "socks5h://user:pass@host:port"
```

No third-party dependencies. Requires `curl` on your PATH. Works with `socks5h://`, `socks5://` and `http://` proxies, with or without auth.

Example output:

```
Probing residential exit: 203.0.113.10:7236

Exit IP: 203.0.113.10 · Leesburg, Virginia, US · AS400072

✅ Claude web         HTTP 403 · 0.44s
✅ LinkedIn           HTTP 200 · 0.80s
✅ Sentry ingest      HTTP 404 · 0.57s
❌ Stripe JS          proxy refused (curl 97)  ← The classic silent block
❌ Stripe API         proxy refused (curl 97)
❌ Stripe Checkout    proxy refused (curl 97)
✅ PayPal             HTTP 200 · 0.81s
...

=== Summary ===
Passed 14/17
Blocked: Stripe JS, Stripe API, Stripe Checkout
```

## How to read the results

| Result | Meaning |
|---|---|
| ✅ OK (any HTTP status) | A real HTTP response came back — the request **reached** the service. Even `401` / `403` / `404` count: a Cloudflare `403` challenge on a homepage means the service saw your request; that's a sign of life, not a block. |
| ❌ BLOCKED (curl 97) | The **proxy itself refused** the connection (SOCKS5 error 2, "connection not allowed"). This is the silent-block signature — the request never left the proxy. |
| ⚠️ SLOW | Timeout. Line quality problem, or the service is stalling on your exit IP. |

The distinction that matters: **BLOCKED = your provider's policy, OK-with-403 = the service's bot check.** Different problems, different fixes.

## Options

```
--proxy URL     (required) e.g. socks5h://user:pass@host:port
--json          machine-readable output, for cron / CI / monitoring
--timeout N     per-request timeout in seconds (default 20)
```

Exit code: `0` = nothing blocked, `1` = at least one service blocked, `2` = usage error.

## What gets probed

Claude, LinkedIn, Sentry, Datadog, Segment, Sift, ChatGPT / OpenAI, Stripe (JS / API / Checkout), PayPal, Google, GitHub, X, YouTube — plus an exit-IP self-check (IP, city, country, ASN).

The list lives in `TARGETS` at the top of `probe.py`. Add your own services in one line each.

## Why telemetry services are on the list

If you run accounts that care about IP consistency (AI tools, social platforms), routing only the main site through your residential IP is not enough: error telemetry (Sentry), product analytics (Segment), RUM intake (Datadog) and fraud fingerprinting (Sift) all phone home from the same apps. If those go out through a datacenter/airport IP while the main traffic uses your residential IP, the account ends up with **two IP trails** — exactly the kind of inconsistency risk engines look for. Probe them, then route them the same way.

## License

MIT

---

## 中文说明

**你的住宅代理是不是在偷偷屏蔽某些服务？**

部分代理供应商会在代理层屏蔽特定域名：连接被代理本身拒绝，其他一切看起来都正常。我们就这么踩过坑——某知名静态住宅 IP 供应商静默屏蔽了 `*.stripe.com`，所有支付流程全挂，其他网站全好，排查了好几天，因为它看起来像 Stripe 的问题，而不是代理的问题。

本工具会拿你的代理通道，把关键服务**逐个真穿过去请求一遍**，在你的用户付款失败之前告诉你哪些被屏蔽了。

```bash
python3 probe.py --proxy "socks5h://用户名:密码@地址:端口"
```

读数要点：

- ✅ **收到任何真实 HTTP 响应 = 通**。哪怕是 403——那是对方的人机验证，说明请求到达了，是活的。
- ❌ **curl 97 = 代理层拒绝**，这就是"静默屏蔽"的指纹，请求根本没出代理。
- ⚠️ 超时 = 线路质量问题。

遥测类服务（Sentry / Datadog / Segment / Sift）也在清单里：主站走住宅 IP、这些上报走机房 IP，同一个账号就会留下**两条 IP 轨迹**，正是风控系统最爱抓的不一致。要测一起测，要走一起走。
