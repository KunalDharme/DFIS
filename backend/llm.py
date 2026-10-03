"""LLM analysis. Works with Anthropic, OpenAI, or a local Ollama model (OpenAI-compatible API).
Only structured findings are sent. The email address and username are redacted."""
import json, os, re
import httpx

P = os.getenv("LLM_PROVIDER", "").lower()  # anthropic | openai | ollama | "" (disabled)
MODEL = os.getenv("LLM_MODEL", {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o-mini", "ollama": "llama3.1:8b"}.get(P, ""))
BASE = os.getenv("LLM_BASE_URL", {"openai": "https://api.openai.com/v1", "ollama": "http://ollama:11434/v1"}.get(P, ""))
KEY = os.getenv("LLM_API_KEY", "")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))
ERR = ""  # last failure reason, shown in the UI terminal

SYSTEM = """You are a cautious cybersecurity analyst inside DFIS, a digital footprint tool. You get OSINT findings for one person. Reply with ONLY JSON:
{"summary": "3-4 plain sentences", "breach_analysis": [{"source": str, "what_leaked": str, "impact": str, "what_to_do": [str]}],
"account_actions": [{"domain": str, "priority": "high|medium|low", "steps": [str]}], "top_steps": [3-5 short imperative strings], "confidence_notes": str}
Rules: only mention breaches and accounts present in the evidence. Treat confirmed accounts as confirmed only when found_by includes holehe or mailaccess; Sherlock and Maigret are possible username matches and may belong to another person. Explicitly describe incomplete or failed coverage as inconclusive. Never say the scan is safe, secure, comprehensive, or proof of identity. Do not call a site phishing, malicious, fraudulent, or unsafe, and do not recommend a VPN or reporting to authorities unless the supplied evidence explicitly supports it. Do not change numeric scores. Every list must be a JSON array of short strings (under 20 words each), never one string with bullets. Be specific to the evidence, no generic filler."""


def describe():
    return f"{P}:{MODEL}" if P and MODEL else None


async def analyse(r, ctx):
    global ERR
    ERR = ""
    if not describe():
        return None
    ev = {"scores": {k: r[k] for k in ("S", "SB", "SP", "SD")}, "breaches": r["breaches"], "domain": r["domain"],
          "coverage": r.get("coverage", {}),
          "accounts": [{k: a[k] for k in ("domain", "category", "found_by", "confirmed", "confidence_label",
                                           "breached", "age_years", "risk", "difficulty")} for a in r["accounts"][:20]]}
    extra = r["mailaccess"].replace(ctx.email, "[email]").replace(ctx.user, "[user]")[-1800:]
    user = json.dumps(ev) + ("\nExtra tool report:\n" + extra if extra else "")
    async def request(prompt, max_tokens):
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            if P == "anthropic":
                j = (await c.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": KEY, "anthropic-version": "2023-06-01"},
                                  json={"model": MODEL, "max_tokens": max_tokens, "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]})).json()
                if "error" in j:
                    raise RuntimeError(j["error"])
                text = j["content"][0]["text"]
            else:
                h = {"Authorization": f"Bearer {KEY}"} if KEY else {}
                j = (await c.post(BASE + "/chat/completions", headers=h, json={"model": MODEL, "temperature": 0.1,
                     "max_tokens": max_tokens, "top_p": 0.9, "response_format": {"type": "json_object"},
                     "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})).json()
                if "error" in j:
                    raise RuntimeError(j["error"])
                text = j["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("LLM returned no JSON object")
        return json.loads(match.group(0))
    try:
        return await request(user, 1000)
    except Exception as e:
        if P == "ollama":
            try:
                return await request(json.dumps(ev), 600)
            except Exception as retry_error:
                ERR = (repr(retry_error) if not str(retry_error) else str(retry_error))[:200]
                print("LLM analysis failed:", ERR)
                return None
        ERR = (repr(e) if not str(e) else str(e))[:200]
        print("LLM analysis failed:", ERR)
        return None