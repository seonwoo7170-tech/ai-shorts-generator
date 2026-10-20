"""Shopping short, end to end:

  product -> script -> route scenes to providers
          -> Krea scenes generated now (API)
          -> Meta AI / Vibes / Dola scenes: prompt packet, wait for dropped files
          -> CTA card (real photo + price)
          -> voice + captions + music (pipeline) -> final.mp4 + upload copy

`start` stops at "awaiting_assets" when manual files are missing (unless
fill_missing); `resume` continues from the same folder once they are dropped in.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from pipeline import config as base
from pipeline import state, voice
from pipeline.assemble import assemble
from pipeline.cards import render_fallback_bg
from pipeline.util import log, read_json, step, write_json

from . import cards, config, handoff, krea, scriptgen
from .models import Product, ShopScene, ShopScript
from .product import fetch_photo, portrait_canvas


class Job:
    """One shopping short's folder: product.json, script.json, manifest 'shop' block."""

    def __init__(self, video: state.Video, product: Product, script: ShopScript):
        self.video, self.product, self.script = video, product, script
        shop = video.manifest.setdefault("shop", {})
        self.plan: dict[int, str] = {int(k): v for k, v in shop.get("plan", {}).items()}
        self.assets: dict[int, dict] = {int(k): v for k, v in shop.get("assets", {}).items()}
        self.krea_videos = int(shop.get("krea_videos", 0))
        self.photo: Path | None = Path(shop["photo"]) if shop.get("photo") else None
        self.canvas: Path | None = Path(shop["canvas"]) if shop.get("canvas") else None
        self._canvas_url = shop.get("canvas_url", "")

    @property
    def dir(self) -> Path:
        return self.video.dir

    def save(self) -> None:
        self.video.manifest["shop"] = {
            "plan": self.plan, "assets": self.assets, "krea_videos": self.krea_videos,
            "photo": str(self.photo or ""), "canvas": str(self.canvas or ""),
            "canvas_url": self._canvas_url,
        }
        self.video.save()

    def set_asset(self, scene: ShopScene, path: Path, kind: str, source: str) -> None:
        self.assets[scene.index] = {"path": str(path), "kind": kind, "source": source}
        self.save()
        log(f"scene {scene.index} ({scene.role}): {source} {kind} -> {path.name}")

    def product_start_url(self) -> str:
        """URL of the product photo for Krea image-to-video ('' if none possible)."""
        if self._canvas_url:
            return self._canvas_url
        try:
            # the 9:16 canvas keeps the product un-cropped; needs an upload (FAL_KEY)
            self._canvas_url = krea.public_url(self.canvas) if self.canvas else ""
        except krea.KreaError:
            self._canvas_url = self.product.image if self.product.image.startswith("http") else ""
        self.save()
        return self._canvas_url


# --- scene sources ---------------------------------------------------------------
def _scene_path(job: Job, scene: ShopScene, ext: str) -> Path:
    return job.video.scenes_dir / f"scene_{scene.index:02d}{ext}"


def _photo_still(job: Job, scene: ShopScene, source: str = "photo") -> None:
    """Ken Burns on the real product photo (or a neutral background)."""
    if job.canvas and job.canvas.exists():
        job.set_asset(scene, job.canvas, "image", source)
    else:
        out = render_fallback_bg(_scene_path(job, scene, ".png"))
        job.set_asset(scene, out, "image", "fallback")


def _krea_scene(job: Job, scene: ShopScene) -> None:
    if not krea.available():
        log(f"scene {scene.index}: no KREA_API_KEY")
        return _photo_still(job, scene)
    prompt = scene.visual_prompt + (f" {scene.motion_prompt}" if scene.motion_prompt else "")
    try:
        if scene.uses_product_photo and job.canvas:
            start = job.product_start_url()
            if not start or job.krea_videos >= config.KREA_MAX_VIDEOS:
                return _photo_still(job, scene)
            out = krea.video(prompt, _scene_path(job, scene, ".mp4"), start_image_url=start)
            job.krea_videos += 1
            return job.set_asset(scene, out, "video", "krea")
        if job.krea_videos < config.KREA_MAX_VIDEOS:
            out = krea.video(prompt, _scene_path(job, scene, ".mp4"))
            job.krea_videos += 1
            return job.set_asset(scene, out, "video", "krea")
        out, _ = krea.image(scene.visual_prompt, _scene_path(job, scene, "_raw.png"))
        from pipeline.images import _cover_crop
        final = _scene_path(job, scene, ".png")
        _cover_crop(out, final)
        out.unlink(missing_ok=True)
        job.set_asset(scene, final, "image", "krea")
    except Exception as e:  # noqa: BLE001 - never lose the whole short to one scene
        log(f"scene {scene.index}: krea failed ({e}) -> product photo")
        _photo_still(job, scene)


