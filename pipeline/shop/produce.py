"""End-to-end shopping short: Coupang link -> Xiaohongshu clip -> Korean script,
TTS and captions -> output/{date}-coupang-{productId}/final.mp4 + meta.json.

The source clip comes from (first match wins): --video (a local file you have
rights to), --xhs (a specific note URL), or an automatic Xiaohongshu search.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .. import config, state
from ..util import ffprobe_duration, log, step, write_json
from . import compose, coupang, shopscript, xhs


def _usable(path: Path) -> dict | None:
    info = compose.probe(path)
    if info["duration"] < config.SHOP_MIN_SECONDS or not info["width"]:
        log(f"rejected {path.name}: {info['duration']:.1f}s, {info['width']}x{info['height']}")
        return None
    return info


def _auto_source(product, video, keyword: str | None) -> tuple[Path, dict, dict]:
    """Search Xiaohongshu, try the best-matching note first, then the rest."""
    keywords = [keyword] if keyword else shopscript.search_keywords(product.name)
    notes: list = []
    for kw in keywords:
        try:
            notes = xhs.search_videos(kw)
        except RuntimeError as e:
            log(str(e))
            continue
        if notes:
            break
    if not notes:
        raise RuntimeError("Xiaohongshu search found nothing — pass --keyword, --xhs or --video")
    best = shopscript.pick_note(product.name, notes)
    if best < 0:
        raise RuntimeError("no candidate matches the product — pass --keyword or --xhs")
    order = [notes[best]] + [n for i, n in enumerate(notes) if i != best]
    for note in order[:4]:
        try:
            path = xhs.download(note.url, video.dir / f"source_{note.note_id}")
        except Exception as e:  # noqa: BLE001
            log(f"download failed for {note.note_id} ({e})")
            continue
        info = _usable(path)
        if info:
            return path, info, note.to_dict()
    raise RuntimeError("could not download a usable clip from the top candidates")


def get_source(product, video, xhs_url: str | None, video_path: str | None,
               keyword: str | None) -> tuple[Path, dict, dict]:
    if video_path:
        src = video.dir / ("source" + Path(video_path).suffix.lower())
        shutil.copyfile(video_path, src)
        info = _usable(src)
        if not info:
            raise RuntimeError(f"{video_path} is too short / unreadable")
        return src, info, {"local_file": str(video_path)}
    if xhs_url:
        path = xhs.download(xhs_url, video.dir / "source_xhs")
        info = _usable(path)
        if not info:
            raise RuntimeError("the given Xiaohongshu note has no usable video")
        return path, info, {"url": xhs_url}
    return _auto_source(product, video, keyword)


def _description(product, script, note: dict) -> str:
    tags = " ".join(f"#{t.lstrip('#')}" for t in script.hashtags)
    parts = [script.description.strip(), "", f"👉 제품 보러가기: {product.affiliate_url}", "",
             config.COUPANG_DISCLOSURE]
    if note.get("url"):
        who = f" @{note['author']}" if note.get("author") else ""
        parts += ["", f"영상 출처: 小红书{who} {note['url'].split('?')[0]}"]
    return "\n".join(parts + ["", tags])


def make_shop(link: str, name: str = "", xhs_url: str | None = None,
              video_path: str | None = None, keyword: str | None = None,
              instruction: str = "") -> Path:
    product = coupang.get_product(link, name=name)
    video = state.Video(f"coupang-{product.product_id or 'item'}")
    state.record_video(video, product.name, "generating")
    video.manifest["product"] = product.to_dict()
    video.save()

    src, info, note = get_source(product, video, xhs_url, video_path, keyword)
    return produce(product, video, src, info, note, instruction=instruction)


def produce(product, video, src: Path, info: dict, note: dict, instruction: str = "",
            on_stage=None) -> Path:
    """Second half of make_shop: script, voice, captions, render. Also used by the
    dashboard once the user has picked (or uploaded) the source clip."""
    stage = on_stage or (lambda s: None)
    video.manifest["source"] = {**note, "path": src.name, **info}
    video.save()
    clip_seconds = min(info["duration"], config.SHOP_MAX_SECONDS)
    log(f"source {info['width']}x{info['height']} {info['duration']:.1f}s "
        f"(script targets {clip_seconds:.1f}s)")

    frames = []
    stage("대본 작성")
    if config.SHOP_VISION and config.OPENAI_API_KEY:
        frames = shopscript.keyframes(src, clip_seconds, video.scenes_dir)
    script = shopscript.write(product.name, clip_seconds, note.get("title", ""), frames,
                              instruction=instruction)
    write_json(video.script_path, script.model_dump())

    stage("TTS 생성")
    narration = compose.narrate(script.lines, video.audio_dir / "narration.mp3")
    total = compose.LEAD_IN + ffprobe_duration(narration) + compose.TAIL
    stage("자막 타이밍")
    ass = compose.build_ass(narration, script.lines, script.hook_title, total,
                            video.dir / "captions.ass")
    stage("렌더링")
    final = compose.render(src, info, narration, ass, total, video.final_path)

    step("Copy")
    meta = {"youtube_title": script.youtube_title,
            "description": _description(product, script, note),
            "pinned_comment": f"👉 {product.name}\n{product.affiliate_url}\n\n{config.COUPANG_DISCLOSURE}",
            "hashtags": script.hashtags}
    write_json(video.dir / "meta.json", meta)
    (video.dir / "description.txt").write_text(meta["description"], encoding="utf-8")
    log(f"title: {script.youtube_title}")
    video.mark("complete", final=str(final))
    state.record_video(video, product.name, "complete")
    return final
