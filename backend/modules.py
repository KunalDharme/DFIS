"""OSINT modules. Each module is `async def fn(ctx)`; all selected modules run concurrently.
To add a tool: write a function, append it to REGISTRY. Group names follow the DFIS paper."""
import asyncio, os, re, shutil
import httpx

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FREE = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com", "icloud.com", "proton.me", "protonmail.com"}
_mailaccess_process = None
_mailaccess_url = None


async def stop_mailaccess():
    global _mailaccess_process
    if _mailaccess_process and _mailaccess_process.returncode is None:
        _mailaccess_process.terminate()
        await _mailaccess_process.wait()
    _mailaccess_process = None


class Skip(Exception):
    pass


class Ctx:
    def __init__(self, email, emit):
        self.email, self.emit = email, emit
        self.user, self.domain = email.split("@")[0], email.split("@")[1].lower()
        self.breaches, self.accounts, self.domain_info = [], {}, {}
        self.stealers, self.evidence = 0, {}
        self.coverage = {}

    def hit(self, domain, source):
        self.accounts.setdefault(domain.lower(), set()).add(source)

    def observe(self, module, line):
        stats = self.coverage.setdefault(module, {"checked": 0, "rate_limited": 0, "errors": 0})
        if re.search(r"\b(rate.?limit|too many requests|429)\b", line, re.I):
            stats["rate_limited"] += 1
        if re.search(r"\b(dns|timeout|connection|error|failed)\b", line, re.I):
            stats["errors"] += 1


OVERRIDES = {"hugging face": "huggingface.co", "twitter": "twitter.com"}


def guess_domain(name):
    """mailaccess prints site names, not domains: 'Chess.Com' -> chess.com, 'Canva' -> canva.com"""
    n = name.strip().lower()
    return n.replace(" ", "") if "." in n else OVERRIDES.get(n, n.replace(" ", "") + ".com")


def domain_of(u):
    from urllib.parse import urlparse
    h = (urlparse(u if "//" in u else "//" + u).hostname or u).lower()
    return h[4:] if h.startswith("www.") else h


async def run_cli(ctx, mid, cmd, on_line, timeout=240):
    if not shutil.which(cmd[0]):
        raise Skip(f"{cmd[0]} is not installed (it is baked into the Docker image)")
    await ctx.emit(mid, "$ " + " ".join(cmd).replace(ctx.email, "<target>"), "cmd")
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                         env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})  # Windows-safe output
    try:
        async with asyncio.timeout(timeout):
            async for raw in p.stdout:
                line = ANSI.sub("", raw.decode(errors="ignore")).rstrip()
                if line:
                    ctx.observe(mid, line)
                    await on_line(line)
    except TimeoutError:
        await ctx.emit(mid, "timed out, keeping partial results", "warn")
    finally:
        if p.returncode is None:
            p.kill()


# ---------------- Breach Intelligence ----------------
async def breach_xposedornot(ctx):
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get("https://api.xposedornot.com/v1/breach-analytics", params={"email": ctx.email})
    if r.status_code == 404:
        return await ctx.emit("breach_xposedornot", "no breaches found", "ok")
    details = (r.json().get("ExposedBreaches") or {}).get("breaches_details") or []
    if not details:
        return await ctx.emit("breach_xposedornot", "no breaches found", "ok")
    for b in details:
        data = [x.strip() for x in (b.get("xposed_data") or "").split(";") if x.strip()]
        ctx.breaches.append({"source": b.get("breach"), "date": str(b.get("xposed_date", "")), "data": data, "records": b.get("xposed_records")})
        await ctx.emit("breach_xposedornot", f"breach: {b.get('breach')} ({', '.join(data) or 'unknown data'})", "warn")


async def breach_leakcheck(ctx):
    async with httpx.AsyncClient(timeout=25) as c:
        j = (await c.get("https://leakcheck.io/api/public", params={"check": ctx.email})).json()
    if not j.get("success") or not j.get("found"):
        return await ctx.emit("breach_leakcheck", "no results", "ok")
    for s in j.get("sources", []):
        ctx.breaches.append({"source": s.get("name"), "date": s.get("date", ""), "data": j.get("fields", []), "records": None})
        await ctx.emit("breach_leakcheck", f"breach: {s.get('name')} ({s.get('date','')}) fields: {', '.join(j.get('fields', []))}", "warn")


async def stealer_hudsonrock(ctx):
    async with httpx.AsyncClient(timeout=25) as c:
        j = (await c.get("https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email", params={"email": ctx.email})).json()
    ctx.stealers = len(j.get("stealers") or [])
    await ctx.emit("stealer_hudsonrock", f"{ctx.stealers} infostealer infections" if ctx.stealers else "no infostealer logs", "err" if ctx.stealers else "ok")


# ---------------- Platform Presence ----------------
async def holehe(ctx):
    async def on(line):
        checked = re.match(r"\[[+x-]\]\s+(\S+)", line, re.I)
        if checked:
            ctx.coverage.setdefault("holehe", {"checked": 0, "rate_limited": 0, "errors": 0})["checked"] += 1
        m = re.match(r"\[\+\]\s+([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,})(?:\s|$)", line, re.I)
        if m:  # Holehe emits domains; its legend does not contain a domain.
            ctx.hit(domain_of(m.group(1)), "holehe")
        await ctx.emit("holehe", line, "ok" if m else "info")
    await run_cli(ctx, "holehe", ["holehe", "--only-used", "--no-color", ctx.email], on)


