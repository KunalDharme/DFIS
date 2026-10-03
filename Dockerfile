FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
# OSINT CLIs live in isolated venvs (pipx) so their pinned dependencies never clash
RUN pip install --no-cache-dir pipx && \
    for t in holehe maigret sherlock-project mailaccess; do PIPX_BIN_DIR=/usr/local/bin pipx install "$t" || echo "WARN: $t failed"; done && \
    PIPX_HOME=/root/.local/pipx PIPX_BIN_DIR=/usr/local/bin pipx inject mailaccess greenlet || echo "WARN: could not inject greenlet into MailAccess"
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY static/ static/
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
