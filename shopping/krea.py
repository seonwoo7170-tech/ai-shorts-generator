"""Minimal Krea API client: submit a job, poll /jobs/{id}, download result.urls[0].

    POST {KREA_API_BASE}{model_path}   Authorization: Bearer <KREA_API_KEY>  -> {job_id}
    GET  {KREA_API_BASE}/jobs/{job_id}  -> {status, result: {urls: [...]}}

Model paths are configurable (KREA_IMAGE_MODEL / KREA_VIDEO_MODEL) so a renamed
slug is a .env change, not a code change.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from pipeline import config as base
from pipeline.util import log

from . import config

_DONE = "completed"
_FAILED = ("failed", "cancelled", "canceled", "error")


class KreaError(RuntimeError):
    pass


def available() -> bool:
    return bool(config.KREA_API_KEY)


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.KREA_API_KEY}",
            "Content-Type": "application/json"}


def _submit(model_path: str, body: dict) -> str:
    url = config.KREA_API_BASE + "/" + model_path.lstrip("/")
    r = requests.post(url, json=body, headers=_headers(), timeout=60)
    if r.status_code >= 400:
        raise KreaError(f"submit {model_path} -> HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    job_id = data.get("job_id") or data.get("id")
    if not job_id:
        raise KreaError(f"no job_id in response: {str(data)[:300]}")
    return job_id


def _wait(job_id: str) -> str:
    deadline = time.time() + config.KREA_TIMEOUT
    status = ""
    while time.time() < deadline:
        r = requests.get(f"{config.KREA_API_BASE}/jobs/{job_id}", headers=_headers(), timeout=30)
        r.raise_for_status()
        job = r.json()
        status = (job.get("status") or "").lower()
        if status == _DONE:
            urls = (job.get("result") or {}).get("urls") or []
            if not urls:
                raise KreaError(f"job {job_id} completed without result urls")
            return urls[0]
        if status in _FAILED:
            raise KreaError(f"job {job_id} {status}: {str(job.get('error') or job)[:300]}")
        time.sleep(config.KREA_POLL_SECONDS)
    raise KreaError(f"job {job_id} timed out after {config.KREA_TIMEOUT}s (last: {status})")


def _download(url: str, out: Path) -> Path:
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    out.write_bytes(r.content)
    return out


def public_url(path_or_url: str | Path) -> str:
    """Krea takes images by URL. http(s) passes through; a local file is uploaded
    to fal storage (FAL_KEY) to get a URL."""
    s = str(path_or_url)
    if s.startswith(("http://", "https://")):
        return s
    if not base.FAL_KEY:
        raise KreaError("local image needs a public URL: set FAL_KEY (used only for the "
                        "upload) or give the product image as an http(s) URL")
    import fal_client
    return fal_client.upload_file(s)


def image(prompt: str, out: Path) -> tuple[Path, str]:
    """Text -> 9:16 still. Returns (local path, result url)."""
    log(f"krea image -> {out.name}")
    url = _wait(_submit(config.KREA_IMAGE_MODEL, {"prompt": prompt, "aspect_ratio": "9:16"}))
    return _download(url, out), url


def video(prompt: str, out: Path, start_image_url: str = "") -> Path:
    """Text or image -> short 9:16 clip."""
    body = {"prompt": prompt, "duration": config.KREA_VIDEO_SECONDS, "aspect_ratio": "9:16"}
    if start_image_url:
        body["start_image"] = start_image_url
    log(f"krea video ({'i2v' if start_image_url else 't2v'}) -> {out.name}")
    return _download(_wait(_submit(config.KREA_VIDEO_MODEL, body)), out)