async def _username_tool(ctx, mid, cmd):
    async def on(line):
        m = re.match(r"\[\+\]\s+([^:]+):\s+(https?://\S+)", line, re.I)
        if m:
            ctx.coverage.setdefault(mid, {"checked": 0, "rate_limited": 0, "errors": 0})["checked"] += 1
            ctx.hit(domain_of(m.group(2)), mid)
        await ctx.emit(mid, line, "ok" if m else "info")
    await run_cli(ctx, mid, cmd, on)


async def sherlock(ctx):
    await _username_tool(ctx, "sherlock", ["sherlock", ctx.user, "--print-found", "--timeout", "8", "--no-color"])


async def maigret(ctx):
    await _username_tool(ctx, "maigret", ["maigret", ctx.user, "--no-color", "--no-progressbar", "--top-sites", "200", "--timeout", "8",
                                           "--dns-resolver", "threaded"])


async def mailaccess(ctx):
    """Parses its account hits and also passes the full report to the LLM as extra context."""
    global _mailaccess_process, _mailaccess_url
    lines = []
    noise = re.compile(r"^(?:mailaccess(?:\s+v?\d[\w.-]*)?|usage:|options?:|commands?:|version\b|copyright\b|license\b|configuration\b|config(?:uration)?\s+(?:set|show)|starting\s+(?:server|mailaccess)|server\s+(?:started|running)|health\b|installed\b|loading\s+(?:config|settings)|\s*)$", re.I)
    async def on(line):
        lines.append(line)
        m = re.match(r"\s*[~\u2713]\s+(.+?)\s{2,}email registration signal", line)
        if m:
            ctx.hit(guess_domain(m.group(1)), "mailaccess")
        if not noise.match(line.strip()):
            await ctx.emit("mailaccess", line.strip()[:300], "ok" if m else "info")
    port = int(os.getenv("MAILACCESS_PORT", "8001"))
    _mailaccess_url = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(timeout=1) as client:
            await client.get(_mailaccess_url + "/health")
    except httpx.HTTPError:
        if _mailaccess_process is None or _mailaccess_process.returncode is not None:
            _mailaccess_process = await asyncio.create_subprocess_exec(
                "mailaccess", "serve", "--host", "127.0.0.1", "--port", str(port),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        for _ in range(20):
            await asyncio.sleep(.25)
            try:
                async with httpx.AsyncClient(timeout=1) as client:
                    response = await client.get(_mailaccess_url + "/health")
                if response.is_success:
                    break
            except httpx.HTTPError:
                continue
        else:
            raise RuntimeError(f"MailAccess server did not start on {_mailaccess_url}")
    await run_cli(ctx, "mailaccess", ["mailaccess", "config", "set-url", _mailaccess_url], lambda line: asyncio.sleep(0))
    await run_cli(ctx, "mailaccess", ["mailaccess", "investigate", ctx.email], on, timeout=270)
    ctx.evidence["mailaccess"] = "\n".join(lines)[-6000:]


# ---------------- Domain Intelligence ----------------
async def domain_intel(ctx):
    d = ctx.domain
    if d in FREE:
        ctx.domain_info = {"free": True}
        return await ctx.emit("domain_intel", f"{d} is a free email provider: baseline domain score", "warn")
    import dns.resolver
    def q(name):
        try:
            return [r.to_text() for r in dns.resolver.resolve(name, "TXT", lifetime=6)]
        except Exception:
            return []
    txt, dm = await asyncio.to_thread(q, d), await asyncio.to_thread(q, "_dmarc." + d)
    pol = next((m.group(1) for t in dm if (m := re.search(r"p=(\w+)", t))), None)
    subs = set()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get("https://crt.sh/", params={"q": "%." + d, "output": "json"})
        subs = {n.strip().lstrip("*.") for e in r.json() for n in e.get("name_value", "").split("\n")}
    except Exception:
        await ctx.emit("domain_intel", "crt.sh unavailable, subdomains skipped", "warn")
    ctx.domain_info = {"free": False, "spf": any("v=spf1" in t for t in txt), "dmarc": pol, "subdomains": len(subs)}
    await ctx.emit("domain_intel", f"SPF: {ctx.domain_info['spf']}, DMARC policy: {pol}, subdomains in certs: {len(subs)}", "ok")


REGISTRY = [  # (module id, paper group, function)
    ("breach_xposedornot", "Breach Intelligence", breach_xposedornot),
    ("breach_leakcheck", "Breach Intelligence", breach_leakcheck),
    ("stealer_hudsonrock", "Breach Intelligence", stealer_hudsonrock),
    ("holehe", "Platform Presence", holehe),
    ("sherlock", "Platform Presence", sherlock),
    ("maigret", "Platform Presence", maigret),
    ("mailaccess", "Platform Presence", mailaccess),
    ("domain_intel", "Domain Intelligence", domain_intel),
]