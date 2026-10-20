# 쇼핑 쇼츠 자동화 (Meta AI · Vibes · Krea · Dola)

상품 정보(JSON) 하나를 넣으면 대본 → 장면별 AI 영상 → 음성 → 자막 → 가격 카드 → 업로드 문구까지 만들어
`output/<날짜>-<slug>/final.mp4` (1080×1920)로 뽑아줍니다.

## 4개 AI의 역할

| 도구 | 연동 방식 | 기본 담당 장면 | 이유 |
|---|---|---|---|
| **Krea** (krea.ai) | **API 완전 자동** | `hero`, `benefit` (상품 클로즈업) | 공개 API가 있음. 실제 상품 사진을 시작 프레임으로 image-to-video (Kling) → 상품이 왜곡되지 않음 |
| **Vibes** (vibes.ai) | 프롬프트 핸드오프 | `hook` (첫 1~2초) | 트렌디한 숏폼 AI 영상/리믹스에 강함 → 스크롤 멈추게 하는 훅 |
| **Meta AI** (meta.ai) | 프롬프트 핸드오프 | `problem` (공감 장면) | 무료 이미지 생성(+Animate) → 일상 공감 컷 |
| **Dola** (dola.com) | 프롬프트 핸드오프 | `usage` (사용 장면) | Seedance 기반 사람 동작이 자연스러운 영상 |
| 카드 (로컬) | 자동, AI 아님 | `cta` (마지막) | 실제 상품 사진 + 정확한 가격 + "링크는 고정 댓글" |

> **왜 Meta AI / Vibes / Dola는 반자동인가?** 세 서비스 모두 공개 개발자 API가 없는 소비자용 앱입니다.
> 브라우저 봇으로 자동 조작하면 이용약관 위반 소지가 있고, 로그인/UI가 바뀌면 바로 깨집니다.
> 그래서 파이프라인이 **복사-붙여넣기용 프롬프트 패킷**을 만들어 주고, 받은 파일을 폴더에 넣으면 나머지는 자동으로 이어집니다.
> 장면 배정은 `.env`의 `SHOP_ROUTE`로 바꿀 수 있습니다 (예: 전부 Krea로 → 완전 무인 자동).

## 흐름

