# AI Shorts Generator — Automated Short-Form Video Pipeline

> Turn a single topic into a finished, captioned vertical video for **YouTube Shorts, TikTok, and Instagram Reels** — script, AI visuals, voiceover, karaoke captions, music, and an optional watermark, fully automated.

**AI Shorts Generator** is an open-source, faceless short-form video maker. Give it a topic (or let it pick one) and it writes the script, generates the visuals, narrates it, burns in word-by-word captions, lays a music bed, and exports a ready-to-post `1080×1920` MP4 with per-platform titles, descriptions, and hashtags — plus a local review dashboard to preview and publish.

It works **two ways**, and you can mix them per video:

- 🎨 **Generate with AI** — cinematic images via **Flux** and motion clips via **Wan** on [fal.ai](https://fal.ai).
- 🎞️ **Pull from a clip library** — free real stock footage from **Pexels / Pixabay**, plus a reusable semantic library so you generate a shot once and reuse it forever (**match-then-generate**).

> 🛠️ *A weekend project, shared openly in case it's useful to you too. Fork it, break it, build on it.*

<p align="center">
  <img alt="MIT License" src="https://img.shields.io/badge/license-MIT-blue.svg">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue.svg">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg">
  <img alt="PRs Welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg">
</p>

---

## ✨ Features

- **Topic → finished video**, end to end, in one command.
- **Two visual modes:** AI generation (fal Flux + Wan) and/or free stock footage (Pexels/Pixabay).
- **Reusable clip library** with semantic matching — reuse a good shot across videos instead of paying to regenerate it.
- **AI voiceover** (OpenAI `gpt-4o-mini-tts`) with a tunable, punchy delivery.
- **Word-by-word karaoke captions** auto-aligned with `faster-whisper`.
- **Music bed** with automatic ducking under the voice.
- **Optional watermark** (your logo + disclaimer) and an **optional branded outro / end card**.
- **Per-platform metadata** — YouTube title + description, TikTok caption, X caption, and hashtags.
- **Batch mode** — generate a week of content from a topic backlog.
- **Local review dashboard** (Flask) — preview, swap clips, pick music, copy captions, download.
- **Niche-agnostic** — set `CONTENT_NICHE` for any subject (finance, fitness, tech, motivation…), or stay purely topic-driven, and swap the writer's whole voice with **prompt presets**.
- **Graceful degradation** — missing an API key or a GPU? The pipeline falls back instead of crashing.

## 🧠 How it works

```
topic ─▶ script (OpenAI, structured JSON)
      ─▶ visuals:  match clip library ──hit──▶ reuse clip
                                     └─miss─▶ generate (Flux image ─▶ Wan motion) ─▶ add to library
      ─▶ voiceover (gpt-4o-mini-tts)
      ─▶ captions (faster-whisper, word-level)
      ─▶ assemble (ffmpeg): Ken Burns / motion + music + watermark + outro
      ─▶ output/{date}-{slug}/final.mp4  +  per-platform titles/descriptions/hashtags
```

Each scene is a cinematic moving image; the only on-screen text is the karaoke captions, so the **voice carries the message**. Output lands in `output/{date}-{slug}/final.mp4` (1080×1920) alongside a `script.json` with all the platform copy.

## 🚀 Quickstart

**Prerequisites:** Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html) on your `PATH`.

```bash
git clone https://github.com/AbdullahNaveed/ai-shorts-generator.git
cd ai-shorts-generator

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium      # for crisp HTML-rendered overlays

cp .env.example .env                        # then add your API keys
python run.py setup                         # one-time: Chromium + overlays
```

Add at least an `OPENAI_API_KEY` to `.env`. Add `FAL_KEY` for AI visuals and/or a free `PEXELS_API_KEY` for stock footage. (No keys at all? The pipeline still runs in an offline smoke-test mode with a sample script and silent timing.)

```bash
python run.py make "why your mornings decide the rest of your day"
# → output/2026-06-24-why-your-mornings.../final.mp4
```

## 🎬 Usage

```bash
python run.py make ["topic"]     # one video on a topic (or auto-pick if omitted)
python run.py batch 7            # a week's worth from data/topics.txt
python run.py topics import      # load the backlog from data/topics.txt
python run.py fetch-library 20   # pull FREE Pexels/Pixabay stock into the library
python run.py gen-library 10     # AI-generate library clips from library/inventory.csv (fal)
python run.py library-stats      # show library counts / usage
python run.py list               # list generated videos
python run.py serve              # open the review dashboard at http://127.0.0.1:5000
python run.py shop "<coupang link>"  # Coupang → Xiaohongshu → Korean shopping short (see below)
```

On Windows you can also double-click **`start.bat`** to launch the dashboard and **`stop.bat`** to shut it down.

### The review dashboard

`python run.py serve` opens a local web app where you can:

- write/approve/regenerate a script with your own notes,
- **preview which library clip each scene will use and swap it**,
- fetch stock or AI-generate new clips into the library,
- fit a music track over a video and adjust its volume,
- copy the per-platform caption + hashtags and download the MP4.

