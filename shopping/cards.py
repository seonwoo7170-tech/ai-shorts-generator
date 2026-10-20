"""Product/price CTA card: the real product photo + name + price, rendered with PIL
(no AI, so the price and product shown are always accurate)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline import config as base
from pipeline.util import log

from . import config
from .models import Product
from .product import portrait_canvas

_font_path: str | None = None


def _korean_font() -> str | None:
    """SHOP_FONT, then a CJK font in assets/fonts, then fontconfig (:lang=ko)."""
    global _font_path
    if _font_path is not None:
        return _font_path or None
    candidates = [config.SHOP_FONT] if config.SHOP_FONT else []
    candidates += [str(p) for p in sorted(base.FONT_DIR.glob("*"))
                   if p.suffix.lower() in (".ttf", ".otf", ".ttc")
                   and any(k in p.name.lower() for k in ("kr", "cjk", "gothic", "pretendard"))]
    try:
        out = subprocess.run(["fc-list", ":lang=ko", "file"], capture_output=True,
                             text=True, timeout=10).stdout
        found = [ln.split(":")[0].strip() for ln in out.splitlines() if ln.strip()]
        # prefer real outline fonts (Noto/Nanum/...) over bitmap fallbacks like unifont
        candidates += sorted(found, key=lambda f: ("unifont" in f.lower(),
                                                   "noto" not in f.lower() and "nanum" not in f.lower()))
    except Exception:  # noqa: BLE001 - fontconfig not installed (Windows)
        pass
    candidates += [r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf",
                   "/System/Library/Fonts/AppleSDGothicNeo.ttc"]
    _font_path = next((c for c in candidates if c and Path(c).exists()), "")
    if not _font_path:
        log("no Korean font found — set SHOP_FONT or drop NotoSansKR in assets/fonts")
    return _font_path or None


def _font(size: int):
    from PIL import ImageFont
    path = _korean_font()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for ch in text:                       # char-wise: works for Korean without spaces
        if draw.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur.rstrip())
            cur = ch.lstrip()
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines[:2]


def render_cta(product: Product, photo: Path | None, out: Path) -> Path:
    from PIL import Image, ImageDraw

    W, H = base.WIDTH, base.HEIGHT
    if photo:
        portrait_canvas(photo, out, max_h=0.5, y_shift=-300)   # leave room for the panel
        img = Image.open(out).convert("RGB")
    else:
        from pipeline.cards import render_fallback_bg
        img = Image.open(render_fallback_bg(out)).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    accent = base.BRAND["accent"]

    # bottom panel
    top = int(H * 0.70)
    d.rounded_rectangle([60, top, W - 60, H - 120], radius=48, fill=(10, 12, 18, 225))
    y = top + 50
    for line in _wrap(d, product.name, _font(58), W - 200):
        d.text((100, y), line, font=_font(58), fill="#F8FAFC")
        y += 74
    y += 10
    if product.price:
        price = f"{product.price}{config.SHOP_CURRENCY}"
        d.text((100, y), price, font=_font(96), fill=accent)
        if product.original_price:
            px = 100 + d.textlength(price, font=_font(96)) + 30
            orig = f"{product.original_price}{config.SHOP_CURRENCY}"
            d.text((px, y + 38), orig, font=_font(48), fill="#94A3B8")
            ow = d.textlength(orig, font=_font(48))
            d.line([px, y + 66, px + ow, y + 66], fill="#94A3B8", width=4)
        y += 120
    # CTA pill
    cta_font = _font(52)
    tw = d.textlength(config.SHOP_CTA_TEXT, font=cta_font)
    d.rounded_rectangle([100, y, 100 + tw + 80, y + 90], radius=45, fill=accent)
    d.text((140, y + 14), config.SHOP_CTA_TEXT, font=cta_font, fill="#FFFFFF")
    img.save(out)
    return out