```
상품 JSON ─▶ 대본(OpenAI, 한국어 내레이션 + 영어 비주얼 프롬프트)
          ─▶ 장면 배정 (SHOP_ROUTE)
          ─▶ Krea 장면: API로 바로 생성   ─┐
          ─▶ CTA 가격 카드: 로컬 렌더     ─┤
          ─▶ Meta/Vibes/Dola: HANDOFF.md ─┤  ← 파일 받아서 폴더에 넣기
                                           ▼
             음성(TTS) + 카라오케 자막 + 음악 ─▶ final.mp4 + upload.txt
```

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env      # OPENAI_API_KEY, KREA_API_KEY 입력 (FAL_KEY는 선택)
```

1. 상품 파일 만들기: `data/products.example.json` 복사해서 수정 (여러 개 넣으면 일괄 처리)
   - `image`: 상품 사진 URL 또는 로컬 경로. **http(s) URL을 권장** (Krea가 URL로 이미지를 받음.
     로컬 파일이면 `FAL_KEY`가 있을 때 업로드해서 사용, 없으면 해당 장면은 사진 Ken Burns로 대체)
   - `url`: 쿠팡 파트너스 등 제휴 링크 → 설명/고정댓글에 자동 삽입 + 대가성 문구 자동 추가
2. 실행
   ```bash
   python run.py shop make data/my_products.json
   ```
   Krea 장면과 가격 카드가 만들어지고 `output/<폴더>/handoff/HANDOFF.md`가 생성됩니다.
3. `HANDOFF.md`를 열어 장면별 프롬프트를 각 사이트에 붙여넣고, 결과를 다운로드해서
   지정된 이름(`handoff/vibes/scene_01.mp4` 등)으로 저장하거나 아래 명령으로 복사:
   ```bash
   python run.py shop drop "output/<폴더>" 1=~/Downloads/vibes.mp4 2=~/Downloads/meta.png 4=~/Downloads/dola.mp4
   ```
   영상(.mp4/.mov/.webm)과 이미지(.png/.jpg/.webp) 모두 됩니다. 이미지는 줌/팬 효과가 들어갑니다.
4. 완성
   ```bash
   python run.py shop resume "output/<폴더>"          # 빠진 파일이 있으면 다시 대기
   python run.py shop resume "output/<폴더>" --auto   # 빠진 장면은 Krea(또는 상품사진)로 채움
   ```
5. `final.mp4` 업로드, `upload.txt`의 제목/설명/고정댓글/해시태그 복사.

**완전 무인 모드:** `python run.py shop make data/my_products.json --auto`.
수동 파일을 기다리지 않고 Meta/Vibes/Dola 장면을 `SHOP_MANUAL_FALLBACK`(기본 Krea)로 채워 바로 완성합니다.
또는 `SHOP_ROUTE=hook=krea,problem=krea,hero=krea,usage=krea,benefit=krea,cta=card`.

`python run.py shop status`로 대기 중(awaiting_assets) / 완료 목록을 볼 수 있습니다.

## 설정 (.env)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `KREA_API_KEY` | — | Krea API 토큰 |
| `KREA_VIDEO_MODEL` | `/generate/video/kling/kling-2.5` | 영상 모델 엔드포인트 (Krea가 슬러그를 바꾸면 여기만 수정) |
| `KREA_IMAGE_MODEL` | `/generate/image/krea/krea-2/medium` | 이미지 모델 엔드포인트 |
| `KREA_MAX_VIDEOS` | `3` | 쇼츠 1개당 Krea 영상 생성 최대 횟수 (비용 상한). 상품 사진 장면이 우선 |
| `SHOP_ROUTE` | `hook=vibes,problem=meta,hero=krea,usage=dola,benefit=krea,cta=card` | 장면 역할 → 도구 |
| `SHOP_MANUAL_FALLBACK` | `krea` | `--auto`일 때 빈 장면 채우기: `krea` 또는 `photo` |
| `SHOP_LANGUAGE` | `Korean` | 내레이션 언어 |
| `SHOP_TARGET_SECONDS` | `25` | 목표 길이(초) |
| `SHOP_CTA_TEXT` | `구매 링크는 고정 댓글에!` | 가격 카드 버튼 문구 |
| `SHOP_DISCLOSURE` | 쿠팡 파트너스 문구 | 제휴 링크가 있을 때 설명에 자동 추가 |
| `SHOP_FONT` / `CAPTION_FONT` | 자동 탐색 | 한글 폰트. 자막은 `CAPTION_FONT=Noto Sans KR`처럼 **한글 폰트 필수** (기본 Sora엔 한글 없음) |

한글 폰트: [Noto Sans KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR)을 `assets/fonts/`에 넣고
`.env`에 `CAPTION_FONT=Noto Sans KR`을 지정하세요. Windows는 맑은 고딕을 자동으로 찾습니다(카드용).

## 주의사항 (꼭 읽기)

- **대가성 표기:** 제휴 링크가 있으면 `upload.txt` 설명에 공정위 대가성 문구가 자동으로 들어갑니다. 지우지 마세요.
- **AI 콘텐츠 표시:** YouTube/Instagram/TikTok 모두 사실적인 AI 생성 영상에 라벨 표시를 요구합니다. 업로드할 때 켜세요.
- **과장 금지:** 대본 프롬프트가 입력에 없는 스펙, 할인, 리뷰, 효능을 지어내지 않도록 막고 있지만, 업로드 전에 한 번 확인하세요.
- **각 서비스 약관:** Meta AI·Vibes·Dola 생성물의 상업적 이용 조건은 각 서비스 약관을 따릅니다.
  Meta AI 이미지에는 보이는/보이지 않는 워터마크가 들어갈 수 있습니다.
- **Krea API 스펙:** 엔드포인트와 필드(`prompt`, `aspect_ratio`, `duration`, `start_image`, `/jobs/{id}` 폴링,
  `result.urls`)는 Krea 문서 기준입니다. 에러가 나면 [Krea API 문서](https://www.krea.ai/docs)에서 모델 경로를 확인해
  `KREA_VIDEO_MODEL`만 바꾸면 됩니다.

## 파일 구조

```
shopping/
  config.py     SHOP_* / KREA_* 설정, 장면 배정
  models.py     Product, ShopScene, ShopScript
  product.py    상품 JSON/URL 로드, 사진 → 9:16 캔버스
  scriptgen.py  쇼핑 대본 (prompts/shopping_system.md)
  krea.py       Krea REST 클라이언트 (submit → /jobs 폴링 → 다운로드)
  handoff.py    Meta AI / Vibes / Dola 프롬프트 패킷 + 받은 파일 수집
  cards.py      가격/CTA 카드 (PIL)
  produce.py    전체 오케스트레이션 (start / resume / drop / status)
```
음성, 자막, 음악, 워터마크, 최종 합성은 기존 `pipeline/`을 그대로 재사용합니다.
