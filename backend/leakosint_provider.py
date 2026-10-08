"""Optional LeakOSINT provider for redacted exposure summaries.

The provider token is read from LEAKOSINT_TOKEN and is never returned to callers.
Raw records are never exposed by the API.
"""
import os
import re

import httpx

URL = "https://leakosintapi.com/"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE = re.compile(r"^\+?[1-9]\d{7,14}$")
SECRET_FIELD = re.compile(r"(password|passwd|pass|token|secret|api.?key|cookie|session|hash|salt|ssn|credit|card|cvv)", re.I)
EMAIL_VALUE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_VALUE = re.compile(r"^\+?[\d\s().-]{8,}$")


def configured():
    return bool(os.getenv("LEAKOSINT_TOKEN", "").strip())


def validate_query(kind, value):
    value = value.strip()
    if kind == "email" and not EMAIL.fullmatch(value):
        raise ValueError("Enter a valid email address")
    if kind == "phone":
        compact = re.sub(r"[\s().-]", "", value)
        if not PHONE.fullmatch(compact):
            raise ValueError("Enter a phone number with country code, for example +919876543210")
        value = compact
    return value


def redact_value(field, value):
    text = str(value)
    if SECRET_FIELD.search(field):
        return "[REDACTED]"
    if EMAIL_VALUE.fullmatch(text):
        name, domain = text.split("@", 1)
        return (name[:1] + "***@" + domain) if name else "***@" + domain
    if PHONE_VALUE.fullmatch(text):
        digits = re.sub(r"\D", "", text)
        return ("+" if text.startswith("+") else "") + "*" * max(0, len(digits) - 4) + digits[-4:]
    if len(text) > 32:
        return text[:12] + "…" + text[-8:]
    return text


async def search(kind, value):
    if not configured():
        raise RuntimeError("Advanced exposure checking is not configured yet")
    query = validate_query(kind, value)
    payload = {"token": os.environ["LEAKOSINT_TOKEN"], "request": query, "limit": 100, "lang": "en", "type": "json"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(URL, json=payload)
        response.raise_for_status()
        result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("The exposure provider returned an invalid response")
    if "Error code" in result:
        raise RuntimeError("The exposure provider rejected the request")
    sources = []
    record_count = 0
    for name, database in (result.get("List") or {}).items():
        if name == "No results found":
            continue
        if not isinstance(database, dict):
            continue
        rows = database.get("Data") or []
        samples = []
        fields = set()
        for row in rows[:3]:
            if not isinstance(row, dict):
                continue
            sample = {}
            for field, item in row.items():
                field_name = str(field)[:80]
                fields.add(field_name)
                sample[field_name] = redact_value(field_name, item)
            samples.append(sample)
        sources.append({"name": str(name)[:120], "info": str(database.get("InfoLeak") or "")[:240],
                        "records": len(rows), "fields": sorted(fields), "samples": samples})
        record_count += len(rows)
    return {
        "kind": kind,
        "found": bool(sources),
        "source_count": len(sources),
        "record_count": record_count,
        "sources": sources[:30],
        "notice": "Values are redacted for safety. Passwords, tokens, hashes, and full personal identifiers are never displayed.",
    }
