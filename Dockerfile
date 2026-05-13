# Dockerfile for the Social Auto Engine dashboard.
#
# Designed for the public read-only demo on Hugging Face Spaces. To run it
# anywhere else (Fly.io, Render, your own VPS), the same image works — just
# unset DEMO_MODE and pass real platform credentials via env vars.
#
# Build:   docker build -t social-auto-engine .
# Run:     docker run -p 7860:7860 -e DEMO_MODE=1 social-auto-engine
# HF Space: set Space SDK to "docker" and set DEMO_MODE=1 in the Space
#          secrets. Spaces expose port 7860 by default.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps kept minimal. curl is used by the HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs the container as user 1000. Create a matching
# home directory so the dashboard's SQLite file at ~/.social-auto-engine/
# is writable.
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY --chown=user:user requirements.txt ./
RUN pip install -r requirements.txt

COPY --chown=user:user . .

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7860/landing >/dev/null || exit 1

CMD ["uvicorn", "dashboard.app:app", "--host", "0.0.0.0", "--port", "7860"]