def _card_scene(job: Job, scene: ShopScene) -> None:
    out = cards.render_cta(job.product, job.photo, _scene_path(job, scene, "_card.png"))
    job.set_asset(scene, out, "image", "card")


def _collect_manual(job: Job, fill_missing: bool) -> list[ShopScene]:
    """Pick up dropped Meta AI / Vibes / Dola files; return scenes still missing."""
    missing = []
    for scene in job.script.scenes:
        provider = job.plan[scene.index]
        if provider not in handoff.MANUAL:
            continue
        found = handoff.find_asset(job.dir, provider, scene)
        if found:
            job.set_asset(scene, found, "video" if handoff.is_video(found) else "image", provider)
        elif scene.index in job.assets and Path(job.assets[scene.index]["path"]).exists():
            continue                      # already filled by an earlier fallback
        elif fill_missing:
            log(f"scene {scene.index}: no {provider} file -> fallback ({config.MANUAL_FALLBACK})")
            if config.MANUAL_FALLBACK == "krea" and krea.available():
                _krea_scene(job, scene)
            else:
                _photo_still(job, scene)
        else:
            missing.append(scene)
    return missing


# --- public entry points ---------------------------------------------------------
def route(script: ShopScript) -> dict[int, str]:
    plan = {}
    for s in script.scenes:
        provider = config.ROUTE.get(s.role, "krea")
        if provider not in ("krea", "card", *handoff.MANUAL):
            log(f"unknown provider {provider!r} for role {s.role} -> krea")
            provider = "krea"
        plan[s.index] = provider
    return plan


def start(product: Product, fill_missing: bool = False) -> Path:
    script = scriptgen.generate(product)
    video = state.Video(script.slug)
    write_json(video.dir / "product.json", product.model_dump())
    write_json(video.script_path, script.model_dump())
    state.record_video(video, product.name, "generating")
    job = Job(video, product, script)
    job.assets, job.krea_videos = {}, 0           # fresh run (same slug + date reuses the folder)

    step("Product photo")
    try:
        job.photo = fetch_photo(product, video.dir)
        if job.photo:
            job.canvas = portrait_canvas(job.photo, video.scenes_dir / "product_canvas.png")
    except Exception as e:  # noqa: BLE001 - bad URL / not an image: continue without it
        log(f"could not use product photo ({e})")
        job.photo = job.canvas = None
    job.plan = route(script)
    job.save()
    log("route: " + ", ".join(f"{s.index}:{s.role}->{job.plan[s.index]}" for s in script.scenes))

    step("Krea scenes (API) + CTA card")
    # real-product shots first, so they get the KREA_MAX_VIDEOS budget before b-roll
    for scene in sorted(script.scenes, key=lambda s: not s.uses_product_photo):
        if job.plan[scene.index] == "krea":
            _krea_scene(job, scene)
        elif job.plan[scene.index] == "card":
            _card_scene(job, scene)

    packet = handoff.write_packet(video.dir, script, job.plan, job.photo)
    if packet:
        log(f"handoff packet -> {packet}")
    return _finish_or_wait(job, fill_missing)


def resume(video_dir: Path, fill_missing: bool = False) -> Path:
    video_dir = Path(video_dir).resolve()
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)", video_dir.name)
    if not m:
        raise SystemExit(f"not a video folder: {video_dir}")
    video = state.Video(m.group(2), date=m.group(1))
    product = Product(**read_json(video.dir / "product.json"))
    script = ShopScript(**read_json(video.script_path))
    return _finish_or_wait(Job(video, product, script), fill_missing)


