# Python 3.12 rather than 3.14: every dependency here ships a prebuilt wheel for
# it, so the image builds in seconds instead of compiling pydantic-core from
# Rust source. (That compile is exactly what failed on the dev machine.)
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes, so
# ordinary code edits redeploy without reinstalling anything.
COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt

COPY app ./app

# Never run as root in a container that talks to the open internet.
RUN useradd --create-home --uid 10001 prospector
USER prospector

ENV PORT=8000 \
    PROSPECTOR_ENV=production
EXPOSE 8000

# One worker on purpose. The API key pools live in this process's memory, so a
# second worker would hand the same visitor a different, empty pool depending
# on which one answered. Read the "Limites do armazenamento atual" section of
# the README before raising this.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 75"]
