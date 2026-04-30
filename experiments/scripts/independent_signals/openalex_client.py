"""Small cached OpenAlex client for independent-signal diagnostics."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from experiments.scripts.independent_signals.common import IdentifierInfo, parse_identifier

USER_AGENT = "MetaScreener/2.0"


def openalex_api_url(info: IdentifierInfo) -> str | None:
    """Build an OpenAlex work endpoint URL from a supported identifier."""
    if info.kind == "openalex":
        return f"https://api.openalex.org/works/{urllib.parse.quote(info.value)}"
    if info.kind == "pmid":
        return f"https://api.openalex.org/works/pmid:{urllib.parse.quote(info.value)}"
    if info.kind == "doi":
        return "https://api.openalex.org/works/doi:" + urllib.parse.quote(info.value, safe="")
    return None


def cache_key_for_record_id(record_id: str) -> str:
    """Return a stable filesystem-safe cache key for one record ID."""
    parsed = parse_identifier(record_id)
    raw = f"{parsed.kind}_{parsed.value or 'missing'}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_") or "missing"


def fetch_work_payload(
    *,
    record_id: str,
    cache_dir: Path,
    timeout_s: float,
    sleep_s: float = 0.1,
) -> tuple[dict[str, Any] | None, str]:
    """Fetch one OpenAlex work, using a JSON cache before network."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key_for_record_id(record_id)}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text())
        return (payload if payload.get("_status") == "ok" else None), "cache"

    parsed = parse_identifier(record_id)
    url = openalex_api_url(parsed)
    if not url:
        cache_path.write_text(
            json.dumps({"_status": "not_queryable", "record_id": record_id}) + "\n",
            encoding="utf-8",
        )
        return None, "not_queryable"

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        cache_path.write_text(
            json.dumps({"_status": f"http_{exc.code}", "record_id": record_id}) + "\n",
            encoding="utf-8",
        )
        return None, f"http_{exc.code}"
    except Exception as exc:
        cache_path.write_text(
            json.dumps({"_status": type(exc).__name__, "record_id": record_id}) + "\n",
            encoding="utf-8",
        )
        return None, type(exc).__name__

    payload["_status"] = "ok"
    cache_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    if sleep_s > 0:
        time.sleep(sleep_s)
    return payload, "network"


def metadata_text(payload: dict[str, Any]) -> str:
    """Extract non-title metadata terms from one OpenAlex work payload."""
    parts: list[str] = []
    for key in ["type", "language"]:
        if payload.get(key):
            parts.append(str(payload[key]))
    source = ((payload.get("primary_location") or {}).get("source") or {}).get("display_name")
    if source:
        parts.append(str(source))
    primary_topic = payload.get("primary_topic") or {}
    if primary_topic.get("display_name"):
        parts.append(str(primary_topic["display_name"]))
    for item in payload.get("topics") or []:
        if item.get("display_name"):
            parts.append(str(item["display_name"]))
    for item in payload.get("concepts") or []:
        if item.get("display_name"):
            parts.append(str(item["display_name"]))
    for item in payload.get("mesh") or []:
        if item.get("descriptor_name"):
            parts.append(str(item["descriptor_name"]))
        if item.get("qualifier_name"):
            parts.append(str(item["qualifier_name"]))
    for item in payload.get("keywords") or []:
        if item.get("display_name"):
            parts.append(str(item["display_name"]))
        elif item.get("keyword"):
            parts.append(str(item["keyword"]))
    return " ".join(parts)


def citation_sets(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Return referenced and related OpenAlex work IDs from payload."""
    referenced = {str(item) for item in payload.get("referenced_works") or []}
    related = {str(item) for item in payload.get("related_works") or []}
    return referenced, related
