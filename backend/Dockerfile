# WayBetter API image.
# Build context is ./backend. No secrets are baked in — every credential is read
# from the environment at runtime (CLAUDE.md "Secrets").

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app


FROM base AS builder

# Dependency layer first so app edits do not invalidate the wheel cache.
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

COPY app ./app
RUN /opt/venv/bin/pip install --no-deps .


FROM base AS runtime

RUN groupadd --system waybetter && useradd --system --gid waybetter --home /srv waybetter

COPY --from=builder /opt/venv /opt/venv
COPY --chown=waybetter:waybetter app ./app
COPY --chown=waybetter:waybetter pyproject.toml README.md ./

ENV PATH="/opt/venv/bin:${PATH}"

USER waybetter
EXPOSE 8000

# Liveness only — readiness (datastore reachability) is Compose's depends_on job
# and the orchestrator's /readyz probe.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
