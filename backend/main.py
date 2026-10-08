"""DFIS API. Run: uvicorn main:app --reload  (Python 3.11+)"""
import asyncio, os, random, re, secrets, shutil, time
import httpx


def _load_env():  # reads .env itself, so Windows users don't have to set variables by hand
    for path in (".env", "../.env"):
        if os.path.isfile(path):
            for line in open(path, encoding="utf-8"):
                line = line.split(" #")[0].strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return


_load_env()
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import llm, modules as M, scoring as S
import leakosint_provider as L

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
app = FastAPI(title="DFIS")
otps, tokens = {}, {}


@app.on_event("startup")
async def startup():
    await S.load_jdm()


@app.on_event("shutdown")
async def shutdown():
    await M.stop_mailaccess()


class OtpReq(BaseModel):
    email: str

class OtpVerify(BaseModel):
    email: str
    code: str


class DomainCheck(BaseModel):
    domain: str


class ExposureCheck(BaseModel):
    query: str


@app.post("/api/pro/exposure/{kind}")
async def pro_exposure_check(kind: str, r: ExposureCheck):
    if kind not in ("email", "phone"):
        raise HTTPException(404, "Unsupported exposure check")
    try:
        return await L.search(kind, r.query)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError:
        raise HTTPException(502, "The exposure provider could not be reached")
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/pro/domain-check")
async def pro_domain_check(r: DomainCheck):
    try:
        return await M.check_domain_safety(r.domain)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, "The domain could not be checked right now")


@app.post("/api/otp/request")
async def otp_request(r: OtpReq):
    if not EMAIL.match(r.email):
        raise HTTPException(400, "Enter a valid email address")
    code = f"{random.randint(0, 999999):06d}"
    otps[r.email.lower()] = (code, time.time() + 600)
    print(f"[OTP] {r.email}: {code}")  # TODO: send via SMTP/Resend. Shown in the UI while DEV_SHOW_OTP=1
    return {"dev_code": code if os.getenv("DEV_SHOW_OTP", "1") == "1" else None}


@app.post("/api/otp/verify")
async def otp_verify(r: OtpVerify):
    code, exp = otps.get(r.email.lower(), ("", 0))
    if not secrets.compare_digest(code, r.code) or time.time() > exp:
        raise HTTPException(401, "Code is wrong or expired")
    otps.pop(r.email.lower(), None)
    t = secrets.token_urlsafe(24)
    tokens[t] = r.email.lower()
    return {"token": t}


@app.get("/api/health")
async def health():
    return {"tools": {t: bool(shutil.which(t)) for t in ("holehe", "sherlock", "maigret", "mailaccess")}, "llm": llm.describe(),
            "modules": [m[0] for m in M.REGISTRY]}


async def pipeline(email, q, only):
    async def emit(module, text, kind="info"):
        await q.put({"type": "log", "module": module, "text": text, "kind": kind})
    async def status(module, state, secs=None):
        await q.put({"type": "status", "module": module, "state": state, "secs": secs})
    try:
        ctx = M.Ctx(email, emit)
        sel = [(m, f) for m, _, f in M.REGISTRY if not only or m in only]
        async def run(mid, fn):
            await status(mid, "running"); t, st = time.time(), "done"
            try:
                await asyncio.wait_for(fn(ctx), 300)
            except M.Skip as e:
                st = "skipped"; await emit(mid, str(e), "warn")
            except Exception as e:
                st = "failed"; await emit(mid, f"failed: {e}", "err")
            ctx.coverage.setdefault(mid, {"checked": 0, "rate_limited": 0, "errors": 0})["status"] = st
            await status(mid, st, round(time.time() - t, 1))
            if st in ("done", "failed", "skipped"):
                partial = await S.build(ctx, partial=True)
                await q.put({"type": "partial_result", **partial})
        for m, _ in sel:
            await status(m, "queued")
        await asyncio.gather(*[run(m, f) for m, f in sel])
        await emit("aggregate", "S = 0.50*SB + 0.35*SP + 0.15*SD: scoring breaches and accounts...", "cmd")
        res = await S.build(ctx)
        await emit("aggregate", f"SB={res['SB']} SP={res['SP']} SD={res['SD']} -> S={res['S']}", "ok")
        await emit("llm", f"sending findings to {llm.describe() or 'no LLM configured'}...", "cmd")
        ana = await llm.analyse(res, ctx)
        if llm.describe() and not ana:
            await emit("llm", f"LLM call failed: {llm.ERR or 'no usable JSON in the reply'}", "err")
        res.pop("mailaccess", None)
        res["analysis"] = S.merge(res, ana)  # validated: junk from small models falls back to rule-based text
        res["llm_used"] = llm.describe() if ana else None
        await emit("llm", "analysis ready" if ana else "using rule-based analysis", "ok")
        await q.put({"type": "result", **res})
    except Exception as e:
        await q.put({"type": "error", "text": str(e)})
    finally:
        await q.put(None)


@app.websocket("/ws/scan")
async def scan_ws(ws: WebSocket):
    await ws.accept()
    task = None
    try:
        req = await ws.receive_json()
        email = tokens.get(req.get("token", ""))
        if not email:
            return await ws.send_json({"type": "error", "text": "Verify your email first"})
        q = asyncio.Queue()
        task = asyncio.create_task(pipeline(email, q, set(req.get("modules") or [])))
        while (ev := await q.get()) is not None:
            await ws.send_json(ev)
    except Exception:
        pass
    finally:
        if task:
            task.cancel()
        try:
            await ws.close()
        except Exception:
            pass


STATIC = next(p for p in ("static", "../static") if os.path.isdir(p))  # Docker vs. running from backend/


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))

app.mount("/static", StaticFiles(directory=STATIC), name="static")