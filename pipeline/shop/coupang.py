"""Coupang link -> product info.

Accepts a Partners short link (link.coupang.com/a/..., coupa.ng/...) or a plain
coupang.com product URL. Redirects are followed by hand so we learn the product
URL even when the product page itself refuses bots (Coupang often answers 403).
The product name comes from the page's og:title when reachable; otherwise pass
it with --name.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import html
import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from .. import config
from ..util import log, step

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
OPEN_API = "https://api-gateway.coupang.com"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"


@dataclass
class Product:
    affiliate_url: str
    product_url: str
    product_id: str
    item_id: str = ""
    vendor_item_id: str = ""
    name: str = ""
    image: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _is_product_url(url: str) -> bool:
    return "coupang.com" in urlparse(url).netloc and "/products/" in urlparse(url).path


def resolve_url(link: str, max_hops: int = 10) -> str:
    """Follow redirects one hop at a time; stop at the first coupang product URL."""
    url = link
    for _ in range(max_hops):
        if _is_product_url(url):
            return url
        r = requests.get(url, headers=HEADERS, allow_redirects=False, timeout=15)
        loc = r.headers.get("Location")
        if not loc:
            # some short links redirect via an HTML/JS page instead of a 30x
            m = re.search(r"https?://(?:www\.|m\.)?coupang\.com/vp/products/[^\"'\s<>]+", r.text)
            if m:
                return html.unescape(m.group(0))
            break
        url = urljoin(url, loc)
    if not _is_product_url(url):
        raise ValueError(f"could not resolve a coupang product URL from {link!r} (ended at {url})")
    return url


def parse_ids(url: str) -> dict:
    u = urlparse(url)
    m = re.search(r"/products/(\d+)", u.path)
    q = parse_qs(u.query)
    return {
        "product_id": m.group(1) if m else "",
        "item_id": (q.get("itemId") or [""])[0],
        "vendor_item_id": (q.get("vendorItemId") or [""])[0],
    }


def _meta(page: str, prop: str) -> str:
    m = (re.search(rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']*)', page)
         or re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']{prop}', page))
    return html.unescape(m.group(1)).strip() if m else ""


def _clean_title(t: str) -> str:
    return re.sub(r"\s*[-|]\s*쿠팡!?\s*$", "", t).strip()


def fetch_meta(product_url: str) -> dict:
    """og:title / og:image from the product page; plain HTTP first, then a real
    browser (Playwright). Returns {} when Coupang blocks both."""
    try:
        r = requests.get(product_url, headers=HEADERS, timeout=15)
        if r.ok and "og:title" in r.text:
            return {"name": _clean_title(_meta(r.text, "og:title")),
                    "image": _meta(r.text, "og:image")}
        log(f"coupang page HTTP {r.status_code} — trying a browser")
    except requests.RequestException as e:
        log(f"coupang page fetch failed ({type(e).__name__}) — trying a browser")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, locale="ko-KR")
            page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
            content = page.content()
            browser.close()
        if "og:title" in content:
            return {"name": _clean_title(_meta(content, "og:title")),
                    "image": _meta(content, "og:image")}
    except Exception as e:  # noqa: BLE001
        log(f"browser fetch failed ({type(e).__name__})")
    return {}


def _signed_headers(method: str, path: str, query: str = "") -> dict:
    signed = dt.datetime.now(dt.timezone.utc).strftime("%y%m%dT%H%M%SZ")
    msg = signed + method + path + query
    sig = hmac.new(config.COUPANG_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {
        "Authorization": (f"CEA algorithm=HmacSHA256, access-key={config.COUPANG_ACCESS_KEY}, "
                          f"signed-date={signed}, signature={sig}"),
        "Content-Type": "application/json;charset=UTF-8",
    }


def deeplink(product_url: str) -> str:
    """Plain coupang URL -> your Partners short link (needs Open API keys)."""
    r = requests.post(OPEN_API + DEEPLINK_PATH, headers=_signed_headers("POST", DEEPLINK_PATH),
                      json={"coupangUrls": [product_url]}, timeout=15)
    r.raise_for_status()
    data = r.json().get("data") or []
    if not data:
        raise RuntimeError(f"deeplink API returned no data: {r.text[:200]}")
    return data[0]["shortenUrl"]


def get_product(link: str, name: str = "") -> Product:
    step("Coupang product")
    link = link.strip()
    product_url = resolve_url(link)
    ids = parse_ids(product_url)
    affiliate = link
    if _is_product_url(link):
        if config.COUPANG_ACCESS_KEY and config.COUPANG_SECRET_KEY:
            affiliate = deeplink(product_url)
            log(f"partners deeplink: {affiliate}")
        else:
            log("plain coupang URL and no COUPANG_ACCESS_KEY — the link in the "
                "description will NOT earn commission")
    meta = {} if name else fetch_meta(product_url)
    product = Product(affiliate_url=affiliate, product_url=product_url,
                      name=name or meta.get("name", ""), image=meta.get("image", ""), **ids)
    if not product.name:
        raise RuntimeError("Coupang blocked the product page — rerun with --name \"상품명\"")
    log(f"{product.name} (productId={product.product_id})")
    return product
