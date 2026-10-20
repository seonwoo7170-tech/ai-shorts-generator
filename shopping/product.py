"""Load products from a JSON file or (best-effort) from a product page URL, and
prepare the product photo as a 9:16 canvas the video stages can use."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

from pipeline import config as base
from pipeline.util import log

from .models import Product

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def load_products(source: str) -> list[Product]:
    """`source` = path to a .json file (one product object or a list), or a URL."""
    if source.startswith(("http://", "https://")):
        return [from_url(source)]
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    base_dir = Path(source).resolve().parent
    products = []
    for item in items:
        p = Product(**item)
        # relative image paths are relative to the JSON file
        if p.image and not p.image.startswith(("http://", "https://")):
            img = Path(p.image)
            p.image = str(img if img.is_absolute() else (base_dir / img).resolve())
        products.append(p)
    return products


def _meta(page: str, *names: str) -> str:
    for n in names:
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(n)}["\'][^>]+content=["\']([^"\']+)',
            page, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def from_url(url: str) -> Product:
    """Read og:title / og:image / price meta tags. Many shops (incl. Coupang)
    block bots — if this fails, write a product JSON instead."""
    import requests

    page = requests.get(url, headers={"User-Agent": _UA}, timeout=20).text
    name = _meta(page, "og:title", "twitter:title")
    if not name:
        raise RuntimeError("could not read product info from the page (bot-blocked?). "
                           "Use a product JSON file instead — see data/products.example.json")
    return Product(
        name=name,
        image=_meta(page, "og:image", "twitter:image"),
        price=_meta(page, "product:price:amount", "og:price:amount"),
        url=url,
        notes=_meta(page, "og:description", "description")[:300],
    )


def fetch_photo(product: Product, dest_dir: Path) -> Path | None:
    """Download/copy the product photo into the video folder. None if unavailable."""
    if not product.image:
        return None
    if product.image.startswith(("http://", "https://")):
        import requests

        ext = Path(product.image.split("?")[0]).suffix.lower() or ".jpg"
        out = dest_dir / f"product{ext if ext in ('.jpg', '.jpeg', '.png', '.webp') else '.jpg'}"
        r = requests.get(product.image, headers={"User-Agent": _UA}, timeout=60)
        r.raise_for_status()
        out.write_bytes(r.content)
        return out
    src = Path(product.image)
    if not src.exists():
        log(f"product image not found: {src}")
        return None
    return src


def portrait_canvas(photo: Path, out: Path, max_h: float = 0.62, y_shift: int = -80) -> Path:
    """Fit a (usually square, white-background) product photo onto a 1080x1920
    canvas over a blurred copy of itself, so nothing gets cropped off."""
    from PIL import Image, ImageFilter

    W, H = base.WIDTH, base.HEIGHT
    img = Image.open(photo).convert("RGB")
    scale = max(W / img.width, H / img.height)
    bg = img.resize((round(img.width * scale), round(img.height * scale)))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2,
                  (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(40)).point(lambda v: int(v * 0.7))
    fit = min(W * 0.9 / img.width, H * max_h / img.height)
    fg = img.resize((round(img.width * fit), round(img.height * fit)), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2 + y_shift))
    bg.save(out)
    return out


def fallback_slug(product: Product) -> str:
    return "product-" + hashlib.sha1(product.name.encode("utf-8")).hexdigest()[:8]
