# DFIS

DFIS (Digital Footprint Intelligence System) is a local, consent-based OSINT application for personal exposure analysis. It combines breach checks, platform-presence checks, domain checks, risk scoring, and account-removal guidance in one browser dashboard.

The application is intended for email addresses that the person running the scan owns or is authorized to investigate. Results are indicators, not proof of identity, account ownership, or safety.

## What It Includes

- Breach checks through XposedOrNot and LeakCheck.
- Infostealer exposure checks through Hudson Rock.
- Email-presence checks through Holehe.
- Username-presence checks through Sherlock and Maigret.
- Additional email evidence through MailAccess.
- Domain intelligence through DNS and certificate lookups.
- Rule-based scoring with optional LLM-generated explanations and remediation steps.
- A browser UI with live WebSocket progress, coverage notes, and deletion guidance.

## Pro Development Trial

DFIS Pro is currently available as a free development trial; no payment gateway
is active. From the normal homepage, choose **Upgrade to Pro** to open the
sign-in or sign-up dialog. Pro accounts use a local SQLite database and are
separate from the normal OTP-based scan flow.

Pro includes:

- Domain safety checks covering HTTPS, redirects, SPF, DMARC, status, and risk signals.
- Email and phone exposure checks with redacted metadata and sample records.
- Saved scan history, account settings, password changes, and account deletion.
- Removal guidance and downloadable redacted HTML reports.

LeakOSINT is the primary provider for Pro email and phone exposure checks. If
the email request fails, times out, or is unavailable, DFIS uses XposedOrNot
as an email-only metadata fallback. Raw credentials, passwords, tokens, and
unmasked personal records are not displayed. Phone checks continue to use
LeakOSINT only.

The Buy Premium button is informational during development and does not start
a payment or subscription.

## Requirements

### All platforms

- Python 3.11 or newer.
- Git, if cloning the repository.
- Internet access for public OSINT services and package installation.
- A modern browser with WebSocket support.

### Optional LLM

DFIS works without an LLM and uses rule-based analysis by default. Choose one of these only if you want generated summaries and remediation wording:

- Ollama for a local model.
- OpenAI-compatible API.
- Anthropic API.

### OSINT command-line tools

The four CLI tools are installed separately with `pipx` because their dependency trees can conflict with the DFIS API. They are not included in `backend/requirements.txt`.

- `holehe`
- `sherlock-project`
- `maigret`
- `mailaccess`

## Quick Start: Windows

Open PowerShell in the repository directory.

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

Install `pipx` and the OSINT tools:

```powershell
python -m pip install --user pipx
python -m pipx ensurepath
```

Close and reopen PowerShell after `ensurepath`, then run:

```powershell
pipx install holehe
pipx install maigret
pipx install sherlock-project
pipx install mailaccess
pipx inject mailaccess greenlet
```

Create the local configuration file:

```powershell
Copy-Item .env.example .env
```

The one-click launcher starts DFIS on `http://127.0.0.1:8000` and automatically starts MailAccess during a scan when needed:

```powershell
.\run_dfis.ps1
```

If PowerShell blocks local scripts, use this only for the current PowerShell process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\run_dfis.ps1
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser.

## Run Without the Launcher

With the virtual environment activated:

```powershell
Set-Location backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The API and web application are served together on port `8000`. MailAccess uses port `8001` by default and is started automatically by the application.

## Docker

Docker is the most reproducible setup because the image installs the API dependencies and the OSINT CLI tools in isolated environments.

1. Install Docker Desktop and make sure it is running.
2. Create `.env` from the template.
3. Build and start DFIS:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000).

Stop the application with `Ctrl+C`, or from another terminal:

```powershell
docker compose down
```

The optional Ollama service can be started with:

```powershell
docker compose --profile local-llm up --build
```

In the containerized setup, set the following in `.env`:

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://ollama:11434/v1
```

Then download the model in a second terminal:

```powershell
docker compose exec ollama ollama pull llama3.1:8b
```

## Ollama on Windows

