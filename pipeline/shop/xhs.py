"""Xiaohongshu (小红书): search video notes for a product and download one.

Xiaohongshu has no public API and requires a logged-in session to search, so this
drives a real Chromium with a persistent profile (log in once with
`python run.py xhs-login`). Search results are read from the site's own JSON
responses (/api/sns/web/v1/search/notes) rather than the DOM, which changes often.
Download goes through yt-dlp (XiaoHongShu extractor) with the profile's cookies,
falling back to the video URL in the note page's __INITIAL_STATE__.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

import requests

from .. import config
from ..util import log, step

HOME = "https://www.xiaohongshu.com"
SEARCH_API = "/api/sns/web/v1/search/notes"
COOKIES_TXT = config.DATA / "xhs_cookies.txt"


@dataclass
class Note:
    note_id: str
    xsec_token: str
    title: str
    author: str
    likes: int
    cover: str = ""

    @property
    def url(self) -> str:
        return (f"{HOME}/explore/{self.note_id}?xsec_token={quote(self.xsec_token)}"
                "&xsec_source=pc_search")

    def to_dict(self) -> dict:
        return {**asdict(self), "url": self.url}


def _count(v) -> int:
    """'1.2万' / '3456' / 3456 -> int"""
    s = str(v or "0").strip()
    try:
        if s.endswith("万"):
            return int(float(s[:-1]) * 10000)
        return int(float(s))
    except ValueError:
        return 0


def _context(p, headless: bool):
    config.XHS_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    import os
    kwargs = {}
    if os.getenv("CHROMIUM_PATH"):            # use a system Chromium instead of Playwright's
        kwargs["executable_path"] = os.getenv("CHROMIUM_PATH")
    return p.chromium.launch_persistent_context(
        str(config.XHS_PROFILE_DIR), headless=headless, locale="zh-CN",
        viewport={"width": 1280, "height": 900}, **kwargs,
    )


def login() -> None:
    """Open a visible browser on the shared profile so the user can log in (QR)."""
    from playwright.sync_api import sync_playwright
    step("Xiaohongshu login")
    with sync_playwright() as p:
        ctx = _context(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(HOME)
        input("   - 브라우저에서 샤오홍슈에 로그인한 뒤 Enter를 누르세요... ")
        _export_cookies(ctx)
        ctx.close()
    log(f"profile saved -> {config.XHS_PROFILE_DIR}")


def logged_in(ctx) -> bool:
    return any(c["name"] == "web_session" and c["value"] for c in ctx.cookies()
               if "xiaohongshu" in c["domain"])


class WebLogin:
    """Headless login for servers: keeps a browser open on xiaohongshu.com, exposes
    screenshots of the QR code for the dashboard, and saves the profile once the
    session cookie appears. One instance at a time (the profile dir is locked)."""

    def __init__(self):
        self.qr: bytes = b""
        self.status = "idle"      # idle | starting | waiting | done | error
        self.error = ""
        self._stop = False
        self._thread = None

    def start(self):
        import threading
        if self._thread and self._thread.is_alive():
            return
        self.status, self.error, self.qr, self._stop = "starting", "", b"", False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True

    def _run(self):
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                ctx = _context(p, headless=True)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                if logged_in(ctx):
                    _export_cookies(ctx)
                    self.status = "done"
                    ctx.close()
                    return
                for sel in ("#login-btn", ".login-btn", "text=登录"):   # open the login modal
                    try:
                        page.locator(sel).first.click(timeout=2000)
                        break
                    except Exception:  # noqa: BLE001
                        continue
                self.status = "waiting"
                for _ in range(90):                     # ~3 min, QR refreshes every 2s
                    if self._stop:
                        break
                    page.wait_for_timeout(2000)
                    try:
                        qr = page.locator(".qrcode-img, .qrcode img, canvas.qrcode, img[src^='data:image']").first
                        self.qr = qr.screenshot(timeout=1500) if qr.count() else page.screenshot()
                    except Exception:  # noqa: BLE001
                        self.qr = page.screenshot()
                    if logged_in(ctx):
                        page.wait_for_timeout(1500)
                        _export_cookies(ctx)
                        self.status = "done"
                        break
                else:
                    self.status, self.error = "error", "시간 초과 — 다시 시작해 주세요"
                if self._stop and self.status == "waiting":
                    self.status = "idle"
                ctx.close()
        except Exception as e:  # noqa: BLE001
            self.status, self.error = "error", f"{type(e).__name__}: {e}"


WEB_LOGIN = WebLogin()


def _export_cookies(ctx) -> Path:
    """Write the profile's cookies as a Netscape cookies.txt for yt-dlp."""
    lines = ["# Netscape HTTP Cookie File"]
    for c in ctx.cookies():
        if "xiaohongshu" not in c["domain"]:
            continue
        domain = c["domain"]
        lines.append("\t".join([
            domain, "TRUE" if domain.startswith(".") else "FALSE", c.get("path", "/"),
            "TRUE" if c.get("secure") else "FALSE", str(int(max(c.get("expires", 0), 0))),
            c["name"], c["value"],
        ]))
    COOKIES_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return COOKIES_TXT


