# Cloud deploy (Railway / Fly / any Docker host) so the dashboard works from a phone
# with no PC. Mount a volume and set DATA_DIR / OUTPUT_DIR inside it.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DATA_DIR=/storage/data OUTPUT_DIR=/storage/output HF_HOME=/storage/hf \
    XHS_HEADLESS=true WHISPER_DEVICE=cpu

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .
RUN mkdir -p /storage/data /storage/output
EXPOSE 5000
CMD ["python", "run.py", "serve"]
