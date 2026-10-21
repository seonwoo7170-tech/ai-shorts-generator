"""Korean TTS, captions and the final render for shopping shorts.

The source clip is cover-cropped to 1080x1920 when it's already near-vertical,
otherwise fit over a blurred copy of itself. Its original audio is muted (or kept
quiet via SHOP_ORIGINAL_VOLUME), the narration starts after a short lead-in, and
the clip loops if the narration outlasts it. Captions, the hook title and the
Coupang Partners disclosure are one ASS file burned in by ffmpeg.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from .. import config
from ..assemble import _ass_path_escape, _find_music
from ..captions import _align_to_script, _cc, _hex_to_ass, transcribe_words
from ..util import ffprobe_duration, log, run, step
from ..voice import _apply_tempo

W, H, FPS = config.WIDTH, config.HEIGHT, config.FPS
LEAD_IN = 0.3      # seconds before the narration starts
TAIL = 0.7         # seconds kept after it ends


# --- probing -----------------------------------------------------------------
def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True)
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        rot = int(float(sd.get("rotation", 0) or 0)) or rot
    rot = rot or int(float((v.get("tags") or {}).get("rotate", 0) or 0))
    if abs(rot) % 180 == 90:
        w, h = h, w
    return {"width": w, "height": h,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "duration": float((data.get("format") or {}).get("duration", 0) or 0)}


# --- TTS ---------------------------------------------------------------------
def _tts_openai(text: str, out: Path) -> None:
    from openai import OpenAI
    raw = out.with_name(out.stem + "_raw.mp3")
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    with client.audio.speech.with_streaming_response.create(
        model=config.TTS_MODEL, voice=config.SHOP_TTS_VOICE, input=text,
        instructions=config.SHOP_TTS_INSTRUCTIONS, response_format="mp3",
    ) as response:
        response.stream_to_file(str(raw))
    _apply_tempo(raw, out)


def _tts_edge(text: str, out: Path) -> None:
    import edge_tts
    comm = edge_tts.Communicate(text, config.SHOP_EDGE_VOICE, rate=config.SHOP_EDGE_RATE)
    asyncio.run(comm.save(str(out)))


def _tts_silent(text: str, out: Path) -> None:
    from .shopscript import KO_CHARS_PER_SEC
    dur = max(2.0, len(text.replace(" ", "")) / KO_CHARS_PER_SEC)
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", f"{dur:.3f}", "-q:a", "9", str(out)])


def narrate(lines: list[str], out: Path) -> Path:
    """One TTS pass over the whole script (better prosody than per-line clips)."""
    step(f"Voiceover (ko, {config.SHOP_TTS_BACKEND})")
    text = " ".join(ln.strip() for ln in lines)
    if out.exists():
        log(f"cached {out.name}")
    elif config.SHOP_TTS_BACKEND == "edge":
        _tts_edge(text, out)
    elif config.OPENAI_API_KEY:
        _tts_openai(text, out)
    else:
        log("no OPENAI_API_KEY — silent narration sized by a chars/sec estimate")
        _tts_silent(text, out)
    log(f"narration {ffprobe_duration(out):.2f}s")
    return out


# --- captions ----------------------------------------------------------------
def _even_words(text: str, duration: float) -> list[dict]:
    """Fallback timing (no whisper): spread tokens by character count."""
    tokens = text.split()
    total = sum(len(t) for t in tokens) or 1
    t, words = 0.0, []
    for tok in tokens:
        d = duration * len(tok) / total
        words.append({"word": tok, "start": t, "end": t + d})
        t += d
    return words


def _word_timings(narration: Path, text: str) -> list[dict]:
    try:
        words = transcribe_words(narration, language="ko")
        return _align_to_script(words, text) if words else _even_words(text, ffprobe_duration(narration))
    except Exception as e:  # noqa: BLE001 - faster-whisper missing / model download blocked
        log(f"whisper unavailable ({type(e).__name__}) — even caption timing")
        return _even_words(text, ffprobe_duration(narration))


def _group(words: list[dict], max_chars: int) -> list[list[dict]]:
    lines, cur, n = [], [], 0
    for w in words:
        word = w["word"].strip()
        if cur and n + len(word) > max_chars:
            lines.append(cur)
            cur, n = [], 0
        cur.append(w)
        n += len(word) + 1
        if word.endswith((".", "?", "!", "~", ",")):
            lines.append(cur)
            cur, n = [], 0
    if cur:
        lines.append(cur)
    return lines


def _ass_text(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(narration: Path, lines: list[str], hook_title: str, total: float,
              out: Path) -> Path:
    step("Captions (ko)")
    b = config.BRAND
    text = " ".join(ln.strip() for ln in lines)
    words = [{**w, "start": w["start"] + LEAD_IN, "end": w["end"] + LEAD_IN}
             for w in _word_timings(narration, text)]
    font, m = config.SHOP_FONT, config.CAPTION_MARGIN_H
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font},{config.SHOP_CAPTION_FONTSIZE},&H0000E1FF&,{_hex_to_ass(b['text'])},&H00000000&,&H66000000&,1,0,0,0,100,100,0,0,1,7,4,2,{m},{m},{config.SHOP_CAPTION_MARGIN_V},1
Style: Title,{font},92,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&HB4000000&,1,0,0,0,100,100,0,0,3,18,0,8,60,60,190,1
Style: Disclosure,{font},30,&H00E0E0E0&,&H00E0E0E0&,&H00000000&,&H80000000&,0,0,0,0,100,100,0,0,1,2,0,8,80,80,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [
        f"Dialogue: 1,{_cc(0)},{_cc(total)},Title,,0,0,0,,{_ass_text(hook_title)}",
        f"Dialogue: 1,{_cc(0)},{_cc(total)},Disclosure,,0,0,0,,{_ass_text(config.COUPANG_DISCLOSURE)}",
    ]
    for grp in _group(words, config.SHOP_CAPTION_MAX_CHARS):
        parts = "".join(
            f"{{\\k{max(1, int(round((w['end'] - w['start']) * 100)))}}}{_ass_text(w['word'].strip())} "
            for w in grp)
        events.append(f"Dialogue: 0,{_cc(grp[0]['start'])},{_cc(grp[-1]['end'])},Karaoke,,0,0,0,,"
                      f"{parts.strip()}")
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    log(f"{len(words)} words -> {len(events) - 2} caption lines")
    return out


# --- render ------------------------------------------------------------------
def _video_filter(src_info: dict, ass: Path) -> str:
    w, h = src_info["width"] or W, src_info["height"] or H
    subs = f"ass='{_ass_path_escape(ass)}':fontsdir='{_ass_path_escape(config.FONT_DIR)}'"
    tail = f"fps={FPS},setsar=1,format=yuv420p,{subs}[v]"
    if abs(w / h - W / H) < 0.08:          # already ~9:16 -> cover crop
        return (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},{tail}")
    return (f"[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=40:4,eq=brightness=-0.12[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{tail}")


def render(src: Path, src_info: dict, narration: Path, ass: Path, total: float,
           out: Path) -> Path:
    step("Render")
    delay = int(LEAD_IN * 1000)
    inputs = ["-stream_loop", "-1", "-i", str(src), "-i", str(narration)]
    audio = [f"[1:a]aresample=44100,adelay={delay}|{delay},apad[nar]"]
    mix = ["[nar]"]
    if config.SHOP_ORIGINAL_VOLUME > 0 and src_info["has_audio"]:
        audio.append(f"[0:a]aresample=44100,volume={config.SHOP_ORIGINAL_VOLUME:.3f}[orig]")
        mix.append("[orig]")
    music = _find_music()
    if music:
        log(f"music bed: {music.name}")
        idx = inputs.count("-i")           # index of the input added next
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        audio.append(f"[{idx}:a]aresample=44100,volume={config.SHOP_MUSIC_VOLUME:.3f}[mus]")
        mix.append("[mus]")
    audio.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
                 f"afade=t=out:st={max(0, total - 0.6):.3f}:d=0.6,"
                 f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    flt = _video_filter(src_info, ass) + ";" + ";".join(audio)
    run(["ffmpeg", "-y", *inputs, "-filter_complex", flt, "-map", "[v]", "-map", "[a]",
         "-t", f"{total:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(out)])
    log(f"final -> {out}")
    return out
