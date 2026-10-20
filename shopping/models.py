"""Product input + the shopping script the LLM returns.

ShopScene keeps the field names pipeline.voice / pipeline.assemble read
(index, narration), so the existing voice, caption and assembly stages are reused.
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

Role = Literal["hook", "problem", "hero", "usage", "benefit", "cta"]


class Product(BaseModel):
    name: str
    price: str = ""                       # e.g. "29,900"
    original_price: str = ""              # shown struck-through on the card
    url: str = ""                         # affiliate / product link
    image: str = ""                       # product photo: http(s) URL or local path
    features: List[str] = []
    category: str = ""
    target: str = ""                      # who it's for, e.g. "자취생"
    notes: str = ""                       # anything the writer must (not) say


class ShopScene(BaseModel):
    index: int = Field(..., description="1-based scene order")
    role: Role = Field(..., description="hook | problem | hero | usage | benefit | cta")
    narration: str = Field(..., description="One short spoken sentence in the target language")
    visual_prompt: str = Field(
        ..., description="ENGLISH prompt for an AI image/video generator: subject, setting, "
        "lighting, camera, vertical 9:16. Describe the product faithfully. No text in frame."
    )
    motion_prompt: str = Field(
        "", description="ENGLISH: what moves / camera move, for image-to-video"
    )
    uses_product_photo: bool = Field(
        False, description="True if this shot should animate the REAL product photo "
        "(hero/benefit close-ups) instead of inventing the product"
    )


class ShopScript(BaseModel):
    product_name: str
    slug: str = Field(..., description="short ascii kebab-case slug, e.g. 'mini-vacuum'")
    scenes: List[ShopScene] = Field(..., min_length=5, max_length=7)
    youtube_title: str
    youtube_description: str
    tiktok_caption: str
    instagram_caption: str
    pinned_comment: str = Field(..., description="Pinned comment that carries the buy link")
    hashtags: List[str]
