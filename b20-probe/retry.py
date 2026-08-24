#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote

import requests

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
NVDAC = "0xb20000000000000000000078ee7ce2fE4908108C"
USER = "0x1111111111111111111111111111111111111111"
AMOUNT = "100000000"
OUT = Path("results")
OUT.mkdir(exist_ok=True)

s = requests.Session()
s.headers.update({
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "identity",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36 b20-route-research/2",
})


def call(name, method, url, *, params=None, headers=None, body=None, timeout=45):
    t = time.time()
    rec = {"name": name, "method": method, "url": url, "params": params, "request_headers": headers or {}, "request_json": body}
    try:
        r = s.request(method, url, params=params, headers=headers, json=body, timeout=timeout, allow_redirects=True)
        raw = r.content
        txt = raw.decode(r.encoding or "utf-8", errors="replace")
        rec.update({
            "final_url": r.url,
            "status": r.status_code,
            "reason": r.reason,
            "elapsed_ms": round((time.time()-t)*1000),
            "response_headers": dict(r.headers),
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "body_length": len(raw),
            "body": txt,
        })
        try: rec["json"] = r.json()
        except Exception: rec["json"] = None
    except Exception as e:
        rec.update({"status": None, "elapsed_ms": round((time.time()-t)*1000), "exception_type": type(e).__name__, "exception": str(e)})
    return rec

calls = []

para_params = {
    "srcToken": USDC,
    "destToken": NVDAC,
    "amount": AMOUNT,
    "srcDecimals": "6",
    "destDecimals": "8",
    "side": "SELL",
    "network": "8453",
    "version": "6.2",
    "userAddress": USER,
    "maxImpact": "100",
}
for host in ("https://api.paraswap.io", "https://api.velora.xyz"):
    calls.append(call(f"ParaSwap/Velora corrected ({host})", "GET", f"{host}/prices", params=para_params))

# Retry Odos after the first run encountered owner-side Cloudflare Tunnel error 1033.
odos_body = {
    "chainId": 8453,
    "inputTokens": [{"tokenAddress": USDC, "amount": AMOUNT}],
    "outputTokens": [{"tokenAddress": NVDAC, "proportion": 1}],
    "userAddr": USER,
    "slippageLimitPercent": 0.5,
    "disableRFQs": True,
    "compact": True,
    "referralCode": 0,
}
for attempt in range(1, 4):
    rec = call(f"Odos quote retry {attempt}", "POST", "https://api.odos.xyz/sor/quote/v2", body=odos_body, headers={"Content-Type": "application/json"})
    calls.append(rec)
    if rec.get("status") != 530:
        break
    time.sleep(15)
calls.append(call("Odos chain health", "GET", "https://api.odos.xyz/info/chains"))

browser_headers = {
    "Origin": "https://openocean.finance",
    "Referer": "https://openocean.finance/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}
oo_v4 = {
    "inTokenAddress": USDC,
    "outTokenAddress": NVDAC,
    "amountDecimals": AMOUNT,
    "gasPriceDecimals": "6000000",
    "slippage": "0.5",
}
calls.append(call("OpenOcean V4 browser headers", "GET", "https://open-api.openocean.finance/v4/base/quote", params=oo_v4, headers=browser_headers))
calls.append(call("OpenOcean V4 enterprise host no key", "GET", "https://open-api-enterprise.openocean.finance/v4/base/quote", params=oo_v4, headers=browser_headers))
calls.append(call("OpenOcean V3 quote", "GET", "https://open-api.openocean.finance/v3/base/quote", params={
    "inTokenAddress": USDC,
    "outTokenAddress": NVDAC,
    "amount": "100",
    "gasPrice": "0.006",
    "slippage": "0.5",
}, headers=browser_headers))
calls.append(call("OpenOcean Base dexList", "GET", "https://open-api.openocean.finance/v4/base/dexList"))

# Verify Kyber fee fields are accepted by the same public route endpoint.
calls.append(call("KyberSwap route with 50 bps integrator fee", "GET", "https://aggregator-api.kyberswap.com/base/api/v1/routes", params={
    "tokenIn": USDC,
    "tokenOut": NVDAC,
    "amountIn": AMOUNT,
    "gasInclude": "true",
    "saveGas": "false",
    "feeAmount": "50",
    "chargeFeeBy": "currency_in",
    "isInBps": "true",
    "feeReceiver": USER,
}, headers={"x-client-id": "b20-route-research"}))

report = {
    "tested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "chain_id": 8453,
    "pair": {"sell_token": USDC, "buy_token": NVDAC, "sell_amount_raw": AMOUNT, "sell_amount_display": "100 USDC"},
    "calls": calls,
}
(OUT / "retry-quotes.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

packages = [
    "@lifi/widget",
    "@kyberswap/widgets",
    "@openocean.finance/widget",
    "odos-widgets",
    "@paraswap/sdk",
    "@uniswap/widgets",
    "@0x/instant",
]
package_results = []
for package in packages:
    url = "https://registry.npmjs.org/" + quote(package, safe="")
    rec = call(f"npm {package}", "GET", url)
    summary = {"package": package, "status": rec.get("status"), "body_sha256": rec.get("body_sha256")}
    j = rec.get("json")
    if isinstance(j, dict):
        latest = (j.get("dist-tags") or {}).get("latest")
        v = (j.get("versions") or {}).get(latest, {}) if latest else {}
        summary.update({
            "latest": latest,
            "latest_published_at": (j.get("time") or {}).get(latest),
            "modified_at": (j.get("time") or {}).get("modified"),
            "license": v.get("license") or j.get("license"),
            "deprecated": v.get("deprecated"),
            "repository": v.get("repository") or j.get("repository"),
            "homepage": v.get("homepage") or j.get("homepage"),
        })
    else:
        summary["body"] = rec.get("body")
    package_results.append(summary)

pkg_report = {"tested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "packages": package_results}
(OUT / "package-metadata.json").write_text(json.dumps(pkg_report, indent=2, ensure_ascii=False), encoding="utf-8")

print(json.dumps({
    "calls": [{"name": c["name"], "status": c.get("status"), "length": c.get("body_length"), "exception": c.get("exception")} for c in calls],
    "packages": package_results,
}, indent=2))
