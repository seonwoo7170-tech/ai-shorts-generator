"""Manual-provider handoff for Meta AI, Vibes and Dola.

These three are consumer apps with no public API, so instead of scripting their
websites (fragile, and against their terms) the pipeline writes a prompt packet:

    output/<video>/handoff/HANDOFF.md        what to make where (copy-paste prompts)
    output/<video>/handoff/<provider>/       drop the downloaded file here as scene_NN.*

`shop resume` then picks the files up. Images get Ken Burns; videos are cut to fit.
"""
from __future__ import annotations

from pathlib import Path

from pipeline.util import write_json

from . import config
from .models import ShopScene, ShopScript

MANUAL = ("meta", "vibes", "dola")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")

_HOWTO = {
    "meta": ("Meta AI", "Open meta.ai, type `/imagine` (or Create → Image), paste the prompt, "
             "pick 9:16. Optional: press **Animate** for a short clip. Download it."),
    "vibes": ("Vibes", "Open vibes.ai → Create, paste the prompt (or remix a similar trending "
              "clip and edit the prompt). Download the video."),
    "dola": ("Dola", "Open dola.com → AI video (Seedance) or image. Paste the prompt, choose "
             "9:16. For product shots, attach the product photo as the reference image. "
             "Download the result."),
}


def provider_dir(video_dir: Path, provider: str) -> Path:
    d = video_dir / "handoff" / provider
    d.mkdir(parents=True, exist_ok=True)
    return d


def _scene_name(scene: ShopScene) -> str:
    return f"scene_{scene.index:02d}"


def write_packet(video_dir: Path, script: ShopScript, plan: dict[int, str],
                 product_photo: Path | None) -> Path | None:
    """Write HANDOFF.md + prompts.json for every scene routed to a manual provider."""
    jobs = [(s, plan[s.index]) for s in script.scenes if plan[s.index] in MANUAL]
    if not jobs:
        return None
    root = video_dir / "handoff"
    root.mkdir(exist_ok=True)
    lines = [f"# Handoff: {script.product_name}", "",
             "Make each asset below, download it, and save it under the exact filename "
             "shown (any image or video extension is fine). Then run:", "",
             f"    python run.py shop resume \"{video_dir}\"", ""]
    if product_photo:
        lines += [f"Product photo for reference uploads: `{product_photo}`", ""]
    packet = []
    for provider in MANUAL:
        mine = [s for s, p in jobs if p == provider]
        if not mine:
            continue
        title, howto = _HOWTO[provider]
        lines += [f"## {title} ({config.PROVIDER_LINKS[provider]})", "", howto, ""]
        for s in mine:
            target = provider_dir(video_dir, provider) / f"{_scene_name(s)}.mp4"
            prompt = s.visual_prompt + (f" Motion: {s.motion_prompt}" if s.motion_prompt else "")
            lines += [f"### Scene {s.index} · {s.role}",
                      f"- Narration: {s.narration}",
                      f"- Save as: `{target.relative_to(video_dir)}` (.png/.jpg also OK)",
                      "", "```", prompt, "```", ""]
            packet.append({"scene": s.index, "role": s.role, "provider": provider,
                           "link": config.PROVIDER_LINKS[provider], "prompt": prompt,
                           "save_as": str(target.relative_to(video_dir))})
    out = root / "HANDOFF.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    write_json(root / "prompts.json", packet)
    return out


def find_asset(video_dir: Path, provider: str, scene: ShopScene) -> Path | None:
    """The dropped file for a scene: handoff/<provider>/scene_NN.* (or handoff/scene_NN.*)."""
    name = _scene_name(scene)
    for d in (video_dir / "handoff" / provider, video_dir / "handoff"):
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.stem.lower() == name and f.suffix.lower() in IMAGE_EXTS + VIDEO_EXTS:
                return f
    return None


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS
