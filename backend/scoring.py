"""Scoring. Overall score follows the DFIS paper: S = 0.50*SB + 0.35*SP + 0.15*SD."""
import asyncio, re
from datetime import datetime, timezone
import httpx

JDM_URL = "https://raw.githubusercontent.com/jdm-contrib/jdm/master/_data/sites.json"
jdm: dict = {}
W = {"SB": .50, "SP": .35, "SD": .15}
KW = [("password", 45), ("credit", 50), ("bank", 50), ("financ", 50), ("passport", 50), ("govern", 50), ("security question", 30),
      ("phone", 20), ("address", 20), ("birth", 15), ("ip address", 10), ("name", 10), ("email", 10), ("username", 8), ("location", 8)]
SENS = {"bank": ("finance", 100), "pay": ("finance", 100), "coin": ("finance", 90), "adobe": ("files/identity", 55), "canva": ("design", 45),
        "figma": ("design", 45), "spotify": ("media", 40), "duolingo": ("education", 30), "twitter": ("social", 60), "facebook": ("social", 65),
        "instagram": ("social", 65), "pinterest": ("social", 60), "github": ("dev", 45), "hackerrank": ("jobs", 50), "convert": ("file converter", 55),
        "pdf": ("file converter", 55), "movie": ("streaming", 60), "stream": ("streaming", 60)}
_sem = asyncio.Semaphore(5)


async def load_jdm():
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            for s in (await c.get(JDM_URL)).json():
                for d in s.get("domains", []):
                    jdm[d.lower()] = s
    except Exception as e:
        print("JustDeleteMe dataset unavailable:", e)


def severity(data):
    return min(100, sum(next((w for k, w in KW if k in d.lower()), 5) for d in data))


async def age_years(domain):
    async with _sem:
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                j = (await c.get("https://rdap.org/domain/" + ".".join(domain.split(".")[-2:]))).json()
            for e in j.get("events", []):
                if e.get("eventAction") == "registration":
                    return (datetime.now(timezone.utc) - datetime.fromisoformat(e["eventDate"].replace("Z", "+00:00"))).days / 365
        except Exception:
            pass


async def enrich(domain, found_by, breach_names):
    stem = domain.split(".")[0].lower()
    cat, sens = next(((c, s) for k, (c, s) in SENS.items() if k in domain), ("other", 40))
    e = jdm.get(domain) or jdm.get(".".join(domain.split(".")[-2:])) or {}
    age = await age_years(domain)
    rep = 40 if age is None else 100 if age < 1 else 60 if age < 3 else 30 if age < 8 else 10
    rep = max(0, min(100, rep + (-10 if e else 15)))
    breached = len(stem) >= 4 and any(stem in (b or "").lower() for b in breach_names)
    raw_risk = round(.35 * rep + .35 * (100 if breached else 0) + .30 * sens)
    confirmed = bool({"holehe", "mailaccess"} & set(found_by))
    confidence = 1.0 if confirmed else min(.75, .45 + .10 * max(0, len(found_by) - 1))
    return {"domain": domain, "category": cat, "found_by": sorted(found_by), "confirmed": confirmed,
            "confidence": confidence, "confidence_label": "confirmed" if confirmed else "possible",
            "breached": breached, "age_years": None if age is None else round(age, 1),
            "raw_risk": raw_risk, "risk": round(raw_risk * confidence),
            "difficulty": e.get("difficulty"), "delete_url": e.get("url"), "delete_email": e.get("email"), "notes": e.get("notes")}


def domain_score(i):
    if not i or i.get("free"):
        return 10
    return min(100, 10 + (30 if i.get("dmarc") is None else 20 if i["dmarc"] == "none" else 0) + (0 if i.get("spf") else 20) + min(40, i.get("subdomains", 0) // 5))


async def build(ctx, partial=False):
    merged = {}
    for b in ctx.breaches:
        m = merged.setdefault((b["source"] or "?").lower(), {"source": b["source"], "date": b.get("date", ""), "data": [], "records": b.get("records")})
        m["data"] += [d for d in b["data"] if d.lower() not in [x.lower() for x in m["data"]]]
    breaches = list(merged.values())
    for b in breaches:
        b["severity"] = severity(b["data"])
    if ctx.stealers:
        breaches.append({"source": "Infostealer malware logs", "date": "", "data": ["credentials", "cookies"], "severity": 95, "records": ctx.stealers})
    sev = sorted((b["severity"] for b in breaches), reverse=True)
    SB = min(100, round(sev[0] + .25 * sum(sev[1:]))) if sev else 0
    names = [b["source"] for b in breaches]
    if partial:
        accounts = []
        for domain, found_by in ctx.accounts.items():
            confirmed = bool({"holehe", "mailaccess"} & set(found_by))
            accounts.append({"domain": domain, "category": "other", "found_by": sorted(found_by),
                             "confirmed": confirmed, "confidence": 1.0 if confirmed else .55,
                             "confidence_label": "confirmed" if confirmed else "possible",
                             "breached": False, "age_years": None, "raw_risk": 65 if confirmed else 35,
                             "risk": 65 if confirmed else 35, "difficulty": None, "delete_url": None,
                             "delete_email": None, "notes": None})
        accounts.sort(key=lambda a: (-a["risk"], -a["confidence"], a["domain"]))
    else:
        accounts = sorted(await asyncio.gather(*[enrich(d, s, names) for d, s in ctx.accounts.items()]),
                          key=lambda a: (-a["risk"], -a["confidence"], a["domain"]))
    rs = [a["risk"] for a in accounts]
    SP = round(.5 * rs[0] + .5 * sum(rs) / len(rs)) if rs else 0
    SD = domain_score(ctx.domain_info)
    confirmed_count = sum(1 for a in accounts if a["confirmed"])
    completed = [v for v in ctx.coverage.values() if v.get("status") == "done"]
    failed = [v for v in ctx.coverage.values() if v.get("status") in ("failed", "skipped")]
    return {"S": round(W["SB"] * SB + W["SP"] * SP + W["SD"] * SD), "SB": SB, "SP": SP, "SD": SD,
            "breaches": breaches, "accounts": accounts, "domain": ctx.domain_info,
            "coverage": {"tools": ctx.coverage, "completed": len(completed), "failed": len(failed),
                         "confirmed_accounts": confirmed_count, "confidence": round(
                             (0.5 if failed else 1.0) * (1.0 if confirmed_count else .55), 2),
                        "assessment": "inconclusive" if failed or not confirmed_count else "indicative"},
            "partial": partial,
            "mailaccess": ctx.evidence.get("mailaccess", "")}


def fallback(r):
    top = r["accounts"][:5]
    c = r.get("coverage", {})
    assessment = c.get("assessment", "inconclusive")
    return {"summary": f"{len(r['breaches'])} breach sources and {len(r['accounts'])} accounts found. "
                       f"Assessment: {assessment}; coverage is incomplete evidence, not a safety guarantee. "
                       f"Overall exposure score {r['S']}/100.",
            "breach_analysis": [{"source": b["source"], "what_leaked": ", ".join(b["data"]), "impact": "Leaked credentials can be reused on other sites." if severity(b["data"]) >= 45 else "Mostly contact details, which can increase unwanted contact risk.",
                                 "what_to_do": ["Change the password here and anywhere it was reused", "Enable two-factor authentication"]} for b in r["breaches"]],
            "account_actions": [{"domain": a["domain"], "priority": "high" if a["risk"] >= 60 else "medium" if a["risk"] >= 35 else "low",
                                 "steps": ["Delete the account via its settings page or the link in this dialog", "Email a data-erasure request if no delete button exists", "Change the password anywhere it was reused"]} for a in top],
            "top_steps": ["Delete the highest-risk accounts first", "Change reused passwords and use a password manager", "Turn on two-factor authentication for accounts you keep"]}


def _steps(v, lo=1):
    if isinstance(v, str):
        v = v.split("\n")
    if not isinstance(v, list):
        return []
    v = [re.sub(r"^[\s*\-\u2022\d.)]+", "", str(x)).strip() for x in v]
    v = [x for x in v if 8 < len(x) < 220]
    return v[:5] if len(v) >= lo else []


def _supported(text, res):
    text = str(text or "")
    facts = " ".join(str(x) for b in res["breaches"] for x in b.get("data", []))
    if not re.search(r"\b(phish|malicious|fraud|unsafe|vpn|authorit)", facts + " " + " ".join(
            str(a.get("notes", "")) for a in res["accounts"]), re.I):
        if re.search(r"\b(phishing|malicious|fraudulent|unsafe|vpn|authorit(?:y|ies))\b", text, re.I):
            return False
    return not re.search(r"\b(safe|secure|no risk|guarantee(?:d)?)\b", text, re.I)


def merge(res, ana):
    """Rule-based analysis is the safe base. Valid LLM output overrides it; junk from small models is dropped."""
    out = fallback(res)
    out["confidence_notes"] = "Rule-based assessment based on the available tool evidence."
    if not isinstance(ana, dict):
        return out
    facts = out["summary"]
    if isinstance(ana.get("summary"), str) and len(ana["summary"].strip()) > 40 and _supported(ana["summary"], res):
        out["summary"] = facts + " " + ana["summary"].strip()
    if (t := _steps(ana.get("top_steps"), 3)) and all(_supported(x, res) for x in t):
        out["top_steps"] = t
    if isinstance(ana.get("confidence_notes"), str) and _supported(ana["confidence_notes"], res):
        out["confidence_notes"] = ana["confidence_notes"].strip()[:500]
    names = {(b["source"] or "").lower() for b in res["breaches"]}
    ba = [b for b in ana.get("breach_analysis") or [] if isinstance(b, dict) and str(b.get("source", "")).lower() in names]
    for b in ba:
        b["what_to_do"] = _steps(b.get("what_to_do")) or ["Change the password here and anywhere it was reused", "Enable two-factor authentication"]
        b["what_leaked"], b["impact"] = str(b.get("what_leaked", "")), str(b.get("impact", ""))
        if not _supported(b["what_leaked"] + " " + b["impact"], res):
            b["impact"] = "Review the supplied evidence; this finding is not independently verified."
    if ba:
        out["breach_analysis"] = ba
    doms = {a["domain"] for a in res["accounts"]}
    acts = {a["domain"]: a for a in out["account_actions"]}
    for a in ana.get("account_actions") or []:
        if isinstance(a, dict) and a.get("domain") in doms and (st := _steps(a.get("steps"))):
            acts[a["domain"]] = {"domain": a["domain"], "priority": a.get("priority") if a.get("priority") in ("high", "medium", "low") else "medium", "steps": st}
    out["account_actions"] = list(acts.values())
    return out