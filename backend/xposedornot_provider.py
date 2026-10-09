"""XposedOrNot fallback for email breach metadata.

This provider is used only when the primary LeakOSINT provider fails. It
returns breach metadata and exposed categories, never recovered credentials.
"""
import re
from urllib.parse import quote

import httpx

BASE_URL = "https://api.xposedornot.com/v1"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value):
    value = value.strip().lower()
    if not EMAIL.fullmatch(value):
        raise ValueError("Enter a valid email address")
    return value


async def _get(client, path, params=None):
    try:
        response = await client.get(BASE_URL + path, params=params)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("The backup email exposure provider could not be reached") from exc
    if not isinstance(data, dict):
        raise RuntimeError("The backup email exposure provider returned an invalid response")
    return data


async def search_email(value):
    email = _validate_email(value)
    headers = {"User-Agent": "DFIS/1.0"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), headers=headers) as client:
        check = await _get(client, "/check-email/" + quote(email, safe=""))
        if check.get("status") != "success":
            raise RuntimeError("The backup email exposure provider rejected the request")
        breach_ids = check.get("breaches") or []
        if breach_ids and isinstance(breach_ids[0], list):
            breach_ids = breach_ids[0]
        if not isinstance(breach_ids, list):
            raise RuntimeError("The backup email exposure provider returned invalid breach data")

        sources = []
        for breach_id in breach_ids[:30]:
            if not isinstance(breach_id, str) or not breach_id.strip():
                continue
            details = await _get(client, "/breaches", {"breach_id": breach_id})
            exposed = details.get("exposedBreaches") or []
            if not exposed or not isinstance(exposed[0], dict):
                continue
            breach = exposed[0]
            fields = [str(field)[:80] for field in breach.get("exposedData") or []]
            records = breach.get("exposedRecords")
            sources.append({
                "name": str(breach.get("breachID") or breach_id)[:120],
                "info": _description(breach),
                "records": records if isinstance(records, int) else 0,
                "fields": sorted(set(fields)),
                "samples": [],
            })

    return {
        "kind": "email",
        "found": bool(sources),
        "source_count": len(sources),
        "record_count": sum(source["records"] for source in sources),
        "sources": sources,
        "provider": "XposedOrNot backup",
        "notice": (
            "LeakOSINT was unavailable, so XposedOrNot breach metadata was used as a backup. "
            "Only breach details and exposed categories are shown; credentials are never displayed."
        ),
    }


def _description(breach):
    parts = [
        breach.get("domain"),
        breach.get("industry"),
        breach.get("breachedDate"),
    ]
    return " · ".join(str(part) for part in parts if part)[:240]
