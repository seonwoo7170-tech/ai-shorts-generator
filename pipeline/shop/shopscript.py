"""LLM helpers for shopping shorts: Chinese search keywords, picking the best
Xiaohongshu note, and the Korean narration script (optionally grounded in
keyframes of the source clip). Falls back to simple offline output without an
OPENAI_API_KEY.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from .. import config
from ..util import log, run, step

# Korean TTS at the default tempo speaks roughly this many characters per second.
KO_CHARS_PER_SEC = 6.5


class ShopScript(BaseModel):
    hook_title: str = Field(..., description="화면 상단 고정 제목, 14자 이내")
    lines: List[str] = Field(..., min_length=3, max_length=10)
    youtube_title: str
    description: str
    short_caption: str = Field("", description="틱톡/릴스 캡션 한 줄, 40자 이내")
    hashtags: List[str]


class Keywords(BaseModel):
    keywords: List[str] = Field(..., description="2-3 short Simplified Chinese search queries")


class Pick(BaseModel):
    index: int = Field(..., description="0-based index of the best candidate, -1 if none fit")
    reason: str


def _client():
    from openai import OpenAI
    return OpenAI(api_key=config.OPENAI_API_KEY)


def _parse(model: str, messages: list, schema):
    kwargs = dict(model=model, messages=messages, response_format=schema)
    return _client().beta.chat.completions.parse(**kwargs).choices[0].message.parsed


def search_keywords(product_name: str) -> list[str]:
    if not config.OPENAI_API_KEY:
        return [product_name]
    out = _parse(config.METADATA_MODEL, [
        {"role": "system", "content": (
            "Translate a Korean shopping product title into what a Chinese shopper would "
            "type on Xiaohongshu to find real usage videos of that exact product type. "
            "Drop brand names that only exist in Korea, seller fluff, quantities and "
            "options. Return 2-3 queries, most specific first, each 2-8 Chinese characters.")},
        {"role": "user", "content": product_name},
    ], Keywords)
    log(f"xhs keywords: {out.keywords}")
    return out.keywords or [product_name]


def pick_note(product_name: str, notes: list) -> int:
    """Index of the note whose title best matches the product (most-liked fallback)."""
    if not config.OPENAI_API_KEY or len(notes) == 1:
        return 0
    listing = "\n".join(f"{i}. {n.title} (♥{n.likes})" for i, n in enumerate(notes))
    out = _parse(config.METADATA_MODEL, [
        {"role": "system", "content": (
            "Pick the Xiaohongshu video note most likely to show the given product being "
            "used or unboxed (same product type, not a haul/vlog of unrelated items). "
            "Prefer clear product demos. Return -1 if none fit.")},
        {"role": "user", "content": f"Product: {product_name}\n\nCandidates:\n{listing}"},
    ], Pick)
    log(f"picked #{out.index}: {out.reason}")
    return out.index


def keyframes(video: Path, duration: float, out_dir: Path, n: int = 4) -> list[Path]:
    frames = []
    for i in range(n):
        t = duration * (i + 0.5) / n
        f = out_dir / f"frame_{i}.jpg"
        run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
             "-vf", "scale=512:-2", "-q:v", "4", str(f)])
        frames.append(f)
    return frames


def _image_part(p: Path) -> dict:
    b64 = base64.b64encode(p.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                                               "detail": "low"}}


def _sample(product_name: str) -> ShopScript:
    return ShopScript(
        hook_title="이거 없으면 손해 🔥",
        lines=[f"아직도 이거 없이 사세요?", f"{product_name[:20]}, 써보면 바로 알아요.",
               "쓰는 법도 진짜 간단해요.", "한 번 쓰면 계속 손이 가요.",
               "링크는 프로필이랑 댓글에 있어요."],
        youtube_title=f"{product_name[:30]} #shorts",
        description=f"{product_name} 실사용 영상.",
        short_caption="이거 하나로 끝. 링크는 프로필에 👆",
        hashtags=["쿠팡추천", "꿀템", "살림템", "쇼핑", "추천템", "쿠팡"],
    )


def write(product_name: str, duration: float, note_title: str = "",
          frames: list[Path] | None = None, instruction: str = "") -> ShopScript:
    step("Shopping script (ko)")
    if not config.OPENAI_API_KEY:
        log("no OPENAI_API_KEY — using offline sample script")
        return _sample(product_name)
    lo, hi = int(duration * KO_CHARS_PER_SEC * 0.75), int(duration * KO_CHARS_PER_SEC * 0.95)
    text = (f"상품명: {product_name}\n"
            f"원본 영상 길이: {duration:.1f}초 → 내레이션 총 {lo}~{hi}자(공백 제외)\n"
            + (f"원본 샤오홍슈 제목(참고): {note_title}\n" if note_title else "")
            + ("아래 이미지는 영상의 키프레임이다. 실제로 보이는 장면 순서에 맞춰 써라.\n"
               if frames else ""))
    if instruction:
        text += f"\n추가 요청: {instruction}\n"
    content: list = [{"type": "text", "text": text}]
    content += [_image_part(f) for f in frames or []]
    system = (config.PROMPTS / "shop_script_ko.md").read_text(encoding="utf-8")
    script = _parse(config.SCRIPT_MODEL, [{"role": "system", "content": system},
                                          {"role": "user", "content": content}], ShopScript)
    chars = sum(len(ln.replace(" ", "")) for ln in script.lines)
    log(f"{len(script.lines)} lines · {chars} chars · title={script.hook_title!r}")
    return script
