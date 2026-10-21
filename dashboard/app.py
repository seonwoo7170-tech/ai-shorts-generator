"""Review dashboard for the AI short-form video pipeline.

- Home: produced videos, preview + per-platform captions + download.
- Library: every generated image/animation in the catalog.
- Create: a guided workflow — write the script, approve or regenerate with your
  notes, then produce the video (background job with live status).
- Music selector: pick a track and fit it over an existing video.
"""
from __future__ import annotations

import threading
import uuid
from pathlib import Path

import hmac
import os
import secrets

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session

from pipeline import config, drafts, library, scriptgen, state
from pipeline.util import read_json, slugify

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 600 * 1024 * 1024      # uploaded source clips
JOBS: dict[str, dict] = {}


# ---------- auth (only when DASHBOARD_PASSWORD is set, i.e. cloud deploys) ----------
@app.before_request
def _require_login():
    if not config.DASHBOARD_PASSWORD or session.get("ok"):
        return None
    if request.endpoint in ("login", "webmanifest", "static"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "login required"}), 401
    return redirect("/login?next=" + request.path)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), config.DASHBOARD_PASSWORD):
            session.permanent = True
            session["ok"] = True
            return redirect(request.args.get("next") or "/shop")
        error = "비밀번호가 틀렸어요"
    return render_template("login.html", brand=config.BRAND, error=error)

_AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def _spawn(fn) -> str:
    """Run fn(set_stage) in a background thread; return a job id to poll."""
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"stage": "queued", "vid": None, "error": None}

    def _run():
        try:
            fn(lambda s, **kw: JOBS[job_id].update(stage=s, **kw))
            JOBS[job_id].setdefault("stage", "done")
            if JOBS[job_id]["stage"] not in ("done", "error"):
                JOBS[job_id]["stage"] = "done"
        except Exception as e:  # noqa: BLE001
            JOBS[job_id].update(stage="error", error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return job_id


# ---------- helpers ----------
def _videos() -> list[dict]:
    items = []
    if config.OUTPUT.exists():
        for d in sorted(config.OUTPUT.iterdir(), reverse=True):
            if (d / "script.json").exists() and (d / "final.mp4").exists():
                data = read_json(d / "script.json")
                if (d / "manifest.json").exists():     # shopping shorts: product name
                    data.setdefault("topic", read_json(d / "manifest.json")
                                    .get("product", {}).get("name", d.name))
                items.append({"id": d.name, "topic": data.get("topic", d.name),
                              "title": data.get("youtube_title", "")})
    return items


def _video_obj(vid: str):
    d = config.OUTPUT / vid
    if not (d / "script.json").exists():
        abort(404)
    return state.Video(vid[11:], vid[:10])   # {YYYY-MM-DD}-{slug}


def _music_files() -> list[str]:
    return sorted(f.name for f in config.MUSIC_DIR.iterdir()
                  if f.suffix.lower() in _AUDIO_EXTS) if config.MUSIC_DIR.exists() else []


# ---------- pages ----------
@app.route("/")
def index():
    videos = _videos()
    vids = {v["id"] for v in videos}
    all_drafts = drafts.list_drafts()
    # "In-progress" = work that isn't a finished, still-present video. A draft whose
    # produced video already exists belongs under Videos, not the drafts shelf.
    in_progress = [d for d in all_drafts
                   if not (d.get("stage") == "produced" and d.get("vid") in vids)]
    draft_by_vid = {d["vid"]: d["id"] for d in all_drafts if d.get("vid")}
    return render_template("index.html", videos=videos, drafts=in_progress,
                           draft_by_vid=draft_by_vid, brand=config.BRAND)


@app.get("/api/drafts")
def api_drafts():
    return jsonify(drafts.list_drafts())


@app.get("/api/draft/<draft_id>")
def api_draft_get(draft_id: str):
    d = drafts.load(draft_id)
    return jsonify(d) if d else (jsonify({"error": "not found"}), 404)


@app.post("/api/draft/save")
def api_draft_save():
    return jsonify({"id": drafts.save(request.get_json(force=True))})


@app.post("/api/draft/delete")
def api_draft_delete():
    return jsonify({"ok": drafts.delete(request.get_json(force=True).get("id", ""))})


@app.route("/v/<vid>")
def video(vid: str):
    d = config.OUTPUT / vid
    if not (d / "script.json").exists():
        abort(404)
    s = read_json(d / "script.json")
    manifest = read_json(d / "manifest.json") if (d / "manifest.json").exists() else {}
    if (d / "meta.json").exists():            # shopping short: merge the platform copy
        meta = read_json(d / "meta.json")
        s = {**s, "shop": True, "topic": manifest.get("product", {}).get("name", vid),
             "youtube_description": meta.get("description", ""),
             "pinned_comment": meta.get("pinned_comment", ""),
             "tiktok_caption": meta.get("tiktok_caption", ""),
             "reels_caption": meta.get("reels_caption", ""),
             "bio_link": meta.get("bio_link", ""), "x_caption": "",
             "scenes": [{"index": i + 1, "narration": ln} for i, ln in enumerate(s.get("lines", []))]}
    return render_template("video.html", vid=vid, s=s, brand=config.BRAND,
                           music=_music_files(), current_music=manifest.get("music", ""),
                           current_volume=manifest.get("music_volume", 0.16))


@app.route("/library")
def library_page():
    clips = library.all_clips()
    groups = sorted({c["grp"] for c in clips})
    return render_template("library.html", clips=clips, groups=groups,
                           stats=library.stats(), brand=config.BRAND)


@app.route("/create")
def create_page():
    return render_template("create.html", brand=config.BRAND)


@app.route("/shop")
def shop_page():
    return render_template("shop.html", brand=config.BRAND)


@app.route("/xhs")
def xhs_login_page():
    return render_template("xhs_login.html", brand=config.BRAND)


@app.post("/api/xhs/login/start")
def api_xhs_login_start():
    from pipeline.shop.xhs import WEB_LOGIN
    WEB_LOGIN.start()
    return jsonify({"status": WEB_LOGIN.status})


@app.get("/api/xhs/login/status")
def api_xhs_login_status():
    from pipeline.shop.xhs import COOKIES_TXT, WEB_LOGIN
    return jsonify({"status": WEB_LOGIN.status, "error": WEB_LOGIN.error,
                    "has_qr": bool(WEB_LOGIN.qr), "cookies": COOKIES_TXT.exists()})


@app.get("/api/xhs/login/qr.png")
def api_xhs_login_qr():
    from flask import Response
    from pipeline.shop.xhs import WEB_LOGIN
    if not WEB_LOGIN.qr:
        abort(404)
    return Response(WEB_LOGIN.qr, mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.route("/manifest.webmanifest")
def webmanifest():
    """Lets a phone 'Add to Home Screen' the dashboard as a standalone app."""
    return jsonify({"name": "Shorts Studio", "short_name": "Shorts", "start_url": "/shop",
                    "display": "standalone", "background_color": config.BRAND["bg"],
                    "theme_color": config.BRAND["bg"], "icons": []})


# ---------- media ----------
@app.route("/media/<vid>/final.mp4")
def media(vid: str):
    f = config.OUTPUT / vid / "final.mp4"
    return send_file(f, mimetype="video/mp4", conditional=True) if f.exists() else abort(404)


@app.route("/download/<vid>")
def download(vid: str):
    f = config.OUTPUT / vid / "final.mp4"
    return send_file(f, as_attachment=True, download_name=f"{vid}.mp4") if f.exists() else abort(404)


@app.route("/media/music/<path:name>")
def media_music(name: str):
    f = config.MUSIC_DIR / Path(name).name
    return send_file(f, conditional=True) if f.exists() else abort(404)


@app.route("/media/preview/<vid>")
def media_preview(vid: str):
    from pipeline.assemble import build_preview_base
    try:
        f = build_preview_base(_video_obj(vid))
    except FileNotFoundError:
        abort(404)
    return send_file(f, mimetype="video/mp4", conditional=True)


@app.route("/media/lib/<cid>.mp4")
def lib_clip(cid: str):
    f = config.LIB_CLIPS / f"{cid}.mp4"
    return send_file(f, mimetype="video/mp4", conditional=True) if f.exists() else abort(404)


@app.route("/media/libimg/<cid>")
def lib_img(cid: str):
    for ext in (".jpg", ".png"):
        f = config.LIB_IMAGES / f"{cid}{ext}"
        if f.exists():
            return send_file(f, conditional=True)
    abort(404)


# ---------- workflow API ----------
@app.post("/api/script")
def api_script():
    data = request.get_json(force=True)
    topic = (data.get("topic") or "").strip()   # blank => auto-pick a topic
    if data.get("target"):
        config.TARGET_SECONDS = int(data["target"])
    script = scriptgen.generate(topic, instruction=data.get("instruction", ""))
    return jsonify(script.model_dump())


@app.post("/api/match")
def api_match():
    """Preview which library clip each scene will use, with swap candidates."""
    from pipeline import match
    from pipeline.models import Script

    script = Script(**request.get_json(force=True)["script"])
    used: set[str] = set()
    scenes = []
    for sc in script.scenes:
        clip, score = match.match_scene(sc, used)
        cands = match.candidates(sc.image_prompt, used)
        chosen = clip["id"] if clip else (cands[0]["id"] if cands else None)
        if chosen:
            used.add(chosen)
        scenes.append({"index": sc.index, "narration": sc.narration,
                       "image_prompt": sc.image_prompt, "chosen": chosen,
                       "auto_score": round(score, 3), "candidates": cands})
    return jsonify({"scenes": scenes})


@app.post("/api/produce")
def api_produce():
    from pipeline.models import Script
    from pipeline.produce import make

    data = request.get_json(force=True)
    topic = data.get("topic", "")
    script = Script(**data["script"])
    clips = {str(k): v for k, v in (data.get("clips") or {}).items() if v}
    draft_id = data.get("draft")

    def job(set_stage):
        if data.get("voice"):
            config.TTS_VOICE = data["voice"]
        if data.get("tempo"):
            config.SPEECH_TEMPO = float(data["tempo"])
        make(topic, script=script, on_stage=lambda s: set_stage(s), clip_overrides=clips)
        vid = f"{state.Video(script.slug).date}-{script.slug}"
        if draft_id:
            d = drafts.load(draft_id)
            if d:
                d.update(stage="produced", vid=vid)
                drafts.save(d)
        set_stage("done", vid=vid)

    return jsonify({"job": _spawn(job)})


@app.get("/api/job/<job_id>")
def api_job(job_id: str):
    return jsonify(JOBS.get(job_id, {"stage": "unknown"}))


# ---------- shopping shorts (Coupang -> Xiaohongshu) ----------
SHOP_SESSIONS: dict[str, dict] = {}   # sid -> {product, notes}


@app.post("/api/shop/product")
def api_shop_product():
    """Step 1: resolve the Coupang link. Returns a session id for the next steps."""
    from pipeline.shop import coupang

    data = request.get_json(force=True)
    link = (data.get("link") or "").strip()
    if not link:
        return jsonify({"error": "link required"}), 400
    try:
        product = coupang.get_product(link, name=(data.get("name") or "").strip())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400
    sid = uuid.uuid4().hex[:8]
    SHOP_SESSIONS[sid] = {"product": product, "notes": {}}
    return jsonify({"sid": sid, "product": product.to_dict()})


@app.post("/api/shop/search")
def api_shop_search():
    """Step 2: search Xiaohongshu (background job; result carries the candidates)."""
    from pipeline.shop import shopscript, xhs

    data = request.get_json(force=True)
    sess = SHOP_SESSIONS.get(data.get("sid", ""))
    if not sess:
        return jsonify({"error": "unknown session"}), 404
    keyword = (data.get("keyword") or "").strip()

    def job(set_stage):
        product = sess["product"]
        keywords = [keyword] if keyword else shopscript.search_keywords(product.name)
        notes = []
        for kw in keywords:
            set_stage(f"샤오홍슈 검색: {kw}")
            try:
                notes = xhs.search_videos(kw)
            except RuntimeError:
                continue
            if notes:
                break
        if not notes:
            raise RuntimeError("검색 결과가 없습니다. 로그인(xhs-login) 상태나 검색어를 확인하세요.")
        best = shopscript.pick_note(product.name, notes) if len(notes) > 1 else 0
        sess["notes"] = {n.note_id: n for n in notes}
        set_stage("done", keywords=keywords, best=notes[best].note_id if best >= 0 else None,
                  candidates=[n.to_dict() for n in notes])

    return jsonify({"job": _spawn(job)})


@app.get("/api/shop/thumb/<sid>/<note_id>")
def api_shop_thumb(sid: str, note_id: str):
    """Proxy a candidate's cover image (the CDN wants a xiaohongshu Referer)."""
    import requests as rq
    from flask import Response

    note = (SHOP_SESSIONS.get(sid) or {}).get("notes", {}).get(note_id)
    if not note or not note.cover:
        abort(404)
    r = rq.get(note.cover, headers={"Referer": "https://www.xiaohongshu.com/"}, timeout=15)
    return Response(r.content, mimetype=r.headers.get("Content-Type", "image/jpeg"))


@app.get("/api/shop/preview/<sid>/<note_id>")
def api_shop_preview(sid: str, note_id: str):
    """Download a candidate (cached) so it can be played in the picker."""
    from pipeline.shop import xhs

    note = (SHOP_SESSIONS.get(sid) or {}).get("notes", {}).get(note_id)
    if not note:
        abort(404)
    try:
        f = xhs.preview_path(note)
    except Exception:  # noqa: BLE001
        abort(502)
    return send_file(f, mimetype="video/mp4", conditional=True)


@app.post("/api/shop/produce")
def api_shop_produce():
    """Step 3: produce with the chosen note, a pasted note URL, or an uploaded file."""
    import shutil

    from pipeline.shop import compose, xhs
    from pipeline.shop.produce import produce

    sid = request.form.get("sid", "")
    sess = SHOP_SESSIONS.get(sid)
    if not sess:
        return jsonify({"error": "unknown session"}), 404
    product = sess["product"]
    note_id = request.form.get("note", "")
    xhs_url = (request.form.get("xhs_url") or "").strip()
    instruction = (request.form.get("note_text") or "").strip()
    upload = request.files.get("file")
    video = state.Video(f"coupang-{product.product_id or 'item'}")
    video.manifest["product"] = product.to_dict()
    video.save()
    state.record_video(video, product.name, "generating")
    uploaded = None
    if upload and upload.filename:
        uploaded = video.dir / ("source" + Path(upload.filename).suffix.lower())
        upload.save(uploaded)

    def job(set_stage):
        if uploaded:
            src, note = uploaded, {"local_file": upload.filename}
        elif note_id and note_id in sess["notes"]:
            n = sess["notes"][note_id]
            set_stage("원본 다운로드")
            cached = xhs.preview_path(n)
            src = video.dir / f"source_{n.note_id}.mp4"
            shutil.copyfile(cached, src)
            note = n.to_dict()
        elif xhs_url:
            set_stage("원본 다운로드")
            src, note = xhs.download(xhs_url, video.dir / "source_xhs"), {"url": xhs_url}
        else:
            raise RuntimeError("후보를 고르거나 영상을 올려주세요")
        info = compose.probe(src)
        if info["duration"] < config.SHOP_MIN_SECONDS or not info["width"]:
            raise RuntimeError(f"영상이 너무 짧거나 읽을 수 없습니다 ({info['duration']:.1f}s)")
        video.manifest["source"] = {**note, "path": src.name, **info}
        video.save()
        produce(product, video, src, info, note, instruction=instruction, on_stage=set_stage)
        set_stage("done", vid=video.dir.name)

    return jsonify({"job": _spawn(job)})


# ---------- inventory management ----------
@app.post("/api/library/fetch")
def api_library_fetch():
    """Add clips by fetching stock footage for a query (free)."""
    from pipeline import stock

    data = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400
    row = {"id": f"stock_{slugify(query)[:28]}", "group": data.get("group", "custom"),
           "lighting": "", "query": query, "description": data.get("description") or query}
    n = int(data.get("n", 5))

    def job(set_stage):
        set_stage(f"fetching '{query}'")
        stock.fetch_variants(row, n)

    return jsonify({"job": _spawn(job)})


@app.post("/api/library/generate")
def api_library_generate():
    """Add a clip by AI-generating it (Flux + Wan) — costs fal credit."""
    from pipeline import animate, images, library as lib
    from pipeline.assemble import _prepare_motion  # noqa: F401 (ensure module ok)

    data = request.get_json(force=True)
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    motion = data.get("motion", "")
    group = data.get("group", "generated")

    def job(set_stage):
        cid = f"gen_{slugify(prompt)[:24]}"
        img = config.LIB_IMAGES / f"{cid}.png"
        set_stage("generating image")
        url = images.generate_image(prompt, img)
        set_stage("animating")
        raw = config.LIB_CLIPS / f"{cid}_raw.mp4"
        animate.i2v(img, url, motion, raw)
        clip = config.LIB_CLIPS / f"{cid}.mp4"
        from pipeline.produce import _normalize_clip
        _normalize_clip(raw, clip)
        raw.unlink(missing_ok=True)
        from pipeline.util import ffprobe_duration
        row = {"id": cid, "group": group, "lighting": "", "style": "generated",
               "description": prompt, "image_prompt": prompt, "motion_prompt": motion}
        lib.add_clip(row, img, clip, ffprobe_duration(clip), lib.embed(prompt))

    return jsonify({"job": _spawn(job)})


# ---------- video / music management ----------
@app.post("/api/video/delete")
def api_video_delete():
    import shutil
    vid = request.get_json(force=True).get("vid", "")
    d = config.OUTPUT / vid
    if d.exists() and d.parent == config.OUTPUT:
        shutil.rmtree(d, ignore_errors=True)
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 404


@app.post("/api/music/delete")
def api_music_delete():
    name = request.get_json(force=True).get("name", "")
    f = config.MUSIC_DIR / Path(name).name
    if f.exists():
        f.unlink()
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 404


@app.get("/api/clips")
def api_clips():
    """All clips (for the visual picker): id, description, group."""
    return jsonify([{"id": c["id"], "description": c["description"], "grp": c["grp"]}
                    for c in library.all_clips()])


@app.post("/api/clip/delete")
def api_clip_delete():
    cid = request.get_json(force=True).get("id", "")
    return jsonify({"ok": library.delete_clip(cid)})


@app.post("/api/clip/update")
def api_clip_update():
    data = request.get_json(force=True)
    return jsonify({"ok": library.update_description(data.get("id", ""), data.get("description", ""))})


@app.get("/api/music")
def api_music():
    return jsonify({"tracks": _music_files()})


@app.post("/api/remix")
def api_remix():
    from pipeline.assemble import remix_music

    data = request.get_json(force=True)
    video = _video_obj(data["vid"])
    track = data.get("music") or ""
    music_path = (config.MUSIC_DIR / track) if track else None
    if music_path and not music_path.exists():
        return jsonify({"error": "track not found"}), 400
    remix_music(video, music_path,
                volume=float(data.get("volume", 0.16)),
                start=float(data.get("start", 0.0)))
    return jsonify({"ok": True})


@app.post("/api/upload-music")
def api_upload_music():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(_AUDIO_EXTS):
        return jsonify({"error": "audio file required"}), 400
    dest = config.MUSIC_DIR / Path(f.filename).name
    f.save(dest)
    return jsonify({"ok": True, "name": dest.name})


def run_server(host: str | None = None, port: int | None = None) -> None:
    host = host or config.DASHBOARD_HOST      # 0.0.0.0 = reachable from your phone / the internet
    port = port or config.DASHBOARD_PORT
    print(f"\nShorts Studio -> http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_server()
