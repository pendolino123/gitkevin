#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path("results")
OUT.mkdir(exist_ok=True)
packages = ["@velora-dex/widget", "@velora-dex/sdk"]
results = []

for package in packages:
    url = "https://registry.npmjs.org/" + quote(package, safe="")
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": "b20-route-research/3"},
            timeout=45,
        )
        raw = response.content
        item = {
            "package": package,
            "url": url,
            "status": response.status_code,
            "reason": response.reason,
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "body_length": len(raw),
        }
        try:
            data = response.json()
        except Exception:
            data = None
        if isinstance(data, dict):
            latest = (data.get("dist-tags") or {}).get("latest")
            version = (data.get("versions") or {}).get(latest, {}) if latest else {}
            item.update({
                "latest": latest,
                "latest_published_at": (data.get("time") or {}).get(latest),
                "modified_at": (data.get("time") or {}).get("modified"),
                "license": version.get("license") or data.get("license"),
                "deprecated": version.get("deprecated"),
                "repository": version.get("repository") or data.get("repository"),
                "homepage": version.get("homepage") or data.get("homepage"),
            })
        else:
            item["body"] = raw.decode("utf-8", errors="replace")
        results.append(item)
    except Exception as exc:
        results.append({"package": package, "url": url, "exception": type(exc).__name__, "message": str(exc)})

report = {
    "tested_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "packages": results,
}
(OUT / "velora-widget-metadata.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
