"""Shopping-shorts settings (all overridable in .env). Shared settings — paths,
voice, captions, watermark — come from pipeline.config."""
from __future__ import annotations

import os

from pipeline import config as base  # noqa: F401  (loads .env)

# --- Providers -----------------------------------------------------------------
# Which AI makes each scene, by scene role. Providers:
#   krea  — automated via the Krea API (KREA_API_KEY)
#   meta  — Meta AI (meta.ai) image/animate      ┐ manual handoff: the pipeline
#   vibes — Meta Vibes (vibes.ai) AI video        │ writes ready-to-paste prompts,
#   dola  — Dola (dola.com) Seedance video/images ┘ you drop the results in a folder
#   card  — local product card (real photo + price), no AI
DEFAULT_ROUTE = "hook=vibes,problem=meta,hero=krea,usage=dola,benefit=krea,cta=card"
ROUTE = dict(
    pair.split("=", 1) for pair in
    os.getenv("SHOP_ROUTE", DEFAULT_ROUTE).replace(" ", "").split(",") if "=" in pair
)

# When a manual (meta/vibes/dola) asset is missing at assembly time:
#   "krea"  -> generate that scene with Krea instead (needs KREA_API_KEY)
#   "photo" -> Ken Burns on the real product photo (free)
MANUAL_FALLBACK = os.getenv("SHOP_MANUAL_FALLBACK", "krea").strip().lower()

PROVIDER_LINKS = {
    "meta": "https://www.meta.ai/",
    "vibes": "https://vibes.ai/",
    "krea": "https://www.krea.ai/",
    "dola": "https://www.dola.com/",
}

# --- Krea API ------------------------------------------------------------------
# Submit -> job_id, poll GET /jobs/{id} until completed, results in result.urls.
# Endpoint paths are env-overridable in case Krea renames a model slug.
KREA_API_KEY = os.getenv("KREA_API_KEY", "")
KREA_API_BASE = os.getenv("KREA_API_BASE", "https://api.krea.ai").rstrip("/")
KREA_IMAGE_MODEL = os.getenv("KREA_IMAGE_MODEL", "/generate/image/krea/krea-2/medium")
KREA_VIDEO_MODEL = os.getenv("KREA_VIDEO_MODEL", "/generate/video/kling/kling-2.5")
KREA_VIDEO_SECONDS = int(os.getenv("KREA_VIDEO_SECONDS", "5"))
KREA_POLL_SECONDS = float(os.getenv("KREA_POLL_SECONDS", "4"))
KREA_TIMEOUT = int(os.getenv("KREA_TIMEOUT", "900"))
# Spend cap: max Krea video jobs per short (stills beyond the cap get Ken Burns).
KREA_MAX_VIDEOS = int(os.getenv("KREA_MAX_VIDEOS", "3"))

# --- Content -------------------------------------------------------------------
SHOP_LANGUAGE = os.getenv("SHOP_LANGUAGE", "Korean")
SHOP_TARGET_SECONDS = int(os.getenv("SHOP_TARGET_SECONDS", "25"))
SHOP_CURRENCY = os.getenv("SHOP_CURRENCY", "원")
SHOP_CTA_TEXT = os.getenv("SHOP_CTA_TEXT", "구매 링크는 고정 댓글에!")
# Affiliate disclosure appended to every description (required for Coupang
# Partners and most affiliate programs — keep it unless you have no affiliate link).
SHOP_DISCLOSURE = os.getenv(
    "SHOP_DISCLOSURE",
    "이 콘텐츠는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.",
)
SHOP_TTS_INSTRUCTIONS = os.getenv("SHOP_TTS_INSTRUCTIONS", (
    "Energetic, friendly Korean shopping-haul narrator. Fast and upbeat, like a "
    "creator who genuinely found something great. Natural Korean intonation, "
    "punch the product benefit and the price."
))
# Font for the product/price card. Empty = auto-detect a Korean-capable font.
SHOP_FONT = os.getenv("SHOP_FONT", "")