## 🎨 Two ways to get footage

| Mode | How | Cost | Set in `.env` |
|---|---|---|---|
| **Free Ken Burns** | AI/stock still + zoom/pan motion | free motion | `ANIMATE=none` (default) |
| **Free stock footage** | Pull real clips from Pexels/Pixabay | free | `PEXELS_API_KEY=...` |
| **AI images** | Flux stills via fal.ai | ~$0.025 / image | `IMAGE_BACKEND=fal` |
| **AI motion** | Wan image-to-video via fal.ai | ~$0.15 / clip | `ANIMATE=all` |
| **Local images** | SDXL-Turbo on your GPU | free | `IMAGE_BACKEND=local` (+ `requirements-gpu.txt`) |

The **clip library** ties it together: every generated/fetched clip is embedded and cataloged, so the next time a scene is similar enough it **reuses an existing clip** instead of paying to make a new one (tune `MATCH_THRESHOLD`).

## 🛒 Shopping shorts (Coupang Partners × Xiaohongshu)

쿠팡 파트너스 링크 하나로 **샤오홍슈(小红书) 실사용 영상 → 한국어 대본 → TTS → 카라오케 자막 → 1080×1920 MP4 + 설명란/고정댓글 문구**까지 만듭니다.

```
쿠팡 링크 ─▶ 리다이렉트 추적 → productId, 상품명(og:title)
          ─▶ 상품명 → 중국어 검색어(LLM) ─▶ 샤오홍슈 검색(로그인된 브라우저) → 영상 노트 후보
          ─▶ LLM이 상품과 가장 맞는 노트 선택 ─▶ yt-dlp 다운로드 (실패 시 브라우저 폴백)
          ─▶ 키프레임 4장 + 상품명 → 한국어 쇼핑 대본(영상 길이에 맞춘 글자 수)
          ─▶ TTS (OpenAI 또는 무료 edge-tts) ─▶ faster-whisper 단어 타이밍 자막
          ─▶ ffmpeg: 9:16 크롭/블러 배경 + 상단 훅 제목 + 파트너스 고지 + 자막 + BGM
          ─▶ output/{date}-coupang-{productId}/final.mp4, meta.json, description.txt
```

```bash
pip install -r requirements.txt && python -m playwright install chromium
python run.py xhs-login                       # 최초 1회: 뜨는 브라우저에서 샤오홍슈 QR 로그인

python run.py shop "https://link.coupang.com/a/XXXXX"
python run.py shop "https://link.coupang.com/a/XXXXX" --name "스테인리스 마늘 다지기"  # 쿠팡이 차단할 때
python run.py shop "https://link.coupang.com/a/XXXXX" --keyword "压蒜器"             # 검색어 직접 지정
python run.py shop "https://link.coupang.com/a/XXXXX" --xhs "https://www.xiaohongshu.com/explore/..."
python run.py shop "https://link.coupang.com/a/XXXXX" --video my_clip.mp4           # 직접 촬영/허락받은 영상
python run.py shop "..." --note "자취생 타깃으로, 더 웃기게"                           # 대본 추가 요청
```

**대시보드에서 후보 고르기** — `python run.py serve` → **Shop** 탭. 링크 입력 → 샤오홍슈 검색 결과를 썸네일·좋아요·작성자와 함께 보여주고(AI 추천 표시), ▶로 미리 본 뒤 카드를 골라 만들면 됩니다. 게시물 URL 직접 입력이나 내 영상 업로드도 됩니다.

**폰에서 쓰기** — PC에서 `DASHBOARD_HOST=0.0.0.0 python run.py serve`로 띄우고 같은 와이파이의 폰 브라우저에서 `http://<PC IP>:5000/shop`을 열면 됩니다. "홈 화면에 추가"하면 앱처럼 전체화면으로 뜹니다. (무거운 작업—브라우저 검색, 다운로드, ffmpeg, whisper—은 PC가 하고 폰은 조작만 합니다.)

- 한국어 자막 폰트: `assets/fonts/`에 Noto Sans KR·Pretendard 등을 넣고 `SHOP_FONT`에 패밀리명 지정(Windows 기본값은 맑은 고딕).
- 원본 소리는 기본 음소거(`SHOP_ORIGINAL_VOLUME`), `assets/music/`에 BGM을 넣으면 깔립니다.
- 설명란에는 파트너스 링크, **공정위 추천·보증 고지문**, 원본 출처(작성자·노트 URL)가 자동으로 들어갑니다. 쇼츠 설명란 링크는 클릭이 잘 안 되므로 `meta.json`의 `pinned_comment`를 고정댓글로 쓰세요.

> ⚠️ **저작권 주의.** 샤오홍슈 영상의 저작권은 원작자에게 있고, 샤오홍슈 약관은 자동 수집을 금지합니다. 허락 없이 재업로드해 수익(제휴 수수료)을 내면 저작권 침해 신고·채널 경고, 유튜브 *재사용 콘텐츠* 정책에 따른 수익화 거절 대상이 될 수 있습니다. 원작자에게 사용 허락을 받거나, 셀러/브랜드가 제공한 영상·직접 촬영한 영상(`--video`)을 쓰는 것을 권장합니다. 이 도구는 출처 표기를 자동으로 넣지만 출처 표기가 허락을 대신하지는 않습니다.

