#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path

import requests

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
NVDAC = "0xb20000000000000000000078ee7ce2fE4908108C"
USER = "0x1111111111111111111111111111111111111111"
AMOUNT = "100000000"  # 100 USDC, 6 decimals

OUT = Path("results")
OUT.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "identity",
    "User-Agent": "b20-route-research/2026-08-25",
})


def request_record(name, method, url, *, headers=None, body=None, params=None, timeout=35):
    started = time.time()
    rec = {
        "name": name,
        "method": method,
        "url": url,
        "params": params,
        "request_headers": headers or {},
        "request_json": body,
    }
    try:
        resp = session.request(
            method,
            url,
            headers=headers,
            json=body,
            params=params,
            timeout=timeout,
            allow_redirects=True,
        )
        raw = resp.content
        text = raw.decode(resp.encoding or "utf-8", errors="replace")
        rec.update({
            "final_url": resp.url,
            "status": resp.status_code,
            "reason": resp.reason,
            "elapsed_ms": round((time.time() - started) * 1000),
            "response_headers": dict(resp.headers),
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "body_length": len(raw),
            "body": text,
        })
        try:
            rec["json"] = resp.json()
        except Exception:
            rec["json"] = None
    except Exception as exc:
        rec.update({
            "status": None,
            "elapsed_ms": round((time.time() - started) * 1000),
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        })
    return rec


calls = []

calls.append(request_record(
    "LI.FI quote",
    "GET",
    "https://li.quest/v1/quote",
    params={
        "fromChain": "8453",
        "toChain": "8453",
        "fromToken": USDC,
        "toToken": NVDAC,
        "fromAmount": AMOUNT,
        "fromAddress": USER,
        "toAddress": USER,
        "slippage": "0.005",
    },
))

calls.append(request_record(
    "KyberSwap routes",
    "GET",
    "https://aggregator-api.kyberswap.com/base/api/v1/routes",
    params={
        "tokenIn": USDC,
        "tokenOut": NVDAC,
        "amountIn": AMOUNT,
        "gasInclude": "true",
        "saveGas": "false",
    },
    headers={"x-client-id": "b20-route-research"},
))

calls.append(request_record(
    "0x allowance-holder quote",
    "GET",
    "https://api.0x.org/swap/allowance-holder/quote",
    params={
        "chainId": "8453",
        "sellToken": USDC,
        "buyToken": NVDAC,
        "sellAmount": AMOUNT,
        "taker": USER,
        "slippageBps": "50",
    },
    headers={"0x-version": "v2"},
))

for chain_key in ("base", "8453"):
    calls.append(request_record(
        f"OpenOcean v4 quote ({chain_key})",
        "GET",
        f"https://open-api.openocean.finance/v4/{chain_key}/quote",
        params={
            "inTokenAddress": USDC,
            "outTokenAddress": NVDAC,
            "amountDecimals": AMOUNT,
            "gasPriceDecimals": "1000000",
            "slippage": "0.5",
        },
    ))

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
calls.append(request_record(
    "Odos SOR quote v2",
    "POST",
    "https://api.odos.xyz/sor/quote/v2",
    body=odos_body,
    headers={"Content-Type": "application/json"},
))

for host in ("https://api.paraswap.io", "https://api.velora.xyz"):
    calls.append(request_record(
        f"ParaSwap/Velora prices ({host})",
        "GET",
        f"{host}/prices",
        params={
            "srcToken": USDC,
            "destToken": NVDAC,
            "amount": AMOUNT,
            "srcDecimals": "6",
            "side": "SELL",
            "network": "8453",
            "version": "6.2",
            "userAddress": USER,
            "maxImpact": "100",
        },
    ))

uniswap_body = {
    "type": "EXACT_INPUT",
    "amount": AMOUNT,
    "tokenInChainId": 8453,
    "tokenOutChainId": 8453,
    "tokenIn": USDC,
    "tokenOut": NVDAC,
    "swapper": USER,
    "slippageTolerance": 0.5,
    "routingPreference": "BEST_PRICE",
}
calls.append(request_record(
    "Uniswap Trading API quote",
    "POST",
    "https://trade-api.gateway.uniswap.org/v1/quote",
    body=uniswap_body,
    headers={
        "Content-Type": "application/json",
        "x-universal-router-version": "2.0",
    },
))

# Secondary discovery calls used to corroborate negative route findings.
calls.append(request_record(
    "LI.FI token lookup NVDAc",
    "GET",
    f"https://li.quest/v1/token/8453/{NVDAC}",
))
calls.append(request_record(
    "KyberSwap token list search",
    "GET",
    "https://aggregator-api.kyberswap.com/base/api/v1/tokens",
    params={"ids": NVDAC},
))
calls.append(request_record(
    "OpenOcean token list Base",
    "GET",
    "https://open-api.openocean.finance/v4/base/tokenList",
))
calls.append(request_record(
    "ParaSwap token list Base",
    "GET",
    "https://api.paraswap.io/tokens/8453",
))

report = {
    "tested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "chain_id": 8453,
    "pair": {
        "sell_token": USDC,
        "buy_token": NVDAC,
        "sell_amount_raw": AMOUNT,
        "sell_amount_display": "100 USDC",
        "taker": USER,
    },
    "calls": calls,
}

(OUT / "http-quotes.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({
    "tested_at_utc": report["tested_at_utc"],
    "calls": [{"name": c["name"], "status": c.get("status"), "length": c.get("body_length"), "exception": c.get("exception")} for c in calls],
}, indent=2))
