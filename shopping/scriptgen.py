"""Product -> ShopScript via OpenAI structured outputs (offline sample without a key)."""
from __future__ import annotations

from pipeline import config as base
from pipeline.util import log, slugify, step

from . import config
from .models import Product, ShopScript
from .product import fallback_slug


def _sample(product: Product) -> ShopScript:
    """Offline script so the whole pipeline can be smoke-tested without a key."""
    price = f"{product.price}{config.SHOP_CURRENCY}" if product.price else "가격"
    name = product.name
    return ShopScript(
        product_name=name,
        slug=fallback_slug(product),
        scenes=[
            dict(index=1, role="hook", narration="이거 진짜 왜 이제 알았지?",
                 visual_prompt="fast whip-pan into a surprised young person in a bright modern "
                 "apartment, dramatic reaction, vertical 9:16, photoreal",
                 motion_prompt="quick whip pan, energetic handheld"),
            dict(index=2, role="problem", narration="매번 이것 때문에 짜증났던 분들 많죠.",
                 visual_prompt="frustrated person dealing with an everyday mess at home, soft "
                 "window light, vertical 9:16, photoreal",
                 motion_prompt="slow push in on the frustrated face"),
            dict(index=3, role="hero", narration=f"그래서 찾은 게 바로 {name}.",
                 visual_prompt=f"premium studio product shot of {name}, clean seamless "
                 "background, soft rim light, vertical 9:16",
                 motion_prompt="slow 3/4 orbit around the product, light sweep",
                 uses_product_photo=True),
            dict(index=4, role="usage", narration="쓰는 법도 간단해서 바로 적응돼요.",
                 visual_prompt=f"natural person using {name} at home, hands in focus, warm "
                 "daylight, vertical 9:16, photoreal",
                 motion_prompt="natural hand motion, gentle handheld camera"),
            dict(index=5, role="benefit", narration="한 번 써보면 예전으로 못 돌아가요.",
                 visual_prompt=f"close-up detail of {name}, macro, shallow depth of field, "
                 "vertical 9:16",
                 motion_prompt="slow slide along the product", uses_product_photo=True),
            dict(index=6, role="cta", narration=f"지금 {price}, 링크는 고정 댓글에 있어요.",
                 visual_prompt=f"{name} product card", motion_prompt=""),
        ],
        youtube_title=f"{name[:30]} 써보고 놀람 #shorts",
        youtube_description=f"{name} 솔직 소개.",
        tiktok_caption=f"{name} 이거 하나면 끝",
        instagram_caption=f"{name} 실사용 후기",
        pinned_comment="👉 구매 링크: {link}",
        hashtags=["쇼핑", "추천템", "살림템", "꿀템", "shorts", "리뷰"],
    )


def generate(product: Product) -> ShopScript:
    step(f"Shopping script — {product.name!r}")
    if not base.OPENAI_API_KEY:
        log("no OPENAI_API_KEY — using offline sample script")
        return _sample(product)

    from openai import OpenAI

    client = OpenAI(api_key=base.OPENAI_API_KEY)
    system = (base.PROMPTS / "shopping_system.md").read_text(encoding="utf-8")
    user = (
        f"Narration language: {config.SHOP_LANGUAGE}\n"
        f"Target spoken length: ~{config.SHOP_TARGET_SECONDS} seconds total.\n\n"
        f"Product JSON:\n{product.model_dump_json(indent=2, exclude={'image', 'url'})}"
    )
    kwargs = dict(model=base.SCRIPT_MODEL,
                  messages=[{"role": "system", "content": system},
                            {"role": "user", "content": user}],
                  response_format=ShopScript)
    if not base.SCRIPT_MODEL.startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["temperature"] = 0.9
    script = client.beta.chat.completions.parse(**kwargs).choices[0].message.parsed
    script.slug = slugify(script.slug) if slugify(script.slug) != "short" else fallback_slug(product)
    for i, s in enumerate(script.scenes, 1):
        s.index = i
    log(f"{len(script.scenes)} scenes · slug={script.slug}")
    return script