## 💧 Watermark & outro

- **Watermark** (on by default): drop a square `assets/logo/logo.png` and it's overlaid bottom-right on every video; add `BRAND_DISCLAIMER=` for a footer line. Set `WATERMARK=false` to disable. With no logo and no disclaimer, nothing is stamped.
- **Outro / end card** (off by default): set `OUTRO=true` with your `BRAND_NAME`, `BRAND_URL`, `BRAND_TAGLINE`, and `logo.png` to stitch a 3-second branded end card (with a spoken call-to-action) onto every video.

## ⚙️ Configuration

Everything is environment-driven — see [`.env.example`](.env.example) for the full list. Highlights:

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_API_KEY` | – | Script, voiceover, captions alignment, embeddings |
| `FAL_KEY` | – | AI images (Flux) + AI motion (Wan) |
| `PEXELS_API_KEY` / `PIXABAY_API_KEY` | – | Free stock footage |
| `IMAGE_BACKEND` | `fal` | `fal` (Flux) or `local` (SDXL on GPU) |
| `ANIMATE` | `none` | `none` (free Ken Burns), `all`, or `N` |
| `CONTENT_NICHE` | – | Focus the writer (e.g. `personal finance`) |
| `SCRIPT_PROMPT` | – | Swap in a custom writer preset from `prompts/presets/` |
| `TTS_VOICE` | `onyx` | OpenAI TTS voice |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` for captions |
| `WATERMARK` / `OUTRO` | `true` / `false` | Toggle the overlays |
| `TARGET_SECONDS` | `20` | Spoken length target |

Deeper defaults (palette, timings, models, caption styling) live in [`pipeline/config.py`](pipeline/config.py).

### ✍️ Custom script presets

The scriptwriter's persona lives in [`prompts/scriptgen_system.md`](prompts/scriptgen_system.md). Want a different voice or framework? Drop a Markdown file in [`prompts/presets/`](prompts/presets/) and select it by setting `SCRIPT_PROMPT` in `.env` (the filename, without `.md`). One generic example ships there — copy it, make it yours, and switch presets per run. `CONTENT_NICHE` layers a subject focus on top of whichever preset is active.

## 🗂️ Project layout

```
run.py              CLI orchestrator
pipeline/           config, models, scriptgen, images, animate, stock,
                    library, match, voice, captions, assemble, cards, outro
dashboard/          Flask review UI (app.py + templates)
templates/          HTML/CSS for the watermark + outro overlays
prompts/            scriptwriter system prompt + presets/ (swap the writer's voice)
assets/             fonts, your logo, music, generated brand overlays
library/            clip catalog (index.db) + clips/ + images/ + inventory CSVs
data/topics.txt     your topic backlog
output/             generated videos
```

## 💰 Cost per video (rough)

| Setup | What | Approx |
|---|---|---|
| Script + voice + captions only | OpenAI text + TTS | **~$0.02** |
| + free stock or local SDXL stills | Pexels / GPU | ~$0.02 |
| + Flux AI images (5 scenes) | fal images | ~$0.15 |
| + Wan AI motion (5 scenes) | fal motion | ~$0.75 |

Start cheap (`ANIMATE=none`, stock footage) and turn the dials up where it matters.

## ❓ FAQ

**Do I need a GPU?** No. Use `IMAGE_BACKEND=fal` and `WHISPER_DEVICE=cpu`. A GPU only helps for free local SDXL images and faster captions.

**Can I run it 100% free?** Mostly — OpenAI text/TTS is cents per video, and stock footage + Ken Burns motion are free. AI images/motion are the only paid pieces, and they're opt-in.

**Is auto-posting included?** No — you review and post manually (the dashboard makes it one click to grab captions + the MP4). A publishing backend is a welcome PR.

**What content niche is it for?** Any. Set `CONTENT_NICHE` or just pass topics. The bundled examples are niche-neutral.

## 🤝 Contributing

This started as a weekend project and is shared as-is for anyone to use, fork, or build on. Issues and PRs are welcome — auto-posting backends, new image/i2v models, extra stock sources, and caption styles are all great starting points.

Want to contribute, collaborate, or just say hi? Reach out on **[LinkedIn](https://www.linkedin.com/in/abdullahnaveed0007/)**.

## 📄 License

[MIT](LICENSE) © AbdullahNaveed. Bundled fonts (Inter, Sora) are under the SIL Open Font License — see [`assets/fonts/README.md`](assets/fonts/README.md). You are responsible for the licensing of any stock footage, music, or AI-generated media you produce or redistribute.

---

<sub>Keywords: AI video generator · faceless video generator · short-form video automation · YouTube Shorts generator · TikTok video maker · Instagram Reels automation · text-to-video · AI voiceover · auto captions · fal.ai · Flux · Wan · Stable Diffusion · Pexels stock footage · Python content pipeline.</sub>
