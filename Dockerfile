FROM python:3.12.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip setuptools

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m pip install --no-cache-dir --prefix=/install .

FROM python:3.12.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=builder /install /usr/local
COPY --chown=app:app pyproject.toml README.md ./
COPY --chown=app:app app ./app
# Knowledge base: sources plus the built retrieval index (kb/out is gitignored, so it
# is built here; without it every procedure question is answered with "no data").
COPY --chown=app:app kb/__init__.py ./kb/__init__.py
COPY --chown=app:app kb/src ./kb/src
COPY --chown=app:app kb/data ./kb/data
RUN python kb/src/build_kb.py > /dev/null && chown -R app:app kb

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