Install Ollama from [ollama.com/download](https://ollama.com/download), then download a model:

```powershell
ollama pull llama3.1:8b
```

Set `.env` as follows:

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://127.0.0.1:11434/v1
```

The Windows launcher starts `ollama serve` if Ollama is installed and its API is not already running. If Ollama or the model is unavailable, DFIS falls back to rule-based analysis.

## Hosted LLM Configuration

For OpenAI:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=replace-with-your-key
```

For Anthropic:

```dotenv
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-5-5
LLM_API_KEY=replace-with-your-key
```

Do not commit `.env` or place API keys in source files. The LLM receives structured findings with the scanned email and username redacted where applicable. The numeric risk score is calculated locally and is not generated by the LLM.

## Configuration

`.env.example` contains the supported settings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama`, `openai`, `anthropic`, or empty for rule-based analysis | empty in a fresh setup |
| `LLM_MODEL` | Model name for the selected provider | provider-specific |
| `LLM_BASE_URL` | Base URL for OpenAI-compatible providers | provider-specific |
| `LLM_API_KEY` | Hosted provider key | empty |
| `LLM_TIMEOUT` | LLM request timeout in seconds | `300` |
| `DEV_SHOW_OTP` | Show the verification code in the UI for local development | `1` |
| `MAILACCESS_PORT` | Local MailAccess port | `8001` |
| `LEAKOSINT_TOKEN` | Local token for Pro email and phone exposure checks | empty |
| `DFIS_AUTH_DB` | Optional path for the Pro SQLite database | `backend/dfis_auth.sqlite3` |
| `COOKIE_SECURE` | Set to `1` only when serving over HTTPS | `0` |

`DEV_SHOW_OTP=1` is for local development only. The application currently prints and returns the OTP because email delivery has not been wired in yet. Keep the app private while this setting is enabled.

Keep `LEAKOSINT_TOKEN` in the local `.env` file only. Do not commit it or
expose it to the frontend. XposedOrNot does not require a token for the
email fallback.

## Scan Flow

1. Enter an email address and accept the ownership declaration.
2. Request the verification code.
3. Enter the code shown in local development mode.
4. DFIS runs the registered modules concurrently.
5. The browser receives live progress and preliminary results over WebSocket.
6. The final score and report are shown after aggregation and optional LLM analysis.

Coverage gaps, rate limits, failed tools, and possible username matches are shown in the report. A missing result does not mean that no account exists.

## Development

The project has no frontend build step. The browser loads `static/index.html`, `static/app.js`, and `static/style.css` directly from the FastAPI application.

Useful checks:

```powershell
python -m pip install -r backend\requirements.txt
python -m compileall backend
node --check static\app.js
```

The health endpoint reports detected CLI tools and registered modules:

```text
GET http://127.0.0.1:8000/api/health
```

To add an OSINT module, implement an async function in `backend/modules.py` and add it to `REGISTRY`. The module will appear in the UI and run with the other registered modules.

## Project Layout

```text
backend/
  auth.py             Pro accounts, sessions, and scan history
  llm.py              Optional LLM integration
  leakosint_provider.py Primary Pro exposure provider and redaction
  main.py             FastAPI application and WebSocket pipeline
  modules.py          OSINT modules and tool registry
  scoring.py          Score calculation and report aggregation
  requirements.txt    Python API dependencies
  xposedornot_provider.py Email-only Pro fallback provider
static/
  app.js              React UMD frontend
  index.html          Frontend entry point
  style.css           Frontend styles
Dockerfile             Container image definition
docker-compose.yml      DFIS and optional Ollama services
run_dfis.ps1            Windows launcher
```

For the complete Windows installation, restart, verification, and shutdown
steps, see [INSTALLATION_&_START_GUIDE.txt](INSTALLATION_&_START_GUIDE.txt).

## Troubleshooting

### A tool is shown as not installed

Check its executable is on `PATH`:

```powershell
Get-Command holehe, sherlock, maigret, mailaccess
```

Reopen PowerShell after installing with `pipx`, or add the pipx executable directory to `PATH`.

### MailAccess does not start

Check that port `8001` is free. To use another port, set `MAILACCESS_PORT` in `.env` and restart DFIS.

### Ollama is unavailable

Verify the service and model:

```powershell
ollama list
Invoke-WebRequest http://127.0.0.1:11434/api/tags
```

DFIS continues with rule-based analysis when Ollama is unavailable.

### Docker changes are not appearing

Rebuild the image:

```powershell
docker compose down
docker compose up --build
```

## Privacy and Responsible Use

DFIS is a research and development project. Use it only with authorization, respect the terms and rate limits of external services, and do not use it to investigate people without consent. Treat all reports as sensitive personal data. Do not expose the development server to the public internet.