def _parse_items(payload: dict) -> list[Note]:
    notes = []
    for it in (payload.get("data") or {}).get("items") or []:
        card = it.get("note_card") or {}
        if card.get("type") != "video" or not it.get("id"):
            continue
        notes.append(Note(
            note_id=it["id"], xsec_token=it.get("xsec_token", ""),
            title=card.get("display_title", "") or "",
            author=(card.get("user") or {}).get("nickname", "") or "",
            likes=_count((card.get("interact_info") or {}).get("liked_count")),
            cover=((card.get("cover") or {}).get("url_default")
                   or (card.get("cover") or {}).get("url") or ""),
        ))
    return notes


def search_videos(keyword: str, limit: int | None = None) -> list[Note]:
    from playwright.sync_api import sync_playwright
    limit = limit or config.XHS_MAX_CANDIDATES
    step(f"Xiaohongshu search — {keyword}")
    found: dict[str, Note] = {}

    def on_response(resp):
        if SEARCH_API in resp.url:
            try:
                for n in _parse_items(resp.json()):
                    found.setdefault(n.note_id, n)
            except Exception:  # noqa: BLE001
                pass

    with sync_playwright() as p:
        ctx = _context(p, headless=config.XHS_HEADLESS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_response)
        page.goto(f"{HOME}/search_result?keyword={quote(keyword)}&source=web_search_result_notes",
                  wait_until="domcontentloaded", timeout=45000)
        for _ in range(6):                       # scroll to load more result pages
            if len(found) >= limit:
                break
            page.wait_for_timeout(2500)
            page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)
        _export_cookies(ctx)
        ctx.close()
    notes = sorted(found.values(), key=lambda n: n.likes, reverse=True)[:limit]
    if not notes:
        raise RuntimeError("no video notes found — log in again (`python run.py xhs-login`) "
                           "or pass a note URL with --xhs")
    for n in notes:
        log(f"{n.likes:>7} ♥  {n.title[:40]}  ({n.note_id})")
    return notes


def _download_ytdlp(url: str, out: Path) -> Path:
    import yt_dlp
    opts = {"outtmpl": str(out.with_suffix(".%(ext)s")), "format": "bv*+ba/b",
            "merge_output_format": "mp4", "quiet": True, "noprogress": True,
            "http_headers": {"Referer": HOME + "/"}}
    if COOKIES_TXT.exists():
        opts["cookiefile"] = str(COOKIES_TXT)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info)).with_suffix(".mp4")


def _video_url_from_state(state: dict) -> str:
    detail = (state.get("note") or {}).get("noteDetailMap") or {}
    for entry in detail.values():
        stream = ((((entry.get("note") or {}).get("video") or {}).get("media") or {})
                  .get("stream") or {})
        for codec in ("h264", "h265", "av1"):
            for s in stream.get(codec) or []:
                if s.get("masterUrl"):
                    return s["masterUrl"]
    return ""


def _download_browser(url: str, out: Path) -> Path:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _context(p, headless=config.XHS_HEADLESS)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)
        raw = page.evaluate("() => JSON.stringify(window.__INITIAL_STATE__ || {})")
        ctx.close()
    video_url = _video_url_from_state(json.loads(raw.replace(":undefined", ":null")))
    if not video_url:
        raise RuntimeError("no video stream in note page")
    with requests.get(video_url, headers={"Referer": HOME + "/"}, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return out


PREVIEW_DIR = config.DATA / "xhs_preview"


def preview_path(note: Note) -> Path:
    """Download (once) a candidate's video into the preview cache for the dashboard."""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    return download(note.url, PREVIEW_DIR / note.note_id)


def download(url: str, out: Path) -> Path:
    """Download a note's video to `out` (.mp4)."""
    step("Download source video")
    out = out.with_suffix(".mp4")
    if out.exists() and out.stat().st_size > 0:
        log(f"cached {out.name}")
        return out
    try:
        path = _download_ytdlp(url, out)
        log(f"yt-dlp -> {path.name}")
        return path
    except Exception as e:  # noqa: BLE001
        log(f"yt-dlp failed ({type(e).__name__}: {str(e)[:120]}) — trying browser")
    time.sleep(1)
    path = _download_browser(url, out)
    log(f"browser -> {path.name}")
    return path
