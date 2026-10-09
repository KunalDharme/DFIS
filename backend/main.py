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
from fastapi import Cookie, FastAPI, HTTPException, Response, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import llm, modules as M, scoring as S
import leakosint_provider as L
import auth as A

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
app = FastAPI(title="DFIS")
otps, tokens = {}, {}


@app.on_event("startup")
async def startup():
    await S.load_jdm()
    A.init_db()


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


class ProSignup(BaseModel):
    email: str
    password: str
    name: str = ""


class ProLogin(BaseModel):
    email: str
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class DeleteAccount(BaseModel):
    current_password: str


def _require_pro_user(session_token):
    user = A.get_user(session_token)
    if not user:
        raise HTTPException(401, "Sign in to a Pro account first")
    return user


def _set_session(response, raw_token):
    response.set_cookie("dfis_pro_session", raw_token, httponly=True, samesite="lax",
                        secure=os.getenv("COOKIE_SECURE", "0") == "1", max_age=30 * 86400)


@app.post("/api/pro/auth/signup")
async def pro_signup(r: ProSignup, response: Response):
    try:
        user = A.create_user(r.email, r.password, r.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _set_session(response, A.create_session(user["id"]))
    return {"user": user}


@app.post("/api/pro/auth/login")
async def pro_login(r: ProLogin, response: Response):
    try:
        user = A.authenticate(r.email, r.password)
    except ValueError as e:
        raise HTTPException(401, str(e))
    _set_session(response, A.create_session(user["id"]))
    return {"user": user}


@app.get("/api/pro/auth/me")
async def pro_me(dfis_pro_session: str | None = Cookie(default=None)):
    return {"user": A.get_user(dfis_pro_session)}


@app.post("/api/pro/auth/logout")
async def pro_logout(response: Response, dfis_pro_session: str | None = Cookie(default=None)):
    A.delete_session(dfis_pro_session)
    response.delete_cookie("dfis_pro_session")
    return {"ok": True}


@app.post("/api/pro/auth/password")
async def pro_change_password(r: ChangePassword, response: Response, dfis_pro_session: str | None = Cookie(default=None)):
    user = _require_pro_user(dfis_pro_session)
    try:
        A.change_password(user["id"], r.current_password, r.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    response.delete_cookie("dfis_pro_session")
    return {"ok": True, "message": "Password changed. Sign in again."}


@app.delete("/api/pro/auth/account")
async def pro_delete_account(r: DeleteAccount, response: Response, dfis_pro_session: str | None = Cookie(default=None)):
    user = _require_pro_user(dfis_pro_session)
    if not A.verify_password(user["id"], r.current_password):
        raise HTTPException(400, "Current password is incorrect")
    A.delete_user(user["id"])
    response.delete_cookie("dfis_pro_session")
    return {"ok": True}


@app.get("/api/pro/history")
async def pro_history(dfis_pro_session: str | None = Cookie(default=None)):
    user = _require_pro_user(dfis_pro_session)
    return {"items": A.get_history(user["id"])}


@app.delete("/api/pro/history")
async def pro_delete_history(dfis_pro_session: str | None = Cookie(default=None)):
    user = _require_pro_user(dfis_pro_session)
    A.delete_history(user["id"])
    return {"ok": True}


@app.post("/api/pro/exposure/{kind}")
async def pro_exposure_check(kind: str, r: ExposureCheck, dfis_pro_session: str | None = Cookie(default=None)):
    user = _require_pro_user(dfis_pro_session)
    if kind not in ("email", "phone"):
        raise HTTPException(404, "Unsupported exposure check")
    try:
        result = await L.search(kind, r.query)
        label = result["kind"] + ": " + ("*" * 3 + r.query[-4:] if kind == "phone" else r.query[:1] + "***" + r.query[r.query.index("@"):])
        A.add_history(user["id"], kind, label, f"{result['record_count']} records across {result['source_count']} sources")
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError:
        raise HTTPException(502, "The exposure provider could not be reached")
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/pro/domain-check")
async def pro_domain_check(r: DomainCheck, dfis_pro_session: str | None = Cookie(default=None)):
    user = _require_pro_user(dfis_pro_session)
    try:
        result = await M.check_domain_safety(r.domain)
        A.add_history(user["id"], "domain", result["domain"], f"{result['level']} risk ({result['score']}/100)")
        return result
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