def _finish_or_wait(job: Job, fill_missing: bool) -> Path:
    step("Manual assets (Meta AI / Vibes / Dola)")
    missing = _collect_manual(job, fill_missing)
    if missing:
        state.record_video(job.video, job.product.name, "awaiting_assets")
        job.video.manifest["status"] = "awaiting_assets"
        job.save()
        log(f"{len(missing)} scene(s) waiting for files: "
            + ", ".join(f"{s.index}({job.plan[s.index]})" for s in missing))
        log(f"open {job.dir / 'handoff' / 'HANDOFF.md'}, drop the files, then run "
            f"`python run.py shop resume \"{job.dir}\"` (add --auto to fill gaps)")
        return job.dir / "handoff" / "HANDOFF.md"
    return _assemble(job)


def _assemble(job: Job) -> Path:
    images: dict[int, Path] = {}
    motion: dict[int, Path] = {}
    for scene in job.script.scenes:
        a = job.assets.get(scene.index)
        if not a or not Path(a["path"]).exists():
            _photo_still(job, scene)
            a = job.assets[scene.index]
        (motion if a["kind"] == "video" else images)[scene.index] = Path(a["path"])

    base.TTS_INSTRUCTIONS = config.SHOP_TTS_INSTRUCTIONS
    audio_info = voice.synthesize(job.video.audio_dir, job.script)
    final = assemble(job.video, job.script, images, audio_info, motion_clips=motion,
                     want_captions=bool(base.OPENAI_API_KEY))
    _write_upload_copy(job)
    job.video.manifest["status"] = "complete"
    job.video.mark("complete", final=str(final))
    state.record_video(job.video, job.product.name, "complete")
    return final


def _write_upload_copy(job: Job) -> None:
    s, p = job.script, job.product
    link = p.url or "(링크)"
    tags = " ".join("#" + t.lstrip("#") for t in s.hashtags)
    desc = "\n\n".join(x for x in (s.youtube_description, f"👉 {link}",
                                   config.SHOP_DISCLOSURE if p.url else "", tags) if x)
    sources = sorted({a["source"] for a in job.assets.values()})
    text = (f"[YouTube 제목]\n{s.youtube_title}\n\n[YouTube 설명]\n{desc}\n\n"
            f"[고정 댓글]\n{s.pinned_comment.replace('{link}', link)}\n\n"
            f"[TikTok]\n{s.tiktok_caption}\n{tags}\n\n[Instagram]\n{s.instagram_caption}\n{tags}\n\n"
            f"[사용된 AI 소스] {', '.join(sources)}\n"
            "※ AI 생성 영상이 포함되어 있으면 업로드 시 플랫폼의 'AI 생성 콘텐츠' 표시를 켜세요.\n")
    (job.dir / "upload.txt").write_text(text, encoding="utf-8")
    log(f"upload copy -> {job.dir / 'upload.txt'}")


def status() -> list[dict]:
    """Shopping shorts and how many manual files each still needs."""
    rows = []
    for d in sorted(base.OUTPUT.glob("*/product.json"), reverse=True):
        man = read_json(d.parent / "manifest.json") if (d.parent / "manifest.json").exists() else {}
        rows.append({"dir": str(d.parent), "status": man.get("status", "?")})
    return rows


def import_dropped(video_dir: Path, files: list[str]) -> None:
    """Convenience: copy downloaded files into place by scene number, e.g.
    `shop drop <dir> 1=~/Downloads/vibes.mp4 2=~/Downloads/meta.png`."""
    video_dir = Path(video_dir)
    plan = read_json(video_dir / "manifest.json").get("shop", {}).get("plan", {})
    for spec in files:
        idx, _, src = spec.partition("=")
        provider = plan.get(idx) or plan.get(str(int(idx)))
        if provider not in handoff.MANUAL:
            log(f"scene {idx} is not a manual scene (provider={provider}); skipped")
            continue
        src_p = Path(src).expanduser()
        dst = handoff.provider_dir(video_dir, provider) / f"scene_{int(idx):02d}{src_p.suffix.lower()}"
        shutil.copy2(src_p, dst)
        log(f"scene {idx}: {src_p.name} -> {dst.relative_to(video_dir)}")

